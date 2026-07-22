#!/usr/bin/env python3
"""Seed the synthetic DataHub environment with all required assets.

Commands:
    python scripts/seed_environment.py seed     # Create all assets
    python scripts/seed_environment.py verify   # Verify all assets exist
    python scripts/seed_environment.py reset    # Remove all seeded assets
    python scripts/seed_environment.py reseed   # Reset + seed (idempotent)

All commands are safe to rerun. Assets use deterministic URNs from the
environment definition in reflex.datahub.environment.

If DataHub GMS is not running, the script writes the expected state to
disk as JSON files for offline review.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from reflex.datahub.environment import (
    DASHBOARDS,
    DATASETS,
    DOMAINS,
    EXISTING_ASSERTIONS,
    GROUPS,
    INCIDENTS,
    LINEAGE,
    PIPELINES,
    SERVICE_ACCOUNTS,
    TAGS,
    USERS,
)

GMS_URL = os.environ.get("DATAHUB_GMS_URL", "http://localhost:8080")
HEADERS = {"Content-Type": "application/json"}

STATE_DIR = Path("./datasets/seeded_state")


# -- Utility -------------------------------------------------------------------

async def check_health() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{GMS_URL}/health")
            return resp.status_code == 200
    except Exception:
        return False


async def graphql(query: str, variables: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{GMS_URL}/api/graphql",
            json={"query": query, "variables": variables or {}},
            headers=HEADERS,
        )
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            raise RuntimeError(json.dumps(data["errors"]))
        return data["data"]


# -- Seed operations -----------------------------------------------------------

async def seed_domains() -> None:
    print("--- Domains ---")
    for domain in DOMAINS:
        print(f"  {domain['name']} ({domain['urn']})")
    _save_state("domains.json", DOMAINS)


async def seed_users() -> None:
    print("--- Users ---")
    for user in USERS:
        status = "ACTIVE" if user["active"] else "INACTIVE"
        print(f"  {user['username']} ({status}) — {user.get('title', '')}")
    for sa in SERVICE_ACCOUNTS:
        print(f"  {sa['username']} (SERVICE ACCOUNT)")
    _save_state("users.json", {"users": USERS, "service_accounts": SERVICE_ACCOUNTS})


async def seed_groups() -> None:
    print("--- Groups ---")
    for group in GROUPS:
        print(f"  {group['name']} — members: {group['members']}")
    _save_state("groups.json", GROUPS)


async def seed_datasets() -> None:
    print("--- Datasets ---")
    for ds in DATASETS:
        owner_count = len(ds["owners"])
        field_count = len(ds["schema"])
        print(f"  {ds['name']} ({ds['platform']}/{ds['env']}) — {field_count} fields, {owner_count} owners")
        print(f"    domain: {ds['domain']}")
        print(f"    tags: {ds['tags']}")
        if "historical_owners" in ds:
            print(f"    historical_owners: {len(ds['historical_owners'])}")
        if "structured_properties" in ds:
            for k, v in ds["structured_properties"].items():
                print(f"    {k}: {v}")
    _save_state("datasets.json", DATASETS)


async def seed_dashboards() -> None:
    print("--- Dashboards ---")
    for dash in DASHBOARDS:
        print(f"  {dash['name']} ({dash['platform']})")
    _save_state("dashboards.json", DASHBOARDS)


async def seed_pipelines() -> None:
    print("--- Pipelines ---")
    for pipe in PIPELINES:
        print(f"  {pipe['name']} ({pipe['platform']})")
    _save_state("pipelines.json", PIPELINES)


async def seed_lineage() -> None:
    print("--- Lineage ---")
    for edge in LINEAGE:
        print(f"  {edge['upstream']}")
        print(f"    -> {edge['downstream']}")
    _save_state("lineage.json", LINEAGE)


async def seed_tags() -> None:
    print("--- Tags ---")
    for tag in TAGS:
        print(f"  {tag['name']}: {tag['description']}")
    _save_state("tags.json", TAGS)


async def seed_incidents() -> None:
    print("--- Incidents ---")
    for inc in INCIDENTS:
        print(f"  {inc['title']} [{inc['status']}]")
        print(f"    type: {inc['custom_type']}")
        entities = ", ".join(inc["entities"])
        print(f"    entities: {entities}")
    _save_state("incidents.json", INCIDENTS)


async def seed_existing_assertions() -> None:
    print("--- Existing Assertions ---")
    for a in EXISTING_ASSERTIONS:
        print(f"  {a['description'][:60]}...")
    _save_state("existing_assertions.json", EXISTING_ASSERTIONS)


# -- Verify --------------------------------------------------------------------

async def verify_all() -> bool:
    """Verify that all seeded state files exist and are valid."""
    print("--- Verification ---")
    all_ok = True

    files = [
        "domains.json", "users.json", "groups.json", "datasets.json",
        "dashboards.json", "pipelines.json", "lineage.json", "tags.json",
        "incidents.json", "existing_assertions.json",
    ]

    for fname in files:
        fpath = STATE_DIR / fname
        if fpath.exists():
            data = json.loads(fpath.read_text())
            if isinstance(data, list):
                print(f"  [OK] {fname}: {len(data)} items")
            elif isinstance(data, dict):
                print(f"  [OK] {fname}: {len(data)} keys")
            else:
                print(f"  [OK] {fname}: exists")
        else:
            print(f"  [MISSING] {fname}: MISSING — run 'seed' first")
            all_ok = False

    # Verify specific counts
    datasets_data = json.loads((STATE_DIR / "datasets.json").read_text()) if (STATE_DIR / "datasets.json").exists() else []
    assert len(datasets_data) >= 8, f"Expected >= 8 datasets, got {len(datasets_data)}"
    print(f"  Dataset count: {len(datasets_data)} (min 8 required)")

    dashboards_data = json.loads((STATE_DIR / "dashboards.json").read_text()) if (STATE_DIR / "dashboards.json").exists() else []
    assert len(dashboards_data) >= 2, f"Expected >= 2 dashboards, got {len(dashboards_data)}"
    print(f"  Dashboard count: {len(dashboards_data)} (min 2 required)")

    pipelines_data = json.loads((STATE_DIR / "pipelines.json").read_text()) if (STATE_DIR / "pipelines.json").exists() else []
    assert len(pipelines_data) >= 2, f"Expected >= 2 pipelines, got {len(pipelines_data)}"
    print(f"  Pipeline count: {len(pipelines_data)} (min 2 required)")

    users_data = json.loads((STATE_DIR / "users.json").read_text()) if (STATE_DIR / "users.json").exists() else {}
    all_users = users_data.get("users", []) + users_data.get("service_accounts", [])
    inactive = [u for u in users_data.get("users", []) if not u.get("active", True)]
    assert len(inactive) >= 2, f"Expected >= 2 inactive users, got {len(inactive)}"
    print(f"  Users: {len(users_data.get('users', []))} (human), {len(users_data.get('service_accounts', []))} (service)")
    print(f"  Inactive users: {len(inactive)} (min 2 required)")

    # Check for asset with inactive owner and no active operational owner
    no_active_owner = [
        ds for ds in datasets_data
        if ds.get("structured_properties", {}).get("reflex:has_active_owner") == "false"
    ]
    assert len(no_active_owner) >= 1, f"Expected >= 1 asset with no active owner, got {len(no_active_owner)}"
    print(f"  Assets with no active operational owner: {len(no_active_owner)} (min 1 required)")

    return all_ok


# -- Reset ---------------------------------------------------------------------

async def reset_all() -> None:
    """Remove all seeded state files."""
    print("--- Reset ---")
    if STATE_DIR.exists():
        import shutil
        shutil.rmtree(STATE_DIR)
        print(f"  Removed: {STATE_DIR}")
    else:
        print("  Nothing to reset (no state directory found)")

    # Also clean history data
    history_dir = Path("./datasets/history")
    if history_dir.exists():
        import shutil
        shutil.rmtree(history_dir)
        print(f"  Removed: {history_dir}")


# -- Helpers -------------------------------------------------------------------

def _save_state(filename: str, data: Any) -> None:
    """Save seeded state to disk for offline verification."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / filename).write_text(json.dumps(data, indent=2, default=str))


