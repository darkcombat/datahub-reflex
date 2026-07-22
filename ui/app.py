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

app = Flask(__name__)

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
</style>
</head>
<body>

<header>
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

<main>
  <div id="error" class="error-box" style="display:none"></div>
  <div class="steps" id="steps"></div>
</main>

<footer>
  DataHub Reflex Demo &mdash; explicit human approval required.
  All state is real application state. Synthetic data and Reflex-owned execution are labeled.
</footer>

<script>
const STEP_LABELS = [
  {num:1, title:"Resolved Incident", owner:"DataHub OSS"},
  {num:2, title:"Human-Confirmed Root Cause", owner:"Reflex"},
  {num:3, title:"Structured Lesson", owner:"Reflex"},
  {num:4, title:"Proposed Preventive Control", owner:"Reflex"},
  {num:5, title:"Similar Assets &amp; Signals", owner:"Reflex"},
  {num:6, title:"Backtest Metrics", owner:"Reflex-owned"},
  {num:7, title:"Approval Action", owner:"Reflex"},
  {num:8, title:"DataHub Publication", owner:"DataHub OSS"},
  {num:9, title:"Analogous Future Detection", owner:"Reflex"},
];

let currentState = null;

function badge(owner) {
  if (owner.includes('Reflex')) return '<span class="badge badge-reflex">Reflex</span>';
  if (owner.includes('DataHub')) return '<span class="badge badge-datahub">DataHub</span>';
  return '';
}

function renderSteps(state) {
  currentState = state;
  const container = document.getElementById('steps');
  const currentStep = state.current_step || 0;
  const hasError = !!state.error;

  let html = '';
  for (let i = 0; i < STEP_LABELS.length; i++) {
    const s = STEP_LABELS[i];
    const n = s.num;
    let cls = 'step';
    if (hasError && n > currentStep) cls += '';
    else if (n < currentStep) cls += ' done';
    else if (n === currentStep) cls += ' active';
    html += `<div class="${cls}">`;
    html += `<div class="step-header"><div class="step-number">${n}</div>`;
    html += `<div class="step-title">${s.title} ${badge(s.owner)}</div></div>`;
    html += `<div class="step-detail">${renderDetail(n, state)}</div>`;
    html += `</div>`;
  }

  if (hasError) {
    html += `<div class="step active"><div class="step-header" style="color:var(--red)">`;
    html += `⚠ Pipeline Error</div>`;
    html += `<div class="step-detail" style="color:var(--red)">${state.error}</div></div>`;
  }

  container.innerHTML = html;

  // Show/hide error box
  const errBox = document.getElementById('error');
  if (hasError) { errBox.style.display = 'block'; errBox.textContent = 'Error: ' + state.error; }
  else errBox.style.display = 'none';
}

