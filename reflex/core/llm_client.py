"""LLM client abstraction for lesson extraction.

Provides a provider-neutral interface for extracting structured lessons
from incidents. Two implementations:

- DeterministicLLMClient: Template-based, no network, always available.
- APIBasedLLMClient: Calls an external LLM API (OpenAI-compatible).

Mode selection via REFLEX_LLM_MODE env var:
    - "deterministic" (default): Uses template-based extraction.
    - "api": Uses the configured LLM API.

The pipeline never silently falls back from API mode to deterministic mode.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

import httpx
import structlog

from reflex.core.lesson_extractor import (
    ALLOWED_CONTROL_TYPES,
    ALLOWED_FAILURE_CATEGORIES,
    ALLOWED_TRIGGERS,
    ALLOWED_VULNERABILITIES,
    ExtractedControlType,
    ExtractedFailureCategory,
    ExtractedTrigger,
    ExtractedVulnerability,
    LessonExtractionResult,
)
from reflex.models import Confidence

logger = structlog.get_logger(__name__)


# -- Domain models ------------------------------------------------------------


@dataclass
class ExtractionInput:
    """Input for lesson extraction — incident context only."""

    incident_urn: str
    incident_title: str
    incident_description: str
    human_confirmed_root_cause: str
    incident_custom_type: str = ""


@dataclass
class ExtractionOutput:
    """Output from lesson extraction with full provenance."""

    result: LessonExtractionResult
    model_identifier: str
    prompt_version: str
    extraction_mode: str  # "deterministic" | "api"
    elapsed_ms: int
    token_count: int | None = None
    cost_estimate: float | None = None
    request_id: str | None = None
    extracted_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class LLMError(Exception):
    """Base error for LLM client failures."""


class LLMAuthenticationError(LLMError):
    """API key missing or invalid."""


class LLMTimeoutError(LLMError):
    """LLM API request timed out."""


class LLMValidationError(LLMError):
    """LLM returned output that failed schema validation."""


class LLMFallbackProhibitedError(LLMError):
    """API mode was requested but the API is unavailable.

    Reflex never silently falls back to deterministic mode.
    This error must be surfaced to the user.
    """


# -- Protocol -----------------------------------------------------------------


@runtime_checkable
class LLMClient(Protocol):
    """Provider-neutral interface for LLM-based lesson extraction.

    Implementations must handle their own authentication, retry, and
    error handling. The pipeline only calls extract_lesson().
    """

    @property
    def mode(self) -> str:
        """Return the extraction mode: 'deterministic' or 'api'."""
        ...

    async def extract_lesson(self, input: ExtractionInput) -> ExtractionOutput:
        """Extract a structured lesson from an incident.

        Args:
            input: Incident context with human-confirmed root cause.

        Returns:
            ExtractionOutput with validated result and provenance.

        Raises:
            LLMAuthenticationError: API key missing/invalid.
            LLMTimeoutError: Request timed out after retries.
            LLMValidationError: Output failed schema validation.
        """
        ...


# -- Deterministic implementation ---------------------------------------------


class DeterministicLLMClient:
    """Template-based extraction. No network, no API key, always available.

    This is the default mode. It uses the same deterministic rules as the
    current LessonExtractor._run_extraction() method.
    """

    mode = "deterministic"

    async def extract_lesson(self, input: ExtractionInput) -> ExtractionOutput:
        """Extract using deterministic template rules."""
        started = time.monotonic()

        result = _build_deterministic_extraction(
            incident_custom_type=input.incident_custom_type,
            root_cause=input.human_confirmed_root_cause,
            incident_description=input.incident_description,
        )

        elapsed_ms = int((time.monotonic() - started) * 1000)

        return ExtractionOutput(
            result=result,
            model_identifier="deterministic-template",
            prompt_version="mvp-template-v1",
            extraction_mode="deterministic",
            elapsed_ms=elapsed_ms,
            token_count=None,
            cost_estimate=None,
            request_id=None,
        )


# -- API-based implementation -------------------------------------------------


class APIBasedLLMClient:
    """Calls an OpenAI-compatible LLM API for lesson extraction.

    Configured via environment variables:
        REFLEX_LLM_API_KEY: API key (required).
        REFLEX_LLM_API_BASE: Base URL (default: https://api.openai.com/v1).
        REFLEX_LLM_MODEL: Model name (default: gpt-4o).
        REFLEX_LLM_TIMEOUT_SECONDS: Request timeout (default: 60).
        REFLEX_LLM_MAX_RETRIES: Max retries for transient failures (default: 2).

    Never logs API keys or raw incident content.
    """

    mode = "api"

    def __init__(self) -> None:
        self._api_key = os.environ.get("REFLEX_LLM_API_KEY", "").strip()
        self._api_base = os.environ.get(
            "REFLEX_LLM_API_BASE", "https://api.openai.com/v1"
        ).rstrip("/")
        self._model = os.environ.get("REFLEX_LLM_MODEL", "gpt-4o")
        self._timeout = float(os.environ.get("REFLEX_LLM_TIMEOUT_SECONDS", "60"))
        self._max_retries = int(os.environ.get("REFLEX_LLM_MAX_RETRIES", "2"))

        if not self._api_key:
            raise LLMAuthenticationError(
                "REFLEX_LLM_API_KEY is required for API mode. "
                "Set it in the environment or switch to REFLEX_LLM_MODE=deterministic."
            )

        self._headers: dict[str, str] = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def extract_lesson(self, input: ExtractionInput) -> ExtractionOutput:
        """Extract using the configured LLM API with retry and timeout."""
        started = time.monotonic()
        prompt = _build_llm_prompt(input)

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._call_api(prompt)
                result = LessonExtractionResult.model_validate_json(response["content"])
                elapsed_ms = int((time.monotonic() - started) * 1000)
                return ExtractionOutput(
                    result=result,
                    model_identifier=response.get("model", self._model),
                    prompt_version="mvp-template-v1",
                    extraction_mode="api",
                    elapsed_ms=elapsed_ms,
                    token_count=response.get("usage", {}).get("total_tokens"),
                    request_id=response.get("id"),
                )
            except (ValidationError, ValueError) as e:
                raise LLMValidationError(
                    f"LLM output failed schema validation: {e}"
                ) from e
            except httpx.TimeoutException as e:
                last_error = e
                if attempt == self._max_retries:
                    raise LLMTimeoutError(
                        f"LLM request timed out after {self._max_retries + 1} attempts"
                    ) from e
                await asyncio.sleep(0.5 * (attempt + 1))
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (401, 403):
                    raise LLMAuthenticationError(
                        f"LLM API authentication failed: {e.response.status_code}"
                    ) from e
                last_error = e
                if attempt == self._max_retries:
                    raise LLMError(f"LLM API error: {e.response.status_code}") from e
                await asyncio.sleep(1.0 * (attempt + 1))

        raise LLMError(f"LLM extraction failed: {last_error}")

    async def _call_api(self, prompt: str) -> dict[str, Any]:
        """Make a single API call to the LLM."""
        async with httpx.AsyncClient(timeout=self._timeout, trust_env=False) as client:
            response = await client.post(
                f"{self._api_base}/chat/completions",
                json={
                    "model": self._model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a data-quality incident analyzer. "
                                "Extract structured lessons from resolved incidents. "
                                "Return ONLY valid JSON matching the schema. "
                                "Do not include markdown, explanations, or code blocks."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.0,
                    "response_format": {"type": "json_object"},
                },
                headers=self._headers,
            )
            response.raise_for_status()
            data = response.json()
            choice = data["choices"][0]
            content = choice["message"]["content"]
            return {
                "content": content,
                "model": data.get("model", self._model),
                "id": data.get("id"),
                "usage": data.get("usage"),
            }


# -- Factory ------------------------------------------------------------------


def create_llm_client(mode: str | None = None) -> LLMClient:
    """Create an LLM client based on configuration.

    Args:
        mode: "deterministic" or "api". If None, reads REFLEX_LLM_MODE env var.

    Returns:
        An LLMClient implementation.

    Raises:
        ValueError: Unknown mode.
        LLMAuthenticationError: API mode requested but no key configured.
    """
    if mode is None:
        mode = os.environ.get("REFLEX_LLM_MODE", "deterministic").strip().lower()

    if mode == "deterministic":
        logger.info("llm_client.mode", mode="deterministic")
        return DeterministicLLMClient()

    if mode == "api":
        logger.info("llm_client.mode", mode="api")
        return APIBasedLLMClient()

    raise ValueError(
        f"Unknown REFLEX_LLM_MODE: {mode!r}. "
        f"Valid values: 'deterministic', 'api'."
    )


# -- Prompt builder -----------------------------------------------------------


def _build_llm_prompt(input: ExtractionInput) -> str:
    """Build the LLM extraction prompt."""
    return f"""Extract a structured data-quality lesson from this resolved incident.

INCIDENT:
  URN: {input.incident_urn}
  Title: {input.incident_title}
  Type: {input.incident_custom_type}
  Description: {input.incident_description}

HUMAN-CONFIRMED ROOT CAUSE:
{input.human_confirmed_root_cause}

Return a JSON object with these fields:
- failure_category: one of {sorted(ALLOWED_FAILURE_CATEGORIES)}
- trigger: one of {sorted(ALLOWED_TRIGGERS)}
- vulnerable_characteristics: list of {sorted(ALLOWED_VULNERABILITIES)}
- candidate_control_type: one of {sorted(ALLOWED_CONTROL_TYPES)}
- target_field: primary field for the control (e.g., transaction_id)
- propagation_scope: domains or tags for propagation (list of strings)
- assumptions: list of assumptions about the extraction (list of strings)
- limitations: list of known limitations (list of strings)
- confidence: one of [high, medium, low, unknown]

Return ONLY the JSON object. No markdown, no explanation."""


def _build_deterministic_extraction(
    incident_custom_type: str,
    root_cause: str,
    incident_description: str,
) -> LessonExtractionResult:
    """Build extraction using deterministic template rules.

    Mirrors the existing LessonExtractor._run_extraction() logic.
    """
    root_lower = root_cause.lower()
    desc_lower = incident_description.lower()
    combined = f"{root_lower} {desc_lower}"

    # Duplicate rows detection
    if (
        incident_custom_type.upper() in ("DUPLICATE_ROWS", "DATA_QUALITY")
        or "duplicate" in combined
        or "retry" in root_lower
    ):
        return LessonExtractionResult(
            failure_category=ExtractedFailureCategory.DUPLICATE_ROWS,
            trigger=ExtractedTrigger.RETRY_AFTER_PARTIAL_FAILURE,
            vulnerable_characteristics=[
                ExtractedVulnerability.APPEND_ONLY_WITHOUT_IDEMPOTENCY,
            ],
            candidate_control_type=ExtractedControlType.UNIQUENESS,
            target_field="transaction_id",
            propagation_scope=["finance"],
            assumptions=[
                "Ingestion pipeline uses append-only writes",
                "Retry logic does not check for existing rows",
            ],
            limitations=[
                "Template-based extraction — not LLM-driven",
                "Target field assumed from incident type",
            ],
            confidence=Confidence.HIGH,
        )

    # Orphaned ownership detection
    if (
        incident_custom_type.upper() in ("ORPHANED_OWNERSHIP", "OWNERSHIP")
        or "owner" in combined
        or "offboarding" in root_lower
        or "deactivated" in desc_lower
    ):
        return LessonExtractionResult(
            failure_category=ExtractedFailureCategory.ORPHANED_OWNERSHIP,
            trigger=ExtractedTrigger.EMPLOYEE_OFFBOARDING,
            vulnerable_characteristics=[
                ExtractedVulnerability.NO_AUTOMATED_OWNERSHIP_REVIEW,
            ],
            candidate_control_type=ExtractedControlType.ACTIVE_OWNERSHIP,
            target_field="",
            propagation_scope=["finance", "operations"],
            assumptions=[
                "Employee offboarding does not update DataHub ownership",
                "No automated ownership review exists",
            ],
            limitations=[
                "Template-based extraction — not LLM-driven",
                "Ownership review scope limited to known domains",
            ],
            confidence=Confidence.HIGH,
        )

    # Fallback
    return LessonExtractionResult(
        failure_category=ExtractedFailureCategory.OTHER,
        trigger=ExtractedTrigger.UNKNOWN,
        vulnerable_characteristics=[],
        candidate_control_type=ExtractedControlType.UNIQUENESS,
        target_field="",
        propagation_scope=[],
        assumptions=[],
        limitations=["Unable to classify incident with deterministic rules"],
        confidence=Confidence.LOW,
    )


# Import needed at bottom to avoid circular dependency
from pydantic import ValidationError  # noqa: E402
