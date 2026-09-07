from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Any, cast

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_platform.controls import active_suspension
from app.agent_platform.runtime.graph import RunGraphState, evaluate_run_state
from app.agent_platform.runtime.validation import (
    validate_completion_binding,
    validate_completion_payload,
)
from app.cases.hashing import canonical_sha256
from app.models import (
    AgentCaseStatus,
    AgentInvocation,
    AgentInvocationStatus,
    AgentRunStatus,
    ApprovalRequest,
    ApprovalStatus,
    Case,
    CasePlan,
    CasePlanStep,
    CaseRun,
    CaseSource,
    JobStatus,
    ProcessingJob,
    RunEvent,
    WorkflowTemplateVersion,
    utcnow,
)
from app.security.auth import Principal

RUN_STATE_SCHEMA_VERSION = "pharmaagent-run-state@1.0.0"
ACTIVE_RUN_STATUSES = frozenset(
    {
        AgentRunStatus.PENDING.value,
        AgentRunStatus.RUNNING.value,
        AgentRunStatus.PAUSED.value,
        AgentRunStatus.WAITING_FOR_APPROVAL.value,
    }
)
TERMINAL_RUN_STATUSES = frozenset(
    {
        AgentRunStatus.COMPLETED.value,
        AgentRunStatus.BLOCKED.value,
        AgentRunStatus.FAILED.value,
        AgentRunStatus.CANCELLED.value,
    }
)
_ZERO_USAGE: dict[str, int | float] = {
    "turns": 0,
    "tool_calls": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "runtime_seconds": 0.0,
    "cost_usd": 0.0,
}


def _run_event_sha256(
    *,
    run: CaseRun,
    sequence: int,
    event_type: str,
    actor: Principal,
    request_id: str,
    idempotency_key: str,
    payload: dict[str, Any],
    previous_event_hash: str | None,
) -> str:
    return canonical_sha256(
        {
            "schema_version": "run-event-v1",
            "run_id": run.id,
            "case_id": run.case_id,
            "sequence": sequence,
            "event_type": event_type,
            "actor": {"type": actor.actor_type, "id": actor.subject},
            "request_id": request_id,
            "idempotency_key": idempotency_key,
            "payload": payload,
            "previous_event_hash": previous_event_hash,
            "plan_sha256": run.plan_sha256,
            "bound_state_hash": run.bound_state_hash,
        }
    )


async def append_run_event(
    session: AsyncSession,
    *,
    run: CaseRun,
    event_type: str,
    actor: Principal,
    request_id: str,
    idempotency_key: str,
    payload: dict[str, Any],
) -> RunEvent:
    existing = await session.scalar(
        select(RunEvent).where(
            RunEvent.run_id == run.id,
            RunEvent.idempotency_key == idempotency_key,
        )
    )
    if existing:
        return existing
    previous = await session.scalar(
        select(RunEvent)
        .where(RunEvent.run_id == run.id)
        .order_by(RunEvent.sequence.desc())
        .limit(1)
        .with_for_update()
    )
    sequence = (previous.sequence if previous else 0) + 1
    previous_hash = previous.event_hash if previous else None
    event = RunEvent(
        run_id=run.id,
        case_id=run.case_id,
        sequence=sequence,
        event_type=event_type,
        actor_type=actor.actor_type,
        actor_id=actor.subject,
        request_id=request_id,
        idempotency_key=idempotency_key,
        payload=payload,
        previous_event_hash=previous_hash,
        event_hash=_run_event_sha256(
            run=run,
            sequence=sequence,
            event_type=event_type,
            actor=actor,
            request_id=request_id,
            idempotency_key=idempotency_key,
            payload=payload,
            previous_event_hash=previous_hash,
        ),
        occurred_at=utcnow(),
    )
    session.add(event)
    await session.flush()
    return event


