from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cases.hashing import canonical_sha256
from app.internal_knowledge.retrieval import KnowledgeRepository
from app.internal_knowledge.schemas import EvidenceReference, InternalAssetCandidate
from app.models import (
    Case,
    CaseSource,
    Finding,
    ImpactHypothesis,
    InternalAsset,
    InternalAssetVersion,
)
from app.security.auth import Principal


@dataclass(frozen=True)
class FindingCandidates:
    finding: Finding
    source: CaseSource
    candidates: list[InternalAssetCandidate]


class InternalKnowledgeAgent:
    """Deterministic retrieval specialist over only the caller-authorized corpus."""

    name = "internal-knowledge-agent"
    version = "1.1.0"

    def __init__(self, session: AsyncSession, principal: Principal) -> None:
        self.session = session
        self.repository = KnowledgeRepository(session, principal)

    async def retrieve_for_case(
        self,
        case: Case,
        *,
        query_override: str | None = None,
        per_finding_limit: int = 5,
    ) -> list[FindingCandidates]:
        rows = (
            await self.session.execute(
                select(Finding, CaseSource)
                .join(
                    CaseSource,
                    (CaseSource.case_id == case.id)
                    & (CaseSource.document_version_id == Finding.document_version_id),
                )
                .where(Finding.review_state == "approved")
                .order_by(Finding.created_at, Finding.id)
            )
        ).all()
        results: list[FindingCandidates] = []
        for finding, source in rows:
            search_query = query_override or " ".join(
                [*finding.categories, *finding.process_lenses, finding.finding_text[:1_200]]
            )
            response = await self.repository.search(search_query, limit=per_finding_limit)
            results.append(
                FindingCandidates(
                    finding=finding,
                    source=source,
                    candidates=response.items,
                )
            )
        return results


