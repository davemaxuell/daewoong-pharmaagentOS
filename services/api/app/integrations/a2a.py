from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import add_audit_event
from app.cases.hashing import canonical_sha256
from app.cases.router import _case_for_read
from app.config import Settings
from app.dependencies import session_dependency, settings_dependency
from app.integrations.schemas import A2ATaskRequest, A2ATaskResponse
from app.models import A2AExchange, Artifact, ArtifactVersion
from app.security.auth import Principal, _roles_from_value, require_roles

router = APIRouter(tags=["A2A interoperability"])
SERVICE_CALLERS = require_roles("service")


@router.get("/.well-known/agent-card.json", include_in_schema=False)
async def agent_card() -> dict[str, object]:
    return {
        "name": "PharmaAgent OS",
        "version": "1.0.0",
        "description": "Governed pharmaceutical regulatory decision-support agent.",
        "capabilities": {
            "answer_only": True,
            "streaming": False,
            "tool_delegation": False,
            "controlled_system_writes": False,
        },
        "intents": ["CASE_STATUS", "APPROVED_ARTIFACT_METADATA"],
        "authentication": {"type": "oauth2", "audience_bound": True},
    }


def _response(exchange: A2AExchange) -> A2ATaskResponse:
    return A2ATaskResponse(
        id=exchange.id,
        task_key=exchange.task_key,
        case_id=exchange.case_id,
        intent=exchange.intent,
        status="COMPLETED",
        response=dict(exchange.response_payload or {}),
        request_sha256=exchange.request_sha256,
        response_sha256=exchange.response_sha256,
        created_at=exchange.created_at,
    )


@router.post("/api/v1/a2a/tasks", response_model=A2ATaskResponse, status_code=201)
async def answer_a2a_task(
    payload: A2ATaskRequest,
    request: Request,
    service: Principal = Depends(SERVICE_CALLERS),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> A2ATaskResponse:
    request_data = payload.model_dump(mode="json")
    request_sha256 = canonical_sha256(request_data)
    existing = await session.scalar(
        select(A2AExchange).where(A2AExchange.task_key == payload.task_key)
    )
    if existing:
        if existing.request_sha256 != request_sha256:
            raise HTTPException(status_code=409, detail="A2A task key payload conflict")
        return _response(existing)
    delegated_roles = _roles_from_value(payload.delegated_roles)
    if not delegated_roles:
        raise HTTPException(status_code=403, detail="A2A delegation has no recognized role")
    delegated = Principal(payload.delegated_subject, frozenset(delegated_roles))
    case = await _case_for_read(session, payload.case_id, delegated)
    response: dict[str, object] = {
        "case_id": case.id,
        "case_status": case.status,
        "current_state_hash": case.current_state_hash,
        "decision_support_only": True,
    }
    if payload.intent == "APPROVED_ARTIFACT_METADATA":
        artifacts = list(
            (
                await session.execute(
                    select(ArtifactVersion.id, ArtifactVersion.content_sha256)
                    .join(Artifact, Artifact.id == ArtifactVersion.artifact_id)
                    .where(
                        Artifact.case_id == case.id,
                        ArtifactVersion.status == "APPROVED",
                    )
                    .order_by(ArtifactVersion.created_at.desc())
                )
            ).all()
        )
        response["approved_artifacts"] = [
            {"artifact_version_id": item.id, "content_sha256": item.content_sha256}
            for item in artifacts
        ]
    response_sha256 = canonical_sha256(response)
    exchange = A2AExchange(
        case_id=case.id,
        task_key=payload.task_key,
        intent=payload.intent,
        request_payload=request_data,
        request_sha256=request_sha256,
        response_payload=response,
        response_sha256=response_sha256,
        status="COMPLETED",
        requester_service=service.subject,
        delegated_subject=delegated.subject,
    )
    session.add(exchange)
    await session.flush()
    add_audit_event(
        session,
        principal=service,
        request_id=request.state.request_id,
        operation="a2a.answer.create",
        object_type="a2a_exchange",
        object_id=exchange.id,
        application_version=settings.app_version,
        after={
            "case_id": exchange.case_id,
            "intent": exchange.intent,
            "request_sha256": exchange.request_sha256,
            "response_sha256": exchange.response_sha256,
            "answer_only": True,
        },
        context={"delegated_subject": exchange.delegated_subject},
    )
    await session.commit()
    return _response(exchange)
