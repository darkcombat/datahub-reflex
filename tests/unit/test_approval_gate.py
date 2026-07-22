"""Tests for the explicit human approval gate (Step 2)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from reflex.core.approval import (
    ApprovalService,
    ApprovalState,
)
from reflex.core.pipeline import (
    ApprovalDecision,
    PipelineApprovalRequired,
    PipelineError,
    ReflexPipeline,
    _sanitize_urn,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_historical_data(days: int = 8) -> list[tuple[datetime, list[dict]]]:
    """Build synthetic historical snapshots with a duplicate on the last two days."""
    now = datetime.now(UTC)
    base_rows = [
        {"transaction_id": f"TXN-{i:03d}", "amount": 100.0 * i}
        for i in range(1, 11)
    ]
    data = []
    for d in range(days, 0, -1):
        snapshot = list(base_rows)
        if d <= 2:
            snapshot.append({"transaction_id": "TXN-003", "amount": 300.0})
        data.append((now - timedelta(days=d), snapshot))
    return data


# ---------------------------------------------------------------------------
# PipelineApprovalRequired – blocking without test mode
# ---------------------------------------------------------------------------

class TestApprovalGateBlocksWithoutTestMode:
    """Pipeline MUST raise PipelineApprovalRequired when no approval exists."""

    def test_raises_when_no_approval_file_and_not_test_mode(self, tmp_path: Path) -> None:
        """Without test mode and without approval file, the pipeline blocks."""
        import asyncio

        async def _run():
            pipeline = ReflexPipeline(
                lessons_dir=tmp_path,
                non_interactive_test_mode=False,
            )
            historical = _make_historical_data()
            with pytest.raises(PipelineApprovalRequired) as exc_info:
                await pipeline.run(
                    incident_urn="urn:li:incident:approval-test-001",
                    scenario="duplicate_rows",
                    human_confirmed_root_cause="Non-idempotent retries caused dupes",
                    confirmed_by="tester@example.com",
                    target_asset_urn="urn:li:dataset:(urn:li:dataPlatform:bigquery,test_table,PROD)",
                    historical_data=historical,
                    uniqueness_columns=["transaction_id"],
                )
            assert "Root cause" in str(exc_info.value)
            assert "requires explicit human approval" in str(exc_info.value)

        asyncio.run(_run())

    def test_passes_when_test_mode_enabled(self) -> None:
        """With non_interactive_test_mode=True, the pipeline auto-approves."""
        import asyncio

        async def _run():
            pipeline = ReflexPipeline(
                lessons_dir=Path("./datasets"),
                non_interactive_test_mode=True,
            )
            historical = _make_historical_data()
            result = await pipeline.run(
                incident_urn="urn:li:incident:approval-test-002",
                scenario="duplicate_rows",
                human_confirmed_root_cause="Non-idempotent retries caused dupes",
                confirmed_by="tester@example.com",
                target_asset_urn="urn:li:dataset:(urn:li:dataPlatform:bigquery,test_table,PROD)",
                historical_data=historical,
                uniqueness_columns=["transaction_id"],
            )
            assert result["lesson"].is_confirmed
            assert result["control"].control_type.value == "uniqueness"

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Approval file-based explicit decisions
# ---------------------------------------------------------------------------

class TestApprovalFileExplicitDecision:
    """When approval_required=True and non_interactive_test_mode=False,
    an explicit JSON approval file must exist."""

    def test_full_pipeline_with_all_approvals(self, tmp_path: Path) -> None:
        """Pipeline completes when root cause is approved. Control still needs
        explicit approval to proceed past backtesting (tested separately)."""
        import asyncio

        approvals_dir = tmp_path / "approvals"
        approvals_dir.mkdir(parents=True)

        async def _run():
            pipeline = ReflexPipeline(
                lessons_dir=tmp_path,
                non_interactive_test_mode=False,
            )
            historical = _make_historical_data()

            # Pre-create the root cause approval file
            rc_file = approvals_dir / "root_cause_urn_li_incident_full-approval-test.json"
            rc_file.write_text(json.dumps({
                "incident_urn": "urn:li:incident:full-approval-test",
                "proposed_root_cause": "Non-idempotent retries caused dupes",
                "final_root_cause": "Non-idempotent retries caused dupes",
                "state": "approved",
                "approver": "human-reviewer",
                "timestamp": datetime.now(UTC).isoformat(),
                "provenance": "human-interface",
            }))

            # Control still needs approval — expect block at control stage
            with pytest.raises(PipelineApprovalRequired) as exc_info:
                await pipeline.run(
                    incident_urn="urn:li:incident:full-approval-test",
                    scenario="duplicate_rows",
                    human_confirmed_root_cause="Non-idempotent retries caused dupes",
                    confirmed_by="tester@example.com",
                    target_asset_urn="urn:li:dataset:(urn:li:dataPlatform:bigquery,test_table,PROD)",
                    historical_data=historical,
                    uniqueness_columns=["transaction_id"],
                )
            assert "Control" in str(exc_info.value)

        asyncio.run(_run())

    def test_control_stage_blocks_without_decision(self, tmp_path: Path) -> None:
        """After root cause is approved, pipeline blocks at control stage if no
        control decision file exists."""
        import asyncio

        approvals_dir = tmp_path / "approvals"
        approvals_dir.mkdir(parents=True)

        async def _run():
            pipeline = ReflexPipeline(
                lessons_dir=tmp_path,
                non_interactive_test_mode=False,
            )
            historical = _make_historical_data()

            # Root cause approved...
            rc_file = approvals_dir / "root_cause_urn_li_incident_control-block-test.json"
            rc_file.write_text(json.dumps({
                "incident_urn": "urn:li:incident:control-block-test",
                "proposed_root_cause": "Non-idempotent retries caused dupes",
                "final_root_cause": "Non-idempotent retries caused dupes",
                "state": "approved",
                "approver": "human-reviewer",
                "timestamp": datetime.now(UTC).isoformat(),
                "provenance": "human-interface",
            }))

            with pytest.raises(PipelineApprovalRequired) as exc_info:
                await pipeline.run(
                    incident_urn="urn:li:incident:control-block-test",
                    scenario="duplicate_rows",
                    human_confirmed_root_cause="Non-idempotent retries caused dupes",
                    confirmed_by="tester@example.com",
                    target_asset_urn="urn:li:dataset:(urn:li:dataPlatform:bigquery,test_table,PROD)",
                    historical_data=historical,
                    uniqueness_columns=["transaction_id"],
                )
            assert "Control" in str(exc_info.value)
            assert "requires explicit human approval" in str(exc_info.value)

        asyncio.run(_run())

    def test_root_cause_rejected_blocks_pipeline(self, tmp_path: Path) -> None:
        """Pipeline raises PipelineError when root cause was rejected."""
        import asyncio

        approvals_dir = tmp_path / "approvals"
        approvals_dir.mkdir(parents=True)

        # Pre-create a REJECTED root cause approval
        rc_file = approvals_dir / "root_cause_urn_li_incident_reject-test.json"
        rc_file.write_text(json.dumps({
            "incident_urn": "urn:li:incident:reject-test",
            "proposed_root_cause": "Bad root cause",
            "final_root_cause": "Bad root cause",
            "state": "rejected",
            "approver": "human-reviewer",
            "timestamp": datetime.now(UTC).isoformat(),
            "provenance": "human-interface",
        }))

        async def _run():
            pipeline = ReflexPipeline(
                lessons_dir=tmp_path,
                non_interactive_test_mode=False,
            )
            historical = _make_historical_data()
            with pytest.raises(PipelineError) as exc_info:
                await pipeline.run(
                    incident_urn="urn:li:incident:reject-test",
                    scenario="duplicate_rows",
                    human_confirmed_root_cause="Bad root cause",
                    confirmed_by="tester@example.com",
                    target_asset_urn="urn:li:dataset:(urn:li:dataPlatform:bigquery,test_table,PROD)",
                    historical_data=historical,
                    uniqueness_columns=["transaction_id"],
                )
            assert "in state 'rejected'" in str(exc_info.value)

        asyncio.run(_run())

    def test_pending_root_cause_still_blocks(self, tmp_path: Path) -> None:
        """A root cause in 'pending' state still blocks the pipeline."""
        import asyncio

        approvals_dir = tmp_path / "approvals"
        approvals_dir.mkdir(parents=True)

        # Pre-create a PENDING root cause approval
        rc_file = approvals_dir / "root_cause_urn_li_incident_pending-test.json"
        rc_file.write_text(json.dumps({
            "incident_urn": "urn:li:incident:pending-test",
            "proposed_root_cause": "Non-idempotent retries",
            "final_root_cause": "Non-idempotent retries",
            "state": "pending",
            "approver": "",
            "timestamp": datetime.now(UTC).isoformat(),
            "provenance": "human-interface",
        }))

        async def _run():
            pipeline = ReflexPipeline(
                lessons_dir=tmp_path,
                non_interactive_test_mode=False,
            )
            historical = _make_historical_data()
            with pytest.raises(PipelineError) as exc_info:
                await pipeline.run(
                    incident_urn="urn:li:incident:pending-test",
                    scenario="duplicate_rows",
                    human_confirmed_root_cause="Non-idempotent retries",
                    confirmed_by="tester@example.com",
                    target_asset_urn="urn:li:dataset:(urn:li:dataPlatform:bigquery,test_table,PROD)",
                    historical_data=historical,
                    uniqueness_columns=["transaction_id"],
                )
            assert "in state 'pending'" in str(exc_info.value)

        asyncio.run(_run())

    def test_revised_root_cause_counts_as_approved(self, tmp_path: Path) -> None:
        """A revised root cause (state=revised) should be treated as approved."""
        import asyncio

        approvals_dir = tmp_path / "approvals"
        approvals_dir.mkdir(parents=True)

        rc_file = approvals_dir / "root_cause_urn_li_incident_revised-test.json"
        rc_file.write_text(json.dumps({
            "incident_urn": "urn:li:incident:revised-test",
            "proposed_root_cause": "Non-idempotent retries",
            "final_root_cause": "Edited: race condition in retry logic",
            "state": "revised",
            "approver": "human-reviewer",
            "timestamp": datetime.now(UTC).isoformat(),
            "provenance": "human-interface (edited=True)",
        }))

        async def _run():
            pipeline = ReflexPipeline(
                lessons_dir=tmp_path,
                non_interactive_test_mode=False,
            )
            historical = _make_historical_data()
            # This will pass root cause (revised=approved), then block at
            # control approval stage (no control decision file).
            with pytest.raises(PipelineApprovalRequired) as exc_info:
                await pipeline.run(
                    incident_urn="urn:li:incident:revised-test",
                    scenario="duplicate_rows",
                    human_confirmed_root_cause="Edited: race condition in retry logic",
                    confirmed_by="tester@example.com",
                    target_asset_urn="urn:li:dataset:(urn:li:dataPlatform:bigquery,test_table,PROD)",
                    historical_data=historical,
                    uniqueness_columns=["transaction_id"],
                )
            # Should fail at CONTROL approval, not root cause
            assert "Control" in str(exc_info.value)

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# ApprovalService persistence
# ---------------------------------------------------------------------------

class TestApprovalServicePersistence:
    """ApprovalService must persist decisions and allow retrieval."""

    def test_submit_and_approve_root_cause(self, tmp_path: Path) -> None:
        import asyncio

        async def _run():
            service = ApprovalService(tmp_path)

            # Submit
            rc = await service.submit_root_cause(
                incident_urn="urn:li:incident:persist-001",
                proposed_root_cause="Test root cause",
            )
            assert rc.state == ApprovalState.PENDING

            # Approve
            approved = await service.approve_root_cause(
                incident_urn="urn:li:incident:persist-001",
                approver="tester",
            )
            assert approved.state == ApprovalState.APPROVED
            assert approved.approver == "tester"

            # Retrieve
            retrieved = service.get_root_cause("urn:li:incident:persist-001")
            assert retrieved is not None
            assert retrieved.state == ApprovalState.APPROVED

        asyncio.run(_run())

    def test_reject_root_cause(self, tmp_path: Path) -> None:
        import asyncio

        async def _run():
            service = ApprovalService(tmp_path)
            await service.submit_root_cause(
                incident_urn="urn:li:incident:persist-002",
                proposed_root_cause="Bad cause",
            )
            rejected = await service.reject_root_cause(
                incident_urn="urn:li:incident:persist-002",
                approver="tester",
            )
            assert rejected.state == ApprovalState.REJECTED

            retrieved = service.get_root_cause("urn:li:incident:persist-002")
            assert retrieved is not None
            assert retrieved.state == ApprovalState.REJECTED

        asyncio.run(_run())

    def test_submit_approve_reject_control(self, tmp_path: Path) -> None:
        import asyncio

        async def _run():
            service = ApprovalService(tmp_path)

            # Submit
            await service.submit_control_for_approval(
                control_id="reflex-control-test-001",
                lesson_id="reflex-lesson-test-001",
                backtest_metrics={"precision": 1.0, "recall": 0.8},
            )

            # Approve
            approved = await service.approve_control(
                control_id="reflex-control-test-001",
                approver="tester",
                revision_notes="Looks good",
            )
            assert approved.state == ApprovalState.REVISED  # has revision notes
            assert approved.revision_notes == "Looks good"

            retrieved = service.get_control_approval("reflex-control-test-001")
            assert retrieved is not None
            assert retrieved.state == ApprovalState.REVISED

        asyncio.run(_run())

    def test_reject_control(self, tmp_path: Path) -> None:
        import asyncio

        async def _run():
            service = ApprovalService(tmp_path)
            await service.submit_control_for_approval(
                control_id="reflex-control-test-002",
                lesson_id="reflex-lesson-test-002",
                backtest_metrics={"precision": 0.5, "recall": 0.3},
            )
            rejected = await service.reject_control(
                control_id="reflex-control-test-002",
                approver="tester",
                reason="Precision too low",
            )
            assert rejected.state == ApprovalState.REJECTED
            assert rejected.revision_notes == "Precision too low"

        asyncio.run(_run())

    def test_get_nonexistent_returns_none(self, tmp_path: Path) -> None:
        service = ApprovalService(tmp_path)
        assert service.get_root_cause("urn:li:incident:nonexistent") is None
        assert service.get_control_approval("control-nonexistent") is None


# ---------------------------------------------------------------------------
# _sanitize_urn helper
# ---------------------------------------------------------------------------

class TestSanitizeUrn:
    def test_sanitize_standard_urn(self) -> None:
        result = _sanitize_urn("urn:li:incident:test-001")
        assert result == "urn_li_incident_test-001"

    def test_sanitize_dataset_urn(self) -> None:
        result = _sanitize_urn(
            "urn:li:dataset:(urn:li:dataPlatform:bigquery,test.table,PROD)"
        )
        assert "(" not in result
        assert ")" not in result
        assert result.startswith("urn_li_dataset_")

    def test_sanitize_truncates_long_urns(self) -> None:
        long_urn = "urn:li:dataset:" + "x" * 200
        result = _sanitize_urn(long_urn)
        assert len(result) <= 100


# ---------------------------------------------------------------------------
# ApprovalDecision enum
# ---------------------------------------------------------------------------

class TestApprovalDecision:
    def test_approved_value(self) -> None:
        assert ApprovalDecision.APPROVED == "approved"

    def test_rejected_value(self) -> None:
        assert ApprovalDecision.REJECTED == "rejected"

    def test_modified_value(self) -> None:
        assert ApprovalDecision.MODIFIED == "modified"
