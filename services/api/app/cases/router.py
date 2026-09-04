from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_platform.registry.workflows import approved_workflow_template
from app.audit import add_audit_event
from app.config import Settings
from app.dependencies import session_dependency, settings_dependency
from app.enums import ScopeStatus
from app.models import (
    AgentCaseStatus,
    AgentVersion,
    ApprovalRequest,
    ApprovalStatus,
    Case,
    CaseEvent,
    CasePlan,
    CasePlanStep,
    CaseSource,
    Document,
    DocumentVersion,
    RegistryReleaseStatus,
    SkillVersion,
    ToolVersion,
    WarningLetter,
    utcnow,
)
from app.pagination import InvalidCursor, decode_cursor, encode_cursor
from app.security.auth import Principal, current_principal, require_roles

from .hashing import canonical_sha256, case_state_sha256, event_sha256
from .schemas import (
    ApprovalResponse,
    CaseCreateRequest,
    CaseEventPage,
    CaseEventResponse,
    CasePage,
    CasePlanCreateRequest,
    CasePlanResponse,
    CaseResponse,
    CaseSourceResponse,
    PlanDecisionRequest,
    PlanStepResponse,
    StepLimits,
)

router = APIRouter(prefix="/cases", tags=["Cases"])

IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=16,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]

CASE_CREATORS = require_roles("analyst", "system_owner")
PLAN_APPROVERS = require_roles("reviewer")
GLOBAL_CASE_READ_ROLES = frozenset({"reviewer", "domain_sme", "system_owner", "auditor"})
CASE_LIST_ROLES = GLOBAL_CASE_READ_ROLES | {"analyst"}
PROHIBITED_ACTIONS = [
    "MODIFY_CONTROLLED_DOCUMENT",
    "CREATE_CAPA",
    "APPROVE_CAPA",
    "UPDATE_QMS_RECORD",
    "UPDATE_EDMS_RECORD",
    "UPDATE_MES_RECORD",
    "UPDATE_LIMS_RECORD",
    "RELEASE_OR_REJECT_PRODUCT",
    "SUBMIT_TO_REGULATOR",
]


def _scoped_idempotency_key(principal: Principal, idempotency_key: str) -> str:
    """Keep client keys replayable without making them global cross-user identifiers."""

    digest = canonical_sha256({"subject": principal.subject, "idempotency_key": idempotency_key})
    return f"subject:{digest}"


def _event_key(operation: str, principal: Principal, idempotency_key: str) -> str:
    return f"{operation}:{_scoped_idempotency_key(principal, idempotency_key)}"


def _approval_key(case_id: str, principal: Principal, idempotency_key: str) -> str:
    digest = canonical_sha256(
        {"case_id": case_id, "subject": principal.subject, "key": idempotency_key}
    )
    return f"approval:{digest}"


def _request_fingerprint(value: object) -> str:
    return canonical_sha256(value)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _require_list_access(principal: Principal) -> None:
    if not principal.has_any(CASE_LIST_ROLES):
        raise HTTPException(status_code=403, detail="Case role is not authorized")


def _require_case_read(case: Case, principal: Principal) -> None:
    if case.owner_subject == principal.subject:
        return
    if principal.has_any(GLOBAL_CASE_READ_ROLES):
        return
    raise HTTPException(status_code=403, detail="Case is not available to this identity")


def _require_case_write(case: Case, principal: Principal) -> None:
    owner_analyst = case.owner_subject == principal.subject and "analyst" in principal.roles
    if owner_analyst or "system_owner" in principal.roles:
        return
    raise HTTPException(status_code=403, detail="Only the case owner may change this case")


async def _case_for_read(
    session: AsyncSession,
    case_id: UUID,
    principal: Principal,
    *,
    lock: bool = False,
) -> Case:
    query = select(Case).where(Case.id == str(case_id))
    if lock:
        query = query.with_for_update()
    case = await session.scalar(query)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    _require_case_read(case, principal)
    return case


