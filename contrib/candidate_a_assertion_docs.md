# Upstream Contribution: Assertion Execution Boundary Documentation

**Candidate**: A
**Target repository**: `datahub-project/datahub`
**Status**: `patch prepared locally`
**Date**: 2026-07-23

## Purpose

Clarify which assertion capabilities are available in DataHub OSS versus
DataHub Cloud. This patch is based on evidence collected during the
DataHub Reflex project (tested against OSS v1.5.0.6).

## Proposed addition to DataHub Python SDK documentation

The following text should be added to the `DataHubGraph` class docstring
or a dedicated "Assertions" section in the SDK documentation:

```markdown
### Assertion Support: OSS vs Cloud

DataHub supports two assertion-related capabilities with different
availability:

| Capability | OSS | Cloud | Notes |
|-----------|-----|-------|-------|
| Assertion definition storage | Partial | Yes | `upsertAssertion` GraphQL mutation available in older OSS versions; removed in v1.5.0.6 |
| Assertion run event storage | Partial | Yes | REST endpoint `/openapi/assertions/v1/run` returns 404 in OSS v1.5.0.6 |
| Assertion execution (`run_assertion`) | No | Yes | Requires DataHub Cloud backend; not available via OSS GraphQL |
| Assertion scheduling | No | Yes | Cloud-only feature |

#### For OSS users

If you are using DataHub OSS:

- Store assertion **definitions** via the `assertions` aspect on datasets.
- Implement your own **execution layer** to run assertions against data.
- Do not call `DataHubGraph.run_assertion()` or `run_assertions()` —
  these methods require a Cloud backend and will fail in OSS.
- The `AcrylCloudExecutionRequest` and `AcrylCloudExecutionResult`
  classes are Cloud-only types.

#### For Cloud users

- `run_assertion()` and `run_assertions()` are available.
- Assertion scheduling is configured in the Cloud UI.
- Run results appear in the DataHub UI under the "Validation" tab.

#### Recommended OSS pattern

```python
# Write assertion definitions to DataHub
from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.metadata.schema_classes import AssertionInfoClass

# Execute assertions in your own layer
def execute_assertion(assertion_urn: str, dataset_urn: str) -> dict:
    \"\"\"Custom assertion execution — not provided by OSS.\"\"\"
    # Your execution logic here
    pass

# Store run results as DataHub timeseries (if supported)
# Or maintain your own result store
```

## Evidence

Collected from the DataHub Reflex project (Apache 2.0, public):

1. `reflex/datahub/write_client.py`:
   - `OSS_ASSERTION_DEFINITIONS = False`
   - `OSS_ASSERTION_RUN_EVENTS = False`
   - `create_assertion_definition()` raises `DataHubCapabilityUnavailable`
   - `ingest_assertion_run_event()` raises `DataHubCapabilityUnavailable`

2. `spikes/spike-01-datahub-write-path/run_spike.py` line 297:
   > "DataHub OSS does not support run_assertion() via GraphQL."

3. `spikes/spike-01-datahub-write-path/test_spike.py`:
   - `test_spike_does_not_call_run_assertion()` — automated verification

## Compatibility

- Documentation-only change.
- No code changes to the SDK.
- Does not modify existing behavior.

## Estimated size

Small: ~50 lines of documentation in one file.
