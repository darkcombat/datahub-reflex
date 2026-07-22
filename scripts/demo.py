#!/usr/bin/env python3
"""DataHub Reflex -- Hackathon Demo Script.

Runs a complete demo showing both scenarios end-to-end, then launches the UI.
Purely local -- no DataHub required for the synthetic demo path.

Usage:
    python scripts/demo.py              # Full demo (CLI)
    python scripts/demo.py --ui         # Launch UI after CLI demo
    python scripts/demo.py --ui-only    # Only launch UI
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reflex.core.pipeline import ReflexPipeline

# ---------------------------------------------------------------------------
# Historical data builders (same as tests/integration/conftest.py)
# ---------------------------------------------------------------------------

def build_duplicate_rows_history(days: int = 8) -> list[tuple[datetime, list[dict]]]:
    now = datetime.now(UTC)
    base = [{"transaction_id": f"TXN-{i:03d}", "amount": 100.0 * i} for i in range(1, 11)]
    dup_row = [{"transaction_id": "TXN-003", "amount": 300.0}, {"transaction_id": "TXN-007", "amount": 700.0}]
    data = []
    for d in range(days, 0, -1):
        snapshot = list(base)
        if d <= 2:
            snapshot.extend(dup_row)
        data.append((now - timedelta(days=d), snapshot))
    return data


def build_orphaned_ownership_history(days: int = 8) -> list[tuple[datetime, list[dict]]]:
    now = datetime.now(UTC)
    active = [{"owner": "alice", "type": "TECHNICAL_OWNER", "active": True}, {"owner": "charlie", "type": "TECHNICAL_OWNER", "active": True}]
    inactive = [{"owner": "bob", "type": "TECHNICAL_OWNER", "active": False}, {"owner": "alice", "type": "TECHNICAL_OWNER", "active": True}]
    data = []
    for d in range(days, 0, -1):
        data.append((now - timedelta(days=d), inactive if d == 1 else active))
    return data


# ---------------------------------------------------------------------------
# Demo runner
# ---------------------------------------------------------------------------

SEPARATOR = "=" * 60


async def run_scenario(name: str, scenario: str, incident_urn: str, root_cause: str,
                       target: str, history: list, current_data: list | dict | None = None,
                       **kwargs) -> dict:
    """Run a single scenario and print results."""
    print(f"\n{SEPARATOR}")
    print(f"  DataHub Reflex -- {name}")
    print(f"{SEPARATOR}")

    pipeline = ReflexPipeline(
        lessons_dir=Path("./datasets"),
        non_interactive_test_mode=True,
    )

    print(f"\n[1/9] Resolved Incident: {incident_urn}")
    print(f"[2/9] Root Cause (human-confirmed): {root_cause[:100]}...")

    result = await pipeline.run(
        incident_urn=incident_urn,
        scenario=scenario,
        human_confirmed_root_cause=root_cause,
        confirmed_by="demo-user@reflex",
        target_asset_urn=target,
        historical_data=history,
        current_data=current_data,
        **kwargs,
    )

    lesson = result["lesson"]
    control = result["control"]
    summary = result["backtest_summary"]

    print("\n[3/9] Structured Lesson:")
    print(f"       Lesson ID:  {lesson.lesson_id}")
    print(f"       Title:      {lesson.title}")
    fp = lesson.failure_pattern
    fp_str = fp.value if hasattr(fp, 'value') else str(fp)
    print(f"       Pattern:    {fp_str}")
    print(f"       Confidence: {lesson.confidence.value if hasattr(lesson.confidence, 'value') else lesson.confidence}")

    print("\n[4/9] Preventive Control:")
    print(f"       Control ID: {control.control_id}")
    print(f"       Type:       {control.control_type.value if hasattr(control.control_type, 'value') else control.control_type}")
    print(f"       Definition: {control.control_definition[:120]}...")

    print("\n[5/9] Similar Assets:")
    sim = result.get("similar_assets", [])
    for a in sim[:5]:
        urn = a.asset_urn if hasattr(a, 'asset_urn') else str(a)
        conf = a.confidence.value if hasattr(a.confidence, 'value') else str(getattr(a, 'confidence', '?'))
        rat = getattr(a, 'similarity_rationale', '')[:100]
        print(f"       * {urn.split(',')[-1].rstrip(')')} -- {conf} -- {rat}")

    print("\n[6/9] Backtest Metrics:")
    print(f"       Snapshots:  {summary.total_snapshots}")
    print(f"       Detections: {summary.detections}")
    print(f"       Precision:  {summary.precision:.1%}")
    print(f"       Recall:     {summary.detection_rate:.1%}")
    print(f"       Prevented:  {'[OK] YES' if summary.would_have_prevented else '[X] NO'}")

    print("\n[7/9] Approval: APPROVED (offline test-mode)")
    print("       This CLI path uses test mode; the UI path requires explicit human approval.")

    print("\n[8/9] DataHub Publication:")
    pub = result.get("publication_result")
    if pub and isinstance(pub, dict):
        print(f"       Assets published: {pub.get('count', 0)}")
    else:
        print("       Assertion definitions & run events: REFLEX-OWNED")
        print("       (DataHub OSS v1.5.0.6 endpoints unavailable)")

    print("\n[9/9] Analogous Future Detection:")
    detections = result.get("detection_results", [])
    violations = [d for d in detections if hasattr(d, 'passed') and not d.passed]
    print(f"       Assets checked: {len(detections)}")
    if violations:
        for v in violations:
            print(f"       [X] {v.asset_urn if hasattr(v, 'asset_urn') else v} -- {v.violation_count if hasattr(v, 'violation_count') else '?'} violations")
    else:
        print("       [OK] No violations detected on similar assets.")

    print(f"\n{SEPARATOR}")
    print(f"  {name} -- COMPLETE")
    print(f"{SEPARATOR}")

    return result


async def main_cli() -> None:
    """Run both scenarios via CLI."""
    print(f"\n{'=' * 60}")
    print("  DataHub Reflex -- Hackathon Demo")
    print(f"  Date: {datetime.now(UTC).strftime('%Y-%m-%d')}")
    print("  Mode: SYNTHETIC (no live DataHub required)")
    print(f"{'=' * 60}")

    # Scenario 1: Duplicate Rows
    await run_scenario(
        name="Scenario 1: Duplicate Rows -> UniquenessControl",
        scenario="duplicate_rows",
        incident_urn="urn:li:incident:reflex-demo-dup-001",
        root_cause="Non-idempotent retry logic in the ingestion pipeline caused duplicate inserts on partial failure.",
        target="urn:li:dataset:(urn:li:dataPlatform:bigquery,finance.transactions,PROD)",
        history=build_duplicate_rows_history(8),
        current_data=[
            [{"transaction_id": "TXN-003", "amount": 300.0},
             {"transaction_id": "TXN-003", "amount": 300.0}]
        ],
        uniqueness_columns=["transaction_id"],
    )

    # Scenario 2: Orphaned Ownership
    await run_scenario(
        name="Scenario 2: Orphaned Ownership -> ActiveOwnershipControl",
        scenario="orphaned_ownership",
        incident_urn="urn:li:incident:reflex-demo-orphan-001",
        root_cause="Employee offboarding did not trigger ownership reassignment. Inactive owners remained on critical datasets.",
        target="urn:li:dataset:(urn:li:dataPlatform:bigquery,finance.transactions,PROD)",
        history=build_orphaned_ownership_history(8),
        current_data=[[
            {"owner": "bob", "type": "TECHNICAL_OWNER", "active": False},
            {"owner": "alice", "type": "TECHNICAL_OWNER", "active": True},
        ]],
    )

    # Summary
    print(f"\n{'=' * 60}")
    print("  Demo Complete")
    print("")
    print("  DataHub OSS boundaries respected:")
    print("  * Assertion execution: Reflex-owned (never calls run_assertion)")
    print("  * Assertion definitions: Reflex-owned (upsertAssertion removed in v1.5.0.6)")
    print("  * Run events: Reflex-owned (REST endpoint 404s in OSS v1.5.0.6)")
    print("  * Incidents, ownership, tags, structured properties: DataHub OSS")
    print("")
    print("  Human approval gates: mandatory (bypassed in demo mode)")
    print("  Similarity resolution: 6 signals, synthetic mode")
    print("  Historical data: SYNTHETIC (JSON snapshots)")
    print("")
    print("  Tests: 86 passing (offline/UI/evaluation), 8 require live DataHub")
    print("  UI: python -m ui.app  ->  http://localhost:5000")
    print(f"{'=' * 60}")


def launch_ui() -> None:
    """Launch the Reflex UI."""
    print("\nLaunching Reflex UI at http://localhost:5000 ...")
    print("Press Ctrl+C to stop.\n")
    from ui.app import main
    main()


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="DataHub Reflex Demo")
    parser.add_argument("--ui", action="store_true", help="Launch UI after CLI demo")
    parser.add_argument("--ui-only", action="store_true", help="Only launch UI")
    args = parser.parse_args()

    if args.ui_only:
        launch_ui()
    else:
        asyncio.run(main_cli())
        if args.ui:
            launch_ui()


if __name__ == "__main__":
    main()