def initial_checkpoint(
    *,
    run: CaseRun,
    plan: CasePlan,
    template: WorkflowTemplateVersion,
    steps: list[CasePlanStep],
) -> dict[str, Any]:
    definitions = [
        {
            "id": step.id,
            "position": step.position,
            "step_key": step.step_key,
            "title": step.title,
            "depends_on": list(step.depends_on or []),
            "agent_version_id": step.agent_version_id,
            "skill_version_ids": list(step.skill_version_ids or []),
            "tool_version_ids": list(step.tool_version_ids or []),
            "output_schema_ref": step.output_schema_ref,
            "risk_level": step.risk_level,
            "requires_approval": step.requires_approval,
            "limits": dict(step.limits or {}),
        }
        for step in steps
    ]
    return {
        "schema_version": RUN_STATE_SCHEMA_VERSION,
        "checkpoint_version": 1,
        "run_id": run.id,
        "case_id": run.case_id,
        "plan_id": plan.id,
        "plan_version": plan.version,
        "plan_sha256": plan.plan_sha256,
        "bound_state_hash": plan.based_on_state_hash,
        "workflow_template": {
            "id": template.id,
            "workflow_key": template.workflow_key,
            "version": template.version,
            "manifest_sha256": template.manifest_sha256,
        },
        "step_definitions": definitions,
        "steps": {
            step.step_key: {
                "status": AgentInvocationStatus.PENDING.value,
                "attempt": 0,
                "invocation_id": None,
                "approval_id": None,
                "output_sha256": None,
                "usage": dict(_ZERO_USAGE),
            }
            for step in steps
        },
        # Regulatory MCP deliberately reads this compatibility field and denies
        # every call if it is absent or does not match the approved plan step.
        "step_key": None,
        "control": {
            "pause_requested": False,
            "cancel_requested": False,
            "resume_status": None,
        },
        "budget": dict(_ZERO_USAGE),
        "directive": "HOLD",
    }


def _checkpoint(run: CaseRun) -> dict[str, Any]:
    value = dict(run.checkpoint or {})
    if value.get("schema_version") != RUN_STATE_SCHEMA_VERSION:
        raise RuntimeError("Run checkpoint schema is unsupported")
    if value.get("run_id") != run.id or value.get("case_id") != run.case_id:
        raise RuntimeError("Run checkpoint identity binding is invalid")
    if (
        value.get("plan_id") != run.plan_id
        or value.get("plan_sha256") != run.plan_sha256
        or value.get("bound_state_hash") != run.bound_state_hash
    ):
        raise RuntimeError("Run checkpoint plan binding is invalid")
    return value


def _bump_checkpoint(checkpoint: dict[str, Any]) -> dict[str, Any]:
    checkpoint["checkpoint_version"] = int(checkpoint.get("checkpoint_version", 0)) + 1
    return checkpoint


async def queue_run_advance(session: AsyncSession, run: CaseRun, *, reason: str) -> ProcessingJob:
    checkpoint = _checkpoint(run)
    version = int(checkpoint["checkpoint_version"])
    key = f"case-run:{run.id}:advance:{version}"
    existing = await session.scalar(
        select(ProcessingJob).where(ProcessingJob.idempotency_key == key)
    )
    if existing:
        return existing
    job = ProcessingJob(
        job_type="orchestrate_case_run",
        status=JobStatus.PENDING.value,
        idempotency_key=key,
        payload={
            "run_id": run.id,
            "case_id": run.case_id,
            "checkpoint_version": version,
            "reason": reason,
        },
        max_attempts=3,
        available_at=utcnow(),
    )
    session.add(job)
    await session.flush()
    return job


async def _input_packet(
    session: AsyncSession,
    *,
    run: CaseRun,
    case: Case,
    step: CasePlanStep,
    checkpoint: Mapping[str, Any],
) -> dict[str, Any]:
    sources = list(
        (
            await session.scalars(
                select(CaseSource)
                .where(CaseSource.case_id == run.case_id)
                .order_by(CaseSource.created_at, CaseSource.id)
            )
        ).all()
    )
    return {
        "schema_version": "agent-context-packet@1.0.0",
        "task": {
            "case_id": case.id,
            "run_id": run.id,
            "plan_id": run.plan_id,
            "step_key": step.step_key,
            "objective": case.objective,
            "instructions": step.instructions,
        },
        "relevant_policies": [
            "decision-support-only",
            "pinned-evidence-only",
            "deny-unlisted-tools",
            "no-controlled-system-writes",
        ],
        "required_schema": step.output_schema_ref,
        "selected_skill_version_ids": list(step.skill_version_ids or []),
        "minimum_evidence": [
            {
                "case_source_id": source.id,
                "document_version_id": source.document_version_id,
                "source_sha256": source.source_sha256,
                "source_role": source.source_role,
            }
            for source in sources
        ],
        "allowed_tool_version_ids": list(step.tool_version_ids or []),
        "remaining_budget": dict(step.limits or {}),
        "upstream_results": {
            key: value.get("output_sha256")
            for key, value in (checkpoint.get("steps") or {}).items()
            if isinstance(value, Mapping) and value.get("status") == "COMPLETED"
        },
    }


