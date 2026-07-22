# Architecture

## System Boundaries

```
┌──────────────────────────────────────────────────────┐
│                      Reflex                          │
│                                                      │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────┐  │
│  │ Pipeline │  │ Backtester│  │ Control Executors│  │
│  │ (orchest-│  │ (Reflex-  │  │ (Uniqueness,     │  │
│  │  rator)  │  │  owned)   │  │  ActiveOwnership)│  │
│  └────┬─────┘  └─────┬─────┘  └────────┬─────────┘  │
│       │              │                │              │
│  ┌────┴──────────────┴────────────────┴──────────┐   │
│  │              Domain Models                     │   │
│  │  ReflexLesson, ReflexControl, BacktestResult,  │   │
│  │  SimilarAssetCandidate, ApprovalDecision       │   │
│  └────────────────────┬───────────────────────────┘   │
│                       │                               │
│  ┌────────────────────┴───────────────────────────┐   │
│  │           Approval Service                      │   │
│  │      (mandatory human approval gate)            │   │
│  └────────────────────────────────────────────────┘   │
│                                                      │
└──────────────────────┬───────────────────────────────┘
                       │
               ┌───────┴────────┐
               │  DataHub OSS   │
               │  (GMS/GraphQL) │
               │                │
               │  • Incidents   │
               │  • Lineage     │
               │  • Ownership   │
               │  • Domains     │
               │  • Tags        │
               │  • Assertions  │
               │    (definitions│
               │     & events)  │
               └────────────────┘
```

## Key Design Decisions

### 1. DataHub is the metadata store, not the execution engine
DataHub OSS stores assertion definitions and run events. Reflex executes controls in its own backtesting engine. This avoids the Cloud-only `run_assertion()` dependency.

### 2. Typed controls, not a rule engine
Only two control types exist for the MVP: `UniquenessControl` and `ActiveOwnershipControl`. Each has a deterministic executor. No generic rule language is implemented.

### 3. Mandatory human approval
No control, remediation, or ownership change is published without explicit human approval. The approval gate is architectural, not optional.

### 4. Root cause must be confirmed
A `ReflexLesson` is not valid (`is_confirmed = False`) until `confirmed_or_edited_by` is set. The pipeline refuses to proceed with unconfirmed root causes.

## Component Responsibilities

| Component | Responsibility | Owned By |
|-----------|---------------|----------|
| `ReflexPipeline` | Orchestrates the central loop (8 steps) | Reflex |
| `ReflexBacktester` | Runs controls against synthetic historical data | Reflex |
| `ControlSynthesizer` | Generates typed controls from lessons | Reflex |
| `SimilarityResolver` | Discovers similar assets (live DataHub or synthetic) | Reflex |
| `DataHubSimilarityResolver` | Queries live DataHub via `searchAcrossEntities` (6 signals) | Reflex |
| `ApprovalService` | Enforces mandatory human approval gates | Reflex |
| `DataHubReadClient` | Reads incidents, lineage, ownership, etc. | DataHub |
| `DataHubWriteClient` | Writes incidents, ownership, tags, structured properties | DataHub |

## Data Flow

```
Resolved Incident (DataHub)
    │
    ▼
Human confirms root cause (ApprovalService gate 1)
    │
    ▼
ReflexLesson (Reflex domain model — template-based or LLM-assisted)
    │
    ▼
Similar Asset Discovery
    ├── Live mode: DataHubSimilarityResolver → searchAcrossEntities (6 signals)
    └── Synthetic mode: SimilarityResolver → in-memory datasets
    │
    ▼
ReflexControl (typed, deterministic control_definition)
    │
    ▼
Historical Backtest (ReflexBacktester against synthetic JSON snapshots)
    │
    ▼
Human Control Approval (ApprovalService gate 2)
    ├── non_interactive_test_mode=True → auto-approve
    └── non_interactive_test_mode=False → requires decision_{control_id}.json
    │
    ▼
Publication to DataHub (incidents, ownership, tags, structured properties)
    │
    ▼
Assertion definitions & run events (Reflex-owned in OSS v1.5.0.6)
    │
    ▼
Detection on similar assets (ControlExecutor)
    │
    ▼
New Incident creation for violations (DataHubWriteClient.raise_incident)
```
