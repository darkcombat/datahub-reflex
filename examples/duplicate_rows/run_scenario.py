#!/usr/bin/env python3
"""Example: Run the duplicate-rows scenario end-to-end.

This demonstrates the complete Reflex loop for Scenario 1:
1. Load a resolved incident about duplicate transactions
2. Confirm the root cause (human-in-the-loop)
3. Extract a structured lesson
4. Synthesize a UniquenessControl
5. Backtest against historical snapshots
6. (Human approval step)
7. Detect similar assets
8. Check for analogous issues on similar assets

Usage:
    python examples/duplicate_rows/run_scenario.py

Prerequisites:
    python scripts/seed_history.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from reflex.core.pipeline import ReflexPipeline

DEFAULT_DAILY_URN = "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_daily_ledger,PROD)"
DEFAULT_MONTHLY_URN = "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_monthly_ledger,PROD)"
LIVE_MANIFEST = Path("./datasets/live_seed_manifest.json")


def load_asset_config() -> tuple[str, str, str, bool]:
    """Return incident/source/analogous URNs for synthetic or live mode."""
    use_live = os.environ.get("REFLEX_LIVE_DATAHUB", "").lower() in {"1", "true", "yes"}
    if not use_live:
        return "urn:li:incident:dup-rows-001", DEFAULT_DAILY_URN, DEFAULT_MONTHLY_URN, False
    if not LIVE_MANIFEST.exists():
        raise RuntimeError(
            "REFLEX_LIVE_DATAHUB is enabled but datasets/live_seed_manifest.json is missing. "
            "Run: python scripts/seed_live_datahub.py seed"
        )
    manifest = json.loads(LIVE_MANIFEST.read_text())
    datasets = manifest["datasets"]
    return (
        manifest["incident"],
        datasets["reflex_finance_daily_ledger"],
        datasets["reflex_finance_monthly_ledger"],
        True,
    )


def load_historical_data() -> list:
    """Load historical snapshots for the duplicate-rows scenario."""
    history_file = Path("./datasets/history/duplicate_rows/historical_snapshots.json")
    if not history_file.exists():
        print("ERROR: Historical data not found. Run: python scripts/seed_history.py")
        sys.exit(1)

    snapshots_raw = json.loads(history_file.read_text())
    # Convert to (datetime, rows) tuples
    from datetime import datetime

    return [
        (datetime.fromisoformat(s["timestamp"]), s["rows"])
        for s in snapshots_raw
    ]


async def main() -> None:
    print("=" * 70)
    print("DataHub Reflex — Scenario 1: Duplicate Rows")
    print("Non-idempotent retries -> duplicate transactions -> UniquenessControl")
    print("=" * 70)

    incident_urn, target_asset_urn, analogous_asset_urn, use_live = load_asset_config()

    # Load historical data
    historical_data = load_historical_data()
    print(f"\nLoaded {len(historical_data)} historical snapshots.")

    # The last anomalous snapshot is used as the analogous future incident on
    # the propagated monthly ledger. The mapping keeps asset identity explicit
    # instead of relying on list ordering.
    analogous_current_data = {analogous_asset_urn: historical_data[-2][1]}

    # Create the pipeline
    pipeline = ReflexPipeline(
        lessons_dir=Path("./datasets"),
        approval_required=True,
        non_interactive_test_mode=True,
        use_live_datahub=use_live,
    )

    # Run the pipeline
    result = await pipeline.run(
        incident_urn=incident_urn,
        scenario="duplicate_rows",
        human_confirmed_root_cause=(
            "The ingestion pipeline's retry logic is not idempotent. "
            "After a partial failure, retried batches re-inserted already-committed rows, "
            "producing duplicate transaction_ids."
        ),
        confirmed_by="alice@example.com",
        target_asset_urn=target_asset_urn,
        historical_data=historical_data,
        current_data=analogous_current_data,
        uniqueness_columns=["transaction_id"],
    )

    # Display results
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)

    lesson = result["lesson"]
    print(f"\nLesson: {lesson.lesson_id}")
    print(f"  Title: {lesson.title}")
    print(f"  Confirmed by: {lesson.confirmed_or_edited_by}")
    print(f"  Confidence: {lesson.confidence.value}")

    control = result["control"]
    print(f"\nControl: {control.control_id}")
    print(f"  Type: {control.control_type.value}")
    print(f"  Definition: {control.control_definition[:80]}...")

    summary = result["backtest_summary"]
    print("\nBacktest Results:")
    print(f"  Snapshots evaluated: {summary.total_snapshots}")
    print(f"  Detections: {summary.detections}")
    print(f"  Detection rate: {summary.detection_rate:.1%}")
    print(f"  Precision: {summary.precision:.1%}")
    print(f"  Would have prevented incident: {summary.would_have_prevented}")

    # Show individual backtest results
    print("\nPer-snapshot results:")
    for r in result["backtest_results"]:
        status = "DETECTED" if r.would_have_detected else "CLEAN"
        print(f"  {r.historical_window_start.date()} - {status} (TP={r.true_positives}, FP={r.false_positives})")

    print(f"\nSimilar assets: {len(result['similar_assets'])}")
    print(f"Detection results: {len(result['detection_results'])}")
    for detection in result["detection_results"]:
        status = "DETECTED" if not detection.passed else "CLEAN"
        print(
            f"  {detection.asset_urn} - {status} "
            f"(violations={detection.violation_count})"
        )

    print("\nScenario 1 complete.")


if __name__ == "__main__":
    asyncio.run(main())