async def _dispatch_step(
    session: AsyncSession,
    *,
    run: CaseRun,
    case: Case,
    plan: CasePlan,
    step: CasePlanStep,
    checkpoint: dict[str, Any],
    request_approval: bool,
    actor: Principal,
    request_id: str,
) -> None:
    workflow = dict(checkpoint.get("workflow_template") or {})
    template = await session.get(WorkflowTemplateVersion, str(workflow.get("id", "")))
    if not template or template.manifest_sha256 != workflow.get("manifest_sha256"):
        raise RuntimeError("Run workflow-template binding is unavailable")
    invocation_count = int(
        await session.scalar(
            select(func.count())
            .select_from(AgentInvocation)
            .where(AgentInvocation.run_id == run.id)
        )
        or 0
    )
    workflow_limit = int(
        (((template.manifest or {}).get("spec") or {}).get("limits") or {}).get(
            "maximumAgentInvocations", 12
        )
    )
    if invocation_count >= workflow_limit:
        run.status = AgentRunStatus.BLOCKED.value
        run.error_code = "AGENT_INVOCATION_LIMIT_EXCEEDED"
        case.status = AgentCaseStatus.BLOCKED.value
        await append_run_event(
            session,
            run=run,
            event_type="LIMIT_EXCEEDED",
            actor=actor,
            request_id=request_id,
            idempotency_key=f"limit:invocations:{checkpoint['checkpoint_version']}",
            payload={"limit": workflow_limit, "resource": "agent_invocations"},
        )
        return

    state_for_step = dict((checkpoint.get("steps") or {})[step.step_key])
    attempt = int(state_for_step.get("attempt", 0)) + 1
    packet = await _input_packet(
        session,
        run=run,
        case=case,
        step=step,
        checkpoint=checkpoint,
    )
    invocation_status = (
        AgentInvocationStatus.WAITING_FOR_APPROVAL.value
        if request_approval
        else AgentInvocationStatus.RUNNING.value
    )
    invocation = AgentInvocation(
        run_id=run.id,
        case_id=run.case_id,
        plan_step_id=step.id,
        step_key=step.step_key,
        attempt=attempt,
        agent_version_id=step.agent_version_id,
        status=invocation_status,
        input_payload=packet,
        input_sha256=canonical_sha256(packet),
        output_schema_ref=step.output_schema_ref,
        limits=dict(step.limits or {}),
        usage=dict(_ZERO_USAGE),
        started_at=None if request_approval else utcnow(),
    )
    session.add(invocation)
    await session.flush()

    approval: ApprovalRequest | None = None
    if request_approval:
        approval = ApprovalRequest(
            case_id=case.id,
            plan_id=plan.id,
            plan_version=plan.version,
            plan_sha256=plan.plan_sha256,
            bound_state_hash=plan.based_on_state_hash,
            run_id=run.id,
            plan_step_id=step.id,
            step_key=step.step_key,
            approval_type="STEP_APPROVAL",
            status=ApprovalStatus.PENDING.value,
            requested_by=run.requested_by,
            assigned_reviewer_id=None,
            idempotency_key=f"step-approval:{run.id}:{step.step_key}:{attempt}",
            expires_at=utcnow() + timedelta(days=7),
        )
        session.add(approval)
        await session.flush()

    state_for_step.update(
        {
            "status": invocation_status,
            "attempt": attempt,
            "invocation_id": invocation.id,
            "approval_id": approval.id if approval else None,
            "output_sha256": None,
            "usage": dict(_ZERO_USAGE),
        }
    )
    steps = dict(checkpoint["steps"])
    steps[step.step_key] = state_for_step
    checkpoint["steps"] = steps
    checkpoint["step_key"] = step.step_key
    _bump_checkpoint(checkpoint)
    run.checkpoint = checkpoint
    run.started_at = run.started_at or utcnow()
    run.status = (
        AgentRunStatus.WAITING_FOR_APPROVAL.value
        if request_approval
        else AgentRunStatus.RUNNING.value
    )
    case.status = (
        AgentCaseStatus.WAITING_FOR_REVIEW.value
        if request_approval
        else AgentCaseStatus.RUNNING.value
    )
    event_type = "APPROVAL_REQUESTED" if request_approval else "AGENT_STARTED"
    await append_run_event(
        session,
        run=run,
        event_type=event_type,
        actor=actor,
        request_id=request_id,
        idempotency_key=f"dispatch:{step.step_key}:{attempt}",
        payload={
            "step_key": step.step_key,
            "invocation_id": invocation.id,
            "approval_id": approval.id if approval else None,
            "agent_version_id": invocation.agent_version_id,
            "input_sha256": invocation.input_sha256,
            "output_schema_ref": invocation.output_schema_ref,
            "limits": invocation.limits,
        },
    )


