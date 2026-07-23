"""DataHub write client — thin wrapper over DataHub OSS GraphQL API for mutations.

This client ONLY writes. It does NOT contain Reflex business logic.

Capabilities used:
- Incident creation and updates
- Assertion definition creation (NOT execution — Cloud-only)
- Assertion run event ingestion (Reflex records its own backtest/execution results)
- Ownership updates
- Structured property updates
- Tag assignment
- Coverage metadata (stored as structured properties or custom aspects)

IMPORTANT: DataHub OSS cannot execute assertions. Reflex implements its own
backtesting and execution layer. We only use DataHub to STORE assertion definitions
and run-result events for discoverability.
"""

from __future__ import annotations

import json
from typing import Any

import httpx


class DataHubWriteClient:
    """Write client for DataHub OSS.

    All mutations are explicit. No implicit side effects.
    """

    # Assertion definition upsert and assertion run-event ingestion are not
    # available in DataHub OSS v1.5.0.6. Reflex owns these artifacts.
    OSS_ASSERTION_DEFINITIONS = False
    OSS_ASSERTION_RUN_EVENTS = False

    def __init__(self, gms_url: str = "http://localhost:8080", token: str = "") -> None:
        self._gms_url = gms_url.rstrip("/")
        self._token = token
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if token:
            self._headers["Authorization"] = f"Bearer {token}"

    async def _ingest(self, entity_type: str, aspect_type: str, urn: str, aspect: dict[str, Any]) -> dict[str, Any]:
        """Ingest a metadata aspect via the /openapi endpoint."""
        payload = {
            "entity": {
                "value": {
                    f"com.linkedin.metadata.snapshot.{entity_type}Snapshot": {
                        "urn": urn,
                        "aspects": [
                            {
                                f"com.linkedin.common.{aspect_type}": aspect,
                            }
                        ],
                    }
                }
            }
        }
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            response = await client.post(
                f"{self._gms_url}/openapi/entities/v1/",
                json=payload,
                headers=self._headers,
            )
            response.raise_for_status()
            return response.json()

    # -- Incidents ---------------------------------------------------------------

    async def create_incident(
        self,
        title: str,
        description: str,
        entity_urns: list[str],
        incident_type: str = "CUSTOM",
        custom_type: str = "REFLEX_DETECTED",
        source_type: str = "MANUAL",
    ) -> str:
        """Create a new incident in DataHub (v0.14.x API — deprecated).

        Returns the new incident URN.
        """
        mutation = """
        mutation($input: CreateIncidentInput!) {
            createIncident(input: $input) {
                urn
            }
        }
        """
        variables = {
            "input": {
                "title": title,
                "description": description,
                "type": incident_type,
                "customType": custom_type,
                "sourceType": source_type,
                "entities": entity_urns,
            }
        }
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            response = await client.post(
                f"{self._gms_url}/api/graphql",
                json={"query": mutation, "variables": variables},
                headers=self._headers,
            )
            response.raise_for_status()
            data = response.json()
            if "errors" in data:
                raise DataHubMutationError(data["errors"])
            return data["data"]["createIncident"]["urn"]

    async def raise_incident(
        self,
        title: str,
        description: str,
        resource_urn: str,
        custom_type: str = "REFLEX_DETECTED",
        source_type: str = "MANUAL",
        status_state: str = "ACTIVE",
    ) -> str:
        """Raise a new incident in DataHub (v1.5.0.6+ API: raiseIncident).

        Returns the new incident URN.
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
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            response = await client.post(
                f"{self._gms_url}/api/graphql",
                json={"query": mutation, "variables": variables},
                headers=self._headers,
            )
            response.raise_for_status()
            data = response.json()
            if "errors" in data:
                raise DataHubMutationError(data["errors"])
            return data["data"]["raiseIncident"]

    async def update_incident_status(self, incident_urn: str, status: str) -> bool:
        """Update an incident's status (e.g., to RESOLVED)."""
        mutation = """
        mutation($urn: String!, $status: IncidentStatusInput!) {
            updateIncidentStatus(urn: $urn, input: $status)
        }
        """
        # DataHub OSS v1.5.x names this input field `state`, not `type`.
        variables = {"urn": incident_urn, "status": {"state": status}}
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            response = await client.post(
                f"{self._gms_url}/api/graphql",
                json={"query": mutation, "variables": variables},
                headers=self._headers,
            )
            response.raise_for_status()
            data = response.json()
            if "errors" in data:
                raise DataHubMutationError(data["errors"])
            return True

    # -- Assertion Definitions ---------------------------------------------------

    async def create_assertion_definition(
        self,
        dataset_urn: str,
        assertion_type: str,
        description: str,
        platform_urn: str = "urn:li:dataPlatform:reflex",
    ) -> str:
        """Create an assertion definition in DataHub.

        This STORES the definition. It does NOT execute it.
        Execution is handled by Reflex's own backtesting engine.
        """
        if not self.OSS_ASSERTION_DEFINITIONS:
            raise DataHubCapabilityUnavailable(
                "DataHub OSS does not expose assertion definition upsert; "
                "Reflex must store the control definition locally."
            )
        mutation = """
        mutation($input: UpsertAssertionInput!) {
            upsertAssertion(input: $input) {
                urn
            }
        }
        """
        variables = {
            "input": {
                "entityUrn": dataset_urn,
                "type": assertion_type,
                "description": description,
                "platformUrn": platform_urn,
            }
        }
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            response = await client.post(
                f"{self._gms_url}/api/graphql",
                json={"query": mutation, "variables": variables},
                headers=self._headers,
            )
            response.raise_for_status()
            data = response.json()
            if "errors" in data:
                raise DataHubMutationError(data["errors"])
            return data["data"]["upsertAssertion"]["urn"]

    # -- Assertion Run Events ----------------------------------------------------

    async def ingest_assertion_run_event(
        self,
        assertion_urn: str,
        result_type: str,  # "SUCCESS", "FAILURE", "ERROR"
        timestamp_millis: int,
        native_result: dict[str, Any] | None = None,
    ) -> None:
        """Ingest an assertion run event into DataHub.

        This is how Reflex records its own backtest and execution results
        in DataHub for discoverability. DataHub OSS stores these events
        but does not generate them.
        """
        if not self.OSS_ASSERTION_RUN_EVENTS:
            raise DataHubCapabilityUnavailable(
                "DataHub OSS does not expose assertion run-event ingestion; "
                "Reflex must store and execute run events locally."
            )
        event = {
            "timestampMillis": timestamp_millis,
            "assertionUrn": assertion_urn,
            "status": "COMPLETE",
            "result": {
                "type": result_type,
                "nativeResults": native_result or {},
            },
        }
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            response = await client.post(
                f"{self._gms_url}/openapi/assertions/v1/run",
                json=event,
                headers=self._headers,
            )
            response.raise_for_status()

    # -- Ownership Updates -------------------------------------------------------

    async def update_owner(
        self,
        entity_urn: str,
        owner_urn: str,
        ownership_type: str = "TECHNICAL_OWNER",
    ) -> None:
        """Update or add an owner for an entity."""
        mutation = """
        mutation($input: AddOwnerInput!) {
            addOwner(input: $input)
        }
        """
        variables = {
            "input": {
                "resourceUrn": entity_urn,
                "ownerUrn": owner_urn,
                "ownerEntityType": "CORP_USER",
                "ownershipTypeUrn": (
                    "urn:li:ownershipType:__system__technical_owner"
                    if ownership_type == "TECHNICAL_OWNER"
                    else f"urn:li:ownershipType:{ownership_type.lower()}"
                ),
            }
        }
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            response = await client.post(
                f"{self._gms_url}/api/graphql",
                json={"query": mutation, "variables": variables},
                headers=self._headers,
            )
            response.raise_for_status()
            data = response.json()
            if "errors" in data:
                raise DataHubMutationError(data["errors"])

    # -- Structured Properties ---------------------------------------------------

    async def set_structured_property(
        self, entity_urn: str, property_urn: str, values: list[dict[str, Any]]
    ) -> None:
        """Set a structured property on an entity.

        Used for storing Reflex coverage metadata, lesson references, etc.
        """
        mutation = """
        mutation($input: UpsertStructuredPropertiesInput!) {
            upsertStructuredProperties(input: $input) {
                properties {
                    structuredProperty { urn }
                    values {
                        ... on StringValue { stringValue }
                        ... on NumberValue { numberValue }
                    }
                }
            }
        }
        """
        variables = {
            "input": {
                "assetUrn": entity_urn,
                "structuredPropertyInputParams": [
                    {
                        "structuredPropertyUrn": property_urn,
                        "values": values,
                    }
                ],
            }
        }
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            response = await client.post(
                f"{self._gms_url}/api/graphql",
                json={"query": mutation, "variables": variables},
                headers=self._headers,
            )
            response.raise_for_status()
            data = response.json()
            if "errors" in data:
                raise DataHubMutationError(data["errors"])

    # -- Tags --------------------------------------------------------------------

    async def create_tag(self, tag_id: str, name: str, description: str = "") -> str:
        """Create a tag and return its URN; existing tags are idempotent."""
        mutation = """
        mutation($input: CreateTagInput!) {
            createTag(input: $input)
        }
        """
        variables = {"input": {"id": tag_id, "name": name, "description": description}}
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            response = await client.post(
                f"{self._gms_url}/api/graphql",
                json={"query": mutation, "variables": variables},
                headers=self._headers,
            )
            response.raise_for_status()
            data = response.json()
            if "errors" in data:
                messages = json.dumps(data["errors"])
                if "already exists" not in messages.lower():
                    raise DataHubMutationError(data["errors"])
                return f"urn:li:tag:{tag_id}"
            return data["data"]["createTag"]

    async def add_tag(self, entity_urn: str, tag_urn: str) -> None:
        """Add a tag to an entity."""
        mutation = """
        mutation($input: AddTagsInput!) {
            addTags(input: $input)
        }
        """
        variables = {
            "input": {
                "resourceUrn": entity_urn,
                "tagUrns": [tag_urn],
            }
        }
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            response = await client.post(
                f"{self._gms_url}/api/graphql",
                json={"query": mutation, "variables": variables},
                headers=self._headers,
            )
            response.raise_for_status()
            data = response.json()
            if "errors" in data:
                messages = json.dumps(data["errors"])
                if "urn does not exist" in messages.lower() and tag_urn.startswith("urn:li:tag:"):
                    tag_id = tag_urn.removeprefix("urn:li:tag:")
                    await self.create_tag(
                        tag_id=tag_id,
                        name=tag_id,
                        description="DataHub Reflex coverage metadata",
                    )
                    await self.add_tag(entity_urn, tag_urn)
                    return
                raise DataHubMutationError(data["errors"])


class DataHubMutationError(Exception):
    """Raised when a DataHub GraphQL mutation returns errors."""

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self.errors = errors
        super().__init__(json.dumps(errors))


class DataHubCapabilityUnavailable(RuntimeError):
    """Raised when an operation is unavailable in DataHub OSS."""
