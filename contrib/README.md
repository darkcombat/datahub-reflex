# Upstream Contributions — Prepared Patches

This directory contains prepared upstream contribution patches for the
DataHub project. These patches are ready for review and submission but
have NOT been submitted yet.

## Status

| Candidate | File | Status |
|-----------|------|--------|
| A — Assertion docs | `candidate_a_assertion_docs.md` | `patch prepared locally` |
| B — Incident helpers | `candidate_b_incident_helpers.py` | `patch prepared locally` |
| C — MCP tools | (deferred) | `deferred` |

## How to submit

1. **Candidate A**: Open a documentation PR against `datahub-project/datahub`
   adding the proposed text to the SDK documentation or README.

2. **Candidate B**: Open a code PR against `datahub-project/datahub` adding
   the `IncidentHelpersMixin` methods to `DataHubGraph` in
   `src/datahub/ingestion/graph/client.py` with corresponding tests in
   `tests/integration/graph/test_incidents.py`.

## Evidence

All claims in these patches are backed by evidence from the DataHub Reflex
project (Apache 2.0, public at https://github.com/darkcombat/datahub-reflex),
specifically:

- Integration tests against DataHub OSS v1.5.0.6 (8 tests passing)
- Spike analysis of DataHub write paths
- Automated verification that `run_assertion()` is never called

## Important

These patches are NOT submitted. Do not claim they are merged or accepted
without an authoritative upstream URL.
