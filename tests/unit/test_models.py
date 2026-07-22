"""Tests for core domain models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from reflex.models import (
    BacktestResult,
    Confidence,
    ControlId,
    ControlType,
    FailureCategory,
    FailurePattern,
    LessonId,
    ProposedControl,
    PublicationStatus,
    ReflexControl,
    ReflexCoverage,
    ReflexLesson,
    SimilarAssetCandidate,
)


class TestLessonId:
    def test_generate_produces_valid_id(self) -> None:
        lid = LessonId.generate()
        assert lid.startswith("reflex-lesson-")
        assert len(lid) > len("reflex-lesson-")


class TestControlId:
    def test_generate_produces_valid_id(self) -> None:
        cid = ControlId.generate()
        assert cid.startswith("reflex-control-")
        assert len(cid) > len("reflex-control-")


class TestReflexLesson:
    def test_unconfirmed_lesson_is_not_confirmed(self) -> None:
        lesson = ReflexLesson(
            lesson_id=LessonId.generate(),
            source_incident_urn="urn:li:dataset:(urn:li:dataPlatform:bigquery,finance.transactions,PROD)",
            title="Duplicate transactions from non-idempotent retries",
            human_confirmed_root_cause="Pipeline retry after partial failure inserted duplicate rows",
            failure_pattern=FailurePattern(
                category=FailureCategory.DATA_QUALITY,
                description="Non-idempotent retry logic",
            ),
            trigger="Resolved incident INC-001",
            candidate_preventive_control=ProposedControl(
                control_type=ControlType.UNIQUENESS,
                description="Ensure uniqueness on (transaction_id, timestamp)",
            ),
        )
        assert not lesson.is_confirmed

    def test_confirmed_lesson_is_confirmed(self) -> None:
        now = datetime.now(UTC)
        lesson = ReflexLesson(
            lesson_id=LessonId.generate(),
            source_incident_urn="urn:li:dataset:(urn:li:dataPlatform:bigquery,finance.transactions,PROD)",
            title="Duplicate transactions from non-idempotent retries",
            human_confirmed_root_cause="Pipeline retry after partial failure inserted duplicate rows",
            confirmed_or_edited_by="alice@example.com",
            approval_timestamp=now,
            failure_pattern=FailurePattern(
                category=FailureCategory.DATA_QUALITY,
                description="Non-idempotent retry logic",
            ),
            trigger="Resolved incident INC-001",
            candidate_preventive_control=ProposedControl(
                control_type=ControlType.UNIQUENESS,
                description="Ensure uniqueness on (transaction_id, timestamp)",
            ),
        )
        assert lesson.is_confirmed

    def test_missing_title_raises_validation_error(self) -> None:
        with pytest.raises(ValueError):
            ReflexLesson(
                lesson_id=LessonId.generate(),
                source_incident_urn="urn:li:dataset:(urn:li:dataPlatform:bigquery,foo,PROD)",
                title="",
                human_confirmed_root_cause="test",
                failure_pattern=FailurePattern(
                    category=FailureCategory.DATA_QUALITY,
                    description="test",
                ),
                trigger="test",
                candidate_preventive_control=ProposedControl(
                    control_type=ControlType.UNIQUENESS,
                    description="test",
                ),
            )


class TestBacktestResult:
    def test_defaults(self) -> None:
        now = datetime.now(UTC)
        result = BacktestResult(
            control_id=ControlId.generate(),
            target_asset_urn="urn:li:dataset:(urn:li:dataPlatform:bigquery,finance.transactions,PROD)",
            historical_window_start=now,
            historical_window_end=now,
            would_have_detected=False,
        )
        assert result.false_positives == 0
        assert result.true_positives == 0
        assert result.backtest_id.startswith("backtest-")


class TestReflexControl:
    def test_default_state_is_draft(self) -> None:
        control = ReflexControl(
            control_id=ControlId.generate(),
            lesson_id=LessonId.generate(),
            target_asset_urn="urn:li:dataset:(urn:li:dataPlatform:bigquery,test,PROD)",
            control_type=ControlType.UNIQUENESS,
            control_definition="SELECT transaction_id, COUNT(*) FROM t GROUP BY 1 HAVING COUNT(*) > 1",
        )
        assert control.publication_status == PublicationStatus.DRAFT
        assert control.approval_decision is None
        assert control.version == 1


class TestSimilarAssetCandidate:
    def test_minimal_candidate(self) -> None:
        candidate = SimilarAssetCandidate(
            asset_urn="urn:li:dataset:(urn:li:dataPlatform:bigquery,finance.ledger,PROD)",
            asset_type="dataset",
            similarity_rationale="Same domain (finance), same upstream pipeline",
        )
        assert candidate.confidence == Confidence.MEDIUM
        assert candidate.domain == ""


class TestReflexCoverage:
    def test_coverage_defaults(self) -> None:
        coverage = ReflexCoverage(
            control_id=ControlId.generate(),
            lesson_id=LessonId.generate(),
            asset_urn="urn:li:dataset:(urn:li:dataPlatform:bigquery,test,PROD)",
        )
        assert coverage.coverage_id.startswith("coverage-")
        assert coverage.propagation_path == []
