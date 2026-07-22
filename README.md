# DataHub Reflex

Convert a human-confirmed data incident lesson into a backtested, executable preventive control and propagate it to similar assets through the DataHub graph.

> Reflex does not make DataHub self-healing. It turns approved operational lessons into executable, testable, and reusable preventive controls.

## 1. Problem

Data platforms detect and resolve incidents every day. But the operational lesson — _why_ the incident happened and _how_ to prevent it — usually stays trapped in a ticket, post-mortem document, or Slack thread. The next time a similar asset encounters the same failure pattern, the organization starts from zero.

DataHub captures rich metadata about assets, lineage, ownership, and incidents. But there is no structured path from a **resolved incident** back to a **preventive control** that covers similar assets.

## 2. What DataHub Reflex does

Reflex converts a human-confirmed lesson from a resolved DataHub incident into:

- A **structured lesson** (failure pattern, trigger, vulnerable characteristics)
- A **deterministic, executable control** (not only a textual recommendation)
- A **historical backtest** proving the control would have detected the original incident
- A **human approval gate** (mandatory — Reflex is not self-healing)
- **Publication into DataHub** (assertion definition, run events, coverage metadata)
- **Propagation to similar assets** through DataHub's graph (domain, lineage, schema, tags)
- **Detection of analogous future incidents** through the published control

## 3. Why DataHub is structurally necessary

Reflex is not an optional metadata attachment to an otherwise standalone system. DataHub provides:

| Capability | Role in Reflex |
|-----------|---------------|
| **Incidents** | Source of resolved incidents and root causes |
| **Lineage** | Traverses upstream/downstream graph for similar-asset discovery |
| **Ownership** | Identifies inactive owners; proposes domain-based replacements |
| **Domains & Tags** | Filters propagation scope to relevant assets |
| **Schemas** | Matches target fields (e.g., `transaction_id`) across assets |
| **Structured Properties** | Stores Reflex coverage metadata and lesson references |
| **Assertion Definitions** | Stores the control definition in DataHub for discoverability |
| **Assertion Run Events** | Records backtest and execution results as DataHub timeseries |

DataHub **stores** assertion definitions and run events. Reflex **executes** them. This separation is deliberate — DataHub OSS does not support assertion execution natively.

## 4. Central loop

```
Resolved Incident → Human Root-Cause Approval
                          │
                  ┌───────┘
                  ▼
         Structured Lesson Extraction
                  │
                  ▼
         Similar-Asset Discovery (DataHub graph)
                  │
                  ▼
         Control Synthesis (typed, deterministic)
                  │
                  ▼
         Historical Backtest (Reflex-owned execution)
                  │
                  ▼
         Human Control Approval (mandatory gate)
                  │
                  ▼
         Publication into DataHub
                  │
                  ▼
         Analogous Future Incident Detection
```

## 5. Architecture

| Component | Ownership | Responsibility |
|-----------|-----------|---------------|
| `ReflexPipeline` | Reflex | Orchestrates the central loop (steps 1-8) |
| `ReflexBacktester` | Reflex | Executes controls against synthetic historical data |
| `ControlSynthesizer` | Reflex | Generates typed, deterministic controls from lessons |
| `SimilarityResolver` | Reflex or DataHub | Discovers similar assets; live mode queries DataHub via `searchAcrossEntities`; synthetic mode uses in-memory datasets |
| `ApprovalService` | Reflex | Enforces mandatory human approval gates (root cause + control) |
| `LessonExtractor` | Reflex | Extracts structured lessons from incident templates |
| `OwnershipResolver` | Reflex | Classifies ownership and proposes replacement candidates |
| `DataHubReadClient` | DataHub | Thin GraphQL wrapper for reads (incidents, lineage, ownership) |
| `DataHubWriteClient` | DataHub | Thin GraphQL/mutation wrapper for writes (incidents, ownership, tags, structured properties) |

## 6. MVP scenarios

### Scenario 1: Duplicate rows caused by non-idempotent retries

A finance ingestion pipeline retries after a partial failure and inserts duplicate transactions. Reflex generates a `UniquenessControl` on `transaction_id`, backtests it against 8 historical snapshots, and detects duplicates at the exact timestamps where they occurred. After approval, the control is published and then detects analogous duplicates on a similar asset.

**Control type**: `UniquenessControl` — deterministic SQL-like definition: `GROUP BY cols HAVING COUNT(*) > 1`

### Scenario 2: Orphaned ownership after employee offboarding

An employee is deactivated but remains TECHNICAL_OWNER of critical datasets. Reflex identifies all affected assets, proposes active domain owners as replacements, preserves historical ownership records, and backtests the `ActiveOwnershipControl` against ownership snapshots. After approval, a later inactive-owner case is detected.

**Control type**: `ActiveOwnershipControl` — checks that at least N active owners exist per asset

## 7. Quick start

