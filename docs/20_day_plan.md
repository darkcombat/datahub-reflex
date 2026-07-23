# DataHub Reflex — 20-Day Execution Plan

This plan assumes the technical MVP is already public and verified. The video
is deliberately deferred until the product and the demo path are frozen.

## Current status — 2026-07-23

Completed through the rehearsal phase, plus the first product-API hardening pass:

- baseline and issue register;
- live DataHub hardening;
- evaluation improvements and negative cases;
- UI/UX review;
- repository and upstream-contribution analysis;
- two clean-checkout rehearsals.
- approval-gated Product API flow with regression coverage.

There are no BLOCKER or HIGH issues in the current register. The remaining
technical items are MEDIUM/LOW maintenance and must not destabilize the two
working MVP flows.

The product target is defined in [docs/product_brief.md](product_brief.md):
Reflex is an incident-to-control compilation product for DataHub-based data
platform teams, not a general-purpose agent demo.

## Objectives

Raise the submission from a working MVP to a credible, reproducible hackathon
entry without expanding beyond the two existing scenarios:

- duplicate rows caused by non-idempotent retries;
- orphaned ownership after offboarding.

## Days 1–2 — Freeze and baseline

- Freeze MVP scope and reject new control families.
- Tag the current public baseline.
- Run and save offline and live verification outputs.
- Create a short issue list with severity and owner.
- Remove stale claims, stale counts, and misleading demo output.

Exit gate: a clean checkout passes audit, offline tests, benchmark, and the
documented live checks.

## Days 3–6 — Live DataHub hardening

- Verify the live duplicate-row flow from seed to detected analogous incident.
- Verify the live ownership flow from inactive owner to approved replacement.
- Confirm every DataHub write is inspectable.
- Add failure-path tests for rejected root cause and rejected control approval.
- Document the OSS assertion boundary in the UI and README.

Exit gate: no hidden fallback, no Cloud-only call, and both approval gates are
visible in the live UI.

## Days 7–10 — Evaluation credibility

- Automate Baseline A and Baseline B execution where practical.
- Separate generated data, labels, and evaluation outputs.
- Add per-scenario reproducibility metadata.
- Report precision, recall, false-positive rate, coverage, and execution errors.
- Add one negative case for each control so the benchmark is not all-positive.

Exit gate: a judge can reproduce the reported results from a clean checkout and
the README does not imply production generalization.

## Days 11–13 — Product and demo UX

- Make the two approval gates visually unmistakable.
- Show source incident, lesson, control, backtest, write plan, and future detection.
- Show live versus synthetic mode explicitly.
- Show why each similar asset was selected.
- Remove generic dashboard elements and non-functional animations.

Exit gate: a reviewer understands the full loop without reading the source.

## Days 14–15 — Open-source contribution and repository polish

- Prepare the focused DataHub assertion-boundary documentation PR.
- Decide whether incident helper methods are mature enough for a second PR.
- Verify Apache 2.0 metadata, examples, clean-install instructions, and no secrets.
- Update the Devpost draft with measured final results only.

Exit gate: upstream contributions are either linked or honestly labeled as
prepared, never claimed as merged.

## Days 16–17 — Rehearsal

- Run the exact demo from a fresh clone.
- Time the two-minute-fifty-eight-second storyboard.
- Rehearse the OSS/Cloud explanation in one sentence.
- Capture the final command output and screenshots.
- Freeze code except for submission-blocking fixes.

Exit gate: the demo succeeds twice consecutively from a clean checkout.

## Day 18 — Record

- Record one continuous demo under three minutes.
- Show the human approval gate before publication.
- Show the analogous future incident as the payoff.
- Include the public repository URL and Apache 2.0 license.

## Day 19 — Submission review

- Upload the video publicly and verify playback without authentication.
- Replace all URL placeholders.
- Validate Devpost text against the implemented behavior.
- Confirm category: `Agents That Do Real Work`.

## Day 20 — Buffer and submit

- Use the buffer only for blocking defects or a failed upload.
- Do not add a new feature.
- Submit and save the final repository, video, and Devpost URLs.

## Priority rule

If time is lost, cut in this order:

1. open-source contribution breadth;
2. benchmark automation beyond the two scenarios;
3. visual polish;
4. never cut live verification, approval gates, reproducibility, or the
   analogous-incident payoff.

## Immediate next task

Perform a maintenance triage of the remaining MEDIUM issues. Decide whether
the Pydantic deprecation warning and the unused OSS GraphQL read methods can be
fixed safely without touching the critical live paths. If not, document them
and leave the MVP frozen. Do not begin recording the video until the manual
approval path has been rehearsed in the product UI.
