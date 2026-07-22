# DataHub Reflex — Product Development Backlog

## Product target

DataHub Reflex is an incident-to-control compilation product for data platform
teams that use DataHub.

It converts a human-confirmed incident lesson into a validated, backtested,
human-approved preventive control that can be propagated to similar DataHub
assets.

The product is not:

- a generic chatbot;
- a data-observability replacement;
- a self-healing platform;
- an autonomous remediation system;
- a generic multi-agent framework.

## Current verified state

- Public repository on GitHub.
- Two MVP control families:
  - duplicate rows / `UniquenessControl`;
  - orphaned ownership / `ActiveOwnershipControl`.
- Live DataHub OSS reads and supported writes.
- Reflex-owned control execution and backtesting.
- Explicit human approval gates in the UI path.
- Synthetic and live modes are separated.
- 90 offline/UI/evaluation tests pass.
- 8 live DataHub integration tests pass.
- Negative cases are included in the benchmark.
- Two clean-checkout rehearsals pass.
- Public Devpost draft and submission checklist exist.

## Product gaps

The following capabilities are not yet product-complete:

1. Real LLM API integration for lesson extraction.
2. Durable product-facing API for incidents, lessons, controls, approvals, and
   coverage.
3. Persistent approval and provenance storage beyond the current MVP files.
4. Production identity and multi-user authorization.
5. Production historical data connectors beyond synthetic JSON snapshots.
6. A focused upstream DataHub contribution.
7. Final video and Devpost submission.

The hackathon MVP must not attempt to solve all seven as production features.
The critical path is item 1, followed by trust, reproducibility, and release
quality.

---

## P0 — LLM API integration

### P0.1 Provider abstraction

Create a provider-neutral interface:

```python
class LLMClient(Protocol):
    async def extract_lesson(
        self,
        incident: IncidentInput,
    ) -> LessonExtraction:
        ...
```

Requirements:

- keep the existing deterministic extractor as an offline implementation;
- add an API-backed implementation;
- select the implementation through configuration;
- do not place provider-specific code in pipeline orchestration;
- make the API client injectable in tests.

Suggested modes:

```text
REFLEX_LLM_MODE=deterministic
REFLEX_LLM_MODE=api
```

Acceptance criteria:

- both modes return the same validated domain model;
- deterministic mode requires no network or API key;
- API mode fails with a clear error when credentials are missing;
- the pipeline never silently falls back from API mode to deterministic mode.

### P0.2 Structured LLM output

The LLM must return a schema-constrained lesson, not free-form prose.

Required fields:

- failure category;
- trigger;
- vulnerable characteristics;
- proposed control type;
- target field or ownership rule;
- propagation scope;
- assumptions;
- limitations;
- confidence;
- evidence references.

Validate the result with Pydantic before it enters the pipeline.

Reject:

- unknown control types;
- missing target fields;
- unsupported propagation scope;
- malformed confidence values;
- claims without source evidence;
- arbitrary executable code.

### P0.3 LLM responsibility boundary

The LLM may:

- extract a proposed root cause;
- classify the incident pattern;
- propose a typed control;
- explain assumptions and limitations.

The LLM may not:

- publish to DataHub;
- mutate ownership;
- approve itself;
- execute controls;
- bypass backtesting;
- create arbitrary assertions;
- replace human root-cause confirmation.

The deterministic control synthesizer remains the only path from a lesson to
an executable MVP control.

### P0.4 Reliability and cost controls

Implement:

- timeout;
- bounded retry for transient API failures;
- clear authentication errors;
- maximum input size;
- maximum output size;
- per-run cost/token metadata where available;
- request identifier;
- prompt/template version;
- model identifier;
- redacted request/response logging.

Never log API keys, tokens, or raw sensitive incident content.

### P0.5 Testing

Add tests for:

- valid structured response;
- malformed JSON;
- schema validation failure;
- unsupported control type;
- timeout;
- API authentication failure;
- retry exhaustion;
- deterministic mode without network;
- API mode without silent fallback;
- prompt/model provenance.

The evaluation harness must be able to run entirely in deterministic mode.

---

## P0 — Product trust and approval

### Trust requirements

Every generated lesson must show:

- source incident;
- human-confirmed root cause;
- LLM/provider mode;
- model and prompt version;
- evidence used;
- assumptions;
- limitations;
- approval state;
- approver and timestamp.

### Approval requirements

Keep two explicit gates:

1. root-cause approval;
2. control/publication approval.

The product must block on:

- pending approval;
- rejected root cause;
- rejected control;
- failed backtest;
- insufficient historical coverage.

### Product audit trail

Define a durable record for:

- incident;
- lesson;
- control;
- backtest;
- approval;
- publication;
- future detection.

