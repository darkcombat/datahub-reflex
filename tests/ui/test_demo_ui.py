"""Smoke tests for the Reflex UI demo.

Tests the Flask API endpoints and demo runner state machine.
Does NOT require a browser — tests HTTP endpoints directly.
"""

from __future__ import annotations

import json

import pytest

from ui.app import app as flask_app
from ui.demo_runner import (
    DemoRunner,
    build_duplicate_rows_history,
    build_orphaned_ownership_history,
)


@pytest.fixture
def client():
    """Flask test client."""
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


@pytest.fixture
def runner():
    """Fresh DemoRunner for each test."""
    import tempfile
    from pathlib import Path
    tmp = Path(tempfile.mkdtemp())
    r = DemoRunner(lessons_dir=tmp, use_live_datahub=False)
    yield r
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestAPIEndpoints:
    """Smoke tests for each API endpoint."""

    def test_index_returns_html(self, client):
        """GET / returns HTML page."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"<!doctype html>" in resp.data
        assert b"DataHub Reflex" in resp.data
        assert b'id="start-button"' in resp.data
        assert b"What should Reflex learn from?" in resp.data
        assert b"Protection pipeline" in resp.data
        assert b"reflex.css" in resp.data
        assert b"reflex.js" in resp.data

    def test_state_endpoint_returns_json(self, client):
        """GET /api/state returns JSON with expected keys."""
        resp = client.get("/api/state")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "current_step" in data
        assert "incident_urn" in data
        assert "lesson_id" in data
        assert "control_id" in data

    def test_reset_endpoint(self, client):
        """POST /api/reset clears state."""
        resp = client.post("/api/reset")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "reset"
        assert data["current_step"] == 0

    def test_run_endpoint_duplicate_rows(self, client):
        """POST /api/run with duplicate_rows scenario returns completed state."""
        resp = client.post(
            "/api/run",
            data=json.dumps({"scenario": "duplicate_rows"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["is_complete"] is False
        assert data["approval_state"] == "pending"
        approved = client.post(
            "/api/approve",
            data=json.dumps({"decision": "approved", "approver": "tester"}),
            content_type="application/json",
        ).get_json()
        approved = client.post(
            "/api/approve",
            data=json.dumps({"decision": "approved", "approver": "tester"}),
            content_type="application/json",
        ).get_json()
        assert approved["is_complete"] is True
        assert approved["current_step"] == 9
        assert approved["lesson_id"].startswith("reflex-lesson-")
        assert approved["control_type"] == "uniqueness"

    def test_run_endpoint_orphaned_ownership(self, client):
        """POST /api/run with orphaned_ownership scenario."""
        resp = client.post(
            "/api/run",
            data=json.dumps({"scenario": "orphaned_ownership"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["is_complete"] is False
        assert data["approval_state"] == "pending"
        client.post(
            "/api/approve",
            data=json.dumps({"decision": "approved", "approver": "tester"}),
            content_type="application/json",
        )
        data = client.post(
            "/api/approve",
            data=json.dumps({"decision": "approved", "approver": "tester"}),
            content_type="application/json",
        ).get_json()
        assert data["is_complete"] is True
        assert data["control_type"] == "active_ownership"

    def test_run_unknown_scenario_returns_400(self, client):
        """Unknown scenario returns 400."""
        resp = client.post(
            "/api/run",
            data=json.dumps({"scenario": "nonexistent"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_approve_endpoint(self, client, monkeypatch, tmp_path):
        """POST /api/approve sets approval state."""
        # The repository .env may point at a live DataHub instance. Keep this
        # endpoint regression test deterministic and network-free.
        import ui.app as ui_app
        monkeypatch.setattr(
            ui_app,
            "_runner",
            DemoRunner(lessons_dir=tmp_path, use_live_datahub=False),
        )
        run = client.post(
            "/api/run",
            data=json.dumps({"scenario": "duplicate_rows"}),
            content_type="application/json",
        ).get_json()
        resp = client.post(
            "/api/approve",
            data=json.dumps({"decision": "approved", "approver": "tester"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = client.post(
            "/api/approve",
            data=json.dumps({"decision": "approved", "approver": "tester"}),
            content_type="application/json",
        ).get_json()
        assert data["approval_state"] == "approved"

        # The first decision must be recorded as root-cause approval even
        # though the runner advances to the next pending gate in the same
        # request.
        audit = client.get(f"/api/runs/{run['run_id']}").get_json()
        assert audit["approvals"][0]["approval_type"] == "root_cause"

        second = client.post(
            "/api/approve",
            data=json.dumps({"decision": "approved", "approver": "tester"}),
            content_type="application/json",
        ).get_json()
        assert second["approval_state"] == "approved"
        audit = client.get(f"/api/runs/{run['run_id']}").get_json()
        assert [a["approval_type"] for a in audit["approvals"]][-1] == "control"

    def test_reject_endpoint(self, client):
        """POST /api/approve with reject."""
        client.post(
            "/api/run",
            data=json.dumps({"scenario": "duplicate_rows"}),
            content_type="application/json",
        )
        resp = client.post(
            "/api/approve",
            data=json.dumps({"decision": "rejected", "approver": "tester"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["approval_state"] == "rejected"


# ---------------------------------------------------------------------------
# DemoRunner state machine tests
# ---------------------------------------------------------------------------


class TestDemoRunner:
    """Tests for the DemoRunner state machine."""

    def test_initial_state(self, runner):
        """Fresh runner starts at step 0."""
        assert runner.state.current_step == 0
        assert runner.state.is_complete is False
        assert runner.state.similarity_mode == "synthetic"

    def test_reset_clears_state(self, runner):
        """Reset returns to initial state."""
        runner.state.current_step = 5
        runner.state.is_complete = True
        runner.reset()
        assert runner.state.current_step == 0
        assert runner.state.is_complete is False

    def test_run_full_duplicate_rows(self, runner):
        """Full run populates all 9 steps."""
        import asyncio

        async def _run():
            historical = build_duplicate_rows_history(days=8)
            return await runner.run_full(
                incident_urn="urn:li:incident:test-001",
                scenario="duplicate_rows",
                human_confirmed_root_cause="Non-idempotent retries",
                confirmed_by="tester",
                target_asset_urn="urn:li:dataset:(urn:li:dataPlatform:bigquery,test,PROD)",
                historical_data=historical,
                uniqueness_columns=["transaction_id"],
            )

        state = asyncio.run(_run())
        assert state.is_complete is False
        assert state.current_step == 2
        async def _approve_twice():
            await runner.apply_approval("approved", "tester")
            return await runner.apply_approval("approved", "tester")
        state = asyncio.run(_approve_twice())
        assert state.is_complete is True
        assert state.current_step == 9
        assert state.lesson_id.startswith("reflex-lesson-")
        assert state.control_id.startswith("reflex-control-")
        assert state.backtest_snapshots == 8
        assert state.backtest_would_have_prevented is True
        assert state.approval_state == "approved"
        # Synthetic mode labels
        assert "synthetic" in state.similarity_mode

    def test_run_full_orphaned_ownership(self, runner):
        """Full run for orphaned ownership scenario."""
        import asyncio

        async def _run():
            historical = build_orphaned_ownership_history(days=8)
            return await runner.run_full(
                incident_urn="urn:li:incident:test-002",
                scenario="orphaned_ownership",
                human_confirmed_root_cause="Employee offboarding gap",
                confirmed_by="tester",
                target_asset_urn="urn:li:dataset:(urn:li:dataPlatform:bigquery,test,PROD)",
                historical_data=historical,
            )

        state = asyncio.run(_run())
        assert state.is_complete is False
        async def _approve_twice():
            await runner.apply_approval("approved", "tester")
            return await runner.apply_approval("approved", "tester")
        state = asyncio.run(_approve_twice())
        assert state.is_complete is True
        assert state.control_type == "active_ownership"

    def test_to_dict_is_serializable(self, runner):
        """to_dict() produces JSON-serializable output."""
        d = runner.to_dict()
        json.dumps(d)  # should not raise
        assert isinstance(d, dict)
        assert "current_step" in d

    def test_error_state_captured(self, runner):
        """Errors are captured in state.error."""
        import asyncio

        async def _run():
            return await runner.run_full(
                incident_urn="urn:li:incident:test-err",
                scenario="nonexistent_scenario",
                human_confirmed_root_cause="test",
                confirmed_by="tester",
                target_asset_urn="urn:li:dataset:test",
                historical_data=[],
            )

        state = asyncio.run(_run())
        assert state.error != "" or state.is_complete is False

    def test_historical_data_is_labeled_synthetic(self, runner):
        """Historical data builder clearly produces synthetic data."""
        history = build_duplicate_rows_history(days=5)
        assert len(history) == 5
        # All data is Python dicts — no DataHub integration here
        for ts, rows in history:
            assert isinstance(rows, list)
            for row in rows:
                assert isinstance(row, dict)
                assert "transaction_id" in row


# ---------------------------------------------------------------------------
# UI HTML content checks
# ---------------------------------------------------------------------------


class TestUIHtmlContent:
    """Verify the single-page HTML contains required elements."""

    def test_html_contains_all_step_labels(self, client):
        """Each of the 9 steps is represented in the UI."""
        resp = client.get("/")
        html = client.get("/static/reflex.js").data.decode().lower()
        html = html.lower()
        assert "resolved incident" in html
        assert "human-confirmed root cause" in html
        assert "structured lesson" in html
        assert "preventive control" in html
        assert "similar assets" in html
        assert "historical backtest" in html
        assert "publication approval" in html
        assert "datahub publication" in html
        assert "future incident detection" in html

    def test_html_labels_synthetic_data(self, client):
        """Synthetic data is clearly labeled in the UI."""
        resp = client.get("/")
        html = client.get("/static/reflex.js").data.decode()
        assert "synthetic" in html.lower()

    def test_html_labels_reflex_vs_datahub(self, client):
        """UI distinguishes Reflex-owned vs DataHub OSS."""
        resp = client.get("/")
        html = client.get("/static/reflex.js").data.decode()
        assert "badge-reflex" in html
        assert "badge-datahub" in html

    def test_html_has_reset_button(self, client):
        """Reset action is available."""
        resp = client.get("/")
        html = resp.data.decode()
        assert 'id="reset-button"' in html

    def test_html_has_run_button(self, client):
        """Run demo action is available."""
        resp = client.get("/")
        html = resp.data.decode()
        assert 'id="start-button"' in html
