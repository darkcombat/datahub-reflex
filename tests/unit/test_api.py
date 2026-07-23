"""Tests for the product API (P1 — Product API surface)."""

from __future__ import annotations

import json

import pytest

from ui.app import app as flask_app
from reflex.api import routes as api_routes


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    api_routes._runs.clear()
    api_routes._current_run_id = None
    with flask_app.test_client() as c:
        yield c
    api_routes._runs.clear()
    api_routes._current_run_id = None


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
        assert data["current_step"] == 1
        assert data["incident"]["root_cause_approved"] is False
        assert data["lesson"] is None

    def test_analyze_incident_missing_fields(self, client):
        resp = client.post(
            "/api/v1/incidents/test-001/analyze",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data


class TestAPIApproval:
    def test_approve_root_cause(self, client):
        client.post(
            "/api/v1/incidents/urn:li:incident:approval-001/analyze",
            data=json.dumps({
                "incident_title": "Approval test",
                "incident_description": "Duplicate rows after retry.",
                "incident_custom_type": "DUPLICATE_ROWS",
                "human_confirmed_root_cause": "Retry was not idempotent.",
                "confirmed_by": "submitter",
                "target_asset_urn": "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_daily_ledger,PROD)",
            }), content_type="application/json",
        )
        resp = client.post(
            "/api/v1/incidents/urn:li:incident:approval-001/root-cause/approve",
            data=json.dumps({"decision": "approved", "approver": "tester"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["state"] == "approved"
        assert data["approval_type"] == "root_cause"
        run_id = client.get("/api/v1/runs").get_json()["runs"][0]["run_id"]
        assert client.get(f"/api/v1/runs/{run_id}").get_json()["lesson"] is not None

    def test_reject_root_cause(self, client):
        client.post(
            "/api/v1/incidents/urn:li:incident:approval-002/analyze",
            data=json.dumps({
                "incident_title": "Approval test",
                "incident_description": "Duplicate rows after retry.",
                "incident_custom_type": "DUPLICATE_ROWS",
                "human_confirmed_root_cause": "Unconfirmed cause.",
                "confirmed_by": "submitter",
                "target_asset_urn": "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_daily_ledger,PROD)",
            }), content_type="application/json",
        )
        resp = client.post(
            "/api/v1/incidents/urn:li:incident:approval-002/root-cause/approve",
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
        assert resp.status_code == 404
        assert resp.get_json()["error"] == "NOT_FOUND"

    def test_reject_control(self, client):
        resp = client.post(
            "/api/v1/controls/ctrl-001/approve",
            data=json.dumps({"decision": "rejected", "approver": "tester"}),
            content_type="application/json",
        )
        assert resp.status_code == 404
        assert resp.get_json()["error"] == "NOT_FOUND"


class TestAPIBacktestAndPublish:
    def test_backtest_without_active_run(self, client):
        """Backtest endpoint is self-contained."""
        resp = client.post(
            "/api/v1/lessons/lesson-001/backtest",
            data=json.dumps({"target_field": "transaction_id"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "NO_ACTIVE_RUN"

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
        assert r1.get_json()["lesson"] is None

        # Step 2: Explicit root-cause approval
        r_approval = client.post(
            "/api/v1/incidents/urn:li:incident:full-flow-001/root-cause/approve",
            data=json.dumps({"decision": "approved", "approver": "tester"}),
            content_type="application/json",
        )
        assert r_approval.status_code == 200
        lesson_id = client.get(f"/api/v1/runs/{run_id}").get_json()["lesson"]["lesson_id"]

        # Step 3: Backtest
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

        # Step 4: Approve control
        r3 = client.post(
            f"/api/v1/controls/{control_id}/approve",
            data=json.dumps({"decision": "approved", "approver": "tester"}),
            content_type="application/json",
        )
        assert r3.status_code == 200

        # Step 5: Publish
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
        assert resp.status_code == 404
        assert resp.get_json()["error"] == "NOT_FOUND"


    def test_publish_blocked_before_control_approval(self, client):
        """A backtested control cannot be published before human approval."""
        payload = {
            "incident_title": "Publish gate test",
            "incident_description": "Duplicate rows after retry.",
            "incident_custom_type": "DUPLICATE_ROWS",
            "human_confirmed_root_cause": "Retry was not idempotent.",
            "confirmed_by": "tester",
            "target_asset_urn": "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_daily_ledger,PROD)",
        }
        r1 = client.post(
            "/api/v1/incidents/urn:li:incident:publish-gate-001/analyze",
            data=json.dumps(payload), content_type="application/json",
        )
        assert r1.status_code == 200
        client.post(
            "/api/v1/incidents/urn:li:incident:publish-gate-001/root-cause/approve",
            data=json.dumps({"decision": "approved", "approver": "tester"}),
            content_type="application/json",
        )
        run_id = r1.get_json()["run_id"]
        run = client.get(f"/api/v1/runs/{run_id}").get_json()
        backtest = client.post(
            f"/api/v1/lessons/{run['lesson']['lesson_id']}/backtest",
            data=json.dumps({"target_field": "transaction_id"}),
            content_type="application/json",
        ).get_json()
        control_id = backtest["control"]["control_id"]
        publish = client.post(
            f"/api/v1/controls/{control_id}/publish",
            data=json.dumps({}), content_type="application/json",
        )
        assert publish.status_code == 409
        assert publish.get_json()["error"] == "APPROVAL_REQUIRED"


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
