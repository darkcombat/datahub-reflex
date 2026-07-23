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

from flask import Flask, jsonify, render_template, request

from ui.demo_runner import (
    DemoRunner,
    build_duplicate_rows_history,
    build_orphaned_ownership_history,
)
from reflex.api.routes import api_bp
from reflex.persistence import init_db
from reflex.api.errors import register_error_handlers
from reflex.api.security import configure_security

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
