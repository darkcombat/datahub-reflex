"""Stateful demo runner for the Reflex UI.

Wraps ReflexPipeline, captures state at each of the 9 steps,
and exposes it for the UI to render. Supports reset and interactive
approval through explicit human gates.

All state is real application state from ReflexPipeline.run().
Nothing is fabricated.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from reflex.core.phase3_pipeline import Phase3Pipeline
from reflex.core.phase4_pipeline import Phase4Pipeline
from reflex.core.pipeline import (
    ReflexPipeline,
)

# ---------------------------------------------------------------------------
# Demo state model — serializable snapshot of the Reflex loop
# ---------------------------------------------------------------------------


@dataclass
class DemoState:
    """Serializable state of a single demo run."""

    # Step timing
    started_at: str = ""
    completed_at: str = ""

    # Step 1: Resolved incident
    incident_urn: str = ""
    incident_title: str = ""
    incident_description: str = ""
    incident_affected_asset: str = ""

    # Step 2: Human-confirmed root cause
    root_cause: str = ""
    confirmed_by: str = ""
    root_cause_approval_state: str = ""  # pending | approved | rejected
    root_cause_approval_timestamp: str = ""

    # Step 3: Structured lesson
    lesson_id: str = ""
    lesson_title: str = ""
    failure_pattern: str = ""
    vulnerable_characteristics: list[str] = field(default_factory=list)
    lesson_confidence: str = ""
    lesson_assumptions: list[str] = field(default_factory=list)
    lesson_limitations: list[str] = field(default_factory=list)
    lesson_provenance: str = ""

    # Step 4: Proposed preventive control
    control_id: str = ""
    control_type: str = ""
    control_definition: str = ""
    control_target_field: str = ""

    # Step 5: Similar assets + signals
    similar_assets: list[dict[str, Any]] = field(default_factory=list)
    similarity_mode: str = "synthetic"  # "synthetic" | "live-datahub"

    # Step 6: Backtest metrics
    backtest_snapshots: int = 0
    backtest_detections: int = 0
    backtest_precision: float = 0.0
    backtest_recall: float = 0.0
    backtest_fpr: float = 0.0
    backtest_false_positives: int = 0
    backtest_false_negatives: int = 0
    backtest_execution_failures: int = 0
    backtest_would_have_prevented: bool = False
    backtest_results_detail: list[dict[str, Any]] = field(default_factory=list)
    backtest_data_provenance: str = "SYNTHETIC (JSON snapshots)"

    # Step 7: Approval
    approval_state: str = "pending"  # pending | approved | rejected
    approval_approver: str = ""
    approval_notes: str = ""
    approval_timestamp: str = ""
    approval_test_mode: bool = False

    # Step 8: DataHub publication
    publication_assets: list[str] = field(default_factory=list)
    publication_count: int = 0
    publication_mode: str = "reflex-owned"  # "reflex-owned" | "live-datahub"
    publication_skipped_cloud: list[str] = field(default_factory=list)
    publication_reflex_owned: list[str] = field(default_factory=list)
    publication_datahub_owned: list[str] = field(default_factory=list)

    # Step 9: Analogous future incident detection
    detection_assets_checked: int = 0
    detection_violations: list[dict[str, Any]] = field(default_factory=list)

    # Meta
    current_step: int = 0  # 0-9
    error: str = ""
    is_complete: bool = False
    is_demo_mode: bool = False
    mode_label: str = "SYNTHETIC MODE"  # "SYNTHETIC MODE" | "LIVE DATAHUB MODE"


# ---------------------------------------------------------------------------
# Demo runner
# ---------------------------------------------------------------------------


class DemoRunner:
    """Runs the Reflex pipeline step-by-step, capturing state for the UI.

    Usage:
        runner = DemoRunner(lessons_dir=Path("./datasets"))
        await runner.run_full(incident_urn="...", scenario="duplicate_rows", ...)
        state = runner.state  # -> DemoState dataclass
    """

    def __init__(
        self,
        lessons_dir: Path | None = None,
        use_live_datahub: bool = False,
    ) -> None:
        self.lessons_dir = lessons_dir or Path("./datasets")
        self.use_live_datahub = use_live_datahub
        self.state = DemoState(
            similarity_mode="live-datahub" if use_live_datahub else "synthetic",
            publication_mode="live-datahub" if use_live_datahub else "reflex-owned",
            mode_label="LIVE DATAHUB MODE" if use_live_datahub else "SYNTHETIC MODE",
            backtest_data_provenance="SYNTHETIC (JSON snapshots)",
        )
        self._phase3_context: dict[str, Any] = {}

    def reset(self) -> None:
        """Reset to initial state."""
        self.state = DemoState(
            similarity_mode="live-datahub" if self.use_live_datahub else "synthetic",
            publication_mode="live-datahub" if self.use_live_datahub else "reflex-owned",
            mode_label="LIVE DATAHUB MODE" if self.use_live_datahub else "SYNTHETIC MODE",
            backtest_data_provenance="SYNTHETIC (JSON snapshots)",
        )
        self._phase3_context = {}

    async def run_full(
        self,
        incident_urn: str,
        scenario: str,
        human_confirmed_root_cause: str,
        confirmed_by: str,
        target_asset_urn: str,
        historical_data: list[Any],
        current_data: list[Any] | None = None,
        uniqueness_columns: list[str] | None = None,
    ) -> DemoState:
        """Run the full pipeline and capture all state."""
        self.state.started_at = datetime.now(UTC).isoformat()
        self.state.incident_urn = incident_urn
        self.state.root_cause = human_confirmed_root_cause
        self.state.confirmed_by = confirmed_by
        self.state.incident_affected_asset = target_asset_urn
        self.state.current_step = 1
        self.state.publication_skipped_cloud = [
            "upsertAssertion (removed in OSS v1.5.0.6)",
            "assertion run events (REST endpoint 404s in OSS v1.5.0.6)",
        ]
        self.state.publication_reflex_owned = [
            "Assertion definitions",
            "Backtest run events",
            "Control execution results",
        ]
        self.state.publication_datahub_owned = [
            "Incidents (raiseIncident)",
            "Ownership updates (addOwner)",
            "Tags (createTag/addTag)",
            "Structured properties",
        ]

        # Map scenario to incident title/description
        if scenario == "duplicate_rows":
            self.state.incident_title = "Duplicate transactions detected"
            self.state.incident_description = (
                "A partial ingestion failure caused the pipeline to retry, "
                "inserting ~340 duplicate transaction IDs into the dataset."
            )
        elif scenario == "orphaned_ownership":
            self.state.incident_title = "Inactive owner detected"
            self.state.incident_description = (
                "An employee was deactivated but remains TECHNICAL_OWNER "
                "of critical datasets. Assets are effectively orphaned."
            )

        # The duplicate-row UI follows the explicit nine-step pipeline. It
        # stops at each human approval gate instead of using test-mode
        # auto-approval.
        if scenario == "duplicate_rows":
            phase3 = Phase3Pipeline(
                lessons_dir=self.lessons_dir,
                use_live_datahub=self.use_live_datahub,
            )
            await phase3.step1_ingest_incident(
                incident_urn=incident_urn,
                incident_title=self.state.incident_title,
                incident_description=self.state.incident_description,
                incident_custom_type="DATA_QUALITY",
                affected_asset_urn=target_asset_urn,
                proposed_root_cause=human_confirmed_root_cause,
            )
            await phase3.step2_submit_root_cause(
                incident_urn=incident_urn,
                proposed_root_cause=human_confirmed_root_cause,
            )
            self._phase3_context = {
                "pipeline": phase3,
                "incident_urn": incident_urn,
                "incident_title": self.state.incident_title,
                "incident_description": self.state.incident_description,
                "root_cause": human_confirmed_root_cause,
                "confirmed_by": confirmed_by,
                "target_asset_urn": target_asset_urn,
                "historical_data": historical_data,
                "uniqueness_columns": uniqueness_columns or ["transaction_id"],
                "analogous_asset_urn": next(
                    (
                        urn for urn in (current_data or {})
                        if urn != target_asset_urn
                    ),
                    "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_monthly_ledger,PROD)",
                ),
            }
            self.state.current_step = 2
            self.state.approval_state = "pending"
            self.state.approval_approver = ""
            self.state.approval_notes = "Waiting for explicit human root-cause approval."
            self.state.is_demo_mode = False
            return self.state

        if scenario == "orphaned_ownership":
            phase4 = Phase4Pipeline(
                lessons_dir=self.lessons_dir,
                use_live_datahub=self.use_live_datahub,
            )
            await phase4.step1_ingest_incident(
                incident_urn=incident_urn,
                incident_title=self.state.incident_title,
                incident_description=self.state.incident_description,
                affected_asset_urn=target_asset_urn,
                proposed_root_cause=human_confirmed_root_cause,
            )
            await phase4._approvals.submit_root_cause(incident_urn, human_confirmed_root_cause)
            self._phase3_context = {
                "pipeline": phase4,
                "scenario": scenario,
                "incident_urn": incident_urn,
                "incident_title": self.state.incident_title,
                "incident_description": self.state.incident_description,
                "root_cause": human_confirmed_root_cause,
                "confirmed_by": confirmed_by,
                "target_asset_urn": target_asset_urn,
                "historical_data": historical_data,
                "inactive_owner_urn": "urn:li:corpuser:bob",
                "future_ownership_data": ([{"owner": "diana", "type": "TECHNICAL_OWNER", "active": False}] if current_data is None else current_data),
            }
            self.state.current_step = 2
            self.state.approval_state = "pending"
            self.state.approval_approver = ""
            self.state.approval_notes = "Waiting for explicit human root-cause approval."
            self.state.is_demo_mode = False
            return self.state

        try:
            # Create pipeline in demo mode (auto-approves, uses synthetic similarity)
            pipeline = ReflexPipeline(
                lessons_dir=self.lessons_dir,
                non_interactive_test_mode=True,  # demo mode: auto-approve
                use_live_datahub=self.use_live_datahub,
            )

            kwargs: dict[str, Any] = {}
            if uniqueness_columns:
                kwargs["uniqueness_columns"] = uniqueness_columns

            result = await pipeline.run(
                incident_urn=incident_urn,
                scenario=scenario,
                human_confirmed_root_cause=human_confirmed_root_cause,
                confirmed_by=confirmed_by,
                target_asset_urn=target_asset_urn,
                historical_data=historical_data,
                current_data=current_data,
                **kwargs,
            )

            # -- Populate state from pipeline result --

            # Step 3: Lesson
            lesson = result["lesson"]
            self.state.lesson_id = lesson.lesson_id
            self.state.lesson_title = lesson.title
            self.state.failure_pattern = lesson.failure_pattern.value if hasattr(lesson.failure_pattern, 'value') else str(lesson.failure_pattern)
            self.state.vulnerable_characteristics = list(lesson.vulnerable_characteristics)
            self.state.lesson_confidence = lesson.confidence.value if hasattr(lesson.confidence, 'value') else str(lesson.confidence)
            self.state.current_step = 3

            # Step 4: Control
            control = result["control"]
            self.state.control_id = control.control_id
            self.state.control_type = control.control_type.value if hasattr(control.control_type, 'value') else str(control.control_type)
            # Truncate long control definitions for display
            cd = control.control_definition
            self.state.control_definition = cd[:500] + ("..." if len(cd) > 500 else "")
            self.state.current_step = 4

            # Step 5: Similar assets
            sim_assets = result.get("similar_assets", [])
            self.state.similar_assets = [
                {
                    "asset_urn": a.asset_urn if hasattr(a, 'asset_urn') else str(a),
                    "confidence": a.confidence.value if hasattr(a.confidence, 'value') else str(getattr(a, 'confidence', 'unknown')),
                    "rationale": getattr(a, 'similarity_rationale', ''),
                    "domain": getattr(a, 'domain', ''),
                }
                for a in sim_assets
            ]
            self.state.current_step = 5

            # Step 6: Backtest
            summary = result["backtest_summary"]
            self.state.backtest_snapshots = summary.total_snapshots
            self.state.backtest_detections = summary.detections
            self.state.backtest_precision = round(summary.precision, 3)
            self.state.backtest_recall = round(summary.detection_rate, 3)
            self.state.backtest_would_have_prevented = summary.would_have_prevented

            # Backtest per-snapshot details
            bresults = result.get("backtest_results", [])
            self.state.backtest_results_detail = [
                {
                    "timestamp": br.executed_at.isoformat() if hasattr(br, 'executed_at') else "",
                    "would_have_detected": br.would_have_detected if hasattr(br, 'would_have_detected') else False,
                    "true_positives": br.true_positives if hasattr(br, 'true_positives') else 0,
                    "false_positives": br.false_positives if hasattr(br, 'false_positives') else 0,
                }
                for br in bresults
            ]
            self.state.current_step = 6

            # Step 7: Approval (demo mode = auto-approved)
            self.state.approval_state = "approved"
            self.state.approval_approver = "demo-mode (non_interactive_test_mode)"
            self.state.approval_notes = "Auto-approved in demo mode. In production, requires explicit human decision file."
            self.state.current_step = 7

            # Step 8: Publication
            pub = result.get("publication_result")
            if pub and isinstance(pub, dict):
                self.state.publication_assets = pub.get("published_assets", [])
                self.state.publication_count = pub.get("count", 0)
            else:
                self.state.publication_count = 0
                if not self.use_live_datahub:
                    self.state.publication_mode = "reflex-owned (no DataHub connected)"
            self.state.current_step = 8

            # Step 9: Detection
            detections = result.get("detection_results", [])
            self.state.detection_assets_checked = len(detections)
            self.state.detection_violations = [
                {
                    "asset_urn": d.asset_urn if hasattr(d, 'asset_urn') else str(d),
                    "passed": d.passed if hasattr(d, 'passed') else True,
                    "violation_count": d.violation_count if hasattr(d, 'violation_count') else 0,
                    "details": str(getattr(d, 'details', ''))[:200],
                }
                for d in detections
            ]
            self.state.current_step = 9

            self.state.is_complete = True
            self.state.completed_at = datetime.now(UTC).isoformat()

        except Exception as e:
            self.state.error = str(e)

        return self.state

    def to_dict(self) -> dict[str, Any]:
        """Serialize state to a JSON-compatible dict."""
        return asdict(self.state)

    async def apply_approval(self, decision: str, approver: str, notes: str = "") -> DemoState:
        """Apply one explicit approval and advance the manual duplicate-row flow."""
        if not self._phase3_context:
            self.state.error = "No pending manual approval is available."
            return self.state

        phase3: Phase3Pipeline = self._phase3_context["pipeline"]
        incident_urn = self._phase3_context["incident_urn"]

        if self._phase3_context.get("scenario") == "orphaned_ownership":
            phase4: Phase4Pipeline = self._phase3_context["pipeline"]
            if decision != "approved":
                self.state.approval_state = "rejected"
                self.state.approval_approver = approver
                self.state.approval_notes = notes or "Rejected by human approver."
                self.state.error = "Approval rejected; no ownership plan was published."
                return self.state
            if self.state.current_step == 2:
                self.state.root_cause_approval_state = "approved"
                self.state.root_cause_approval_timestamp = datetime.now(UTC).isoformat()
                root = await phase4.step2_approve_root_cause(incident_urn, approver)
                lesson, _ = await phase4.step3_extract_lesson(
                    incident_urn, self._phase3_context["incident_title"],
                    self._phase3_context["incident_description"], root.final_root_cause,
                    approver, self._phase3_context["target_asset_urn"],
                )
                affected = await phase4.step4_identify_affected_assets(self._phase3_context["inactive_owner_urn"])
                classified = await phase4.step5_classify_ownership(affected)
                replacements = await phase4.step6_find_replacements(classified)
                control = await phase4.step7_synthesize_control(lesson)
                results, metrics, can_recommend, blockers = await phase4.step8_backtest(
                    control, self._phase3_context["historical_data"], known_incident_snapshots=1,
                )
                if not can_recommend:
                    self.state.error = "Control cannot be recommended: " + "; ".join(blockers)
                    return self.state
                await phase4._approvals.submit_control_for_approval(control.control_id, control.lesson_id, metrics.to_dict())
                self._phase3_context.update({"lesson": lesson, "control": control, "affected": replacements, "results": results, "metrics": metrics})
                self.state.lesson_id = lesson.lesson_id
                self.state.lesson_title = lesson.title
                self.state.control_id = control.control_id
                self.state.control_type = control.control_type.value
                self.state.control_definition = control.control_definition
                self.state.backtest_snapshots = metrics.run_coverage
                self.state.backtest_detections = metrics.true_positives
                self.state.backtest_precision = metrics.precision
                self.state.backtest_recall = metrics.recall
                self.state.backtest_would_have_prevented = True
                self.state.similar_assets = [{"asset_urn": r.asset_urn, "rationale": r.replacement_rationale} for r in replacements]
                self.state.approval_state = "pending"
                self.state.approval_notes = "Ownership control backtested. Waiting for explicit publication approval."
                self.state.current_step = 7
                return self.state
            if self.state.current_step == 7:
                control = self._phase3_context["control"]
                approval = await phase4.step9_approve(control, self._phase3_context["metrics"], approver)
                update_plan = await phase4.step10_preserve_and_update(self._phase3_context["affected"], approval)
                coverage = await phase4.step12_mark_coverage(control, self._phase3_context["lesson"], self._phase3_context["affected"])
                detection = await phase4.step13_detect_future(control, self._phase3_context["future_ownership_data"])
                self.state.approval_state = "approved"
                self.state.approval_approver = approver
                self.state.approval_notes = notes or "Control approved for publication."
                self.state.publication_count = len(update_plan.get("proposed_updates", []))
                self.state.publication_assets = [u["asset_urn"] for u in update_plan.get("proposed_updates", [])]
                self.state.detection_violations = [detection] if detection.get("detected") else []
                self.state.detection_assets_checked = 1
                self.state.current_step = 9
                self.state.is_complete = True
                self.state.completed_at = datetime.now(UTC).isoformat()
                return self.state

        if decision != "approved":
            self.state.approval_state = "rejected"
            self.state.approval_approver = approver
            self.state.approval_notes = notes or "Rejected by human approver."
            self.state.approval_timestamp = datetime.now(UTC).isoformat()
            self.state.error = "Approval rejected; no lesson or control was published."
            return self.state

        if self.state.current_step == 2:
            self.state.root_cause_approval_state = "approved"
            self.state.root_cause_approval_timestamp = datetime.now(UTC).isoformat()
            root_approval = await phase3.step2_approve_root_cause(
                incident_urn=incident_urn,
                approver=approver,
            )
            lesson, _ = await phase3.step3_extract_lesson(
                incident_urn=incident_urn,
                incident_title=self._phase3_context["incident_title"],
                incident_description=self._phase3_context["incident_description"],
                human_confirmed_root_cause=root_approval.final_root_cause,
                confirmed_by=approver,
                target_asset_urn=self._phase3_context["target_asset_urn"],
                incident_custom_type="DATA_QUALITY",
            )
            candidates = await phase3.step4_discover_similar_assets(
                source_asset_urn=self._phase3_context["target_asset_urn"],
                target_field=self._phase3_context["uniqueness_columns"][0],
                propagation_scope=lesson.intended_propagation_scope,
            )
            control = await phase3.step5_synthesize_control(
                lesson=lesson,
                target_field=self._phase3_context["uniqueness_columns"][0],
            )
            backtest_results, metrics, can_recommend, blockers = await phase3.step6_backtest(
                control=control,
                historical_data=self._phase3_context["historical_data"],
                known_incident_snapshots=2,
            )
            if not can_recommend:
                self.state.error = "Control cannot be recommended: " + "; ".join(blockers)
                return self.state
            await phase3.step7_submit_control_approval(control, metrics)
            self._phase3_context.update({
                "lesson": lesson,
                "control": control,
                "candidates": candidates,
                "backtest_results": backtest_results,
                "metrics": metrics,
            })
            self.state.lesson_id = lesson.lesson_id
            self.state.lesson_title = lesson.title
            self.state.failure_pattern = str(
                getattr(lesson.failure_pattern, "value", lesson.failure_pattern)
            )
            self.state.vulnerable_characteristics = list(lesson.vulnerable_characteristics)
            self.state.lesson_confidence = str(lesson.confidence.value)
            self.state.control_id = control.control_id
            self.state.control_type = control.control_type.value
            self.state.control_definition = control.control_definition
            self.state.similar_assets = [
                {
                    "asset_urn": candidate.asset_urn,
                    "confidence": candidate.score,
                    "rationale": candidate.explanation,
                }
                for candidate in candidates
                if candidate.selected
            ]
            self.state.backtest_snapshots = metrics.run_coverage
            self.state.backtest_detections = metrics.true_positives
            self.state.backtest_precision = metrics.precision
            self.state.backtest_recall = metrics.recall
            self.state.backtest_would_have_prevented = True
            self.state.approval_state = "pending"
            self.state.approval_approver = ""
            self.state.approval_notes = "Control backtested. Waiting for explicit publication approval."
            self.state.current_step = 7
            return self.state

        if self.state.current_step == 7:
            control = self._phase3_context["control"]
            lesson = self._phase3_context["lesson"]
            approval = await phase3.step7_approve_control(control.control_id, approver)
            selected = [c.asset_urn for c in self._phase3_context["candidates"] if c.selected]
            publication = await phase3.step8_publish(
                lesson=lesson,
                control=control,
                approval=approval,
                selected_asset_urns=selected,
                backtest_results=self._phase3_context["backtest_results"],
            )
            analogous = self._phase3_context.get(
                "analogous_asset_urn",
                "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_monthly_ledger,PROD)",
            )
            future_rows = self._phase3_context["historical_data"][-2][1]
            detection = await phase3.step9_detect_analogous_incident(control, analogous, future_rows)
            self.state.approval_state = "approved"
            self.state.approval_approver = approver
            self.state.approval_notes = notes or "Control approved for publication."
            self.state.publication_assets = selected
            self.state.publication_count = len(selected)
            self.state.detection_assets_checked = 1
            self.state.detection_violations = [detection] if detection.get("detected") else []
            self.state.current_step = 9
            self.state.is_complete = True
            self.state.completed_at = datetime.now(UTC).isoformat()
            return self.state

        self.state.error = f"Unexpected approval state at step {self.state.current_step}."
        return self.state


# ---------------------------------------------------------------------------
# Historical data builder (synthetic — Reflex-owned)
# ---------------------------------------------------------------------------


def build_duplicate_rows_history(days: int = 8) -> list[tuple[datetime, list[dict]]]:
    """Build synthetic historical snapshots for the demo.

    SYNTHETIC — Reflex-owned. Not from DataHub.
    """
    now = datetime.now(UTC)
    base = [
        {"transaction_id": f"TXN-{i:03d}", "amount": 100.0 * i}
        for i in range(1, 11)
    ]
    dup_row = [
        {"transaction_id": "TXN-003", "amount": 300.0},
        {"transaction_id": "TXN-007", "amount": 700.0},
    ]
    data: list[tuple[datetime, list[dict]]] = []
    for d in range(days, 0, -1):
        snapshot = list(base)
        if d <= 2:
            snapshot.extend(dup_row)
        data.append((now - timedelta(days=d), snapshot))
    return data


def build_orphaned_ownership_history(days: int = 8) -> list[tuple[datetime, list[dict]]]:
    """Build synthetic ownership snapshots for the demo.

    SYNTHETIC — Reflex-owned. Not from DataHub.
    """
    now = datetime.now(UTC)
    active_owners = [
        {"owner": "alice", "type": "TECHNICAL_OWNER", "active": True},
        {"owner": "charlie", "type": "TECHNICAL_OWNER", "active": True},
    ]
    inactive_owners = [
        {"owner": "bob", "type": "TECHNICAL_OWNER", "active": False},
        {"owner": "alice", "type": "TECHNICAL_OWNER", "active": True},
    ]
    data: list[tuple[datetime, list[dict]]] = []
    for d in range(days, 0, -1):
        owners = inactive_owners if d == 1 else active_owners
        data.append((now - timedelta(days=d), owners))
    return data
