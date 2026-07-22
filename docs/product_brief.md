# DataHub Reflex — Product Brief

## Product definition

DataHub Reflex is an incident-learning product for data platform teams.

It turns a resolved data incident into a human-approved, backtested preventive
control and identifies the other DataHub assets that should receive the same
protection.

## Product promise

> Reduce the time between fixing a data incident and protecting the rest of the
> organization from the same failure pattern.

Reflex does not replace observability or incident detection. It addresses the
step after resolution: converting operational knowledge into reusable controls.

## Initial customer

The initial customer is a data platform or analytics engineering team that:

- already uses DataHub;
- operates multiple pipelines and datasets;
- has recurring data incidents;
- uses tickets or post-mortems to record incident lessons;
- lacks a reliable process for propagating those lessons to similar assets.

The first user is the data reliability engineer or platform owner responsible
for incident follow-up and data quality controls.

## Product workflow

```text
Incident resolved
       ↓
Human confirms root cause
       ↓
Reflex proposes a reusable lesson
       ↓
Reflex finds exposed DataHub assets
       ↓
Reflex generates and backtests a control
       ↓
Owner approves the protection plan
       ↓
Reflex publishes coverage and executes the control
       ↓
Future recurrence is detected and linked to the lesson
```

## Product wedge

The product wedge is not “AI for data quality”. It is:

> Incident-to-control compilation for organizations with a DataHub graph.

This is intentionally narrower than a general observability platform,
governance platform, or autonomous remediation system.

## MVP product capabilities

The MVP supports two control families only:

1. Uniqueness protection for duplicate rows after non-idempotent retries.
2. Active ownership protection after employee offboarding.

Both use the same product workflow and approval model. The control families
are implementation examples of the product loop, not the complete product
vision.

## Product requirements

### Required for a credible product

- persistent incident, lesson, control, approval, and coverage records;
- live DataHub graph reads;
- inspectable asset propagation reasons;
- deterministic control execution;
- historical backtesting;
- explicit human approval;
- audit trail and provenance;
- clear OSS versus Cloud boundaries;
- repeatable seed and reset workflow for development;
- measurable recurrence and false-positive outcomes.

### Deliberately out of scope

- autonomous remediation;
- generic policy language;
- arbitrary natural-language control generation;
- multi-agent orchestration;
- replacing DataHub Observability;
- replacing Jira, Slack, or incident-management platforms;
- production identity and enterprise SSO in the hackathon MVP.

## Product metrics

The most important product metrics are:

- time from incident resolution to approved protection;
- percentage of analogous assets covered;
- recurrence prevention rate;
- false-positive rate;
- percentage of generated controls accepted by an owner;
- percentage of controls that are executable;
- number of incidents linked to an existing lesson;
- completeness of the approval and provenance trail.

Hackathon metrics are synthetic and must not be presented as production
benchmarks.

## Product risks

### Trust

Teams will reject automatically generated protections that cannot explain their
scope, evidence, limitations, or expected false positives.

Mitigation: human approval, deterministic controls, backtesting, and explicit
similarity signals.

### Causality

DataHub metadata does not always contain the complete technical root cause.

Mitigation: require a human-confirmed root cause and treat Reflex as a compiler
and propagation layer, not an autonomous causal investigator.

### Adoption

The product is useful only if it fits the team's existing DataHub workflow.

Mitigation: keep DataHub central, produce inspectable artifacts, and avoid
requiring a new proprietary graph or incident platform.

## Product decision for the remaining hackathon time

Do not add features merely to look like a larger platform. Improve the trust
and repeatability of the existing incident-to-control workflow. The strongest
submission will show a narrow product that a data platform team could adopt,
not a collection of unrelated agent capabilities.
