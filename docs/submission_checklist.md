# Hackathon Submission Checklist

## Repository

- [ ] Publish the repository publicly and record its URL
- [x] Local Git history prepared on `main` (see [publish instructions](publish.md))
- [x] One-command guarded GitHub publication script available
- [x] Apache 2.0 license at repository root
- [x] No secrets committed
- [x] `.env.example` present
- [x] README documents OSS versus Cloud boundaries
- [x] `scripts/seed_live_datahub.py` documents live setup
- [x] `scripts/audit_submission.py` passes the local artifact/security audit
- [x] Devpost submission draft prepared in [docs/devpost_submission.md](devpost_submission.md)

## Functional verification

- [x] Duplicate-row synthetic E2E passes
- [x] Duplicate-row live DataHub E2E passes
- [x] Orphaned-ownership synthetic E2E passes
- [x] Orphaned-ownership live DataHub E2E passes
- [x] Both approval gates are explicit in the UI path
- [x] DataHub OSS assertion execution is never called
- [x] Live resolver never silently falls back to synthetic data

## Evaluation

- [x] Baseline A and Baseline B outputs generated
- [x] Duplicate-row results saved in `examples/evaluation/duplicate_rows_results.json`
- [x] Ownership results saved in `examples/evaluation/ownership_results.json`
- [x] Summary saved in `examples/evaluation/summary.json`
- [x] Synthetic-data limitation stated clearly

## Before submission

- [ ] Record public demo video under three minutes
- [ ] Verify the video URL is public
- [ ] Run the demo from a clean checkout
- [ ] Re-run the full test commands and record outputs
- [ ] Confirm Devpost category: `Agents That Do Real Work`
- [ ] Add final repository URL and video URL to the Devpost submission

## Known honest limitations

- Backtesting history is synthetic JSON, not DataHub timeseries.
- Lesson extraction uses deterministic MVP templates.
- OSS stores Reflex metadata and incidents; Reflex executes controls.
- Remote DataHub reset is intentionally soft and preserves emitted metadata.
