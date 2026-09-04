from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import add_audit_event
from app.cases.router import (
    _case_for_read,
    _require_case_write,
    _scoped_idempotency_key,
)
from app.config import Settings
from app.dependencies import session_dependency, settings_dependency
from app.integrations.schemas import (
    DocumentMetadataResponse,
    DraftCreateRequest,
    DraftReviewRequest,
    IntegrationDraftPage,
    IntegrationDraftResponse,
)
from app.integrations.service import create_draft
from app.internal_knowledge.retrieval import KnowledgeRepository
from app.models import IntegrationOutbox, utcnow
from app.security.auth import Principal, current_principal, require_roles

router = APIRouter(tags=["Controlled integrations"])
IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=16,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
DRAFT_CREATORS = require_roles("analyst", "system_owner")
DRAFT_REVIEWERS = require_roles("reviewer", "domain_sme")


def _response(draft: IntegrationOutbox) -> IntegrationDraftResponse:
    return IntegrationDraftResponse.model_validate(draft, from_attributes=True)


@router.post(
    "/cases/{case_id}/integration-drafts",
    response_model=IntegrationDraftResponse,
    status_code=201,
)
async def create_integration_draft(
    case_id: UUID,
    payload: DraftCreateRequest,
    request: Request,
    idempotency_key: IdempotencyKey,
    principal: Principal = Depends(DRAFT_CREATORS),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> IntegrationDraftResponse:
    case = await _case_for_read(session, case_id, principal)
    _require_case_write(case, principal)
    draft = await create_draft(
        session,
        case=case,
        principal=principal,
        channel=payload.channel,
        destination=payload.destination,
        title=payload.title,
        body=payload.body,
        run_id=str(payload.run_id) if payload.run_id else None,
        idempotency_key=f"integration:{_scoped_idempotency_key(principal, idempotency_key)}",
    )
    add_audit_event(
        session,
        principal=principal,
        request_id=request.state.request_id,
        operation="integration.draft.create",
        object_type="integration_outbox",
        object_id=draft.id,
        application_version=settings.app_version,
        after={
            "channel": draft.channel,
            "status": draft.status,
            "content_sha256": draft.content_sha256,
            "external_delivery_allowed": False,
        },
    )
    await session.commit()
    return _response(draft)


@router.get(
    "/cases/{case_id}/integration-drafts",
    response_model=IntegrationDraftPage,
)
async def list_integration_drafts(
    case_id: UUID,
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(session_dependency),
) -> IntegrationDraftPage:
    await _case_for_read(session, case_id, principal)
    rows = list(
        (
            await session.scalars(
                select(IntegrationOutbox)
                .where(IntegrationOutbox.case_id == str(case_id))
                .order_by(IntegrationOutbox.created_at.desc())
            )
        ).all()
    )
    return IntegrationDraftPage(items=[_response(item) for item in rows])


@router.post(
    "/integration-drafts/{draft_id}/review",
    response_model=IntegrationDraftResponse,
)
async def review_integration_draft(
    draft_id: UUID,
    payload: DraftReviewRequest,
    request: Request,
    principal: Principal = Depends(DRAFT_REVIEWERS),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> IntegrationDraftResponse:
    draft = await session.scalar(
        select(IntegrationOutbox)
        .where(IntegrationOutbox.id == str(draft_id))
        .with_for_update()
    )
    if draft is None:
        raise HTTPException(status_code=404, detail="Integration draft not found")
    await _case_for_read(session, UUID(draft.case_id), principal)
    if draft.requested_by == principal.subject:
        raise HTTPException(status_code=403, detail="Draft creator cannot independently review")
    if draft.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Integration draft is already decided")
    if draft.content_sha256 != payload.expected_content_sha256:
        raise HTTPException(status_code=409, detail="Integration draft content binding is stale")
    draft.status = (
        "REVIEWED_FOR_MANUAL_USE"
        if payload.decision == "review_for_manual_use"
        else "CANCELLED"
    )
    draft.reviewed_by = principal.subject
    draft.review_reason = payload.reason
    draft.reviewed_at = utcnow()
    add_audit_event(
        session,
        principal=principal,
        request_id=request.state.request_id,
        operation="integration.draft.review",
        object_type="integration_outbox",
        object_id=draft.id,
        application_version=settings.app_version,
        after={
            "status": draft.status,
            "content_sha256": draft.content_sha256,
            "external_delivery_allowed": False,
        },
    )
    await session.commit()
    return _response(draft)


@router.get(
    "/cases/{case_id}/document-metadata/{asset_version_id}",
    response_model=DocumentMetadataResponse,
)
async def read_document_metadata(
    case_id: UUID,
    asset_version_id: UUID,
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(session_dependency),
) -> DocumentMetadataResponse:
    await _case_for_read(session, case_id, principal)
    asset, version = await KnowledgeRepository(session, principal).require_version(
        str(asset_version_id)
    )
    return DocumentMetadataResponse(
        asset_id=asset.id,
        asset_version_id=version.id,
        asset_key=asset.asset_key,
        title=asset.title,
        asset_type=asset.asset_type,
        domain=asset.domain,
        revision=version.revision,
        effective_date=version.effective_from.isoformat() if version.effective_from else None,
        status=version.status,
        content_sha256=version.content_sha256,
    )
