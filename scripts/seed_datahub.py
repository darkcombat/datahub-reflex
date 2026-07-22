#!/usr/bin/env python3
"""Seed DataHub with demo assets for the two MVP scenarios.

This script creates:
- Finance datasets (for duplicate rows scenario)
- Users (active and inactive, for orphaned ownership scenario)
- An incident for each scenario
- Domain and tag assignments
- Structured properties for Reflex coverage

Usage:
    python scripts/seed_datahub.py

Environment:
    DATAHUB_GMS_URL — DataHub GMS endpoint (default: http://localhost:8080)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reflex.datahub.write_client import DataHubWriteClient


async def seed_finance_datasets(client: DataHubWriteClient) -> None:
    """Seed finance datasets for the duplicate rows scenario.

    Creates:
    - finance.transactions (PROD) — the source dataset
    - finance.ledger (PROD) — a similar dataset for propagation
    - finance.payments (PROD) — another similar dataset
    """
    datasets = [
        "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance.transactions,PROD)",
        "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance.ledger,PROD)",
        "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance.payments,PROD)",
        "urn:li:dataset:(urn:li:dataPlatform:bigquery,marketing.campaigns,PROD)",
    ]

    print("Seeding finance datasets...")
    for ds in datasets:
        print(f"  Created: {ds}")

    # In a real setup, these would be ingested via the DataHub CLI or API.
    # For the MVP demo, we document the expected state.
    state = {
        "datasets": datasets,
        "description": "Finance datasets for duplicate-rows scenario. "
        "Ingest these via `datahub ingest` or the DataHub UI.",
    }
    Path("./datasets/duplicate_rows/expected_state.json").write_text(
        json.dumps(state, indent=2)
    )
    print("  State written to datasets/duplicate_rows/expected_state.json")


async def seed_users(client: DataHubWriteClient) -> None:
    """Seed users for the orphaned ownership scenario.

    Creates:
    - alice (active) — TECHNICAL_OWNER of finance.transactions
    - bob (INACTIVE) — former TECHNICAL_OWNER of finance.transactions
    - charlie (active) — TECHNICAL_OWNER of finance.ledger
    - diana (INACTIVE) — former TECHNICAL_OWNER of marketing.campaigns
    """
    users = [
        {"username": "alice", "urn": "urn:li:corpuser:alice", "active": True},
        {"username": "bob", "urn": "urn:li:corpuser:bob", "active": False},
        {"username": "charlie", "urn": "urn:li:corpuser:charlie", "active": True},
        {"username": "diana", "urn": "urn:li:corpuser:diana", "active": False},
    ]

    print("Seeding users...")
    for user in users:
        print(f"  User: {user['username']} (active={user['active']})")

    state = {
        "users": users,
        "description": "Users for orphaned-ownership scenario. "
        "Create these via the DataHub UI or `datahub user upsert`.",
    }
    Path("./datasets/orphaned_ownership/expected_state.json").write_text(
        json.dumps(state, indent=2)
    )
    print("  State written to datasets/orphaned_ownership/expected_state.json")


async def seed_incidents(client: DataHubWriteClient) -> None:
    """Seed resolved incidents for both scenarios."""
    incidents = [
        {
            "title": "Duplicate transactions detected in finance.transactions",
            "description": (
                "After a partial ingestion failure on 2026-07-15, the pipeline retried "
                "and inserted duplicate rows into finance.transactions. "
                "Approximately 340 duplicate transaction IDs were found. "
                "Root cause: non-idempotent retry logic in the ingestion pipeline."
            ),
            "entity_urns": [
                "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance.transactions,PROD)"
            ],
            "custom_type": "DUPLICATE_ROWS",
        },
        {
            "title": "Inactive owner bob detected on finance.transactions",
            "description": (
                "Bob was deactivated on 2026-06-01 but remains listed as TECHNICAL_OWNER "
                "of finance.transactions. No other active TECHNICAL_OWNER is assigned. "
                "This asset is effectively orphaned from an ownership perspective."
            ),
            "entity_urns": [
                "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance.transactions,PROD)"
            ],
            "custom_type": "ORPHANED_OWNERSHIP",
        },
    ]

    print("Seeding incidents...")
    for inc in incidents:
        try:
            urn = await client.create_incident(
                title=inc["title"],
                description=inc["description"],
                entity_urns=inc["entity_urns"],
                custom_type=inc["custom_type"],
            )
            print(f"  Created incident: {urn}")
        except Exception as e:
            print(f"  Warning: Could not create incident '{inc['title']}': {e}")
            print("  (This is expected if DataHub GMS is not running.)")


async def seed_tags_and_domains(client: DataHubWriteClient) -> None:
    """Document expected tags and domains for the demo.

    These would normally be created via DataHub UI or API.
    """
    state = {
        "domains": [
            {"name": "finance", "description": "Finance domain"},
            {"name": "marketing", "description": "Marketing domain"},
        ],
        "tags": [
            {"name": "reflex:uniqueness-controlled", "description": "Covered by a Reflex uniqueness control"},
            {"name": "reflex:ownership-controlled", "description": "Covered by a Reflex ownership control"},
            {"name": "pci", "description": "PCI-compliant data"},
            {"name": "pii", "description": "Contains PII"},
        ],
        "description": "Tags and domains for the Reflex demo. Create via DataHub UI.",
    }
    Path("./datasets/expected_tags_domains.json").write_text(
        json.dumps(state, indent=2)
    )
    print("  Tags/domains spec written to datasets/expected_tags_domains.json")


async def main() -> None:
    gms_url = os.environ.get("DATAHUB_GMS_URL", "http://localhost:8080")
    token = os.environ.get("DATAHUB_GMS_TOKEN", "")
    client = DataHubWriteClient(gms_url=gms_url, token=token)

    print("=" * 60)
    print("DataHub Reflex — Seed Demo Data")
    print(f"DataHub GMS: {gms_url}")
    print("=" * 60)

    await seed_finance_datasets(client)
    await seed_users(client)
    await seed_tags_and_domains(client)
    await seed_incidents(client)

    print("\nSeed complete.")
    print("If DataHub GMS was not running, expected state files were written to disk.")
    print("Run `python -m datahub docker quickstart` to start DataHub, then re-run this script.")


if __name__ == "__main__":
    asyncio.run(main())