async def advance_case_run(
    session: AsyncSession,
    *,
    run_id: str,
    request_id: str,
    actor: Principal,
) -> dict[str, int]:
    run = await session.scalar(select(CaseRun).where(CaseRun.id == run_id).with_for_update())
    if not run:
        raise RuntimeError("Case run does not exist")
    if run.status in TERMINAL_RUN_STATUSES or run.status == AgentRunStatus.PAUSED.value:
        return {"runs_advanced": 0}
    case = await session.scalar(select(Case).where(Case.id == run.case_id).with_for_update())
    plan = await session.get(CasePlan, run.plan_id)
    if not case or not plan:
        raise RuntimeError("Case run binding is unavailable")
    checkpoint = _checkpoint(run)
    suspension = await active_suspension(session)
    if suspension:
        run.status = AgentRunStatus.PAUSED.value
        run.error_code = "GLOBAL_KILL_SWITCH"
        case.status = AgentCaseStatus.WAITING_FOR_INPUT.value
        await append_run_event(
            session,
            run=run,
            event_type="RUN_SUSPENDED",
            actor=actor,
            request_id=request_id,
            idempotency_key=f"suspended:global:{checkpoint['checkpoint_version']}",
            payload={
                "error_code": run.error_code,
                "control_key": suspension.control_key,
                "reason_sha256": canonical_sha256(suspension.reason),
            },
        )
        return {"runs_advanced": 1, "runs_paused": 1}
    if case.current_state_hash != run.bound_state_hash:
        run.status = AgentRunStatus.BLOCKED.value
        run.error_code = "STALE_CASE_STATE"
        case.status = AgentCaseStatus.STALE.value
        await append_run_event(
            session,
            run=run,
            event_type="RUN_BLOCKED",
            actor=actor,
            request_id=request_id,
            idempotency_key=f"blocked:stale:{checkpoint['checkpoint_version']}",
            payload={"error_code": run.error_code},
        )
        return {"runs_advanced": 1, "runs_blocked": 1}

    evaluated = cast(RunGraphState, evaluate_run_state(cast(RunGraphState, checkpoint)))
    directive = evaluated["directive"]
    step_key = evaluated.get("step_key")
    checkpoint.update(evaluated)
    if directive == "HOLD":
        return {"runs_advanced": 0}
    if directive == "PAUSE":
        run.status = AgentRunStatus.PAUSED.value
        return {"runs_advanced": 1}
    if directive == "CANCEL":
        run.status = AgentRunStatus.CANCELLED.value
        run.completed_at = utcnow()
        case.status = AgentCaseStatus.CANCELLED.value
        return {"runs_advanced": 1}
    if directive == "COMPLETE":
        checkpoint["step_key"] = None
        _bump_checkpoint(checkpoint)
        run.checkpoint = checkpoint
        run.status = AgentRunStatus.COMPLETED.value
        run.completed_at = utcnow()
        case.status = AgentCaseStatus.COMPLETED.value
        await append_run_event(
            session,
            run=run,
            event_type="RUN_COMPLETED",
            actor=actor,
            request_id=request_id,
            idempotency_key=f"completed:{checkpoint['checkpoint_version']}",
            payload={"budget": checkpoint.get("budget") or {}},
        )
        return {"runs_advanced": 1, "runs_completed": 1}
    if directive == "BLOCK" or not step_key:
        run.status = AgentRunStatus.BLOCKED.value
        run.error_code = "PLAN_GRAPH_BLOCKED"
        case.status = AgentCaseStatus.BLOCKED.value
        await append_run_event(
            session,
            run=run,
            event_type="RUN_BLOCKED",
            actor=actor,
            request_id=request_id,
            idempotency_key=f"blocked:graph:{checkpoint['checkpoint_version']}",
            payload={"error_code": run.error_code},
        )
        return {"runs_advanced": 1, "runs_blocked": 1}

    step = await session.scalar(
        select(CasePlanStep).where(
            CasePlanStep.plan_id == plan.id,
            CasePlanStep.step_key == step_key,
        )
    )
    if not step:
        raise RuntimeError("Selected plan step is unavailable")
    suspension = await active_suspension(
        session, [step.agent_version_id] if step.agent_version_id else []
    )
    if suspension:
        run.status = AgentRunStatus.PAUSED.value
        run.error_code = "AGENT_SUSPENDED"
        case.status = AgentCaseStatus.WAITING_FOR_INPUT.value
        await append_run_event(
            session,
            run=run,
            event_type="RUN_SUSPENDED",
            actor=actor,
            request_id=request_id,
            idempotency_key=f"suspended:{step.step_key}:{checkpoint['checkpoint_version']}",
            payload={
                "error_code": run.error_code,
                "control_key": suspension.control_key,
                "step_key": step.step_key,
                "reason_sha256": canonical_sha256(suspension.reason),
            },
        )
        return {"runs_advanced": 1, "runs_paused": 1}
    await _dispatch_step(
        session,
        run=run,
        case=case,
        plan=plan,
        step=step,
        checkpoint=checkpoint,
        request_approval=directive == "REQUEST_APPROVAL",
        actor=actor,
        request_id=request_id,
    )
    return {"runs_advanced": 1, "steps_dispatched": 1}


