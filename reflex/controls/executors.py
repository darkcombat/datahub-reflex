"""Control implementations for the MVP scenarios.

Each control type has a deterministic, executable definition and a corresponding
executor that Reflex's backtesting engine can run against historical data.

Only two controls exist for the MVP:
- UniquenessControl: detects duplicate rows
- ActiveOwnershipControl: detects assets owned by inactive identities
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from reflex.models import (
    BacktestResult,
    ControlExecutionResult,
    ControlType,
    ReflexControl,
)


class BaseControlExecutor(ABC):
    """Abstract base for control executors.

    Each executor is responsible for running ONE type of control
    against a data source or metadata store. Executors are stateless —
    all state comes from the ReflexControl and the data source.
    """

    @abstractmethod
    async def execute(
        self,
        control: ReflexControl,
        data_source: Any,
    ) -> ControlExecutionResult:
        """Execute the control against live/latest data."""
        ...

    @abstractmethod
    async def backtest(
        self,
        control: ReflexControl,
        historical_data: list[Any],
    ) -> list[BacktestResult]:
        """Run the control against a set of historical snapshots."""
        ...


# -- Uniqueness Control --------------------------------------------------------


UNIQUENESS_CONTROL_DESCRIPTION = """
Detect duplicate rows caused by non-idempotent retries or ingestion failures.
Given a set of uniqueness columns, this control identifies rows that appear
more than once across those columns.
""".strip()


def build_uniqueness_control_definition(columns: list[str]) -> str:
    """Build a deterministic SQL-like uniqueness check.

    The definition is a parameterized template that the executor resolves
    against the actual dataset.
    """
    cols = ", ".join(columns)
    return (
        f"SELECT {cols}, COUNT(*) AS duplicate_count "
        f"FROM {{dataset}} "
        f"GROUP BY {cols} "
        f"HAVING COUNT(*) > 1"
    )


class UniquenessControlExecutor(BaseControlExecutor):
    """Executes uniqueness controls against row-oriented data.

    This executor works with in-memory data (list of dicts) for backtesting
    and can be adapted to live data sources via the data_source parameter.
    """

    async def execute(
        self,
        control: ReflexControl,
        data_source: Any,
    ) -> ControlExecutionResult:
        """Execute the uniqueness control against a data source."""
        # data_source is expected to be a list of dicts (rows)
        rows = list(data_source) if data_source else []
        columns = self._extract_columns(control.control_definition)
        duplicates = self._find_duplicates(rows, columns)

        passed = len(duplicates) == 0
        return ControlExecutionResult(
            control_id=control.control_id,
            asset_urn=control.target_asset_urn,
            passed=passed,
            violation_count=len(duplicates),
            sample_violations=[str(d) for d in duplicates[:10]],
            details=f"Checked {len(rows)} rows across columns {columns}. "
            f"Found {len(duplicates)} duplicate groups."
            if not passed
            else f"Checked {len(rows)} rows across columns {columns}. No duplicates found.",
        )

    async def backtest(
        self,
        control: ReflexControl,
        historical_data: list[Any],
    ) -> list[BacktestResult]:
        """Run the uniqueness control against historical snapshots.

        Each element in historical_data is a (timestamp, rows) tuple representing
        a snapshot of the dataset at that point in time.
        """
        columns = self._extract_columns(control.control_definition)
        results: list[BacktestResult] = []

        for snapshot in historical_data:
            timestamp, rows = snapshot
            duplicates = self._find_duplicates(list(rows), columns)

            result = BacktestResult(
                control_id=control.control_id,
                target_asset_urn=control.target_asset_urn,
                historical_window_start=timestamp,
                historical_window_end=timestamp,
                would_have_detected=len(duplicates) > 0,
                detection_timestamp=timestamp if duplicates else None,
                true_positives=len(duplicates),
                false_positives=0,
                evidence=f"Found {len(duplicates)} duplicate groups at {timestamp.isoformat()}"
                if duplicates
                else f"No duplicates detected at {timestamp.isoformat()}",
            )
            results.append(result)

        return results

    def _extract_columns(self, control_definition: str) -> list[str]:
        """Extract uniqueness columns from the control definition.

        The definition format is: GROUP BY col1, col2, ...
        """
        # Parse the GROUP BY clause from the definition
        group_by_marker = "GROUP BY "
        having_marker = "HAVING "
        start = control_definition.index(group_by_marker) + len(group_by_marker)
        end = control_definition.index(having_marker, start)
        cols_str = control_definition[start:end].strip()
        return [c.strip() for c in cols_str.split(",")]

    def _find_duplicates(
        self, rows: list[dict], columns: list[str]
    ) -> list[dict[str, Any]]:
        """Find duplicate groups in row data."""
        groups: dict[tuple, list[dict]] = {}
        for row in rows:
            key = tuple(row.get(c) for c in columns)
            groups.setdefault(key, []).append(row)

        return [
            {"key": dict(zip(columns, key)), "count": len(group)}
            for key, group in groups.items()
            if len(group) > 1
        ]


# -- Active Ownership Control --------------------------------------------------


ACTIVE_OWNERSHIP_CONTROL_DESCRIPTION = """
Detect assets whose owners are inactive (deactivated) identities.
For each asset, check all owners against the known active user set.
Flag assets where ALL owners are inactive or where the TECHNICAL_OWNER is inactive.
""".strip()


def build_active_ownership_control_definition(
    min_active_owners: int = 1,
    required_owner_types: list[str] | None = None,
) -> str:
    """Build a deterministic ownership-validity check definition."""
    if required_owner_types is None:
        required_owner_types = ["TECHNICAL_OWNER"]
    types_str = ", ".join(required_owner_types)
    return (
        f"CHECK ownership validity: "
        f"at_least_{min_active_owners}_active_owner_per_asset "
        f"required_types=[{types_str}]"
    )


class ActiveOwnershipControlExecutor(BaseControlExecutor):
    """Executes ownership-validity controls against asset metadata.

    This executor checks whether assets have active owners.
    It does NOT modify ownership — that requires human approval.
    """

    async def execute(
        self,
        control: ReflexControl,
        data_source: Any,
    ) -> ControlExecutionResult:
        """Execute the ownership control against asset metadata.

        data_source is expected to be a list of asset ownership records:
        [
            {
                "asset_urn": "...",
                "owners": [
                    {"urn": "...", "username": "...", "type": "TECHNICAL_OWNER", "active": True/False},
                ],
                "domain": "...",
            }
        ]
        """
        assets = list(data_source) if data_source else []
        (min_active, required_types) = self._parse_definition(control.control_definition)

        violations = []
        for asset in assets:
            owners = asset.get("owners", [])
            active_required = [
                o
                for o in owners
                if o.get("type") in required_types and o.get("active", True)
            ]
            if len(active_required) < min_active:
                violations.append(
                    {
                        "asset_urn": asset.get("asset_urn", "unknown"),
                        "inactive_owners": [
                            o.get("username", o.get("urn", ""))
                            for o in owners
                            if o.get("type") in required_types and not o.get("active", True)
                        ],
                        "domain": asset.get("domain", ""),
                    }
                )

        passed = len(violations) == 0
        return ControlExecutionResult(
            control_id=control.control_id,
            asset_urn=control.target_asset_urn,
            passed=passed,
            violation_count=len(violations),
            sample_violations=[str(v) for v in violations[:10]],
            details=f"Checked {len(assets)} assets. "
            f"Found {len(violations)} with inactive required owners."
            if not passed
            else f"Checked {len(assets)} assets. All have active required owners.",
        )

    async def backtest(
        self,
        control: ReflexControl,
        historical_data: list[Any],
    ) -> list[BacktestResult]:
        """Run the ownership control against historical ownership snapshots.

        Each element in historical_data is a (timestamp, assets) tuple.
        """
        (min_active, required_types) = self._parse_definition(control.control_definition)
        results: list[BacktestResult] = []

        for snapshot in historical_data:
            timestamp, assets = snapshot
            assets_list = list(assets)

            violations = []
            for asset in assets_list:
                owners = asset.get("owners", [])
                active_required = [
                    o
                    for o in owners
                    if o.get("type") in required_types and o.get("active", True)
                ]
                if len(active_required) < min_active:
                    violations.append(asset.get("asset_urn", "unknown"))

            result = BacktestResult(
                control_id=control.control_id,
                target_asset_urn=control.target_asset_urn,
                historical_window_start=timestamp,
                historical_window_end=timestamp,
                would_have_detected=len(violations) > 0,
                detection_timestamp=timestamp if violations else None,
                true_positives=len(violations),
                false_positives=0,
                evidence=f"Found {len(violations)} assets with inactive owners at {timestamp.isoformat()}"
                if violations
                else f"All assets have active owners at {timestamp.isoformat()}",
            )
            results.append(result)

        return results

    def _parse_definition(self, control_definition: str) -> tuple[int, list[str]]:
        """Parse min_active_owners and required_types from the definition."""
        import re

        min_match = re.search(r"at_least_(\d+)_active_owner", control_definition)
        min_active = int(min_match.group(1)) if min_match else 1

        types_match = re.search(r"required_types=\[([^\]]*)\]", control_definition)
        if types_match:
            required_types = [t.strip() for t in types_match.group(1).split(",")]
        else:
            required_types = ["TECHNICAL_OWNER"]

        return min_active, required_types


# -- Executor Registry ---------------------------------------------------------


EXECUTOR_REGISTRY: dict[ControlType, type[BaseControlExecutor]] = {
    ControlType.UNIQUENESS: UniquenessControlExecutor,
    ControlType.ACTIVE_OWNERSHIP: ActiveOwnershipControlExecutor,
}


def get_executor(control_type: ControlType) -> BaseControlExecutor:
    """Get the executor for a given control type."""
    executor_cls = EXECUTOR_REGISTRY.get(control_type)
    if executor_cls is None:
        raise ValueError(f"No executor registered for control type: {control_type}")
    return executor_cls()