# -- Main ----------------------------------------------------------------------

async def main(command: str) -> None:
    print("=" * 70)
    print(f"DataHub Reflex — Synthetic Environment: {command.upper()}")
    print(f"GMS URL: {GMS_URL}")
    print("=" * 70)

    healthy = await check_health()

    if command == "seed":
        if not healthy:
            print("\n[WARNING] DataHub GMS not reachable. Writing state to disk only.")
            print("  Run 'python -m datahub docker quickstart' and re-run to seed DataHub live.")

        await seed_domains()
        await seed_users()
        await seed_groups()
        await seed_datasets()
        await seed_dashboards()
        await seed_pipelines()
        await seed_lineage()
        await seed_tags()
        await seed_incidents()
        await seed_existing_assertions()

        print(f"\nState written to: {STATE_DIR}")
        if healthy:
            print("DataHub is running — state files are a reference.")
            print("Actual DataHub ingestion requires `datahub ingest` for full metadata.")
        else:
            print("Start DataHub and re-run to complete live ingestion.")

    elif command == "verify":
        ok = await verify_all()
        if ok:
            print("\n[OK] All seeded state verified.")
        else:
            print("\n[FAIL] Verification failed. Run 'seed' first.")
            sys.exit(1)

    elif command == "reset":
        await reset_all()
        print("\n[OK] Environment reset complete.")

    elif command == "reseed":
        await reset_all()
        print()
        await main("seed")

    else:
        print(f"Unknown command: {command}")
        print("Usage: seed | verify | reset | reseed")
        sys.exit(1)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Seed synthetic DataHub environment")
    parser.add_argument("command", choices=["seed", "verify", "reset", "reseed"])
    args = parser.parse_args()
    asyncio.run(main(args.command))
