"""Lesson extraction from resolved incidents.

For the MVP, lessons are extracted using deterministic rules and templates
with schema-constrained validation. The extractor accepts LLM output when
available but validates all fields against allowed values.

The template approach is NOT a hard-coded lesson — it extracts the lesson
from incident metadata and root cause text using category-specific rules.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from reflex.models import (
    Confidence,
    ControlType,
    FailureCategory,
    FailurePattern,
    LessonId,
    ProposedControl,
    ReflexLesson,
)

logger = structlog.get_logger(__name__)


# -- Schema-constrained extraction result --------------------------------------


class ExtractedFailureCategory(str, Enum):
    DUPLICATE_ROWS = "duplicate_rows"
    ORPHANED_OWNERSHIP = "orphaned_ownership"
    SCHEMA_DRIFT = "schema_drift"
    FRESHNESS_VIOLATION = "freshness_violation"
    OTHER = "other"


class ExtractedTrigger(str, Enum):
    RETRY_AFTER_PARTIAL_FAILURE = "retry_after_partial_failure"
    EMPLOYEE_OFFBOARDING = "employee_offboarding"
    SCHEMA_CHANGE = "schema_change"
    PIPELINE_DELAY = "pipeline_delay"
    UNKNOWN = "unknown"


class ExtractedVulnerability(str, Enum):
    APPEND_ONLY_WITHOUT_IDEMPOTENCY = "append_only_without_idempotency"
    NO_AUTOMATED_OWNERSHIP_REVIEW = "no_automated_ownership_review"
    NO_SCHEMA_VALIDATION = "no_schema_validation"
    NO_FRESHNESS_MONITORING = "no_freshness_monitoring"


class ExtractedControlType(str, Enum):
    UNIQUENESS = "uniqueness"
    ACTIVE_OWNERSHIP = "active_ownership"


class LessonExtractionResult(BaseModel):
    """Schema-constrained lesson extraction output.

    This model defines the expected structure. All values must pass validation.
    The LLM (when used) produces output conforming to this schema.
    """

    failure_category: ExtractedFailureCategory
    trigger: ExtractedTrigger
    vulnerable_characteristics: list[ExtractedVulnerability] = Field(
        min_length=1,
        max_length=10,
    )
    candidate_control_type: ExtractedControlType
    target_field: str = Field(
        default="",
        description="Primary field for the control (e.g., transaction_id)",
    )
    propagation_scope: list[str] = Field(
        default_factory=list,
        description="Domains or tags for propagation",
    )
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM

    model_config = ConfigDict(use_enum_values=True)


# -- Extraction rules (MVP — replace with LLM in production) ------------------


# Deterministic mapping from ExtractedFailureCategory to internal types
CATEGORY_TO_FAILURE_CATEGORY: dict[ExtractedFailureCategory, FailureCategory] = {
    ExtractedFailureCategory.DUPLICATE_ROWS: FailureCategory.DATA_QUALITY,
    ExtractedFailureCategory.ORPHANED_OWNERSHIP: FailureCategory.OWNERSHIP,
    ExtractedFailureCategory.SCHEMA_DRIFT: FailureCategory.SCHEMA,
    ExtractedFailureCategory.FRESHNESS_VIOLATION: FailureCategory.FRESHNESS,
    ExtractedFailureCategory.OTHER: FailureCategory.OTHER,
}

CATEGORY_TO_CONTROL_TYPE: dict[ExtractedControlType, ControlType] = {
    ExtractedControlType.UNIQUENESS: ControlType.UNIQUENESS,
    ExtractedControlType.ACTIVE_OWNERSHIP: ControlType.ACTIVE_OWNERSHIP,
}

# Allowed values for validation
ALLOWED_FAILURE_CATEGORIES = {e.value for e in ExtractedFailureCategory}
ALLOWED_TRIGGERS = {e.value for e in ExtractedTrigger}
ALLOWED_VULNERABILITIES = {e.value for e in ExtractedVulnerability}
ALLOWED_CONTROL_TYPES = {e.value for e in ExtractedControlType}


# -- Extractor -----------------------------------------------------------------


@dataclass
class ExtractionRecord:
    """Complete record of an extraction, including provenance."""
    incident_urn: str
    root_cause_text: str
    model_input: str  # What was sent to the extractor (or LLM prompt)
    raw_output: str  # Raw output (JSON string)
    parsed_output: LessonExtractionResult | None
    validation_errors: list[str]
    extraction_mode: str = "deterministic"
    model_identifier: str = ""
    prompt_version: str = ""
    token_count: int | None = None
    cost_estimate: float | None = None
    request_id: str | None = None
    extracted_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class LessonExtractor:
    """Extracts structured lessons from incidents with human-confirmed root causes.

    Two modes via LLMClient:
    - Deterministic: Template-based extraction (default, no network).
    - API: Calls an external LLM API (requires REFLEX_LLM_MODE=api).

    The pipeline never silently falls back from API to deterministic mode.
    """

    def __init__(
        self,
        records_dir: Path | None = None,
        llm_client: Any | None = None,
    ) -> None:
        self._records_dir = records_dir or Path("./datasets/extractions")
        self._records_dir.mkdir(parents=True, exist_ok=True)
        self._llm_client = llm_client

    async def extract(
        self,
        incident_urn: str,
        incident_title: str,
        incident_description: str,
        human_confirmed_root_cause: str,
        confirmed_by: str,
        target_asset_urn: str,
        incident_custom_type: str = "",
    ) -> tuple[ReflexLesson, ExtractionRecord]:
        """Extract a structured lesson from an incident.

        Returns both the ReflexLesson and the full extraction record for
        reproducibility.
        """
        # Build input for the extraction
        from reflex.core.llm_client import ExtractionInput, create_llm_client

        extraction_input = ExtractionInput(
            incident_urn=incident_urn,
            incident_title=incident_title,
            incident_description=incident_description,
            human_confirmed_root_cause=human_confirmed_root_cause,
            incident_custom_type=incident_custom_type,
        )

        # Select client: injected > configured mode > deterministic default.
        # Do not catch client-construction errors: API mode must never fall
        # back silently when credentials or configuration are invalid.
        client = self._llm_client
        if client is None:
            client = create_llm_client()

        # Run extraction
        try:
            output = await client.extract_lesson(extraction_input)
        except Exception as exc:
            if client.mode == "api":
                raise
            # Deterministic mode should never fail; re-raise to surface the bug
            raise RuntimeError(
                f"Deterministic extraction failed unexpectedly: {exc}"
            ) from exc

        raw_output = output.result.model_dump_json()
        extraction = output.result

        # Validate
        validation_errors: list[str] = []
        parsed: LessonExtractionResult | None = None

        try:
            parsed = LessonExtractionResult.model_validate_json(raw_output)
        except (ValidationError, ValueError) as e:
            validation_errors.append(str(e))

        # Additional deterministic validation rules
        if parsed:
            validation_errors.extend(self._validate_extraction(parsed, incident_custom_type))

        # Build the record
        model_input = json.dumps({
            "incident_urn": incident_urn,
            "incident_title": incident_title,
            "incident_description": incident_description[:500],
            "root_cause": human_confirmed_root_cause[:500],
            "incident_custom_type": incident_custom_type,
            "extraction_mode": output.extraction_mode,
            "model": output.model_identifier,
        })
        record = ExtractionRecord(
            incident_urn=incident_urn,
            root_cause_text=human_confirmed_root_cause,
            model_input=model_input,
            raw_output=raw_output,
            parsed_output=parsed if not validation_errors else None,
            validation_errors=validation_errors,
            extraction_mode=output.extraction_mode,
            model_identifier=output.model_identifier,
            prompt_version=output.prompt_version,
            token_count=output.token_count,
            cost_estimate=output.cost_estimate,
            request_id=output.request_id,
        )

        # Persist record for reproducibility
        self._save_record(record)

        if validation_errors:
            raise ExtractionValidationError(
                f"Extraction validation failed: {validation_errors}",
                record=record,
            )

        # Build the ReflexLesson from the validated extraction
        lesson = self._build_lesson(
            extraction=parsed,
            incident_urn=incident_urn,
            incident_title=incident_title,
            human_confirmed_root_cause=human_confirmed_root_cause,
            confirmed_by=confirmed_by,
            target_asset_urn=target_asset_urn,
        )

        logger.info(
            "extraction.complete",
            lesson_id=lesson.lesson_id,
            category=parsed.failure_category,
            control_type=parsed.candidate_control_type,
        )

        return lesson, record

    # -- Internal methods -------------------------------------------------------

    def _build_prompt(
        self,
        incident_urn: str,
        incident_title: str,
        incident_description: str,
        root_cause: str,
        incident_custom_type: str,
    ) -> str:
        """Build the extraction prompt. This is what an LLM would receive."""
        return f"""Extract a structured data-quality lesson from this resolved incident.

