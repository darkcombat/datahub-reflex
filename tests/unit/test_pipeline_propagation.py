"""Tests for executing an approved control on explicitly mapped similar assets."""

from __future__ import annotations

from reflex.core.pipeline import ReflexPipeline
from reflex.models import (
    ControlId,
    ControlType,
    LessonId,
    ReflexControl,
    SimilarAssetCandidate,
)


async def test_detection_uses_asset_mapping_and_preserves_asset_urn() -> None:
    target = "urn:li:dataset:(urn:li:dataPlatform:bigquery,source,PROD)"
    analogous = "urn:li:dataset:(urn:li:dataPlatform:bigquery,monthly,PROD)"
    control = ReflexControl(
        control_id=ControlId("reflex-control-test"),
        lesson_id=LessonId("reflex-lesson-test"),
        target_asset_urn=target,
        control_type=ControlType.UNIQUENESS,
        control_definition=(
            "SELECT transaction_id, COUNT(*) FROM {dataset} "
            "GROUP BY transaction_id HAVING COUNT(*) > 1"
        ),
    )
    candidate = SimilarAssetCandidate(
        asset_urn=analogous,
        asset_type="dataset",
        similarity_rationale="Same domain and compatible schema",
    )
    duplicate_rows = [
        {"transaction_id": "txn-1", "amount": 10},
        {"transaction_id": "txn-1", "amount": 10},
    ]

    results = await ReflexPipeline(approval_required=True).detect_on_similar_assets(
        control=control,
        similar_assets=[candidate],
        current_data={analogous: duplicate_rows},
    )

    assert len(results) == 1
    assert results[0].asset_urn == analogous
    assert results[0].passed is False
    assert results[0].violation_count == 1
