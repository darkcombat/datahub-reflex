"""Verify the UI duplicate-row demo requires two explicit approvals."""

from __future__ import annotations

from ui.app import app


def test_duplicate_rows_ui_requires_root_and_control_approval() -> None:
    client = app.test_client()

    client.post("/api/reset")
    response = client.post("/api/run", json={"scenario": "duplicate_rows"})
    state = response.get_json()
    assert response.status_code == 200
    assert state["current_step"] == 2
    assert state["approval_state"] == "pending"
    assert state["lesson_id"] == ""

    response = client.post(
        "/api/approve",
        json={"decision": "approved", "approver": "test-user"},
    )
    state = response.get_json()
    assert response.status_code == 200
    assert state["current_step"] == 7
    assert state["approval_state"] == "pending"
    assert state["control_id"]
    assert state["detection_violations"] == []

    response = client.post(
        "/api/approve",
        json={"decision": "approved", "approver": "test-user"},
    )
    state = response.get_json()
    assert response.status_code == 200
    assert state["is_complete"] is True
    assert state["current_step"] == 9
    assert len(state["detection_violations"]) == 1
