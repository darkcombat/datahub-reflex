"""End-to-end test for Phase 3 — duplicate-row vertical slice.

This test proves the complete Reflex loop:
resolved incident A → approved root cause → lesson → control → backtest
→ approval → DataHub publication → analogous failure on asset B
→ failed result → new incident in DataHub

This test does NOT require a running DataHub instance.
It tests the complete Reflex business logic with synthetic data.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from reflex.core.approval import ApprovalState
from reflex.core.phase3_pipeline import (
    Phase3Pipeline,
    can_recommend_publication,
    compute_metrics,
)
from reflex.models import (
    BacktestResult,
    ControlId,
    ControlType,
)

# -- Synthetic data ------------------------------------------------------------


def build_duplicate_rows_historical_data() -> list:
    """Build synthetic historical snapshots for the duplicate-row scenario.

    Timeline:
    - T-7 to T-2: Clean data, no duplicates
    - T-2: Duplicates appear (TXN-003, TXN-007 duplicated)
    - T-1: More duplicates (TXN-003, TXN-007, TXN-009 duplicated)
    - T-0: Incident resolved, duplicates cleaned
    """
    now = datetime.now(UTC)
    base_rows = [
        {"transaction_id": f"TXN-{i:03d}", "amount": 100.0 * i, "timestamp": f"2026-07-{10+i:02d}T10:00:00Z"}
        for i in range(1, 11)
    ]

    # Duplicate rows (non-idempotent retry inserts these)
    duplicates_t2 = [
        {"transaction_id": "TXN-003", "amount": 300.0, "timestamp": "2026-07-13T10:00:01Z"},
        {"transaction_id": "TXN-007", "amount": 700.0, "timestamp": "2026-07-13T16:00:01Z"},
    ]

    duplicates_t1 = [
        {"transaction_id": "TXN-003", "amount": 300.0, "timestamp": "2026-07-13T10:00:01Z"},
        {"transaction_id": "TXN-007", "amount": 700.0, "timestamp": "2026-07-13T16:00:01Z"},
        {"transaction_id": "TXN-009", "amount": 900.0, "timestamp": "2026-07-13T18:00:01Z"},
    ]

    snapshots = []
    for days_ago in range(7, 2, -1):
        ts = now - timedelta(days=days_ago)
        snapshots.append((ts, base_rows[:]))

    # T-2: Duplicates appear
    snapshots.append((now - timedelta(days=2), base_rows + duplicates_t2))

    # T-1: More duplicates
    snapshots.append((now - timedelta(days=1), base_rows + duplicates_t1))

    # T-0: Clean after resolution
    snapshots.append((now, base_rows[:]))

    return snapshots


def build_monthly_ledger_with_duplicates() -> list[dict]:
    """Build synthetic finance_monthly_ledger data WITH duplicates injected.

    This simulates Step 9: an analogous failure on a similar asset.
    """
    base = [
        {"transaction_id": f"TXN-{i:03d}", "ledger_month": "2026-07", "amount": 100.0 * i, "category": "general"}
        for i in range(1, 21)
    ]
    # Inject duplicates for 3 transaction IDs
    duplicates = [
        {"transaction_id": "TXN-005", "ledger_month": "2026-07", "amount": 500.0, "category": "general"},
        {"transaction_id": "TXN-005", "ledger_month": "2026-07", "amount": 500.0, "category": "general"},
        {"transaction_id": "TXN-012", "ledger_month": "2026-07", "amount": 1200.0, "category": "general"},
        {"transaction_id": "TXN-012", "ledger_month": "2026-07", "amount": 1200.0, "category": "general"},
        {"transaction_id": "TXN-018", "ledger_month": "2026-07", "amount": 1800.0, "category": "general"},
        {"transaction_id": "TXN-018", "ledger_month": "2026-07", "amount": 1800.0, "category": "general"},
    ]
    return base + duplicates


# -- Tests ---------------------------------------------------------------------


class TestPhase3DuplicateRowE2E:
    """Complete end-to-end test for the duplicate-row vertical slice."""

    @pytest.fixture
    def pipeline(self, tmp_path: Path) -> Phase3Pipeline:
        return Phase3Pipeline(lessons_dir=tmp_path)

    def test_full_loop(self, pipeline: Phase3Pipeline) -> None:
        """Prove the complete Reflex loop for duplicate rows."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._run_full_loop(pipeline))
        finally:
            loop.close()

    async def _run_full_loop(self, pipeline: Phase3Pipeline) -> None:
        incident_urn = "urn:li:incident:dup-rows-001"
        target_asset = "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_daily_ledger,PROD)"
        similar_asset = "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_monthly_ledger,PROD)"

        # -- Step 1: Ingest resolved incident --
        incident = await pipeline.step1_ingest_incident(
            incident_urn=incident_urn,
            incident_title="Duplicate transactions detected in finance_daily_ledger",
            incident_description=(
                "After a partial ingestion failure on 2026-07-19, the pipeline retried "
                "and inserted duplicate rows. 340 duplicate transaction_ids found."
            ),
            incident_custom_type="DUPLICATE_ROWS",
            affected_asset_urn=target_asset,
            proposed_root_cause=(
                "Non-idempotent retry logic in the ingestion pipeline. "
                "Append-only writes without deduplication key."
            ),
        )
        assert incident["root_cause_confirmed"] is False

        # -- Step 2: Human root-cause approval --
        await pipeline.step2_submit_root_cause(
            incident_urn=incident_urn,
            proposed_root_cause=incident["proposed_root_cause"],
        )
        approval = await pipeline.step2_approve_root_cause(
            incident_urn=incident_urn,
            approver="alice@example.com",
        )
        assert approval.state == ApprovalState.APPROVED
        assert approval.approver == "alice@example.com"

        # -- Step 3: Structured lesson extraction --
        lesson, record = await pipeline.step3_extract_lesson(
            incident_urn=incident_urn,
            incident_title=incident["title"],
            incident_description=incident["description"],
            human_confirmed_root_cause=approval.final_root_cause,
            confirmed_by="alice@example.com",
            target_asset_urn=target_asset,
            incident_custom_type="DUPLICATE_ROWS",
        )
        assert lesson.is_confirmed
        assert lesson.failure_pattern.category.value == "data_quality"
        assert lesson.candidate_preventive_control.control_type == ControlType.UNIQUENESS
        # Verify extraction record was persisted
        assert record.parsed_output is not None
        assert record.parsed_output.failure_category == "duplicate_rows"

        # -- Step 4: Similar-asset discovery --
        candidates = await pipeline.step4_discover_similar_assets(
            source_asset_urn=target_asset,
            target_field="transaction_id",
            propagation_scope=["finance"],
        )
        # Should find at least the monthly ledger
        similar_urns = [c.asset_urn for c in candidates if c.selected]
        assert len(similar_urns) >= 1, f"Expected at least 1 similar asset, got {similar_urns}"
        # Monthly ledger should be a candidate
        assert similar_asset in [c.asset_urn for c in candidates]

        # -- Step 5: Control synthesis --
        control = await pipeline.step5_synthesize_control(
            lesson=lesson,
            target_field="transaction_id",
        )
        assert control.control_type == ControlType.UNIQUENESS
        assert "GROUP BY transaction_id" in control.control_definition
        assert "HAVING COUNT(*) > 1" in control.control_definition

        # -- Step 6: Reflex backtest --
        historical_data = build_duplicate_rows_historical_data()
        results, metrics, can_recommend, blockers = await pipeline.step6_backtest(
            control=control,
            historical_data=historical_data,
            known_incident_snapshots=2,  # T-2 and T-1 have duplicates
        )

        # Verify metrics
        assert len(results) == 8
        assert metrics.true_positives >= 2, f"Expected at least 2 detections, got {metrics.true_positives}"
        assert metrics.recall == 1.0, f"Recall must be 100%, got {metrics.recall:.2%}"
        assert metrics.false_positive_rate <= 0.10, f"FPR must be <= 10%, got {metrics.false_positive_rate:.2%}"
        assert metrics.precision == 1.0, f"Precision must be 100%, got {metrics.precision:.2%}"
        assert can_recommend, f"Control should be recommended. Blockers: {blockers}"

        # -- Step 7: Human control approval --
        approval_pending = await pipeline.step7_submit_control_approval(
            control=control,
            metrics=metrics,
        )
        assert approval_pending.state == ApprovalState.PENDING

        control_approval = await pipeline.step7_approve_control(
            control_id=control.control_id,
            approver="alice@example.com",
        )
        assert control_approval.state == ApprovalState.APPROVED

        # -- Step 8: DataHub publication --
        selected_urns = [c.asset_urn for c in candidates if c.selected]
        publication = await pipeline.step8_publish(
            lesson=lesson,
            control=control,
            approval=control_approval,
            selected_asset_urns=selected_urns,
            backtest_results=results,
        )
        assert publication["publication_status"] == "published"
        assert len(publication["published_assets"]) >= 1

        # -- Step 9: Analogous future incident --
        monthly_data = build_monthly_ledger_with_duplicates()
        detection = await pipeline.step9_detect_analogous_incident(
            control=control,
            similar_asset_urn=similar_asset,
            data_with_duplicates=monthly_data,
        )
        assert detection["detected"] is True, (
            f"Control must detect duplicates on {similar_asset}"
        )
        assert detection["violation_count"] == 3, (
            f"Expected 3 duplicate groups, got {detection['violation_count']}"
        )
        assert detection["control_id"] == control.control_id
        assert "new_incident_title" in detection

        print("\n✓ E2E test passed: Complete duplicate-row Reflex loop verified.")


