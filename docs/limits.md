# Limitations

This document records all known limitations, assumptions, and constraints.
It is a living document — update it whenever a new limitation is discovered.

## DataHub OSS vs Cloud

| Capability | DataHub OSS | DataHub Cloud | Reflex Workaround |
|-----------|-------------|---------------|-------------------|
| Assertion execution (`run_assertion`) | ❌ Not available | ✅ Available | Reflex owns execution via `ReflexBacktester` |
| Assertion definition storage | ⚠️ `upsertAssertion` removed in v1.5.0.6 | ✅ Available | Reflex stores definitions locally |
| Assertion run event storage | ⚠️ REST endpoint unavailable in OSS v1.5.0.6 | ✅ Available | Reflex stores run events locally |
| Incident creation (`raiseIncident`) | ✅ Available | ✅ Available | Used directly (v1.5.0.6+ API) |
| Incident status updates | ✅ Available | ✅ Available | Used directly |
| Structured properties | ✅ Available (>= 0.14) | ✅ Available | Used for Reflex coverage metadata |
| Ownership updates | ✅ Available | ✅ Available | Executed only after human approval |
| Search across entities | ✅ Available | ✅ Available | Used for candidate discovery |
| Agent Context tools | ✅ Read-oriented | ✅ Read-oriented | Custom write clients implemented |
| Actions framework | ❌ Limited | ✅ Available | Not used by Reflex |

**Key boundary**: Reflex owns control execution, backtesting, lesson extraction, approval workflow, and similarity scoring. In live mode, candidate discovery is performed against DataHub and a query failure is surfaced explicitly; Reflex never silently substitutes its synthetic fixture graph. DataHub OSS stores metadata, incidents, ownership, structured properties, and (when supported) assertion definitions and run events.

## Known Limitations (Current Implementation)

### 1. Lesson extraction is template-based, not LLM-driven
The current implementation uses scenario-specific templates (`build_duplicate_rows_lesson`, `build_orphaned_ownership_lesson`). An LLM interface is available but not the default. Two scenarios: `duplicate_rows` and `orphaned_ownership`.

### 2. Similarity resolution has two modes
- **Live DataHub mode** (`use_live_datahub=True`): Uses `DataHubSimilarityResolver` which queries live DataHub via `searchAcrossEntities` (max 10 datasets), applies 6 signals (same_domain, shared_tags, compatible_schema, append_only_vulnerability, similar_lineage, no_existing_control), and raises an explicit `DataHubLiveQueryError` if DataHub is unreachable. It never falls back to synthetic data.
- **Synthetic mode** (`use_live_datahub=False`, default): Uses the `SimilarityResolver` with in-memory datasets from `reflex.datahub.environment`.

### 3. Live DataHub integration tests exist but require running instance
Integration tests in `tests/integration/` verify the live Reflex/DataHub paths. These require a running DataHub OSS instance started with the tested Quickstart command (`python -m datahub docker quickstart`) and are marked `@pytest.mark.requires_datahub`. Unit and evaluation tests run without DataHub.

### 4. DataHub Docker image and API versioning
- DataHub OSS v1.5.0.6 is the tested version (via `quickstart`).
- `upsertAssertion` GraphQL mutation was removed in v1.5.0.6. Assertion definitions are Reflex-owned.
- `createIncident` is deprecated; `raiseIncident` is the current API (v1.5.0.6+).
- The REST endpoint `/openapi/assertions/v1/run` returns 404 in OSS v1.5.0.6.
- GraphQL schema changes between versions (e.g., `IncidentStatus.type` → `IncidentStatus.state`).

### 5. Backtesting data is synthetic
Historical snapshots are JSON files built by Reflex, not actual DataHub timeseries (`DatasetProfile`, `Operation` aspects). Production would read from DataHub's timeseries API.

### 6. Human approval is mandatory, not simulated
Two explicit approval gates exist:
1. **Root-cause approval** — Before lesson extraction. Blocking unless `non_interactive_test_mode=True`.
2. **Control approval** — Before publication. Requires explicit `decision_{control_id}.json` file or test mode.

In non-test mode, the pipeline raises `PipelineApprovalRequired` if no explicit decision exists. Test mode (`non_interactive_test_mode=True`) auto-approves both gates for automated testing.

### 7. Only two control types
Only `UniquenessControl` (SQL-like `GROUP BY cols HAVING COUNT(*) > 1`) and `ActiveOwnershipControl` (ownership validity checks) are implemented. No generic rule engine exists.

### 8. No schema-change protection
This is explicitly a stretch goal and is not on the critical path.

### 9. Single-asset backtesting
Each `ReflexControl` targets one asset. Propagation to similar assets generates detection results but those similar assets are not individually backtested against historical data.

### 10. Ownership remediation is approval-gated
The `ActiveOwnershipControl` detects orphaned assets and proposes replacement candidates. In the live UI path, approved replacements are written to DataHub after the second human approval; there is no autonomous reassignment. The synthetic evaluation path persists an update plan rather than mutating DataHub.

### 11. Control approval decision file ties to dynamic control ID
When `non_interactive_test_mode=False`, the control approval stage requires a JSON file at `approvals/decision_{control_id}.json`. Since `control_id` is a deterministic hash, this file can be pre-created if the control ID is known, but in practice test mode is used for integration testing.

## Assumptions

1. DataHub OSS is accessible at `http://localhost:8080` (configurable via `DATAHUB_GMS_URL`)
2. Incidents use a custom `customType` field for Reflex-specific categorization (e.g., `REFLEX_DETECTED`, `REFLEX_TEST`)
3. Root cause is stored as approved text in Reflex domain models, not as a dedicated DataHub field
4. The `reflex:` tag and structured property namespace is available for Reflex-specific metadata
5. Assertion execution is Reflex-owned; DataHub OSS stores metadata only
6. Test URNs use an isolated prefix (`REFLEX_TEST_PREFIX`, default: `reflex-test`)
