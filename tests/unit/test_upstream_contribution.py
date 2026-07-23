"""Regression tests for prepared DataHub upstream contribution patches."""

from __future__ import annotations

from typing import Any

from contrib.candidate_b_incident_helpers import IncidentHelpersMixin


class _FakeGraph(IncidentHelpersMixin):
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def execute_graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((query, variables))
        if "raiseIncident" in query:
            return {"raiseIncident": "urn:li:incident:test-upstream-001"}
        return {"updateIncidentStatus": True}


def test_incident_helper_uses_oss_status_field() -> None:
    graph = _FakeGraph()

    assert graph.update_incident_status("urn:li:incident:test-001", "RESOLVED") is True

    _, variables = graph.calls[-1]
    assert variables["status"] == {"state": "RESOLVED"}


def test_incident_helper_raise_returns_urn() -> None:
    graph = _FakeGraph()

    urn = graph.raise_incident(
        title="Test incident",
        description="Created by the contribution regression test.",
        resource_urn="urn:li:dataset:(urn:li:dataPlatform:bigquery,test,PROD)",
    )

    assert urn.startswith("urn:li:incident:")