function renderDetail(n, state) {
  switch (n) {
    case 1: // Incident
      if (!state.incident_title) return `<em style="color:var(--muted)">Awaiting incident input...</em>`;
      return state.incident_title
        ? `<strong>${state.incident_title}</strong><br>${state.incident_description}<br>
           <span style="font-size:0.75rem;color:var(--muted)">URN: ${state.incident_urn}</span>`
        : `<em style="color:var(--muted)">Awaiting incident input...</em>`;
    case 2: // Root Cause
      return state.root_cause
        ? `<strong>Root cause:</strong> ${state.root_cause}<br>
           <span style="font-size:0.75rem">Confirmed by: ${state.confirmed_by}</span>`
        : `<em style="color:var(--muted)">Awaiting human root cause confirmation...</em>`;
    case 3: // Lesson
      return state.lesson_id
        ? `<strong>${state.lesson_title}</strong> (${state.lesson_id})<br>
           Failure pattern: <code>${state.failure_pattern}</code><br>
           Confidence: ${state.lesson_confidence}<br>
           Vulnerable: ${(state.vulnerable_characteristics||[]).join(', ') || 'none'}`
        : `<em style="color:var(--muted)">Extracting lesson...</em>`;
    case 4: // Control
      return state.control_id
        ? `<strong>Type:</strong> ${state.control_type} &nbsp;
           <span class="badge badge-reflex">Reflex-owned execution</span><br>
           <strong>ID:</strong> ${state.control_id}<br>
           <strong>Definition:</strong> <code style="font-size:0.75rem">${state.control_definition}</code>`
        : `<em style="color:var(--muted)">Synthesizing control...</em>`;
    case 5: // Similar Assets
      if (!state.similar_assets || state.similar_assets.length === 0)
        return `<em style="color:var(--muted)">Discovering similar assets...</em>
          <br><span class="badge badge-synthetic">SYNTHETIC</span>
          <span style="font-size:0.75rem;color:var(--muted)">${state.similarity_mode} mode</span>`;
      let ahtml = `<span class="badge badge-synthetic">${state.similarity_mode.toUpperCase()}</span><br>`;
      state.similar_assets.forEach(a => {
        ahtml += `<div class="asset-row">
          <strong>${(a.asset_urn||'').split(',').pop()||a.asset_urn}</strong>
          <span style="color:var(--muted)"> &mdash; ${a.confidence||'?'} confidence</span><br>
          <span style="font-size:0.75rem;color:var(--muted)">${a.rationale||''}</span>
          </div>`;
      });
      return ahtml;
    case 6: // Backtest
      if (!state.backtest_snapshots)
        return `<em style="color:var(--muted)">Running backtest against synthetic historical data...</em>`;
      let mhtml = `<span class="badge badge-synthetic">SYNTHETIC HISTORICAL DATA</span><br>
        <div class="metrics">
          <div class="metric"><div class="val">${state.backtest_snapshots}</div>snapshots</div>
          <div class="metric"><div class="val">${state.backtest_detections}</div>detections</div>
          <div class="metric"><div class="val">${(state.backtest_precision*100).toFixed(0)}%</div>precision</div>
          <div class="metric"><div class="val">${(state.backtest_recall*100).toFixed(0)}%</div>recall</div>
          <div class="metric"><div class="val">${state.backtest_would_have_prevented ? '✅' : '❌'}</div>prevented</div>
        </div>`;
      return mhtml;
    case 7: // Approval
      if (!state.approval_state) return `<em style="color:var(--muted)">Awaiting approval...</em>`;
      let acolor = state.approval_state === 'approved' ? 'var(--green)' : state.approval_state === 'rejected' ? 'var(--red)' : 'var(--amber)';
      return `<strong style="color:${acolor}">${state.approval_state.toUpperCase()}</strong>
        ${state.approval_approver ? ` &mdash; ${state.approval_approver}` : ''}<br>
        <span style="font-size:0.75rem;color:var(--muted)">${state.approval_notes || ''}</span>
        ${state.approval_state === 'pending' ? `<br><button class="btn" onclick="approve('approved')" style="margin-top:0.5rem">Approve</button>
        <button class="btn btn-danger" onclick="approve('rejected')" style="margin-top:0.5rem">Reject</button>` : ''}`;
    case 8: // Publication
      if (state.publication_count === undefined || state.publication_count === null)
        return `<em style="color:var(--muted)">Publishing to DataHub...</em>`;
      if (!state.publication_count)
        return `<span class="badge badge-reflex">REFLEX-OWNED</span>
          <span style="font-size:0.75rem;color:var(--muted)">Assertion definitions and run events stored in Reflex (DataHub OSS v1.5.0.6 endpoints unavailable).</span>`;
      return `<strong>${state.publication_count} assets</strong> published
        <span class="badge badge-datahub">DataHub OSS</span><br>
        ${(state.publication_assets||[]).slice(0,5).map(a => `<div class="asset-row">${a}</div>`).join('')}`;
    case 9: // Detection
      if (state.detection_assets_checked === undefined || state.detection_assets_checked === null)
        return `<em style="color:var(--muted)">Running detection on similar assets...</em>`;
      let dhtml = `<strong>${state.detection_assets_checked} assets</strong> checked<br>`;
      (state.detection_violations||[]).forEach(v => {
        dhtml += `<div class="asset-row">
          ${v.passed ? '✅' : '❌'} ${(v.asset_urn||'').split(',').pop()||v.asset_urn}
          ${!v.passed ? `<span class="badge badge-err">${v.violation_count||0} violations</span>` : ''}
          </div>`;
      });
      if (!state.detection_violations.length) dhtml += '<span style="color:var(--muted)">No violations detected.</span>';
      return dhtml;
    default:
      return '';
  }
}

async function runDemo() {
  const scenario = document.getElementById('scenario').value;
  document.getElementById('error').style.display = 'none';
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
    document.getElementById('error').textContent = 'Failed to run: ' + e.message;
  }
}

async function resetDemo() {
  await fetch('/api/reset', {method:'POST'});
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