The hackathon may keep JSON persistence, but each record must have a stable
identifier, version, timestamp, and provenance.

---

## P0 — DataHub product integration

Keep DataHub structurally necessary.

### Reads

Use DataHub APIs for:

- incident discovery;
- asset search;
- schemas;
- domains;
- tags;
- lineage;
- ownership;
- existing coverage metadata.

### Writes

Use supported OSS operations for:

- incidents;
- ownership after approval;
- tags;
- structured properties;
- supported metadata aspects.

### OSS boundary

Do not attribute these to DataHub OSS v1.5.0.6:

- native assertion execution;
- native assertion scheduling;
- unavailable assertion GraphQL mutations;
- unavailable assertion REST run endpoint.

Reflex owns execution and backtesting for the MVP.

### Similar-asset propagation

Every candidate must expose:

- matched signals;
- missing signals;
- score;
- source DataHub entities;
- selected/rejected state;
- control coverage state.

No opaque embedding-only decision is allowed in the MVP.

---

## P1 — Product API surface

Expose a stable application API over the current orchestration layer.

Suggested endpoints:

```text
POST /incidents/{incident_id}/analyze
POST /incidents/{incident_id}/root-cause/approve
GET  /lessons/{lesson_id}
POST /lessons/{lesson_id}/backtest
GET  /controls/{control_id}
POST /controls/{control_id}/approve
POST /controls/{control_id}/publish
GET  /assets/{asset_id}/coverage
GET  /runs/{run_id}
```

Requirements:

- typed request and response models;
- stable error model;
- idempotency for approval and publication requests;
- correlation/request ID;
- no direct arbitrary GraphQL passthrough;
- no mutation without approval;
- API behavior identical to the UI workflow.

The API layer must not become a second implementation of business logic.
It should call the same services used by the UI.

---

## P1 — Persistence and deployment readiness

For the hackathon, keep the implementation small but define the migration
path from files to durable storage.

Required design decisions:

- lesson storage format;
- control versioning;
- approval record format;
- backtest result storage;
- publication provenance;
- replay/idempotency behavior;
- retention of rejected proposals.

Do not introduce a database unless it is required to demonstrate a product
workflow. A documented repository-backed persistence layer is acceptable for
the MVP if its limitations are explicit.

---

## P1 — Evaluation as product evidence

Maintain two baselines:

- text-only incident agent;
- read-only DataHub agent.

Measure:

- control executability;
- similar-asset selection;
- backtest ability;
- publication ability;
- recurrence detection;
- false-positive rate;
- approval acceptance;
- time-to-protection.

Record:

- dataset version;
- Git commit;
- prompt version;
- model identifier;
- control version;
- random seed;
- execution mode;
- raw JSON outputs.

Never present synthetic results as production performance.

---

## P1 — Security and operating model

Before product claims are expanded, document:

- API key handling;
- sensitive incident data handling;
- DataHub token handling;
- least-privilege write permissions;
- approval identity;
- audit log retention;
- ownership mutation safeguards;
- failure and retry behavior;
- manual rollback procedure.

No secrets or real customer data belong in the repository or demo fixtures.

---

## P2 — Upstream contribution

Keep the scope focused on one contribution first:

1. document the OSS/Cloud assertion execution boundary;
2. optionally prepare generic incident helpers for `DataHubGraph`;
3. defer MCP write tools until after the hackathon.

Use only these statuses:

- researched;
- patch prepared locally;
- submitted;
- merged;
- deferred.

Never claim submitted or merged without an upstream URL.

---

## Release and submission

Before recording:

- freeze product behavior;
- run two clean-checkout rehearsals;
- verify live and synthetic labels;
- verify both approval gates;
- verify analogous incident payoff;
- verify README commands;
- verify repository URL;
- remove stale claims.

Record the video only during the final release window. Do not use the video as
the primary validation mechanism.

Before Devpost submission:

- public video URL works without authentication;
- repository URL is correct;
- category is `Agents That Do Real Work`;
- description matches implemented behavior;
- limitations are included;
- no placeholder URLs remain.

## Priority order for the remaining 20 days

1. LLM API provider abstraction and structured lesson extraction.
2. Trust, provenance, and approval correctness.
3. Product API boundary over the existing services.
4. Evaluation repeatability and cost/error reporting.
5. Security and repository quality.
6. One focused upstream contribution.
7. Final rehearsal, video, and Devpost submission.

Do not add a new scenario or control family before all P0 items are complete.

## Immediate next task

Implement the provider-neutral `LLMClient` abstraction with deterministic and
API-backed modes, structured Pydantic output, and tests that prove API mode
never silently falls back to deterministic mode.
