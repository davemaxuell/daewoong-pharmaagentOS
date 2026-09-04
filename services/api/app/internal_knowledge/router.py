from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import add_audit_event
from app.cases.router import (
    _append_event,
    _case_for_read,
    _event_key,
    _request_fingerprint,
    _require_case_write,
)
from app.config import Settings
from app.dependencies import session_dependency, settings_dependency
from app.internal_knowledge.agents import ImpactAnalysisAgent, hypothesis_response_rows
from app.internal_knowledge.retrieval import KnowledgeRepository
from app.internal_knowledge.schemas import (
    GenerateImpactRequest,
    ImpactDecisionRequest,
    ImpactHypothesisResponse,
    ImpactMapResponse,
    InternalAnchor,
    InternalAssetResponse,
    InternalAssetVersionResponse,
    KnowledgeSearchResponse,
    RelatedAssetsResponse,
    RevisionHistoryResponse,
)
from app.models import CaseEvent, ImpactHypothesis, ImpactHypothesisStatus, utcnow
from app.security.auth import Principal, current_principal, require_roles

router = APIRouter(tags=["Internal Knowledge and Impact"])

IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=16,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
IMPACT_GENERATORS = require_roles("analyst", "system_owner")
IMPACT_REVIEWERS = require_roles("reviewer", "domain_sme")


def _hypothesis_response(
    row: tuple[ImpactHypothesis, Any, Any],
) -> ImpactHypothesisResponse:
    hypothesis, asset, version = row
    return ImpactHypothesisResponse(
        id=hypothesis.id,
        case_id=hypothesis.case_id,
        run_id=hypothesis.run_id,
        finding_id=hypothesis.finding_id,
        asset_id=hypothesis.asset_id,
        asset_version_id=hypothesis.asset_version_id,
        asset_key=asset.asset_key,
        asset_title=asset.title,
        asset_type=asset.asset_type,
        asset_domain=asset.domain,
        revision=version.revision,
        effective_status=version.status,
        relationship_type=hypothesis.relationship_type,
        statement=hypothesis.statement,
        known_facts=hypothesis.known_facts,
        derived_relationships=hypothesis.derived_relationships,
        assumptions=hypothesis.assumptions,
        counterevidence=hypothesis.counterevidence,
        unknowns=hypothesis.unknowns,
        recommended_verification=hypothesis.recommended_verification,
        external_evidence=hypothesis.external_evidence,
        internal_evidence=hypothesis.internal_evidence,
        confidence=hypothesis.confidence,
        review_priority=hypothesis.review_priority,
        status=hypothesis.status,
        hypothesis_sha256=hypothesis.hypothesis_sha256,
        created_by=hypothesis.created_by,
        reviewed_by=hypothesis.reviewed_by,
        review_reason=hypothesis.review_reason,
        reviewed_at=hypothesis.reviewed_at,
        created_at=hypothesis.created_at,
    )


async def _impact_map(
    session: AsyncSession,
    case_id: str,
    principal: Principal,
    *,
    generated_count: int = 0,
) -> ImpactMapResponse:
    authorized = await KnowledgeRepository(session, principal).authorized_asset_ids()
    rows = await hypothesis_response_rows(session, case_id, authorized)
    return ImpactMapResponse(
        case_id=case_id,
        generated_count=generated_count,
        items=[_hypothesis_response(row) for row in rows],
    )


@router.get(
    "/cases/{case_id}/knowledge/search", response_model=KnowledgeSearchResponse
)
async def search_case_knowledge(
    case_id: UUID,
    q: str = Query(min_length=2, max_length=500),
    limit: int = Query(default=10, ge=1, le=20),
    include_obsolete: bool = Query(default=False),
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(session_dependency),
) -> KnowledgeSearchResponse:
    await _case_for_read(session, case_id, principal)
    return await KnowledgeRepository(session, principal).search(
        q, limit=limit, include_obsolete=include_obsolete
    )


@router.get(
    "/cases/{case_id}/knowledge/assets/{asset_id}", response_model=InternalAssetResponse
)
async def get_case_asset(
    case_id: UUID,
    asset_id: UUID,
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(session_dependency),
) -> InternalAssetResponse:
    await _case_for_read(session, case_id, principal)
    return await KnowledgeRepository(session, principal).get_asset(str(asset_id))


@router.get(
    "/cases/{case_id}/knowledge/versions/{version_id}",
    response_model=InternalAssetVersionResponse,
)
async def get_case_asset_version(
    case_id: UUID,
    version_id: UUID,
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(session_dependency),
) -> InternalAssetVersionResponse:
    await _case_for_read(session, case_id, principal)
    return await KnowledgeRepository(session, principal).get_document_version(str(version_id))


@router.get(
    "/cases/{case_id}/knowledge/versions/{version_id}/anchors/{anchor_id}",
    response_model=InternalAnchor,
)
async def get_case_asset_anchor(
    case_id: UUID,
    version_id: UUID,
    anchor_id: str,
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(session_dependency),
) -> InternalAnchor:
    await _case_for_read(session, case_id, principal)
    return await KnowledgeRepository(session, principal).get_anchor(str(version_id), anchor_id)


@router.get(
    "/cases/{case_id}/knowledge/assets/{asset_id}/revisions",
    response_model=RevisionHistoryResponse,
)
async def get_case_asset_revisions(
    case_id: UUID,
    asset_id: UUID,
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(session_dependency),
) -> RevisionHistoryResponse:
    await _case_for_read(session, case_id, principal)
    return await KnowledgeRepository(session, principal).revision_history(str(asset_id))


