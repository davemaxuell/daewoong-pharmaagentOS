from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_platform.controls import active_suspension
from app.agent_platform.runtime.schemas import (
    AgentInvocationResponse,
    CaseRunResponse,
    InvocationUsage,
    RunCheckpointResponse,
    RunControlRequest,
    RunEventPage,
    RunEventResponse,
    RunStartRequest,
    RunStepStateResponse,
    StepApprovalDecisionRequest,
    StepResultRequest,
    WorkflowBindingResponse,
)
from app.agent_platform.runtime.service import (
    ACTIVE_RUN_STATUSES,
    TERMINAL_RUN_STATUSES,
    append_run_event,
    complete_step,
    initial_checkpoint,
    queue_run_advance,
)
from app.agent_platform.temporal.client import best_effort_start_or_wake
from app.audit import add_audit_event
from app.cases.hashing import canonical_sha256
from app.cases.router import (
    _append_event,
    _case_for_read,
    _event_key,
    _request_fingerprint,
    _require_case_read,
    _require_case_write,
    _scoped_idempotency_key,
)
from app.config import Settings
from app.dependencies import session_dependency, settings_dependency
from app.models import (
    AgentCaseStatus,
    AgentInvocation,
    AgentInvocationStatus,
    AgentRunStatus,
    AgentVersion,
    ApprovalRequest,
    ApprovalStatus,
    Case,
    CasePlan,
    CasePlanStep,
    CaseRun,
    RegistryReleaseStatus,
    RunEvent,
    SkillVersion,
    ToolVersion,
    WorkflowTemplateVersion,
    utcnow,
)
from app.pagination import InvalidCursor, decode_cursor, encode_cursor
from app.security.auth import Principal, current_principal, require_roles

router = APIRouter(tags=["Case runs"])

IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=16,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
RUN_WORKERS = require_roles("service", "system_owner")
RUN_APPROVERS = require_roles("reviewer")


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def _run_for_read(
    session: AsyncSession,
    run_id: UUID,
    principal: Principal,
    *,
    lock: bool = False,
) -> tuple[CaseRun, Case]:
    query = select(CaseRun).where(CaseRun.id == str(run_id))
    if lock:
        query = query.with_for_update()
    run = await session.scalar(query)
    if not run:
        raise HTTPException(status_code=404, detail="Case run not found")
    case = await session.get(Case, run.case_id)
    if not case:
        raise HTTPException(status_code=409, detail="Case run binding is unavailable")
    _require_case_read(case, principal)
    return run, case


def _invocation_response(invocation: AgentInvocation) -> AgentInvocationResponse:
    return AgentInvocationResponse(
        id=invocation.id,
        run_id=invocation.run_id,
        case_id=invocation.case_id,
        plan_step_id=invocation.plan_step_id,
        step_key=invocation.step_key,
        attempt=invocation.attempt,
        agent_version_id=invocation.agent_version_id,
        status=invocation.status,
        output_schema_ref=invocation.output_schema_ref,
        input_sha256=invocation.input_sha256,
        output_sha256=invocation.output_sha256,
        limits=dict(invocation.limits or {}),
        usage=InvocationUsage.model_validate(invocation.usage or {}),
        error_code=invocation.error_code,
        started_at=invocation.started_at,
        completed_at=invocation.completed_at,
        created_at=invocation.created_at,
    )


def _checkpoint_response(value: dict[str, Any]) -> RunCheckpointResponse:
    workflow = dict(value.get("workflow_template") or {})
    control = dict(value.get("control") or {})
    return RunCheckpointResponse(
        schema_version=value.get("schema_version"),
        checkpoint_version=int(value.get("checkpoint_version", 0)),
        step_key=value.get("step_key"),
        workflow_template=WorkflowBindingResponse.model_validate(workflow),
        steps={
            str(key): RunStepStateResponse.model_validate(step)
            for key, step in (value.get("steps") or {}).items()
        },
        budget=InvocationUsage.model_validate(value.get("budget") or {}),
        pause_requested=bool(control.get("pause_requested")),
        cancel_requested=bool(control.get("cancel_requested")),
    )


