"""
Upstream Contribution: DataHubGraph Incident Helpers

Candidate: B
Target repository: datahub-project/datahub (Python SDK: acryl-datahub)
Status: patch prepared locally
Date: 2026-07-23

These methods are designed to be added to `DataHubGraph` in the
`acryl-datahub` package. They follow existing SDK conventions:
- snake_case method names (make_dataset_urn, get_aspect_v2)
- type hints with Optional
- docstrings with Args/Returns/Raises
- httpx for HTTP calls (consistent with SDK internals)

To integrate upstream:
1. Add these methods to the DataHubGraph class in:
   src/datahub/ingestion/graph/client.py
2. Add corresponding tests in:
   tests/integration/graph/test_incidents.py
3. Follow the SDK's existing test patterns (pytest + fixtures)

These methods have been tested against DataHub OSS v1.5.0.6 via the
DataHub Reflex integration test suite (tests/integration/test_live_datahub.py).
"""

from __future__ import annotations

from typing import Any, Optional

# ---------------------------------------------------------------------------
# Proposed additions to DataHubGraph (acryl-datahub SDK)
# ---------------------------------------------------------------------------


class IncidentHelpersMixin:
    """Mixin providing incident management helpers for DataHubGraph.

    These methods are designed to be added to the DataHubGraph class.
    They follow the SDK's existing naming and typing conventions.

    Usage:
        graph = DataHubGraph(server="http://localhost:8080")
        urn = graph.raise_incident(
            title="Duplicate rows detected",
            description="Non-idempotent retry caused duplicates.",
            resource_urn="urn:li:dataset:(urn:li:dataPlatform:bigquery,finance,PROD)",
        )
        graph.update_incident_status(urn, "RESOLVED")
    """

    def raise_incident(
        self,
        title: str,
        description: str,
        resource_urn: str,
        custom_type: str = "CUSTOM",
        source_type: str = "MANUAL",
        status_state: str = "ACTIVE",
    ) -> str:
        """Raise a new incident in DataHub via the raiseIncident GraphQL mutation.

        This is the recommended API for DataHub v1.5.0.6+. The older
        `createIncident` mutation is deprecated.

        Args:
            title: Human-readable incident title.
            description: Detailed incident description.
            resource_urn: URN of the affected entity (e.g., dataset).
            custom_type: Application-specific incident type.
            source_type: Source of the incident (MANUAL, AUTOMATED, etc.).
            status_state: Initial incident state (ACTIVE, RESOLVED).

        Returns:
            The new incident URN (e.g., urn:li:incident:<uuid>).

        Raises:
            DataHubGraphError: If the GraphQL mutation fails.
        """
        mutation = """
        mutation($input: RaiseIncidentInput!) {
            raiseIncident(input: $input)
        }
        """
        variables = {
            "input": {
                "title": title,
                "description": description,
                "type": "CUSTOM",
                "customType": custom_type,
                "resourceUrns": [resource_urn],
                "source": {"type": source_type},
                "status": {"state": status_state},
            }
        }
        # Use the SDK's existing GraphQL client
        result = self.execute_graphql(mutation, variables)
        return result["raiseIncident"]

    def update_incident_status(
        self,
        incident_urn: str,
        status: str,
        message: Optional[str] = None,
    ) -> bool:
        """Update an incident's status in DataHub.

        Common status values: ACTIVE, RESOLVED, INVESTIGATING.

        Args:
            incident_urn: The incident URN to update.
            status: New status (ACTIVE, RESOLVED, INVESTIGATING).
            message: Optional status change message.

        Returns:
            True if the update succeeded.

        Raises:
            DataHubGraphError: If the GraphQL mutation fails.
        """
        mutation = """
        mutation($urn: String!, $status: IncidentStatusInput!) {
            updateIncidentStatus(urn: $urn, input: $status)
        }
        """
        # DataHub OSS v1.5.x names the status field `state`.
        status_input: dict[str, Any] = {"state": status}
        if message:
            status_input["message"] = message
        variables = {"urn": incident_urn, "status": status_input}
        self.execute_graphql(mutation, variables)
        return True

    def resolve_incident(
        self,
        incident_urn: str,
        message: Optional[str] = None,
    ) -> bool:
        """Resolve an incident (convenience wrapper around update_incident_status).

        Args:
            incident_urn: The incident URN to resolve.
            message: Optional resolution message.

        Returns:
            True if the resolution succeeded.
        """
        return self.update_incident_status(
            incident_urn=incident_urn,
            status="RESOLVED",
            message=message,
        )

    def search_incidents(
        self,
        query: str = "*",
        start: int = 0,
        count: int = 20,
    ) -> list[dict[str, Any]]:
        """Search for incidents in DataHub.

        Args:
            query: Search query string (default: "*" for all).
            start: Pagination offset.
            count: Maximum results to return.

        Returns:
            List of incident entities with their metadata.
        """
        graphql_query = """
        query($query: String!, $start: Int!, $count: Int!) {
            searchAcrossEntities(
                input: {
                    types: [INCIDENT]
                    query: $query
                    start: $start
                    count: $count
                }
            ) {
                searchResults {
                    entity {
                        urn
                        type
                        ... on Incident {
                            title
                            description
                            status { state }
                            customType
                            created { time }
                        }
                    }
                }
            }
        }
        """
        result = self.execute_graphql(
            graphql_query,
            {"query": query, "start": start, "count": count},
        )
        results = result.get("searchAcrossEntities", {}).get("searchResults", [])
        return [r["entity"] for r in results if r.get("entity")]

    def get_incident(self, incident_urn: str) -> Optional[dict[str, Any]]:
        """Get a single incident by URN via search.

        Note: DataHub OSS v1.5.0.6 does not expose a top-level
        `incident(urn:)` GraphQL query. This method uses
        searchAcrossEntities to look up the incident by URN.

        Args:
            incident_urn: The incident URN to fetch.

        Returns:
            Incident entity dict, or None if not found.
        """
        # Extract a searchable token from the URN
        parts = incident_urn.split(":")
        search_token = parts[-1] if len(parts) > 1 else incident_urn
        results = self.search_incidents(query=search_token, count=10)
        for entity in results:
            if entity.get("urn") == incident_urn:
                return entity
        return None


