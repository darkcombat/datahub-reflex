# Known Limitations — Rehearsal Phase (2026-07-23)

These limitations are honest and documented. None are BLOCKING.

## Synthetic data

- Backtesting history is synthetic JSON, not DataHub timeseries.
- Similar-asset resolution in synthetic mode uses in-memory datasets.
- Shared tags and lineage signals are limited by the synthetic graph.

## DataHub OSS v1.5.0.6

- upsertAssertion removed — assertion definitions are Reflex-owned.
- REST endpoint /openapi/assertions/v1/run returns 404 — run events are Reflex-owned.
- Ownership type normalized to NONE on read-back (OSS behavior).
- 7 DataHubReadClient methods use GraphQL fields absent in v1.5.0.6 (MED-03, not in critical path).

## Approval

- CLI demo uses test-mode auto-approval (labeled OFFLINE TEST MODE).
- UI path requires explicit human approval at both gates.

## MVP scope

- Two control types only: UniquenessControl, ActiveOwnershipControl.
- Template-based lesson extraction (LLM interface available but not default).
- No production identity management.

## Statistical

- Sample size (8 snapshots) is too small for meaningful statistical inference.
- Results are on the synthetic benchmark — not evidence of production generalization.