async def _run_response(session: AsyncSession, run: CaseRun) -> CaseRunResponse:
    active = await session.scalar(
        select(AgentInvocation)
        .where(
            AgentInvocation.run_id == run.id,
            AgentInvocation.status.in_(
                [
                    AgentInvocationStatus.PENDING.value,
                    AgentInvocationStatus.RUNNING.value,
                    AgentInvocationStatus.WAITING_FOR_APPROVAL.value,
                ]
            ),
        )
        .order_by(AgentInvocation.created_at.desc())
        .limit(1)
    )
    return CaseRunResponse(
        id=run.id,
        case_id=run.case_id,
        plan_id=run.plan_id,
        plan_version=run.plan_version,
        plan_sha256=run.plan_sha256,
        bound_state_hash=run.bound_state_hash,
        status=run.status,
        requested_by=run.requested_by,
        checkpoint=_checkpoint_response(dict(run.checkpoint or {})),
        active_invocation=_invocation_response(active) if active else None,
        error_code=run.error_code,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
    )


def _run_event_response(event: RunEvent) -> RunEventResponse:
    return RunEventResponse(
        id=event.id,
        run_id=event.run_id,
        case_id=event.case_id,
        sequence=event.sequence,
        event_type=event.event_type,
        actor_type=event.actor_type,
        actor_id=event.actor_id,
        request_id=event.request_id,
        payload=dict(event.payload or {}),
        previous_event_hash=event.previous_event_hash,
        event_hash=event.event_hash,
        occurred_at=event.occurred_at,
    )


async def _validate_release_bindings(session: AsyncSession, plan: CasePlan) -> None:
    template = await session.get(WorkflowTemplateVersion, plan.workflow_template_version_id)
    approved = {RegistryReleaseStatus.APPROVED.value, RegistryReleaseStatus.PRODUCTION.value}
    if (
        not template
        or template.release_status not in approved
        or not bool(((template.manifest or {}).get("spec") or {}).get("executionEnabled"))
    ):
        raise HTTPException(status_code=409, detail="Workflow template is not executable")
    steps = list(
        (
            await session.scalars(
                select(CasePlanStep).where(CasePlanStep.plan_id == plan.id)
            )
        ).all()
    )
    suspension = await active_suspension(
        session, (step.agent_version_id for step in steps if step.agent_version_id)
    )
    if suspension:
        raise HTTPException(
            status_code=503,
            detail=f"Agent runtime is suspended by {suspension.control_key}",
            headers={"Retry-After": "60"},
        )
    checks: tuple[tuple[type[Any], set[str], str], ...] = (
        (
            AgentVersion,
            {step.agent_version_id for step in steps if step.agent_version_id},
            "Agent",
        ),
        (
            SkillVersion,
            {item for step in steps for item in (step.skill_version_ids or [])},
            "Skill",
        ),
        (
            ToolVersion,
            {item for step in steps for item in (step.tool_version_ids or [])},
            "Tool",
        ),
    )
    for model, identifiers, label in checks:
        if not identifiers:
            continue
        available = set(
            await session.scalars(
                select(model.id).where(
                    model.id.in_(identifiers), model.release_status.in_(approved)
                )
            )
        )
        if available != identifiers:
            raise HTTPException(status_code=409, detail=f"{label} release binding is unavailable")