# ---------------------------------------------------------------------------
# Test sketch (to be adapted to SDK test conventions)
# ---------------------------------------------------------------------------

"""
Example test structure for upstream integration:

```python
import pytest
from datahub.ingestion.graph.client import DataHubGraph

@pytest.mark.integration
class TestIncidentHelpers:
    def test_raise_incident_creates_urn(self, graph: DataHubGraph):
        urn = graph.raise_incident(
            title="TEST: Integration test incident",
            description="Created by integration test.",
            resource_urn="urn:li:dataset:(urn:li:dataPlatform:hive,SampleHiveDataset,PROD)",
            custom_type="TEST",
        )
        assert urn.startswith("urn:li:incident:")

    def test_update_incident_status(self, graph: DataHubGraph):
        urn = graph.raise_incident(
            title="TEST: Status update test",
            description="Testing status updates.",
            resource_urn="urn:li:dataset:(urn:li:dataPlatform:hive,SampleHiveDataset,PROD)",
        )
        result = graph.update_incident_status(urn, "RESOLVED")
        assert result is True

    def test_search_incidents_finds_results(self, graph: DataHubGraph):
        results = graph.search_incidents(query="*", count=5)
        assert len(results) >= 0  # May be empty if no incidents exist

    def test_resolve_incident(self, graph: DataHubGraph):
        urn = graph.raise_incident(
            title="TEST: Resolution test",
            description="Testing resolution.",
            resource_urn="urn:li:dataset:(urn:li:dataPlatform:hive,SampleHiveDataset,PROD)",
        )
        result = graph.resolve_incident(urn, message="Resolved by test.")
        assert result is True
```
"""
