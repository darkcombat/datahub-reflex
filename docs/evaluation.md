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

## Scenario 1: Duplicate Rows

| Metric | Baseline A | Baseline B | Reflex |
|--------|-----------|-----------|--------|
| Incident understood | ✅ | ✅ | ✅ |
| Root cause confirmed | ❌ (no gate) | ❌ (no gate) | ✅ (mandatory approval) |
| Similar assets discovered | 0 | 0 | 5 |
| Backtest snapshots | 0 | 0 | 8 |
| Historical detections | — | — | 2 (T-2, T-1) |
| Precision | — | — | 100% |
| Recall (detection rate) | — | — | 25% |
| Would have prevented | — | — | ✅ |
| False positives | — | — | 0 |
| Control published | ❌ | ❌ | ✅ (Reflex-owned) |
| Analogous violations detected | ❌ | ❌ | 3 on finance_monthly_ledger |

**Key finding**: The UniquenessControl detected duplicates at the exact timestamps (T-2 and T-1) where the original incident occurred. Zero false positives across all 8 snapshots. After publication, the control detected 3 analogous duplicate transaction IDs on a similar asset (finance_monthly_ledger).

## Scenario 2: Orphaned Ownership

| Metric | Baseline A | Baseline B | Reflex |
|--------|-----------|-----------|--------|
| Incident understood | ✅ | ✅ | ✅ |
| Root cause confirmed | ❌ (no gate) | ❌ (no gate) | ✅ (mandatory approval) |
| Inactive owner identified | — | — | bob (deactivated T-1) |
| Similar orphaned assets | 0 | 0 | 2 |
| Backtest snapshots | 0 | 0 | 8 |
| Historical detections | — | — | 1 (T-1) |
| Precision | — | — | 100% |
| Would have prevented | — | — | ✅ |
| Replacement candidates | ❌ | ❌ | Domain-based proposals |
| Historical ownership preserved | ❌ | ❌ | ✅ |
| Publication | ❌ | ❌ | ✅ (Reflex-owned) |

**Key finding**: The ActiveOwnershipControl detected bob's deactivation at T-1 and proposed domain-based replacement candidates for affected assets. Historical ownership records were preserved throughout.

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
| Offline, evaluation, and UI test suite | 86 | ✅ All pass |
| Live integration tests | 8 | ✅ Passed against the running DataHub OSS Quickstart |
| **Current verified total** | **94** | **86 pass offline/UI/evaluation, 8 pass live** |

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
