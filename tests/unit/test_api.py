"""Tests for the product API with SQLite persistence (P0.1)."""

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
        assert data["persistence"] == "sqlite"


class TestAPIIncidentAnalysis:
    def test_analyze_incident(self, client):
        resp = client.post("/api/v1/incidents/urn:li:incident:api-test/analyze",
            data=json.dumps({"incident_title": "T", "incident_description": "D",
                "incident_custom_type": "DUPLICATE_ROWS",
                "human_confirmed_root_cause": "R", "confirmed_by": "t",
                "target_asset_urn": "urn:li:dataset:(urn:li:dataPlatform:bigquery,x,PROD)"}),
            content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "run_id" in data
        assert data["incident"]["root_cause_approved"] is True
        assert data["lesson"]["control_type"] == "uniqueness"


class TestAPIApproval:
    def test_approve_root_cause(self, client):
        resp = client.post("/api/v1/incidents/t1/root-cause/approve",
            data=json.dumps({"decision": "approved", "approver": "t", "run_id": "r1"}),
            content_type="application/json")
        assert resp.status_code == 200

    def test_reject_root_cause(self, client):
        resp = client.post("/api/v1/incidents/t1/root-cause/approve",
            data=json.dumps({"decision": "rejected", "approver": "t"}),
            content_type="application/json")
        assert resp.status_code == 200

    def test_approve_control(self, client):
        resp = client.post("/api/v1/controls/c1/approve",
            data=json.dumps({"decision": "approved", "approver": "t", "run_id": "r1"}),
            content_type="application/json")
        assert resp.status_code == 200

    def test_reject_control(self, client):
        resp = client.post("/api/v1/controls/c1/approve",
            data=json.dumps({"decision": "rejected", "approver": "t", "run_id": "r1"}),
            content_type="application/json")
        assert resp.status_code == 200


class TestAPIBacktestAndPublish:
    def test_backtest(self, client):
        resp = client.post("/api/v1/lessons/L1/backtest",
            data=json.dumps({"target_field": "transaction_id"}),
            content_type="application/json")
        assert resp.status_code == 200
        assert resp.get_json()["backtest"]["can_recommend"] is True

    def test_publish(self, client):
        resp = client.post("/api/v1/controls/c1/publish",
            data=json.dumps({"run_id": "r1"}), content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["publication"]["status"] == "reflex-owned"
        assert data["detection"]["detected"] is True

    def test_full_workflow(self, client):
        r1 = client.post("/api/v1/incidents/urn:li:incident:full/analyze",
            data=json.dumps({"incident_title": "F", "incident_description": "F",
                "incident_custom_type": "DUPLICATE_ROWS",
                "human_confirmed_root_cause": "R", "confirmed_by": "t",
                "target_asset_urn": "urn:li:dataset:(urn:li:dataPlatform:bigquery,x,PROD)"}),
            content_type="application/json")
        assert r1.status_code == 200
        run_id = r1.get_json()["run_id"]
        lesson_id = r1.get_json()["lesson"]["lesson_id"]

        r2 = client.post(f"/api/v1/lessons/{lesson_id}/backtest",
            data=json.dumps({"target_field": "transaction_id", "run_id": run_id}),
            content_type="application/json")
        assert r2.status_code == 200
        control_id = r2.get_json()["control"]["control_id"]

        r3 = client.post(f"/api/v1/controls/{control_id}/approve",
            data=json.dumps({"decision": "approved", "approver": "t", "run_id": run_id}),
            content_type="application/json")
        assert r3.status_code == 200

        r4 = client.post(f"/api/v1/controls/{control_id}/publish",
            data=json.dumps({"run_id": run_id}), content_type="application/json")
        assert r4.status_code == 200
        assert r4.get_json()["is_complete"] is True

        # Verify persistence: runs survive between requests
        r5 = client.get(f"/api/v1/runs/{run_id}")
        assert r5.status_code == 200
        assert r5.get_json()["is_complete"] is True

        # Audit trail is available
        r6 = client.get(f"/api/v1/runs/{run_id}/audit")
        assert r6.status_code == 200
        assert len(r6.get_json()["events"]) >= 5


class TestAPIRuns:
    def test_list_runs(self, client):
        resp = client.get("/api/v1/runs")
        assert resp.status_code == 200
        assert "runs" in resp.get_json()

    def test_get_nonexistent_run(self, client):
        resp = client.get("/api/v1/runs/nonexistent")
        assert resp.status_code == 404
