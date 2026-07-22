"""Integration test fixtures requiring a running DataHub OSS instance.

Provides setup/teardown for isolated test runs:
- Creates incidents with REFLEX_TEST custom type
- Cleans up by resolving all REFLEX_TEST incidents on teardown
- Does NOT destroy unrelated DataHub data.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from reflex.datahub.read_client import DataHubReadClient
from reflex.datahub.write_client import DataHubWriteClient

from ..conftest import GMS_TOKEN, GMS_URL, _datahub_available_or_skip

# ---------------------------------------------------------------------------
# Client fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def read_client() -> DataHubReadClient:
    """Read client for live DataHub."""
    _datahub_available_or_skip()
    return DataHubReadClient(gms_url=GMS_URL, token=GMS_TOKEN)


@pytest.fixture
def write_client() -> DataHubWriteClient:
    """Write client for live DataHub."""
    _datahub_available_or_skip()
    return DataHubWriteClient(gms_url=GMS_URL, token=GMS_TOKEN)


# ---------------------------------------------------------------------------
# Historical data builders (Reflex-owned, synthetic)
# ---------------------------------------------------------------------------


def build_duplicate_rows_history(days: int = 8) -> list[tuple[datetime, list[dict]]]:
    """Build synthetic historical snapshots with duplicates on last 2 days.

    This is Reflex-owned historical data. DataHub does NOT store this.
    """
    now = datetime.now(UTC)
    base = [
        {"transaction_id": f"TXN-{i:03d}", "amount": 100.0 * i}
        for i in range(1, 11)
    ]
    dup_row = [
        {"transaction_id": "TXN-003", "amount": 300.0},
        {"transaction_id": "TXN-007", "amount": 700.0},
    ]
    data: list[tuple[datetime, list[dict]]] = []
    for d in range(days, 0, -1):
        snapshot = list(base)
        if d <= 2:
            snapshot.extend(dup_row)
        data.append((now - timedelta(days=d), snapshot))
    return data


def build_orphaned_ownership_history(days: int = 8) -> list[tuple[datetime, list[dict]]]:
    """Build synthetic historical snapshots with inactive owner on last day.

    This is Reflex-owned historical data. DataHub does NOT store this.
    """
    now = datetime.now(UTC)
    active_owners = [
        {"owner": "alice", "type": "TECHNICAL_OWNER", "active": True},
        {"owner": "charlie", "type": "TECHNICAL_OWNER", "active": True},
    ]
    inactive_owners = [
        {"owner": "bob", "type": "TECHNICAL_OWNER", "active": False},
        {"owner": "alice", "type": "TECHNICAL_OWNER", "active": True},
    ]
    data: list[tuple[datetime, list[dict]]] = []
    for d in range(days, 0, -1):
        owners = inactive_owners if d == 1 else active_owners
        data.append((now - timedelta(days=d), owners))
    return data


# ---------------------------------------------------------------------------
# Approval file helpers
# ---------------------------------------------------------------------------


def write_root_cause_approval(
    approvals_dir: Path,
    incident_urn: str,
    approver: str = "test-reviewer",
) -> Path:
    """Write a root cause approval file to bypass the human gate."""
    from reflex.core.approval import _sanitize
    content = {
        "incident_urn": incident_urn,
        "proposed_root_cause": "Automated test root cause",
        "final_root_cause": "Automated test root cause",
        "state": "approved",
        "approver": approver,
        "timestamp": datetime.now(UTC).isoformat(),
        "provenance": "test-automation",
    }
    path = approvals_dir / f"root_cause_{_sanitize(incident_urn)}.json"
    import json
    path.write_text(json.dumps(content, indent=2))
    return path


def write_control_approval(
    approvals_dir: Path,
    control_id: str,
    approver: str = "test-reviewer",
    decision: str = "approved",
) -> Path:
    """Write a control approval decision file to bypass the human gate."""
    content = {
        "decision": decision,
        "approver": approver,
        "revision_notes": "Automated test approval",
    }
    from reflex.core.pipeline import _sanitize_urn
    path = approvals_dir / f"decision_{_sanitize_urn(control_id)}.json"
    import json
    path.write_text(json.dumps(content, indent=2))
    return path