@router.post("/cases/{case_id}/runs", response_model=CaseRunResponse, status_code=201)
async def start_case_run(
    case_id: UUID,
    payload: RunStartRequest,
    request: Request,
    idempotency_key: IdempotencyKey,
    principal: Principal = Depends(current_principal),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> CaseRunResponse:
    fingerprint = _request_fingerprint(payload.model_dump(mode="json"))
    stored_key = f"run:{_scoped_idempotency_key(principal, idempotency_key)}"
    existing = await session.scalar(select(CaseRun).where(CaseRun.idempotency_key == stored_key))
    if existing:
        prior = await session.scalar(
            select(RunEvent).where(
                RunEvent.run_id == existing.id,
                RunEvent.idempotency_key == f"run-started:{stored_key}",
            )
        )
        if not prior or prior.payload.get("request_fingerprint") != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency key payload conflict")
        replay_case = await session.get(Case, existing.case_id)
        if not replay_case:
            raise HTTPException(status_code=409, detail="Idempotent run result is unavailable")
        _require_case_write(replay_case, principal)
        await best_effort_start_or_wake(settings, existing.id)
        return await _run_response(session, existing)

    case = await _case_for_read(session, case_id, principal, lock=True)
    _require_case_write(case, principal)
    quota_since = utcnow() - timedelta(hours=1)
    recent_runs = int(
        await session.scalar(
            select(func.count()).select_from(CaseRun).where(
                CaseRun.requested_by == principal.subject,
                CaseRun.created_at >= quota_since,
            )
        )
        or 0
    )
    active_runs = int(
        await session.scalar(
            select(func.count()).select_from(CaseRun).where(
                CaseRun.requested_by == principal.subject,
                CaseRun.status.in_(ACTIVE_RUN_STATUSES),
            )
        )
        or 0
    )
    if recent_runs >= settings.agent_run_rate_limit_per_hour:
        raise HTTPException(
            status_code=429,
            detail="Hourly agent-run quota exceeded",
            headers={"Retry-After": "3600"},
        )
    if active_runs >= settings.agent_active_runs_per_subject:
        raise HTTPException(
            status_code=429,
            detail="Concurrent agent-run quota exceeded",
            headers={"Retry-After": "60"},
        )
    if case.status != AgentCaseStatus.READY.value:
        raise HTTPException(status_code=409, detail="Case is not ready for execution")
    active = await session.scalar(
        select(CaseRun.id).where(
            CaseRun.case_id == case.id,
            CaseRun.status.in_(ACTIVE_RUN_STATUSES),
        )
    )
    if active:
        raise HTTPException(status_code=409, detail="Case already has an active run")
    latest_version = int(
        await session.scalar(select(func.max(CasePlan.version)).where(CasePlan.case_id == case.id))
        or 0
    )
    if payload.plan_version != latest_version:
        raise HTTPException(status_code=409, detail="Only the latest plan version may execute")
    plan = await session.scalar(
        select(CasePlan).where(
            CasePlan.case_id == case.id,
            CasePlan.version == payload.plan_version,
        )
    )
    if not plan:
        raise HTTPException(status_code=404, detail="Plan version not found")
    if (
        payload.expected_plan_sha256 != plan.plan_sha256
        or payload.expected_state_hash != plan.based_on_state_hash
        or plan.based_on_state_hash != case.current_state_hash
    ):
        raise HTTPException(status_code=409, detail="Plan approval binding is stale")
    approval = await session.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.plan_id == plan.id,
            ApprovalRequest.approval_type == "PLAN_APPROVAL",
        )
    )
    if (
        not approval
        or approval.status != ApprovalStatus.APPROVED.value
        or _as_utc(approval.expires_at) <= utcnow()
        or approval.plan_sha256 != plan.plan_sha256
        or approval.bound_state_hash != case.current_state_hash
    ):
        raise HTTPException(status_code=409, detail="Current plan has no valid approval")
    await _validate_release_bindings(session, plan)
    template = await session.get(WorkflowTemplateVersion, plan.workflow_template_version_id)
    if not template:
        raise HTTPException(status_code=409, detail="Workflow template binding is unavailable")
    steps = list(
        (
            await session.scalars(
                select(CasePlanStep)
                .where(CasePlanStep.plan_id == plan.id)
                .order_by(CasePlanStep.position)
            )
        ).all()
    )
    run = CaseRun(
        case_id=case.id,
        plan_id=plan.id,
        plan_version=plan.version,
        plan_sha256=plan.plan_sha256,
        bound_state_hash=plan.based_on_state_hash,
        status=AgentRunStatus.PENDING.value,
        requested_by=principal.subject,
        idempotency_key=stored_key,
        checkpoint={},
    )
    session.add(run)
    await session.flush()
    run.checkpoint = initial_checkpoint(run=run, plan=plan, template=template, steps=steps)
    case.status = AgentCaseStatus.RUNNING.value
    await append_run_event(
        session,
        run=run,
        event_type="RUN_STARTED",
        actor=principal,
        request_id=request.state.request_id,
        idempotency_key=f"run-started:{stored_key}",
        payload={
            "request_fingerprint": fingerprint,
            "plan_id": plan.id,
            "plan_version": plan.version,
            "plan_sha256": plan.plan_sha256,
            "bound_state_hash": plan.based_on_state_hash,
            "workflow_template_version_id": template.id,
            "workflow_template_sha256": template.manifest_sha256,
        },
    )
    await _append_event(
        session,
        case=case,
        event_type="RUN_STARTED",
        principal=principal,
        request_id=request.state.request_id,
        idempotency_key=_event_key("run-started", principal, idempotency_key),
        payload={
            "run_id": run.id,
            "plan_id": plan.id,
            "plan_version": plan.version,
            "plan_sha256": plan.plan_sha256,
        },
    )
    await queue_run_advance(session, run, reason="run-started")
    add_audit_event(
        session,
        principal=principal,
        request_id=request.state.request_id,
        operation="case.run.start",
        object_type="case_run",
        object_id=run.id,
        application_version=settings.app_version,
        after={"case_id": case.id, "status": run.status, "plan_sha256": run.plan_sha256},
    )
    await session.commit()
    await best_effort_start_or_wake(settings, run.id)
    return await _run_response(session, run)