async def _append_event(
    session: AsyncSession,
    *,
    case: Case,
    event_type: str,
    principal: Principal,
    request_id: str,
    idempotency_key: str,
    payload: dict[str, Any],
) -> CaseEvent:
    previous = await session.scalar(
        select(CaseEvent)
        .where(CaseEvent.case_id == case.id)
        .order_by(CaseEvent.sequence.desc())
        .limit(1)
        .with_for_update()
    )
    sequence = (previous.sequence if previous else 0) + 1
    previous_hash = previous.event_hash if previous else None
    digest = event_sha256(
        case_id=case.id,
        sequence=sequence,
        event_type=event_type,
        actor_type=principal.actor_type,
        actor_id=principal.subject,
        request_id=request_id,
        idempotency_key=idempotency_key,
        payload=payload,
        previous_event_hash=previous_hash,
        state_hash=case.current_state_hash,
    )
    event = CaseEvent(
        case_id=case.id,
        sequence=sequence,
        event_type=event_type,
        actor_type=principal.actor_type,
        actor_id=principal.subject,
        request_id=request_id,
        idempotency_key=idempotency_key,
        payload=payload,
        previous_event_hash=previous_hash,
        event_hash=digest,
        state_hash=case.current_state_hash,
        occurred_at=utcnow(),
    )
    session.add(event)
    # The session disables autoflush; the next append must be able to see this row.
    await session.flush()
    return event


def _source_response(
    source: CaseSource,
    version: DocumentVersion,
    document: Document,
) -> CaseSourceResponse:
    return CaseSourceResponse(
        id=source.id,
        case_id=source.case_id,
        warning_letter_id=document.warning_letter_id,
        document_id=document.id,
        document_version_id=version.id,
        document_version_number=version.version_number,
        source_role=source.source_role,
        source_sha256=source.source_sha256,
        source_url=document.canonical_url,
        pinned_by=source.pinned_by,
        created_at=source.created_at,
    )


