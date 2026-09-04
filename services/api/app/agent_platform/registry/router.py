from __future__ import annotations

from copy import deepcopy
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_platform.registry.schemas import (
    WorkflowTemplateCreateRequest,
    WorkflowTemplatePage,
    WorkflowTemplatePromotionRequest,
    WorkflowTemplateResponse,
)
from app.audit import add_audit_event
from app.cases.hashing import canonical_sha256
from app.cases.router import _scoped_idempotency_key
from app.config import Settings
from app.dependencies import session_dependency, settings_dependency
from app.models import RegistryReleaseStatus, ReleaseApproval, WorkflowTemplateVersion
from app.security.auth import Principal, require_roles, view_principal

router = APIRouter(prefix="/workflow-templates", tags=["Workflow templates"])

IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=16,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
TEMPLATE_CREATORS = require_roles("agent_developer")
TEMPLATE_PROMOTERS = require_roles("system_owner")


def _response(template: WorkflowTemplateVersion) -> WorkflowTemplateResponse:
    return WorkflowTemplateResponse(
        id=template.id,
        workflow_key=template.workflow_key,
        version=template.version,
        display_name=template.display_name,
        manifest=dict(template.manifest or {}),
        manifest_sha256=template.manifest_sha256,
        release_status=template.release_status,
        created_by=template.created_by,
        created_at=template.created_at,
    )


def _validate_manifest(payload: WorkflowTemplateCreateRequest) -> str:
    manifest = payload.manifest
    metadata = manifest.get("metadata")
    spec = manifest.get("spec")
    if (
        manifest.get("apiVersion") != "pharmaagent.io/v1"
        or manifest.get("kind") != "Workflow"
        or not isinstance(metadata, dict)
        or not isinstance(spec, dict)
    ):
        raise HTTPException(status_code=422, detail="Workflow manifest structure is invalid")
    if metadata.get("name") != payload.workflow_key or metadata.get("version") != payload.version:
        raise HTTPException(status_code=422, detail="Workflow manifest identity does not match")
    declared_hash = metadata.get("definitionHash")
    canonical = deepcopy(manifest)
    canonical_metadata = canonical.get("metadata")
    if isinstance(canonical_metadata, dict):
        canonical_metadata.pop("definitionHash", None)
    actual_hash = canonical_sha256(canonical)
    if declared_hash != actual_hash:
        raise HTTPException(status_code=422, detail="Workflow definition hash does not match")
    if metadata.get("releaseState") != RegistryReleaseStatus.DRAFT.value:
        raise HTTPException(status_code=422, detail="New workflow versions must begin in DRAFT")
    if spec.get("executionEnabled") is not False:
        raise HTTPException(status_code=422, detail="Draft workflow cannot enable execution")
    return actual_hash


@router.get("", response_model=WorkflowTemplatePage)
async def list_workflow_templates(
    _principal: Principal = Depends(view_principal),
    session: AsyncSession = Depends(session_dependency),
) -> WorkflowTemplatePage:
    rows = list(
        (
            await session.scalars(
                select(WorkflowTemplateVersion).order_by(
                    WorkflowTemplateVersion.workflow_key,
                    WorkflowTemplateVersion.version.desc(),
                )
            )
        ).all()
    )
    return WorkflowTemplatePage(items=[_response(item) for item in rows])


@router.get("/{template_id}", response_model=WorkflowTemplateResponse)
async def get_workflow_template(
    template_id: UUID,
    _principal: Principal = Depends(view_principal),
    session: AsyncSession = Depends(session_dependency),
) -> WorkflowTemplateResponse:
    template = await session.get(WorkflowTemplateVersion, str(template_id))
    if not template:
        raise HTTPException(status_code=404, detail="Workflow template version not found")
    return _response(template)


@router.post("", response_model=WorkflowTemplateResponse, status_code=201)
async def create_workflow_template(
    payload: WorkflowTemplateCreateRequest,
    request: Request,
    idempotency_key: IdempotencyKey,
    principal: Principal = Depends(TEMPLATE_CREATORS),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> WorkflowTemplateResponse:
    manifest_hash = _validate_manifest(payload)
    stored_key = _scoped_idempotency_key(principal, idempotency_key)
    existing = await session.scalar(
        select(WorkflowTemplateVersion).where(
            WorkflowTemplateVersion.workflow_key == payload.workflow_key,
            WorkflowTemplateVersion.version == payload.version,
        )
    )
    if existing:
        if existing.manifest_sha256 != manifest_hash:
            raise HTTPException(status_code=409, detail="Workflow version already exists")
        return _response(existing)
    template = WorkflowTemplateVersion(
        workflow_key=payload.workflow_key,
        version=payload.version,
        display_name=payload.display_name,
        manifest=payload.manifest,
        manifest_sha256=manifest_hash,
        release_status=RegistryReleaseStatus.DRAFT.value,
        created_by=principal.subject,
    )
    session.add(template)
    await session.flush()
    add_audit_event(
        session,
        principal=principal,
        request_id=request.state.request_id,
        operation="workflow_template.create",
        object_type="workflow_template_version",
        object_id=template.id,
        application_version=settings.app_version,
        after={
            "workflow_key": template.workflow_key,
            "version": template.version,
            "manifest_sha256": template.manifest_sha256,
            "idempotency_scope": stored_key,
        },
    )
    await session.commit()
    return _response(template)


@router.post("/{template_id}/promote", response_model=WorkflowTemplateResponse)
async def promote_workflow_template(
    template_id: UUID,
    payload: WorkflowTemplatePromotionRequest,
    request: Request,
    _idempotency_key: IdempotencyKey,
    principal: Principal = Depends(TEMPLATE_PROMOTERS),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> WorkflowTemplateResponse:
    template = await session.scalar(
        select(WorkflowTemplateVersion)
        .where(WorkflowTemplateVersion.id == str(template_id))
        .with_for_update()
    )
    if not template:
        raise HTTPException(status_code=404, detail="Workflow template version not found")
    transitions = {
        "DRAFT": {"APPROVED", "RETIRED"},
        "APPROVED": {"PRODUCTION", "SUSPENDED", "RETIRED"},
        "PRODUCTION": {"SUSPENDED", "RETIRED"},
        "SUSPENDED": {"APPROVED", "RETIRED"},
    }
    if payload.target_status not in transitions.get(template.release_status, set()):
        raise HTTPException(status_code=409, detail="Workflow release transition is not allowed")
    if payload.target_status == RegistryReleaseStatus.PRODUCTION.value:
        release_approval = await session.scalar(
            select(ReleaseApproval.id).where(
                ReleaseApproval.target_kind == "WORKFLOW_VERSION",
                ReleaseApproval.target_version_id == template.id,
                ReleaseApproval.target_sha256 == template.manifest_sha256,
                ReleaseApproval.target_status == RegistryReleaseStatus.PRODUCTION.value,
                ReleaseApproval.decision == "APPROVED",
            )
        )
        if release_approval is None:
            raise HTTPException(
                status_code=409,
                detail="Production promotion requires an approved evaluation release gate",
            )
    before = template.release_status
    template.release_status = payload.target_status
    add_audit_event(
        session,
        principal=principal,
        request_id=request.state.request_id,
        operation="workflow_template.promote",
        object_type="workflow_template_version",
        object_id=template.id,
        application_version=settings.app_version,
        before={"release_status": before},
        after={
            "release_status": template.release_status,
            "reason_sha256": canonical_sha256(payload.reason),
        },
    )
    await session.commit()
    return _response(template)
