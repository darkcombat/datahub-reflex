"""Reflex backtesting engine.

The backtester runs ReflexControls against historical data snapshots.
This is NOT delegated to DataHub — DataHub OSS cannot execute assertions.
Reflex owns the execution layer entirely.

Historical data is expected to be provided as time-ordered snapshots:
- For data controls (UniquenessControl): list of (timestamp, [rows]) tuples
- For metadata controls (ActiveOwnershipControl): list of (timestamp, [asset_records]) tuples
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from reflex.controls.executors import get_executor
from reflex.models import BacktestResult, ReflexControl

logger = structlog.get_logger(__name__)


class BacktestSummary:
    """Aggregated summary of backtest results for a single control."""

    def __init__(self, results: list[BacktestResult]) -> None:
        self.results = results
        self.total_snapshots = len(results)
        self.detections = sum(1 for r in results if r.would_have_detected)
        self.total_true_positives = sum(r.true_positives for r in results)
        self.total_false_positives = sum(r.false_positives for r in results)

    @property
    def detection_rate(self) -> float:
        if self.total_snapshots == 0:
            return 0.0
        return self.detections / self.total_snapshots

    @property
    def precision(self) -> float:
        total = self.total_true_positives + self.total_false_positives
        if total == 0:
            return 1.0
        return self.total_true_positives / total

    @property
    def would_have_prevented(self) -> bool:
        """True if the control would have detected the issue in historical data."""
        return self.detections > 0


class ReflexBacktester:
    """Runs ReflexControls against historical data and produces BacktestResults.

    The backtester is stateless. All state comes from the control and the
    provided historical data.
    """

    async def backtest(
        self,
        control: ReflexControl,
        historical_data: list[Any],
    ) -> list[BacktestResult]:
        """Run a control against historical data snapshots.

        Args:
            control: The ReflexControl to backtest.
            historical_data: A list of (timestamp, data) tuples where data
                            is appropriately typed for the control type.

        Returns:
            A list of BacktestResult, one per historical snapshot.
        """
        logger.info(
            "backtesting.start",
            control_id=control.control_id,
            control_type=control.control_type.value,
            snapshots=len(historical_data),
        )

        if not historical_data:
            logger.warning("backtesting.no_data", control_id=control.control_id)
            return []

        executor = get_executor(control.control_type)
        results = await executor.backtest(control, historical_data)

        summary = BacktestSummary(results)
        logger.info(
            "backtesting.complete",
            control_id=control.control_id,
            snapshots=summary.total_snapshots,
            detections=summary.detections,
            detection_rate=summary.detection_rate,
            would_have_prevented=summary.would_have_prevented,
        )

        return results

    async def execute(
        self,
        control: ReflexControl,
        current_data: Any,
    ) -> BacktestResult:
        """Execute a control against current (live) data.

        This is used for detecting NEW incidents, not for backtesting.
        """
        logger.info(
            "execution.start",
            control_id=control.control_id,
            control_type=control.control_type.value,
        )

        executor = get_executor(control.control_type)
        # The executor's execute method returns ControlExecutionResult,
        # but for consistency with the backtester we wrap it.
        exec_result = await executor.execute(control, current_data)

        # Convert to BacktestResult for uniformity
        now = datetime.now(UTC)
        return BacktestResult(
            control_id=control.control_id,
            target_asset_urn=control.target_asset_urn,
            historical_window_start=now,
            historical_window_end=now,
            would_have_detected=not exec_result.passed,
            detection_timestamp=now if not exec_result.passed else None,
            true_positives=exec_result.violation_count,
            false_positives=0,
            evidence=exec_result.details,
        )


def summarize_backtest(results: list[BacktestResult]) -> BacktestSummary:
    """Create a summary from backtest results."""
    return BacktestSummary(results)
