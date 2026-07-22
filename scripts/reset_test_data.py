#!/usr/bin/env python3
"""Reset/cleanup script for Reflex integration test data in DataHub.

Resolves all incidents with customType='REFLEX_TEST' so they don't
accumulate. Does NOT touch any non-test data.

Usage:
    python scripts/reset_test_data.py
    python scripts/reset_test_data.py --dry-run  # List what would be cleaned
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reflex.datahub.read_client import DataHubReadClient
from reflex.datahub.write_client import DataHubWriteClient

GMS_URL = os.environ.get("DATAHUB_GMS_URL", "http://localhost:8080")
GMS_TOKEN = os.environ.get("DATAHUB_GMS_TOKEN", "")


async def list_test_incidents(read_client: DataHubReadClient) -> list[dict]:
    """List all incidents created by Reflex integration tests.

    Searches by customType=REFLEX_TEST using searchAcrossEntities.
    """
    query = """
    query($start: Int!, $count: Int!) {
        searchAcrossEntities(
            input: {
                types: [INCIDENT]
                query: "customType:REFLEX_TEST"
                start: $start
                count: $count
            }
        ) {
            start
            count
            total
            searchResults {
                entity {
                    urn
                    type
                    ... on Incident {
                        title
                        status { state }
                        customType
                        created { time }
                    }
                }
            }
        }
    }
    """
    result = await read_client._query(query, {"start": 0, "count": 100})
    search = result.get("searchAcrossEntities", {})
    results = search.get("searchResults", [])
    total = search.get("total", 0)
    print(f"Found {total} test incidents (showing {len(results)})")
    return results


async def resolve_test_incidents(
    write_client: DataHubWriteClient,
    incidents: list[dict],
    dry_run: bool = False,
) -> int:
    """Resolve all REFLEX_TEST incidents.

    Returns count of resolved incidents.
    """
    count = 0
    for item in incidents:
        entity = item.get("entity", {})
        urn = entity.get("urn", "")
        status = entity.get("status", {}).get("state", "UNKNOWN")
        title = entity.get("title", "")

        if status == "RESOLVED":
            print(f"  SKIP (already resolved): {title[:60]}")
            continue

        if dry_run:
            print(f"  WOULD RESOLVE: {urn} ({title[:60]})")
            count += 1
        else:
            try:
                ok = await write_client.update_incident_status(urn, "RESOLVED")
                if ok:
                    print(f"  RESOLVED: {urn}")
                    count += 1
                else:
                    print(f"  FAILED: {urn}")
            except Exception as e:
                print(f"  ERROR resolving {urn}: {e}")

    return count


async def main(dry_run: bool = False) -> None:
    read = DataHubReadClient(gms_url=GMS_URL, token=GMS_TOKEN)
    write = DataHubWriteClient(gms_url=GMS_URL, token=GMS_TOKEN)

    print("=" * 60)
    print("DataHub Reflex — Reset Test Data")
    print(f"DataHub GMS: {GMS_URL}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print("=" * 60)

    try:
        incidents = await list_test_incidents(read)
        if not incidents:
            print("No REFLEX_TEST incidents found — nothing to clean.")
            return

        resolved = await resolve_test_incidents(write, incidents, dry_run=dry_run)
        print(f"\nResolved {resolved} test incidents.")
    except Exception as e:
        print(f"Error: {e}")
        print("(Is DataHub running? python -m datahub docker quickstart)")
        sys.exit(1)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Reset Reflex test data in DataHub")
    parser.add_argument("--dry-run", action="store_true", help="List without modifying")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