class TestBacktestMetrics:
    """Unit tests for backtest metric computation."""

    def test_perfect_detection(self) -> None:
        """Control detects exactly the known incidents, no false positives."""
        control_id = ControlId.generate()
        now = datetime.now(UTC)
        results = [
            BacktestResult(
                control_id=control_id, target_asset_urn="urn:li:dataset:test",
                historical_window_start=now, historical_window_end=now,
                would_have_detected=False,
            ),
            BacktestResult(
                control_id=control_id, target_asset_urn="urn:li:dataset:test",
                historical_window_start=now, historical_window_end=now,
                would_have_detected=True, true_positives=2,
            ),
            BacktestResult(
                control_id=control_id, target_asset_urn="urn:li:dataset:test",
                historical_window_start=now, historical_window_end=now,
                would_have_detected=True, true_positives=3,
            ),
            BacktestResult(
                control_id=control_id, target_asset_urn="urn:li:dataset:test",
                historical_window_start=now, historical_window_end=now,
                would_have_detected=False,
            ),
        ]

        metrics = compute_metrics(results, known_incident_snapshots=2)
        assert metrics.true_positives == 2
        assert metrics.false_positives == 0
        assert metrics.true_negatives == 2
        assert metrics.false_negatives == 0
        assert metrics.precision == 1.0
        assert metrics.recall == 1.0
        assert metrics.false_positive_rate == 0.0

    def test_cannot_recommend_with_high_fpr(self) -> None:
        """Control with high false-positive rate should not be recommended."""
        control_id = ControlId.generate()
        now = datetime.now(UTC)
        results = [
            BacktestResult(
                control_id=control_id, target_asset_urn="urn:li:dataset:test",
                historical_window_start=now, historical_window_end=now,
                would_have_detected=True, true_positives=1,
            ),
            BacktestResult(
                control_id=control_id, target_asset_urn="urn:li:dataset:test",
                historical_window_start=now, historical_window_end=now,
                would_have_detected=True, false_positives=5,
            ),
        ]

        can_rec, blockers = can_recommend_publication(
            compute_metrics(results, known_incident_snapshots=1),
            results,
        )
        assert not can_rec
        assert any("false-positive" in b.lower() for b in blockers)

    def test_cannot_recommend_with_insufficient_recall(self) -> None:
        """Control that misses the incident should not be recommended."""
        control_id = ControlId.generate()
        now = datetime.now(UTC)
        results = [
            BacktestResult(
                control_id=control_id, target_asset_urn="urn:li:dataset:test",
                historical_window_start=now, historical_window_end=now,
                would_have_detected=False,
            ),
        ]

        can_rec, blockers = can_recommend_publication(
            compute_metrics(results, known_incident_snapshots=1),
            results,
        )
        assert not can_rec
        assert any("recall" in b.lower() or "detect" in b.lower() for b in blockers)


