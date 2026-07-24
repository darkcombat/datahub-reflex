# DataHub Reflex — Devpost Submission Draft

## Title

DataHub Reflex

## Tagline

Turn a resolved data incident into a backtested preventive control that protects similar assets.

## Category

Agents That Do Real Work

## Description

Data teams usually fix an incident once, then leave the lesson in a ticket,
post-mortem, or an engineer's memory. A similar failure can happen later in a
different dataset or pipeline.

DataHub Reflex closes that loop. It takes a human-confirmed incident lesson,
compiles it into an executable preventive control, backtests the control on
historical snapshots, requires human approval, and propagates the approved
coverage to similar assets discovered through the DataHub graph.

The MVP demonstrates two patterns:

1. Duplicate finance rows caused by a non-idempotent retry. Reflex generates a
   `UniquenessControl` for `transaction_id`, evaluates it against historical
   snapshots, and detects a later analogous violation on another ledger.
2. Orphaned ownership after employee offboarding. Reflex finds inactive owners,
   proposes valid operational replacements, preserves historical ownership,
   and detects a later ownership problem.

The defining loop is:

```text
resolved incident
→ human-confirmed root cause
→ structured lesson
→ typed preventive control
→ Reflex-owned backtest
→ human approval
→ DataHub write-back
→ similar-asset coverage
→ analogous incident detection
```

## Why DataHub is essential

DataHub is not used as a generic prompt context source. Its graph provides the
lineage, domains, tags, schemas, ownership, incidents, and structured
properties needed to identify which other assets share the vulnerability.
Reflex writes coverage metadata, tags, incidents, and approved ownership
changes back to DataHub OSS.

DataHub OSS v1.5.0.6 does not expose native assertion execution or the
assertion endpoints used by DataHub Cloud. Reflex therefore owns control
execution and historical backtesting; this boundary is explicit in the code,
README, and demo. The project never calls `run_assertion()` and does not claim
to be self-healing.

## Technical implementation

- Python 3.11+
- Pydantic domain models
- Reflex-owned deterministic control executors and backtester
- DataHub GraphQL and metadata emitter integration
- Live six-signal similarity resolution
- Flask single-page demo UI
- Synthetic reproducible evaluation harness
- Mandatory approval gates in the UI path

## Evaluation

The repository contains reproducible synthetic results and two baselines:

- incident text only;
- read-only DataHub agent;
- full Reflex loop.

The verified local suite contains 139 offline/unit/evaluation/UI tests and 9 live
DataHub integration checks. The benchmark reports GO for both MVP scenarios
with negative cases. Synthetic results are not presented as production
generalization.

## Reproduce

```powershell
python -m pip install -e ".[dev]"
python scripts/audit_submission.py
python -m pytest -q tests/unit tests/evaluation tests/ui
python scripts/demo.py
```

For the live DataHub path:

```powershell
python -m datahub docker quickstart
python scripts/seed_live_datahub.py seed
python -m pytest -q tests/integration/test_live_datahub.py
```

## Links

- Repository: https://github.com/darkcombat/datahub-reflex
- Demo video: `<PUBLIC_VIDEO_URL>`
- Architecture: `docs/architecture.md`
- Evaluation: `docs/evaluation.md`
- Limitations: `docs/limits.md`

## Honest limitations

- Backtesting history is synthetic JSON in the MVP.
- Lesson extraction uses deterministic scenario templates.
- Only uniqueness and active-ownership controls are implemented.
- Human approval is required; there is no autonomous remediation.
- DataHub OSS stores supported metadata and incidents, while Reflex executes
  controls and backtests.