async def _case_response(session: AsyncSession, case: Case) -> CaseResponse:
    rows = (
        await session.execute(
            select(CaseSource, DocumentVersion, Document)
            .join(DocumentVersion, DocumentVersion.id == CaseSource.document_version_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(CaseSource.case_id == case.id)
            .order_by(CaseSource.created_at, CaseSource.id)
        )
    ).all()
    return CaseResponse(
        id=case.id,
        title=case.title,
        objective=case.objective,
        status=case.status,
        owner_subject=case.owner_subject,
        workflow_key=case.workflow_key,
        current_state_hash=case.current_state_hash,
        sources=[_source_response(source, version, document) for source, version, document in rows],
        created_at=case.created_at,
        updated_at=case.updated_at,
    )


def _step_response(step: CasePlanStep) -> PlanStepResponse:
    return PlanStepResponse(
        id=step.id,
        position=step.position,
        step_key=step.step_key,
        title=step.title,
        instructions=step.instructions,
        depends_on=list(step.depends_on or []),
        agent_version_id=step.agent_version_id,
        skill_version_ids=list(step.skill_version_ids or []),
        tool_version_ids=list(step.tool_version_ids or []),
        output_schema_ref=step.output_schema_ref,
        risk_level=step.risk_level,
        requires_approval=step.requires_approval,
        limits=StepLimits.model_validate(step.limits or {}),
        created_at=step.created_at,
    )


def _approval_response(approval: ApprovalRequest) -> ApprovalResponse:
    return ApprovalResponse(
        id=approval.id,
        approval_type=approval.approval_type,
        status=approval.status,
        requested_by=approval.requested_by,
        assigned_reviewer_id=approval.assigned_reviewer_id,
        decision_by=approval.decision_by,
        decision_reason=approval.decision_reason,
        decided_at=approval.decided_at,
        expires_at=approval.expires_at,
        plan_sha256=approval.plan_sha256,
        bound_state_hash=approval.bound_state_hash,
        created_at=approval.created_at,
    )


async def _plan_response(session: AsyncSession, plan: CasePlan) -> CasePlanResponse:
    steps = list(
        (
            await session.scalars(
                select(CasePlanStep)
                .where(CasePlanStep.plan_id == plan.id)
                .order_by(CasePlanStep.position)
            )
        ).all()
    )
    approval = await session.scalar(
        select(ApprovalRequest)
        .where(
            ApprovalRequest.plan_id == plan.id,
            ApprovalRequest.approval_type == "PLAN_APPROVAL",
        )
        .limit(1)
    )
    if not approval:
        raise RuntimeError(f"Plan {plan.id} has no approval binding")
    definition = plan.plan_definition or {}
    return CasePlanResponse(
        id=plan.id,
        case_id=plan.case_id,
        version=plan.version,
        objective=plan.objective,
        plan_schema_version=plan.plan_schema_version,
        plan_sha256=plan.plan_sha256,
        based_on_state_hash=plan.based_on_state_hash,
        workflow_template_version_id=plan.workflow_template_version_id,
        prohibited_actions=list(definition.get("prohibited_actions") or []),
        created_by=plan.created_by,
        created_at=plan.created_at,
        steps=[_step_response(step) for step in steps],
        approval=_approval_response(approval),
    )


def _event_response(event: CaseEvent) -> CaseEventResponse:
    return CaseEventResponse(
        id=event.id,
        case_id=event.case_id,
        sequence=event.sequence,
        event_type=event.event_type,
        actor_type=event.actor_type,
        actor_id=event.actor_id,
        request_id=event.request_id,
        payload=dict(event.payload or {}),
        previous_event_hash=event.previous_event_hash,
        event_hash=event.event_hash,
        state_hash=event.state_hash,
        occurred_at=event.occurred_at,
    )


async def _pinned_drug_version(
    session: AsyncSession,
    *,
    warning_letter_id: UUID,
    document_version_id: UUID,
) -> tuple[WarningLetter, Document, DocumentVersion]:
    row = (
        await session.execute(
            select(WarningLetter, Document, DocumentVersion)
            .join(Document, Document.warning_letter_id == WarningLetter.id)
            .join(DocumentVersion, DocumentVersion.document_id == Document.id)
            .where(
                WarningLetter.id == str(warning_letter_id),
                WarningLetter.current_in_scope.is_(True),
                WarningLetter.scope_status == ScopeStatus.IN_SCOPE_DRUGS.value,
                DocumentVersion.id == str(document_version_id),
                DocumentVersion.scope_status == ScopeStatus.IN_SCOPE_DRUGS.value,
            )
        )
    ).one_or_none()
    if not row:
        # Do not disclose whether the letter, version, relationship, or scope check failed.
        raise HTTPException(status_code=404, detail="In-scope Drug source version not found")
    letter, document, version = row
    if len(version.canonical_hash) != 64 or any(
        character not in "0123456789abcdef" for character in version.canonical_hash
    ):
        raise HTTPException(status_code=409, detail="Source version has no valid canonical hash")
    return letter, document, version


async def _validate_registry_pins(
    session: AsyncSession,
    payload: CasePlanCreateRequest,
) -> None:
    agent_ids = {
        str(step.agent_version_id) for step in payload.steps if step.agent_version_id is not None
    }
    skill_ids = {str(item) for step in payload.steps for item in step.skill_version_ids}
    tool_ids = {str(item) for step in payload.steps for item in step.tool_version_ids}

    async def approved_ids(model: type[AgentVersion] | type[SkillVersion] | type[ToolVersion], ids):
        if not ids:
            return set()
        return set(
            await session.scalars(
                select(model.id).where(
                    model.id.in_(ids),
                    model.release_status.in_(
                        [
                            RegistryReleaseStatus.APPROVED.value,
                            RegistryReleaseStatus.PRODUCTION.value,
                        ]
                    ),
                )
            )
        )

    if await approved_ids(AgentVersion, agent_ids) != agent_ids:
        raise HTTPException(status_code=422, detail="Agent version is missing or not approved")
    if await approved_ids(SkillVersion, skill_ids) != skill_ids:
        raise HTTPException(status_code=422, detail="Skill version is missing or not approved")
    if await approved_ids(ToolVersion, tool_ids) != tool_ids:
        raise HTTPException(status_code=422, detail="Tool version is missing or not approved")


@router.post("", response_model=CaseResponse, status_code=201)
async def create_case(
    payload: CaseCreateRequest,
    request: Request,
    idempotency_key: IdempotencyKey,
    principal: Principal = Depends(CASE_CREATORS),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> CaseResponse:
    fingerprint = _request_fingerprint(payload.model_dump(mode="json"))
    stored_idempotency_key = _scoped_idempotency_key(principal, idempotency_key)
    existing = await session.scalar(
        select(Case).where(Case.idempotency_key == stored_idempotency_key)
    )
    if existing:
        prior_event = await session.scalar(
            select(CaseEvent).where(
                CaseEvent.case_id == existing.id,
                CaseEvent.idempotency_key == _event_key("case-created", principal, idempotency_key),
            )
        )
        if not prior_event or prior_event.payload.get("request_fingerprint") != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency key payload conflict")
        _require_case_read(existing, principal)
        return await _case_response(session, existing)

    _letter, document, version = await _pinned_drug_version(
        session,
        warning_letter_id=payload.warning_letter_id,
        document_version_id=payload.document_version_id,
    )
    initial_state_hash = case_state_sha256(
        objective=payload.objective,
        workflow_key=payload.workflow_key,
        source_pins=[],
    )
    case = Case(
        title=payload.title,
        objective=payload.objective,
        status=AgentCaseStatus.DRAFT.value,
        owner_subject=principal.subject,
        workflow_key=payload.workflow_key,
        current_state_hash=initial_state_hash,
        idempotency_key=stored_idempotency_key,
    )
    session.add(case)
    await session.flush()
    await _append_event(
        session,
        case=case,
        event_type="CASE_CREATED",
        principal=principal,
        request_id=request.state.request_id,
        idempotency_key=_event_key("case-created", principal, idempotency_key),
        payload={
            "request_fingerprint": fingerprint,
            "title": case.title,
            "objective": case.objective,
            "workflow_key": case.workflow_key,
        },
    )

    source = CaseSource(
        case_id=case.id,
        document_version_id=version.id,
        source_role=payload.source_role,
        source_sha256=version.canonical_hash,
        pinned_by=principal.subject,
    )
    session.add(source)
    await session.flush()
    case.current_state_hash = case_state_sha256(
        objective=case.objective,
        workflow_key=case.workflow_key,
        source_pins=[
            {
                "source_role": source.source_role,
                "document_version_id": source.document_version_id,
                "source_sha256": source.source_sha256,
            }
        ],
    )
    await session.flush()
    await _append_event(
        session,
        case=case,
        event_type="SOURCE_PINNED",
        principal=principal,
        request_id=request.state.request_id,
        idempotency_key=_event_key("source-pinned", principal, idempotency_key),
        payload={
            "case_source_id": source.id,
            "warning_letter_id": str(payload.warning_letter_id),
            "document_id": document.id,
            "document_version_id": version.id,
            "source_role": source.source_role,
            "source_sha256": source.source_sha256,
        },
    )
    add_audit_event(
        session,
        principal=principal,
        request_id=request.state.request_id,
        operation="case.create",
        object_type="case",
        object_id=case.id,
        application_version=settings.app_version,
        after={
            "status": case.status,
            "owner_subject": case.owner_subject,
            "workflow_key": case.workflow_key,
            "state_hash": case.current_state_hash,
            "source_version_id": source.document_version_id,
            "source_sha256": source.source_sha256,
        },
    )
    await session.commit()
    return await _case_response(session, case)


@router.get("", response_model=CasePage)
async def list_cases(
    cursor: str | None = Query(default=None, max_length=2_048),
    limit: int = Query(default=50, ge=1, le=100),
    case_status: AgentCaseStatus | None = Query(default=None, alias="status"),
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(session_dependency),
) -> CasePage:
    _require_list_access(principal)
    try:
        offset = decode_cursor(cursor)
    except InvalidCursor as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    query = select(Case)
    if not principal.has_any(GLOBAL_CASE_READ_ROLES):
        query = query.where(Case.owner_subject == principal.subject)
    if case_status is not None:
        query = query.where(Case.status == case_status.value)
    rows = list(
        (
            await session.scalars(
                query.order_by(Case.updated_at.desc(), Case.id).offset(offset).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    visible = rows[:limit]
    return CasePage(
        items=[await _case_response(session, case) for case in visible],
        next_cursor=encode_cursor(offset + limit) if has_more else None,
        has_more=has_more,
    )


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: UUID,
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(session_dependency),
) -> CaseResponse:
    case = await _case_for_read(session, case_id, principal)
    return await _case_response(session, case)


@router.post("/{case_id}/plans", response_model=CasePlanResponse, status_code=201)
async def create_case_plan(
    case_id: UUID,
    payload: CasePlanCreateRequest,
    request: Request,
    idempotency_key: IdempotencyKey,
    principal: Principal = Depends(current_principal),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> CasePlanResponse:
    fingerprint = _request_fingerprint(payload.model_dump(mode="json"))
    replay_event = await session.scalar(
        select(CaseEvent).where(
            CaseEvent.case_id == str(case_id),
            CaseEvent.idempotency_key == _event_key("plan-created", principal, idempotency_key),
        )
    )
    if replay_event:
        if replay_event.payload.get("request_fingerprint") != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency key payload conflict")
        replay_case = await _case_for_read(session, case_id, principal)
        _require_case_write(replay_case, principal)
        plan = await session.get(CasePlan, str(replay_event.payload.get("plan_id", "")))
        if not plan or plan.case_id != replay_case.id:
            raise HTTPException(status_code=409, detail="Idempotent plan result is unavailable")
        return await _plan_response(session, plan)

    case = await _case_for_read(session, case_id, principal, lock=True)
    _require_case_write(case, principal)
    if case.status not in {
        AgentCaseStatus.DRAFT.value,
        AgentCaseStatus.PLANNING.value,
        AgentCaseStatus.NEEDS_REVISION.value,
        AgentCaseStatus.READY.value,
    }:
        raise HTTPException(status_code=409, detail="Case is not accepting a new plan version")
    if payload.objective is not None and payload.objective != case.objective:
        raise HTTPException(
            status_code=409,
            detail="Plan objective must match the case planning-input objective",
        )
    if payload.assigned_reviewer_id in {principal.subject, case.owner_subject}:
        raise HTTPException(
            status_code=422,
            detail="Assigned reviewer must be independent from the case owner and plan creator",
        )
    await _validate_registry_pins(session, payload)
    workflow_template = await approved_workflow_template(session, case.workflow_key)
    if workflow_template is None:
        raise HTTPException(
            status_code=422,
            detail="Workflow template is missing, suspended, or not enabled for execution",
        )
    latest_version = await session.scalar(
        select(func.max(CasePlan.version)).where(CasePlan.case_id == case.id)
    )
    version_number = int(latest_version or 0) + 1
    objective = case.objective
    step_definitions = [step.model_dump(mode="json") for step in payload.steps]
    plan_definition = {
        "schema_version": payload.plan_schema_version,
        "objective": objective,
        "workflow_template": {
            "id": workflow_template.id,
            "workflow_key": workflow_template.workflow_key,
            "version": workflow_template.version,
            "manifest_sha256": workflow_template.manifest_sha256,
        },
        "steps": step_definitions,
        "prohibited_actions": PROHIBITED_ACTIONS,
    }
    plan_hash = canonical_sha256(
        {
            "case_id": case.id,
            "version": version_number,
            "based_on_state_hash": case.current_state_hash,
            "definition": plan_definition,
        }
    )
    plan = CasePlan(
        case_id=case.id,
        version=version_number,
        objective=objective,
        plan_schema_version=payload.plan_schema_version,
        plan_definition=plan_definition,
        plan_sha256=plan_hash,
        based_on_state_hash=case.current_state_hash,
        workflow_template_version_id=workflow_template.id,
        created_by=principal.subject,
    )
    session.add(plan)
    await session.flush()
    for position, step in enumerate(payload.steps, start=1):
        session.add(
            CasePlanStep(
                plan_id=plan.id,
                position=position,
                step_key=step.step_key,
                title=step.title,
                instructions=step.instructions,
                agent_version_id=(
                    str(step.agent_version_id) if step.agent_version_id is not None else None
                ),
                depends_on=list(step.depends_on),
                skill_version_ids=[str(item) for item in step.skill_version_ids],
                tool_version_ids=[str(item) for item in step.tool_version_ids],
                output_schema_ref=step.output_schema_ref,
                risk_level=step.risk_level,
                requires_approval=step.requires_approval,
                limits=step.limits.model_dump(mode="json"),
            )
        )
    await session.flush()
    approval = ApprovalRequest(
        case_id=case.id,
        plan_id=plan.id,
        plan_version=plan.version,
        plan_sha256=plan.plan_sha256,
        bound_state_hash=plan.based_on_state_hash,
        approval_type="PLAN_APPROVAL",
        status=ApprovalStatus.PENDING.value,
        requested_by=principal.subject,
        assigned_reviewer_id=payload.assigned_reviewer_id,
        idempotency_key=_approval_key(case.id, principal, idempotency_key),
        expires_at=utcnow() + timedelta(days=7),
    )
    session.add(approval)
    case.status = AgentCaseStatus.AWAITING_PLAN_APPROVAL.value
    await session.flush()
    await _append_event(
        session,
        case=case,
        event_type="PLAN_GENERATED",
        principal=principal,
        request_id=request.state.request_id,
        idempotency_key=_event_key("plan-created", principal, idempotency_key),
        payload={
            "request_fingerprint": fingerprint,
            "plan_id": plan.id,
            "plan_version": plan.version,
            "plan_sha256": plan.plan_sha256,
            "based_on_state_hash": plan.based_on_state_hash,
        },
    )
    await _append_event(
        session,
        case=case,
        event_type="APPROVAL_REQUESTED",
        principal=principal,
        request_id=request.state.request_id,
        idempotency_key=_event_key("approval-requested", principal, idempotency_key),
        payload={
            "approval_id": approval.id,
            "plan_id": plan.id,
            "plan_version": plan.version,
            "plan_sha256": plan.plan_sha256,
            "bound_state_hash": approval.bound_state_hash,
            "assigned_reviewer_id": approval.assigned_reviewer_id,
            "expires_at": approval.expires_at.isoformat() if approval.expires_at else None,
        },
    )
    add_audit_event(
        session,
        principal=principal,
        request_id=request.state.request_id,
        operation="case.plan.create",
        object_type="case_plan",
        object_id=plan.id,
        application_version=settings.app_version,
        after={
            "case_id": case.id,
            "version": plan.version,
            "plan_sha256": plan.plan_sha256,
            "based_on_state_hash": plan.based_on_state_hash,
            "approval_id": approval.id,
        },
    )
    await session.commit()
    return await _plan_response(session, plan)


@router.get("/{case_id}/plans/{version}", response_model=CasePlanResponse)
async def get_case_plan(
    case_id: UUID,
    version: int,
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(session_dependency),
) -> CasePlanResponse:
    if version < 1:
        raise HTTPException(status_code=422, detail="Plan version must be positive")
    case = await _case_for_read(session, case_id, principal)
    plan = await session.scalar(
        select(CasePlan).where(CasePlan.case_id == case.id, CasePlan.version == version)
    )
    if not plan:
        raise HTTPException(status_code=404, detail="Plan version not found")
    return await _plan_response(session, plan)


@router.post("/{case_id}/plans/{version}/approve", response_model=CasePlanResponse)
async def decide_case_plan(
    case_id: UUID,
    version: int,
    payload: PlanDecisionRequest,
    request: Request,
    idempotency_key: IdempotencyKey,
    principal: Principal = Depends(PLAN_APPROVERS),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> CasePlanResponse:
    fingerprint = _request_fingerprint(
        {
            "case_id": str(case_id),
            "version": version,
            **payload.model_dump(mode="json"),
        }
    )
    decision_event_key = _event_key("plan-decision", principal, idempotency_key)
    replay_event = await session.scalar(
        select(CaseEvent).where(
            CaseEvent.case_id == str(case_id),
            CaseEvent.idempotency_key == decision_event_key,
        )
    )
    if replay_event:
        if replay_event.payload.get("request_fingerprint") != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency key payload conflict")
        replay_case = await _case_for_read(session, case_id, principal)
        plan = await session.get(CasePlan, str(replay_event.payload.get("plan_id", "")))
        if not plan or plan.case_id != replay_case.id or plan.version != version:
            raise HTTPException(status_code=409, detail="Idempotent decision result is unavailable")
        return await _plan_response(session, plan)

    case = await _case_for_read(session, case_id, principal, lock=True)
    plan = await session.scalar(
        select(CasePlan)
        .where(CasePlan.case_id == case.id, CasePlan.version == version)
        .with_for_update()
    )
    if not plan:
        raise HTTPException(status_code=404, detail="Plan version not found")
    approval = await session.scalar(
        select(ApprovalRequest)
        .where(
            ApprovalRequest.plan_id == plan.id,
            ApprovalRequest.approval_type == "PLAN_APPROVAL",
        )
        .with_for_update()
    )
    if not approval:
        raise HTTPException(status_code=409, detail="Plan has no approval request")
    if case.owner_subject == principal.subject or approval.requested_by == principal.subject:
        raise HTTPException(status_code=403, detail="Plan creators cannot approve their own plan")
    if approval.assigned_reviewer_id and approval.assigned_reviewer_id != principal.subject:
        raise HTTPException(status_code=403, detail="Plan is assigned to another reviewer")
    if approval.status == ApprovalStatus.EXPIRED.value:
        raise HTTPException(status_code=409, detail="Plan approval has expired")
    if approval.status != ApprovalStatus.PENDING.value:
        raise HTTPException(status_code=409, detail="Plan approval has already been decided")
    if approval.expires_at and _as_utc(approval.expires_at) <= utcnow():
        approval.status = ApprovalStatus.EXPIRED.value
        case.status = AgentCaseStatus.NEEDS_REVISION.value
        await session.flush()
        await _append_event(
            session,
            case=case,
            event_type="PLAN_APPROVAL_EXPIRED",
            principal=principal,
            request_id=request.state.request_id,
            idempotency_key=_event_key("approval-expired", principal, idempotency_key),
            payload={
                "request_fingerprint": fingerprint,
                "approval_id": approval.id,
                "plan_id": plan.id,
                "plan_version": plan.version,
                "plan_sha256": plan.plan_sha256,
                "bound_state_hash": approval.bound_state_hash,
                "expired_at": _as_utc(approval.expires_at).isoformat(),
            },
        )
        add_audit_event(
            session,
            principal=principal,
            request_id=request.state.request_id,
            operation="case.plan.decision",
            object_type="approval_request",
            object_id=approval.id,
            application_version=settings.app_version,
            result="denied",
            reason="Plan approval expired before decision",
            after={"approval_status": approval.status, "case_status": case.status},
        )
        await session.commit()
        raise HTTPException(status_code=409, detail="Plan approval has expired")
    latest_version = await session.scalar(
        select(func.max(CasePlan.version)).where(CasePlan.case_id == case.id)
    )
    binding_matches = (
        payload.expected_plan_sha256 == plan.plan_sha256
        and payload.expected_state_hash == plan.based_on_state_hash
        and approval.plan_sha256 == plan.plan_sha256
        and approval.bound_state_hash == plan.based_on_state_hash
        and case.current_state_hash == plan.based_on_state_hash
        and latest_version == plan.version
    )
    if not binding_matches:
        raise HTTPException(status_code=409, detail="Plan approval binding is stale")
    if case.status != AgentCaseStatus.AWAITING_PLAN_APPROVAL.value:
        raise HTTPException(status_code=409, detail="Case is not awaiting this plan approval")

    before = {
        "approval_status": approval.status,
        "case_status": case.status,
        "plan_sha256": plan.plan_sha256,
        "bound_state_hash": approval.bound_state_hash,
    }
    approval.status = (
        ApprovalStatus.APPROVED.value
        if payload.decision == "approve"
        else ApprovalStatus.REJECTED.value
    )
    approval.decision_by = principal.subject
    approval.decision_reason = payload.reason
    approval.decided_at = utcnow()
    case.status = (
        AgentCaseStatus.READY.value
        if payload.decision == "approve"
        else AgentCaseStatus.NEEDS_REVISION.value
    )
    await session.flush()
    event_type = "PLAN_APPROVED" if payload.decision == "approve" else "PLAN_REJECTED"
    await _append_event(
        session,
        case=case,
        event_type=event_type,
        principal=principal,
        request_id=request.state.request_id,
        idempotency_key=decision_event_key,
        payload={
            "request_fingerprint": fingerprint,
            "decision": payload.decision,
            "reason": payload.reason,
            "approval_id": approval.id,
            "plan_id": plan.id,
            "plan_version": plan.version,
            "plan_sha256": plan.plan_sha256,
            "bound_state_hash": approval.bound_state_hash,
        },
    )
    add_audit_event(
        session,
        principal=principal,
        request_id=request.state.request_id,
        operation=f"case.plan.{payload.decision}",
        object_type="approval_request",
        object_id=approval.id,
        application_version=settings.app_version,
        reason=payload.reason,
        before=before,
        after={
            "approval_status": approval.status,
            "case_status": case.status,
            "decision_by": approval.decision_by,
            "plan_sha256": plan.plan_sha256,
            "bound_state_hash": approval.bound_state_hash,
        },
    )
    await session.commit()
    return await _plan_response(session, plan)


@router.get("/{case_id}/events", response_model=CaseEventPage)
async def list_case_events(
    case_id: UUID,
    cursor: str | None = Query(default=None, max_length=2_048),
    limit: int = Query(default=100, ge=1, le=200),
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(session_dependency),
) -> CaseEventPage:
    case = await _case_for_read(session, case_id, principal)
    try:
        offset = decode_cursor(cursor)
    except InvalidCursor as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    rows = list(
        (
            await session.scalars(
                select(CaseEvent)
                .where(CaseEvent.case_id == case.id)
                .order_by(CaseEvent.sequence)
                .offset(offset)
                .limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    return CaseEventPage(
        items=[_event_response(event) for event in rows[:limit]],
        next_cursor=encode_cursor(offset + limit) if has_more else None,
        has_more=has_more,
    )
