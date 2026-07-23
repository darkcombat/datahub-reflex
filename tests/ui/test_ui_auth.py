"""Authentication boundary tests for the product browser workflow."""

from __future__ import annotations

import pytest

from reflex.auth import create_token
from ui.app import app


@pytest.fixture
def auth_client(monkeypatch):
    monkeypatch.setenv("REFLEX_API_SECRET", "ui-auth-test-secret")
    monkeypatch.setenv("REFLEX_UI_AUTH_REQUIRED", "true")
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_product_ui_requires_token_for_state(auth_client):
    response = auth_client.get("/api/state")
    assert response.status_code == 401
    assert response.get_json()["error"] == "UNAUTHORIZED"


def test_product_ui_accepts_valid_read_token(auth_client):
    token = create_token("viewer@example.com", "viewer")
    response = auth_client.get(
        "/api/state", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert "current_step" in response.get_json()


def test_product_ui_restricts_mutations_by_role(auth_client):
    viewer = create_token("viewer@example.com", "viewer")
    approver = create_token("approver@example.com", "approver")

    run_as_viewer = auth_client.post(
        "/api/run",
        json={"scenario": "duplicate_rows"},
        headers={"Authorization": f"Bearer {viewer}"},
    )
    assert run_as_viewer.status_code == 403

    approval_as_approver = auth_client.post(
        "/api/approve",
        json={"decision": "approved"},
        headers={"Authorization": f"Bearer {approver}"},
    )
    assert approval_as_approver.status_code == 200
    assert approval_as_approver.get_json()["error"] != "FORBIDDEN"
