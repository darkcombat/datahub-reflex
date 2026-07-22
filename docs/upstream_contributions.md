# DataHub Reflex — Upstream Contribution Candidates

Generated: 2026-07-23
Evaluated by: Open-Source Contribution and Repository Quality Engineer

Status definitions:
- `researched`: Code inspected, gap documented, no patch prepared
- `patch prepared locally`: Patch exists in the Reflex repository, not yet submitted
- `submitted`: PR/issue opened upstream (requires external evidence URL)
- `merged`: Accepted upstream (requires authoritative evidence)
- `deferred`: Not appropriate for current phase

**Critical rule**: Never use `submitted` or `merged` without an external,
authoritative link to the upstream repository.

---

## Candidate A — Assertion execution documentation gap

| Field | Value |
|-------|-------|
| **Upstream repository** | `datahub-project/datahub` |
| **Status** | `researched` |
| **Files inspected** | `reflex/datahub/write_client.py` (class flags: `OSS_ASSERTION_DEFINITIONS = False`, `OSS_ASSERTION_RUN_EVENTS = False`); `spikes/spike-01-datahub-write-path/run_spike.py` (line 297: "DataHub OSS does not support run_assertion() via GraphQL."); `spikes/spike-01-datahub-write-path/test_spike.py` (test_spike_does_not_call_run_assertion) |
| **Current behavior** | DataHub OSS v1.5.0.6 does not expose `run_assertion()` via GraphQL. The `upsertAssertion` mutation was removed. The `/openapi/assertions/v1/run` REST endpoint returns 404. DataHub Cloud supports assertion execution natively. |
| **Gap** | DataHub's Python SDK (`acryl-datahub`) documents `DataHubGraph` methods but does not clearly indicate which are Cloud-only. Users may assume `run_assertion()` works in OSS. |
| **Proposed change** | Add a table or docstring note to `DataHubGraph` (or the upstream docs) clarifying: (a) `run_assertion()` and `run_assertions()` require DataHub Cloud; (b) OSS users should implement their own execution layer; (c) assertion definitions can be stored in OSS but not executed. |
| **Compatibility impact** | None — documentation-only change. |
| **Tests required** | A single test verifying `run_assertion()` raises `NotImplementedError` or a clear error when GMS does not support it. |
| **Estimated size** | Small (1 file: documentation + 1 test). |
| **Ready to submit** | No — requires coordination with DataHub maintainers. |
| **Submitted** | No. |
| **Issue/PR URL** | None. |

---

## Candidate B — DataHubGraph incident helpers

| Field | Value |
|-------|-------|
| **Upstream repository** | `datahub-project/datahub` (Python SDK: `acryl-datahub`) |
| **Status** | `researched` |
| **Files inspected** | `reflex/datahub/write_client.py` (methods `raise_incident`, `update_incident_status`, `create_incident` — thin GraphQL wrappers); `reflex/datahub/read_client.py` (methods `get_incident`, `list_resolved_incidents` — note: broken against OSS v1.5.0.6, see MED-03 in issue register) |
| **Current behavior** | Reflex implements its own `DataHubWriteClient` and `DataHubReadClient` with incident GraphQL operations. These are thin wrappers using raw GraphQL queries via `httpx`. The `acryl-datahub` SDK (`DataHubGraph`) does not currently expose convenience methods for `raiseIncident`, `updateIncidentStatus`, or `resolveIncident`. |
| **Gap** | The DataHub Python SDK lacks first-class incident management helpers. Users must write raw GraphQL mutations for common incident operations. |
| **Proposed change** | Add `raise_incident(title, description, resource_urn, custom_type, source_type)`, `update_incident_status(incident_urn, status)`, and `resolve_incident(incident_urn)` to `DataHubGraph`. Follow existing naming conventions (`make_dataset_urn`, `get_aspect_v2`). Use type hints consistent with the SDK. Include tests for `raiseIncident` and `updateIncidentStatus` GraphQL mutations. |
| **Compatibility impact** | Additive — no breaking changes. New methods on `DataHubGraph`. |
| **Tests required** | Integration tests against a running DataHub OSS instance using the SDK's existing test patterns. |
| **Estimated size** | Medium (~200 lines: 3 methods + docstrings + 3-5 tests). |
| **Ready to submit** | No — the Reflex live path uses `raiseIncident` successfully, but `get_incident` and `list_resolved_incidents` are broken against OSS v1.5.0.6 (MED-03). Upstream helpers must be tested against a clean OSS instance first. |
| **Submitted** | No. |
| **Issue/PR URL** | None. |

---

## Candidate C — MCP incident tools

| Field | Value |
|-------|-------|
| **Upstream repository** | `datahub-project/datahub` (subproject: `datahub-agent-context` MCP server) |
| **Status** | `deferred` |
| **Files inspected** | Reflex MCP-related code is not implemented. This is a forward-looking candidate. |
| **Current behavior** | The `datahub-agent-context` MCP server exposes read-oriented tools (search, browse, schema inspection). Incident write tools (`raise_incident`, `update_incident_status`) are not currently exposed. |
| **Gap** | Agent-based workflows cannot raise or update incidents through MCP. This limits agent-driven incident management. |
| **Proposed change** | Add `search_incidents`, `get_incident`, `raise_incident`, and `update_incident_status` as MCP tools in `datahub-agent-context`. Follow existing tool conventions. |
| **Compatibility impact** | Additive — new MCP tools only. |
| **Tests required** | MCP integration tests against a running DataHub instance. |
| **Estimated size** | Large (requires MCP server changes, new GraphQL queries, tool registration, tests). |
| **Ready to submit** | No — depends on Candidates A and B being researched first. |
| **Submitted** | No. |
| **Issue/PR URL** | None. |
| **Reason for deferral** | The 20-day plan (Days 14-15) explicitly states: "Decide whether incident helper methods are mature enough for a second PR." MCP tools are a further extension. This candidate is deferred until after the hackathon submission to avoid sacrificing the MVP for upstream breadth. |

---

## Summary

| Candidate | Status | Ready to submit | Estimated size |
|-----------|--------|----------------|---------------|
| A — Assertion execution docs | `researched` | No | Small |
| B — DataHubGraph incident helpers | `researched` | No | Medium |
| C — MCP incident tools | `deferred` | No | Large |

**No upstream PRs have been submitted.** All candidates are in the research phase, consistent with the 20-day plan (Days 14-15) which says: "upstream contributions are either linked or honestly labeled as prepared, never claimed as merged."

---

## Next steps (post-submission)

1. Fix MED-03 (broken GraphQL queries in `DataHubReadClient`) to ensure the incident read path works against OSS v1.5.0.6.
2. Prepare a patch for Candidate B (incident helpers) with proper SDK conventions and tests.
3. Open a documentation issue for Candidate A with specific evidence from this project.
4. Re-evaluate Candidate C only after Candidates A and B are submitted or merged.
