from __future__ import annotations

import pytest

from reflex.core.similarity import DataHubLiveQueryError, DataHubSimilarityResolver


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
