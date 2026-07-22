"""Tests for control executors and the backtesting engine."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from reflex.backtesting.engine import ReflexBacktester, summarize_backtest
from reflex.controls.executors import (
    ActiveOwnershipControlExecutor,
    UniquenessControlExecutor,
    build_active_ownership_control_definition,
    build_uniqueness_control_definition,
    get_executor,
)
from reflex.models import (
    BacktestResult,
    ControlId,
    ControlType,
    LessonId,
    ReflexControl,
)

# -- Uniqueness Control Tests -------------------------------------------------


class TestUniquenessControl:
    def test_build_definition(self) -> None:
        definition = build_uniqueness_control_definition(["transaction_id", "timestamp"])
        assert "GROUP BY transaction_id, timestamp" in definition
        assert "HAVING COUNT(*) > 1" in definition

    def test_execute_no_duplicates(self) -> None:
        executor = UniquenessControlExecutor()
        control = ReflexControl(
            control_id=ControlId.generate(),
            lesson_id=LessonId.generate(),
            target_asset_urn="urn:li:dataset:test",
            control_type=ControlType.UNIQUENESS,
            control_definition=build_uniqueness_control_definition(["id"]),
        )

        data = [
            {"id": 1, "value": "a"},
            {"id": 2, "value": "b"},
            {"id": 3, "value": "c"},
        ]

        import asyncio
        result = asyncio.run(executor.execute(control, data))
        assert result.passed
        assert result.violation_count == 0

    def test_execute_with_duplicates(self) -> None:
        executor = UniquenessControlExecutor()
        control = ReflexControl(
            control_id=ControlId.generate(),
            lesson_id=LessonId.generate(),
            target_asset_urn="urn:li:dataset:test",
            control_type=ControlType.UNIQUENESS,
            control_definition=build_uniqueness_control_definition(["id"]),
        )

        data = [
            {"id": 1, "value": "a"},
            {"id": 1, "value": "a"},  # duplicate
            {"id": 2, "value": "b"},
            {"id": 2, "value": "c"},  # duplicate
            {"id": 3, "value": "d"},
        ]

        import asyncio
        result = asyncio.run(executor.execute(control, data))
        assert not result.passed
        assert result.violation_count == 2  # two duplicate groups

    def test_backtest_detects_historical_duplicates(self) -> None:
        executor = UniquenessControlExecutor()
        control = ReflexControl(
            control_id=ControlId.generate(),
            lesson_id=LessonId.generate(),
            target_asset_urn="urn:li:dataset:test",
            control_type=ControlType.UNIQUENESS,
            control_definition=build_uniqueness_control_definition(["id"]),
        )

        now = datetime.now(UTC)
        historical = [
            (now, [{"id": 1, "v": "a"}, {"id": 2, "v": "b"}]),
            (now, [{"id": 1, "v": "a"}, {"id": 1, "v": "a"}]),
        ]

        import asyncio
        results = asyncio.run(executor.backtest(control, historical))
        assert len(results) == 2
        assert not results[0].would_have_detected
        assert results[1].would_have_detected
        assert results[1].true_positives == 1

    def test_extract_columns(self) -> None:
        executor = UniquenessControlExecutor()
        definition = build_uniqueness_control_definition(["col_a", "col_b"])
        columns = executor._extract_columns(definition)
        assert columns == ["col_a", "col_b"]


# -- Active Ownership Control Tests ------------------------------------------


class TestActiveOwnershipControl:
    def test_build_definition(self) -> None:
        definition = build_active_ownership_control_definition(
            min_active_owners=1,
            required_owner_types=["TECHNICAL_OWNER"],
        )
        assert "at_least_1_active_owner" in definition
        assert "required_types=[TECHNICAL_OWNER]" in definition

    def test_execute_all_active(self) -> None:
        executor = ActiveOwnershipControlExecutor()
        control = ReflexControl(
            control_id=ControlId.generate(),
            lesson_id=LessonId.generate(),
            target_asset_urn="urn:li:dataset:test",
            control_type=ControlType.ACTIVE_OWNERSHIP,
            control_definition=build_active_ownership_control_definition(),
        )

        data = [
            {
                "asset_urn": "urn:li:dataset:finance.transactions",
                "owners": [
                    {"urn": "urn:li:corpuser:alice", "username": "alice", "type": "TECHNICAL_OWNER", "active": True},
                ],
                "domain": "finance",
            }
        ]

        import asyncio
        result = asyncio.run(executor.execute(control, data))
        assert result.passed
        assert result.violation_count == 0

    def test_execute_inactive_owner(self) -> None:
        executor = ActiveOwnershipControlExecutor()
        control = ReflexControl(
            control_id=ControlId.generate(),
            lesson_id=LessonId.generate(),
            target_asset_urn="urn:li:dataset:test",
            control_type=ControlType.ACTIVE_OWNERSHIP,
            control_definition=build_active_ownership_control_definition(),
        )

        data = [
            {
                "asset_urn": "urn:li:dataset:finance.transactions",
                "owners": [
                    {"urn": "urn:li:corpuser:bob", "username": "bob", "type": "TECHNICAL_OWNER", "active": False},
                ],
                "domain": "finance",
            }
        ]

        import asyncio
        result = asyncio.run(executor.execute(control, data))
        assert not result.passed
        assert result.violation_count == 1

    def test_execute_multiple_owners_one_active(self) -> None:
        executor = ActiveOwnershipControlExecutor()
        control = ReflexControl(
            control_id=ControlId.generate(),
            lesson_id=LessonId.generate(),
            target_asset_urn="urn:li:dataset:test",
            control_type=ControlType.ACTIVE_OWNERSHIP,
            control_definition=build_active_ownership_control_definition(),
        )

        data = [
            {
                "asset_urn": "urn:li:dataset:finance.ledger",
                "owners": [
                    {"urn": "urn:li:corpuser:bob", "username": "bob", "type": "TECHNICAL_OWNER", "active": False},
                    {"urn": "urn:li:corpuser:alice", "username": "alice", "type": "TECHNICAL_OWNER", "active": True},
                ],
                "domain": "finance",
            }
        ]

        import asyncio
        result = asyncio.run(executor.execute(control, data))
        assert result.passed

    def test_backtest_detects_historical_orphaned_ownership(self) -> None:
        executor = ActiveOwnershipControlExecutor()
        control = ReflexControl(
            control_id=ControlId.generate(),
            lesson_id=LessonId.generate(),
            target_asset_urn="urn:li:dataset:test",
            control_type=ControlType.ACTIVE_OWNERSHIP,
            control_definition=build_active_ownership_control_definition(),
        )

        now = datetime.now(UTC)
        # Snapshot 1: all owners active
        # Snapshot 2: owner deactivated
        historical = [
            (
                now,
                [
                    {
                        "asset_urn": "urn:li:dataset:finance.transactions",
                        "owners": [
                            {"urn": "urn:li:corpuser:bob", "username": "bob", "type": "TECHNICAL_OWNER", "active": True},
                        ],
                        "domain": "finance",
                    }
                ],
            ),
            (
                now,
                [
                    {
                        "asset_urn": "urn:li:dataset:finance.transactions",
                        "owners": [
                            {"urn": "urn:li:corpuser:bob", "username": "bob", "type": "TECHNICAL_OWNER", "active": False},
                        ],
                        "domain": "finance",
                    }
                ],
            ),
        ]

        import asyncio
        results = asyncio.run(executor.backtest(control, historical))
        assert len(results) == 2
        assert not results[0].would_have_detected
        assert results[1].would_have_detected

    def test_parse_definition(self) -> None:
        executor = ActiveOwnershipControlExecutor()
        definition = build_active_ownership_control_definition(
            min_active_owners=2,
            required_owner_types=["TECHNICAL_OWNER", "BUSINESS_OWNER"],
        )
        min_active, required_types = executor._parse_definition(definition)
        assert min_active == 2
        assert required_types == ["TECHNICAL_OWNER", "BUSINESS_OWNER"]


# -- Executor Registry Tests --------------------------------------------------


class TestExecutorRegistry:
    def test_get_uniqueness_executor(self) -> None:
        executor = get_executor(ControlType.UNIQUENESS)
        assert isinstance(executor, UniquenessControlExecutor)

    def test_get_ownership_executor(self) -> None:
        executor = get_executor(ControlType.ACTIVE_OWNERSHIP)
        assert isinstance(executor, ActiveOwnershipControlExecutor)

    def test_unknown_type_raises(self) -> None:
        with pytest.raises(ValueError):
            get_executor("nonexistent")  # type: ignore[arg-type]


# -- Backtesting Engine Tests ------------------------------------------------


class TestBacktestingEngine:
    def test_backtest_empty_data(self) -> None:
        engine = ReflexBacktester()
        control = ReflexControl(
            control_id=ControlId.generate(),
            lesson_id=LessonId.generate(),
            target_asset_urn="urn:li:dataset:test",
            control_type=ControlType.UNIQUENESS,
            control_definition=build_uniqueness_control_definition(["id"]),
        )

        import asyncio
        results = asyncio.run(engine.backtest(control, []))
        assert results == []

    def test_summarize_backtest(self) -> None:
        now = datetime.now(UTC)
        results = [
            BacktestResult(
                control_id=ControlId.generate(),
                target_asset_urn="urn:li:dataset:test",
                historical_window_start=now,
                historical_window_end=now,
                would_have_detected=False,
            ),
            BacktestResult(
                control_id=ControlId.generate(),
                target_asset_urn="urn:li:dataset:test",
                historical_window_start=now,
                historical_window_end=now,
                would_have_detected=True,
                true_positives=3,
            ),
            BacktestResult(
                control_id=ControlId.generate(),
                target_asset_urn="urn:li:dataset:test",
                historical_window_start=now,
                historical_window_end=now,
                would_have_detected=True,
                true_positives=1,
                false_positives=1,
            ),
        ]
        summary = summarize_backtest(results)
        assert summary.total_snapshots == 3
        assert summary.detections == 2
        assert summary.total_true_positives == 4
        assert summary.total_false_positives == 1
        assert summary.detection_rate == 2 / 3
        assert summary.precision == 4 / 5
        assert summary.would_have_prevented