```bash
# Clone and install
git clone <YOUR_PUBLIC_REPOSITORY_URL>
cd datahub-reflex
pip install -e ".[dev]"

# Seed synthetic historical data (no DataHub required)
python scripts/seed_history.py

# Run unit and evaluation tests (no DataHub required)
python -m pytest tests/unit/ tests/evaluation/ -v

# Run synthetic scenarios (no DataHub required)
python examples/duplicate_rows/run_scenario.py
python examples/orphaned_ownership/run_scenario.py

# Optional: Start the tested DataHub OSS Quickstart for live integration
python -m datahub docker quickstart

# Seed the minimum real DataHub graph for the duplicate-rows demo
python scripts/seed_live_datahub.py seed
python scripts/seed_live_datahub.py verify

# Run live integration tests (requires DataHub)
python -m pytest tests/integration/ -v

# Verify Step 3: full Reflex/DataHub loop
python scripts/verify_step3.py

# Run deterministic pre-submission checks (no external writes)
python scripts/audit_submission.py

# Clean isolated test artifacts from DataHub
python scripts/reset_test_data.py

# Remove only the live-seed manifest (remote metadata is intentionally preserved)
python scripts/seed_live_datahub.py reset

# Run everything except live DataHub tests
python -m pytest tests/ -v -m "not requires_datahub"
```

### Synthetic mode vs Live DataHub mode

Reflex can operate in two similarity-resolution modes:

| Mode | Flag | Similarity Source | Requires DataHub |
|------|------|-------------------|-----------------|
| **Synthetic** (default) | `use_live_datahub=False` | In-memory datasets from `reflex.datahub.environment` | No |
| **Live DataHub** | `use_live_datahub=True` | Live DataHub via `searchAcrossEntities` (6 signals) | Yes |

Both modes share the same 6-signal resolution logic: same_domain, shared_tags, compatible_schema, append_only_vulnerability, similar_lineage, no_existing_control.

## 8. Data model

Core domain models (Pydantic v2, frozen):

- **ReflexLesson** — Confirmed root cause, failure pattern, trigger, vulnerable characteristics, propagation scope
- **ReflexControl** — Deterministic control definition, backtest results, approval state, version
- **BacktestResult** — Per-snapshot: would_have_detected, true/false positives, evidence
- **SimilarAssetCandidate** — Asset matched by domain, schema, lineage, tags signals with confidence
- **ReflexCoverage** — Which assets are covered by which controls
- **ControlExecutionResult** — Live execution with violation count and samples
- **RootCauseApproval / ControlApproval** — Persisted decisions with approver, timestamp, provenance

## 9. Backtesting model

Reflex owns control execution. DataHub OSS stores results.

Metrics per control: True Positives, False Positives, True Negatives, False Negatives, Precision, Recall, False Positive Rate, F1 Score.

**Publication gates**: Recall ≥ 100% on known incidents, FPR ≤ 10%, execution success.

## 10. Human approval model

Two mandatory gates enforced by `ApprovalService`:

1. **Root-cause approval** — Must be `APPROVED` or `REVISED` before lesson extraction. Raises `PipelineApprovalRequired` if no explicit decision exists.
2. **Control approval** — After backtesting: must be `APPROVED` or `MODIFIED`. No publication without approval.

All decisions persisted as JSON files with approver identity, timestamp, and provenance. Test mode (`non_interactive_test_mode=True`) auto-approves both gates for automated testing.

## 11. DataHub OSS versus Cloud boundaries

| Capability | OSS (v1.5.0.6) | Cloud | Reflex |
|-----------|-----|-------|--------|
| Assertion execution | ❌ | ✅ | Reflex owns execution |
| Assertion definition storage | ⚠️ `upsertAssertion` removed | ✅ | Reflex stores locally |
| Assertion run event storage | ⚠️ REST endpoint 404s | ✅ | Reflex stores locally |
| Incident CRUD (`raiseIncident`) | ✅ | ✅ | Used directly |
| Structured properties | ✅ (>= 0.14) | ✅ | Used for coverage |
| Ownership updates | ✅ | ✅ | Only after approval |
| Search across entities | ✅ | ✅ | Used for candidate discovery |

**Reflex never calls `run_assertion()`.** Verified by automated test.

## 12. Evaluation methodology

Three baselines compared against Reflex:

- **Baseline A** (text-only): Incident text without DataHub graph
- **Baseline B** (read-only DataHub): Queries DataHub but cannot backtest or publish
- **Reflex**: Full loop with backtesting, approval, publication, future detection

Fixed random seeds, versioned datasets, synthetic scenarios. Results in `examples/evaluation/summary.json`.

## 13. Results

| Metric | Duplicate Rows | Orphaned Ownership |
|--------|---------------|-------------------|
| Precision | 100% | 100% |
| Recall | 100% | 100% |
| FPR | 0% | 0% |
| Future detection | ✅ | ✅ |
| Publication | ✅ | ✅ |
| History preserved | N/A | ✅ |

