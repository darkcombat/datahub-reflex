"""Tests for the product API with SQLite persistence and auth (P0.1-P0.2)."""

from __future__ import annotations

import json
import os

import pytest

from ui.app import app as flask_app
from reflex.auth import create_token
from reflex.persistence import database as db


@pytest.fixture(autouse=True)
def _set_secret(monkeypatch):
    monkeypatch.setenv("REFLEX_API_SECRET", "test-secret-key-for-tests")
    monkeypatch.setenv("REFLEX_BOOTSTRAP_SECRET", "test-bootstrap-secret")


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


@pytest.fixture
def admin_headers():
    token = create_token("admin-user", "admin")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture
def approver_headers():
    token = create_token("approver-user", "approver")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture
def viewer_headers():
    token = create_token("viewer-user", "viewer")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


class TestAPIHealth:
    def test_health_endpoint(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["persistence"] == "sqlite"


class TestAPIAuth:
    def test_create_token_admin(self, client):
        resp = client.post("/api/v1/auth/token",
            data=json.dumps({"subject": "test", "role": "admin", "bootstrap_secret": "test-bootstrap-secret"}),
            content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "token" in data
        assert data["role"] == "admin"

    def test_create_token_invalid_role(self, client):
        resp = client.post("/api/v1/auth/token",
            data=json.dumps({"subject": "test", "role": "superuser"}),
            content_type="application/json")
        assert resp.status_code == 400

    def test_token_requires_bootstrap_secret(self, client):
        resp = client.post("/api/v1/auth/token",
            data=json.dumps({"subject": "test", "role": "admin"}),
            content_type="application/json")
        assert resp.status_code == 401

    def test_unauthenticated_rejected(self, client):
        resp = client.post("/api/v1/incidents/test/analyze",
            data=json.dumps({}), content_type="application/json")
        assert resp.status_code == 401

    def test_viewer_cannot_approve(self, client, viewer_headers):
        resp = client.post("/api/v1/incidents/test/root-cause/approve",
            data=json.dumps({"decision": "approved"}),
            headers=viewer_headers)
        assert resp.status_code == 403

    def test_admin_can_create(self, client, admin_headers):
        resp = client.post("/api/v1/incidents/urn:li:incident:auth-test/analyze",
            data=json.dumps({"incident_title": "Auth", "incident_description": "Test",
                "incident_custom_type": "DUPLICATE_ROWS",
                "human_confirmed_root_cause": "R", "confirmed_by": "admin",
                "target_asset_urn": "urn:li:dataset:(urn:li:dataPlatform:bigquery,x,PROD)"}),
            headers=admin_headers)
        assert resp.status_code == 200

    def test_invalid_token_rejected(self, client):
        resp = client.post("/api/v1/incidents/test/analyze",
            data=json.dumps({}),
            headers={"Authorization": "Bearer invalid.token.here"})
        assert resp.status_code == 401


class TestAPIIncidentAnalysis:
    def test_analyze_incident(self, client, admin_headers):
        resp = client.post("/api/v1/incidents/urn:li:incident:api-test/analyze",
            data=json.dumps({"incident_title": "T", "incident_description": "D",
                "incident_custom_type": "DUPLICATE_ROWS",
                "human_confirmed_root_cause": "R", "confirmed_by": "t",
                "target_asset_urn": "urn:li:dataset:(urn:li:dataPlatform:bigquery,x,PROD)"}),
            headers=admin_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "run_id" in data
        assert data["incident"]["root_cause_approved"] is False
        assert data["lesson"] is None
        approval = client.post(
            "/api/v1/incidents/urn:li:incident:api-test/root-cause/approve",
            data=json.dumps({"decision": "approved", "approver": "t", "run_id": data["run_id"]}),
            headers=admin_headers,
        )
        assert approval.status_code == 200


class TestAPIApproval:
    def test_approve_root_cause(self, client, admin_headers):
        resp = client.post("/api/v1/incidents/t1/root-cause/approve",
            data=json.dumps({"decision": "approved", "approver": "t", "run_id": "r1"}),
            headers=admin_headers)
        assert resp.status_code == 404

    def test_reject_root_cause(self, client, admin_headers):
        resp = client.post("/api/v1/incidents/t1/root-cause/approve",
            data=json.dumps({"decision": "rejected", "approver": "t"}),
            headers=admin_headers)
        assert resp.status_code == 404

    def test_approve_control(self, client, admin_headers):
        resp = client.post("/api/v1/controls/c1/approve",
            data=json.dumps({"decision": "approved", "approver": "t", "run_id": "r1"}),
            headers=admin_headers)
        assert resp.status_code == 404

    def test_reject_control(self, client, admin_headers):
        resp = client.post("/api/v1/controls/c1/approve",
            data=json.dumps({"decision": "rejected", "approver": "t", "run_id": "r1"}),
            headers=admin_headers)
        assert resp.status_code == 404


class TestAPIBacktestAndPublish:
    def test_backtest(self, client, admin_headers):
        resp = client.post("/api/v1/lessons/L1/backtest",
            data=json.dumps({"target_field": "transaction_id"}),
            headers=admin_headers)
        assert resp.status_code == 404

    def test_publish(self, client, admin_headers):
        resp = client.post("/api/v1/controls/c1/publish",
            data=json.dumps({"run_id": "r1"}), headers=admin_headers)
        assert resp.status_code == 404

    def test_full_workflow(self, client, admin_headers):
        r1 = client.post("/api/v1/incidents/urn:li:incident:full/analyze",
            data=json.dumps({"incident_title": "F", "incident_description": "F",
                "incident_custom_type": "DUPLICATE_ROWS",
                "human_confirmed_root_cause": "R", "confirmed_by": "t",
                "target_asset_urn": "urn:li:dataset:(urn:li:dataPlatform:bigquery,x,PROD)"}),
            headers=admin_headers)
        assert r1.status_code == 200
        run_id = r1.get_json()["run_id"]
        blocked = client.post(
            "/api/v1/lessons/not-yet-created/backtest",
            data=json.dumps({"target_field": "transaction_id", "run_id": run_id}),
            headers=admin_headers,
        )
        assert blocked.status_code == 404
        approval = client.post(
            "/api/v1/incidents/urn:li:incident:full/root-cause/approve",
            data=json.dumps({"decision": "approved", "approver": "t", "run_id": run_id}),
            headers=admin_headers,
        )
        assert approval.status_code == 200
        lesson_row = db.get_db().execute(
            "SELECT id FROM lessons WHERE run_id = ? ORDER BY created_at DESC LIMIT 1", (run_id,)
        ).fetchone()
        assert lesson_row is not None
        lesson_id = lesson_row["id"]

        r2 = client.post(f"/api/v1/lessons/{lesson_id}/backtest",
            data=json.dumps({"target_field": "transaction_id", "run_id": run_id}),
            headers=admin_headers)
        assert r2.status_code == 200
        control_id = r2.get_json()["control"]["control_id"]

        r3 = client.post(f"/api/v1/controls/{control_id}/approve",
            data=json.dumps({"decision": "approved", "approver": "t", "run_id": run_id}),
            headers=admin_headers)
        assert r3.status_code == 200

        r4 = client.post(f"/api/v1/controls/{control_id}/publish",
            data=json.dumps({"run_id": run_id}), headers=admin_headers)
        assert r4.status_code == 200
        assert r4.get_json()["is_complete"] is True

        # Verify persistence: runs survive between requests
        r5 = client.get(f"/api/v1/runs/{run_id}", headers=admin_headers)
        assert r5.status_code == 200
        assert r5.get_json()["is_complete"] is True

        # Audit trail is available
        r6 = client.get(f"/api/v1/runs/{run_id}/audit", headers=admin_headers)
        assert r6.status_code == 200
        assert len(r6.get_json()["events"]) >= 5


class TestAPIRuns:
    def test_list_runs(self, client):
        token = create_token("viewer-user", "viewer")
        resp = client.get("/api/v1/runs", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert "runs" in resp.get_json()

    def test_get_nonexistent_run(self, client):
        token = create_token("viewer-user", "viewer")
        resp = client.get("/api/v1/runs/nonexistent",
            headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 404

    def test_execute_duplicate_rows(self, client, admin_headers):
        resp = client.post("/api/v1/runs/urn:li:incident:exec-dup-001/execute",
            data=json.dumps({"scenario": "duplicate_rows",
                "incident_title": "Exec Test", "incident_description": "Test",
                "human_confirmed_root_cause": "Retry bug",
                "target_asset_urn": "urn:li:dataset:(urn:li:dataPlatform:bigquery,x,PROD)",
                "target_field": "transaction_id"}),
            headers=admin_headers)
        assert resp.status_code == 409
        assert resp.get_json()["error"] == "NON_INTERACTIVE_EXECUTION_DISABLED"

    def test_execute_orphaned_ownership(self, client, admin_headers):
        resp = client.post("/api/v1/runs/urn:li:incident:exec-owner-001/execute",
            data=json.dumps({"scenario": "orphaned_ownership",
                "incident_title": "Ownership Test", "incident_description": "Inactive owner",
                "human_confirmed_root_cause": "Offboarding gap",
                "target_asset_urn": "urn:li:dataset:(urn:li:dataPlatform:bigquery,x,PROD)",
                "inactive_owner_urn": "urn:li:corpuser:bob"}),
            headers=admin_headers)
        assert resp.status_code == 409
        assert resp.get_json()["error"] == "NON_INTERACTIVE_EXECUTION_DISABLED"
