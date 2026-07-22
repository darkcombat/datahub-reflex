# Scope

DataHub Reflex converts a human-confirmed lesson from a resolved data incident into a backtested, executable preventive control that can be propagated to similar assets through the DataHub graph.

## In scope

- duplicate-row incident learning (UniquenessControl);
- orphaned-ownership incident learning (ActiveOwnershipControl);
- human-confirmed root cause with mandatory approval gate;
- deterministic control generation (SQL-like and ownership check);
- Reflex-owned historical backtesting against synthetic data;
- human approval workflow with `PipelineApprovalRequired` enforcement;
- live DataHub candidate discovery via `searchAcrossEntities` (6 signals);
- synthetic similarity resolution fallback (no DataHub required);
- DataHub write-back (incidents, ownership, tags, structured properties);
- assertion definitions and run events (Reflex-owned in OSS v1.5.0.6);
- analogous future incident detection;
- live integration tests against DataHub OSS (8 verified checks);
- test-mode bypass for automated testing (`non_interactive_test_mode`).

## Out of scope

- self-healing;
- autonomous remediation;
- generic multi-agent systems;
- real-time warehouse integration;
- production-grade identity management;
- distributed scheduling;
- breaking schema-change support;
- generic policy language;
- Slack, Jira, GitHub, or Airflow integrations unless strictly required later.

## MVP Scenarios

1. **Duplicate rows caused by non-idempotent retries** — UniquenessControl
2. **Orphaned ownership after employee offboarding** — ActiveOwnershipControl

## Out of Scope (Recorded for Backlog)

- Additional control types beyond uniqueness and active ownership
- Schema-change protection (stretch goal, not on critical path)
- Generic rule language
- LLM-based lesson extraction (MVP uses scenario templates; LLM interface available)
- Production-grade identity management for approval workflow
- Integration with non-DataHub metadata sources
- CI pipeline with automated DataHub instance