class TestSimilarityResolver:
    """Tests for the deterministic similarity resolver."""

    def test_finds_similar_assets_by_domain_and_field(self) -> None:
        """Resolver should find assets in the same domain with matching fields."""
        from reflex.core.similarity import SimilarityResolver

        resolver = SimilarityResolver(
            source_urn="urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_daily_ledger,PROD)",
            target_field="transaction_id",
            control_type="uniqueness",
            propagation_scope=["finance"],
        )

        loop = asyncio.new_event_loop()
        try:
            candidates = loop.run_until_complete(resolver.resolve())
        finally:
            loop.close()

        selected = [c for c in candidates if c.selected]
        assert len(selected) >= 1, f"Expected at least 1 selected candidate, got {len(selected)}"

        # Monthly ledger should score high (same domain, same field, append-only)
        monthly = [c for c in candidates if "monthly_ledger" in c.asset_urn]
        assert len(monthly) == 1
        assert monthly[0].score > 0.5, f"Monthly ledger should score high, got {monthly[0].score:.2f}"

    def test_each_candidate_has_signals(self) -> None:
        """Every candidate must have matched and missing signals listed."""
        from reflex.core.similarity import SimilarityResolver

        resolver = SimilarityResolver(
            source_urn="urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_daily_ledger,PROD)",
            target_field="transaction_id",
        )

        loop = asyncio.new_event_loop()
        try:
            candidates = loop.run_until_complete(resolver.resolve())
        finally:
            loop.close()

        for c in candidates:
            assert len(c.signals) == 6, f"Expected 6 signals, got {len(c.signals)}"
            assert len(c.matched_signals) + len(c.missing_signals) == 6
            assert c.explanation, "Each candidate must have an explanation"


