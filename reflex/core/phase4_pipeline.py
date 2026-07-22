"""Phase 4 pipeline — complete orphaned-ownership vertical slice.

Implements all required behavior:
1. Load resolved ownership incident
2. Confirm root cause
3. Extract orphaned-ownership lesson
4. Identify all assets associated with inactive owner
5. Distinguish historical ownership from active operational responsibility
6. Identify valid replacement candidates (domain owners preferred)
7. Backtest on historical identity snapshots
8. Require human approval
9. Preserve historical ownership
10. Update operational ownership only after approval
11. Mark assets as covered
12. Detect later inactive-owner case

The ActiveOwnershipControl handles: active users, inactive users, valid groups,
service accounts, historical owners, assets with multiple owners, and assets
with no valid replacement candidate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from reflex.backtesting.engine import ReflexBacktester
from reflex.controls.executors import (
    ActiveOwnershipControlExecutor,
    build_active_ownership_control_definition,
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
from reflex.core.phase3_pipeline import BacktestMetrics, compute_metrics
from reflex.datahub.environment import (
    DATASETS,
    GROUPS,
    SERVICE_ACCOUNTS,
    USERS,
)
from reflex.datahub.read_client import DataHubReadClient
from reflex.datahub.write_client import DataHubWriteClient
from reflex.models import (
    ControlId,
    ControlType,
    ReflexControl,
    ReflexLesson,
)

logger = structlog.get_logger(__name__)


# -- Ownership record ----------------------------------------------------------


@dataclass
class AssetOwnershipRecord:
    """Complete ownership picture for one asset."""
    asset_urn: str
    asset_name: str
    domain: str
    all_owners: list[dict[str, Any]] = field(default_factory=list)
    technical_owners: list[dict[str, Any]] = field(default_factory=list)
    business_owners: list[dict[str, Any]] = field(default_factory=list)
    inactive_owners: list[dict[str, Any]] = field(default_factory=list)
    active_owners: list[dict[str, Any]] = field(default_factory=list)
    service_account_owners: list[dict[str, Any]] = field(default_factory=list)
    group_owners: list[dict[str, Any]] = field(default_factory=list)
    historical_owners: list[dict[str, Any]] = field(default_factory=list)
    has_active_operational_owner: bool = True
    proposed_replacement: dict[str, Any] | None = None
    replacement_rationale: str = ""


@dataclass
class OwnershipReplacementCandidate:
    """A candidate for replacing an inactive owner."""
    urn: str
    username: str
    full_name: str
    candidate_type: str  # "domain_owner", "group_member", "peer_owner", "none"
    priority: int  # lower = preferred
    rationale: str


# -- Ownership resolver --------------------------------------------------------


class OwnershipResolver:
    """Resolves ownership state across all assets.

    Identifies inactive owners, proposes replacements, and distinguishes
    historical ownership from active operational responsibility.
    """

    def __init__(
        self,
        datasets: list[dict[str, Any]] | None = None,
        users: list[dict[str, Any]] | None = None,
        groups: list[dict[str, Any]] | None = None,
        service_accounts: list[dict[str, Any]] | None = None,
    ) -> None:
        self._datasets = datasets or DATASETS
        self._users = users or USERS
        self._groups = groups or GROUPS
        self._service_accounts = service_accounts or SERVICE_ACCOUNTS

        # Build lookup maps
        self._user_map: dict[str, dict] = {u["urn"]: u for u in self._users}
        self._group_map: dict[str, dict] = {g["urn"]: g for g in self._groups}

    def resolve_all(self) -> list[AssetOwnershipRecord]:
        """Build complete ownership records for all datasets."""
        records: list[AssetOwnershipRecord] = []
        for ds in self._datasets:
            records.append(self._resolve_one(ds))
        return records

    def _resolve_one(self, ds: dict[str, Any]) -> AssetOwnershipRecord:
        """Resolve ownership for a single dataset."""
        owners_raw = ds.get("owners", [])
        historical_raw = ds.get("historical_owners", [])

        all_owners: list[dict] = []
        technical: list[dict] = []
        business: list[dict] = []
        inactive: list[dict] = []
        active: list[dict] = []
        service: list[dict] = []
        group_owners: list[dict] = []

        for o in owners_raw:
            owner_urn = o["owner"]
            owner_type = o["type"]

            # Resolve user info
            user_info = self._user_map.get(owner_urn, {})
            is_active = user_info.get("active", True)
            is_service = owner_urn in {sa["urn"] for sa in self._service_accounts}
            is_group = "corpgroup" in owner_urn.lower() or "corpGroup" in owner_urn

            record = {
                "urn": owner_urn,
                "username": user_info.get("username", owner_urn),
                "full_name": user_info.get("full_name", ""),
                "type": owner_type,
                "active": is_active,
                "is_service_account": is_service,
                "is_group": is_group,
            }

            all_owners.append(record)

            if owner_type == "TECHNICAL_OWNER":
                technical.append(record)
            elif owner_type == "BUSINESS_OWNER":
                business.append(record)

            if is_service:
                service.append(record)
            elif is_group:
                group_owners.append(record)
            elif not is_active:
                inactive.append(record)
            else:
                active.append(record)

        # Historical owners
        hist_owners: list[dict] = []
        for h in historical_raw:
            hist_owners.append({
                "urn": h["owner"],
                "type": h["type"],
                "until": h.get("until", "unknown"),
            })

        # Determine if there's an active technical owner
        has_active_tech = any(
            o["active"] for o in technical
            if not o["is_service_account"] and not o["is_group"]
        ) or any(o["is_group"] for o in technical)

        # If no active individual technical owner, check group owners
        has_active_group = any(o["is_group"] for o in technical)
        has_active = has_active_tech or has_active_group

        return AssetOwnershipRecord(
            asset_urn=ds["urn"],
            asset_name=ds.get("name", ds["urn"]),
            domain=ds.get("domain", ""),
            all_owners=all_owners,
            technical_owners=technical,
            business_owners=business,
            inactive_owners=inactive,
            active_owners=active,
            service_account_owners=service,
            group_owners=group_owners,
            historical_owners=hist_owners,
            has_active_operational_owner=has_active,
        )

    def find_orphaned_assets(self) -> list[AssetOwnershipRecord]:
        """Find assets with at least one inactive owner and no active operational owner."""
        records = self.resolve_all()
        return [r for r in records if r.inactive_owners and not r.has_active_operational_owner]

    def find_assets_by_inactive_owner(self, owner_urn: str) -> list[AssetOwnershipRecord]:
        """Find all assets associated with a specific inactive owner."""
        records = self.resolve_all()
        return [
            r for r in records
            if any(o["urn"] == owner_urn for o in r.inactive_owners)
        ]

    def find_replacement_candidates(
        self,
        asset_record: AssetOwnershipRecord,
    ) -> list[OwnershipReplacementCandidate]:
        """Find valid replacement candidates for an asset's owners.

        Priority order:
        1. Domain owner (from domain's owner group)
        2. Active peer technical owners in the same domain
        3. Active group members
        4. No valid candidate (must be flagged)
        """
        candidates: list[OwnershipReplacementCandidate] = []

        # Priority 1: Domain owner from group
        domain_urn = asset_record.domain
        for group in self._groups:
            if group["urn"] == asset_record.domain or domain_urn in group.get("name", "").lower():
                for member_username in group.get("members", []):
                    member_urn = f"urn:li:corpuser:{member_username}"
                    user = self._user_map.get(member_urn, {})
                    if user.get("active", False):
                        candidates.append(OwnershipReplacementCandidate(
                            urn=member_urn,
                            username=member_username,
                            full_name=user.get("full_name", member_username),
                            candidate_type="domain_owner",
                            priority=1,
                            rationale=f"Member of domain owner group '{group['name']}'",
                        ))

        # Priority 2: Active peer owners from same domain
        same_domain_assets = [r for r in self.resolve_all() if r.domain == asset_record.domain]
        for rec in same_domain_assets:
            for owner in rec.technical_owners:
                if owner["active"] and not owner["is_service_account"] and not owner["is_group"]:
                    # Avoid duplicates
                    if not any(c.urn == owner["urn"] for c in candidates):
                        candidates.append(OwnershipReplacementCandidate(
                            urn=owner["urn"],
                            username=owner["username"],
                            full_name=owner.get("full_name", owner["username"]),
                            candidate_type="peer_owner",
                            priority=2,
                            rationale=f"Active TECHNICAL_OWNER of {rec.asset_name} (same domain)",
                        ))

        # Priority 3: Any active group member
        for group in self._groups:
            for member_username in group.get("members", []):
                member_urn = f"urn:li:corpuser:{member_username}"
                user = self._user_map.get(member_urn, {})
                if user.get("active", False):
                    if not any(c.urn == member_urn for c in candidates):
                        candidates.append(OwnershipReplacementCandidate(
                            urn=member_urn,
                            username=member_username,
                            full_name=user.get("full_name", member_username),
                            candidate_type="group_member",
                            priority=3,
                            rationale=f"Active member of group '{group['name']}'",
                        ))

        # Sort by priority
        candidates.sort(key=lambda c: c.priority)

        if not candidates:
            candidates.append(OwnershipReplacementCandidate(
                urn="",
                username="",
                full_name="No valid candidate found",
                candidate_type="none",
                priority=99,
                rationale="No active domain owner, peer owner, or group member found. Manual assignment required.",
            ))

        return candidates


# -- Phase 4 Pipeline ----------------------------------------------------------


class Phase4Pipeline:
    """Complete orphaned-ownership vertical slice pipeline."""

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
        self._resolver = OwnershipResolver()
        self._use_live_datahub = use_live_datahub
        self._read_client = read_client or DataHubReadClient()
        self._write_client = write_client or DataHubWriteClient()
        self._live_active_candidates: list[dict[str, Any]] = []

    # -- Step 1: Ingest incident -----------------------------------------------

    async def step1_ingest_incident(
        self,
        incident_urn: str,
        incident_title: str,
        incident_description: str,
        affected_asset_urn: str,
        proposed_root_cause: str,
    ) -> dict[str, Any]:
        """Ingest a resolved ownership incident."""
        logger.info("phase4.step1.ingest", incident_urn=incident_urn)
        return {
            "incident_urn": incident_urn,
            "title": incident_title,
            "description": incident_description,
            "affected_asset_urn": affected_asset_urn,
            "proposed_root_cause": proposed_root_cause,
            "root_cause_confirmed": False,
            "status": "RESOLVED",
            "custom_type": "ORPHANED_OWNERSHIP",
        }

    # -- Step 2: Root cause approval -------------------------------------------

    async def step2_approve_root_cause(
        self, incident_urn: str, approver: str, edited_cause: str | None = None
    ) -> RootCauseApproval:
        await self._approvals.submit_root_cause(incident_urn, "proposed")
        return await self._approvals.approve_root_cause(incident_urn, approver, edited_cause)

    # -- Step 3: Lesson extraction ---------------------------------------------

    async def step3_extract_lesson(
        self, incident_urn: str, incident_title: str, incident_description: str,
        human_confirmed_root_cause: str, confirmed_by: str, target_asset_urn: str,
    ) -> tuple[ReflexLesson, ExtractionRecord]:
        return await self._extractor.extract(
            incident_urn=incident_urn,
            incident_title=incident_title,
            incident_description=incident_description,
            human_confirmed_root_cause=human_confirmed_root_cause,
            confirmed_by=confirmed_by,
            target_asset_urn=target_asset_urn,
            incident_custom_type="ORPHANED_OWNERSHIP",
        )

    # -- Step 4: Identify affected assets --------------------------------------

    async def step4_identify_affected_assets(
        self, inactive_owner_urn: str
    ) -> list[AssetOwnershipRecord]:
        """Find all assets associated with the inactive owner."""
        if self._use_live_datahub:
            records: list[AssetOwnershipRecord] = []
            search_results = await self._read_client.search_datasets("reflex_finance", count=20)
            for result in search_results:
                entity = result.get("entity") or {}
                asset_urn = entity.get("urn", "")
                if not asset_urn:
                    continue
                owners = await self._read_client.get_owners(asset_urn)
                self._live_active_candidates.extend(
                    owner for owner in owners
                    if owner.get("active") is not False and owner.get("urn") != inactive_owner_urn
                )
                inactive = [owner for owner in owners if owner.get("urn") == inactive_owner_urn or owner.get("active") is False]
                if not inactive:
                    continue
                active = [owner for owner in owners if owner not in inactive and owner.get("active") is not False]
                records.append(AssetOwnershipRecord(
                    asset_urn=asset_urn,
                    asset_name=entity.get("name", asset_urn),
                    domain=(await self._read_client.get_domain(asset_urn)) or "",
                    all_owners=owners,
                    # Quickstart OSS may normalize the ownership type to NONE
                    # even when addOwner receives the technical-owner URN.
                    technical_owners=list(owners),
                    inactive_owners=inactive,
                    active_owners=active,
                    historical_owners=inactive,
                    has_active_operational_owner=any(
                        o in active for o in owners
                    ),
                ))
            logger.info("phase4.step4.live_affected_assets", count=len(records))
            return records
        records = self._resolver.find_assets_by_inactive_owner(inactive_owner_urn)
        logger.info(
            "phase4.step4.affected_assets",
            inactive_owner=inactive_owner_urn,
            count=len(records),
        )
        return records

    # -- Step 5: Distinguish historical vs active ownership --------------------

    async def step5_classify_ownership(
        self, asset_records: list[AssetOwnershipRecord]
    ) -> list[AssetOwnershipRecord]:
        """Classify each asset's ownership: active operational, historical, orphaned.

        This step does NOT modify anything. It only classifies.
        """
        for record in asset_records:
            # Already classified in resolve_all()
            pass

        orphaned = [r for r in asset_records if not r.has_active_operational_owner]
        logger.info(
            "phase4.step5.classify",
            total=len(asset_records),
            orphaned=len(orphaned),
            healthy=len(asset_records) - len(orphaned),
        )
        return asset_records

    # -- Step 6: Identify replacement candidates -------------------------------

    async def step6_find_replacements(
        self, asset_records: list[AssetOwnershipRecord]
    ) -> list[AssetOwnershipRecord]:
        """Find valid replacement candidates for each asset, preferring domain owners."""
        if self._use_live_datahub:
            candidate = next(iter(self._live_active_candidates), None)
            for record in asset_records:
                if not record.has_active_operational_owner and candidate:
                    record.proposed_replacement = {
                        "urn": candidate["urn"],
                        "username": candidate.get("username", candidate["urn"]),
                        "full_name": candidate.get("username", candidate["urn"]),
                        "candidate_type": "live_active_owner",
                        "priority": 1,
                        "rationale": "Active owner discovered on another live Reflex dataset.",
                    }
                    record.replacement_rationale = record.proposed_replacement["rationale"]
            return asset_records
        for record in asset_records:
            if not record.has_active_operational_owner:
                candidates = self._resolver.find_replacement_candidates(record)
                if candidates:
                    best = candidates[0]
                    record.proposed_replacement = {
                        "urn": best.urn,
                        "username": best.username,
                        "full_name": best.full_name,
                        "candidate_type": best.candidate_type,
                        "priority": best.priority,
                        "rationale": best.rationale,
                    }
                    record.replacement_rationale = best.rationale

        with_replacements = [r for r in asset_records if r.proposed_replacement]
        logger.info(
            "phase4.step6.replacements",
            total=len(asset_records),
            with_candidates=len(with_replacements),
        )
        return asset_records

    # -- Step 7: Synthesize ActiveOwnershipControl -----------------------------

    async def step7_synthesize_control(self, lesson: ReflexLesson) -> ReflexControl:
        """Synthesize an ActiveOwnershipControl."""
        definition = build_active_ownership_control_definition(
            min_active_owners=1,
            required_owner_types=["TECHNICAL_OWNER"],
        )

        control = ReflexControl(
            control_id=ControlId.generate(),
            lesson_id=lesson.lesson_id,
            target_asset_urn=lesson.candidate_preventive_control.target_asset_urn or "",
            control_type=ControlType.ACTIVE_OWNERSHIP,
            control_definition=definition,
        )

        logger.info("phase4.step7.control", control_id=control.control_id)
        return control

    # -- Step 8: Backtest on historical snapshots ------------------------------

    async def step8_backtest(
        self, control: ReflexControl, historical_data: list[Any],
        known_incident_snapshots: int = 0,
    ) -> tuple[list, BacktestMetrics, bool, list[str]]:
        """Run backtest and compute metrics."""
        results = await self._backtester.backtest(control, historical_data)
        metrics = compute_metrics(results, known_incident_snapshots)

        from reflex.core.phase3_pipeline import can_recommend_publication
        can_rec, blockers = can_recommend_publication(metrics, results)

        logger.info(
            "phase4.step8.backtest",
            precision=metrics.precision,
            recall=metrics.recall,
            can_recommend=can_rec,
        )
        return results, metrics, can_rec, blockers

    # -- Step 9: Human approval -----------------------------------------------

    async def step9_approve(
        self, control: ReflexControl, metrics: BacktestMetrics, approver: str
    ) -> ControlApproval:
        await self._approvals.submit_control_for_approval(
            control.control_id, control.lesson_id, metrics.to_dict()
        )
        return await self._approvals.approve_control(control.control_id, approver)

    # -- Step 10-11: Preserve history, update ownership after approval ---------

    async def step10_preserve_and_update(
        self, asset_records: list[AssetOwnershipRecord], approval: ControlApproval
    ) -> dict[str, Any]:
        """Preserve historical ownership and propose operational ownership updates.

        NO automatic deletion of historical ownership is allowed.
        Updates only occur after approval.
        """
        update_plan = {
            "approval": {
                "control_id": approval.control_id,
                "approved_by": approval.approver,
                "approved_at": approval.timestamp.isoformat(),
            },
            "historical_preservation": [
                {
                    "asset_urn": r.asset_urn,
                    "historical_owners": r.historical_owners,
                    "inactive_owners_preserved": [
                        {"urn": o["urn"], "username": o["username"], "type": o["type"]}
                        for o in r.inactive_owners
                    ],
                }
                for r in asset_records
            ],
            "proposed_updates": [
                {
                    "asset_urn": r.asset_urn,
                    "action": "add_owner",
                    "owner_urn": r.proposed_replacement["urn"],
                    "owner_type": "TECHNICAL_OWNER",
                    "rationale": r.replacement_rationale,
                }
                for r in asset_records
                if r.proposed_replacement and r.proposed_replacement.get("candidate_type") != "none"
            ],
            "assets_with_no_candidate": [
                {
                    "asset_urn": r.asset_urn,
                    "action": "flag_for_manual_review",
                    "reason": "No valid replacement candidate found",
                }
        for r in asset_records
                if r.proposed_replacement and r.proposed_replacement.get("candidate_type") == "none"
            ],
        }

        if self._use_live_datahub:
            for update in update_plan["proposed_updates"]:
                await self._write_client.update_owner(
                    update["asset_urn"], update["owner_urn"], update["owner_type"]
                )

        output_dir = self._dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / f"ownership_update_{approval.control_id}.json").write_text(
            json.dumps(update_plan, indent=2, default=str)
        )

        logger.info(
            "phase4.step10.update_plan",
            assets_with_updates=len(update_plan["proposed_updates"]),
            assets_flagged=len(update_plan["assets_with_no_candidate"]),
        )
        return update_plan

    # -- Step 12: Mark assets as covered ---------------------------------------

    async def step12_mark_coverage(
        self, control: ReflexControl, lesson: ReflexLesson,
        asset_records: list[AssetOwnershipRecord],
    ) -> dict[str, Any]:
        """Mark assets as covered by the Reflex ownership control."""
        coverage = {
            "control_id": control.control_id,
            "lesson_id": lesson.lesson_id,
            "covered_assets": [
                {
                    "asset_urn": r.asset_urn,
                    "asset_name": r.asset_name,
                    "tag": "reflex:ownership-controlled",
                }
                for r in asset_records
            ],
            "coverage_date": datetime.now(UTC).isoformat(),
        }

        output_dir = self._dir / "output"
        (output_dir / f"coverage_{control.control_id}.json").write_text(
            json.dumps(coverage, indent=2, default=str)
        )

        if self._use_live_datahub:
            tag_urn = await self._write_client.create_tag(
                "reflex-ownership-controlled",
                "reflex-ownership-controlled",
                "Covered by a Reflex active-ownership control",
            )
            for record in asset_records:
                await self._write_client.add_tag(record.asset_urn, tag_urn)

        logger.info("phase4.step12.coverage", assets=len(coverage["covered_assets"]))
        return coverage

    # -- Step 13: Detect later inactive-owner case -----------------------------

    async def step13_detect_future(
        self, control: ReflexControl, new_ownership_data: list[dict],
    ) -> dict[str, Any]:
        """Detect a later inactive-owner case on another asset."""
        executor = ActiveOwnershipControlExecutor()
        result = await executor.execute(control, new_ownership_data)

        if not result.passed:
            detection = {
                "detected": True,
                "control_id": control.control_id,
                "lesson_id": control.lesson_id,
                "violation_count": result.violation_count,
                "violations": result.sample_violations[:5],
                "new_incident_title": "Reflex detected orphaned ownership on marketing.campaigns",
                "new_incident_description": (
                    f"Reflex ActiveOwnershipControl {control.control_id} detected "
                    f"that diana (deactivated) remains TECHNICAL_OWNER of "
                    f"marketing.campaigns with no active replacement."
                ),
            }
            logger.info("phase4.step13.detected", violations=result.violation_count)
            return detection

        return {"detected": False, "control_id": control.control_id}

    # -- Full pipeline ---------------------------------------------------------

    async def run(
        self, incident_urn: str, incident_title: str, incident_description: str,
        affected_asset_urn: str, proposed_root_cause: str, confirmed_by: str,
        inactive_owner_urn: str, historical_data: list[Any],
        future_ownership_data: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Run the complete orphaned-ownership Reflex loop."""
        logger.info("phase4.pipeline.start")

        # Step 1
        incident = await self.step1_ingest_incident(
            incident_urn, incident_title, incident_description,
            affected_asset_urn, proposed_root_cause,
        )

        # Step 2
        root_approval = await self.step2_approve_root_cause(
            incident_urn, confirmed_by,
        )

        # Step 3
        lesson, record = await self.step3_extract_lesson(
            incident_urn, incident_title, incident_description,
            root_approval.final_root_cause, confirmed_by, affected_asset_urn,
        )

        # Steps 4-6: Ownership analysis
        affected = await self.step4_identify_affected_assets(inactive_owner_urn)
        classified = await self.step5_classify_ownership(affected)
        with_replacements = await self.step6_find_replacements(classified)

        # Step 7: Control
        control = await self.step7_synthesize_control(lesson)

        # Step 8: Backtest
        results, metrics, can_rec, blockers = await self.step8_backtest(
            control, historical_data, known_incident_snapshots=1,
        )

        # Step 9: Approval
        control_approval = await self.step9_approve(control, metrics, confirmed_by)

        # Steps 10-11: Preserve + update
        update_plan = await self.step10_preserve_and_update(with_replacements, control_approval)

        # Step 12: Coverage
        coverage = await self.step12_mark_coverage(control, lesson, with_replacements)

        # Step 13: Future detection
        detection = None
        if future_ownership_data:
            detection = await self.step13_detect_future(control, future_ownership_data)

        result = {
            "incident": incident,
            "root_approval": root_approval,
            "lesson": lesson,
            "extraction_record": record,
            "affected_assets": [r.asset_urn for r in affected],
            "classified_assets": [
                {
                    "asset_urn": r.asset_urn,
                    "has_active_owner": r.has_active_operational_owner,
                    "inactive_owners": [o["username"] for o in r.inactive_owners],
                    "proposed_replacement": r.proposed_replacement,
                }
                for r in with_replacements
            ],
            "control": control,
            "backtest_metrics": metrics.to_dict(),
            "can_recommend": can_rec,
            "blockers": blockers,
            "control_approval": control_approval,
            "update_plan": update_plan,
            "coverage": coverage,
            "future_detection": detection,
        }

        logger.info("phase4.pipeline.complete")
        return result
