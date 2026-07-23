"""Flask UI for DataHub Reflex — minimal single-page demo.

Provides:
  GET  /             — single-page UI (inline HTML)
  GET  /api/state    — current DemoRunner state as JSON
  POST /api/run      — start a new demo run
  POST /api/reset    — reset demo state
  POST /api/approve  — interactively approve (demo mode)

Stack: Flask + inline HTML/CSS. Zero build step. Zero npm.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict
from pathlib import Path

from flask import Flask, jsonify, request

from ui.demo_runner import (
    DemoRunner,
    build_duplicate_rows_history,
    build_orphaned_ownership_history,
)
from reflex.api.routes import api_bp

app = Flask(__name__)
app.register_blueprint(api_bp)

# -- Global demo runner (single-user demo) --
_runner: DemoRunner | None = None


def _get_runner() -> DemoRunner:
    global _runner
    if _runner is None:
        lessons_dir = Path(os.environ.get("REFLEX_LESSONS_DIR", "./datasets"))
        use_live = os.environ.get("DATAHUB_GMS_URL", "").strip() != ""
        _runner = DemoRunner(lessons_dir=lessons_dir, use_live_datahub=use_live)
    return _runner


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


@app.get("/api/state")
def api_state():
    """Return current demo state as JSON."""
    runner = _get_runner()
    return jsonify(runner.to_dict())


@app.post("/api/run")
def api_run():
    """Start a new demo run. Expects JSON body with scenario and params."""
    runner = _get_runner()
    runner.reset()

    data = request.get_json(silent=True) or {}
    scenario = data.get("scenario", "duplicate_rows")
    live_manifest = Path("./datasets/live_seed_manifest.json")
    live_config = json.loads(live_manifest.read_text()) if runner.use_live_datahub and live_manifest.exists() else {}

    if scenario == "duplicate_rows":
        historical = build_duplicate_rows_history(days=8)
        incident_urn = live_config.get("incident", "urn:li:incident:reflex-demo-dup-rows-001")
        root_cause = "Non-idempotent retry logic in the ingestion pipeline caused duplicate inserts on partial failure."
        target = live_config.get("datasets", {}).get(
            "reflex_finance_daily_ledger",
            "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance.transactions,PROD)",
        )
        analogous = live_config.get("datasets", {}).get("reflex_finance_monthly_ledger")
        current_data = {analogous: build_duplicate_rows_history(days=8)[-2][1]} if analogous else None
        kwargs = {"uniqueness_columns": ["transaction_id"]}
    elif scenario == "orphaned_ownership":
        historical = build_orphaned_ownership_history(days=8)
        incident_urn = "urn:li:incident:reflex-demo-orphaned-001"
        root_cause = "Employee offboarding did not trigger ownership reassignment. Inactive owners remained on critical datasets."
        target = live_config.get("datasets", {}).get(
            "reflex_finance_daily_ledger",
            "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance.transactions,PROD)",
        )
        current_data = None
        kwargs = {}
    else:
        return jsonify({"error": f"Unknown scenario: {scenario}"}), 400

    async def _run():
        return await runner.run_full(
            incident_urn=incident_urn,
            scenario=scenario,
            human_confirmed_root_cause=root_cause,
            confirmed_by="demo-user@reflex",
            target_asset_urn=target,
            historical_data=historical,
            current_data=current_data,
            **kwargs,
        )

    state = asyncio.run(_run())
    return jsonify(asdict(state))


@app.post("/api/reset")
def api_reset():
    """Reset the demo runner to initial state."""
    runner = _get_runner()
    runner.reset()
    return jsonify({"status": "reset", "current_step": 0})


@app.post("/api/approve")
def api_approve():
    """Apply an explicit human approval to the pending demo step."""
    runner = _get_runner()
    data = request.get_json(silent=True) or {}
    decision = data.get("decision", "approved")
    state = asyncio.run(runner.apply_approval(
        decision=decision,
        approver=data.get("approver", "demo-user"),
        notes=data.get("notes", ""),
    ))
    return jsonify(asdict(state))


# ---------------------------------------------------------------------------
# Single-page UI (inline HTML — no template files needed)
# ---------------------------------------------------------------------------

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DataHub Reflex — Demo</title>
<style>
:root {
  --bg: #0d1117; --card: #161b22; --border: #30363d;
  --text: #c9d1d9; --muted: #8b949e; --accent: #58a6ff;
  --green: #3fb950; --red: #f85149; --amber: #d2991d;
  --reflex: #7c3aed; --datahub: #2563eb;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.5; }
header { padding: 1.5rem 2rem; border-bottom: 1px solid var(--border);
  display: flex; justify-content: space-between; align-items: center; }
header h1 { font-size: 1.25rem; }
header h1 span { color: var(--accent); }
.actions { display: flex; gap: 0.5rem; }
.btn { padding: 0.5rem 1rem; border-radius: 6px; border: 1px solid var(--border);
  background: var(--card); color: var(--text); cursor: pointer; font-size: 0.875rem; }
.btn:hover { border-color: var(--accent); }
.btn-primary { background: var(--accent); color: #fff; border-color: var(--accent); }
.btn-danger { border-color: var(--red); color: var(--red); }
main { max-width: 900px; margin: 0 auto; padding: 2rem; }
.scenario-select { display: flex; gap: 1rem; margin-bottom: 2rem; }
.scenario-card { flex: 1; padding: 1.25rem; border: 2px solid var(--border);
  border-radius: 8px; cursor: pointer; transition: border-color .2s; }
.scenario-card:hover, .scenario-card.active { border-color: var(--accent); }
.scenario-card h3 { font-size: 1rem; margin-bottom: 0.25rem; }
.scenario-card p { font-size: 0.8rem; color: var(--muted); }
.steps { display: flex; flex-direction: column; gap: 1rem; }
.step { padding: 1rem 1.25rem; border: 1px solid var(--border); border-radius: 8px;
  background: var(--card); border-left: 4px solid var(--border);
  opacity: 0.4; transition: opacity .3s, border-color .3s; }
.step.active { opacity: 1; border-left-color: var(--accent); }
.step.done { opacity: 1; border-left-color: var(--green); }
.step-header { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.5rem; }
.step-number { width: 28px; height: 28px; border-radius: 50%; display: flex;
  align-items: center; justify-content: center; font-size: 0.75rem; font-weight: 700;
  background: var(--border); }
.step.active .step-number { background: var(--accent); color: #fff; }
.step.done .step-number { background: var(--green); color: #fff; }
.step-title { font-weight: 600; font-size: 0.95rem; }
.step-detail { font-size: 0.85rem; color: var(--muted); padding-left: 2.5rem; }
.step-detail strong { color: var(--text); }
.badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 12px;
  font-size: 0.7rem; font-weight: 600; margin-left: 0.5rem; }
.badge-reflex { background: var(--reflex); color: #fff; }
.badge-datahub { background: var(--datahub); color: #fff; }
.badge-synthetic { background: var(--amber); color: #000; }
.badge-ok { background: var(--green); color: #fff; }
.badge-err { background: var(--red); color: #fff; }
.metrics { display: flex; gap: 1rem; flex-wrap: wrap; margin-top: 0.5rem; }
.metric { background: rgba(255,255,255,0.04); padding: 0.5rem 0.75rem;
  border-radius: 6px; font-size: 0.8rem; }
.metric .val { font-size: 1.1rem; font-weight: 700; }
.signal-list { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 0.25rem; }
.signal { font-size: 0.75rem; padding: 0.2rem 0.5rem; border-radius: 4px; }
.signal.matched { background: rgba(63,185,80,0.15); color: var(--green); }
.signal.missed { background: rgba(248,81,73,0.12); color: var(--red); }
.asset-row { font-size: 0.8rem; padding: 0.35rem 0; border-bottom: 1px solid var(--border); }
.asset-row:last-child { border-bottom: none; }
.error-box { background: rgba(248,81,73,0.1); border: 1px solid var(--red);
  border-radius: 6px; padding: 1rem; color: var(--red); }
footer { text-align: center; padding: 2rem; font-size: 0.75rem; color: var(--muted);
  border-top: 1px solid var(--border); margin-top: 2rem; }

/* Product workspace layer: focused hierarchy, explicit states, keyboard-visible controls. */
:root { color-scheme: dark; --surface: #111827; --surface-2: #1b2332; --line: #263244; --text-strong: #f0f6fc; --blue-soft: rgba(88,166,255,.12); }
html { scroll-behavior: smooth; }
body { background: radial-gradient(circle at 50% -20%, #18243a 0, var(--bg) 42rem); overflow-x: hidden; }
button, select { touch-action: manipulation; }
button:focus-visible, select:focus-visible, a:focus-visible { outline: 3px solid rgba(88,166,255,.7); outline-offset: 3px; }
.skip-link { position: absolute; left: 1rem; top: -4rem; z-index: 20; padding: .65rem 1rem; border-radius: 6px; background: var(--accent); color: white; font-weight: 700; }
.skip-link:focus { top: 1rem; }
.app-header { max-width: 1180px; margin: 0 auto; padding: 1.1rem 2rem; background: transparent; border-bottom: 0; }
.app-header h1 { color: var(--text-strong); letter-spacing: -.02em; }
.app-header h1 span { color: #a78bfa; }
.app-header .actions { gap: .6rem; }
.app-header .actions { display: none; }
.app-header select { min-width: 150px; }
.header-status { display: flex; align-items: center; gap: .5rem; color: var(--muted); font-size: .75rem; }
.status-dot, .chip-dot { width: .45rem; height: .45rem; border-radius: 50%; background: var(--green); display: inline-block; box-shadow: 0 0 0 4px rgba(63,185,80,.12); }
.header-divider { width: 1px; height: 1rem; background: var(--border); margin: 0 .25rem; }
.product-hero, .scenario-picker, main { max-width: 1180px; margin-left: auto; margin-right: auto; }
.product-hero { display: flex; align-items: end; justify-content: space-between; gap: 2rem; padding: 2.5rem 2rem 1.5rem; }
.product-hero h2 { max-width: 700px; color: var(--text-strong); font-size: clamp(1.8rem, 4vw, 3rem); line-height: 1.08; letter-spacing: -.045em; text-wrap: balance; }
.hero-copy { max-width: 650px; margin-top: .85rem; color: var(--muted); font-size: 1rem; text-wrap: pretty; }
.eyebrow { color: #8b9bb4; font-size: .66rem; font-weight: 800; letter-spacing: .13em; margin-bottom: .45rem; }
.hero-chips { display: flex; flex-direction: column; align-items: flex-end; gap: .5rem; white-space: nowrap; }
.product-chip { display: inline-flex; align-items: center; gap: .55rem; padding: .45rem .7rem; border: 1px solid rgba(63,185,80,.32); border-radius: 999px; color: #b8f1c0; background: rgba(63,185,80,.08); font-size: .72rem; font-weight: 700; }
.muted-chip { border-color: var(--line); color: var(--muted); background: rgba(255,255,255,.03); }
.scenario-picker { padding: 1rem 2rem 1.25rem; }
.section-heading { display: flex; justify-content: space-between; align-items: end; gap: 1rem; margin-bottom: .8rem; }
.section-heading h2 { color: var(--text-strong); font-size: 1.05rem; letter-spacing: -.02em; }
.section-helper { color: var(--muted); font-size: .72rem; }
.scenario-cards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .8rem; }
.scenario-card { display: flex; align-items: center; gap: .75rem; width: 100%; min-height: 74px; padding: 1rem; border: 1px solid var(--line); border-radius: 10px; background: rgba(17,24,39,.82); color: var(--text); text-align: left; cursor: pointer; transition: border-color .18s ease, background-color .18s ease, transform .18s ease; }
.scenario-card:hover { border-color: #58749b; background: var(--surface-2); transform: translateY(-1px); }
.scenario-card.active { border-color: var(--accent); background: linear-gradient(135deg, var(--blue-soft), rgba(124,58,237,.1)); box-shadow: 0 0 0 1px rgba(88,166,255,.18); }
.scenario-card strong, .scenario-card small { display: block; }
.scenario-card strong { color: var(--text-strong); font-size: .86rem; }
.scenario-card small { margin-top: .2rem; color: var(--muted); font-size: .73rem; }
.scenario-icon { display: grid; place-items: center; width: 2rem; height: 2rem; flex: 0 0 auto; border-radius: 8px; color: #8ec5ff; background: rgba(88,166,255,.12); font-size: 1.2rem; }
.ownership-icon { color: #c4b5fd; background: rgba(124,58,237,.16); }
.scenario-check { display: none; margin-left: auto; color: var(--accent); font-weight: 800; }
.scenario-card.active .scenario-check { display: block; }
.workflow-actions { display: flex; justify-content: flex-end; gap: .6rem; padding: .2rem 0 1.2rem; }
.btn { transition: border-color .18s ease, background-color .18s ease, opacity .18s ease, transform .18s ease; }
.btn:hover { transform: translateY(-1px); }
.btn:disabled { cursor: wait; opacity: .65; transform: none; }
.btn-quiet { background: transparent; color: var(--muted); }
main { padding: 0 2rem 2rem; }
.workspace-grid { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(280px, .75fr); gap: 1rem; align-items: start; }
.progress-panel, .insight-panel { min-width: 0; padding: 1.15rem; border: 1px solid var(--line); border-radius: 12px; background: rgba(17,24,39,.74); box-shadow: 0 12px 34px rgba(0,0,0,.16); }
.compact-heading { align-items: center; margin-bottom: 1rem; }
.steps { gap: .7rem; }
.step { padding: .85rem 1rem; border-color: var(--line); background: rgba(27,35,50,.7); border-left-width: 3px; }
.step-detail { line-height: 1.55; }
.step-number { width: 25px; height: 25px; font-size: .7rem; }
.insight-panel { position: sticky; top: 1rem; }
.insights { min-height: 160px; }
.insight-callout { display: flex; gap: .7rem; align-items: flex-start; padding: .8rem; margin-bottom: .5rem; border: 1px solid rgba(88,166,255,.2); border-radius: 8px; background: rgba(88,166,255,.07); }
.insight-callout .empty-icon { flex: 0 0 auto; }
.insight-callout strong { color: var(--text-strong); font-size: .82rem; overflow-wrap: anywhere; }
.insight-callout p { margin-top: .2rem; color: var(--muted); font-size: .72rem; line-height: 1.5; }
.empty-insight { display: grid; gap: .6rem; place-items: start; padding: 1.2rem .2rem; color: var(--muted); font-size: .8rem; }
.empty-insight strong { color: var(--text-strong); font-size: .9rem; }
.empty-insight p { line-height: 1.6; }
.empty-icon { display: grid; place-items: center; width: 2rem; height: 2rem; border-radius: 8px; color: #c4b5fd; background: rgba(124,58,237,.16); }
.insight-stat { display: flex; justify-content: space-between; gap: 1rem; padding: .7rem 0; border-bottom: 1px solid var(--line); font-size: .78rem; }
.insight-stat:last-child { border-bottom: 0; }
.insight-stat span { color: var(--muted); }
.insight-stat strong { color: var(--text-strong); text-align: right; font-variant-numeric: tabular-nums; }
footer a { color: var(--accent); text-decoration: none; }
footer a:hover { text-decoration: underline; }
@media (max-width: 800px) { .app-header, .product-hero, .scenario-picker, main { padding-left: 1rem; padding-right: 1rem; } .app-header { align-items: flex-start; gap: .8rem; flex-direction: column; } .product-hero { align-items: flex-start; flex-direction: column; padding-top: 1.5rem; } .hero-chips { align-items: flex-start; flex-direction: row; flex-wrap: wrap; } .scenario-cards, .workspace-grid { grid-template-columns: 1fr; } .insight-panel { position: static; } .workflow-actions { justify-content: stretch; } .workflow-actions .btn-primary { flex: 1; } }
@media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto; } *, *::before, *::after { transition-duration: .01ms !important; animation-duration: .01ms !important; } }
</style>
</head>
<body>

<a class="skip-link" href="#main-content">Skip to main content</a>
<header class="app-header">
  <h1>DataHub <span>Reflex</span> — Demo</h1>
  <div class="actions">
    <select id="scenario" style="padding:0.5rem;border-radius:6px;background:var(--card);color:var(--text);border:1px solid var(--border)">
      <option value="duplicate_rows">Duplicate Rows</option>
      <option value="orphaned_ownership">Orphaned Ownership</option>
    </select>
    <button class="btn btn-primary" onclick="runDemo()">▶ Run Demo</button>
    <button class="btn btn-danger" onclick="resetDemo()">↺ Reset</button>
  </div>
</header>

<section class="product-hero" aria-labelledby="page-title">
  <div>
    <p class="eyebrow">DATA RELIABILITY WORKSPACE</p>
    <h2 id="page-title">Turn resolved incidents into reusable protection.</h2>
    <p class="hero-copy">Reflex extracts an approved lesson, validates a preventive control against history, and propagates coverage through your DataHub graph.</p>
  </div>
  <div class="hero-chips"><span class="product-chip"><span class="chip-dot"></span> Human approval required</span><span class="product-chip muted-chip">DataHub OSS compatible</span></div>
</section>

<section class="scenario-picker" aria-labelledby="scenario-heading">
  <div class="section-heading"><div><p class="eyebrow">START A WORKFLOW</p><h2 id="scenario-heading">Choose an incident pattern</h2></div><span class="section-helper">2 supported patterns</span></div>
  <div class="scenario-cards" role="radiogroup" aria-labelledby="scenario-heading">
    <button class="scenario-card active" id="scenario-card-duplicate_rows" role="radio" aria-checked="true" onclick="selectScenario('duplicate_rows')"><span class="scenario-icon" aria-hidden="true">↗</span><span><strong>Duplicate rows</strong><small>Non-idempotent retries in finance pipelines</small></span><span class="scenario-check" aria-hidden="true">✓</span></button>
    <button class="scenario-card" id="scenario-card-orphaned_ownership" role="radio" aria-checked="false" onclick="selectScenario('orphaned_ownership')"><span class="scenario-icon ownership-icon" aria-hidden="true">◉</span><span><strong>Orphaned ownership</strong><small>Offboarded users still own critical assets</small></span><span class="scenario-check" aria-hidden="true">✓</span></button>
  </div>
</section>

<main id="main-content">
  <div id="error" class="error-box" style="display:none"></div>
  <div class="workspace-grid">
    <section class="progress-panel" aria-labelledby="progress-heading">
      <div class="section-heading compact-heading"><div><p class="eyebrow">WORKFLOW</p><h2 id="progress-heading">Protection pipeline</h2></div><span id="progress-label" class="section-helper">Not started</span></div>
      <div class="steps" id="steps" aria-live="polite"></div>
    </section>
    <aside class="insight-panel" aria-labelledby="insight-heading">
      <div class="section-heading compact-heading"><div><p class="eyebrow">DECISION SUPPORT</p><h2 id="insight-heading">Run summary</h2></div></div>
      <div id="insights" class="insights" aria-live="polite"><div class="empty-insight"><span class="empty-icon" aria-hidden="true">✦</span><strong>Your run summary will appear here</strong><p>Start an analysis to inspect evidence, backtest results and approval state.</p></div></div>
    </aside>
  </div>
</main>

<footer>
  <span translate="no">DataHub Reflex</span> · Explicit human approval required · <a href="https://github.com/darkcombat/datahub-reflex" target="_blank" rel="noreferrer">View source</a>
  <span id="mode-footer"></span>
</footer>

<script>
const STEP_LABELS = [
  {num:1, title:"Resolved Incident", owner:"DataHub OSS"},
  {num:2, title:"Human-Confirmed Root Cause", owner:"Reflex"},
  {num:3, title:"Structured Lesson", owner:"Reflex"},
  {num:4, title:"Preventive Control", owner:"Reflex"},
  {num:5, title:"Similar Assets & Signals", owner:"Reflex"},
  {num:6, title:"Backtest Metrics", owner:"Reflex-owned execution"},
  {num:7, title:"Publication Approval", owner:"Reflex"},
  {num:8, title:"DataHub Publication", owner:"DataHub OSS"},
  {num:9, title:"Future Incident Detection", owner:"Reflex"},
];

let currentState = null;

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, function(ch) {
    return {'&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;'}[ch];
  });
}

function selectScenario(scenario) {
  const select = document.getElementById('scenario');
  if (select) select.value = scenario;
  ['duplicate_rows', 'orphaned_ownership'].forEach(function(name) {
    const card = document.getElementById('scenario-card-' + name);
    if (!card) return;
    const active = name === scenario;
    card.classList.toggle('active', active);
    card.setAttribute('aria-checked', active ? 'true' : 'false');
  });
}

function badge(owner) {
  if (owner.includes('Reflex')) return '<span class="badge badge-reflex">REFLEX</span>';
  if (owner.includes('DataHub')) return '<span class="badge badge-datahub">DATAHUB OSS</span>';
  return '';
}

function modeBadge(mode) {
  if (mode === 'live-datahub' || mode === 'LIVE DATAHUB MODE')
    return '<span class="badge" style="background:var(--datahub);color:#fff">LIVE DATAHUB</span>';
  return '<span class="badge badge-synthetic">SYNTHETIC</span>';
}

function renderSteps(state) {
  currentState = state;
  const container = document.getElementById('steps');
  const currentStep = state.current_step || 0;
  const hasError = !!state.error;
  const mode = state.mode_label || state.similarity_mode || 'synthetic';
  const progressLabel = document.getElementById('progress-label');
  if (progressLabel) progressLabel.textContent = state.is_complete ? 'Complete' : (currentStep ? 'Step ' + currentStep + ' of 9' : 'Not started');
  const connectionLabel = document.getElementById('connection-label');
  if (connectionLabel) connectionLabel.textContent = hasError ? 'Action required' : (state.is_complete ? 'Run complete' : (currentStep ? 'Analysis in progress' : 'Ready to run'));
  const headerMode = document.getElementById('header-mode');
  if (headerMode) headerMode.textContent = mode === 'live-datahub' || mode === 'LIVE DATAHUB MODE' ? 'Live DataHub' : 'Synthetic mode';

  // Mode banner
  let html = '<div style="padding:0.75rem 1rem;margin-bottom:1rem;border-radius:6px;' +
    'background:rgba(124,58,237,0.1);border:1px solid rgba(124,58,237,0.3);text-align:center;font-size:0.85rem">' +
    modeBadge(mode) +
    ' <span style="color:var(--muted);margin-left:0.5rem">| Historical data: ' +
    (state.backtest_data_provenance || 'SYNTHETIC (JSON snapshots)') +
    ' | Execution: Reflex-owned | Assertion storage: Reflex-owned (OSS v1.5.0.6)</span></div>';

  for (let i = 0; i < STEP_LABELS.length; i++) {
    const s = STEP_LABELS[i];
    const n = s.num;
    let cls = 'step';
    if (hasError && n > currentStep) cls += '';
    else if (n < currentStep) cls += ' done';
    else if (n === currentStep) cls += ' active';
    html += '<div class="' + cls + '">';
    html += '<div class="step-header"><div class="step-number">' + n + '</div>';
    html += '<div class="step-title">' + s.title + ' ' + badge(s.owner) + '</div></div>';
    html += '<div class="step-detail">' + renderDetail(n, state) + '</div>';
    html += '</div>';
  }

  if (hasError) {
    html += '<div class="step active"><div class="step-header" style="color:var(--red)">';
    html += '&#9888; Pipeline Error</div>';
    html += '<div class="step-detail" style="color:var(--red)">' + state.error + '</div></div>';
  }

  container.innerHTML = html;
  document.getElementById('mode-footer').innerHTML =
    '| ' + modeBadge(mode) + ' | Explicit human approval required |';

  const errBox = document.getElementById('error');
  if (hasError) { errBox.style.display = 'block'; errBox.textContent = 'Error: ' + state.error; }
  else errBox.style.display = 'none';
  renderInsights(state);
}

function renderInsights(state) {
  const target = document.getElementById('insights');
  if (!target) return;
  if (!state || !state.incident_title) {
    target.innerHTML = '<div class="empty-insight"><span class="empty-icon" aria-hidden="true">✦</span><strong>Your run summary will appear here</strong><p>Start an analysis to inspect evidence, backtest results and approval state.</p></div>';
    return;
  }
  const metrics = state.backtest_snapshots !== undefined ?
    '<div class="insight-stat"><span>Backtest coverage</span><strong>' + escapeHtml(state.backtest_snapshots) + ' snapshots</strong></div>' +
    '<div class="insight-stat"><span>Detection recall</span><strong>' + escapeHtml(((state.backtest_recall || 0) * 100).toFixed(0)) + '%</strong></div>' +
    '<div class="insight-stat"><span>False-positive rate</span><strong>' + escapeHtml(((state.backtest_fpr || 0) * 100).toFixed(0)) + '%</strong></div>' :
    '<div class="insight-stat"><span>Backtest</span><strong>Pending</strong></div>';
  const approval = state.approval_state ? escapeHtml(state.approval_state) : 'Pending';
  const coverage = state.detection_assets_checked !== undefined ? escapeHtml(state.detection_assets_checked + ' assets checked') : 'Not published';
  target.innerHTML = '<div class="insight-callout"><span class="empty-icon" aria-hidden="true">✦</span><div><strong>' + escapeHtml(state.incident_title) + '</strong><p>Reflex is compiling a reusable protection pattern.</p></div></div>' +
    '<div class="insight-stat"><span>Root cause</span><strong>' + (state.root_cause_approval_state === 'approved' ? 'Confirmed' : 'Needs review') + '</strong></div>' +
    metrics + '<div class="insight-stat"><span>Publication approval</span><strong>' + approval + '</strong></div>' +
    '<div class="insight-stat"><span>Future coverage</span><strong>' + coverage + '</strong></div>';
}

function renderDetail(n, state) {
  switch (n) {
    case 1: // Incident
      if (!state.incident_title) return '<em style="color:var(--muted)">Select scenario and run demo...</em>';
      return '<strong>' + state.incident_title + '</strong><br>' +
        '<span style="font-size:0.8rem;color:var(--muted)">' + state.incident_description + '</span><br>' +
        '<span style="font-size:0.75rem;color:var(--muted)">URN: <code>' + state.incident_urn + '</code></span>' +
        (state.incident_affected_asset ? '<br><span style="font-size:0.75rem;color:var(--muted)">Affected: <code>' + state.incident_affected_asset + '</code></span>' : '');
    case 2: // Root Cause
      if (!state.root_cause) return '<em style="color:var(--muted)">Awaiting root cause submission...</em>';
      var rcState = state.root_cause_approval_state || (state.current_step >= 2 ? 'approved' : 'pending');
      var rcColor = rcState === 'approved' ? 'var(--green)' : rcState === 'rejected' ? 'var(--red)' : 'var(--amber)';
      return '<strong>Root cause:</strong> ' + state.root_cause + '<br>' +
        '<span style="color:' + rcColor + ';font-weight:600">' + rcState.toUpperCase() + '</span>' +
        (state.confirmed_by ? ' &mdash; ' + state.confirmed_by : '') +
        (state.root_cause_approval_timestamp ? '<br><span style="font-size:0.7rem;color:var(--muted)">' + state.root_cause_approval_timestamp + '</span>' : '') +
        (rcState === 'pending' && !state.is_complete ? '<br><button class="btn" onclick="approve(\'approved\')" style="margin-top:0.5rem;font-size:0.75rem">&#10003; Approve Root Cause</button> <button class="btn btn-danger" onclick="approve(\'rejected\')" style="margin-top:0.5rem;font-size:0.75rem">&#10007; Reject</button>' : '');
    case 3: // Lesson
      if (!state.lesson_id) return '<em style="color:var(--muted)">Extracting lesson...</em>';
      return '<strong>' + state.lesson_title + '</strong> <code style="font-size:0.75rem">(' + state.lesson_id + ')</code><br>' +
        'Failure: <code>' + state.failure_pattern + '</code> | Confidence: ' + state.lesson_confidence + '<br>' +
        'Vulnerable: ' + ((state.vulnerable_characteristics||[]).join(', ') || 'none') +
        (state.lesson_assumptions && state.lesson_assumptions.length ? '<br><span style="font-size:0.7rem;color:var(--muted)">Assumptions: ' + state.lesson_assumptions.join('; ') + '</span>' : '') +
        (state.lesson_limitations && state.lesson_limitations.length ? '<br><span style="font-size:0.7rem;color:var(--muted)">Limitations: ' + state.lesson_limitations.join('; ') + '</span>' : '');
    case 4: // Control
      if (!state.control_id) return '<em style="color:var(--muted)">Synthesizing control...</em>';
      return '<span class="badge badge-reflex">REFLEX-OWNED EXECUTION</span><br>' +
        '<strong>Type:</strong> ' + state.control_type +
        (state.control_target_field ? ' | <strong>Target:</strong> <code>' + state.control_target_field + '</code>' : '') + '<br>' +
        '<strong>ID:</strong> <code style="font-size:0.7rem">' + state.control_id + '</code><br>' +
        '<strong>Definition:</strong> <code style="font-size:0.7rem;word-break:break-all">' + (state.control_definition||'').substring(0,200) + '</code>';
    case 5: // Similar Assets
      if (!state.similar_assets || state.similar_assets.length === 0)
        return '<em style="color:var(--muted)">Discovering similar assets...</em><br>' +
          modeBadge(state.similarity_mode) + ' <span style="font-size:0.75rem;color:var(--muted)">6-signal resolution</span>';
      var ahtml = modeBadge(state.similarity_mode) + ' <span style="font-size:0.75rem;color:var(--muted)">| Signals: same_domain, shared_tags, compatible_schema, append_only_vulnerability, similar_lineage, no_existing_control</span><br>';
      state.similar_assets.forEach(function(a) {
        var name = (a.asset_urn||'').split(',').pop()||a.asset_urn||'';
        ahtml += '<div class="asset-row"><strong>' + name + '</strong>';
        if (a.score !== undefined) ahtml += ' <span style="color:var(--muted)">score: ' + (typeof a.score === 'number' ? a.score.toFixed(2) : a.score) + '</span>';
        if (a.confidence) ahtml += ' <span style="color:var(--muted)">| ' + a.confidence + '</span>';
        if (a.rationale) ahtml += '<br><span style="font-size:0.75rem;color:var(--muted)">' + a.rationale + '</span>';
        if (a.matched_signals && a.matched_signals.length) ahtml += '<br><span style="font-size:0.7rem;color:var(--green)">Matched: ' + a.matched_signals.join(', ') + '</span>';
        if (a.missing_signals && a.missing_signals.length) ahtml += ' <span style="font-size:0.7rem;color:var(--red)">Missing: ' + a.missing_signals.join(', ') + '</span>';
        if (a.domain) ahtml += ' <span style="font-size:0.7rem;color:var(--muted)">| domain: ' + a.domain + '</span>';
        ahtml += '</div>';
      });
      return ahtml;
    case 6: // Backtest
      if (!state.backtest_snapshots)
        return '<em style="color:var(--muted)">Running backtest...</em>';
      var mhtml = '<span class="badge badge-reflex">REFLEX-OWNED EXECUTION</span> ' +
        '<span class="badge badge-synthetic">' + (state.backtest_data_provenance||'SYNTHETIC HISTORICAL DATA') + '</span><br>' +
        '<div class="metrics">' +
          '<div class="metric"><div class="val">' + state.backtest_snapshots + '</div>snapshots</div>' +
          '<div class="metric"><div class="val">' + state.backtest_detections + '</div>detections</div>' +
          '<div class="metric"><div class="val">' + (state.backtest_precision*100).toFixed(0) + '%</div>precision</div>' +
          '<div class="metric"><div class="val">' + (state.backtest_recall*100).toFixed(0) + '%</div>recall</div>' +
          '<div class="metric"><div class="val">' + (state.backtest_fpr !== undefined ? (state.backtest_fpr*100).toFixed(0) + '%' : '0%') + '</div>FPR</div>' +
          '<div class="metric"><div class="val">' + (state.backtest_would_have_prevented ? '&#10004;' : '&#10008;') + '</div>prevented</div>' +
        '</div>' +
        '<span style="font-size:0.7rem;color:var(--muted)">FP: ' + (state.backtest_false_positives||0) +
        ' | FN: ' + (state.backtest_false_negatives||0) +
        ' | Exec errors: ' + (state.backtest_execution_failures||0) + '</span>';
      return mhtml;
    case 7: // Approval
      if (!state.approval_state) return '<em style="color:var(--muted)">Awaiting approval...</em>';
      var acolor = state.approval_state === 'approved' ? 'var(--green)' : state.approval_state === 'rejected' ? 'var(--red)' : 'var(--amber)';
      var ahtml2 = '<strong style="color:' + acolor + '">' + state.approval_state.toUpperCase() + '</strong>';
      if (state.approval_approver) ahtml2 += ' &mdash; <code>' + state.approval_approver + '</code>';
      if (state.approval_test_mode) ahtml2 += ' <span class="badge badge-synthetic">TEST MODE</span>';
      if (state.approval_timestamp) ahtml2 += '<br><span style="font-size:0.7rem;color:var(--muted)">' + state.approval_timestamp + '</span>';
      if (state.approval_notes) ahtml2 += '<br><span style="font-size:0.75rem;color:var(--muted)">' + state.approval_notes + '</span>';
      if (state.approval_state === 'pending' && !state.is_complete) ahtml2 += '<br><button class="btn btn-primary" onclick="approve(\'approved\')" style="margin-top:0.5rem;font-size:0.75rem">&#10003; Approve Publication</button> <button class="btn btn-danger" onclick="approve(\'rejected\')" style="margin-top:0.5rem;font-size:0.75rem">&#10007; Reject</button>';
      return ahtml2;
    case 8: // Publication
      if (state.publication_count === undefined || state.publication_count === null)
        return '<em style="color:var(--muted)">Publishing to DataHub...</em>';
      var phtml = '';
      if (state.publication_count > 0) {
        phtml += '<strong>' + state.publication_count + ' assets</strong> published <span class="badge badge-datahub">DATAHUB OSS</span><br>';
        (state.publication_assets||[]).slice(0,5).forEach(function(a) { phtml += '<div class="asset-row"><code style="font-size:0.65rem">' + a + '</code></div>'; });
      } else {
        phtml += '<span class="badge badge-reflex">REFLEX-OWNED</span> ';
        phtml += '<span style="font-size:0.75rem;color:var(--muted)">Assertion definitions & run events stored in Reflex (OSS endpoints unavailable).</span><br>';
      }
      if (state.publication_datahub_owned && state.publication_datahub_owned.length) {
        phtml += '<span class="badge badge-datahub" style="font-size:0.65rem">DATAHUB OSS WRITES</span> ';
        phtml += '<span style="font-size:0.7rem;color:var(--muted)">' + state.publication_datahub_owned.join(', ') + '</span><br>';
      }
      if (state.publication_reflex_owned && state.publication_reflex_owned.length) {
        phtml += '<span class="badge badge-reflex" style="font-size:0.65rem">REFLEX-OWNED</span> ';
        phtml += '<span style="font-size:0.7rem;color:var(--muted)">' + state.publication_reflex_owned.join(', ') + '</span><br>';
      }
      if (state.publication_skipped_cloud && state.publication_skipped_cloud.length) {
        phtml += '<span class="badge badge-err" style="font-size:0.65rem">CLOUD-ONLY / NOT EXECUTED</span> ';
        phtml += '<span style="font-size:0.7rem;color:var(--red)">' + state.publication_skipped_cloud.join(', ') + '</span>';
      }
      return phtml;
    case 9: // Detection
      if (state.detection_assets_checked === undefined || state.detection_assets_checked === null)
        return '<em style="color:var(--muted)">Running detection on similar assets...</em>';
      var dhtml = '<strong>' + state.detection_assets_checked + ' assets</strong> checked<br>';
      (state.detection_violations||[]).forEach(function(v) {
        var name = (v.asset_urn||'').split(',').pop()||v.asset_urn||'';
        dhtml += '<div class="asset-row">' +
          (v.passed ? '&#10004; PASSED' : '&#10008; VIOLATION') + ' <code>' + name + '</code>';
        if (!v.passed && v.violation_count) dhtml += ' <span class="badge badge-err">' + v.violation_count + ' violations</span>';
        dhtml += '</div>';
      });
      if (!(state.detection_violations||[]).length) dhtml += '<span style="color:var(--muted);font-size:0.8rem">No violations detected.</span>';
      return dhtml;
    default:
      return '';
  }
}

async function runDemo() {
  const scenario = document.getElementById('scenario').value;
  const runButton = document.getElementById('run-button');
  document.getElementById('error').style.display = 'none';
  if (runButton) { runButton.disabled = true; runButton.innerHTML = '<span aria-hidden="true">◌</span> Starting analysis…'; }
  // Show loading state
  renderSteps({current_step: 1, incident_title:'Running pipeline...'});

  try {
    const resp = await fetch('/api/run', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({scenario}),
    });
    const state = await resp.json();
    renderSteps(state);
  } catch(e) {
    document.getElementById('error').style.display = 'block';
    document.getElementById('error').textContent = 'Unable to start analysis. Check the server and try again.';
  } finally {
    if (runButton) { runButton.disabled = false; runButton.innerHTML = '<span aria-hidden="true">▶</span> Start analysis'; }
  }
}

async function resetDemo() {
  await fetch('/api/reset', {method:'POST'});
  selectScenario(document.getElementById('scenario').value || 'duplicate_rows');
  renderSteps({current_step: 0});
}

async function approve(decision) {
  await fetch('/api/approve', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({decision, approver:'demo-user', notes:'Approved via Reflex UI.'}),
  });
  // Refresh
  const resp = await fetch('/api/state');
  const state = await resp.json();
  renderSteps(state);
}

// Initial load: fetch current state
(async function init() {
  try {
    const resp = await fetch('/api/state');
    const state = await resp.json();
    renderSteps(state);
  } catch(e) {
    renderSteps({current_step: 0});
  }
})();
</script>
</body>
</html>"""


@app.get("/")
def index():
    return _HTML


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    """Run the Reflex UI demo server."""
    port = int(os.environ.get("REFLEX_UI_PORT", "5000"))
    debug = os.environ.get("REFLEX_UI_DEBUG", "0") == "1"
    print(f"DataHub Reflex UI → http://localhost:{port}")
    print("Press Ctrl+C to stop.")
    app.run(host="127.0.0.1", port=port, debug=debug)


if __name__ == "__main__":
    main()
