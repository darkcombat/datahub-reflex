"""Approval service — enforces mandatory human approval gates.

Two approval points exist in the Reflex loop:
1. Root-cause approval (before lesson extraction proceeds)
2. Control approval (before publication to DataHub)

No approval is automatic. The service persists all decisions with provenance.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class ApprovalState(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISED = "revised"


class RootCauseApproval:
    """Records a human decision on a proposed root cause."""

    def __init__(
        self,
        incident_urn: str,
        proposed_root_cause: str,
        final_root_cause: str,
        state: ApprovalState,
        approver: str,
        timestamp: datetime | None = None,
        provenance: str = "human-interface",
    ) -> None:
        self.incident_urn = incident_urn
        self.proposed_root_cause = proposed_root_cause
        self.final_root_cause = final_root_cause
        self.state = state
        self.approver = approver
        self.timestamp = timestamp or datetime.now(UTC)
        self.provenance = provenance

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_urn": self.incident_urn,
            "proposed_root_cause": self.proposed_root_cause,
            "final_root_cause": self.final_root_cause,
            "state": self.state.value,
            "approver": self.approver,
            "timestamp": self.timestamp.isoformat(),
            "provenance": self.provenance,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RootCauseApproval:
        return cls(
            incident_urn=data["incident_urn"],
            proposed_root_cause=data["proposed_root_cause"],
            final_root_cause=data["final_root_cause"],
            state=ApprovalState(data["state"]),
            approver=data["approver"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            provenance=data.get("provenance", "human-interface"),
        )


class ControlApproval:
    """Records a human decision on a ReflexControl before publication."""

    def __init__(
        self,
        control_id: str,
        lesson_id: str,
        state: ApprovalState,
        approver: str,
        backtest_metrics: dict[str, Any] | None = None,
        revision_notes: str = "",
        timestamp: datetime | None = None,
        provenance: str = "human-interface",
    ) -> None:
        self.control_id = control_id
        self.lesson_id = lesson_id
        self.state = state
        self.approver = approver
        self.backtest_metrics = backtest_metrics or {}
        self.revision_notes = revision_notes
        self.timestamp = timestamp or datetime.now(UTC)
        self.provenance = provenance

    def to_dict(self) -> dict[str, Any]:
        return {
            "control_id": self.control_id,
            "lesson_id": self.lesson_id,
            "state": self.state.value,
            "approver": self.approver,
            "backtest_metrics": self.backtest_metrics,
            "revision_notes": self.revision_notes,
            "timestamp": self.timestamp.isoformat(),
            "provenance": self.provenance,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ControlApproval:
        return cls(
            control_id=data["control_id"],
            lesson_id=data["lesson_id"],
            state=ApprovalState(data["state"]),
            approver=data["approver"],
            backtest_metrics=data.get("backtest_metrics", {}),
            revision_notes=data.get("revision_notes", ""),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            provenance=data.get("provenance", "human-interface"),
        )


class ApprovalService:
    """Manages the human-approval workflow with persistence.

    In the MVP, decisions are stored as JSON files in the approvals directory.
    In production, this would integrate with a ticketing system or UI.
    """

    def __init__(self, approvals_dir: Path | None = None) -> None:
        self._dir = approvals_dir or Path("./datasets/approvals")
        self._dir.mkdir(parents=True, exist_ok=True)

    # -- Root-cause approval ---------------------------------------------------

    async def submit_root_cause(
        self,
        incident_urn: str,
        proposed_root_cause: str,
    ) -> RootCauseApproval:
        """Submit a proposed root cause for human review (pending state)."""
        approval = RootCauseApproval(
            incident_urn=incident_urn,
            proposed_root_cause=proposed_root_cause,
            final_root_cause=proposed_root_cause,  # initially same
            state=ApprovalState.PENDING,
            approver="",
        )
        self._save(f"root_cause_{_sanitize(incident_urn)}.json", approval.to_dict())
        logger.info(
            "approval.root_cause_submitted",
            incident_urn=incident_urn,
            state="pending",
        )
        return approval

    async def approve_root_cause(
        self,
        incident_urn: str,
        approver: str,
        edited_cause: str | None = None,
    ) -> RootCauseApproval:
        """Approve a root cause, optionally with edits."""
        existing = self._load_root_cause(incident_urn)
        final_cause = edited_cause or existing.proposed_root_cause
        state = ApprovalState.REVISED if edited_cause else ApprovalState.APPROVED

        approval = RootCauseApproval(
            incident_urn=incident_urn,
            proposed_root_cause=existing.proposed_root_cause,
            final_root_cause=final_cause,
            state=state,
            approver=approver,
            provenance=f"human-interface (edited={edited_cause is not None})",
        )
        self._save(f"root_cause_{_sanitize(incident_urn)}.json", approval.to_dict())
        logger.info(
            "approval.root_cause_approved",
            incident_urn=incident_urn,
            approver=approver,
            state=state.value,
        )
        return approval

    async def reject_root_cause(
        self,
        incident_urn: str,
        approver: str,
    ) -> RootCauseApproval:
        """Reject a proposed root cause."""
        existing = self._load_root_cause(incident_urn)
        approval = RootCauseApproval(
            incident_urn=incident_urn,
            proposed_root_cause=existing.proposed_root_cause,
            final_root_cause=existing.proposed_root_cause,
            state=ApprovalState.REJECTED,
            approver=approver,
        )
        self._save(f"root_cause_{_sanitize(incident_urn)}.json", approval.to_dict())
        logger.info(
            "approval.root_cause_rejected",
            incident_urn=incident_urn,
            approver=approver,
        )
        return approval

    def get_root_cause(self, incident_urn: str) -> RootCauseApproval | None:
        """Get the current root-cause approval state."""
        return self._load_root_cause(incident_urn)

    # -- Control approval ------------------------------------------------------

    async def submit_control_for_approval(
        self,
        control_id: str,
        lesson_id: str,
        backtest_metrics: dict[str, Any],
    ) -> ControlApproval:
        """Submit a control for human approval."""
        approval = ControlApproval(
            control_id=control_id,
            lesson_id=lesson_id,
            state=ApprovalState.PENDING,
            approver="",
            backtest_metrics=backtest_metrics,
        )
        self._save(f"control_{_sanitize(control_id)}.json", approval.to_dict())
        logger.info(
            "approval.control_submitted",
            control_id=control_id,
            lesson_id=lesson_id,
        )
        return approval

    async def approve_control(
        self,
        control_id: str,
        approver: str,
        revision_notes: str = "",
    ) -> ControlApproval:
        """Approve a control for publication."""
        existing = self._load_control(control_id)
        if existing is None:
            raise ValueError(f"No pending approval for control {control_id}")

        approval = ControlApproval(
            control_id=control_id,
            lesson_id=existing.lesson_id,
            state=ApprovalState.APPROVED if not revision_notes else ApprovalState.REVISED,
            approver=approver,
            backtest_metrics=existing.backtest_metrics,
            revision_notes=revision_notes,
        )
        self._save(f"control_{_sanitize(control_id)}.json", approval.to_dict())
        logger.info(
            "approval.control_approved",
            control_id=control_id,
            approver=approver,
        )
        return approval

    async def reject_control(
        self,
        control_id: str,
        approver: str,
        reason: str = "",
    ) -> ControlApproval:
        """Reject a control."""
        existing = self._load_control(control_id)
        if existing is None:
            raise ValueError(f"No pending approval for control {control_id}")

        approval = ControlApproval(
            control_id=control_id,
            lesson_id=existing.lesson_id,
            state=ApprovalState.REJECTED,
            approver=approver,
            backtest_metrics=existing.backtest_metrics,
            revision_notes=reason,
        )
        self._save(f"control_{_sanitize(control_id)}.json", approval.to_dict())
        logger.info(
            "approval.control_rejected",
            control_id=control_id,
            approver=approver,
            reason=reason,
        )
        return approval

    def get_control_approval(self, control_id: str) -> ControlApproval | None:
        """Get the current control approval state."""
        return self._load_control(control_id)

    # -- Internal persistence --------------------------------------------------

    def _save(self, filename: str, data: dict[str, Any]) -> None:
        (self._dir / filename).write_text(json.dumps(data, indent=2, default=str))

    def _load_root_cause(self, incident_urn: str) -> RootCauseApproval | None:
        path = self._dir / f"root_cause_{_sanitize(incident_urn)}.json"
        if path.exists():
            return RootCauseApproval.from_dict(json.loads(path.read_text()))
        return None

    def _load_control(self, control_id: str) -> ControlApproval | None:
        path = self._dir / f"control_{_sanitize(control_id)}.json"
        if path.exists():
            return ControlApproval.from_dict(json.loads(path.read_text()))
        return None


def _sanitize(urn: str) -> str:
    """Sanitize a URN for use in a filename."""
    return urn.replace(":", "_").replace("(", "").replace(")", "").replace(",", "_")[:100]
