"""Flask UI for DataHub Reflex — product-grade single-page demo.

Provides:
  GET  /             — single-page UI (Jinja2 template)
  GET  /api/state    — current DemoRunner state as JSON
  POST /api/run      — start a new demo run (persisted to SQLite)
  POST /api/reset    — reset demo state
  POST /api/approve  — interactively approve (persisted to SQLite)
  GET  /api/runs     — list past runs (recovery after restart)
  GET  /api/runs/<id> — load a past run's details

Stack: Flask + Jinja2 templates + SQLite persistence. Zero npm.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

# -- Load .env before any other config-dependent imports --
from reflex.core.env import load_dotenv

# Resolve the project environment file from the repository root rather than
# the process working directory. This keeps auth and DataHub configuration
# reliable when Flask is launched by a service manager or another directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

from flask import Flask, jsonify, render_template, request

from ui.demo_runner import (
    DemoRunner,
    build_duplicate_rows_history,
    build_orphaned_ownership_history,
)
from reflex.api.routes import api_bp
from reflex.persistence import init_db, database as db
from reflex.api.errors import register_error_handlers
from reflex.api.security import configure_security
from reflex.auth import validate_token

app = Flask(
    __name__,
    template_folder="../templates",
    static_folder="../static",
    static_url_path="/static",
)
try:
    app.register_blueprint(api_bp)
except ValueError:
    pass  # Already registered in test collection
init_db()
register_error_handlers(app)
configure_security(app)

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
    state_dict = runner.to_dict()
    # If we have an active run_id, include it for recovery reference
    if runner._active_run_id:
        state_dict["run_id"] = runner._active_run_id
    return jsonify(state_dict)


def _get_authenticated_identity() -> tuple[str | None, str | None]:
    """Extract subject and role from the Authorization header if present."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None, None
    token = auth_header[7:]
    try:
        claims = validate_token(token)
        return claims.get("sub"), claims.get("role")
    except Exception:
        return None, None


@app.post("/api/run")
def api_run():
    """Start a new demo run. Expects JSON body with scenario and params.
    Persists state to SQLite for recovery after restart."""
    runner = _get_runner()
    runner.reset()

    data = request.get_json(silent=True) or {}
    scenario = data.get("scenario", "duplicate_rows")

    # Generate a run ID and persist to SQLite
    run_id = str(uuid.uuid4())
    runner._active_run_id = run_id
    db.create_run(run_id, scenario, mode_label=runner.state.mode_label)
    db.save_incident(run_id, id=run_id, urn=data.get("incident_urn", run_id),
        title="", description="", affected_asset_urn="", root_cause="")

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
    state_dict = asdict(state)
    state_dict["run_id"] = run_id

    # Persist completion state to SQLite
    _persist_demo_state(run_id, scenario, state)

    return jsonify(state_dict)


@app.post("/api/reset")
def api_reset():
    """Reset the demo runner to initial state."""
    runner = _get_runner()
    runner.reset()
    return jsonify({"status": "reset", "current_step": 0})


@app.post("/api/approve")
def api_approve():
    """Apply an explicit human approval to the pending demo step.
    Uses authenticated identity when available, falls back to 'demo-user'."""
    runner = _get_runner()
    data = request.get_json(silent=True) or {}
    decision = data.get("decision", "approved")
    subject, _role = _get_authenticated_identity()
    approver = subject or data.get("approver", "demo-user")
    notes = data.get("notes", "Decision recorded in Reflex workspace.")

    state = asyncio.run(runner.apply_approval(
        decision=decision,
        approver=approver,
        notes=notes,
    ))
    state_dict = asdict(state)
    run_id = runner._active_run_id
    state_dict["run_id"] = run_id

    # Persist approval to SQLite
    if run_id:
        approval_type = "root_cause" if (state.current_step or 0) <= 3 else "control"
        db.save_approval(run_id, approval_type=approval_type, state=decision,
            approver=approver, notes=notes)
        step = 3 if approval_type == "root_cause" else 7
        db.update_run(run_id, current_step=step)

    return jsonify(state_dict)


@app.get("/api/runs")
def api_list_runs():
    """List past runs from SQLite (survives restart)."""
    return jsonify({"runs": db.list_runs(), "persistence": "sqlite"})


@app.get("/api/runs/<run_id>")
def api_get_run(run_id: str):
    """Load a past run's details from SQLite."""
    run = db.get_run(run_id)
    if not run:
        return jsonify({"error": "NOT_FOUND", "detail": f"Run {run_id} not found."}), 404
    approvals = db.get_run_approvals(run_id)
    audit = db.get_run_audit_log(run_id)
    return jsonify({
        "run": dict(run),
        "approvals": [dict(a) for a in approvals],
        "audit_log": [dict(e) for e in audit],
    })


# -- Persistence helper -------------------------------------------------------


def _persist_demo_state(run_id: str, scenario: str, state: "DemoState") -> None:
    """Persist DemoState fields to SQLite for recovery after restart."""
    try:
        db.update_run(run_id, current_step=state.current_step, is_complete=state.is_complete)
        if state.incident_title:
            db.save_incident(run_id, id=run_id, urn=state.incident_urn,
                title=state.incident_title, description=state.incident_description,
                affected_asset_urn=state.incident_affected_asset, root_cause=state.root_cause,
                root_cause_approved=(state.root_cause_approval_state == "approved"))
        if state.lesson_id:
            db.save_lesson(run_id, id=state.lesson_id, incident_id=state.incident_urn,
                title=state.lesson_title, failure_category=state.failure_pattern,
                vulnerable_characteristics=state.vulnerable_characteristics,
                control_type=state.control_type, confidence=state.lesson_confidence)
        if state.control_id:
            db.save_control(run_id, id=state.control_id, lesson_id=state.lesson_id,
                control_type=state.control_type, control_definition=state.control_definition,
                target_field=state.control_target_field)
        if state.backtest_snapshots:
            db.save_backtest(run_id, control_id=state.control_id,
                total_snapshots=state.backtest_snapshots, detections=state.backtest_detections,
                true_positives=state.backtest_detections, false_positives=state.backtest_false_positives,
                true_negatives=0, false_negatives=state.backtest_false_negatives,
                precision=state.backtest_precision, recall=state.backtest_recall,
                false_positive_rate=state.backtest_fpr,
                f1_score=0.0, execution_failures=state.backtest_execution_failures,
                would_have_prevented=state.backtest_would_have_prevented,
                can_recommend=True, blockers=[], data_provenance=state.backtest_data_provenance)
        if state.approval_state and state.approval_state != "pending":
            db.save_approval(run_id, approval_type="control", state=state.approval_state,
                approver=state.approval_approver, notes=state.approval_notes)
        if state.publication_count is not None:
            db.save_publication(run_id, status=state.publication_mode,
                count=state.publication_count, published_assets=state.publication_assets,
                reflex_owned=state.publication_reflex_owned, datahub_owned=state.publication_datahub_owned,
                cloud_skipped=state.publication_skipped_cloud)
        if state.detection_assets_checked is not None:
            db.save_detection(run_id, control_id=state.control_id,
                detected=bool(state.detection_violations), asset_urn="",
                violation_count=len(state.detection_violations), evidence="")
    except Exception:
        pass  # Persistence is best-effort; pipeline result is primary


@app.get("/")
def index():
    return render_template("index.html")


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
