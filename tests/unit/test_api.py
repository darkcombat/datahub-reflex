"""Tests for the product API (P1 — Product API surface)."""

from __future__ import annotations

import json

import pytest

from ui.app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


class TestAPIHealth:
    def test_health_endpoint(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert "timestamp" in data


class TestAPIIncidentAnalysis:
    def test_analyze_incident_duplicate_rows(self, client):
        resp = client.post(
            "/api/v1/incidents/urn:li:incident:api-test-001/analyze",
            data=json.dumps({
                "scenario": "duplicate_rows",
                "incident_title": "Duplicate transactions in ledger",
                "incident_description": "Non-idempotent retry inserted duplicate rows.",
                "incident_custom_type": "DUPLICATE_ROWS",
                "human_confirmed_root_cause": "Non-idempotent retry logic.",
                "confirmed_by": "api-tester",
                "target_asset_urn": "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_daily_ledger,PROD)",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "run_id" in data
        assert data["current_step"] == 3
        assert data["incident"]["root_cause_approved"] is True
        assert data["lesson"]["failure_category"] == "data_quality"
        assert data["lesson"]["control_type"] == "uniqueness"

    def test_analyze_incident_missing_fields(self, client):
        resp = client.post(
            "/api/v1/incidents/test-001/analyze",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 500
        data = resp.get_json()
        assert "error" in data


class TestAPIApproval:
    def test_approve_root_cause(self, client):
        resp = client.post(
            "/api/v1/incidents/test-001/root-cause/approve",
            data=json.dumps({"decision": "approved", "approver": "tester"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["state"] == "approved"
        assert data["approval_type"] == "root_cause"

    def test_reject_root_cause(self, client):
        resp = client.post(
            "/api/v1/incidents/test-001/root-cause/approve",
            data=json.dumps({"decision": "rejected", "approver": "tester"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["state"] == "rejected"

    def test_approve_control(self, client):
        resp = client.post(
            "/api/v1/controls/ctrl-001/approve",
            data=json.dumps({"decision": "approved", "approver": "tester"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["state"] == "approved"

    def test_reject_control(self, client):
        resp = client.post(
            "/api/v1/controls/ctrl-001/approve",
            data=json.dumps({"decision": "rejected", "approver": "tester"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["state"] == "rejected"


class TestAPIBacktestAndPublish:
    def test_backtest_without_active_run(self, client):
        """Backtest endpoint is self-contained."""
        resp = client.post(
            "/api/v1/lessons/lesson-001/backtest",
            data=json.dumps({"target_field": "transaction_id"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "backtest" in data
        assert data["backtest"]["can_recommend"] is True

    def test_full_workflow(self, client):
        """Complete API workflow: analyze → backtest → approve → publish."""
        # Step 1: Analyze
        r1 = client.post(
            "/api/v1/incidents/urn:li:incident:full-flow-001/analyze",
            data=json.dumps({
                "scenario": "duplicate_rows",
                "incident_title": "Full flow test",
                "incident_description": "Testing the complete API workflow.",
                "incident_custom_type": "DUPLICATE_ROWS",
                "human_confirmed_root_cause": "Non-idempotent retry.",
                "confirmed_by": "tester",
                "target_asset_urn": "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_daily_ledger,PROD)",
            }),
            content_type="application/json",
        )
        assert r1.status_code == 200
        run_id = r1.get_json()["run_id"]
        lesson_id = r1.get_json()["lesson"]["lesson_id"]

        # Step 2: Backtest
        r2 = client.post(
            f"/api/v1/lessons/{lesson_id}/backtest",
            data=json.dumps({"target_field": "transaction_id"}),
            content_type="application/json",
        )
        assert r2.status_code == 200
        data2 = r2.get_json()
        assert data2["backtest"]["can_recommend"] is True
        assert len(data2["similar_assets"]) >= 1
        control_id = data2["control"]["control_id"]

        # Step 3: Approve control
        r3 = client.post(
            f"/api/v1/controls/{control_id}/approve",
            data=json.dumps({"decision": "approved", "approver": "tester"}),
            content_type="application/json",
        )
        assert r3.status_code == 200

        # Step 4: Publish
        r4 = client.post(
            f"/api/v1/controls/{control_id}/publish",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert r4.status_code == 200
        data4 = r4.get_json()
        assert data4["is_complete"] is True
        assert data4["detection"]["detected"] is True
        assert data4["publication"]["status"] == "reflex-owned"

    def test_publish_without_approval(self, client):
        """Publish endpoint is self-contained — returns publication + detection."""
        resp = client.post(
            "/api/v1/controls/ctrl-any/publish",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["publication"]["status"] == "reflex-owned"
        assert data["detection"]["detected"] is True


class TestAPIRuns:
    def test_list_runs(self, client):
        resp = client.get("/api/v1/runs")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "runs" in data

    def test_get_nonexistent_run(self, client):
        resp = client.get("/api/v1/runs/nonexistent-id")
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["error"] == "NOT_FOUND"


class TestAPIErrorModel:
    def test_error_response_structure(self, client):
        resp = client.get("/api/v1/lessons/nonexistent")
        assert resp.status_code == 404
        data = resp.get_json()
        assert "error" in data
        assert "correlation_id" in data
        assert "detail" in data
