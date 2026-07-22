"""Deterministic similarity resolver — finds similar assets using graph and schema signals.

No LLM required. Uses explicit, testable signals for scoring.

Supported signals:
- same domain
- same tags
- compatible schema (presence of target field)
- append-only write pattern
- similar lineage position
- absence of equivalent active control
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from reflex.datahub.environment import DATASETS, LINEAGE
from reflex.datahub.read_client import DataHubReadClient
from reflex.models import Confidence, SimilarAssetCandidate

logger = structlog.get_logger(__name__)


class DataHubLiveQueryError(RuntimeError):
    """Raised when live DataHub discovery cannot be completed.

    Live mode must fail explicitly instead of silently using the synthetic
    fixture graph, otherwise a demo can appear to use DataHub while actually
    resolving candidates from local test data.
    """


# -- Signal definitions --------------------------------------------------------


@dataclass
class SimilaritySignal:
    name: str
    weight: float  # contribution to total score
    matched: bool = False
    detail: str = ""


@dataclass
class CandidateResult:
    """Full similarity assessment for one candidate asset."""
    asset_urn: str
    asset_type: str = "dataset"
    selected: bool = False
    signals: list[SimilaritySignal] = field(default_factory=list)
    score: float = 0.0
    max_score: float = 0.0
    explanation: str = ""

    @property
    def matched_signals(self) -> list[str]:
        return [s.name for s in self.signals if s.matched]

    @property
    def missing_signals(self) -> list[str]:
        return [s.name for s in self.signals if not s.matched]


# -- Resolver ------------------------------------------------------------------


class SimilarityResolver:
    """Finds assets similar to a source asset using deterministic signals.

    Independently testable — no LLM dependency.
    """

    def __init__(
        self,
        source_urn: str,
        target_field: str = "",
        control_type: str = "uniqueness",
        propagation_scope: list[str] | None = None,
        datasets: list[dict[str, Any]] | None = None,
        lineage: list[dict[str, Any]] | None = None,
    ) -> None:
        self.source_urn = source_urn
        self.target_field = target_field
        self.control_type = control_type
        self.propagation_scope = propagation_scope or []
        self._datasets = datasets or DATASETS
        self._lineage = lineage or LINEAGE
        self._source_ds = self._find_dataset(source_urn)

    def _find_dataset(self, urn: str) -> dict[str, Any] | None:
        for ds in self._datasets:
            if ds["urn"] == urn:
                return ds
        return None

    async def resolve(
        self,
        max_candidates: int = 10,
        min_score: float = 0.2,
    ) -> list[CandidateResult]:
        """Find similar assets and score them deterministically.

        Returns candidates sorted by score (descending). Only candidates
        at or above min_score are marked as selected.
        """
        results: list[CandidateResult] = []

        for ds in self._datasets:
            if ds["urn"] == self.source_urn:
                continue  # Skip the source asset itself

            candidate = self._score_candidate(ds)
            if candidate.score >= min_score:
                candidate.selected = True
            results.append(candidate)

        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:max_candidates]

    def _score_candidate(self, ds: dict[str, Any]) -> CandidateResult:
        """Score a single candidate dataset against the source."""
        signals: list[SimilaritySignal] = []
        source_domain = self._source_ds.get("domain") if self._source_ds else ""
        source_tags_set = set(self._source_ds.get("tags", [])) if self._source_ds else set()

        # Signal 1: Same domain (weight: 0.25)
        same_domain = ds.get("domain") == source_domain if source_domain else False
        signals.append(SimilaritySignal(
            name="same_domain",
            weight=0.25,
            matched=same_domain,
            detail=f"Both in {ds.get('domain', 'unknown')}" if same_domain else f"Source: {source_domain}, Candidate: {ds.get('domain')}",
        ))

        # Signal 2: Shared tags (weight: 0.20)
        candidate_tags = set(ds.get("tags", []))
        shared_tags = source_tags_set & candidate_tags
        signals.append(SimilaritySignal(
            name="shared_tags",
            weight=0.20,
            matched=len(shared_tags) > 0,
            detail=f"Shared: {shared_tags}" if shared_tags else "No shared tags",
        ))

        # Signal 3: Compatible schema — presence of target field (weight: 0.25)
        has_target_field = False
        if self.target_field:
            schema_fields = {f["name"] for f in ds.get("schema", [])}
            has_target_field = self.target_field in schema_fields
        signals.append(SimilaritySignal(
            name="compatible_schema",
            weight=0.25,
            matched=has_target_field,
            detail=f"Has '{self.target_field}' field" if has_target_field else f"Missing '{self.target_field}' field",
        ))

        # Signal 4: Append-only property (weight: 0.15)
        # For uniqueness control, append-only without idempotency is a vulnerability signal
        props = ds.get("structured_properties", {})
        is_append_only = props.get("reflex:write_pattern") == "append-only"
        has_no_idempotency = props.get("reflex:has_idempotency_key") == "false"
        append_vulnerable = is_append_only and has_no_idempotency
        signals.append(SimilaritySignal(
            name="append_only_vulnerability",
            weight=0.15,
            matched=append_vulnerable,
            detail="Append-only without idempotency" if append_vulnerable else "Not vulnerable to append-duplicate pattern",
        ))

        # Signal 5: Similar lineage position (weight: 0.10)
        source_downstreams = self._get_downstreams(self.source_urn)
        source_upstreams = self._get_upstreams(self.source_urn)
        candidate_upstreams = self._get_upstreams(ds["urn"])
        candidate_downstreams = self._get_downstreams(ds["urn"])

        # Shares an upstream or downstream with source
        shares_upstream = bool(set(source_upstreams) & set(candidate_upstreams))
        shares_downstream = bool(set(source_downstreams) & set(candidate_downstreams))
        lineage_similar = shares_upstream or shares_downstream

        signals.append(SimilaritySignal(
            name="similar_lineage",
            weight=0.10,
            matched=lineage_similar,
            detail=f"Shares upstream: {shares_upstream}, Shares downstream: {shares_downstream}" if lineage_similar else "No shared lineage position",
        ))

        # Signal 6: No equivalent active control (weight: 0.05)
        has_reflex_tag = any(
            t.startswith("reflex:") for t in ds.get("tags", [])
        )
        signals.append(SimilaritySignal(
            name="no_existing_control",
            weight=0.05,
            matched=not has_reflex_tag,
            detail="No existing Reflex control" if not has_reflex_tag else "Already has Reflex tag",
        ))

        # Compute score
        total_weight = sum(s.weight for s in signals)
        score = sum(s.weight for s in signals if s.matched) / total_weight if total_weight > 0 else 0.0

        # Build explanation
        matched = [s.name for s in signals if s.matched]
        missing = [s.name for s in signals if not s.matched]
        explanation = f"Score: {score:.2f}. Matched: {matched}. Missing: {missing}."

        return CandidateResult(
            asset_urn=ds["urn"],
            asset_type="dataset",
            signals=signals,
            score=score,
            max_score=1.0,
            explanation=explanation,
        )

    def _get_upstreams(self, urn: str) -> list[str]:
        """Get URNs that are upstream of the given URN."""
        return [e["upstream"] for e in self._lineage if e["downstream"] == urn]

    def _get_downstreams(self, urn: str) -> list[str]:
        """Get URNs that are downstream of the given URN."""
        return [e["downstream"] for e in self._lineage if e["upstream"] == urn]


def candidates_to_similar_assets(
    candidates: list[CandidateResult],
) -> list[SimilarAssetCandidate]:
    """Convert CandidateResults to SimilarAssetCandidate domain models."""
    results: list[SimilarAssetCandidate] = []
    for c in candidates:
        if c.selected:
            confidence = Confidence.HIGH if c.score >= 0.6 else Confidence.MEDIUM if c.score >= 0.3 else Confidence.LOW
            results.append(SimilarAssetCandidate(
                asset_urn=c.asset_urn,
                asset_type=c.asset_type,
                similarity_rationale=c.explanation,
                matched_characteristics=c.matched_signals,
                confidence=confidence,
            ))
    return results


# -- Live DataHub resolver ----------------------------------------------------


class DataHubSimilarityResolver(SimilarityResolver):
    """Similarity resolver that fetches candidate assets from a live DataHub instance.

    Uses the same 6-signal scoring as the synthetic resolver, but sources
    datasets and lineage from DataHub GraphQL instead of in-memory data.
    """

    def __init__(
        self,
        source_urn: str,
        target_field: str = "",
        control_type: str = "uniqueness",
        propagation_scope: list[str] | None = None,
        read_client: DataHubReadClient | None = None,
    ) -> None:
        self._client = read_client or DataHubReadClient()
        self._live_datasets: list[dict[str, Any]] | None = None
        super().__init__(
            source_urn=source_urn,
            target_field=target_field,
            control_type=control_type,
            propagation_scope=propagation_scope,
            datasets=[],  # Will be populated from DataHub
            lineage=[],
        )

    async def _fetch_datasets_from_datahub(self) -> list[dict[str, Any]]:
        """Fetch all datasets and their metadata from DataHub."""
        if self._live_datasets is not None:
            return self._live_datasets

        source_name = self.source_urn.split(",")[-2].replace(")", "")
        search_term = source_name.split(".")[0].split("_")[0]
        query = """
        query($query: String!, $start: Int!, $count: Int!) {
            searchAcrossEntities(
                input: { types: [DATASET], query: $query, start: $start, count: $count }
            ) {
                searchResults {
                    entity {
                        urn
                        type
                        ... on Dataset {
                            name
                            platform { name }
                            domain { domain { urn properties { name } } }
                            tags { tags { tag { properties { name } } } }
                            schemaMetadata { fields { fieldPath } }
                            ownership {
                                owners {
                                    owner { ... on CorpUser { username } ... on CorpGroup { name } }
                                    type
                                }
                            }
                        }
                    }
                }
            }
        }
        """
        try:
            result = await self._client._query(
                query,
                {"query": search_term, "start": 0, "count": 10},
            )
            search_results = result.get("searchAcrossEntities", {}).get("searchResults", [])
            datasets: list[dict[str, Any]] = []
            for sr in search_results:
                entity = sr.get("entity") or {}
                if not entity.get("urn"):
                    continue

                # Extract domain
                domain_urn = ""
                domain_name = ""
                domain_data = (entity.get("domain") or {}).get("domain")
                if domain_data:
                    domain_urn = domain_data.get("urn", "")
                    domain_name = (domain_data.get("properties") or {}).get("name", "")

                # Extract tags
                tags = [
                    ((t.get("tag") or {}).get("properties") or {}).get("name", "")
                    for t in ((entity.get("tags") or {}).get("tags") or [])
                    if (((t.get("tag") or {}).get("properties") or {}).get("name"))
                ]

                # Extract schema fields
                fields = [
                    {"name": f.get("fieldPath", "")}
                    for f in ((entity.get("schemaMetadata") or {}).get("fields") or [])
                ]

                # Extract owners
                owners_raw = ((entity.get("ownership") or {}).get("owners") or [])
                owners = []
                for o in owners_raw:
                    owner_obj = o.get("owner") or {}
                    owner_urn = owner_obj.get("username") or owner_obj.get("name") or ""
                    owners.append({"owner": owner_urn, "type": o.get("type", "")})

                datasets.append({
                    "urn": entity["urn"],
                    "name": entity.get("name", ""),
                    "platform": (entity.get("platform") or {}).get("name", ""),
                    "domain": domain_urn,
                    "domain_name": domain_name,
                    "tags": tags,
                    "schema": fields,
                    "owners": owners,
                    "structured_properties": {},
                })

            self._live_datasets = datasets
            logger.info("datahub_resolver.fetched", count=len(datasets))
            return datasets
        except Exception as e:
            logger.error("datahub_resolver.fetch_failed", error=str(e))
            raise DataHubLiveQueryError(
                f"Live DataHub dataset discovery failed: {e}"
            ) from e

    async def resolve(
        self,
        max_candidates: int = 10,
        min_score: float = 0.2,
    ) -> list[CandidateResult]:
        """Fetch from DataHub and score with the same signals."""
        live_datasets = await self._fetch_datasets_from_datahub()
        self._datasets = live_datasets
        self._lineage = []

        return await super().resolve(max_candidates=max_candidates, min_score=min_score)


def create_similarity_resolver(
    source_urn: str,
    target_field: str = "",
    control_type: str = "uniqueness",
    propagation_scope: list[str] | None = None,
    use_live_datahub: bool = False,
    read_client: DataHubReadClient | None = None,
) -> SimilarityResolver:
    """Factory: create a synthetic or live DataHub resolver.

    Args:
        use_live_datahub: If True, queries the live DataHub instance.
        read_client: Optional pre-configured DataHubReadClient.
    """
    if use_live_datahub:
        return DataHubSimilarityResolver(
            source_urn=source_urn,
            target_field=target_field,
            control_type=control_type,
            propagation_scope=propagation_scope,
            read_client=read_client,
        )
    return SimilarityResolver(
        source_urn=source_urn,
        target_field=target_field,
        control_type=control_type,
        propagation_scope=propagation_scope,
    )
