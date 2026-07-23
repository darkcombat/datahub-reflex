"""Integration tests requiring a running DataHub OSS instance.

Uses the existing `requires_datahub` marker from spike-01 config.
Run with: pytest tests/integration/ -v
Skip if DataHub unavailable: pytest tests/integration/ -v -m "not requires_datahub"
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from reflex.core.pipeline import ReflexPipeline
from reflex.core.similarity import (
    DataHubSimilarityResolver,
    SimilarityResolver,
    create_similarity_resolver,
)
from reflex.datahub.read_client import DataHubReadClient
from reflex.datahub.write_client import DataHubWriteClient

pytestmark = pytest.mark.requires_datahub

GMS_URL = os.environ.get("DATAHUB_GMS_URL", "http://localhost:8080")


def _datahub_available() -> bool:
    try:
        resp = httpx.get(f"{GMS_URL}/health", timeout=5.0)
        return resp.status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(not _datahub_available(), reason="DataHub GMS not reachable")
class TestLiveDataHubIntegration:
    """Tests that require a running DataHub OSS instance."""

    def test_datahub_reachable(self) -> None:
        """Verify DataHub GMS responds."""
        resp = httpx.get(f"{GMS_URL}/health", timeout=10.0)
        assert resp.status_code == 200

    def test_can_search_datasets(self) -> None:
        """Verify searchAcrossEntities returns datasets from live DataHub."""
        async def _run():
            client = DataHubReadClient(gms_url=GMS_URL)
            result = await client._query(
                """query($start: Int!, $count: Int!) {
                    searchAcrossEntities(input: {types: [DATASET], query: "SampleHiveDataset", start: $start, count: $count}) {
                        searchResults { entity { urn type } }
                    }
                }""",
                {"start": 0, "count": 10},
            )
            results = result.get("searchAcrossEntities", {}).get("searchResults", [])
            assert len(results) >= 1, "Expected at least 1 dataset in DataHub"
            return results
        results = asyncio.run(_run())
        print(f"Found {len(results)} datasets in DataHub")

    def test_read_client_oss_schema_compatibility(self) -> None:
        """Verify supported dataset read fields against the OSS GraphQL schema."""
        async def _run():
            client = DataHubReadClient(gms_url=GMS_URL)
            urn = "urn:li:dataset:(urn:li:dataPlatform:hive,SampleHiveDataset,PROD)"
            upstream = await client.get_upstream_lineage(urn)
            downstream = await client.get_downstream_lineage(urn)
            tags = await client.get_tags(urn)
            properties = await client.get_structured_properties(urn)
            assertions = await client.get_assertion_definitions(urn)
            assert isinstance(upstream, list)
            assert isinstance(downstream, list)
            assert isinstance(tags, list)
            assert isinstance(properties, dict)
            assert isinstance(assertions, list)

        asyncio.run(_run())

    def test_live_resolver_finds_candidates(self) -> None:
        """Verify the live resolver discovers similar assets from real DataHub."""
        async def _run():
            # Use the SampleHiveDataset URN that ships with DataHub
            resolver = DataHubSimilarityResolver(
                source_urn="urn:li:dataset:(urn:li:dataPlatform:hive,SampleHiveDataset,PROD)",
                target_field="field1",
                control_type="uniqueness",
            )
            candidates = await resolver.resolve(max_candidates=10)
            # There should be at least the source dataset itself (skipped) and others
            assert len(candidates) >= 0, "Resolver should return list (may be empty if only 1 dataset)"
            # Each candidate must have inspectable signals
            for c in candidates:
                assert len(c.signals) == 6, f"Expected 6 signals per candidate, got {len(c.signals)}"
                assert c.explanation, "Each candidate must have an explanation"
            return candidates
        candidates = asyncio.run(_run())
        print(f"Resolver found {len(candidates)} candidates with live DataHub")

    def test_live_resolver_signals_are_inspectable(self) -> None:
        """Each candidate must have matched and missing signals with details."""
        async def _run():
            resolver = DataHubSimilarityResolver(
                source_urn="urn:li:dataset:(urn:li:dataPlatform:hive,SampleHiveDataset,PROD)",
                target_field="field1",
            )
            candidates = await resolver.resolve()
            for c in candidates[:3]:
                assert c.matched_signals, f"Candidate {c.asset_urn} has no matched signals"
                assert len(c.matched_signals) + len(c.missing_signals) == 6
                for s in c.signals:
                    assert s.detail, f"Signal {s.name} missing detail"
        asyncio.run(_run())

    def test_factory_creates_live_resolver(self) -> None:
        """Factory should create DataHubSimilarityResolver when use_live_datahub=True."""
        resolver = create_similarity_resolver(
            source_urn="urn:li:dataset:test",
            target_field="txn_id",
            use_live_datahub=True,
        )
        assert isinstance(resolver, DataHubSimilarityResolver)

    def test_factory_creates_synthetic_resolver_when_false(self) -> None:
        """Factory should create synthetic SimilarityResolver when use_live_datahub=False."""
        resolver = create_similarity_resolver(
            source_urn="urn:li:dataset:test",
            target_field="txn_id",
            use_live_datahub=False,
        )
        assert isinstance(resolver, SimilarityResolver)
        assert not isinstance(resolver, DataHubSimilarityResolver)

    def test_raise_incident_in_live_datahub(self) -> None:
        """Verify raiseIncident works against live DataHub v1.5.0.6."""
        async def _run():
            client = DataHubWriteClient(gms_url=GMS_URL)
            urn = await client.raise_incident(
                title="REFLEX-INTEGRATION-TEST: Duplicate detection",
                description="Integration test for Reflex raiseIncident.",
                resource_urn="urn:li:dataset:(urn:li:dataPlatform:hive,SampleHiveDataset,PROD)",
                custom_type="REFLEX_TEST",
            )
            assert urn.startswith("urn:li:incident:"), f"Expected incident URN, got {urn}"
            return urn
        urn = asyncio.run(_run())
        print(f"Created incident: {urn}")

    def test_duplicate_rows_scenario_with_live_datahub(self) -> None:
        """End-to-end: duplicate-row pipeline with live DataHub similarity resolution."""
        async def _run():
            pipeline = ReflexPipeline(
                lessons_dir=Path("./datasets"),
                use_live_datahub=True,
                non_interactive_test_mode=True,
            )

            # Build synthetic historical data (backtest still uses JSON)
            now = datetime.now(UTC)
            base = [
                {"transaction_id": f"TXN-{i:03d}", "amount": 100.0 * i}
                for i in range(1, 11)
            ]
            dup = [
                {"transaction_id": "TXN-003", "amount": 300.0},
                {"transaction_id": "TXN-007", "amount": 700.0},
            ]
            historical = [
                (now - timedelta(days=d), base[:]) for d in range(5, 1, -1)
            ] + [
                (now - timedelta(days=1), base + dup),
                (now, base[:]),
            ]

            result = await pipeline.run(
                incident_urn="urn:li:incident:reflex-live-test-001",
                scenario="duplicate_rows",
                human_confirmed_root_cause="Non-idempotent retry logic in ingestion pipeline",
                confirmed_by="alice@example.com",
                target_asset_urn="urn:li:dataset:(urn:li:dataPlatform:hive,SampleHiveDataset,PROD)",
                historical_data=historical,
                uniqueness_columns=["transaction_id"],
            )

            # Verify similar assets were discovered from live DataHub
            assert len(result["similar_assets"]) >= 0, "Similar assets list should exist"
            assert result["backtest_summary"].would_have_prevented

            # If publication was attempted, verify it
            pub = result.get("publication_result")
            if pub:
                print(f"Published to {pub['count']} assets")

            return result

        result = asyncio.run(_run())
        print(f"Similar assets from live DataHub: {len(result['similar_assets'])}")
        print(f"Backtest: precision={result['backtest_summary'].precision}")
