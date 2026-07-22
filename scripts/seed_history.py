#!/usr/bin/env python3
"""Seed historical data for backtesting the two MVP scenarios.

This script creates synthetic historical snapshots that the ReflexBacktester
can run controls against to demonstrate that the control WOULD HAVE detected
the incident.

For the duplicate rows scenario:
- Creates time-series snapshots of finance.transactions with and without duplicates

For the orphaned ownership scenario:
- Creates time-series snapshots of ownership records showing bob's deactivation

Usage:
    python scripts/seed_history.py
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

HISTORY_DIR = Path("./datasets/history")


def seed_duplicate_rows_history() -> None:
    """Create historical snapshots for the duplicate-rows scenario.

    Timeline:
    - T-7d to T-2d: Clean data, no duplicates
    - T-2d to T-1d: Pipeline partial failure and non-idempotent retry → duplicates appear
    - T-1d to T-0: Duplicates persist (incident detected and resolved)
    """
    now = datetime.now(UTC)
    scenario_dir = HISTORY_DIR / "duplicate_rows"
    scenario_dir.mkdir(parents=True, exist_ok=True)

    base_transactions = [
        {"transaction_id": "TXN-001", "amount": 150.00, "timestamp": "2026-07-14T10:00:00Z"},
        {"transaction_id": "TXN-002", "amount": 250.00, "timestamp": "2026-07-14T11:00:00Z"},
        {"transaction_id": "TXN-003", "amount": 75.50, "timestamp": "2026-07-14T12:00:00Z"},
        {"transaction_id": "TXN-004", "amount": 1000.00, "timestamp": "2026-07-14T13:00:00Z"},
        {"transaction_id": "TXN-005", "amount": 500.00, "timestamp": "2026-07-14T14:00:00Z"},
        {"transaction_id": "TXN-006", "amount": 320.00, "timestamp": "2026-07-14T15:00:00Z"},
        {"transaction_id": "TXN-007", "amount": 890.00, "timestamp": "2026-07-14T16:00:00Z"},
        {"transaction_id": "TXN-008", "amount": 45.00, "timestamp": "2026-07-14T17:00:00Z"},
        {"transaction_id": "TXN-009", "amount": 670.00, "timestamp": "2026-07-14T18:00:00Z"},
        {"transaction_id": "TXN-010", "amount": 1100.00, "timestamp": "2026-07-14T19:00:00Z"},
    ]

    # Duplicate transactions that were inserted by the non-idempotent retry
    duplicate_transactions = [
        {"transaction_id": "TXN-003", "amount": 75.50, "timestamp": "2026-07-14T12:00:00Z"},
        {"transaction_id": "TXN-003", "amount": 75.50, "timestamp": "2026-07-14T12:00:01Z"},
        {"transaction_id": "TXN-007", "amount": 890.00, "timestamp": "2026-07-14T16:00:00Z"},
        {"transaction_id": "TXN-007", "amount": 890.00, "timestamp": "2026-07-14T16:00:01Z"},
        {"transaction_id": "TXN-009", "amount": 670.00, "timestamp": "2026-07-14T18:00:00Z"},
        {"transaction_id": "TXN-009", "amount": 670.00, "timestamp": "2026-07-14T18:00:01Z"},
    ]

    snapshots = []

    # Snapshots before the incident (clean data)
    for days_ago in range(7, 2, -1):
        ts = now - timedelta(days=days_ago)
        snapshots.append({
            "timestamp": ts.isoformat(),
            "rows": base_transactions,
            "description": "Clean data — no duplicates",
        })

    # Snapshot at T-2d (duplicates appear)
    ts = now - timedelta(days=2)
    snapshots.append({
        "timestamp": ts.isoformat(),
        "rows": base_transactions + duplicate_transactions[:4],  # first 2 duplicate groups
        "description": "Partial ingestion failure — duplicates appear for TXN-003 and TXN-007",
    })

    # Snapshot at T-1d (more duplicates)
    ts = now - timedelta(days=1)
    snapshots.append({
        "timestamp": ts.isoformat(),
        "rows": base_transactions + duplicate_transactions,  # all 3 duplicate groups
        "description": "Retry adds more duplicates — TXN-009 also duplicated",
    })

    # Snapshot at T-0 (incident resolved, duplicates cleaned)
    ts = now
    snapshots.append({
        "timestamp": ts.isoformat(),
        "rows": base_transactions,
        "description": "Incident resolved — duplicates cleaned",
    })

    output_path = scenario_dir / "historical_snapshots.json"
    output_path.write_text(json.dumps(snapshots, indent=2, default=str))
    print(f"  Duplicate rows history: {len(snapshots)} snapshots -> {output_path}")


def seed_orphaned_ownership_history() -> None:
    """Create historical ownership snapshots for the orphaned-ownership scenario.

    Timeline:
    - T-7d to T-1d: Bob is active and owns finance.transactions
    - T-0: Bob is deactivated, finance.transactions has no active TECHNICAL_OWNER
    """
    now = datetime.now(UTC)
    scenario_dir = HISTORY_DIR / "orphaned_ownership"
    scenario_dir.mkdir(parents=True, exist_ok=True)

    assets_before = [
        {
            "asset_urn": "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance.transactions,PROD)",
            "owners": [
                {"urn": "urn:li:corpuser:bob", "username": "bob", "type": "TECHNICAL_OWNER", "active": True},
                {"urn": "urn:li:corpuser:alice", "username": "alice", "type": "BUSINESS_OWNER", "active": True},
            ],
            "domain": "finance",
        },
        {
            "asset_urn": "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance.ledger,PROD)",
            "owners": [
                {"urn": "urn:li:corpuser:charlie", "username": "charlie", "type": "TECHNICAL_OWNER", "active": True},
            ],
            "domain": "finance",
        },
    ]

    assets_after = [
        {
            "asset_urn": "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance.transactions,PROD)",
            "owners": [
                {"urn": "urn:li:corpuser:bob", "username": "bob", "type": "TECHNICAL_OWNER", "active": False},
                {"urn": "urn:li:corpuser:alice", "username": "alice", "type": "BUSINESS_OWNER", "active": True},
            ],
            "domain": "finance",
        },
        {
            "asset_urn": "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance.ledger,PROD)",
            "owners": [
                {"urn": "urn:li:corpuser:charlie", "username": "charlie", "type": "TECHNICAL_OWNER", "active": True},
            ],
            "domain": "finance",
        },
        {
            "asset_urn": "urn:li:dataset:(urn:li:dataPlatform:bigquery,marketing.campaigns,PROD)",
            "owners": [
                {"urn": "urn:li:corpuser:diana", "username": "diana", "type": "TECHNICAL_OWNER", "active": False},
            ],
            "domain": "marketing",
        },
    ]

    snapshots = []

    # Snapshots before bob's deactivation
    for days_ago in range(7, 0, -1):
        ts = now - timedelta(days=days_ago)
        snapshots.append({
            "timestamp": ts.isoformat(),
            "assets": assets_before,
            "description": f"T-{days_ago}d: All owners active",
        })

    # Snapshot after bob's deactivation
    ts = now
    snapshots.append({
        "timestamp": ts.isoformat(),
        "assets": assets_after,
        "description": "T-0: Bob deactivated. finance.transactions has no active TECHNICAL_OWNER. "
        "marketing.campaigns (diana) also orphaned.",
    })

    output_path = scenario_dir / "historical_snapshots.json"
    output_path.write_text(json.dumps(snapshots, indent=2, default=str))
    print(f"  Orphaned ownership history: {len(snapshots)} snapshots -> {output_path}")


def main() -> None:
    print("=" * 60)
    print("DataHub Reflex — Seed Historical Data for Backtesting")
    print("=" * 60)

    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    seed_duplicate_rows_history()
    seed_orphaned_ownership_history()

    print("\nHistorical data seeded successfully.")
    print("These snapshots are used by the ReflexBacktester to validate controls.")


if __name__ == "__main__":
    main()