Evaluation data is synthetic. Results do not imply production generalization.

## 14. Limitations

1. Synthetic historical data for backtesting (JSON files, not DataHub timeseries).
2. Two control families (`UniquenessControl`, `ActiveOwnershipControl`). No generic rule language.
3. Template-based lesson extraction (MVP). LLM interface available.
4. Live DataHub integration tests exist but require running DataHub instance.
5. File-based approval with `PipelineApprovalRequired` gate. The UI exposes both approval gates interactively; non-test CLI mode blocks without explicit decision files.
6. Assertion definitions and run events are Reflex-owned in OSS v1.5.0.6 (endpoints removed/unavailable).
7. Ownership remediation is executed only after explicit approval in the live UI path; there is no autonomous remediation.

See [docs/limits.md](docs/limits.md) for the full list.

## 15. Security and governance

- No automatic remediation or metadata deletion
- Approval audit trail (identity + timestamp)
- No secrets in repository (`.env.example`)
- Synthetic data only — no real user or transaction data

## 16. Open-source contributions

Candidate upstream DataHub contributions (independent from Reflex):

1. Assertion execution documentation — clarify OSS vs Cloud boundaries
2. Incident helpers — `DataHubGraph` convenience methods
3. MCP incident tools — agent-based incident management

## 17. Repository structure

```
datahub-reflex/
├── LICENSE (Apache 2.0)
├── README.md
├── docker-compose.yml
├── pyproject.toml
├── reflex/           # Core package
│   ├── core/         # Pipeline, approval, extraction, similarity
│   ├── datahub/      # Read/write clients, environment
│   ├── backtesting/  # ReflexBacktester
│   ├── controls/     # UniquenessControl, ActiveOwnershipControl
│   └── models/       # Pydantic domain models
├── scripts/          # seed, reset, seed_history
├── examples/         # Scenario runs, evaluation
├── tests/            # Unit, integration, evaluation
├── spikes/           # Phase 1 write-path verification
└── docs/             # Architecture, data model, scope, limitations
```

## 18. Demo UI

Launch the single-page demo interface:

```bash
python -m ui.app
# Open http://localhost:5000
```

Shows all 9 steps of the Reflex loop with real application state:
1. Resolved incident details
2. Human-confirmed root cause
3. Structured lesson
4. Proposed preventive control (Reflex-owned execution)
5. Similar assets with explicit similarity signals (labeled synthetic or live, depending on mode)
6. Backtest metrics (SYNTHETIC HISTORICAL DATA labeled)
7. Interactive approval actions (approve/reject at both mandatory gates)
8. DataHub publication status (REFLEX-OWNED or DataHub OSS)
9. Analogous future incident detection results

Zero build step. Single HTML file. Flask backend with JSON API.

## 19. Hackathon Demo

One-command demo showing both scenarios:

```bash
python scripts/demo.py        # CLI demo (both scenarios)
python scripts/demo.py --ui   # CLI + launch UI
python scripts/demo.py --ui-only  # UI only
```

Outputs all 9 steps for both scenarios with clear labeling of synthetic data, Reflex-owned execution, and DataHub OSS boundaries.

## 20. Video Storyboard

A 2:58 video storyboard is available in [docs/storyboard.md](docs/storyboard.md) covering:
- 0:00-0:20 Problem and resolved incident
- 0:20-0:40 Human root-cause approval
- 0:40-1:05 Lesson and similar assets
- 1:05-1:30 Backtest (100% precision, 0 false positives)
- 1:30-1:50 DataHub write-back (OSS boundaries)
- 1:50-2:15 Analogous failure detected
- 2:15-2:35 Ownership scenario
- 2:35-2:55 Accurate conclusion (what Reflex is and is NOT)
- 2:55-3:00 Repository and license

See the final [submission checklist](docs/submission_checklist.md) before uploading to Devpost.
Publishing instructions are in [docs/publish.md](docs/publish.md).
The ready-to-submit Devpost text is in [docs/devpost_submission.md](docs/devpost_submission.md).

## 21. Roadmap

Current implementation:
- ✅ Reflex-owned backtesting engine
- ✅ Mandatory human approval gates (non-test mode blocks without explicit decision)
- ✅ Live DataHub similarity resolution (`DataHubSimilarityResolver`, 6 signals)
- ✅ Explicit synthetic mode for offline development (live mode never silently falls back)
- ✅ Live integration tests (8 DataHub integration checks)
- ✅ Single-page UI (Flask + inline HTML, zero build step)
- ✅ 86 tests passing (offline/UI/evaluation), 8 requiring live DataHub

Future work:
- LLM-based lesson extraction from arbitrary incident descriptions
- Additional control families beyond uniqueness and active ownership
- Multi-user approval workflow and authentication
- DataHub timeseries integration for backtesting (replace JSON snapshots)
- CI pipeline for live integration tests with automated DataHub instance

## 19. License

Apache 2.0. See [LICENSE](LICENSE).
