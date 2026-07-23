"""Product API — Flask blueprint with SQLite persistence.

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
    GET  /api/v1/runs/<id>/audit
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from flask import Blueprint, jsonify, request

from reflex.api.models import (
    ApiError, ApprovalResponse, BacktestResponse, ControlResponse,
    DetectionResponse, IncidentResponse, LessonResponse, PublicationResponse,
    RunResponse, SimilarAssetResponse, to_dict,
)
from reflex.core.phase3_pipeline import Phase3Pipeline
from reflex.core.phase4_pipeline import Phase4Pipeline
from reflex.persistence import database as db
from reflex.auth import create_token, require_auth, require_role
from reflex.api.security import rate_limit

api_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")


@api_bp.get("/health")
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now(UTC).isoformat(), "persistence": "sqlite"})


# -- Authentication -----------------------------------------------------------


@api_bp.post("/auth/token")
@rate_limit
def create_auth_token():
    """Create an authentication token. Requires REFLEX_API_SECRET in env."""
    data = request.get_json(silent=True) or {}
    subject = data.get("subject", "api-user")
    role = data.get("role", "viewer")
    if role not in ("admin", "approver", "viewer"):
        return jsonify({"error": "INVALID_ROLE", "detail": f"Role must be admin, approver, or viewer. Got: {role}"}), 400
    try:
        token = create_token(subject=subject, role=role)
        return jsonify({"token": token, "subject": subject, "role": role,
                        "note": "Use as: Authorization: Bearer <token>"})
    except RuntimeError as e:
        return jsonify({"error": "AUTH_NOT_CONFIGURED", "detail": str(e)}), 500


# -- Incidents ----------------------------------------------------------------


@api_bp.post("/incidents/<incident_id>/analyze")
@require_role("admin", "approver")
def analyze_incident(incident_id: str):
    data = request.get_json(silent=True) or {}
    cid = str(uuid.uuid4())[:8]
    scenario = data.get("scenario", "duplicate_rows")
    try:
        lessons_dir = Path(os.environ.get("REFLEX_LESSONS_DIR", "./datasets"))
        pipeline_cls = Phase4Pipeline if scenario == "orphaned_ownership" else Phase3Pipeline
        pipeline = pipeline_cls(lessons_dir=lessons_dir)

        async def _run():
            inc = await pipeline.step1_ingest_incident(
                incident_urn=incident_id, incident_title=data.get("incident_title", ""),
                incident_description=data.get("incident_description", ""),
                incident_custom_type=data.get("incident_custom_type", ""),
                affected_asset_urn=data.get("target_asset_urn", ""),
                proposed_root_cause=data.get("human_confirmed_root_cause", ""),
            )
            await pipeline.step2_submit_root_cause(incident_id, inc["proposed_root_cause"])
            root = await pipeline.step2_approve_root_cause(incident_id, data.get("confirmed_by", "api-user"))
            lesson, _ = await pipeline.step3_extract_lesson(
                incident_id, inc["title"], inc["description"],
                root.final_root_cause, data.get("confirmed_by", "api-user"),
                inc["affected_asset_urn"], data.get("incident_custom_type", ""),
            )
            return inc, root, lesson

        incident, root, lesson = asyncio.run(_run())

        run_id = str(uuid.uuid4())
        db.create_run(run_id, scenario)
        db.save_incident(run_id, id=incident_id, urn=incident_id, title=incident["title"],
            description=incident["description"], affected_asset_urn=incident["affected_asset_urn"],
            root_cause=incident["proposed_root_cause"], root_cause_approved=True)
        db.save_approval(run_id, approval_type="root_cause", state="approved",
            approver=data.get("confirmed_by", "api-user"))
        db.save_lesson(run_id, id=lesson.lesson_id, incident_id=incident_id,
            title=lesson.title, failure_category=lesson.failure_pattern.category.value,
            vulnerable_characteristics=list(lesson.vulnerable_characteristics),
            control_type=lesson.candidate_preventive_control.control_type.value,
            confidence=lesson.confidence.value)
        db.update_run(run_id, current_step=3)

        incident_resp = IncidentResponse(incident_urn=incident_id, title=incident["title"],
            description=incident["description"], affected_asset_urn=incident["affected_asset_urn"],
            status="RESOLVED", root_cause=incident["proposed_root_cause"], root_cause_approved=True,
            approved_by=data.get("confirmed_by", "api-user"), approved_at=datetime.now(UTC).isoformat())
        lesson_resp = LessonResponse(
            lesson_id=lesson.lesson_id, title=lesson.title,
            failure_category=lesson.failure_pattern.category.value,
            vulnerable_characteristics=list(lesson.vulnerable_characteristics),
            control_type=lesson.candidate_preventive_control.control_type.value,
            propagation_scope=list(lesson.intended_propagation_scope),
            confidence=lesson.confidence.value, source_incident_urn=incident_id)

        return jsonify(to_dict(RunResponse(run_id=run_id,
            started_at=datetime.now(UTC).isoformat(), current_step=3, is_complete=False,
            mode_label="SYNTHETIC MODE", incident=incident_resp, lesson=lesson_resp)))
    except Exception as e:
        return jsonify({"error": "ANALYSIS_FAILED", "detail": str(e), "correlation_id": cid}), 500


@api_bp.post("/incidents/<incident_id>/root-cause/approve")
@require_role("admin", "approver")
def approve_root_cause(incident_id: str):
    data = request.get_json(silent=True) or {}
    decision = data.get("decision", "approved")
    run_id = data.get("run_id", "")
    if run_id:
        db.save_approval(run_id, approval_type="root_cause", state=decision,
            approver=data.get("approver", "api-user"), notes=data.get("notes", ""))
    return jsonify(to_dict(ApprovalResponse(approval_type="root_cause", state=decision,
        approver=data.get("approver", "api-user"), notes=data.get("notes", ""),
        timestamp=datetime.now(UTC).isoformat())))


@api_bp.get("/lessons/<lesson_id>")
def get_lesson(lesson_id: str):
    return jsonify(to_dict(ApiError(error="NOT_FOUND",
        detail=f"Lesson {lesson_id} not found.", correlation_id=str(uuid.uuid4())[:8]))), 404


@api_bp.post("/lessons/<lesson_id>/backtest")
@require_role("admin", "approver")
def backtest_lesson(lesson_id: str):
    data = request.get_json(silent=True) or {}
    cid = str(uuid.uuid4())[:8]
    run_id = data.get("run_id", "")
    target_field = data.get("target_field", "transaction_id")
    try:
        lessons_dir = Path(os.environ.get("REFLEX_LESSONS_DIR", "./datasets"))
        pipeline = Phase3Pipeline(lessons_dir=lessons_dir)

        async def _run():
            from reflex.core.lesson_extractor import LessonExtractor
            extractor = LessonExtractor()
            lesson_tuple = await extractor.extract(
                incident_urn=data.get("incident_urn", "urn:li:incident:backtest"),
                incident_title=data.get("incident_title", "Backtest"), incident_description=data.get("incident_description", ""),
                human_confirmed_root_cause=data.get("root_cause", "Non-idempotent retry."),
                confirmed_by=data.get("confirmed_by", "api-user"),
                target_asset_urn=data.get("target_asset_urn", "urn:li:dataset:(urn:li:dataPlatform:bigquery,test,PROD)"),
                incident_custom_type=data.get("incident_custom_type", "DUPLICATE_ROWS"))
            lesson = lesson_tuple[0]
            candidates = await pipeline.step4_discover_similar_assets(
                source_asset_urn=data.get("target_asset_urn", ""), target_field=target_field,
                propagation_scope=data.get("propagation_scope", ["finance"]))
            control = await pipeline.step5_synthesize_control(lesson, target_field=target_field)
            from ui.demo_runner import build_duplicate_rows_history
            historical = build_duplicate_rows_history(days=8)
            results, metrics, can_rec, blockers = await pipeline.step6_backtest(control, historical, known_incident_snapshots=2)
            similar = [SimilarAssetResponse(asset_urn=c.asset_urn,
                asset_name=c.asset_urn.split(",")[-1].replace(")", ""), selected=c.selected,
                score=c.score, matched_signals=c.matched_signals, missing_signals=c.missing_signals,
                explanation=c.explanation, similarity_mode="synthetic") for c in candidates]
            bt = BacktestResponse(control_id=control.control_id, total_snapshots=metrics.run_coverage,
                detections=metrics.true_positives, true_positives=metrics.true_positives,
                false_positives=metrics.false_positives, true_negatives=metrics.true_negatives,
                false_negatives=metrics.false_negatives, precision=metrics.precision,
                recall=metrics.recall, false_positive_rate=metrics.false_positive_rate,
                f1_score=metrics.f1_score, execution_failures=metrics.execution_errors,
                would_have_prevented=any(r.would_have_detected for r in results),
                can_recommend=can_rec, blockers=blockers)
            ctrl = ControlResponse(control_id=control.control_id, control_type=control.control_type.value,
                control_definition=control.control_definition[:500], target_field=target_field)
            return similar, bt, ctrl, control

        similar, bt, ctrl, control = asyncio.run(_run())
        if run_id:
            db.save_control(run_id, id=control.control_id, lesson_id=lesson_id,
                control_type=control.control_type.value, control_definition=control.control_definition[:500],
                target_field=target_field)
            db.save_backtest(run_id, control_id=control.control_id, total_snapshots=bt.total_snapshots,
                detections=bt.detections, true_positives=bt.true_positives, false_positives=bt.false_positives,
                true_negatives=bt.true_negatives, false_negatives=bt.false_negatives,
                precision=bt.precision, recall=bt.recall, false_positive_rate=bt.false_positive_rate,
                f1_score=bt.f1_score, execution_failures=bt.execution_failures,
                would_have_prevented=bt.would_have_prevented, can_recommend=bt.can_recommend, blockers=bt.blockers)
            db.update_run(run_id, current_step=6)
        return jsonify(to_dict(RunResponse(run_id=run_id or cid,
            started_at=datetime.now(UTC).isoformat(), current_step=6, is_complete=False,
            mode_label="SYNTHETIC MODE", control=ctrl, similar_assets=similar, backtest=bt)))
    except Exception as e:
        return jsonify({"error": "BACKTEST_FAILED", "detail": str(e), "correlation_id": cid}), 500


@api_bp.get("/controls/<control_id>")
def get_control(control_id: str):
    return jsonify(to_dict(ApiError(error="NOT_FOUND",
        detail=f"Control {control_id} not found.", correlation_id=str(uuid.uuid4())[:8]))), 404


@api_bp.post("/controls/<control_id>/approve")
@require_role("admin", "approver")
def approve_control(control_id: str):
    data = request.get_json(silent=True) or {}
    decision = data.get("decision", "approved")
    run_id = data.get("run_id", "")
    if run_id:
        db.save_approval(run_id, approval_type="control", state=decision,
            approver=data.get("approver", "api-user"), notes=data.get("notes", ""))
        if decision == "approved":
            db.update_run(run_id, current_step=7)
    return jsonify(to_dict(ApprovalResponse(approval_type="control", state=decision,
        approver=data.get("approver", "api-user"), notes=data.get("notes", ""),
        timestamp=datetime.now(UTC).isoformat())))


@api_bp.post("/controls/<control_id>/publish")
@require_role("admin",)
def publish_control(control_id: str):
    cid = str(uuid.uuid4())[:8]
    data = request.get_json(silent=True) or {}
    run_id = data.get("run_id", "")
    pub = PublicationResponse(status="reflex-owned", count=0,
        reflex_owned=["Assertion definitions", "Backtest run events", "Control execution results"],
        datahub_owned=["Incidents (raiseIncident)", "Ownership updates (addOwner)",
            "Tags (createTag/addTag)", "Structured properties"],
        cloud_skipped=["upsertAssertion (removed in OSS v1.5.0.6)",
            "assertion run events (REST endpoint 404s)"])
    det = DetectionResponse(detected=True,
        asset_urn="urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_monthly_ledger,PROD)",
        violation_count=3, control_id=control_id,
        evidence="3 duplicate transaction IDs detected on analogous asset.")
    if run_id:
        db.save_publication(run_id, status="reflex-owned", count=0,
            reflex_owned=pub.reflex_owned, datahub_owned=pub.datahub_owned, cloud_skipped=pub.cloud_skipped)
        db.save_detection(run_id, control_id=control_id, detected=True,
            asset_urn=det.asset_urn, violation_count=det.violation_count, evidence=det.evidence)
        db.update_run(run_id, current_step=9, is_complete=True)
    return jsonify(to_dict(RunResponse(run_id=run_id or cid,
        started_at=datetime.now(UTC).isoformat(), current_step=9, is_complete=True,
        mode_label="SYNTHETIC MODE", publication=pub, detection=det)))


@api_bp.get("/runs/<run_id>")
def get_run(run_id: str):
    run = db.get_run(run_id)
    if not run:
        return jsonify(to_dict(ApiError(error="NOT_FOUND",
            detail=f"Run {run_id} not found.", correlation_id=str(uuid.uuid4())[:8]))), 404
    approvals = db.get_run_approvals(run_id)
    last_approval = None
    if approvals:
        a = approvals[-1]
        last_approval = ApprovalResponse(approval_type=a["approval_type"], state=a["state"],
            approver=a["approver"], notes=a.get("notes", ""), timestamp=a["created_at"],
            test_mode=bool(a["test_mode"]))
    return jsonify(to_dict(RunResponse(run_id=run_id, started_at=run["started_at"],
        current_step=run["current_step"], is_complete=bool(run["is_complete"]),
        mode_label=run["mode_label"], error=run.get("error", ""), approval=last_approval)))


@api_bp.post("/runs/<run_id>/execute")
@require_role("admin", "approver")
def execute_run(run_id: str):
    """Execute a full pipeline run for either scenario.

    Body: {"scenario": "duplicate_rows|orphaned_ownership", ...}
    For duplicate_rows: requires target_field, uniqueness_columns.
    For orphaned_ownership: requires inactive_owner_urn.
    """
    data = request.get_json(silent=True) or {}
    cid = str(uuid.uuid4())[:8]
    scenario = data.get("scenario", "duplicate_rows")
    lessons_dir = Path(os.environ.get("REFLEX_LESSONS_DIR", "./datasets"))

    try:
        if scenario == "orphaned_ownership":
            return _execute_ownership(run_id, data, lessons_dir, cid)
        else:
            return _execute_duplicate_rows(run_id, data, lessons_dir, cid)
    except Exception as e:
        return jsonify({"error": "EXECUTION_FAILED", "detail": str(e), "correlation_id": cid}), 500


@api_bp.get("/runs")
def list_runs():
    return jsonify({"runs": db.list_runs(), "persistence": "sqlite"})


@api_bp.get("/runs/<run_id>/audit")
def get_audit_log(run_id: str):
    run = db.get_run(run_id)
    if not run:
        return jsonify(to_dict(ApiError(error="NOT_FOUND",
            detail=f"Run {run_id} not found.", correlation_id=str(uuid.uuid4())[:8]))), 404
    return jsonify({"run_id": run_id, "events": db.get_run_audit_log(run_id)})


# -- Internal helpers ---------------------------------------------------------


def _execute_duplicate_rows(run_id: str, data: dict, lessons_dir: Path, cid: str):
    pipeline = Phase3Pipeline(lessons_dir=lessons_dir)
    target_field = data.get("target_field", "transaction_id")

    async def _run():
        inc = await pipeline.step1_ingest_incident(
            incident_urn=data.get("incident_urn", run_id),
            incident_title=data.get("incident_title", "API Run"),
            incident_description=data.get("incident_description", ""),
            incident_custom_type="DUPLICATE_ROWS",
            affected_asset_urn=data.get("target_asset_urn", "urn:li:dataset:test"),
            proposed_root_cause=data.get("human_confirmed_root_cause", "Non-idempotent retry."))
        await pipeline.step2_submit_root_cause(inc["incident_urn"], inc["proposed_root_cause"])
        root = await pipeline.step2_approve_root_cause(inc["incident_urn"], "api-user")
        lesson, _ = await pipeline.step3_extract_lesson(
            inc["incident_urn"], inc["title"], inc["description"],
            root.final_root_cause, "api-user", inc["affected_asset_urn"], "DUPLICATE_ROWS")
        candidates = await pipeline.step4_discover_similar_assets(
            source_asset_urn=inc["affected_asset_urn"], target_field=target_field,
            propagation_scope=["finance"])
        control = await pipeline.step5_synthesize_control(lesson, target_field=target_field)
        from ui.demo_runner import build_duplicate_rows_history
        historical = build_duplicate_rows_history(days=8)
        results, metrics, can_rec, blockers = await pipeline.step6_backtest(control, historical, known_incident_snapshots=2)
        await pipeline.step7_submit_control_approval(control, metrics)
        await pipeline.step7_approve_control(control.control_id, "api-user")
        det = await pipeline.step9_detect_analogous_incident(
            control, "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_monthly_ledger,PROD)",
            build_duplicate_rows_history(days=8)[-2][1])
        return control, metrics, can_rec, det

    control, metrics, can_rec, det = asyncio.run(_run())
    db.create_run(run_id, "duplicate_rows")
    db.update_run(run_id, current_step=9, is_complete=True)
    return jsonify({
        "run_id": run_id, "scenario": "duplicate_rows", "is_complete": True,
        "control_id": control.control_id, "can_recommend": can_rec,
        "precision": metrics.precision, "recall": metrics.recall,
        "future_detected": det["detected"], "violations": det.get("violation_count", 0),
    })


def _execute_ownership(run_id: str, data: dict, lessons_dir: Path, cid: str):
    pipeline = Phase4Pipeline(lessons_dir=lessons_dir)

    async def _run():
        from ui.demo_runner import build_orphaned_ownership_history
        historical = build_orphaned_ownership_history(days=8)
        result = await pipeline.run(
            incident_urn=data.get("incident_urn", run_id),
            incident_title=data.get("incident_title", "API Ownership Run"),
            incident_description=data.get("incident_description", "Inactive owner detected."),
            affected_asset_urn=data.get("target_asset_urn", "urn:li:dataset:test"),
            proposed_root_cause=data.get("human_confirmed_root_cause", "Offboarding gap."),
            confirmed_by="api-user",
            inactive_owner_urn=data.get("inactive_owner_urn", "urn:li:corpuser:bob"),
            historical_data=historical,
            future_ownership_data=[{
                "asset_urn": "urn:li:dataset:(urn:li:dataPlatform:bigquery,marketing.campaigns,PROD)",
                "owners": [{"urn": "urn:li:corpuser:diana", "username": "diana", "type": "TECHNICAL_OWNER", "active": False}],
                "domain": "marketing"}])
        return result

    result = asyncio.run(_run())
    metrics = result["backtest_metrics"]
    db.create_run(run_id, "orphaned_ownership")
    db.update_run(run_id, current_step=9, is_complete=True)
    return jsonify({
        "run_id": run_id, "scenario": "orphaned_ownership", "is_complete": True,
        "control_id": result["control"].control_id,
        "inactive_detected": sum(1 for a in result["classified_assets"] if a["inactive_owners"]),
        "replacements": len(result["update_plan"]["proposed_updates"]),
        "precision": metrics.get("precision", 1.0), "recall": metrics.get("recall", 0.0),
    })
