"""Core Reflex pipeline — the central loop.

This module orchestrates the complete Reflex workflow:

Resolved incident → confirmed root cause → structured lesson → executable control
→ historical backtest → human approval → publication → discovery of similar assets
→ prevention/detection of analogous future incidents
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from reflex.backtesting.engine import ReflexBacktester, summarize_backtest
from reflex.controls.executors import (
    build_active_ownership_control_definition,
    build_uniqueness_control_definition,
    get_executor,
)
from reflex.core.approval import ApprovalService, ApprovalState
from reflex.core.similarity import (
    candidates_to_similar_assets,
    create_similarity_resolver,
)
from reflex.datahub.read_client import DataHubReadClient
from reflex.datahub.write_client import DataHubWriteClient
from reflex.models import (
    ApprovalDecision,
    BacktestResult,
    Confidence,
    ControlExecutionResult,
    ControlId,
    ControlType,
    FailureCategory,
    FailurePattern,
    LessonId,
    ProposedControl,
    ReflexControl,
    ReflexLesson,
    SimilarAssetCandidate,
)

logger = structlog.get_logger(__name__)


# -- Scenario-specific lesson templates (MVP only) ----------------------------


def build_duplicate_rows_lesson(
    incident_urn: str,
    human_confirmed_root_cause: str,
    confirmed_by: str,
    target_asset_urn: str,
    uniqueness_columns: list[str],
) -> ReflexLesson:
    """Build a ReflexLesson for the duplicate-rows scenario."""
    return ReflexLesson(
        lesson_id=LessonId.generate(),
        source_incident_urn=incident_urn,
        title="Duplicate rows caused by non-idempotent retries",
        human_confirmed_root_cause=human_confirmed_root_cause,
        confirmed_or_edited_by=confirmed_by,
        approval_timestamp=datetime.now(UTC),
        failure_pattern=FailurePattern(
            category=FailureCategory.DATA_QUALITY,
            description="Non-idempotent ingestion retry logic produces duplicate rows",
            indicators=[
                "Duplicate transaction IDs in finance dataset",
                "Multiple rows with identical business keys",
                "Retry logs showing partial-failure recovery attempts",
            ],
        ),
        trigger=f"Resolved incident {incident_urn}",
        vulnerable_characteristics=[
            "Write-only ingestion pipeline without deduplication",
            "Non-idempotent retry logic",
            "Lack of uniqueness constraints on business keys",
        ],
        candidate_preventive_control=ProposedControl(
            control_type=ControlType.UNIQUENESS,
            description="Uniqueness check on business key columns",
            target_asset_urn=target_asset_urn,
            parameters={"columns": uniqueness_columns},
        ),
        intended_propagation_scope=[
            "finance",
            "all datasets with transaction_id columns",
        ],
        confidence=Confidence.HIGH,
        limitations=[
            "Control only detects exact duplicates; near-duplicates may pass",
            "Uniqueness columns must be correctly identified per dataset",
        ],
        provenance="human-confirmed via Reflex MVP pipeline",
    )


def build_orphaned_ownership_lesson(
    incident_urn: str,
    human_confirmed_root_cause: str,
    confirmed_by: str,
    target_asset_urn: str,
) -> ReflexLesson:
    """Build a ReflexLesson for the orphaned-ownership scenario."""
    return ReflexLesson(
        lesson_id=LessonId.generate(),
        source_incident_urn=incident_urn,
        title="Orphaned ownership after employee offboarding",
        human_confirmed_root_cause=human_confirmed_root_cause,
        confirmed_or_edited_by=confirmed_by,
        approval_timestamp=datetime.now(UTC),
        failure_pattern=FailurePattern(
            category=FailureCategory.OWNERSHIP,
            description="Deactivated employees remain as asset owners",
            indicators=[
                "Asset owners with inactive CorpUser status",
                "No operational owner for critical datasets",
                "Offboarding process does not update DataHub ownership",
            ],
        ),
        trigger=f"Resolved incident {incident_urn}",
        vulnerable_characteristics=[
            "Assets owned by individual users rather than groups",
            "No automated ownership review process",
            "Offboarding not integrated with metadata management",
        ],
        candidate_preventive_control=ProposedControl(
            control_type=ControlType.ACTIVE_OWNERSHIP,
            description="Validate that all assets have at least one active TECHNICAL_OWNER",
            target_asset_urn=target_asset_urn,
            parameters={"min_active_owners": 1, "required_owner_types": ["TECHNICAL_OWNER"]},
        ),
        intended_propagation_scope=[
            "all domains",
            "all datasets with individual user owners",
        ],
        confidence=Confidence.HIGH,
        limitations=[
            "Control only checks DataHub ownership; does not verify actual access",
            "Domain-based fallback ownership is a heuristic, not authoritative",
        ],
        provenance="human-confirmed via Reflex MVP pipeline",
    )


# -- Pipeline ------------------------------------------------------------------


class ReflexPipeline:
    """The central Reflex pipeline.

    Orchestrates the complete loop from incident to preventive control.
    Each step is explicit and can be inspected independently.
    """

    def __init__(
        self,
        lessons_dir: Path | None = None,
        approval_required: bool = True,
        non_interactive_test_mode: bool = False,
        use_live_datahub: bool = False,
        read_client: DataHubReadClient | None = None,
        write_client: DataHubWriteClient | None = None,
        approval_service: ApprovalService | None = None,
    ) -> None:
        self.lessons_dir = lessons_dir or Path("./datasets")
        self.approval_required = approval_required
        self.non_interactive_test_mode = non_interactive_test_mode
        self.backtester = ReflexBacktester()
        self.use_live_datahub = use_live_datahub
        self.read_client = read_client or DataHubReadClient()
        self.write_client = write_client or DataHubWriteClient()
        self.approval_service = approval_service or ApprovalService(
            self.lessons_dir / "approvals"
        )

    # -- Step 1: Extract lesson from resolved incident --------------------------

    async def extract_lesson(
        self,
        incident_urn: str,
        scenario: str,
        human_confirmed_root_cause: str,
        confirmed_by: str,
        target_asset_urn: str,
        **scenario_params: Any,
    ) -> ReflexLesson:
        """Extract a structured lesson from a resolved incident.

        For the MVP, lessons are constructed from known scenario templates.
        In production, this step would use an LLM to extract the lesson from
        the incident description.

        When non_interactive_test_mode=False, requires explicit root cause
        approval in the approval service before proceeding.
        """
        # Gate: root cause must be explicitly approved (unless in test mode)
        if not self.non_interactive_test_mode:
            existing_approval = self.approval_service.get_root_cause(incident_urn)
            if existing_approval is None:
                # Submit it and raise — must be explicitly approved
                await self.approval_service.submit_root_cause(
                    incident_urn=incident_urn,
                    proposed_root_cause=human_confirmed_root_cause,
                )
                approval_file = self.lessons_dir / "approvals" / f"root_cause_{_sanitize_urn(incident_urn)}.json"
                raise PipelineApprovalRequired(
                    f"Root cause for {incident_urn} requires explicit human approval. "
                    f"Create approval file at: {approval_file} "
                    f'with content: {{"decision": "approved", "approver": "your-name"}} '
                    f"or run with non_interactive_test_mode=True for automated testing."
                )
            elif existing_approval.state not in (ApprovalState.APPROVED, ApprovalState.REVISED):
                raise PipelineError(
                    f"Root cause for {incident_urn} is in state '{existing_approval.state.value}'. "
                    f"Must be approved before proceeding."
                )

        if scenario == "duplicate_rows":
            columns = scenario_params.get("uniqueness_columns", ["transaction_id"])
            lesson = build_duplicate_rows_lesson(
                incident_urn=incident_urn,
                human_confirmed_root_cause=human_confirmed_root_cause,
                confirmed_by=confirmed_by,
                target_asset_urn=target_asset_urn,
                uniqueness_columns=columns,
            )
        elif scenario == "orphaned_ownership":
            lesson = build_orphaned_ownership_lesson(
                incident_urn=incident_urn,
                human_confirmed_root_cause=human_confirmed_root_cause,
                confirmed_by=confirmed_by,
                target_asset_urn=target_asset_urn,
            )
        else:
            raise ValueError(f"Unknown scenario: {scenario}")

        logger.info(
            "pipeline.lesson_extracted",
            lesson_id=lesson.lesson_id,
            scenario=scenario,
            confirmed_by=confirmed_by,
        )
        return lesson

    # -- Step 2: Synthesize an executable control -------------------------------

    async def synthesize_control(self, lesson: ReflexLesson) -> ReflexControl:
        """Generate an executable ReflexControl from a confirmed lesson."""
        proposed = lesson.candidate_preventive_control

        if proposed.control_type == ControlType.UNIQUENESS:
            columns = proposed.parameters.get("columns", ["transaction_id"])
            definition = build_uniqueness_control_definition(columns)
        elif proposed.control_type == ControlType.ACTIVE_OWNERSHIP:
            min_active = proposed.parameters.get("min_active_owners", 1)
            required_types = proposed.parameters.get("required_owner_types")
            definition = build_active_ownership_control_definition(
                min_active_owners=min_active,
                required_owner_types=required_types,
            )
        else:
            raise ValueError(f"Unknown control type: {proposed.control_type}")

        control = ReflexControl(
            control_id=ControlId.generate(),
            lesson_id=lesson.lesson_id,
            target_asset_urn=proposed.target_asset_urn or lesson.source_incident_urn,
            control_type=proposed.control_type,
            control_definition=definition,
        )

        logger.info(
            "pipeline.control_synthesized",
            control_id=control.control_id,
            control_type=control.control_type.value,
        )
        return control

    # -- Step 3: Backtest against historical data -------------------------------

    async def backtest_control(
        self,
        control: ReflexControl,
        historical_data: list[Any],
    ) -> list[BacktestResult]:
        """Run the control against historical data snapshots."""
        results = await self.backtester.backtest(control, historical_data)
        summary = summarize_backtest(results)

        logger.info(
            "pipeline.backtest_complete",
            control_id=control.control_id,
            would_have_prevented=summary.would_have_prevented,
            detection_rate=summary.detection_rate,
            precision=summary.precision,
        )
        return results

    # -- Step 4: Human approval ------------------------------------------------

    async def request_approval(
        self,
        control: ReflexControl,
        backtest_results: list[BacktestResult],
    ) -> ApprovalDecision:
        """Request human approval for a control. BLOCKING unless test mode.

        - non_interactive_test_mode=True → auto-approves (for automated tests)
        - non_interactive_test_mode=False → requires explicit approval file

        The approval file must contain {"decision": "approved"|"rejected"}.
        Rejected decisions block publication.
        """
        summary = summarize_backtest(backtest_results)

        if self.non_interactive_test_mode:
            # Only auto-approve when explicitly enabled for testing
            logger.info(
                "pipeline.auto_approve_test_mode",
                control_id=control.control_id,
                note="non_interactive_test_mode=True",
            )
            return ApprovalDecision.APPROVED

        # Submit to approval service (creates pending record)
        await self.approval_service.submit_control_for_approval(
            control_id=control.control_id,
            lesson_id=control.lesson_id,
            backtest_metrics={
                "precision": summary.precision,
                "recall": summary.detection_rate,
                "detections": summary.detections,
                "snapshots": summary.total_snapshots,
                "would_have_prevented": summary.would_have_prevented,
            },
        )

        # Check if an explicit approval decision file exists
        approval_file = self.lessons_dir / "approvals" / f"decision_{_sanitize_urn(control.control_id)}.json"

        if approval_file.exists():
            decision_data = json.loads(approval_file.read_text())
            decision = ApprovalDecision(decision_data["decision"])
            approver = decision_data.get("approver", "unknown")

            if decision == ApprovalDecision.APPROVED or decision == ApprovalDecision.MODIFIED:
                revision_notes = decision_data.get("revision_notes", "")
                await self.approval_service.approve_control(
                    control_id=control.control_id,
                    approver=approver,
                    revision_notes=revision_notes,
                )
                logger.info("pipeline.control_approved", control_id=control.control_id, approver=approver)
                return decision
            elif decision == ApprovalDecision.REJECTED:
                await self.approval_service.reject_control(
                    control_id=control.control_id,
                    approver=approver,
                    reason=decision_data.get("reason", ""),
                )
                logger.info("pipeline.control_rejected", control_id=control.control_id, approver=approver)
                return ApprovalDecision.REJECTED

        # No decision yet — pipeline cannot proceed
        raise PipelineApprovalRequired(
            f"Control {control.control_id} requires explicit human approval. "
            f"Create approval file at: {approval_file} "
            f'with content: {{"decision": "approved", "approver": "your-name"}} '
            f"or run with non_interactive_test_mode=True for automated testing."
        )

    # -- Step 5: Discover similar assets ----------------------------------------

    async def discover_similar_assets(
        self,
        lesson: ReflexLesson,
        source_asset_urn: str,
        max_candidates: int = 10,
    ) -> list[SimilarAssetCandidate]:
        """Discover assets similar to the source asset through graph traversal.

        Uses the deterministic SimilarityResolver with inspectable signals:
        - Same domain
        - Shared tags
        - Compatible schema (target field presence)
        - Append-only vulnerability
        - Similar lineage position
        - Absence of existing Reflex control
        """
        target_field = lesson.candidate_preventive_control.parameters.get(
            "target_field",
            lesson.candidate_preventive_control.parameters.get("columns", ["transaction_id"])[0],
        )
        resolver = create_similarity_resolver(
            source_urn=source_asset_urn,
            target_field=target_field,
            control_type=lesson.candidate_preventive_control.control_type.value,
            propagation_scope=lesson.intended_propagation_scope,
            use_live_datahub=self.use_live_datahub,
            read_client=self.read_client if self.use_live_datahub else None,
        )
        candidates = await resolver.resolve(max_candidates=max_candidates)
        return candidates_to_similar_assets(candidates)

    # -- Step 6: Execute control on similar assets (detection) -------------------

    async def detect_on_similar_assets(
        self,
        control: ReflexControl,
        similar_assets: list[SimilarAssetCandidate],
        current_data: list[Any] | dict[str, Any],
    ) -> list[ControlExecutionResult]:
        """Execute the control on similar assets to detect analogous issues."""
        executor = get_executor(control.control_type)
        results: list[ControlExecutionResult] = []

        if isinstance(current_data, dict):
            executions = [
                (asset, current_data[asset.asset_urn])
                for asset in similar_assets
                if asset.asset_urn in current_data
            ]
        elif current_data and isinstance(current_data[0], dict):
            # A single row collection is the current observation for every
            # selected analogous asset. Do not zip rows to assets, which
            # would pass one dict (and then its string keys) to the executor.
            executions = [(asset, current_data) for asset in similar_assets]
        else:
            executions = list(zip(similar_assets, current_data, strict=False))

        for asset, asset_data in executions:
            result = await executor.execute(control, asset_data)
            # Executors operate on rows/metadata and therefore do not know the
            # propagated asset URN. Attach it here so downstream incident and
            # DataHub write-back logic identifies the correct asset.
            results.append(result.model_copy(update={"asset_urn": asset.asset_urn}))

        detections = [r for r in results if not r.passed]
        logger.info(
            "pipeline.detection_complete",
            control_id=control.control_id,
            assets_checked=len(results),
            violations_found=len(detections),
        )
        return results

    # -- Full pipeline ----------------------------------------------------------

    async def run(
        self,
        incident_urn: str,
        scenario: str,
        human_confirmed_root_cause: str,
        confirmed_by: str,
        target_asset_urn: str,
        historical_data: list[Any],
        current_data: list[Any] | None = None,
        **scenario_params: Any,
    ) -> dict[str, Any]:
        """Run the complete Reflex pipeline for one scenario.

        Returns a dictionary with all artifacts produced.
        """
        logger.info("pipeline.start", incident_urn=incident_urn, scenario=scenario)

        # Step 1: Extract lesson
        lesson = await self.extract_lesson(
            incident_urn=incident_urn,
            scenario=scenario,
            human_confirmed_root_cause=human_confirmed_root_cause,
            confirmed_by=confirmed_by,
            target_asset_urn=target_asset_urn,
            **scenario_params,
        )

        if not lesson.is_confirmed:
            raise PipelineError("Cannot proceed: root cause is not human-confirmed.")

        # Step 2: Synthesize control
        control = await self.synthesize_control(lesson)

        # Step 3: Backtest
        backtest_results = await self.backtest_control(control, historical_data)

        # Step 4: Approval
        if self.approval_required:
            decision = await self.request_approval(control, backtest_results)
            if decision == ApprovalDecision.REJECTED:
                raise PipelineError(f"Control {control.control_id} was rejected.")

        # Step 5: Discover similar assets
        similar_assets = await self.discover_similar_assets(
            lesson, target_asset_urn
        )

        # Step 6: Detect on similar assets
        detection_results: list[ControlExecutionResult] = []
        if current_data:
            detection_results = await self.detect_on_similar_assets(
                control, similar_assets, current_data
            )

        logger.info("pipeline.complete", control_id=control.control_id)

        # Step 7: Publish to DataHub (only when live mode is active)
        publication_result = None
        if self.use_live_datahub:
            publication_result = await self.publish_to_datahub(
                lesson=lesson,
                control=control,
                similar_assets=similar_assets,
                backtest_results=backtest_results,
            )
            # Step 8: Create incidents for detected failures
            for dr in detection_results:
                if not dr.passed and self.use_live_datahub:
                    await self.raise_incident_for_detection(
                        control=control,
                        lesson=lesson,
                        detection_result=dr,
                    )

        return {
            "lesson": lesson,
            "control": control,
            "backtest_results": backtest_results,
            "backtest_summary": summarize_backtest(backtest_results),
            "similar_assets": similar_assets,
            "detection_results": detection_results,
            "publication_result": publication_result,
        }

    # -- Step 7a: Publish to live DataHub ---------------------------------------

    async def publish_to_datahub(
        self,
        lesson: ReflexLesson,
        control: ReflexControl,
        similar_assets: list[SimilarAssetCandidate],
        backtest_results: list[BacktestResult],
    ) -> dict[str, Any]:
        """Publish control metadata and run events to live DataHub OSS.

        Does NOT call run_assertion() — Cloud-only. Reflex owns execution.
        """
        published: list[str] = []
        coverage_written: list[str] = []
        tag_urn = "urn:li:tag:reflex:uniqueness-controlled"

        local_artifact = self.lessons_dir / "output" / f"reflex_execution_{control.control_id}.json"
        local_artifact.parent.mkdir(parents=True, exist_ok=True)
        local_artifact.write_text(json.dumps({
            "control_id": control.control_id,
            "lesson_id": lesson.lesson_id,
            "assertion_definitions": "reflex-owned",
            "assertion_run_events": "reflex-owned",
            "backtest_results": [br.model_dump(mode="json") for br in backtest_results],
        }, indent=2, default=str))

        for asset in similar_assets:
            try:
                await self.write_client.add_tag(asset.asset_urn, tag_urn)
                coverage = json.dumps({
                    "control_id": control.control_id,
                    "lesson_id": lesson.lesson_id,
                    "execution_artifact": str(local_artifact),
                    "assertion_execution": "reflex-owned",
                })
                try:
                    await self.write_client.set_structured_property(
                        asset.asset_urn,
                        "urn:li:structuredProperty:reflex.spike01.coverage-v2",
                        [{"stringValue": coverage}],
                    )
                    coverage_written.append(asset.asset_urn)
                except Exception as e:
                    logger.warning("pipeline.coverage_property_failed", asset_urn=asset.asset_urn, error=str(e))
                published.append(asset.asset_urn)
                logger.info("pipeline.published_asset", asset_urn=asset.asset_urn)
            except Exception as e:
                logger.warning("pipeline.publish_failed", asset_urn=asset.asset_urn, error=str(e))

        return {
            "published_assets": published,
            "count": len(published),
            "coverage_written": coverage_written,
            "assertion_definitions": "reflex-owned",
            "assertion_run_events": "reflex-owned",
            "execution_artifact": str(local_artifact),
        }

    # -- Step 8a: Raise incident for detected failure ---------------------------

    async def raise_incident_for_detection(
        self,
        control: ReflexControl,
        lesson: ReflexLesson,
        detection_result: ControlExecutionResult,
    ) -> str | None:
        """Create a new DataHub incident when a control detects a violation."""
        try:
            urn = await self.write_client.raise_incident(
                title=f"Reflex detected {control.control_type.value} violation on {detection_result.asset_urn}",
                description=(
                    f"Reflex control {control.control_id} (lesson {lesson.lesson_id}) "
                    f"detected {detection_result.violation_count} violations. "
                    f"Details: {detection_result.details}"
                ),
                resource_urn=detection_result.asset_urn,
                custom_type="REFLEX_DETECTED",
                source_type="MANUAL",
            )
            logger.info("pipeline.incident_raised", incident_urn=urn, control_id=control.control_id)
            return urn
        except Exception as e:
            logger.warning("pipeline.incident_raise_failed", error=str(e))
            return None


class PipelineError(Exception):
    """Raised when the Reflex pipeline cannot proceed."""


class PipelineApprovalRequired(PipelineError):
    """Raised when explicit human approval is required but not yet provided."""


def _sanitize_urn(urn: str) -> str:
    """Sanitize a URN for use in a filename."""
    return urn.replace(":", "_").replace("(", "").replace(")", "").replace(",", "_")[:100]
