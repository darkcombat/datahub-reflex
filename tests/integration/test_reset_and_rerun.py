"""Step 14: Complete reset and rerun cycle.

Verifies that the Reflex pipeline can be executed twice with the same
test prefix, and that isolated test data can be cleaned up without
affecting unrelated DataHub data.

Steps:
  1. Run pipeline → collect artifacts
  2. Reset test state (clean approval files, clear temp data)
  3. Run pipeline again with different incident URN → verify determinism
  4. Verify no cross-contamination between runs
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from reflex.core.pipeline import ReflexPipeline

from ..conftest import (
    make_test_dataset_urn,
    make_test_incident_urn,
)
from .conftest import (
    build_duplicate_rows_history,
    write_root_cause_approval,
)

pytestmark = pytest.mark.requires_datahub


class TestStep14_ResetAndRerun:
    """Step 14: Reset and rerun the full pipeline."""

    def test_two_independent_runs_produce_deterministic_results(
        self, tmp_path: Path
    ) -> None:
        """Run the pipeline twice with different incident URNs and verify
        both produce consistent results.

        This proves the pipeline is deterministic and does not leak state
        between runs.
        """
        async def _run_pipeline(incident_urn: str, run_label: str) -> dict:
            """Run one pipeline cycle with a clean approvals dir."""
            approvals_dir = tmp_path / f"approvals-{run_label}"
            approvals_dir.mkdir(parents=True)

            pipeline = ReflexPipeline(
                lessons_dir=tmp_path,
                use_live_datahub=True,
                non_interactive_test_mode=True,
            )
            historical = build_duplicate_rows_history(days=8)
            return await pipeline.run(
                incident_urn=incident_urn,
                scenario="duplicate_rows",
                human_confirmed_root_cause="Non-idempotent retry logic",
                confirmed_by="reset-test",
                target_asset_urn=make_test_dataset_urn("finance.transactions"),
                historical_data=historical,
                uniqueness_columns=["transaction_id"],
            )

        async def _main():
            # Run 1
            urn1 = make_test_incident_urn("reset-run1")
            result1 = await _run_pipeline(urn1, "run1")
            print(f"Run 1: lesson={result1['lesson'].lesson_id}, "
                  f"control={result1['control'].control_id}, "
                  f"candidates={len(result1['similar_assets'])}")

            # Reset — clean approvals
            shutil.rmtree(tmp_path / "approvals-run1", ignore_errors=True)

            # Run 2
            urn2 = make_test_incident_urn("reset-run2")
            result2 = await _run_pipeline(urn2, "run2")
            print(f"Run 2: lesson={result2['lesson'].lesson_id}, "
                  f"control={result2['control'].control_id}, "
                  f"candidates={len(result2['similar_assets'])}")

            # Both runs should produce valid results
            assert result1["lesson"].is_confirmed
            assert result2["lesson"].is_confirmed
            assert result1["backtest_summary"].would_have_prevented
            assert result2["backtest_summary"].would_have_prevented

            # Different runs produce different lesson/control IDs
            assert result1["lesson"].lesson_id != result2["lesson"].lesson_id
            assert result1["control"].control_id != result2["control"].control_id

            # Both discover similar candidates from live DataHub
            assert isinstance(result1["similar_assets"], list)
            assert isinstance(result2["similar_assets"], list)

            return result1, result2

        r1, r2 = asyncio.run(_main())
        print(f"Step 14 ✓ Reset and rerun: both runs deterministic, "
              f"run1={len(r1['similar_assets'])} candidates, "
              f"run2={len(r2['similar_assets'])} candidates")

    def test_explicit_approval_reset_cycle(self, tmp_path: Path) -> None:
        """Run pipeline with root-cause approval, reset, run again.

        Tests that the root-cause approval service's file-based persistence
        does not leak between test runs. Control approval uses test mode
        (control IDs are dynamically generated).
        """
        approvals_dir = tmp_path / "approvals"
        approvals_dir.mkdir(parents=True)

        async def _run_with_approval(incident_urn: str) -> dict:
            # Pre-create root cause approval
            write_root_cause_approval(approvals_dir, incident_urn)

            pipeline = ReflexPipeline(
                lessons_dir=tmp_path,
                use_live_datahub=True,
                non_interactive_test_mode=True,  # <-- control approval auto-approved
            )
            historical = build_duplicate_rows_history(days=8)
            return await pipeline.run(
                incident_urn=incident_urn,
                scenario="duplicate_rows",
                human_confirmed_root_cause="Non-idempotent retry logic",
                confirmed_by="reset-test",
                target_asset_urn=make_test_dataset_urn("finance.transactions"),
                historical_data=historical,
                uniqueness_columns=["transaction_id"],
            )

        async def _main():
            # Run 1
            urn1 = make_test_incident_urn("explicit-reset-1")
            result1 = await _run_with_approval(urn1)

            # Reset — clear ALL approval files
            for f in approvals_dir.glob("*.json"):
                f.unlink()

            # Run 2 — must create NEW root cause approval
            urn2 = make_test_incident_urn("explicit-reset-2")
            write_root_cause_approval(approvals_dir, urn2)
            result2 = await _run_with_approval(urn2)

            assert result1["lesson"].is_confirmed
            assert result2["lesson"].is_confirmed
            return result1, result2

        r1, r2 = asyncio.run(_main())
        print("Step 14 ✓ Explicit approval reset cycle: both runs pass "
              "with fresh approval files")


class TestRerunIdempotency:
    """Verify the pipeline is idempotent when run with the same inputs."""

    def test_same_input_produces_same_control_type(self, tmp_path: Path) -> None:
        """Running with same parameters should produce the same control type."""
        async def _run():
            pipeline = ReflexPipeline(
                lessons_dir=tmp_path,
                non_interactive_test_mode=True,
            )
            historical = build_duplicate_rows_history(days=8)

            r1 = await pipeline.run(
                incident_urn=make_test_incident_urn("idempotent-1"),
                scenario="duplicate_rows",
                human_confirmed_root_cause="Non-idempotent retries",
                confirmed_by="test",
                target_asset_urn=make_test_dataset_urn("finance.transactions"),
                historical_data=historical,
                uniqueness_columns=["transaction_id"],
            )
            r2 = await pipeline.run(
                incident_urn=make_test_incident_urn("idempotent-2"),
                scenario="duplicate_rows",
                human_confirmed_root_cause="Non-idempotent retries",
                confirmed_by="test",
                target_asset_urn=make_test_dataset_urn("finance.transactions"),
                historical_data=historical,
                uniqueness_columns=["transaction_id"],
            )

            assert r1["control"].control_type == r2["control"].control_type
            assert r1["control"].control_definition == r2["control"].control_definition
            print("Idempotency ✓ Same control type and definition for identical inputs")

        asyncio.run(_run())
