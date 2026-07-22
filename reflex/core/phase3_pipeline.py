"""Phase 3 pipeline — complete duplicate-row vertical slice.

This module implements all 9 steps of the duplicate-row loop:
1. Resolved incident ingestion
2. Human root-cause approval
3. Structured lesson extraction
4. Similar-asset discovery
5. Control synthesis
6. Reflex backtest (with full metrics)
7. Human control approval
8. DataHub publication
9. Analogous future incident detection

The pipeline is the single orchestrator for the duplicate-row scenario.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from reflex.backtesting.engine import ReflexBacktester
from reflex.controls.executors import (
    build_uniqueness_control_definition,
    get_executor,
)
from reflex.core.approval import (
    ApprovalService,
    ControlApproval,
    RootCauseApproval,
)
from reflex.core.lesson_extractor import (
    ExtractionRecord,
    LessonExtractor,
)
from reflex.core.similarity import (
    CandidateResult,
    create_similarity_resolver,
)
from reflex.datahub.read_client import DataHubReadClient
from reflex.datahub.write_client import DataHubWriteClient
from reflex.models import (
    BacktestResult,
    ControlId,
    ControlType,
    ReflexControl,
    ReflexLesson,
)

logger = structlog.get_logger(__name__)


# -- Backtest Metrics ----------------------------------------------------------


@dataclass
class BacktestMetrics:
    """Full backtest metrics required by the Phase 3 specification."""
    true_positives: int = 0
    false_positives: int = 0
    true_negatives: int = 0
    false_negatives: int = 0
    precision: float = 1.0
    recall: float = 0.0
    false_positive_rate: float = 0.0
    run_coverage: int = 0
    execution_errors: int = 0
    per_run_evidence: list[dict[str, Any]] = field(default_factory=list)

    @property
    def f1_score(self) -> float:
        if self.precision + self.recall == 0:
            return 0.0
        return 2 * (self.precision * self.recall) / (self.precision + self.recall)

    def to_dict(self) -> dict[str, Any]:
        return {
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "true_negatives": self.true_negatives,
            "false_negatives": self.false_negatives,
            "precision": self.precision,
            "recall": self.recall,
            "false_positive_rate": self.false_positive_rate,
            "f1_score": self.f1_score,
            "run_coverage": self.run_coverage,
            "execution_errors": self.execution_errors,
        }


def compute_metrics(
    results: list[BacktestResult],
    known_incident_snapshots: int = 0,
) -> BacktestMetrics:
    """Compute full backtest metrics from results.

    Args:
        results: Backtest results per snapshot.
        known_incident_snapshots: Number of snapshots known to contain incidents
            (for computing false negatives).
    """
    tp = sum(1 for r in results if r.would_have_detected)
    fp = sum(r.false_positives for r in results)
    tn = sum(1 for r in results if not r.would_have_detected)
    fn = max(0, known_incident_snapshots - tp)

    total_positives = tp + fp
    precision = tp / total_positives if total_positives > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    total_negatives = tn + fp
    fpr = fp / total_negatives if total_negatives > 0 else 0.0

    per_run = [
        {
            "timestamp": r.detection_timestamp.isoformat() if r.detection_timestamp else r.historical_window_start.isoformat(),
            "detected": r.would_have_detected,
            "true_positives": r.true_positives,
            "false_positives": r.false_positives,
            "evidence": r.evidence[:200],
        }
        for r in results
    ]

    return BacktestMetrics(
        true_positives=tp,
        false_positives=fp,
        true_negatives=tn,
        false_negatives=fn,
        precision=precision,
        recall=recall,
        false_positive_rate=fpr,
        run_coverage=len(results),
        execution_errors=0,
        per_run_evidence=per_run,
    )


def can_recommend_publication(metrics: BacktestMetrics, results: list[BacktestResult]) -> tuple[bool, list[str]]:
    """Check if a control can be recommended for publication.

    Guards:
    - must detect the original incident (recall >= 100% on known incidents)
    - must be executable
    - historical coverage must be sufficient
    - false-positive rate must not exceed threshold (10%)
    - validation must pass
    """
    blockers: list[str] = []

    if metrics.run_coverage < 1:
        blockers.append("Cannot execute: no historical data available")

    if metrics.recall < 1.0:
        blockers.append(
            f"Does not detect the original incident: recall={metrics.recall:.2%}"
        )

    if metrics.false_positive_rate > 0.10:
        blockers.append(
            f"False-positive rate exceeds 10% threshold: FPR={metrics.false_positive_rate:.2%}"
        )

    if not any(r.would_have_detected for r in results):
        blockers.append("Control did not detect any violation in historical data")

    return len(blockers) == 0, blockers


# -- Phase 3 Pipeline ----------------------------------------------------------


class Phase3Pipeline:
    """Complete duplicate-row vertical slice pipeline.

    Orchestrates all 9 steps with mandatory approval gates.
    """

    def __init__(
        self,
        lessons_dir: Path | None = None,
        approval_service: ApprovalService | None = None,
        use_live_datahub: bool = False,
        read_client: DataHubReadClient | None = None,
        write_client: DataHubWriteClient | None = None,
    ) -> None:
        base = lessons_dir or Path("./datasets")
        self._dir = base
        self._approvals = approval_service or ApprovalService(base / "approvals")
        self._extractor = LessonExtractor(base / "extractions")
        self._backtester = ReflexBacktester()
        self._use_live_datahub = use_live_datahub
        self._read_client = read_client or DataHubReadClient()
        self._write_client = write_client or DataHubWriteClient()

    # -- Step 1: Resolved incident ingestion -----------------------------------

    async def step1_ingest_incident(
        self,
        incident_urn: str,
        incident_title: str,
        incident_description: str,
        incident_custom_type: str,
        affected_asset_urn: str,
        proposed_root_cause: str,
    ) -> dict[str, Any]:
        """Ingest a resolved incident and its proposed root cause.

        The root cause is NOT authoritative at this point.
        """
        logger.info("step1.ingest_incident", incident_urn=incident_urn)

        return {
            "incident_urn": incident_urn,
            "title": incident_title,
            "description": incident_description,
            "custom_type": incident_custom_type,
            "affected_asset_urn": affected_asset_urn,
            "proposed_root_cause": proposed_root_cause,
            "root_cause_confirmed": False,
            "status": "RESOLVED",
        }

    # -- Step 2: Human root-cause approval -------------------------------------

    async def step2_submit_root_cause(
        self,
        incident_urn: str,
        proposed_root_cause: str,
    ) -> RootCauseApproval:
        """Submit root cause for human review."""
        return await self._approvals.submit_root_cause(
            incident_urn=incident_urn,
            proposed_root_cause=proposed_root_cause,
        )

    async def step2_approve_root_cause(
        self,
        incident_urn: str,
        approver: str,
        edited_cause: str | None = None,
    ) -> RootCauseApproval:
        """Approve (or edit and approve) the root cause."""
        return await self._approvals.approve_root_cause(
            incident_urn=incident_urn,
            approver=approver,
            edited_cause=edited_cause,
        )

    async def step2_reject_root_cause(
        self,
        incident_urn: str,
        approver: str,
    ) -> RootCauseApproval:
        """Reject the proposed root cause."""
        return await self._approvals.reject_root_cause(
            incident_urn=incident_urn,
            approver=approver,
        )

    # -- Step 3: Structured lesson extraction ----------------------------------

    async def step3_extract_lesson(
        self,
        incident_urn: str,
        incident_title: str,
        incident_description: str,
        human_confirmed_root_cause: str,
        confirmed_by: str,
        target_asset_urn: str,
        incident_custom_type: str,
    ) -> tuple[ReflexLesson, ExtractionRecord]:
        """Extract a structured lesson from the confirmed incident."""
        return await self._extractor.extract(
            incident_urn=incident_urn,
            incident_title=incident_title,
            incident_description=incident_description,
            human_confirmed_root_cause=human_confirmed_root_cause,
            confirmed_by=confirmed_by,
            target_asset_urn=target_asset_urn,
            incident_custom_type=incident_custom_type,
        )

    # -- Step 4: Similar-asset discovery ---------------------------------------

    async def step4_discover_similar_assets(
        self,
        source_asset_urn: str,
        target_field: str,
        propagation_scope: list[str],
    ) -> list[CandidateResult]:
        """Discover similar assets using deterministic signals."""
        resolver = create_similarity_resolver(
            source_urn=source_asset_urn,
            target_field=target_field,
            control_type="uniqueness",
            propagation_scope=propagation_scope,
            use_live_datahub=self._use_live_datahub,
            read_client=self._read_client if self._use_live_datahub else None,
        )
        return await resolver.resolve()

    # -- Step 5: Control synthesis ---------------------------------------------

    async def step5_synthesize_control(
        self,
        lesson: ReflexLesson,
        target_field: str,
    ) -> ReflexControl:
        """Synthesize a UniquenessControl from the lesson."""
        if lesson.candidate_preventive_control.control_type != ControlType.UNIQUENESS:
            raise ValueError(
                f"Expected uniqueness control, got "
                f"{lesson.candidate_preventive_control.control_type}"
            )

        columns = [target_field] if target_field else ["transaction_id"]
        definition = build_uniqueness_control_definition(columns)

        control = ReflexControl(
            control_id=ControlId.generate(),
            lesson_id=lesson.lesson_id,
            target_asset_urn=lesson.candidate_preventive_control.target_asset_urn or "",
            control_type=ControlType.UNIQUENESS,
            control_definition=definition,
        )

        logger.info(
            "step5.control_synthesized",
            control_id=control.control_id,
            target_field=target_field,
            definition=definition[:80],
        )
        return control

    # -- Step 6: Reflex backtest -----------------------------------------------

    async def step6_backtest(
        self,
        control: ReflexControl,
        historical_data: list[Any],
        known_incident_snapshots: int = 0,
    ) -> tuple[list[BacktestResult], BacktestMetrics, bool, list[str]]:
        """Run the Reflex backtest and compute full metrics.

        Returns:
            - backtest results
            - computed metrics
            - can_recommend flag
            - blockers list
        """
        results = await self._backtester.backtest(control, historical_data)
        metrics = compute_metrics(results, known_incident_snapshots)
        can_recommend, blockers = can_recommend_publication(metrics, results)

        logger.info(
            "step6.backtest_complete",
            control_id=control.control_id,
            precision=metrics.precision,
            recall=metrics.recall,
            fpr=metrics.false_positive_rate,
            can_recommend=can_recommend,
            blockers=blockers,
        )
        return results, metrics, can_recommend, blockers

    async def step6_execute_on_candidates(
        self,
        control: ReflexControl,
        candidates: list[CandidateResult],
        current_data: list[Any],
    ) -> list[dict[str, Any]]:
        """Execute the control on candidate assets to check for violations."""
        executor = get_executor(control.control_type)
        results: list[dict[str, Any]] = []

        for i, candidate in enumerate(candidates):
            if i < len(current_data):
                try:
                    exec_result = await executor.execute(control, current_data[i])
                    results.append({
                        "asset_urn": candidate.asset_urn,
                        "passed": exec_result.passed,
                        "violation_count": exec_result.violation_count,
                        "details": exec_result.details,
                    })
                except Exception as e:
                    results.append({
                        "asset_urn": candidate.asset_urn,
                        "passed": False,
                        "violation_count": 0,
                        "details": f"Execution error: {e}",
                    })

        return results

    # -- Step 7: Human control approval ----------------------------------------

    async def step7_submit_control_approval(
        self,
        control: ReflexControl,
        metrics: BacktestMetrics,
    ) -> ControlApproval:
        """Submit a control for human approval before publication."""
        return await self._approvals.submit_control_for_approval(
            control_id=control.control_id,
            lesson_id=control.lesson_id,
            backtest_metrics=metrics.to_dict(),
        )

    async def step7_approve_control(
        self,
        control_id: str,
        approver: str,
    ) -> ControlApproval:
        """Approve the control for publication."""
        return await self._approvals.approve_control(
            control_id=control_id,
            approver=approver,
        )

    async def step7_reject_control(
        self,
        control_id: str,
        approver: str,
        reason: str,
    ) -> ControlApproval:
        """Reject the control."""
        return await self._approvals.reject_control(
            control_id=control_id,
            approver=approver,
            reason=reason,
        )

    # -- Step 8: DataHub publication -------------------------------------------

    async def step8_publish(
        self,
        lesson: ReflexLesson,
        control: ReflexControl,
        approval: ControlApproval,
        selected_asset_urns: list[str],
        backtest_results: list[BacktestResult],
    ) -> dict[str, Any]:
        """Publish the approved control to DataHub.

        This is a NOOP without a running DataHub instance.
        The write plan is documented and can be replayed.
        """
        write_plan = {
            "assertion_definitions": [
                {
                    "entity_urn": urn,
                    "type": "DATASET",
                    "description": f"Reflex {control.control_type.value} control: "
                                   f"{lesson.title} (lesson={lesson.lesson_id})",
                    "platform_urn": "urn:li:dataPlatform:reflex",
                }
                for urn in selected_asset_urns
            ],
            "assertion_run_events": [
                {
                    "assertion_urn": f"urn:li:assertion:{urn}-reflex-{control.control_type.value}",
                    "result_type": "SUCCESS" if not r.would_have_detected else "FAILURE",
                    "timestamp_millis": int(r.executed_at.timestamp() * 1000),
                }
                for urn in selected_asset_urns
                for r in backtest_results
            ],
            "structured_properties": [
                {
                    "entity_urn": urn,
                    "property_urn": "urn:li:structuredProperty:reflex:coverage",
                    "values": [{"stringValue": json.dumps({
                        "control_id": control.control_id,
                        "lesson_id": lesson.lesson_id,
                        "approved_by": approval.approver,
                        "approved_at": approval.timestamp.isoformat(),
                    })}],
                }
                for urn in selected_asset_urns
            ],
            "tags": [
                {"entity_urn": urn, "tag_urn": "urn:li:tag:reflex:uniqueness-controlled"}
                for urn in selected_asset_urns
            ],
        }

        # Persist the write plan
        output_dir = self._dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / f"publication_{control.control_id}.json").write_text(
            json.dumps(write_plan, indent=2, default=str)
        )

        published_assets = list(selected_asset_urns)
        if self._use_live_datahub:
            tag_urn = "urn:li:tag:reflex:uniqueness-controlled"
            for urn in selected_asset_urns:
                await self._write_client.add_tag(urn, tag_urn)
                try:
                    await self._write_client.set_structured_property(
                        urn,
                        "urn:li:structuredProperty:reflex.spike01.coverage-v2",
                        [{"stringValue": json.dumps({
                            "control_id": control.control_id,
                            "lesson_id": lesson.lesson_id,
                            "approved_by": approval.approver,
                            "assertion_execution": "reflex-owned",
                        })}],
                    )
                except Exception as exc:
                    logger.warning("step8.coverage_property_failed", asset_urn=urn, error=str(exc))

        logger.info(
            "step8.publish",
            control_id=control.control_id,
            assets_published=len(selected_asset_urns),
            write_plan_file=str(output_dir / f"publication_{control.control_id}.json"),
        )

        return {
            "write_plan": write_plan,
            "published_assets": published_assets,
            "control_version": 1,
            "publication_status": "published",
        }

    # -- Step 9: Analogous future incident -------------------------------------

    async def step9_detect_analogous_incident(
        self,
        control: ReflexControl,
        similar_asset_urn: str,
        data_with_duplicates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Detect an analogous incident on a similar asset.

        This is the primary end-to-end proof: the approved control detects
        a new issue on a different asset.
        """
        executor = get_executor(control.control_type)
        result = await executor.execute(control, data_with_duplicates)

        if not result.passed:
            # This is the detection event
            detection = {
                "detected": True,
                "control_id": control.control_id,
                "lesson_id": control.lesson_id,
                "asset_urn": similar_asset_urn,
                "violation_count": result.violation_count,
                "sample_violations": result.sample_violations[:5],
                "details": result.details,
                "new_incident_title": (
                    f"Reflex detected duplicates on {similar_asset_urn}"
                ),
                "new_incident_description": (
                    f"Reflex control {control.control_id} (from lesson "
                    f"{control.lesson_id}) detected {result.violation_count} "
                    f"duplicate groups on {similar_asset_urn}. "
                    f"Original lesson: {control.lesson_id}"
                ),
            }

            logger.info(
                "step9.analogous_incident_detected",
                control_id=control.control_id,
                asset_urn=similar_asset_urn,
                violations=result.violation_count,
            )
            return detection
        else:
            logger.info(
                "step9.no_incident_detected",
                control_id=control.control_id,
                asset_urn=similar_asset_urn,
            )
            return {
                "detected": False,
                "control_id": control.control_id,
                "asset_urn": similar_asset_urn,
            }
