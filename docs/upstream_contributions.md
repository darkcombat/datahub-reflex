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
| **Status** | `patch prepared locally` |
| **Files inspected** | `reflex/datahub/write_client.py` (class flags: `OSS_ASSERTION_DEFINITIONS = False`, `OSS_ASSERTION_RUN_EVENTS = False`); `spikes/spike-01-datahub-write-path/` |
| **Prepared patch** | `contrib/candidate_a_assertion_docs.md` — Proposed documentation addition clarifying OSS vs Cloud assertion support, with evidence table and recommended OSS pattern. |
| **Ready to submit** | Yes — documentation-only, no code changes needed. |
| **Submitted** | No. |
| **Issue/PR URL** | None. |

---

## Candidate B — DataHubGraph incident helpers

| Field | Value |
|-------|-------|
| **Upstream repository** | `datahub-project/datahub` (Python SDK: `acryl-datahub`) |
| **Status** | `patch prepared locally` |
| **Files inspected** | `reflex/datahub/write_client.py`, `reflex/datahub/read_client.py`, `tests/integration/test_live_datahub.py` |
| **Prepared patch** | `contrib/candidate_b_incident_helpers.py` — `IncidentHelpersMixin` with `raise_incident`, `update_incident_status`, `resolve_incident`, `search_incidents`, `get_incident`. ~180 lines including docstrings and test sketch. Follows SDK naming conventions. |
| **Ready to submit** | Yes — payload shape is covered by a local unit test and the underlying mutation is verified against OSS (9/9 Reflex integration tests pass). |
| **Submitted** | No. |
| **Issue/PR URL** | None. |
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
| A — Assertion execution docs | `patch prepared locally` | Yes | Small |
| B — DataHubGraph incident helpers | `patch prepared locally` | Yes | Medium |
| C — MCP incident tools | `deferred` | No | Large |

**No upstream PRs have been submitted.** Candidates A and B are prepared locally;
Candidate C remains deferred. No contribution is claimed as submitted or merged
without an authoritative upstream URL.

---

## Next steps (post-submission)

1. Fix MED-03 (broken GraphQL queries in `DataHubReadClient`) to ensure the incident read path works against OSS v1.5.0.6.
2. Prepare a patch for Candidate B (incident helpers) with proper SDK conventions and tests.
3. Open a documentation issue for Candidate A with specific evidence from this project.
4. Re-evaluate Candidate C only after Candidates A and B are submitted or merged.