@router.get("/runs/{run_id}", response_model=CaseRunResponse)
async def get_case_run(
    run_id: UUID,
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(session_dependency),
) -> CaseRunResponse:
    run, _case = await _run_for_read(session, run_id, principal)
    return await _run_response(session, run)


async def _control_run(
    *,
    operation: str,
    run_id: UUID,
    payload: RunControlRequest,
    request: Request,
    idempotency_key: str,
    principal: Principal,
    settings: Settings,
    session: AsyncSession,
) -> CaseRunResponse:
    fingerprint = _request_fingerprint(payload.model_dump(mode="json"))
    event_key = f"control:{operation}:{_scoped_idempotency_key(principal, idempotency_key)}"
    replay = await session.scalar(
        select(RunEvent).where(
            RunEvent.run_id == str(run_id), RunEvent.idempotency_key == event_key
        )
    )
    if replay:
        if replay.payload.get("request_fingerprint") != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency key payload conflict")
        replay_run, replay_case = await _run_for_read(session, run_id, principal)
        _require_case_write(replay_case, principal)
        return await _run_response(session, replay_run)

    run, case = await _run_for_read(session, run_id, principal, lock=True)
    _require_case_write(case, principal)
    checkpoint = dict(run.checkpoint or {})
    control = dict(checkpoint.get("control") or {})
    before = run.status
    now = utcnow()
    if operation == "pause":
        if run.status not in {
            AgentRunStatus.PENDING.value,
            AgentRunStatus.RUNNING.value,
            AgentRunStatus.WAITING_FOR_APPROVAL.value,
        }:
            raise HTTPException(status_code=409, detail="Run cannot be paused from this state")
        control.update({"pause_requested": True, "resume_status": run.status})
        run.status = AgentRunStatus.PAUSED.value
        case.status = AgentCaseStatus.WAITING_FOR_INPUT.value
        event_type = "RUN_PAUSED"
    elif operation == "resume":
        if run.status != AgentRunStatus.PAUSED.value:
            raise HTTPException(status_code=409, detail="Only a paused run may resume")
        plan = await session.get(CasePlan, run.plan_id)
        if not plan or case.current_state_hash != run.bound_state_hash:
            raise HTTPException(status_code=409, detail="Run binding is stale and cannot resume")
        await _validate_release_bindings(session, plan)
        control.update({"pause_requested": False, "resume_status": None})
        active_step = (checkpoint.get("steps") or {}).get(checkpoint.get("step_key")) or {}
        active_status = active_step.get("status")
        if active_status == AgentInvocationStatus.WAITING_FOR_APPROVAL.value:
            run.status = AgentRunStatus.WAITING_FOR_APPROVAL.value
            case.status = AgentCaseStatus.WAITING_FOR_REVIEW.value
        elif active_status == AgentInvocationStatus.RUNNING.value:
            run.status = AgentRunStatus.RUNNING.value
            case.status = AgentCaseStatus.RUNNING.value
        else:
            run.status = AgentRunStatus.PENDING.value
            case.status = AgentCaseStatus.RUNNING.value
        event_type = "RUN_RESUMED"
    elif operation == "cancel":
        if run.status in TERMINAL_RUN_STATUSES:
            raise HTTPException(status_code=409, detail="Terminal run cannot be cancelled")
        control.update({"cancel_requested": True, "pause_requested": False})
        run.status = AgentRunStatus.CANCELLED.value
        run.completed_at = now
        case.status = AgentCaseStatus.CANCELLED.value
        active_invocations = list(
            (
                await session.scalars(
                    select(AgentInvocation).where(
                        AgentInvocation.run_id == run.id,
                        AgentInvocation.status.in_(
                            [
                                AgentInvocationStatus.PENDING.value,
                                AgentInvocationStatus.RUNNING.value,
                                AgentInvocationStatus.WAITING_FOR_APPROVAL.value,
                            ]
                        ),
                    )
                )
            ).all()
        )
        for invocation in active_invocations:
            invocation.status = AgentInvocationStatus.CANCELLED.value
            invocation.completed_at = now
        pending_approvals = list(
            (
                await session.scalars(
                    select(ApprovalRequest).where(
                        ApprovalRequest.run_id == run.id,
                        ApprovalRequest.status == ApprovalStatus.PENDING.value,
                    )
                )
            ).all()
        )
        for approval in pending_approvals:
            approval.status = ApprovalStatus.CANCELLED.value
        event_type = "RUN_CANCELLED"
    else:
        raise RuntimeError(f"Unsupported run control: {operation}")

    checkpoint["control"] = control
    checkpoint["checkpoint_version"] = int(checkpoint.get("checkpoint_version", 0)) + 1
    run.checkpoint = checkpoint
    await append_run_event(
        session,
        run=run,
        event_type=event_type,
        actor=principal,
        request_id=request.state.request_id,
        idempotency_key=event_key,
        payload={
            "request_fingerprint": fingerprint,
            "reason": payload.reason,
            "previous_status": before,
            "status": run.status,
        },
    )
    case_event_key = _event_key(f"run-{operation}", principal, idempotency_key)
    await _append_event(
        session,
        case=case,
        event_type=event_type,
        principal=principal,
        request_id=request.state.request_id,
        idempotency_key=case_event_key,
        payload={"run_id": run.id, "reason": payload.reason, "status": run.status},
    )
    if operation == "resume" and run.status == AgentRunStatus.PENDING.value:
        await queue_run_advance(session, run, reason="user-resumed")
    add_audit_event(
        session,
        principal=principal,
        request_id=request.state.request_id,
        operation=f"case.run.{operation}",
        object_type="case_run",
        object_id=run.id,
        application_version=settings.app_version,
        before={"status": before},
        after={"status": run.status, "reason_sha256": canonical_sha256(payload.reason)},
    )
    await session.commit()
    await best_effort_start_or_wake(settings, run.id)
    return await _run_response(session, run)


