#!/usr/bin/env python3
"""Seed the minimum real DataHub graph required by the duplicate-rows demo.

This script deliberately seeds only metadata that the live Reflex resolver
can inspect. Metadata is safe to upsert. Each ``seed`` run records a fresh
isolated demo incident and updates the local manifest to point to it; remote
metadata is not destructively deleted by ``reset``.

Commands:
    python scripts/seed_live_datahub.py seed
    python scripts/seed_live_datahub.py verify
    python scripts/seed_live_datahub.py reset

``reset`` removes the local manifest only. DataHub OSS does not provide a
safe generic delete operation for all emitted aspects, so the script never
pretends to perform a destructive remote reset.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from datahub.emitter.mce_builder import make_dataset_urn
from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.emitter.rest_emitter import DatahubRestEmitter
from datahub.metadata.schema_classes import (
    CorpUserInfoClass,
    DatasetLineageTypeClass,
    DatasetPropertiesClass,
    DomainPropertiesClass,
    DomainsClass,
    OtherSchemaClass,
    SchemaFieldClass,
    SchemaFieldDataTypeClass,
    SchemaMetadataClass,
    StringTypeClass,
    UpstreamClass,
    UpstreamLineageClass,
)

from reflex.datahub.read_client import DataHubReadClient
from reflex.datahub.write_client import DataHubWriteClient

GMS_URL = os.environ.get("DATAHUB_GMS_URL", "http://localhost:8080")
PLATFORM = "bigquery"
ENV = "PROD"
MANIFEST = Path("datasets/live_seed_manifest.json")

DATASETS = {
    name: make_dataset_urn(PLATFORM, name, ENV)
    for name in (
        "reflex_finance_raw_transactions",
        "reflex_finance_daily_ledger",
        "reflex_finance_monthly_ledger",
    )
}
REFLEX_TAG = "urn:li:tag:reflex-demo-finance"
FINANCE_TAG = "urn:li:tag:finance"
APPEND_ONLY_TAG = "urn:li:tag:append-only"
FINANCE_DOMAIN = "urn:li:domain:finance"


def _emit(
    emitter: DatahubRestEmitter,
    urn: str,
    aspect_name: str,
    aspect: object,
    entity_type: str = "dataset",
) -> None:
    emitter.emit(
        MetadataChangeProposalWrapper(
            entityUrn=urn,
            entityType=entity_type,
            aspectName=aspect_name,
            aspect=aspect,
        )
    )


def _seed_datasets(emitter: DatahubRestEmitter) -> None:
    schemas = {
        "reflex_finance_raw_transactions": [("transaction_id", "STRING"), ("amount", "DOUBLE")],
        "reflex_finance_daily_ledger": [
            ("transaction_id", "STRING"),
            ("ledger_date", "DATE"),
            ("amount", "DOUBLE"),
        ],
        "reflex_finance_monthly_ledger": [
            ("transaction_id", "STRING"),
            ("ledger_month", "STRING"),
            ("amount", "DOUBLE"),
        ],
    }
    for name, urn in DATASETS.items():
        _emit(
            emitter,
            urn,
            "datasetProperties",
            DatasetPropertiesClass(
                name=name,
                description="DataHub Reflex duplicate-rows demo asset",
                customProperties={
                    "reflex.demo": "duplicate_rows",
                    "reflex:write_pattern": "append-only",
                    "reflex:has_idempotency_key": "false",
                },
            ),
        )
        fields = [
            SchemaFieldClass(
                fieldPath=field,
                type=SchemaFieldDataTypeClass(type=StringTypeClass()),
                nativeDataType=data_type,
                nullable=False,
            )
            for field, data_type in schemas[name]
        ]
        _emit(
            emitter,
            urn,
            "schemaMetadata",
            SchemaMetadataClass(
                schemaName=name,
                platform=f"urn:li:dataPlatform:{PLATFORM}",
                version=0,
                hash=f"reflex-{name}",
                platformSchema=OtherSchemaClass(rawSchema="reflex-demo"),
                fields=fields,
            ),
        )
        _emit(emitter, urn, "domains", DomainsClass(domains=[FINANCE_DOMAIN]))

    _emit(
        emitter,
        DATASETS["reflex_finance_daily_ledger"],
        "upstreamLineage",
        UpstreamLineageClass(
            upstreams=[
                UpstreamClass(
                    dataset=DATASETS["reflex_finance_raw_transactions"],
                    type=DatasetLineageTypeClass.TRANSFORMED,
                )
            ]
        ),
    )


    _emit(
        emitter,
        DATASETS["reflex_finance_monthly_ledger"],
        "upstreamLineage",
        UpstreamLineageClass(
            upstreams=[
                UpstreamClass(
                    dataset=DATASETS["reflex_finance_daily_ledger"],
                    type=DatasetLineageTypeClass.TRANSFORMED,
                )
            ]
        ),
    )


def _seed_users_and_ownership(emitter: DatahubRestEmitter) -> list[tuple[str, str]]:
    users = {
        "bob": (False, "Former Finance Engineer"),
        "alice": (True, "Finance Data Steward"),
        "charlie": (True, "Data Platform Lead"),
    }
    for username, (active, title) in users.items():
        _emit(
            emitter,
            f"urn:li:corpuser:{username}",
            "corpUserInfo",
            CorpUserInfoClass(active=active, displayName=username.title(), title=title),
            entity_type="corpuser",
        )
    return [
        (DATASETS["reflex_finance_daily_ledger"], "urn:li:corpuser:bob"),
        (DATASETS["reflex_finance_monthly_ledger"], "urn:li:corpuser:alice"),
        (DATASETS["reflex_finance_raw_transactions"], "urn:li:corpuser:charlie"),
    ]


async def seed() -> None:
    emitter = DatahubRestEmitter(gms_server=GMS_URL, openapi_ingestion=True)
    _emit(
        emitter,
        FINANCE_DOMAIN,
        "domainProperties",
        DomainPropertiesClass(
            name="Finance",
            description="Finance data products used by the Reflex live demo",
        ),
        entity_type="domain",
    )
    _seed_datasets(emitter)
    writer = DataHubWriteClient(gms_url=GMS_URL)
    ownership = _seed_users_and_ownership(emitter)
    for asset_urn, owner_urn in ownership:
        await writer.update_owner(asset_urn, owner_urn)
    await writer.create_tag("reflex-demo-finance", "reflex-demo-finance", "Reflex live demo asset")
    await writer.create_tag("finance", "finance", "Finance domain data")
    await writer.create_tag("append-only", "append-only", "Dataset uses append-only writes")
    for urn in DATASETS.values():
        await writer.add_tag(urn, REFLEX_TAG)
        await writer.add_tag(urn, FINANCE_TAG)
        await writer.add_tag(urn, APPEND_ONLY_TAG)

    incident = await writer.raise_incident(
        title="REFLEX DEMO: duplicate rows in reflex_finance_daily_ledger",
        description=(
            "Human-confirmed demo incident: a non-idempotent retry inserted duplicate "
            "transaction rows into the daily ledger."
        ),
        resource_urn=DATASETS["reflex_finance_daily_ledger"],
        custom_type="REFLEX_DEMO_DUPLICATE_ROWS",
    )
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        json.dumps(
            {"gms_url": GMS_URL, "datasets": DATASETS, "tag": REFLEX_TAG, "incident": incident},
            indent=2,
        )
    )
    print(f"Seeded {len(DATASETS)} live datasets and incident {incident}")


async def verify() -> None:
    if not MANIFEST.exists():
        raise SystemExit("Manifest missing; run seed first")
    manifest = json.loads(MANIFEST.read_text())
    reader = DataHubReadClient(gms_url=GMS_URL)
    results = await reader._query(
        """
        query($query: String!, $start: Int!, $count: Int!) {
          searchAcrossEntities(input: {types: [DATASET], query: $query, start: $start, count: $count}) {
            searchResults { entity { urn } }
          }
        }
        """,
        {"query": "reflex_finance", "start": 0, "count": 10},
    )
    found = {r["entity"]["urn"] for r in results["searchAcrossEntities"]["searchResults"]}
    missing = set(manifest["datasets"].values()) - found
    if missing:
        raise SystemExit(f"Live seed verification failed; missing: {sorted(missing)}")
    print(f"Verified {len(found)} live Reflex datasets in DataHub")


def reset() -> None:
    if MANIFEST.exists():
        MANIFEST.unlink()
    print("Removed local live-seed manifest. Remote DataHub aspects were preserved.")


async def main(command: str) -> None:
    if command == "seed":
        await seed()
    elif command == "verify":
        await verify()
    elif command == "reset":
        reset()
    else:
        raise SystemExit("Usage: seed | verify | reset")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["seed", "verify", "reset"])
    args = parser.parse_args()
    asyncio.run(main(args.command))
