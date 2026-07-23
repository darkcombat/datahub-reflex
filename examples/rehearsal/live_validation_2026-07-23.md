# Live Validation Report — 2026-07-23

This report records the live verification performed against DataHub OSS
Quickstart v1.5.0.6. No credentials or tokens are stored here.

## Environment

- DataHub GMS: `http://127.0.0.1:8080`
- Reflex: authenticated live container with `DATAHUB_GMS_URL` configured
- LLM mode: deterministic MVP mode
- DataHub mode: live; no synthetic fallback
- Approval gates: interactive and both required

## Duplicate rows workflow

1. Started the duplicate-row workflow against live DataHub.
2. Approved the human-confirmed root cause.
3. Resolved similar assets through live `searchAcrossEntities` discovery.
4. Backtested the `uniqueness` control on 8 snapshots.
5. Approved publication through the second human gate.
6. Published coverage metadata and control provenance.
7. Detected an analogous violation on a second asset.

Observed final state: `Run complete`, publication `APPROVED`, and future
incident detection complete.

## Orphaned ownership workflow

1. Reset the workspace and started the orphaned-ownership workflow.
2. Approved the human-confirmed offboarding root cause.
3. Compiled an `active_ownership` control.
4. Resolved live candidate assets and backtested on 8 snapshots.
5. Approved publication through the second human gate.
6. Published coverage metadata without deleting historical ownership.
7. Detected a later inactive-owner violation.

Observed final state: `Run complete`, publication `APPROVED`, and future
incident detection complete.

## Verification commands

```text
python -m pytest -q tests/unit tests/evaluation tests/ui
137 passed

python -m pytest -q tests/integration/test_live_datahub.py
9 passed

python scripts/audit_submission.py
SUBMISSION AUDIT: PASS
```

## OSS boundary verified

Reflex owns control execution and historical backtesting. DataHub OSS stores
supported metadata and incidents. The workflow does not claim native OSS
assertion execution and does not call the Cloud-only `run_assertion()` path.
