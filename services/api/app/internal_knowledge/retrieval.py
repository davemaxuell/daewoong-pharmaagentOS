from __future__ import annotations

from collections import Counter

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.internal_knowledge.embedding import cosine_similarity, deterministic_embedding, tokens
from app.internal_knowledge.schemas import (
    InternalAnchor,
    InternalAssetCandidate,
    InternalAssetResponse,
    InternalAssetVersionResponse,
    KnowledgeSearchResponse,
    RelatedAssetResponse,
    RelatedAssetsResponse,
    RelationEvidenceResponse,
    RevisionHistoryResponse,
    RevisionSummary,
)
from app.internal_knowledge.seed import sha256_text
from app.models import (
    AssetRelation,
    AssetRelationStatus,
    InternalAsset,
    InternalAssetAcl,
    InternalAssetVersion,
    RelationEvidence,
)
from app.security.auth import Principal

CORPUS_NOTICE = (
    "Synthetic portfolio demonstration data only; not a real controlled quality system."
)


def _anchors(
    version: InternalAssetVersion, query_tokens: set[str] | None = None
) -> list[InternalAnchor]:
    values = []
    for item in version.anchors:
        excerpt = str(item.get("excerpt", ""))
        if query_tokens and not query_tokens.intersection(tokens(excerpt)):
            continue
        values.append(
            InternalAnchor(
                id=str(item["id"]),
                excerpt=excerpt,
                excerpt_sha256=sha256_text(excerpt),
            )
        )
    if not values and version.anchors:
        item = version.anchors[0]
        excerpt = str(item["excerpt"])
        values.append(
            InternalAnchor(
                id=str(item["id"]),
                excerpt=excerpt,
                excerpt_sha256=sha256_text(excerpt),
            )
        )
    return values[:5]


