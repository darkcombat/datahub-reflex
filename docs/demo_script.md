# DataHub Reflex - Judge Demo Script

Target duration: 2:45-2:55

The recording must use the interactive UI path. Do not use the offline CLI shortcut: it is test-mode only and would hide the two mandatory approval gates.

## Recording contract

The video must prove one complete causal chain:

```text
resolved incident
-> human confirms root cause
-> Reflex extracts a lesson
-> Reflex generates a typed control
-> history is backtested
-> human approves publication
-> supported artifacts are written to DataHub
-> an analogous failure is detected
```

Be explicit about the boundary:

- DataHub OSS stores incidents, ownership, tags, structured properties, and supported metadata.
- Reflex owns control execution and historical backtesting because native assertion execution is not available in DataHub OSS.
- No control or ownership change is published without human approval.

## Before recording

Run from a clean checkout:

```powershell
python scripts/audit_submission.py
python -m pytest -q tests/unit tests/evaluation tests/ui
python -m pytest -q tests/integration/test_live_datahub.py
```

Verify:

- the browser is on the Reflex UI;
- the UI shows the intended environment (`LIVE DATAHUB MODE` when recording the live path);
- the DataHub seed has already completed;
- browser console and server logs are clean;
- a fresh reset has been performed;
- no token, password, or private URL is visible in the recording.

If the live environment is not stable, record the reproducible synthetic UI path and label every synthetic artifact clearly. Never imply that synthetic history is production data.

## Shot list and narration

### 0:00-0:15 - The problem

Screen: Reflex landing page, before starting a run.

Say:

> Data teams resolve incidents, but the lesson usually remains in a ticket or post-mortem. Reflex turns an approved lesson into reusable protection for similar assets.

Do not mention self-healing or autonomous remediation.

### 0:15-0:32 - Start with a resolved incident

Screen action:

1. Select **Duplicate rows**.
2. Click **Start analysis**.

Show the first workflow card and the incident title.

Say:

> This is a resolved finance incident: a retry after partial failure inserted duplicate transaction IDs. DataHub provides the incident and the affected asset.

Pause until the workflow stops at **Human-confirmed root cause**.

### 0:32-0:50 - Human approval gate

Screen action:

1. Read the proposed root cause.
2. Click **Approve root cause**.

Say:

> Reflex does not treat an LLM or template output as authoritative. A human confirms the root cause before the system can learn from it.

Show that the next steps become available only after approval.

### 0:50-1:10 - Compile the lesson

Screen: structured lesson, failure pattern, and preventive control.

Say:

> The confirmed incident is compiled into a structured lesson: a non-idempotent retry on an append-only pipeline, protected by a uniqueness control on `transaction_id`.

Point out:

- failure category;
- vulnerable characteristic;
- control type;
- target field;
- limitations or assumptions.

### 1:10-1:28 - Explain propagation

Screen: similar assets and their signals.

Say:

> Reflex does not copy the control blindly. It selects candidate assets using inspectable signals from the DataHub graph: domain, schema, tags, lineage, ingestion characteristics, and missing coverage.

Open one candidate explanation and let the judge see why it was selected.

### 1:28-1:48 - Backtest the control

Screen: historical backtest metrics.

Say:

> The control is executed by Reflex against historical snapshots. Here we see the known incidents detected, normal runs accepted, and the false-positive rate. This is a Reflex-owned backtest; DataHub OSS does not execute native assertions.

Show the metric values and at least one historical run detail.

### 1:48-2:03 - Second human approval gate

Screen action:

1. Click **Approve publication**.

Say:

> A second human approval is required before coverage or remediation is published. The approval records the actor, time, decision, and scope.

Do not skip this gate.

### 2:03-2:22 - Write-back and provenance

Screen: publication step and, if possible, the corresponding DataHub entity or API response.

Say:

> Reflex writes the supported result back to DataHub: incident state, ownership or coverage metadata, tags, structured properties, and provenance. Assertion execution and backtesting remain explicitly owned by Reflex in OSS mode.

Show the exact publication status, not a generic success animation.

### 2:22-2:38 - The proof: analogous failure

Screen: future detection step.

Say:

> Now the same failure is injected into a similar ledger. Reflex runs the approved control and detects the analogous violation, producing evidence and a new incident instead of waiting for a human to rediscover the pattern.

Show the asset name, violation count, and evidence.

### 2:38-2:50 - Ownership scenario

Screen action:

1. Reset workspace.
2. Select **Orphaned ownership**.
3. Start analysis.
4. Approve root cause and publication.

Say:

> The same loop also works for governance: an offboarded owner is detected, historical ownership is preserved, a valid replacement is proposed, and the change is applied only after approval.

If time is tight, show this as a fast cut using a previously captured clean run. Do not claim steps that are not visible in the recording.

### 2:50-2:55 - Close

Say:

> DataHub helps teams understand what happened. Reflex makes an approved operational lesson executable, testable, and reusable across the organization.

Show the repository URL and the Apache 2.0 license.

## Claims the narrator must avoid

- "Reflex prevents all future incidents."
- "DataHub OSS runs the assertions."
- "The system automatically discovers the true root cause."
- "The product is self-healing."
- "The benchmark proves production performance."
- "The generated control is safe without review."

## Final capture checklist

- [ ] Duration is below three minutes.
- [ ] The root-cause approval is visible.
- [ ] The control-publication approval is visible.
- [ ] The backtest metrics are visible.
- [ ] At least one similarity explanation is visible.
- [ ] The analogous incident is genuinely detected.
- [ ] DataHub OSS and Reflex responsibilities are explained accurately.
- [ ] Synthetic data is labeled if used.
- [ ] No secrets or local filesystem paths are visible.
- [ ] The public repository URL is visible.
- [ ] The uploaded video is accessible in an incognito browser.

## Acceptance criterion

After watching the video once, a judge should be able to answer “yes” to all of these questions:

1. Is the incident lesson approved by a human?
2. Is the generated control executable and backtested?
3. Is DataHub necessary to find and cover similar assets?
4. Is the result written back with provenance?
5. Does the first incident lead to detection of a later analogous incident?

