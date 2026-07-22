"""Shared test fixtures and configuration for DataHub Reflex test suite.

Environment variables:
    DATAHUB_GMS_URL    — DataHub GMS endpoint (default: http://localhost:8080)
    DATAHUB_GMS_TOKEN  — DataHub auth token (default: empty)
    REFLEX_TEST_PREFIX — Prefix for isolated test URNs (default: reflex-test)

Running tests:
    # All tests (skips live-DataHub tests if DataHub unavailable)
    python -m pytest tests/ -v

    # Live integration tests only (requires running DataHub)
    python -m pytest tests/integration/ -v

    # Skip live-DataHub tests
    python -m pytest tests/ -v -m "not requires_datahub"

    # Run verification script
    python scripts/verify_step3.py
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import httpx
import pytest

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

GMS_URL = os.environ.get("DATAHUB_GMS_URL", "http://localhost:8080")
GMS_TOKEN = os.environ.get("DATAHUB_GMS_TOKEN", "")
TEST_PREFIX = os.environ.get("REFLEX_TEST_PREFIX", "reflex-test")


def _datahub_available() -> bool:
    """Check if DataHub GMS is reachable."""
    try:
        resp = httpx.get(f"{GMS_URL}/health", timeout=5.0)
        return resp.status_code == 200
    except Exception:
        return False


def _datahub_available_or_skip() -> None:
    """Skip test if DataHub is not available (for use in fixtures)."""
    if not _datahub_available():
        pytest.skip("DataHub GMS not reachable — set DATAHUB_GMS_URL")


# ---------------------------------------------------------------------------
# Unique test identifiers
# ---------------------------------------------------------------------------


def make_test_urn(entity_type: str, suffix: str | None = None) -> str:
    """Generate a unique, isolated URN for testing.

    Uses REFLEX_TEST_PREFIX to avoid collision with real DataHub data.

    Example:
        make_test_urn("incident", "dup-001") → "urn:li:incident:reflex-test-dup-001-a1b2c3d4"
    """
    short_id = uuid.uuid4().hex[:8]
    if suffix:
        return f"urn:li:{entity_type}:{TEST_PREFIX}-{suffix}-{short_id}"
    return f"urn:li:{entity_type}:{TEST_PREFIX}-{short_id}"


def make_test_incident_urn(suffix: str = "inc") -> str:
    return make_test_urn("incident", suffix)


def make_test_dataset_urn(name: str) -> str:
    """Make a dataset URN referencing a known existing DataHub dataset.
    Does NOT create the dataset — uses existing ones from the running instance.
    """
    return f"urn:li:dataset:(urn:li:dataPlatform:bigquery,{name},PROD)"


# ---------------------------------------------------------------------------
# Temp directory fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def test_lessons_dir(tmp_path: Path) -> Path:
    """Isolated lessons directory for a test run."""
    lessons = tmp_path / "datasets"
    lessons.mkdir(parents=True)
    (lessons / "approvals").mkdir(parents=True)
    return lessons


@pytest.fixture
def test_approvals_dir(test_lessons_dir: Path) -> Path:
    """Convenience: approvals subdirectory."""
    return test_lessons_dir / "approvals"
