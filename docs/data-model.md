# Data Model

## Core Domain Models

### ReflexLesson
A structured lesson extracted from a resolved incident. Root cause is not authoritative until confirmed.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `lesson_id` | `LessonId` | Yes | Unique identifier (e.g., `reflex-lesson-a1b2c3d4e5f6`) |
| `source_incident_urn` | `UrnStr` | Yes | DataHub URN of the source incident |
| `title` | `str` | Yes | Human-readable title |
| `human_confirmed_root_cause` | `str` | Yes | The root cause text (not authoritative until confirmed) |
| `confirmed_or_edited_by` | `str` | Yes | Identity of confirmer (empty = unconfirmed) |
| `approval_timestamp` | `datetime?` | No | When root cause was confirmed |
| `failure_pattern` | `FailurePattern` | Yes | Categorized failure pattern |
| `trigger` | `str` | Yes | What triggered this lesson |
| `vulnerable_characteristics` | `list[str]` | No | Characteristics making assets vulnerable |
| `candidate_preventive_control` | `ProposedControl` | Yes | Candidate control before synthesis |
| `intended_propagation_scope` | `list[str]` | No | Domains/tags this should propagate to |
| `confidence` | `Confidence` | No | high/medium/low/unknown |
| `limitations` | `list[str]` | No | Known limitations |
| `provenance` | `str` | No | How this lesson was produced |

### ReflexControl
An executable, versioned preventive control.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `control_id` | `ControlId` | Yes | Unique identifier |
| `lesson_id` | `LessonId` | Yes | Parent lesson |
| `target_asset_urn` | `UrnStr` | Yes | Asset this control targets |
| `control_type` | `ControlType` | Yes | uniqueness or active_ownership |
| `control_definition` | `str` | Yes | Deterministic, executable definition |
| `backtest_results` | `list[BacktestResult]` | No | Results from historical backtesting |
| `approval_decision` | `ApprovalDecision?` | No | approved/rejected/modified |
| `approved_by` | `str` | No | Who approved |
| `version` | `int` | Yes | Version number, starts at 1 |
| `publication_status` | `PublicationStatus` | Yes | draft → pending_approval → approved → published |
| `created_at` | `datetime` | Yes | Creation timestamp |
| `updated_at` | `datetime` | Yes | Last update timestamp |

### BacktestResult
Result of running a control against historical data.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `backtest_id` | `str` | Yes | Unique identifier |
| `control_id` | `ControlId` | Yes | Control that was backtested |
| `target_asset_urn` | `UrnStr` | Yes | Asset that was checked |
| `executed_at` | `datetime` | Yes | Execution timestamp |
| `historical_window_start` | `datetime` | Yes | Start of historical window |
| `historical_window_end` | `datetime` | Yes | End of historical window |
| `would_have_detected` | `bool` | Yes | Would the control have detected the incident? |
| `detection_timestamp` | `datetime?` | No | Earliest detection point |
| `false_positives` | `int` | Yes | False positive count |
| `true_positives` | `int` | Yes | True positive count |
| `evidence` | `str` | No | Supporting evidence |
| `limitations` | `list[str]` | No | Known limitations of this result |

### SimilarAssetCandidate
An asset identified as similar through graph traversal.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `asset_urn` | `UrnStr` | Yes | Asset URN |
| `asset_type` | `str` | Yes | Asset type |
| `similarity_rationale` | `str` | Yes | Why this asset is similar |
| `matched_characteristics` | `list[str]` | No | Which characteristics matched |
| `domain` | `str` | No | Domain assignment |
| `owners` | `list[str]` | No | Current owners |
| `confidence` | `Confidence` | No | Similarity confidence |

## Control Types

### UniquenessControl
- **Control Type**: `uniqueness`
- **Definition Format**: SQL-like `SELECT cols GROUP BY cols HAVING COUNT(*) > 1`
- **Executor**: `UniquenessControlExecutor`
- **Data Source**: List of row dicts (in-memory for MVP)

### ActiveOwnershipControl
- **Control Type**: `active_ownership`
- **Definition Format**: `CHECK ownership validity: at_least_N_active_owner required_types=[...]`
- **Executor**: `ActiveOwnershipControlExecutor`
- **Data Source**: List of asset ownership records

## State Machine: PublicationStatus

```
DRAFT → PENDING_APPROVAL → APPROVED → PUBLISHED
  ↓                          ↓
  └──────────────────────────┴──→ REJECTED
                                   ↓
                              SUPERSEDED
```

## DataHub Entity Mapping

| Reflex Model | DataHub Entity | Aspect | OSS v1.5.0.6 Status |
|-------------|---------------|--------|---------------------|
| `ReflexLesson` | Structured Property on dataset | `reflex:lesson` | ✅ Available |
| `ReflexControl` | Assertion Definition | `AssertionInfo` | ⚠️ `upsertAssertion` removed; Reflex-owned |
| `BacktestResult` | Assertion Run Event | `AssertionRunEvent` | ⚠️ REST endpoint 404s; Reflex-owned |
| `ReflexCoverage` | Structured Property on dataset | `reflex:coverage` | ✅ Available |
| `SimilarAssetCandidate` | (computed, not stored) | — | ✅ Via `searchAcrossEntities` |

**Note**: In DataHub OSS v1.5.0.6, assertion definitions and run events are Reflex-owned. The `upsertAssertion` GraphQL mutation was removed and the `/openapi/assertions/v1/run` REST endpoint returns 404. Reflex stores these locally and writes only structured properties, tags, incidents, and ownership to DataHub OSS.