class KnowledgeRepository:
    """Retrieval boundary that always applies positive ACL grants before ranking."""

    def __init__(self, session: AsyncSession, principal: Principal) -> None:
        self.session = session
        self.principal = principal

    async def authorized_asset_ids(self) -> set[str]:
        clauses = [
            (InternalAssetAcl.principal_kind == "SUBJECT")
            & (InternalAssetAcl.principal_value == self.principal.subject)
        ]
        if self.principal.roles:
            clauses.append(
                (InternalAssetAcl.principal_kind == "ROLE")
                & (InternalAssetAcl.principal_value.in_(sorted(self.principal.roles)))
            )
        return set(
            (
                await self.session.scalars(
                    select(InternalAssetAcl.asset_id)
                    .where(InternalAssetAcl.permission == "READ", or_(*clauses))
                    .distinct()
                )
            ).all()
        )

    async def require_asset(self, asset_id: str) -> InternalAsset:
        authorized = await self.authorized_asset_ids()
        if asset_id not in authorized:
            # A single response covers absent and unauthorized IDs so metadata cannot leak.
            raise HTTPException(status_code=404, detail="Internal asset not found or unavailable")
        asset = await self.session.get(InternalAsset, asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="Internal asset not found or unavailable")
        return asset

    async def require_version(self, version_id: str) -> tuple[InternalAsset, InternalAssetVersion]:
        version = await self.session.get(InternalAssetVersion, version_id)
        if version is None:
            raise HTTPException(
                status_code=404,
                detail="Internal asset version not found or unavailable",
            )
        try:
            asset = await self.require_asset(version.asset_id)
        except HTTPException as exc:
            raise HTTPException(
                status_code=404, detail="Internal asset version not found or unavailable"
            ) from exc
        return asset, version

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        include_obsolete: bool = False,
    ) -> KnowledgeSearchResponse:
        authorized = await self.authorized_asset_ids()
        if not authorized:
            return KnowledgeSearchResponse(
                query=query,
                items=[],
                total_authorized_candidates=0,
                corpus_notice=CORPUS_NOTICE,
            )
        status_values = ["EFFECTIVE", "OBSOLETE"] if include_obsolete else ["EFFECTIVE"]
        statement = (
            select(InternalAsset, InternalAssetVersion)
            .join(InternalAssetVersion, InternalAssetVersion.asset_id == InternalAsset.id)
            .where(
                InternalAsset.id.in_(sorted(authorized)),
                InternalAssetVersion.status.in_(status_values),
            )
        )
        if not include_obsolete:
            statement = statement.where(
                InternalAssetVersion.id == InternalAsset.current_version_id
            )
        rows = (await self.session.execute(statement)).all()
        related_ids = set(
            (
                await self.session.scalars(
                    select(AssetRelation.source_asset_id).where(
                        AssetRelation.status == AssetRelationStatus.APPROVED.value,
                        AssetRelation.source_asset_id.in_(sorted(authorized)),
                        AssetRelation.target_asset_id.in_(sorted(authorized)),
                    )
                )
            ).all()
        )
        related_ids.update(
            (
                await self.session.scalars(
                    select(AssetRelation.target_asset_id).where(
                        AssetRelation.status == AssetRelationStatus.APPROVED.value,
                        AssetRelation.source_asset_id.in_(sorted(authorized)),
                        AssetRelation.target_asset_id.in_(sorted(authorized)),
                    )
                )
            ).all()
        )
        query_terms = tokens(query)
        query_set = set(query_terms)
        query_embedding = deterministic_embedding(query)
        ranked: list[InternalAssetCandidate] = []
        for asset, version in rows:
            document_terms = tokens(version.search_text)
            frequencies = Counter(document_terms)
            lexical = (
                sum(min(frequencies[term], 3) for term in query_set)
                / max(1, len(query_set) * 3)
            )
            if query.casefold() in version.search_text.casefold():
                lexical = min(1.0, lexical + 0.25)
            semantic_raw = cosine_similarity(query_embedding, version.embedding or [])
            semantic = max(0.0, min(1.0, (semantic_raw + 1.0) / 2.0))
            relation_score = 1.0 if asset.id in related_ids else 0.0
            combined = min(1.0, 0.55 * lexical + 0.35 * semantic + 0.10 * relation_score)
            if not query_set.intersection(document_terms) and semantic < 0.56:
                continue
            evidence = _anchors(version, query_set)
            ranked.append(
                InternalAssetCandidate(
                    asset_id=asset.id,
                    asset_key=asset.asset_key,
                    asset_type=asset.asset_type,
                    title=asset.title,
                    domain=asset.domain,
                    classification=asset.classification,
                    synthetic=True,
                    asset_version_id=version.id,
                    revision=version.revision,
                    effective_status=version.status,
                    effective_from=version.effective_from,
                    effective_to=version.effective_to,
                    relationship_signal=(
                        "APPROVED_RELATION_PRESENT" if relation_score else "LEXICAL_SEMANTIC_ONLY"
                    ),
                    internal_evidence_anchors=evidence,
                    retrieval_score=round(combined, 6),
                    lexical_score=round(lexical, 6),
                    semantic_score=round(semantic, 6),
                    relation_score=relation_score,
                    missing_metadata=[
                        name
                        for name, value in (
                            ("effective_from", version.effective_from),
                            ("anchors", version.anchors),
                        )
                        if not value
                    ],
                )
            )
        ranked.sort(
            key=lambda item: (
                -item.retrieval_score,
                item.effective_status != "EFFECTIVE",
                item.asset_key,
                -item.revision,
            )
        )
        return KnowledgeSearchResponse(
            query=query,
            items=ranked[:limit],
            total_authorized_candidates=len(rows),
            corpus_notice=CORPUS_NOTICE,
        )

    async def get_asset(self, asset_id: str) -> InternalAssetResponse:
        asset = await self.require_asset(asset_id)
        if not asset.current_version_id:
            raise HTTPException(status_code=409, detail="Internal asset has no current revision")
        _asset, version = await self.require_version(asset.current_version_id)
        return InternalAssetResponse(
            id=asset.id,
            asset_key=asset.asset_key,
            asset_type=asset.asset_type,
            title=asset.title,
            domain=asset.domain,
            classification=asset.classification,
            synthetic=True,
            lifecycle_status=asset.lifecycle_status,
            current_version_id=version.id,
            current_version=self._version_response(version),
        )

    async def get_document_version(self, version_id: str) -> InternalAssetVersionResponse:
        _asset, version = await self.require_version(version_id)
        return self._version_response(version)

    async def get_anchor(self, version_id: str, anchor_id: str) -> InternalAnchor:
        _asset, version = await self.require_version(version_id)
        item = next((item for item in version.anchors if item.get("id") == anchor_id), None)
        if item is None:
            raise HTTPException(status_code=404, detail="Internal anchor not found")
        excerpt = str(item["excerpt"])
        return InternalAnchor(
            id=anchor_id,
            excerpt=excerpt,
            excerpt_sha256=sha256_text(excerpt),
        )

    async def revision_history(self, asset_id: str) -> RevisionHistoryResponse:
        asset = await self.require_asset(asset_id)
        versions = list(
            (
                await self.session.scalars(
                    select(InternalAssetVersion)
                    .where(InternalAssetVersion.asset_id == asset.id)
                    .order_by(InternalAssetVersion.revision.desc())
                )
            ).all()
        )
        return RevisionHistoryResponse(
            asset_id=asset.id,
            asset_key=asset.asset_key,
            revisions=[
                RevisionSummary(
                    id=version.id,
                    revision=version.revision,
                    status=version.status,
                    effective_from=version.effective_from,
                    effective_to=version.effective_to,
                    content_sha256=version.content_sha256,
                    current=version.id == asset.current_version_id,
                )
                for version in versions
            ],
        )

    async def related_assets(self, asset_id: str) -> RelatedAssetsResponse:
        asset = await self.require_asset(asset_id)
        authorized = await self.authorized_asset_ids()
        relations = list(
            (
                await self.session.scalars(
                    select(AssetRelation).where(
                        AssetRelation.status == AssetRelationStatus.APPROVED.value,
                        or_(
                            (AssetRelation.source_asset_id == asset.id)
                            & (AssetRelation.target_asset_id.in_(sorted(authorized))),
                            (AssetRelation.target_asset_id == asset.id)
                            & (AssetRelation.source_asset_id.in_(sorted(authorized))),
                        ),
                    )
                )
            ).all()
        )
        items: list[RelatedAssetResponse] = []
        for relation in relations:
            outbound = relation.source_asset_id == asset.id
            other_id = relation.target_asset_id if outbound else relation.source_asset_id
            other = await self.require_asset(other_id)
            version = await self.session.get(InternalAssetVersion, other.current_version_id)
            if version is None:
                continue
            evidence_rows = list(
                (
                    await self.session.scalars(
                        select(RelationEvidence).where(
                            RelationEvidence.relation_id == relation.id
                        )
                    )
                ).all()
            )
            candidate = InternalAssetCandidate(
                asset_id=other.id,
                asset_key=other.asset_key,
                asset_type=other.asset_type,
                title=other.title,
                domain=other.domain,
                classification=other.classification,
                synthetic=True,
                asset_version_id=version.id,
                revision=version.revision,
                effective_status=version.status,
                effective_from=version.effective_from,
                effective_to=version.effective_to,
                relationship_signal=relation.relation_type,
                internal_evidence_anchors=_anchors(version),
                retrieval_score=relation.confidence,
                lexical_score=0,
                semantic_score=0,
                relation_score=1,
                missing_metadata=[],
            )
            items.append(
                RelatedAssetResponse(
                    relation_id=relation.id,
                    relation_type=relation.relation_type,
                    direction="OUTBOUND" if outbound else "INBOUND",
                    status="APPROVED",
                    confidence=relation.confidence,
                    rationale=relation.rationale,
                    asset=candidate,
                    evidence=[
                        RelationEvidenceResponse(
                            asset_version_id=evidence.asset_version_id,
                            content_sha256=evidence.content_sha256,
                            anchor=evidence.anchor,
                            excerpt_sha256=evidence.excerpt_sha256,
                            evidence_role=evidence.evidence_role,
                        )
                        for evidence in evidence_rows
                    ],
                )
            )
        items.sort(key=lambda item: (item.relation_type, item.asset.asset_key))
        return RelatedAssetsResponse(asset_id=asset.id, items=items)

    @staticmethod
    def _version_response(version: InternalAssetVersion) -> InternalAssetVersionResponse:
        return InternalAssetVersionResponse(
            id=version.id,
            asset_id=version.asset_id,
            revision=version.revision,
            status=version.status,
            effective_from=version.effective_from,
            effective_to=version.effective_to,
            content=version.content,
            content_sha256=version.content_sha256,
            anchors=_anchors(version),
            metadata=version.asset_metadata or {},
            created_at=version.created_at,
        )
