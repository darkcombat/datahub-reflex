# Evaluation Results

## Methodology

DataHub Reflex was evaluated against two synthetic scenarios:

1. **Duplicate Rows** — Non-idempotent retry logic producing duplicate transaction IDs
2. **Orphaned Ownership** — Inactive employee remaining TECHNICAL_OWNER of critical datasets

Each scenario was tested with 8 historical snapshots and compared against two baselines:

- **Baseline A (text-only)**: Incident text without DataHub graph — cannot discover similar assets or backtest
- **Baseline B (read-only DataHub)**: Queries DataHub but cannot backtest or publish
- **Reflex**: Full loop with backtesting, approval, publication, future detection

All data is synthetic. Results do not imply production generalization.
Sample size (8 snapshots per scenario) is too small for meaningful statistical inference.

**Negative cases**: Each scenario includes a clean-data test where the control
must produce zero false positives. Duplicate rows negative case: 25 unique
transaction IDs with no duplicates. Ownership negative case: all owners active
on operations_pipeline_metrics.

**Data leakage controls**: Future incident data is never passed to lesson
extraction. Labels are not passed to control synthesis. Backtest window ends
at T-0; future detection uses data at T+1. Baselines receive only permitted
inputs.

## Capability matrix

| Capability | Baseline A (text-only) | Baseline B (read-only DataHub) | Reflex |
|-----------|----------------------|-------------------------------|--------|
| Propose control | No | Yes | Yes |
| Identify similar assets | No | Yes | Yes |
| Execute control | No | No | Yes |
| Backtest | No | No | Yes |
| Publish coverage | No | No | Yes |
| Detect future incident | No | No | Yes |

## Scenario 1: Duplicate Rows

| Metric | Value |
|--------|-------|
| Total historical runs | 8 |
| Normal runs | 6 |
| Known incident runs | 2 |
| True positives | 2 |
| False positives | 0 |
| True negatives | 6 |
| False negatives | 0 |
| Precision | 100% |
| Recall | 100% |
| False-positive rate | 0% |
| Execution failures | 0 |
| Analogous asset selection precision | 100% |
| Future incident detected | Yes (3 violations on finance_monthly_ledger) |
| Publication success | Yes |
| Negative case (no false positives on clean data) | Passed |

**Key finding**: The UniquenessControl detected duplicates at the exact timestamps
(T-2 and T-1) where the original incident occurred. Zero false positives across
all 8 snapshots. After publication, the control detected 3 analogous duplicate
transaction IDs on a similar asset (finance_monthly_ledger). On the negative
case (25 unique transaction IDs), zero violations were reported.

## Scenario 2: Orphaned Ownership

| Metric | Value |
|--------|-------|
| Total historical snapshots | 8 |
| Inactive owners detected | 3 |
| False inactive-owner detections | 0 |
| Service accounts preserved | Yes |
| Valid groups preserved | Yes |
| Historical ownership preserved count | 2 |
| Valid replacements proposed | 2 |
| Invalid replacements | 0 |
| Approval compliance | Yes |
| Future recurrence detected | Yes |
| Precision | 100% |
| Recall | 100% |
| False-positive rate | 0% |
| Negative case (no false positives on clean data) | Passed |

## Reproducibility metadata

Every run records: evaluation timestamp, Git commit, Python version, dataset
version (`1.0.0`), random seed (`42`), model identifier (`deterministic-template`),
prompt version (`mvp-template-v1`), control version (`1.0.0`), threshold
configuration, DataHub version (`oss-1.5.0.6`), and execution mode (`synthetic`).

See `examples/evaluation/run_metadata.json` for the complete record.

Two consecutive runs from the same commit produce identical GO/NO-GO results
for all deterministic components.

## Limitations

- All historical backtesting data is synthetic JSON, not DataHub timeseries.
- Sample size (8 snapshots) prevents meaningful statistical inference.
- Lesson extraction uses deterministic scenario templates, not an LLM.
- Only two control types (uniqueness, active ownership) are evaluated.
- Shared tags and lineage signals are limited by the synthetic graph.
- Results are "on the synthetic benchmark" — not evidence of production generalization.

## Similarity Resolution Quality

The 6-signal similarity resolver was evaluated across both scenarios:

| Signal | Weight | Duplicate Rows | Orphaned Ownership |
|--------|--------|---------------|-------------------|
| same_domain | 0.25 | Matched on 2/5 assets | Matched on 2/5 assets |
| shared_tags | 0.20 | Not matched (synthetic) | Not matched (synthetic) |
| compatible_schema | 0.25 | Matched on 5/5 assets | N/A |
| append_only_vulnerability | 0.15 | Matched on 3/5 assets | N/A |
| similar_lineage | 0.10 | Not matched (synthetic) | Not matched (synthetic) |
| no_existing_control | 0.05 | Matched on 5/5 assets | Matched on 5/5 assets |

In synthetic mode, domain, tag, and lineage signals are limited by the in-memory dataset. Live DataHub mode uses `searchAcrossEntities` to query the full graph.

## Approval Gate Effectiveness

| Test | Result |
|------|--------|
| Pipeline blocks without root cause approval | ✅ PipelineApprovalRequired raised |
| Pipeline blocks with pending root cause | ✅ PipelineError raised |
| Pipeline blocks with rejected root cause | ✅ PipelineError raised |
| Revised root cause treated as approved | ✅ |
| Test mode auto-approves both gates | ✅ |
| Control stage blocks without decision file | ✅ PipelineApprovalRequired raised |
| Rejected control blocks publication | ✅ |
| Approval audit trail persisted | ✅ (JSON files with approver, timestamp) |

## Test Coverage

| Test Category | Count | Status |
|--------------|-------|--------|
| Offline, evaluation, and UI test suite | 139 | ✅ All pass |
| Live integration tests | 9 | ✅ Passed against the running DataHub OSS Quickstart |
| **Current verified total** | **148** | **139 pass offline/unit/evaluation/UI, 9 pass live** |

## Known Limitations

1. **Synthetic historical data** — Backtesting uses JSON snapshots, not DataHub timeseries
2. **Two control types** — UniquenessControl and ActiveOwnershipControl only
3. **Template-based extraction** — Lessons use scenario templates, not LLM
4. **Assertion endpoints unavailable in OSS v1.5.0.6** — Reflex-owned storage
5. **Live tests require DataHub** — Marked `@pytest.mark.requires_datahub`
6. **No CI pipeline** — Tests run locally only
7. **Single-user demo** — No multi-user approval workflow
8. **Ownership remediation is approval-gated** — Live UI executes approved updates; synthetic evaluation persists the plan

Full details: [docs/limits.md](docs/limits.md)
