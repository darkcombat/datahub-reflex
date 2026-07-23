"""Product API — Flask blueprint for the Reflex API surface (P1).

Endpoints:
    GET  /api/v1/health
    POST /api/v1/incidents/<id>/analyze
    POST /api/v1/incidents/<id>/root-cause/approve
    GET  /api/v1/lessons/<id>
    POST /api/v1/lessons/<id>/backtest
    GET  /api/v1/controls/<id>
    POST /api/v1/controls/<id>/approve
    POST /api/v1/controls/<id>/publish
    GET  /api/v1/runs/<id>
    GET  /api/v1/runs
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from flask import Blueprint, jsonify, request

from reflex.api.models import (
    ApiError,
    ApprovalResponse,
    BacktestResponse,
    ControlResponse,
    DetectionResponse,
    IncidentResponse,
    LessonResponse,
    PublicationResponse,
    RunResponse,
    SimilarAssetResponse,
    to_dict,
)
from reflex.core.phase3_pipeline import Phase3Pipeline

api_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")
_runs: dict[str, dict] = {}
_current_run_id: str | None = None


@api_bp.get("/health")
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now(UTC).isoformat()})


@api_bp.post("/incidents/<incident_id>/analyze")
def analyze_incident(incident_id: str):
    data = request.get_json(silent=True) or {}
    cid = str(uuid.uuid4())[:8]
    required = (
        "incident_title", "incident_description", "human_confirmed_root_cause",
        "confirmed_by", "target_asset_urn", "incident_custom_type",
    )
    missing = [key for key in required if not str(data.get(key, "")).strip()]
    if missing:
        return jsonify(to_dict(ApiError(
            error="INVALID_REQUEST", detail=f"Missing required fields: {', '.join(missing)}.",
            correlation_id=cid, next_action="Provide all incident and approval context fields.",
        ))), 400
    try:
        pipeline = Phase3Pipeline(lessons_dir=Path(os.environ.get("REFLEX_LESSONS_DIR", "./datasets")))

        async def _run():
            inc = await pipeline.step1_ingest_incident(
                incident_urn=incident_id,
                incident_title=data.get("incident_title", ""),
                incident_description=data.get("incident_description", ""),
                incident_custom_type=data.get("incident_custom_type", ""),
                affected_asset_urn=data.get("target_asset_urn", ""),
                proposed_root_cause=data.get("human_confirmed_root_cause", ""),
            )
            await pipeline.step2_submit_root_cause(incident_id, inc["proposed_root_cause"])
            return inc

        incident = asyncio.run(_run())

        incident_resp = IncidentResponse(
            incident_urn=incident_id, title=incident["title"],
            description=incident["description"], affected_asset_urn=incident["affected_asset_urn"],
            status="PENDING_ROOT_CAUSE", root_cause=incident["proposed_root_cause"],
            root_cause_approved=False,
        )
        run_id = str(uuid.uuid4())
        _runs[run_id] = {"pipeline": pipeline, "scenario": "duplicate_rows",
                         "incident_custom_type": data.get("incident_custom_type", ""),
                         "incident": incident_resp, "lesson": None,
                         "incident_id": incident_id, "started_at": datetime.now(UTC).isoformat(), "current_step": 3}
        global _current_run_id
        _current_run_id = run_id
        return jsonify(to_dict(RunResponse(run_id=run_id, started_at=_runs[run_id]["started_at"],
            current_step=1, is_complete=False, mode_label="SYNTHETIC MODE",
            incident=incident_resp, lesson=None)))
    except Exception as e:
        return jsonify({"error": "ANALYSIS_FAILED", "detail": str(e), "correlation_id": cid}), 500


@api_bp.post("/incidents/<incident_id>/root-cause/approve")
def approve_root_cause(incident_id: str):
    data = request.get_json(silent=True) or {}
    decision = data.get("decision", "")
    approver = data.get("approver", "")
    run = _find_run_by_incident(incident_id)
    if decision not in {"approved", "rejected"} or not approver:
        return jsonify(to_dict(ApiError(
            error="INVALID_APPROVAL", detail="decision and approver are required.",
            correlation_id=str(uuid.uuid4())[:8], next_action="Provide decision=approved|rejected and approver.",
        ))), 400
    if not run:
        return jsonify(to_dict(ApiError(
            error="NOT_FOUND", detail=f"Incident {incident_id} has no active API run.",
            correlation_id=str(uuid.uuid4())[:8],
        ))), 404

    async def _approve():
        pipeline = run["pipeline"]
        if decision == "rejected":
            return await pipeline.step2_reject_root_cause(incident_id, approver)
        root = await pipeline.step2_approve_root_cause(
            incident_id, approver, edited_cause=data.get("edited_root_cause", "")
        )
        lesson, _ = await pipeline.step3_extract_lesson(
            incident_id, run["incident"].title, run["incident"].description,
            root.final_root_cause, approver, run["incident"].affected_asset_urn,
            run.get("incident_custom_type", "DUPLICATE_ROWS"),
        )
        return root, lesson

    result = asyncio.run(_approve())
    timestamp = datetime.now(UTC).isoformat()
    if decision == "rejected":
        run["incident"] = IncidentResponse(
            incident_urn=incident_id, title=run["incident"].title,
            description=run["incident"].description,
            affected_asset_urn=run["incident"].affected_asset_urn,
            status="ROOT_CAUSE_REJECTED", root_cause=run["incident"].root_cause,
            root_cause_approved=False,
        )
        run["approval"] = ApprovalResponse(
            approval_type="root_cause", state="rejected", approver=approver,
            notes=data.get("notes", ""), timestamp=timestamp,
        )
        return jsonify(to_dict(run["approval"]))

    root, lesson = result
    run["incident"] = IncidentResponse(
        incident_urn=incident_id, title=run["incident"].title,
        description=run["incident"].description,
        affected_asset_urn=run["incident"].affected_asset_urn,
        status="RESOLVED", root_cause=root.final_root_cause,
        root_cause_approved=True, approved_by=approver, approved_at=timestamp,
    )
    run["lesson_obj"] = lesson
    run["lesson"] = _lesson_response(lesson, incident_id, extraction_mode="deterministic")
    run["root_cause_approval"] = ApprovalResponse(
        approval_type="root_cause", state="approved", approver=approver,
        notes=data.get("notes", ""), timestamp=timestamp,
    )
    run["current_step"] = 3
    return jsonify(to_dict(run["root_cause_approval"]))


@api_bp.get("/lessons/<lesson_id>")
def get_lesson(lesson_id: str):
    run = _get_current_run()
    if run and run.get("lesson") and run["lesson"].lesson_id == lesson_id:
        return jsonify(to_dict(run["lesson"]))
    return jsonify(to_dict(ApiError(error="NOT_FOUND", detail=f"Lesson {lesson_id} not found.",
                                     correlation_id=str(uuid.uuid4())[:8]))), 404


@api_bp.post("/lessons/<lesson_id>/backtest")
def backtest_lesson(lesson_id: str):
    data = request.get_json(silent=True) or {}
    cid = str(uuid.uuid4())[:8]
    run = _get_current_run()
    if not run:
        return jsonify(to_dict(ApiError(error="NO_ACTIVE_RUN", detail="Analyze an incident first.",
                                         correlation_id=cid))), 400
    try:
        pipeline = run["pipeline"]
        async def _run():
            lesson = run.get("lesson_obj")
            if lesson is None or not run["incident"].root_cause_approved:
                raise ValueError("Root cause must be explicitly approved before backtesting.")
            target_field = data.get("target_field", "transaction_id")
            candidates = await pipeline.step4_discover_similar_assets(
                source_asset_urn=run["incident"].affected_asset_urn,
                target_field=target_field, propagation_scope=["finance"],
            )
            control = await pipeline.step5_synthesize_control(lesson, target_field=target_field)
            from ui.demo_runner import build_duplicate_rows_history
            historical = build_duplicate_rows_history(days=8)
            results, metrics, can_rec, blockers = await pipeline.step6_backtest(
                control, historical, known_incident_snapshots=2,
            )
            similar = [SimilarAssetResponse(
                asset_urn=c.asset_urn, asset_name=c.asset_urn.split(",")[-1].replace(")", ""),
                selected=c.selected, score=c.score, matched_signals=c.matched_signals,
                missing_signals=c.missing_signals, explanation=c.explanation, similarity_mode="synthetic",
            ) for c in candidates]
            backtest = BacktestResponse(
                control_id=control.control_id, total_snapshots=metrics.run_coverage,
                detections=metrics.true_positives, true_positives=metrics.true_positives,
                false_positives=metrics.false_positives, true_negatives=metrics.true_negatives,
                false_negatives=metrics.false_negatives, precision=metrics.precision,
                recall=metrics.recall, false_positive_rate=metrics.false_positive_rate,
                f1_score=metrics.f1_score, execution_failures=metrics.execution_errors,
                would_have_prevented=any(r.would_have_detected for r in results),
                can_recommend=can_rec, blockers=blockers,
            )
            control_resp = ControlResponse(
                control_id=control.control_id, control_type=control.control_type.value,
                control_definition=control.control_definition[:500], target_field=target_field,
            )
            return similar, backtest, control_resp, control, metrics

        similar, backtest, control_resp, control, metrics = asyncio.run(_run())
        if similar is None:
            return jsonify(to_dict(ApiError(error="BACKTEST_FAILED",
                detail="Only duplicate_rows supported via API.", correlation_id=cid))), 400
        run["similar_assets"] = similar
        run["backtest"] = backtest
        run["control"] = control_resp
        run["control_obj"] = control
        run["current_step"] = 6
        return jsonify(to_dict(RunResponse(run_id=_current_run_id, started_at=run["started_at"],
            current_step=6, is_complete=False, mode_label="SYNTHETIC MODE",
            incident=run.get("incident"), lesson=run.get("lesson"), control=control_resp,
            similar_assets=similar, backtest=backtest)))
    except Exception as e:
        return jsonify({"error": "BACKTEST_FAILED", "detail": str(e), "correlation_id": cid}), 500


@api_bp.get("/controls/<control_id>")
def get_control(control_id: str):
    run = _get_current_run()
    if run and run.get("control") and run["control"].control_id == control_id:
        return jsonify(to_dict(run["control"]))
    return jsonify(to_dict(ApiError(error="NOT_FOUND", detail=f"Control {control_id} not found.",
                                     correlation_id=str(uuid.uuid4())[:8]))), 404


@api_bp.post("/controls/<control_id>/approve")
def approve_control(control_id: str):
    data = request.get_json(silent=True) or {}
    decision = data.get("decision", "approved")
    run = _get_current_run()
    if not run or not run.get("control") or run["control"].control_id != control_id:
        return jsonify(to_dict(ApiError(
            error="NOT_FOUND", detail=f"Control {control_id} has no active API run.",
            correlation_id=str(uuid.uuid4())[:8],
        ))), 404
    if not run.get("backtest") or not run["backtest"].can_recommend:
        return jsonify(to_dict(ApiError(
            error="BACKTEST_REQUIRED", detail="A successful backtest is required before approval.",
            correlation_id=str(uuid.uuid4())[:8], next_action="Run the lesson backtest first.",
        ))), 409
    if decision == "rejected":
        run["approval"] = ApprovalResponse(approval_type="control", state="rejected",
            approver=data.get("approver", "api-user"), notes=data.get("notes", ""),
            timestamp=datetime.now(UTC).isoformat())
        return jsonify(to_dict(run["approval"]))
    if decision != "approved" or not data.get("approver"):
        return jsonify(to_dict(ApiError(
            error="INVALID_APPROVAL", detail="decision=approved|rejected and approver are required.",
            correlation_id=str(uuid.uuid4())[:8],
        ))), 400
    run["approval"] = ApprovalResponse(approval_type="control", state="approved",
            approver=data.get("approver", "api-user"), notes=data.get("notes", ""),
            timestamp=datetime.now(UTC).isoformat())
    run["current_step"] = 7
    return jsonify(to_dict(ApprovalResponse(approval_type="control", state="approved",
        approver=data.get("approver", "api-user"), notes=data.get("notes", ""),
        timestamp=datetime.now(UTC).isoformat())))


@api_bp.post("/controls/<control_id>/publish")
def publish_control(control_id: str):
    cid = str(uuid.uuid4())[:8]
    run = _get_current_run()
    if not run or not run.get("control") or run["control"].control_id != control_id:
        return jsonify(to_dict(ApiError(
            error="NOT_FOUND", detail=f"Control {control_id} has no active API run.",
            correlation_id=cid,
        ))), 404
    if not run.get("approval") or run["approval"].state != "approved":
        return jsonify(to_dict(ApiError(
            error="APPROVAL_REQUIRED", detail="Control publication requires explicit human approval.",
            correlation_id=cid, next_action=f"POST /api/v1/controls/{control_id}/approve",
        ))), 409
    pub_resp = PublicationResponse(
        status="reflex-owned", count=0,
        reflex_owned=["Assertion definitions", "Backtest run events", "Control execution results"],
        datahub_owned=["Incidents (raiseIncident)", "Ownership updates (addOwner)",
                       "Tags (createTag/addTag)", "Structured properties"],
        cloud_skipped=["upsertAssertion (removed in OSS v1.5.0.6)",
                       "assertion run events (REST endpoint 404s)"],
    )
    detection = DetectionResponse(
        detected=True,
        asset_urn="urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_monthly_ledger,PROD)",
        violation_count=3, control_id=control_id,
        evidence="3 duplicate transaction IDs detected on analogous asset.",
    )
    if run:
        run["publication"] = pub_resp
        run["detection"] = detection
        run["current_step"] = 9
        run["is_complete"] = True
    return jsonify(to_dict(RunResponse(
        run_id=_current_run_id or cid,
        started_at=run["started_at"] if run else datetime.now(UTC).isoformat(),
        current_step=9, is_complete=True, mode_label="SYNTHETIC MODE",
        incident=run.get("incident") if run else None,
        lesson=run.get("lesson") if run else None,
        control=run.get("control") if run else None,
        similar_assets=run.get("similar_assets", []) if run else [],
        backtest=run.get("backtest") if run else None,
        approval=run.get("approval") if run else None,
        publication=pub_resp, detection=detection,
    )))


@api_bp.get("/runs/<run_id>")
def get_run(run_id: str):
    run = _runs.get(run_id)
    if not run:
        return jsonify(to_dict(ApiError(error="NOT_FOUND", detail=f"Run {run_id} not found.",
                                         correlation_id=str(uuid.uuid4())[:8]))), 404
    return jsonify(to_dict(RunResponse(
        run_id=run_id, started_at=run["started_at"], current_step=run["current_step"],
        is_complete=run.get("is_complete", False), mode_label="SYNTHETIC MODE",
        error=run.get("error", ""), incident=run.get("incident"), lesson=run.get("lesson"),
        control=run.get("control"), similar_assets=run.get("similar_assets", []),
        backtest=run.get("backtest"), approval=run.get("approval"),
        publication=run.get("publication"), detection=run.get("detection"),
    )))


@api_bp.get("/runs")
def list_runs():
    return jsonify({"runs": [{"run_id": rid, "started_at": r["started_at"],
                               "current_step": r["current_step"]} for rid, r in _runs.items()]})


def _get_current_run() -> dict | None:
    return _runs.get(_current_run_id) if _current_run_id else None


def _find_run_by_incident(incident_id: str) -> dict | None:
    for run in _runs.values():
        if run.get("incident_id") == incident_id:
            return run
    return None


def _lesson_response(lesson, incident_id: str, extraction_mode: str) -> LessonResponse:
    return LessonResponse(
        lesson_id=lesson.lesson_id,
        title=lesson.title,
        failure_category=lesson.failure_pattern.category.value,
        failure_pattern=str(lesson.failure_pattern),
        vulnerable_characteristics=list(lesson.vulnerable_characteristics),
        control_type=lesson.candidate_preventive_control.control_type.value,
        propagation_scope=list(lesson.intended_propagation_scope),
        confidence=lesson.confidence.value,
        source_incident_urn=incident_id,
        extraction_mode=extraction_mode,
    )
