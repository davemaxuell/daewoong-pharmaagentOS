from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
AnchorId = Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]


class StrictKnowledgeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_default=True)


class InternalAnchor(StrictKnowledgeModel):
    id: AnchorId
    excerpt: str = Field(min_length=1, max_length=4_000)
    excerpt_sha256: Sha256


class InternalAssetCandidate(StrictKnowledgeModel):
    asset_id: UUID
    asset_key: str
    asset_type: str
    title: str
    domain: str
    classification: str
    synthetic: Literal[True]
    asset_version_id: UUID
    revision: int = Field(ge=1)
    effective_status: str
    effective_from: date | None
    effective_to: date | None
    relationship_signal: str
    internal_evidence_anchors: list[InternalAnchor]
    access_status: Literal["AVAILABLE"] = "AVAILABLE"
    retrieval_score: float = Field(ge=0, le=1)
    lexical_score: float = Field(ge=0, le=1)
    semantic_score: float = Field(ge=0, le=1)
    relation_score: float = Field(ge=0, le=1)
    missing_metadata: list[str]


class KnowledgeSearchResponse(StrictKnowledgeModel):
    query: str
    items: list[InternalAssetCandidate]
    total_authorized_candidates: int
    acl_filtered_before_ranking: Literal[True] = True
    corpus_notice: str


class InternalAssetVersionResponse(StrictKnowledgeModel):
    id: UUID
    asset_id: UUID
    revision: int
    status: str
    effective_from: date | None
    effective_to: date | None
    content: str
    content_sha256: Sha256
    anchors: list[InternalAnchor]
    metadata: dict[str, object]
    created_at: datetime


class InternalAssetResponse(StrictKnowledgeModel):
    id: UUID
    asset_key: str
    asset_type: str
    title: str
    domain: str
    classification: str
    synthetic: Literal[True]
    lifecycle_status: str
    current_version_id: UUID
    current_version: InternalAssetVersionResponse


class RevisionSummary(StrictKnowledgeModel):
    id: UUID
    revision: int
    status: str
    effective_from: date | None
    effective_to: date | None
    content_sha256: Sha256
    current: bool


class RevisionHistoryResponse(StrictKnowledgeModel):
    asset_id: UUID
    asset_key: str
    revisions: list[RevisionSummary]


class RelationEvidenceResponse(StrictKnowledgeModel):
    asset_version_id: UUID
    content_sha256: Sha256
    anchor: AnchorId
    excerpt_sha256: Sha256
    evidence_role: str


class RelatedAssetResponse(StrictKnowledgeModel):
    relation_id: UUID
    relation_type: str
    direction: Literal["OUTBOUND", "INBOUND"]
    status: Literal["APPROVED"]
    confidence: float = Field(ge=0, le=1)
    rationale: str
    asset: InternalAssetCandidate
    evidence: list[RelationEvidenceResponse]


class RelatedAssetsResponse(StrictKnowledgeModel):
    asset_id: UUID
    items: list[RelatedAssetResponse]


class GenerateImpactRequest(StrictKnowledgeModel):
    query: str | None = Field(default=None, min_length=2, max_length=500)
    per_finding_limit: int = Field(default=5, ge=1, le=10)


class EvidenceReference(StrictKnowledgeModel):
    source_type: Literal["EXTERNAL_REGULATORY", "INTERNAL_ASSET"]
    source_version_id: UUID
    source_hash: Sha256
    anchor_id: str
    excerpt: str = Field(min_length=1, max_length=4_000)
    source_url: str | None = None


class ImpactHypothesisResponse(StrictKnowledgeModel):
    id: UUID
    case_id: UUID
    run_id: UUID | None
    finding_id: str
    asset_id: UUID
    asset_version_id: UUID
    asset_key: str
    asset_title: str
    asset_type: str
    asset_domain: str
    revision: int
    effective_status: str
    relationship_type: str
    statement: str
    known_facts: list[str]
    derived_relationships: list[str]
    assumptions: list[str]
    counterevidence: list[str]
    unknowns: list[str]
    recommended_verification: list[str]
    external_evidence: list[EvidenceReference]
    internal_evidence: list[EvidenceReference]
    confidence: float
    review_priority: str
    status: str
    hypothesis_sha256: Sha256
    created_by: str
    reviewed_by: str | None
    review_reason: str | None
    reviewed_at: datetime | None
    created_at: datetime
    decision_support_only: Literal[True] = True


class ImpactMapResponse(StrictKnowledgeModel):
    case_id: UUID
    generated_count: int = 0
    items: list[ImpactHypothesisResponse]
    notice: str = (
        "Hypotheses support human review only; they are not compliance, CAPA, or "
        "document-change decisions."
    )


class ImpactDecisionRequest(StrictKnowledgeModel):
    decision: Literal["accept", "reject"]
    expected_hypothesis_sha256: Sha256
    reason: str = Field(min_length=1, max_length=2_000)
