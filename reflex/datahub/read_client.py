"""DataHub read client — thin wrapper over DataHub OSS GraphQL API.

This client ONLY reads. It does NOT contain Reflex business logic.
All DataHub-specific serialization is contained here.

Key capabilities used:
- Incidents (read resolved incidents)
- Lineage (upstream/downstream traversal for similarity)
- Ownership (read current owners)
- Domains (read domain assignments)
- Tags (read tags)
- Structured properties (read custom metadata)

NOT supported in DataHub OSS (Cloud-only):
- run_assertion() — Reflex implements its own backtesting and execution layer
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx


class DataHubReadClient:
    """Read-only client for DataHub OSS GraphQL API.

    This is intentionally minimal. Each method maps to a single GraphQL query
    and returns typed results. No business logic, no orchestration.
    """

    def __init__(self, gms_url: str = "http://localhost:8080", token: str = "") -> None:
        self._gms_url = gms_url.rstrip("/")
        self._token = token
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if token:
            self._headers["Authorization"] = f"Bearer {token}"

    async def _query(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a raw GraphQL query against DataHub GMS."""
        # Quickstart GraphQL can take several seconds while Elasticsearch
        # refreshes; keep a bounded but realistic read timeout.
        request = {
            "query": query,
            "variables": variables or {},
        }
        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            for attempt in range(3):
                try:
                    response = await client.post(
                        f"{self._gms_url}/api/graphql",
                        json=request,
                        headers=self._headers,
                    )
                    response.raise_for_status()
                    data = response.json()
                    if "errors" in data:
                        raise DataHubQueryError(data["errors"])
                    return data["data"]
                except (httpx.ConnectError, httpx.ReadError, httpx.ReadTimeout) as exc:
                    last_error = exc
                    if attempt == 2:
                        raise
                    await asyncio.sleep(0.5 * (attempt + 1))

        # The loop either returns or raises; this keeps static type checkers
        # aware that an unexpected control-flow change is still an error.
        raise RuntimeError(f"DataHub GraphQL request failed: {last_error}")

    # -- Incidents ---------------------------------------------------------------

    async def get_incident(self, incident_urn: str) -> dict[str, Any]:
        """Fetch a single incident by URN.

        DataHub OSS quickstart does not expose the standalone ``incident``
        root query in all supported versions. Use the public search resolver
        instead, which is also the path used for incident discovery.
        """
        query = """
        query($query: String!) {
            searchAcrossEntities(input: {types: [INCIDENT], query: $query, start: 0, count: 20}) {
                searchResults {
                    entity {
                        urn
                        type
                        ... on Incident {
                            title
                            description
                            status { state }
                            customType
                            source { type }
                            created { time actor }
                        }
                    }
                }
            }
        }
        """
        result = await self._query(query, {"query": incident_urn})
        results = result.get("searchAcrossEntities", {}).get("searchResults", [])
        for item in results:
            entity = item.get("entity", {})
            if entity.get("urn") == incident_urn:
                status = entity.get("status") or {}
                if "type" in status and "state" not in status:
                    status["state"] = status["type"]
                return entity
        return {}

    async def list_resolved_incidents(self, start: int = 0, count: int = 20) -> list[dict[str, Any]]:
        """List resolved incidents. Reflex starts from resolved incidents only."""
        query = """
        query($start: Int!, $count: Int!) {
            searchAcrossEntities(
                input: {
                    types: [INCIDENT]
                    query: "*"
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
                            status {
                                type
                            }
                            customType
                            created {
                                time
                            }
                            entities {
                                nodes {
                                    entity {
                                        urn
                                        type
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        """
        result = await self._query(query, {"start": start, "count": count})
        results = result.get("searchAcrossEntities", {}).get("searchResults", [])
        return [
            r["entity"]
            for r in results
            if r.get("entity", {}).get("status", {}).get("type") == "RESOLVED"
        ]

    # -- Lineage -----------------------------------------------------------------

    async def get_upstream_lineage(self, dataset_urn: str) -> list[str]:
        """Get upstream dataset URNs for a given dataset."""
        query = """
        query($urn: String!) {
            entity(urn: $urn) {
                ... on Dataset {
                    upstreamLineage {
                        upstreams {
                            dataset {
                                urn
                            }
                        }
                    }
                }
            }
        }
        """
        result = await self._query(query, {"urn": dataset_urn})
        entity = result.get("entity", {})
        upstreams = entity.get("upstreamLineage", {}).get("upstreams", [])
        return [u["dataset"]["urn"] for u in upstreams]

    async def get_downstream_lineage(self, dataset_urn: str) -> list[str]:
        """Get downstream dataset URNs for a given dataset."""
        query = """
        query($urn: String!) {
            entity(urn: $urn) {
                ... on Dataset {
                    downstreamLineage {
                        downstreams {
                            dataset {
                                urn
                            }
                        }
                    }
                }
            }
        }
        """
        result = await self._query(query, {"urn": dataset_urn})
        entity = result.get("entity", {})
        downstreams = entity.get("downstreamLineage", {}).get("downstreams", [])
        return [d["dataset"]["urn"] for d in downstreams]

    # -- Ownership ---------------------------------------------------------------

    async def get_owners(self, entity_urn: str) -> list[dict[str, Any]]:
        """Get owners for an entity."""
        query = """
        query($urn: String!) {
            entity(urn: $urn) {
                ... on Dataset {
                    ownership {
                        owners {
                            owner {
                                ... on CorpUser {
                                    urn
                                    username
                                    properties {
                                        active
                                    }
                                }
                                ... on CorpGroup {
                                    urn
                                    name
                                }
                            }
                            type
                        }
                    }
                }
            }
        }
        """
        result = await self._query(query, {"urn": entity_urn})
        entity = result.get("entity") or {}
        owners = (entity.get("ownership") or {}).get("owners", [])
        return [
            {
                "urn": o["owner"]["urn"],
                "username": o["owner"].get("username") or o["owner"].get("name", ""),
                "type": o["type"],
                "active": o["owner"].get("properties", {}).get("active", True) if "properties" in o["owner"] else None,
            }
            for o in owners
        ]

    # -- Domains -----------------------------------------------------------------

    async def get_domain(self, entity_urn: str) -> str | None:
        """Get the domain of an entity, if assigned."""
        query = """
        query($urn: String!) {
            entity(urn: $urn) {
                ... on Dataset {
                    domain {
                        domain {
                            urn
                            properties {
                                name
                            }
                        }
                    }
                }
            }
        }
        """
        result = await self._query(query, {"urn": entity_urn})
        domain_data = (result.get("entity") or {}).get("domain")
        domain_data = (domain_data or {}).get("domain")
        if domain_data:
            return domain_data.get("properties", {}).get("name", "")
        return None

    # -- Tags --------------------------------------------------------------------

    async def get_tags(self, entity_urn: str) -> list[str]:
        """Get tags for an entity."""
        query = """
        query($urn: String!) {
            entity(urn: $urn) {
                tags {
                    tags {
                        tag {
                            urn
                            properties {
                                name
                            }
                        }
                    }
                }
            }
        }
        """
        result = await self._query(query, {"urn": entity_urn})
        tags = result.get("entity", {}).get("tags", {}).get("tags", [])
        return [t["tag"]["properties"]["name"] for t in tags if "properties" in t.get("tag", {})]

    # -- Structured Properties ---------------------------------------------------

    async def get_structured_properties(self, entity_urn: str) -> dict[str, Any]:
        """Get structured properties for an entity."""
        query = """
        query($urn: String!) {
            entity(urn: $urn) {
                structuredProperties {
                    properties {
                        propertyUrn
                        values {
                            stringValue
                            numberValue
                        }
                    }
                }
            }
        }
        """
        result = await self._query(query, {"urn": entity_urn})
        props = result.get("entity", {}).get("structuredProperties", {}).get("properties", [])
        output: dict[str, Any] = {}
        for p in props:
            values = p.get("values", [])
            if values:
                # Extract the first non-null value
                for v in values:
                    val = v.get("stringValue") or v.get("numberValue")
                    if val is not None:
                        output[p["propertyUrn"]] = val
                        break
        return output

    # -- Assertions --------------------------------------------------------------

    async def get_assertion_definitions(self, dataset_urn: str) -> list[dict[str, Any]]:
        """Get assertion definitions (NOT executions) for a dataset.

        DataHub OSS can STORE assertion definitions. It cannot EXECUTE them.
        """
        query = """
        query($urn: String!) {
            entity(urn: $urn) {
                ... on Dataset {
                    assertions(start: 0, count: 100) {
                        assertions {
                            urn
                            type
                            description
                            platform {
                                urn
                            }
                        }
                    }
                }
            }
        }
        """
        result = await self._query(query, {"urn": dataset_urn})
        entity = result.get("entity", {})
        return entity.get("assertions", {}).get("assertions", [])

    # -- Search & Discovery ------------------------------------------------------

    async def search_datasets(
        self, query_str: str, start: int = 0, count: int = 20
    ) -> list[dict[str, Any]]:
        """Search for datasets matching a query string."""
        query = """
        query($query: String!, $start: Int!, $count: Int!) {
            searchAcrossEntities(
                input: {
                    types: [DATASET]
                    query: $query
                    start: $start
                    count: $count
                }
            ) {
                searchResults {
                    entity {
                        urn
                        type
                        ... on Dataset {
                            name
                            platform {
                                name
                            }
                            domain {
                                domain {
                                    properties {
                                        name
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        """
        result = await self._query(query, {"query": query_str, "start": start, "count": count})
        return result.get("searchAcrossEntities", {}).get("searchResults", [])


class DataHubQueryError(Exception):
    """Raised when a DataHub GraphQL query returns errors."""

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self.errors = errors
        super().__init__(json.dumps(errors))