def _usage_limits_exceeded(
    usage: Mapping[str, int | float], limits: Mapping[str, Any]
) -> list[str]:
    mapping = {
        "turns": "max_turns",
        "tool_calls": "max_tool_calls",
        "input_tokens": "max_input_tokens",
        "output_tokens": "max_output_tokens",
        "runtime_seconds": "max_runtime_seconds",
        "cost_usd": "max_cost_usd",
    }
    return [
        usage_name
        for usage_name, limit_name in mapping.items()
        if float(usage.get(usage_name, 0)) > float(limits.get(limit_name, 0))
    ]


def _sum_usage(
    current: Mapping[str, int | float], added: Mapping[str, int | float]
) -> dict[str, int | float]:
    return {
        "turns": int(current.get("turns", 0)) + int(added.get("turns", 0)),
        "tool_calls": int(current.get("tool_calls", 0)) + int(added.get("tool_calls", 0)),
        "input_tokens": int(current.get("input_tokens", 0))
        + int(added.get("input_tokens", 0)),
        "output_tokens": int(current.get("output_tokens", 0))
        + int(added.get("output_tokens", 0)),
        "runtime_seconds": float(current.get("runtime_seconds", 0))
        + float(added.get("runtime_seconds", 0)),
        "cost_usd": float(current.get("cost_usd", 0)) + float(added.get("cost_usd", 0)),
    }


