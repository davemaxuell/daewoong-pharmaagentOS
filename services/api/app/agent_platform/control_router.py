from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_platform.control_schemas import (
    ControlUpdateRequest,
    PlatformControlPage,
    PlatformControlResponse,
)
from app.audit import add_audit_event
from app.cases.hashing import canonical_sha256
from app.config import Settings
from app.dependencies import session_dependency, settings_dependency
from app.models import AgentVersion, PlatformControl, utcnow
from app.security.auth import Principal, require_roles

router = APIRouter(prefix="/control-tower/controls", tags=["Agent Control Tower"])
CONTROL_READERS = require_roles("platform_admin", "system_owner", "auditor")
CONTROL_OPERATORS = require_roles("platform_admin", "system_owner")


def _response(control: PlatformControl) -> PlatformControlResponse:
    return PlatformControlResponse.model_validate(control, from_attributes=True)


@router.get("", response_model=PlatformControlPage)
async def list_controls(
    _principal: Principal = Depends(CONTROL_READERS),
    session: AsyncSession = Depends(session_dependency),
) -> PlatformControlPage:
    controls = list(
        (await session.scalars(select(PlatformControl).order_by(PlatformControl.control_key))).all()
    )
    return PlatformControlPage(items=[_response(item) for item in controls])


async def _set_control(
    *,
    control_key: str,
    scope: str,
    agent_version_id: str | None,
    payload: ControlUpdateRequest,
    request: Request,
    principal: Principal,
    settings: Settings,
    session: AsyncSession,
) -> PlatformControlResponse:
    control = await session.scalar(
        select(PlatformControl)
        .where(PlatformControl.control_key == control_key)
        .with_for_update()
    )
    before: dict[str, object] | None = None
    if control:
        if payload.expected_revision is None or payload.expected_revision != control.revision:
            raise HTTPException(status_code=409, detail="Runtime control revision is stale")
        before = {"suspended": control.suspended, "revision": control.revision}
        control.suspended = payload.suspended
        control.reason = payload.reason
        control.revision += 1
        control.updated_by = principal.subject
        control.updated_at = utcnow()
    else:
        if payload.expected_revision is not None:
            raise HTTPException(status_code=409, detail="Runtime control does not exist")
        control = PlatformControl(
            control_key=control_key,
            scope=scope,
            agent_version_id=agent_version_id,
            suspended=payload.suspended,
            reason=payload.reason,
            updated_by=principal.subject,
        )
        session.add(control)
    await session.flush()
    add_audit_event(
        session,
        principal=principal,
        request_id=request.state.request_id,
        operation="runtime_control.update",
        object_type="platform_control",
        object_id=control.id,
        application_version=settings.app_version,
        before=before,
        after={
            "control_key": control.control_key,
            "suspended": control.suspended,
            "revision": control.revision,
            "reason_sha256": canonical_sha256(payload.reason),
        },
    )
    await session.commit()
    return _response(control)


@router.put("/global", response_model=PlatformControlResponse)
async def set_global_control(
    payload: ControlUpdateRequest,
    request: Request,
    principal: Principal = Depends(CONTROL_OPERATORS),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> PlatformControlResponse:
    return await _set_control(
        control_key="global",
        scope="GLOBAL",
        agent_version_id=None,
        payload=payload,
        request=request,
        principal=principal,
        settings=settings,
        session=session,
    )


@router.put("/agents/{agent_version_id}", response_model=PlatformControlResponse)
async def set_agent_control(
    agent_version_id: UUID,
    payload: ControlUpdateRequest,
    request: Request,
    principal: Principal = Depends(CONTROL_OPERATORS),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> PlatformControlResponse:
    identifier = str(agent_version_id)
    if await session.get(AgentVersion, identifier) is None:
        raise HTTPException(status_code=404, detail="Agent version not found")
    return await _set_control(
        control_key=f"agent:{identifier}",
        scope="AGENT",
        agent_version_id=identifier,
        payload=payload,
        request=request,
        principal=principal,
        settings=settings,
        session=session,
    )