@router.post("/runs/{run_id}/pause", response_model=CaseRunResponse)
async def pause_case_run(
    run_id: UUID,
    payload: RunControlRequest,
    request: Request,
    idempotency_key: IdempotencyKey,
    principal: Principal = Depends(current_principal),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> CaseRunResponse:
    return await _control_run(
        operation="pause",
        run_id=run_id,
        payload=payload,
        request=request,
        idempotency_key=idempotency_key,
        principal=principal,
        settings=settings,
        session=session,
    )


@router.post("/runs/{run_id}/resume", response_model=CaseRunResponse)
async def resume_case_run(
    run_id: UUID,
    payload: RunControlRequest,
    request: Request,
    idempotency_key: IdempotencyKey,
    principal: Principal = Depends(current_principal),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> CaseRunResponse:
    return await _control_run(
        operation="resume",
        run_id=run_id,
        payload=payload,
        request=request,
        idempotency_key=idempotency_key,
        principal=principal,
        settings=settings,
        session=session,
    )


@router.post("/runs/{run_id}/cancel", response_model=CaseRunResponse)
async def cancel_case_run(
    run_id: UUID,
    payload: RunControlRequest,
    request: Request,
    idempotency_key: IdempotencyKey,
    principal: Principal = Depends(current_principal),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> CaseRunResponse:
    return await _control_run(
        operation="cancel",
        run_id=run_id,
        payload=payload,
        request=request,
        idempotency_key=idempotency_key,
        principal=principal,
        settings=settings,
        session=session,
    )


@router.post("/runs/{run_id}/steps/{step_key}/result", response_model=CaseRunResponse)
async def submit_step_result(
    run_id: UUID,
    step_key: str,
    payload: StepResultRequest,
    request: Request,
    idempotency_key: IdempotencyKey,
    principal: Principal = Depends(RUN_WORKERS),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> CaseRunResponse:
    fingerprint = _request_fingerprint(payload.model_dump(mode="json"))
    event_key = f"step-result:{_scoped_idempotency_key(principal, idempotency_key)}"
    replay = await session.scalar(
        select(RunEvent).where(
            RunEvent.run_id == str(run_id), RunEvent.idempotency_key == event_key
        )
    )
    if replay:
        if replay.payload.get("request_fingerprint") != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency key payload conflict")
        run, _case = await _run_for_read(session, run_id, principal)
        return await _run_response(session, run)
    run, case = await _run_for_read(session, run_id, principal, lock=True)
    invocation = await session.get(AgentInvocation, str(payload.expected_invocation_id))
    if not invocation or invocation.run_id != run.id or invocation.step_key != step_key:
        raise HTTPException(status_code=409, detail="Invocation binding does not match active step")
    usage = payload.usage.model_dump(mode="json")
    exceeded = await complete_step(
        session,
        run=run,
        invocation=invocation,
        output=payload.output,
        usage=usage,
        actor=principal,
        request_id=request.state.request_id,
        event_key=event_key,
        request_fingerprint=fingerprint,
    )
    add_audit_event(
        session,
        principal=principal,
        request_id=request.state.request_id,
        operation="case.run.step_result",
        object_type="agent_invocation",
        object_id=invocation.id,
        application_version=settings.app_version,
        after={
            "run_id": run.id,
            "step_key": step_key,
            "status": invocation.status,
            "output_sha256": invocation.output_sha256,
            "exceeded": exceeded,
        },
    )
    await session.commit()
    if exceeded:
        raise HTTPException(
            status_code=409,
            detail=f"Step result exceeded runtime limits: {', '.join(exceeded)}",
        )
    _require_case_read(case, principal)
    return await _run_response(session, run)


@router.post("/runs/{run_id}/steps/{step_key}/approval", response_model=CaseRunResponse)
async def decide_step_approval(
    run_id: UUID,
    step_key: str,
    payload: StepApprovalDecisionRequest,
    request: Request,
    idempotency_key: IdempotencyKey,
    principal: Principal = Depends(RUN_APPROVERS),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> CaseRunResponse:
    fingerprint = _request_fingerprint(payload.model_dump(mode="json"))
    event_key = f"step-approval:{_scoped_idempotency_key(principal, idempotency_key)}"
    replay = await session.scalar(
        select(RunEvent).where(
            RunEvent.run_id == str(run_id), RunEvent.idempotency_key == event_key
        )
    )
    if replay:
        if replay.payload.get("request_fingerprint") != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency key payload conflict")
        run, _case = await _run_for_read(session, run_id, principal)
        return await _run_response(session, run)
    run, case = await _run_for_read(session, run_id, principal, lock=True)
    if run.status != AgentRunStatus.WAITING_FOR_APPROVAL.value:
        raise HTTPException(status_code=409, detail="Run is not waiting for step approval")
    approval = await session.get(ApprovalRequest, str(payload.expected_approval_id))
    if (
        not approval
        or approval.run_id != run.id
        or approval.step_key != step_key
        or approval.approval_type != "STEP_APPROVAL"
    ):
        raise HTTPException(status_code=409, detail="Step approval binding is invalid")
    if principal.subject in {case.owner_subject, run.requested_by, approval.requested_by}:
        raise HTTPException(
            status_code=403,
            detail="Step approval requires an independent reviewer",
        )
    if approval.assigned_reviewer_id and approval.assigned_reviewer_id != principal.subject:
        raise HTTPException(status_code=403, detail="Step approval is assigned to another reviewer")
    if approval.status != ApprovalStatus.PENDING.value:
        raise HTTPException(status_code=409, detail="Step approval is already closed")
    if _as_utc(approval.expires_at) <= utcnow():
        approval.status = ApprovalStatus.EXPIRED.value
        run.status = AgentRunStatus.BLOCKED.value
        run.error_code = "STEP_APPROVAL_EXPIRED"
        case.status = AgentCaseStatus.BLOCKED.value
        await session.commit()
        raise HTTPException(status_code=409, detail="Step approval has expired")
    invocation = await session.scalar(
        select(AgentInvocation).where(
            AgentInvocation.run_id == run.id,
            AgentInvocation.step_key == step_key,
            AgentInvocation.status == AgentInvocationStatus.WAITING_FOR_APPROVAL.value,
        )
    )
    if not invocation:
        raise HTTPException(status_code=409, detail="Step invocation is unavailable")
    approval.status = (
        ApprovalStatus.APPROVED.value
        if payload.decision == "approve"
        else ApprovalStatus.REJECTED.value
    )
    approval.decision_by = principal.subject
    approval.decision_reason = payload.reason
    approval.decided_at = utcnow()
    checkpoint = dict(run.checkpoint or {})
    step_state = dict((checkpoint.get("steps") or {})[step_key])
    if payload.decision == "approve":
        invocation.status = AgentInvocationStatus.RUNNING.value
        invocation.started_at = utcnow()
        run.status = AgentRunStatus.RUNNING.value
        case.status = AgentCaseStatus.RUNNING.value
        step_state["status"] = AgentInvocationStatus.RUNNING.value
    else:
        invocation.status = AgentInvocationStatus.BLOCKED.value
        invocation.error_code = "STEP_APPROVAL_REJECTED"
        invocation.completed_at = utcnow()
        run.status = AgentRunStatus.BLOCKED.value
        run.error_code = invocation.error_code
        run.completed_at = utcnow()
        case.status = AgentCaseStatus.BLOCKED.value
        step_state["status"] = AgentInvocationStatus.BLOCKED.value
    steps = dict(checkpoint["steps"])
    steps[step_key] = step_state
    checkpoint["steps"] = steps
    checkpoint["checkpoint_version"] = int(checkpoint.get("checkpoint_version", 0)) + 1
    run.checkpoint = checkpoint
    await append_run_event(
        session,
        run=run,
        event_type="APPROVAL_DECIDED",
        actor=principal,
        request_id=request.state.request_id,
        idempotency_key=event_key,
        payload={
            "request_fingerprint": fingerprint,
            "approval_id": approval.id,
            "step_key": step_key,
            "decision": payload.decision,
            "reason": payload.reason,
            "invocation_id": invocation.id,
        },
    )
    add_audit_event(
        session,
        principal=principal,
        request_id=request.state.request_id,
        operation="case.run.step_approval",
        object_type="approval_request",
        object_id=approval.id,
        application_version=settings.app_version,
        after={"decision": payload.decision, "run_id": run.id, "step_key": step_key},
    )
    await session.commit()
    return await _run_response(session, run)


@router.get("/runs/{run_id}/events")
async def list_run_events(
    run_id: UUID,
    request: Request,
    cursor: str | None = Query(default=None, max_length=2_048),
    limit: int = Query(default=100, ge=1, le=500),
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(session_dependency),
):
    await _run_for_read(session, run_id, principal)
    try:
        offset = decode_cursor(cursor)
    except InvalidCursor as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    rows = list(
        (
            await session.scalars(
                select(RunEvent)
                .where(RunEvent.run_id == str(run_id))
                .order_by(RunEvent.sequence)
                .offset(offset)
                .limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    items = [_run_event_response(event) for event in rows[:limit]]
    if "application/x-ndjson" in request.headers.get("accept", ""):
        lines = [item.model_dump_json() + "\n" for item in items]
        return StreamingResponse(iter(lines), media_type="application/x-ndjson")
    return RunEventPage(
        items=items,
        next_cursor=encode_cursor(offset + limit) if has_more else None,
        has_more=has_more,
    )