class TestLessonExtractor:
    """Tests for lesson extraction and validation."""

    def test_extracts_duplicate_rows_lesson(self) -> None:
        """Extractor should correctly identify duplicate-row pattern."""
        from reflex.core.lesson_extractor import LessonExtractor

        extractor = LessonExtractor()

        loop = asyncio.new_event_loop()
        try:
            lesson, record = loop.run_until_complete(extractor.extract(
                incident_urn="urn:li:incident:dup-001",
                incident_title="Duplicate transactions in ledger",
                incident_description="Duplicate rows found in finance_daily_ledger",
                human_confirmed_root_cause="Non-idempotent retry logic",
                confirmed_by="alice@example.com",
                target_asset_urn="urn:li:dataset:test",
                incident_custom_type="DUPLICATE_ROWS",
            ))
        finally:
            loop.close()

        assert lesson.failure_pattern.category.value == "data_quality"
        assert lesson.candidate_preventive_control.control_type == ControlType.UNIQUENESS
        assert record.parsed_output is not None
        assert record.validation_errors == []
        assert record.parsed_output.candidate_control_type == "uniqueness"

    def test_rejects_wrong_control_type_for_duplicate_incident(self) -> None:
        """Validation should reject mismatch between incident type and control."""
        from reflex.core.lesson_extractor import (
            LessonExtractionResult,
            LessonExtractor,
        )

        extractor = LessonExtractor()

        # Simulate an extraction that returns wrong control type
        bad_extraction = LessonExtractionResult(
            failure_category="duplicate_rows",
            trigger="retry_after_partial_failure",
            vulnerable_characteristics=["append_only_without_idempotency"],
            candidate_control_type="active_ownership",  # WRONG
            target_field="transaction_id",
            propagation_scope=["finance"],
            assumptions=[],
            limitations=[],
            confidence="high",
        )

        errors = extractor._validate_extraction(bad_extraction, "DUPLICATE_ROWS")
        assert len(errors) > 0
        assert any("uniqueness" in e.lower() for e in errors)
