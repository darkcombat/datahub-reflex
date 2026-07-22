"""Product API — typed request/response models for the Reflex API surface.

These models define the stable contract for all API endpoints.
They are separate from internal domain models to allow independent evolution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# -- Request models -----------------------------------------------------------


@dataclass
class AnalyzeIncidentRequest:
    """Request to analyze an incident and extract a lesson."""

    incident_urn: str
    incident_title: str
    incident_description: str
    human_confirmed_root_cause: str
    confirmed_by: str
    target_asset_urn: str
    incident_custom_type: str = ""


@dataclass
class ApproveRootCauseRequest:
    """Request to approve or reject a root cause."""

    decision: str  # "approved" | "rejected"
    approver: str
    notes: str = ""


@dataclass
class BacktestLessonRequest:
    """Request to backtest a control from a lesson."""

    target_field: str = ""
    uniqueness_columns: list[str] = field(default_factory=list)
    known_incident_snapshots: int = 2


@dataclass
class ApproveControlRequest:
    """Request to approve or reject a control for publication."""

    decision: str  # "approved" | "rejected"
    approver: str
    notes: str = ""


@dataclass
class PublishControlRequest:
    """Request to publish a control to selected assets."""

    selected_asset_urns: list[str] = field(default_factory=list)


# -- Response models ----------------------------------------------------------


@dataclass
class ApiError:
    """Standardized API error response."""

    error: str
    detail: str = ""
    correlation_id: str = ""
    affected_step: int = 0
    retry_safe: bool = False
    next_action: str = ""


@dataclass
class IncidentResponse:
    """Incident details returned by the API."""

    incident_urn: str
    title: str
    description: str
    affected_asset_urn: str
    status: str
    root_cause: str = ""
    root_cause_approved: bool = False
    approved_by: str = ""
    approved_at: str = ""


@dataclass
class LessonResponse:
    """Structured lesson returned by the API."""

    lesson_id: str
    title: str
    failure_category: str
    failure_pattern: str
    trigger: str = ""
    vulnerable_characteristics: list[str] = field(default_factory=list)
    control_type: str = ""
    target_field: str = ""
    propagation_scope: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    confidence: str = ""
    extraction_mode: str = "deterministic"
    model_identifier: str = ""
    source_incident_urn: str = ""


@dataclass
class ControlResponse:
    """Control details returned by the API."""

    control_id: str
    control_type: str
    control_definition: str
    target_field: str = ""
    lesson_id: str = ""
    version: str = "1.0.0"


@dataclass
class BacktestResponse:
    """Backtest results returned by the API."""

    control_id: str
    total_snapshots: int
    detections: int
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    precision: float
    recall: float
    false_positive_rate: float
    f1_score: float
    execution_failures: int
    would_have_prevented: bool
    can_recommend: bool
    blockers: list[str] = field(default_factory=list)
    data_provenance: str = "SYNTHETIC (JSON snapshots)"


@dataclass
class SimilarAssetResponse:
    """Similar asset candidate returned by the API."""

    asset_urn: str
    asset_name: str
    selected: bool
    score: float
    matched_signals: list[str] = field(default_factory=list)
    missing_signals: list[str] = field(default_factory=list)
    explanation: str = ""
    domain: str = ""
    similarity_mode: str = "synthetic"


@dataclass
class ApprovalResponse:
    """Approval state returned by the API."""

    approval_type: str  # "root_cause" | "control"
    state: str  # "pending" | "approved" | "rejected"
    approver: str = ""
    notes: str = ""
    timestamp: str = ""
    test_mode: bool = False


@dataclass
class PublicationResponse:
    """Publication result returned by the API."""

    status: str  # "published" | "reflex-owned" | "pending"
    published_assets: list[str] = field(default_factory=list)
    count: int = 0
    reflex_owned: list[str] = field(default_factory=list)
    datahub_owned: list[str] = field(default_factory=list)
    cloud_skipped: list[str] = field(default_factory=list)


@dataclass
class DetectionResponse:
    """Future incident detection result."""

    detected: bool
    asset_urn: str = ""
    violation_count: int = 0
    control_id: str = ""
    evidence: str = ""
    new_incident_urn: str = ""


@dataclass
class RunResponse:
    """Complete run state returned by the API."""

    run_id: str
    started_at: str
    current_step: int
    is_complete: bool
    mode_label: str
    error: str = ""
    incident: IncidentResponse | None = None
    lesson: LessonResponse | None = None
    control: ControlResponse | None = None
    similar_assets: list[SimilarAssetResponse] = field(default_factory=list)
    backtest: BacktestResponse | None = None
    approval: ApprovalResponse | None = None
    publication: PublicationResponse | None = None
    detection: DetectionResponse | None = None


# -- Conversion helpers -------------------------------------------------------


def to_dict(obj: Any) -> dict[str, Any]:
    """Convert a dataclass to a dict, recursively handling nested types."""
    from dataclasses import fields, is_dataclass
    from enum import Enum

    if isinstance(obj, Enum):
        return obj.value
    if is_dataclass(obj):
        result: dict[str, Any] = {}
        for f in fields(obj):
            value = getattr(obj, f.name)
            if isinstance(value, list):
                result[f.name] = [to_dict(v) for v in value]
            elif isinstance(value, dict):
                result[f.name] = {k: to_dict(v) for k, v in value.items()}
            elif isinstance(value, Enum):
                result[f.name] = value.value
            elif is_dataclass(value):
                result[f.name] = to_dict(value)
            elif value is not None:
                result[f.name] = value
            else:
                result[f.name] = None
        return result
    return obj