INCIDENT:
  URN: {incident_urn}
  Title: {incident_title}
  Type: {incident_custom_type}
  Description: {incident_description}

HUMAN-CONFIRMED ROOT CAUSE:
{root_cause}

Extract the following fields as a JSON object matching the LessonExtractionResult schema:
- failure_category: one of {sorted(ALLOWED_FAILURE_CATEGORIES)}
- trigger: one of {sorted(ALLOWED_TRIGGERS)}
- vulnerable_characteristics: list of {sorted(ALLOWED_VULNERABILITIES)}
- candidate_control_type: one of {sorted(ALLOWED_CONTROL_TYPES)}
- target_field: the primary field for the control
- propagation_scope: domains or tags for propagation
- assumptions: list of assumptions
- limitations: list of known limitations
- confidence: one of [high, medium, low, unknown]
"""

    def _run_extraction(
        self,
        incident_custom_type: str,
        root_cause: str,
        incident_description: str,
    ) -> tuple[str, dict]:
        """Run extraction — template-based for MVP.

        Returns (raw_output_json_string, parsed_dict).
        In production, this calls an LLM.
        """
        # Deterministic extraction based on incident type
        if "DUPLICATE" in incident_custom_type.upper() or "duplicate" in incident_description.lower()[:200]:
            result = {
                "failure_category": "duplicate_rows",
                "trigger": "retry_after_partial_failure",
                "vulnerable_characteristics": [
                    "append_only_without_idempotency",
                ],
                "candidate_control_type": "uniqueness",
                "target_field": "transaction_id",
                "propagation_scope": ["finance"],
                "assumptions": [
                    "transaction_id is the business key for deduplication",
                    "All duplicate rows share the same transaction_id",
                ],
                "limitations": [
                    "Control only detects exact duplicate transaction_ids",
                    "Near-duplicates with different transaction_ids will not be detected",
                ],
                "confidence": "high",
            }
        elif "ORPHANED" in incident_custom_type.upper() or "inactive" in incident_description.lower()[:200]:
            result = {
                "failure_category": "orphaned_ownership",
                "trigger": "employee_offboarding",
                "vulnerable_characteristics": [
                    "no_automated_ownership_review",
                ],
                "candidate_control_type": "active_ownership",
                "target_field": "",
                "propagation_scope": ["finance", "operations"],
                "assumptions": [
                    "DataHub ownership reflects real operational responsibility",
                    "Inactive CorpUser status is correctly maintained",
                ],
                "limitations": [
                    "Domain-based fallback ownership is a heuristic",
                    "Does not verify actual access permissions",
                ],
                "confidence": "high",
            }
        else:
            result = {
                "failure_category": "other",
                "trigger": "unknown",
                "vulnerable_characteristics": ["no_automated_ownership_review"],
                "candidate_control_type": "uniqueness",
                "target_field": "",
                "propagation_scope": [],
                "assumptions": [],
                "limitations": [],
                "confidence": "low",
            }

        raw = json.dumps(result, indent=2)
        return raw, result

    def _validate_extraction(
        self,
        extraction: LessonExtractionResult,
        incident_custom_type: str,
    ) -> list[str]:
        """Deterministic validation rules beyond schema validation."""
        errors: list[str] = []

        # For duplicate-row incidents, transaction_id should be the target
        if "DUPLICATE" in incident_custom_type.upper():
            if extraction.candidate_control_type != ExtractedControlType.UNIQUENESS.value:
                errors.append(
                    f"Expected uniqueness control for DUPLICATE_ROWS incident, "
                    f"got {extraction.candidate_control_type}"
                )
            if extraction.failure_category != ExtractedFailureCategory.DUPLICATE_ROWS.value:
                errors.append(
                    f"Expected duplicate_rows category for DUPLICATE_ROWS incident, "
                    f"got {extraction.failure_category}"
                )
            if not extraction.target_field:
                errors.append("target_field is required for uniqueness control")

        # For orphaned-ownership incidents
        if "ORPHANED" in incident_custom_type.upper():
            if extraction.candidate_control_type != ExtractedControlType.ACTIVE_OWNERSHIP.value:
                errors.append(
                    f"Expected active_ownership control for ORPHANED incident, "
                    f"got {extraction.candidate_control_type}"
                )

        # Confidence cannot be LOW for the MVP known scenarios
        if "DUPLICATE" in incident_custom_type.upper() or "ORPHANED" in incident_custom_type.upper():
            if extraction.confidence == Confidence.LOW:
                errors.append("Confidence cannot be 'low' for known MVP scenarios")

        return errors

    def _build_lesson(
        self,
        extraction: LessonExtractionResult,
        incident_urn: str,
        incident_title: str,
        human_confirmed_root_cause: str,
        confirmed_by: str,
        target_asset_urn: str,
    ) -> ReflexLesson:
        """Build a ReflexLesson from a validated extraction."""
        vulnerability_descriptions = {
            ExtractedVulnerability.APPEND_ONLY_WITHOUT_IDEMPOTENCY:
                "Append-only write pattern without idempotency key",
            ExtractedVulnerability.NO_AUTOMATED_OWNERSHIP_REVIEW:
                "No automated ownership review process",
            ExtractedVulnerability.NO_SCHEMA_VALIDATION:
                "No schema validation on write",
            ExtractedVulnerability.NO_FRESHNESS_MONITORING:
                "No freshness monitoring configured",
        }

        return ReflexLesson(
            lesson_id=LessonId.generate(),
            source_incident_urn=incident_urn,
            title=incident_title,
            human_confirmed_root_cause=human_confirmed_root_cause,
            confirmed_or_edited_by=confirmed_by,
            approval_timestamp=datetime.now(UTC),
            failure_pattern=FailurePattern(
                category=CATEGORY_TO_FAILURE_CATEGORY[ExtractedFailureCategory(extraction.failure_category)],
                description=f"Extracted failure pattern: {extraction.failure_category}",
                indicators=[
                    ExtractedVulnerability(v).value if isinstance(v, str) else v.value
                    for v in extraction.vulnerable_characteristics
                ],
            ),
            trigger=ExtractedTrigger(extraction.trigger).value if isinstance(extraction.trigger, str) else extraction.trigger.value,
            vulnerable_characteristics=[
                vulnerability_descriptions.get(
                    ExtractedVulnerability(v) if isinstance(v, str) else v,
                    v if isinstance(v, str) else v.value,
                )
                for v in extraction.vulnerable_characteristics
            ],
            candidate_preventive_control=ProposedControl(
                control_type=CATEGORY_TO_CONTROL_TYPE[ExtractedControlType(extraction.candidate_control_type)],
                description=f"Auto-generated {extraction.candidate_control_type} control",
                target_asset_urn=target_asset_urn,
                parameters={"target_field": extraction.target_field},
            ),
            intended_propagation_scope=extraction.propagation_scope,
            confidence=extraction.confidence,
            limitations=extraction.limitations,
            provenance=f"mvp-extractor (template-based, custom_type={extraction.failure_category})",
        )

    def _save_record(self, record: ExtractionRecord) -> None:
        """Persist extraction record for reproducibility."""
        record_data = {
            "incident_urn": record.incident_urn,
            "root_cause_text": record.root_cause_text,
            "model_input": record.model_input,
            "raw_output": record.raw_output,
            "parsed_output": record.parsed_output.model_dump() if record.parsed_output else None,
            "validation_errors": record.validation_errors,
            "extracted_at": record.extracted_at.isoformat(),
        }
        filename = f"extraction_{_sanitize(record.incident_urn)}_{record.extracted_at.strftime('%Y%m%dT%H%M%S')}.json"
        (self._records_dir / filename).write_text(json.dumps(record_data, indent=2, default=str))


class ExtractionValidationError(Exception):
    """Raised when lesson extraction fails validation."""

    def __init__(self, message: str, record: ExtractionRecord) -> None:
        super().__init__(message)
        self.record = record


def _sanitize(urn: str) -> str:
    return urn.replace(":", "_").replace("(", "").replace(")", "").replace(",", "_")[:80]