class ImpactAnalysisAgent:
    """Creates reviewable hypotheses while refusing to make compliance decisions."""

    name = "impact-analysis-agent"
    version = "1.0.2"

    def __init__(self, session: AsyncSession, principal: Principal) -> None:
        self.session = session
        self.knowledge = InternalKnowledgeAgent(session, principal)

    async def generate_for_case(
        self,
        case: Case,
        *,
        created_by: str,
        query_override: str | None = None,
        per_finding_limit: int = 5,
        run_id: str | None = None,
    ) -> list[ImpactHypothesis]:
        candidate_groups = await self.knowledge.retrieve_for_case(
            case,
            query_override=query_override,
            per_finding_limit=per_finding_limit,
        )
        generated: list[ImpactHypothesis] = []
        for group in candidate_groups:
            for candidate in group.candidates:
                if not group.finding.evidence or not candidate.internal_evidence_anchors:
                    continue
                external = self._external_evidence(group.finding, group.source)
                version_hash = await self._version_hash(str(candidate.asset_version_id))
                internal = [
                    EvidenceReference(
                        source_type="INTERNAL_ASSET",
                        source_version_id=candidate.asset_version_id,
                        source_hash=version_hash,
                        anchor_id=anchor.id,
                        excerpt=anchor.excerpt,
                    ).model_dump(mode="json")
                    for anchor in candidate.internal_evidence_anchors[:3]
                ]
                if not external or not internal:
                    continue
                relationship_type = self._relationship_type(group.finding, candidate)
                statement = (
                    f"Finding {group.finding.label} may warrant human comparison with "
                    f"{candidate.asset_key} revision {candidate.revision}; this is an impact "
                    "hypothesis, not a compliance or change-control conclusion."
                )
                payload: dict[str, Any] = {
                    "case_id": case.id,
                    "run_id": run_id,
                    "finding_id": group.finding.id,
                    "asset_id": str(candidate.asset_id),
                    "asset_version_id": str(candidate.asset_version_id),
                    "relationship_type": relationship_type,
                    "statement": statement,
                    "known_facts": [
                        f"The retained external finding is labeled {group.finding.label}.",
                        f"{candidate.asset_key} revision {candidate.revision} is marked "
                        f"{candidate.effective_status} in the synthetic corpus.",
                    ],
                    "derived_relationships": [
                        "Hybrid retrieval linked the finding vocabulary to the "
                        f"{candidate.domain} domain with score "
                        f"{candidate.retrieval_score:.3f}."
                    ],
                    "assumptions": [
                        "The synthetic asset taxonomy is sufficiently analogous for "
                        "portfolio demonstration."
                    ],
                    "counterevidence": [
                        "The cited internal excerpt does not establish that the external "
                        "observation occurred in this synthetic process."
                    ],
                    "unknowns": [
                        "Applicability, implementation state, and operating effectiveness "
                        "require authorized human review."
                    ],
                    "recommended_verification": [
                        "A qualified reviewer should compare the full effective revision "
                        f"of {candidate.asset_key} with the exact external source anchor.",
                        "Confirm whether additional restricted systems, records, or "
                        "validation evidence are applicable before accepting the relationship.",
                    ],
                    "external_evidence": external,
                    "internal_evidence": internal,
                    "confidence": round(min(0.9, max(0.35, candidate.retrieval_score)), 4),
                    "review_priority": self._priority(group.finding, candidate),
                }
                digest = canonical_sha256(payload)
                existing = await self.session.scalar(
                    select(ImpactHypothesis).where(
                        ImpactHypothesis.case_id == case.id,
                        ImpactHypothesis.finding_id == group.finding.id,
                        ImpactHypothesis.asset_version_id == str(candidate.asset_version_id),
                        ImpactHypothesis.relationship_type == relationship_type,
                    )
                )
                if existing is not None:
                    generated.append(existing)
                    continue
                hypothesis = ImpactHypothesis(
                    **payload,
                    hypothesis_sha256=digest,
                    created_by=created_by,
                )
                self.session.add(hypothesis)
                await self.session.flush()
                generated.append(hypothesis)
        return generated

    async def _version_hash(self, version_id: str) -> str:
        version = await self.session.get(InternalAssetVersion, version_id)
        if version is None:
            raise RuntimeError("Retrieved internal asset revision disappeared")
        return version.content_sha256

    @staticmethod
    def _external_evidence(finding: Finding, source: CaseSource) -> list[dict[str, Any]]:
        values = []
        for item in finding.evidence[:5]:
            anchor = str(item.get("source_anchor", "")).strip()
            excerpt = str(item.get("excerpt", "")).strip()
            if not anchor or not excerpt:
                continue
            values.append(
                EvidenceReference(
                    source_type="EXTERNAL_REGULATORY",
                    source_version_id=source.document_version_id,
                    source_hash=source.source_sha256,
                    anchor_id=anchor,
                    excerpt=excerpt[:4_000],
                    source_url=item.get("official_url"),
                ).model_dump(mode="json")
            )
        return values

    @staticmethod
    def _relationship_type(
        finding: Finding, candidate: InternalAssetCandidate
    ) -> str:
        category_text = " ".join(finding.categories).casefold()
        if candidate.asset_type == "SOP":
            return "FINDING_MAY_RELATE_TO_PROCEDURE"
        if candidate.asset_type == "System":
            return "FINDING_MAY_RELATE_TO_SYSTEM"
        if candidate.asset_type == "Training requirement":
            return "FINDING_MAY_RELATE_TO_TRAINING"
        if "validation" in category_text or candidate.asset_type == "Validation document":
            return "FINDING_MAY_RELATE_TO_VALIDATION"
        if candidate.asset_type == "Process":
            return "FINDING_MAY_RELATE_TO_PROCESS"
        return "FINDING_MAY_RELATE_TO_CONTROL"

    @staticmethod
    def _priority(finding: Finding, candidate: InternalAssetCandidate) -> str:
        text = " ".join([*finding.categories, finding.finding_text]).casefold()
        if candidate.retrieval_score >= 0.65 and any(
            term in text for term in ("steril", "aseptic", "data integrity", "audit trail")
        ):
            return "HIGH"
        if candidate.retrieval_score >= 0.45:
            return "MEDIUM"
        return "LOW"


async def hypothesis_response_rows(
    session: AsyncSession, case_id: str, authorized_asset_ids: set[str]
) -> list[tuple[ImpactHypothesis, InternalAsset, InternalAssetVersion]]:
    if not authorized_asset_ids:
        return []
    return list(
        (
            await session.execute(
                select(ImpactHypothesis, InternalAsset, InternalAssetVersion)
                .join(InternalAsset, InternalAsset.id == ImpactHypothesis.asset_id)
                .join(
                    InternalAssetVersion,
                    InternalAssetVersion.id == ImpactHypothesis.asset_version_id,
                )
                .where(
                    ImpactHypothesis.case_id == case_id,
                    ImpactHypothesis.asset_id.in_(sorted(authorized_asset_ids)),
                )
                .order_by(
                    ImpactHypothesis.review_priority.desc(),
                    ImpactHypothesis.created_at,
                    ImpactHypothesis.id,
                )
            )
        ).all()
    )