async def complete_step(
    session: AsyncSession,
    *,
    run: CaseRun,
    invocation: AgentInvocation,
    output: dict[str, object],
    usage: dict[str, int | float],
    actor: Principal,
    request_id: str,
    event_key: str,
    request_fingerprint: str,
) -> list[str]:
    # Serialize all completion callers, including internal workers. Refresh ORM
    # state so a long-lived executor cannot commit using a cached RUNNING state.
    current_run = await session.scalar(
        select(CaseRun).where(CaseRun.id == run.id).with_for_update()
        .execution_options(populate_existing=True)
    )
    current_invocation = await session.scalar(
        select(AgentInvocation).where(AgentInvocation.id == invocation.id).with_for_update()
        .execution_options(populate_existing=True)
    )
    if not current_run or not current_invocation:
        raise HTTPException(status_code=409, detail="Step completion binding is unavailable")
    run, invocation = current_run, current_invocation
    case = await session.scalar(
        select(Case).where(Case.id == run.case_id).with_for_update()
        .execution_options(populate_existing=True)
    )
    if not case:
        raise RuntimeError("Case run has no case")
    checkpoint = _checkpoint(run)
    if run.status != AgentRunStatus.RUNNING.value:
        raise HTTPException(status_code=409, detail="Run is not accepting a step result")
    if checkpoint.get("step_key") != invocation.step_key:
        raise HTTPException(status_code=409, detail="Invocation is not the active plan step")
    if invocation.status != AgentInvocationStatus.RUNNING.value:
        raise HTTPException(status_code=409, detail="Invocation is not running")

    await validate_completion_binding(session, run=run, case=case, invocation=invocation)
    usage = validate_completion_payload(invocation.output_schema_ref, output, usage)

    exceeded = _usage_limits_exceeded(usage, invocation.limits or {})
    workflow = await session.get(
        WorkflowTemplateVersion,
        str((checkpoint.get("workflow_template") or {}).get("id", "")),
    )
    if not workflow:
        raise RuntimeError("Workflow-template binding is unavailable")
    aggregate = _sum_usage(checkpoint.get("budget") or {}, usage)
    workflow_limits = ((workflow.manifest or {}).get("spec") or {}).get("limits") or {}
    aggregate_mapping = {
        "tool_calls": "maximumToolCalls",
        "runtime_seconds": "maximumRuntimeSeconds",
        "cost_usd": "maximumCostUsd",
    }
    exceeded.extend(
        f"workflow_{name}"
        for name, limit in aggregate_mapping.items()
        if float(aggregate[name]) > float(workflow_limits.get(limit, 0))
    )
    if exceeded:
        invocation.status = AgentInvocationStatus.BLOCKED.value
        invocation.usage = usage
        invocation.error_code = "RUNTIME_LIMIT_EXCEEDED"
        invocation.completed_at = utcnow()
        run.status = AgentRunStatus.BLOCKED.value
        run.error_code = invocation.error_code
        run.completed_at = utcnow()
        case.status = AgentCaseStatus.BLOCKED.value
        step_state = dict((checkpoint.get("steps") or {})[invocation.step_key])
        step_state.update({"status": "BLOCKED", "usage": usage})
        steps = dict(checkpoint["steps"])
        steps[invocation.step_key] = step_state
        checkpoint["steps"] = steps
        checkpoint["budget"] = aggregate
        _bump_checkpoint(checkpoint)
        run.checkpoint = checkpoint
        await append_run_event(
            session,
            run=run,
            event_type="LIMIT_EXCEEDED",
            actor=actor,
            request_id=request_id,
            idempotency_key=event_key,
            payload={
                "step_key": invocation.step_key,
                "invocation_id": invocation.id,
                "exceeded": sorted(set(exceeded)),
                "usage": usage,
                "limits": invocation.limits,
                "request_fingerprint": request_fingerprint,
            },
        )
        return sorted(set(exceeded))

    output_sha256 = canonical_sha256(output)
    invocation.status = AgentInvocationStatus.COMPLETED.value
    invocation.output_payload = output
    invocation.output_sha256 = output_sha256
    invocation.usage = usage
    invocation.completed_at = utcnow()
    step_state = dict((checkpoint.get("steps") or {})[invocation.step_key])
    step_state.update(
        {
            "status": "COMPLETED",
            "output_sha256": output_sha256,
            "usage": usage,
        }
    )
    steps = dict(checkpoint["steps"])
    steps[invocation.step_key] = step_state
    checkpoint["steps"] = steps
    checkpoint["budget"] = aggregate
    checkpoint["step_key"] = None
    checkpoint["directive"] = "HOLD"
    _bump_checkpoint(checkpoint)
    run.checkpoint = checkpoint
    await append_run_event(
        session,
        run=run,
        event_type="AGENT_COMPLETED",
        actor=actor,
        request_id=request_id,
        idempotency_key=event_key,
        payload={
            "step_key": invocation.step_key,
            "invocation_id": invocation.id,
            "output_sha256": output_sha256,
            "output_schema_ref": invocation.output_schema_ref,
            "usage": usage,
            "request_fingerprint": request_fingerprint,
        },
    )
    await queue_run_advance(session, run, reason="step-completed")
    return []