@router.get(
    "/cases/{case_id}/knowledge/assets/{asset_id}/related",
    response_model=RelatedAssetsResponse,
)
async def get_case_related_assets(
    case_id: UUID,
    asset_id: UUID,
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(session_dependency),
) -> RelatedAssetsResponse:
    await _case_for_read(session, case_id, principal)
    return await KnowledgeRepository(session, principal).related_assets(str(asset_id))


@router.get("/cases/{case_id}/impact", response_model=ImpactMapResponse)
async def get_impact_map(
    case_id: UUID,
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(session_dependency),
) -> ImpactMapResponse:
    await _case_for_read(session, case_id, principal)
    return await _impact_map(session, str(case_id), principal)


@router.post("/cases/{case_id}/impact/generate", response_model=ImpactMapResponse)
async def generate_impact_map(
    case_id: UUID,
    payload: GenerateImpactRequest,
    request: Request,
    idempotency_key: IdempotencyKey,
    principal: Principal = Depends(IMPACT_GENERATORS),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> ImpactMapResponse:
    case = await _case_for_read(session, case_id, principal, lock=True)
    _require_case_write(case, principal)
    event_key = _event_key("impact-generate", principal, idempotency_key)
    fingerprint = _request_fingerprint(payload.model_dump(mode="json"))
    prior = await session.scalar(
        select(CaseEvent).where(
            CaseEvent.case_id == case.id,
            CaseEvent.idempotency_key == event_key,
        )
    )
    if prior is not None:
        if prior.payload.get("request_fingerprint") != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency key payload conflict")
        return await _impact_map(session, case.id, principal)

    hypotheses = await ImpactAnalysisAgent(session, principal).generate_for_case(
        case,
        created_by=principal.subject,
        query_override=payload.query,
        per_finding_limit=payload.per_finding_limit,
    )
    await _append_event(
        session,
        case=case,
        event_type="IMPACT_HYPOTHESES_GENERATED",
        principal=principal,
        request_id=request.state.request_id,
        idempotency_key=event_key,
        payload={
            "request_fingerprint": fingerprint,
            "hypothesis_ids": [item.id for item in hypotheses],
            "generated_count": len(hypotheses),
            "agent": {"name": "impact-analysis-agent", "version": "1.0.0"},
            "decision_support_only": True,
        },
    )
    add_audit_event(
        session,
        principal=principal,
        request_id=request.state.request_id,
        operation="case.impact.generate",
        object_type="case",
        object_id=case.id,
        application_version=settings.app_version,
        after={"hypothesis_ids": [item.id for item in hypotheses]},
    )
    await session.commit()
    return await _impact_map(
        session, case.id, principal, generated_count=len(hypotheses)
    )


@router.post(
    "/cases/{case_id}/impact/{hypothesis_id}/decision",
    response_model=ImpactHypothesisResponse,
)
async def decide_impact_hypothesis(
    case_id: UUID,
    hypothesis_id: UUID,
    payload: ImpactDecisionRequest,
    request: Request,
    idempotency_key: IdempotencyKey,
    principal: Principal = Depends(IMPACT_REVIEWERS),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> ImpactHypothesisResponse:
    case = await _case_for_read(session, case_id, principal, lock=True)
    hypothesis = await session.scalar(
        select(ImpactHypothesis)
        .where(
            ImpactHypothesis.id == str(hypothesis_id),
            ImpactHypothesis.case_id == case.id,
        )
        .with_for_update()
    )
    if hypothesis is None:
        raise HTTPException(status_code=404, detail="Impact hypothesis not found")
    await KnowledgeRepository(session, principal).require_asset(hypothesis.asset_id)
    event_key = _event_key("impact-decision", principal, idempotency_key)
    fingerprint = _request_fingerprint(payload.model_dump(mode="json"))
    prior = await session.scalar(
        select(CaseEvent).where(
            CaseEvent.case_id == case.id,
            CaseEvent.idempotency_key == event_key,
        )
    )
    if prior is not None:
        if prior.payload.get("request_fingerprint") != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency key payload conflict")
    else:
        if hypothesis.hypothesis_sha256 != payload.expected_hypothesis_sha256:
            raise HTTPException(status_code=409, detail="Impact hypothesis is stale")
        if hypothesis.status != ImpactHypothesisStatus.PROPOSED.value:
            raise HTTPException(status_code=409, detail="Impact hypothesis is already reviewed")
        if hypothesis.created_by == principal.subject:
            raise HTTPException(status_code=403, detail="Independent impact review is required")
        hypothesis.status = (
            ImpactHypothesisStatus.ACCEPTED.value
            if payload.decision == "accept"
            else ImpactHypothesisStatus.REJECTED.value
        )
        hypothesis.reviewed_by = principal.subject
        hypothesis.review_reason = payload.reason
        hypothesis.reviewed_at = utcnow()
        await _append_event(
            session,
            case=case,
            event_type=f"IMPACT_HYPOTHESIS_{hypothesis.status}",
            principal=principal,
            request_id=request.state.request_id,
            idempotency_key=event_key,
            payload={
                "request_fingerprint": fingerprint,
                "hypothesis_id": hypothesis.id,
                "hypothesis_sha256": hypothesis.hypothesis_sha256,
                "status": hypothesis.status,
            },
        )
        add_audit_event(
            session,
            principal=principal,
            request_id=request.state.request_id,
            operation="case.impact.decision",
            object_type="impact_hypothesis",
            object_id=hypothesis.id,
            application_version=settings.app_version,
            after={"status": hypothesis.status, "reason": payload.reason},
        )
        await session.commit()
    authorized = await KnowledgeRepository(session, principal).authorized_asset_ids()
    rows = await hypothesis_response_rows(session, case.id, authorized)
    row = next((row for row in rows if row[0].id == hypothesis.id), None)
    if row is None:
        raise HTTPException(status_code=404, detail="Impact hypothesis not found")
    return _hypothesis_response(row)
