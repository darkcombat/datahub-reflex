#!/usr/bin/env python3
"""Example: Run the orphaned-ownership scenario end-to-end.

This demonstrates the complete Reflex loop for Scenario 2:
1. Load a resolved incident about orphaned ownership
2. Confirm the root cause (human-in-the-loop)
3. Extract a structured lesson
4. Synthesize an ActiveOwnershipControl
5. Backtest against historical ownership snapshots
6. (Human approval step)
7. Detect similar assets
8. Propose active operational owners from domain

Usage:
    python examples/orphaned_ownership/run_scenario.py

Prerequisites:
    python scripts/seed_history.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from reflex.core.pipeline import ReflexPipeline


def load_historical_data() -> list:
    """Load historical ownership snapshots."""
    history_file = Path("./datasets/history/orphaned_ownership/historical_snapshots.json")
    if not history_file.exists():
        print("ERROR: Historical data not found. Run: python scripts/seed_history.py")
        sys.exit(1)

    snapshots_raw = json.loads(history_file.read_text())
    from datetime import datetime

    return [
        (datetime.fromisoformat(s["timestamp"]), s["assets"])
        for s in snapshots_raw
    ]


async def main() -> None:
    print("=" * 70)
    print("DataHub Reflex — Scenario 2: Orphaned Ownership")
    print("Inactive employee -> orphaned assets -> ActiveOwnershipControl")
    print("=" * 70)

    historical_data = load_historical_data()
    print(f"\nLoaded {len(historical_data)} historical snapshots.")

    pipeline = ReflexPipeline(
        lessons_dir=Path("./datasets"),
        approval_required=True,
        non_interactive_test_mode=True,
    )

    result = await pipeline.run(
        incident_urn="urn:li:incident:orphaned-owner-001",
        scenario="orphaned_ownership",
        human_confirmed_root_cause=(
            "Employee bob was deactivated on 2026-06-01 but remained listed as "
            "TECHNICAL_OWNER of finance.transactions. The offboarding process does "
            "not update DataHub ownership assignments."
        ),
        confirmed_by="alice@example.com",
        target_asset_urn="urn:li:dataset:(urn:li:dataPlatform:bigquery,finance.transactions,PROD)",
        historical_data=historical_data,
    )

    # Display results
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)

    lesson = result["lesson"]
    print(f"\nLesson: {lesson.lesson_id}")
    print(f"  Title: {lesson.title}")
    print(f"  Confirmed by: {lesson.confirmed_or_edited_by}")
    print(f"  Failure category: {lesson.failure_pattern.category.value}")

    control = result["control"]
    print(f"\nControl: {control.control_id}")
    print(f"  Type: {control.control_type.value}")
    print(f"  Definition: {control.control_definition}")

    summary = result["backtest_summary"]
    print("\nBacktest Results:")
    print(f"  Snapshots evaluated: {summary.total_snapshots}")
    print(f"  Detections: {summary.detections}")
    print(f"  Detection rate: {summary.detection_rate:.1%}")
    print(f"  Precision: {summary.precision:.1%}")
    print(f"  Would have prevented incident: {summary.would_have_prevented}")

    # Show violation timeline
    print("\nPer-snapshot results:")
    for r in result["backtest_results"]:
        status = "ORPHANED" if r.would_have_detected else "OK"
        print(f"  {r.historical_window_start.date()} - {status} (violations={r.true_positives})")

    # Proposed remediation (ownership fallback)
    print("\nProposed remediation:")
    for asset in historical_data[-1][1]:
        owners = asset.get("owners", [])
        inactive = [o["username"] for o in owners if o.get("type") == "TECHNICAL_OWNER" and not o.get("active", True)]
        if inactive:
            domain = asset.get("domain", "unknown")
            print(f"  {asset['asset_urn']}:")
            print(f"    Inactive owners: {inactive}")
            print(f"    Domain fallback: check domain '{domain}' for active owners")

    print("\nScenario 2 complete.")


if __name__ == "__main__":
    asyncio.run(main())
