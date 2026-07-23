from __future__ import annotations

import pytest

from reflex.core.similarity import DataHubLiveQueryError, DataHubSimilarityResolver


class _FakeLiveReadClient:
    """Small GraphQL-shaped fixture for the live resolver contract."""

    source = "urn:li:dataset:(urn:li:dataPlatform:bigquery,source,PROD)"
    candidate = "urn:li:dataset:(urn:li:dataPlatform:bigquery,candidate,PROD)"

    async def _query(self, query, variables):
        return {
            "searchAcrossEntities": {
                "searchResults": [
                    {"entity": {
                        "urn": self.source,
                        "type": "DATASET",
                        "name": "source",
                        "platform": {"name": "bigquery"},
                        "domain": {"domain": {"urn": "urn:li:domain:finance", "properties": {"name": "Finance"}}},
                        "tags": {"tags": [{"tag": {"properties": {"name": "finance"}}}]},
                        "schemaMetadata": {"fields": [{"fieldPath": "transaction_id"}]},
                        "ownership": {"owners": []},
                    }},
                    {"entity": {
                        "urn": self.candidate,
                        "type": "DATASET",
                        "name": "candidate",
                        "platform": {"name": "bigquery"},
                        "domain": {"domain": {"urn": "urn:li:domain:finance", "properties": {"name": "Finance"}}},
                        "tags": {"tags": [{"tag": {"properties": {"name": "finance"}}}]},
                        "schemaMetadata": {"fields": [{"fieldPath": "transaction_id"}]},
                        "ownership": {"owners": []},
                    }},
                ]
            }
        }

    async def get_upstream_lineage(self, urn):
        return [] if urn == self.source else [self.source]

    async def get_downstream_lineage(self, urn):
        return [self.candidate] if urn == self.source else []

    async def get_dataset_properties(self, urn):
        return {
            "reflex:write_pattern": "append-only",
            "reflex:has_idempotency_key": "false",
        }


@pytest.mark.asyncio
async def test_live_resolver_does_not_fallback_to_synthetic(monkeypatch):
    resolver = DataHubSimilarityResolver(
        source_urn="urn:li:dataset:test",
        target_field="transaction_id",
    )

    async def fail_fetch():
        raise DataHubLiveQueryError("GMS unavailable")

    monkeypatch.setattr(resolver, "_fetch_datasets_from_datahub", fail_fetch)

    with pytest.raises(DataHubLiveQueryError, match="GMS unavailable"):
        await resolver.resolve()


@pytest.mark.asyncio
async def test_live_resolver_enriches_graph_signals_and_refreshes_source():
    client = _FakeLiveReadClient()
    resolver = DataHubSimilarityResolver(
        source_urn=client.source,
        target_field="transaction_id",
        read_client=client,
    )

    candidates = await resolver.resolve()

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.selected
    assert candidate.score == 1.0
    assert candidate.matched_signals == [
        "same_domain",
        "shared_tags",
        "compatible_schema",
        "append_only_vulnerability",
        "similar_lineage",
        "no_existing_control",
    ]
