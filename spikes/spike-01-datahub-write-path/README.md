# Spike 01: DataHub OSS Write-Path Verification

## Purpose

Prove all required DataHub OSS write and read operations before building the Reflex product. This spike is the Phase 1 exit gate.

## Operations Verified (v1.5.0.6)

| # | Operation | API | OSS Support |
|---|-----------|-----|-------------|
| 01 | Raise incident | GraphQL `raiseIncident` | ✅ (v1.5.0.6+; `createIncident` is deprecated) |
| 02 | Read incident | GraphQL `incident` query | ✅ |
| 03 | Update incident status | GraphQL `updateIncidentStatus` | ✅ |
| 04 | Create assertion definition | GraphQL `upsertAssertion` | ⚠️ Removed in v1.5.0.6 |
| 05 | Read assertion definition | GraphQL `entity` query | ✅ |
| 06 | Write AssertionRunEvent | REST `/openapi/assertions/v1/run` | ⚠️ 404 in OSS v1.5.0.6 |
| 07 | Verify run event | GraphQL `assertions.runEvents` | ✅ (if events exist) |
| 08 | Create structured properties | REST `/openapi/v2/structuredProperty` | ⚠️ Requires DataHub >= 0.14 |
| 09 | Write structured property values | GraphQL `upsertStructuredProperties` | ✅ |
| 10 | Update asset ownership | GraphQL `updateOwnership` | ✅ |
| 11 | Read updated ownership | GraphQL `ownership` query | ✅ |
| 12 | Reset scenario | Entity isolation via prefix | ✅ |

## v1.5.0.6 API Changes

Versus v0.14.x:
- `createIncident` → `raiseIncident` (new API, different input shape)
- `IncidentStatus.type` → `IncidentStatus.state`
- `upsertAssertion` removed from GraphQL schema
- `/openapi/assertions/v1/run` returns 404 (requires assertion platform)

## OSS vs Cloud Boundary

| Capability | OSS | Cloud |
|-----------|-----|-------|
| `run_assertion()` | ❌ Not available | ✅ |
| AssertionRunEvent ingestion via REST | ❌ Not available in v1.5.0.6 | ✅ |
| All GraphQL mutations (except upsertAssertion) | ✅ | ✅ |
| Structured properties | ✅ (>= 0.14) | ✅ |

## Setup

```bash
# From project root
docker compose up -d

# Wait for DataHub to be healthy (~2-5 minutes)
# Check: http://localhost:9002 (DataHub frontend)
# Check: http://localhost:8080/health (GMS health)
```

## Run

```bash
python spikes/spike-01-datahub-write-path/run_spike.py
```

## Reset

```bash
# The spike uses a SPIKE_PREFIX (urn:li:spike01) for isolation.
# No explicit cleanup is needed — entities are namespaced.
# To fully remove, delete via DataHub UI or re-ingest with deletion.

python spikes/spike-01-datahub-write-path/run_spike.py --reset
```

## Integration Test

```bash
# Requires running DataHub
pytest spikes/spike-01-datahub-write-path/test_spike.py -v

# Skip DataHub-dependent tests
pytest spikes/spike-01-datahub-write-path/test_spike.py -v -k "not requires_datahub"
```

## Exit Gate

- All 12 operations must pass or have documented OSS limitations
- No `run_assertion()` call is present
- The spike does not mock or simulate DataHub writes
- Results are saved to `spikes/spike-01-datahub-write-path/results.json`
