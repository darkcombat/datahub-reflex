"""Core domain models for DataHub Reflex.

All models use Pydantic v2 with strict validation.
No model references DataHub internals directly — the DataHub integration
layer maps between these domain models and DataHub entities.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from pydantic_core import core_schema

# -- Identifiers ----------------------------------------------------------------

UrnStr = Annotated[str, StringConstraints(pattern=r"^urn:li:[a-zA-Z_]+:.+")]
"""A DataHub URN string (e.g. urn:li:dataset:...)."""


class LessonId(str):
    """Strongly-typed lesson identifier."""

    @classmethod
    def generate(cls) -> LessonId:
        return cls(f"reflex-lesson-{uuid.uuid4().hex[:12]}")

    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: Any, _handler: Any
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(cls)


class ControlId(str):
    """Strongly-typed control identifier."""

    @classmethod
    def generate(cls) -> ControlId:
        return cls(f"reflex-control-{uuid.uuid4().hex[:12]}")

    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: Any, _handler: Any
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(cls)


# -- Enums ---------------------------------------------------------------------


class FailureCategory(str, Enum):
    DATA_QUALITY = "data_quality"
    OWNERSHIP = "ownership"
    SCHEMA = "schema"
    FRESHNESS = "freshness"
    LINEAGE = "lineage"
    OTHER = "other"


class ControlType(str, Enum):
    UNIQUENESS = "uniqueness"
    ACTIVE_OWNERSHIP = "active_ownership"


class ApprovalDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"


class PublicationStatus(str, Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    PUBLISHED = "published"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


# -- Core domain models --------------------------------------------------------


class FailurePattern(BaseModel):
    """A specific, named pattern of failure extracted from an incident."""

    model_config = ConfigDict(frozen=True)

    category: FailureCategory
    description: str = Field(..., min_length=1, max_length=2000)
    indicators: list[str] = Field(default_factory=list)


class ReflexLesson(BaseModel):
    """A structured lesson extracted from a resolved incident.

    The root cause is NOT authoritative until confirmed_or_edited_by is non-empty.
    """

    model_config = ConfigDict(frozen=True)

    lesson_id: LessonId
    source_incident_urn: UrnStr
    title: str = Field(..., min_length=1, max_length=200)
    human_confirmed_root_cause: str = Field(..., min_length=1, max_length=5000)
    confirmed_or_edited_by: str = Field(
        default="",
        description="Identity of the human who confirmed or edited the root cause. "
        "Empty string means unconfirmed.",
    )
    approval_timestamp: datetime | None = Field(
        default=None,
        description="Timestamp when the root cause was confirmed.",
    )
    failure_pattern: FailurePattern
    trigger: str = Field(..., description="What triggered this lesson to be created.")
    vulnerable_characteristics: list[str] = Field(
        default_factory=list,
        description="Characteristics that make an asset vulnerable to this failure pattern.",
    )
    candidate_preventive_control: ProposedControl
    intended_propagation_scope: list[str] = Field(
        default_factory=list,
        description="Domains, tags, or asset types this lesson should propagate to.",
    )
    confidence: Confidence = Confidence.UNKNOWN
    limitations: list[str] = Field(default_factory=list)
    provenance: str = Field(
        default="",
        description="How this lesson was produced (e.g. 'human-authored', 'llm-assisted').",
    )

    @property
    def is_confirmed(self) -> bool:
        return bool(self.confirmed_or_edited_by) and self.approval_timestamp is not None


class ProposedControl(BaseModel):
    """A candidate control before it is synthesized into a ReflexControl."""

    model_config = ConfigDict(frozen=True)

    control_type: ControlType
    description: str = Field(..., min_length=1, max_length=2000)
    target_asset_urn: UrnStr | None = None
    parameters: dict = Field(default_factory=dict)


class ReflexControl(BaseModel):
    """An executable, versioned preventive control.

    This is the core artifact that Reflex produces and publishes into DataHub.
    """

    model_config = ConfigDict(frozen=True)

    control_id: ControlId
    lesson_id: LessonId
    target_asset_urn: UrnStr
    control_type: ControlType
    control_definition: str = Field(
        ...,
        description="Deterministic, executable control definition (SQL, Python expression, etc.).",
    )
    backtest_results: list[BacktestResult] = Field(default_factory=list)
    approval_decision: ApprovalDecision | None = None
    approved_by: str = ""
    version: int = 1
    publication_status: PublicationStatus = PublicationStatus.DRAFT
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BacktestResult(BaseModel):
    """Result of running a ReflexControl against historical data."""

    model_config = ConfigDict(frozen=True)

    backtest_id: str = Field(default_factory=lambda: f"backtest-{uuid.uuid4().hex[:12]}")
    control_id: ControlId
    target_asset_urn: UrnStr
    executed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    historical_window_start: datetime
    historical_window_end: datetime
    would_have_detected: bool = Field(
        description="True if the control would have detected the incident.",
    )
    detection_timestamp: datetime | None = Field(
        default=None,
        description="The earliest timestamp in the historical window where the control would have fired.",
    )
    false_positives: int = Field(default=0, ge=0)
    true_positives: int = Field(default=0, ge=0)
    evidence: str = Field(default="", description="Supporting evidence for the backtest result.")
    limitations: list[str] = Field(default_factory=list)


class SimilarAssetCandidate(BaseModel):
    """An asset identified as similar to the source asset based on graph traversal."""

    model_config = ConfigDict(frozen=True)

    asset_urn: UrnStr
    asset_type: str
    similarity_rationale: str
    matched_characteristics: list[str] = Field(default_factory=list)
    domain: str = ""
    owners: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM


class ReflexCoverage(BaseModel):
    """Tracks which assets are covered by which controls."""

    model_config = ConfigDict(frozen=True)

    coverage_id: str = Field(default_factory=lambda: f"coverage-{uuid.uuid4().hex[:12]}")
    control_id: ControlId
    lesson_id: LessonId
    asset_urn: UrnStr
    covered_since: datetime = Field(default_factory=lambda: datetime.now(UTC))
    propagation_path: list[str] = Field(
        default_factory=list,
        description="Sequence of relationships that led to this coverage assignment.",
    )


class ControlExecutionResult(BaseModel):
    """Result of executing a ReflexControl against live (or latest) data."""

    model_config = ConfigDict(frozen=True)

    execution_id: str = Field(default_factory=lambda: f"exec-{uuid.uuid4().hex[:12]}")
    control_id: ControlId
    asset_urn: UrnStr
    executed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    passed: bool
    details: str = Field(default="")
    violation_count: int = Field(default=0, ge=0)
    sample_violations: list[str] = Field(default_factory=list)
