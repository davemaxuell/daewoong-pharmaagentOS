from __future__ import annotations

from collections import Counter
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import add_audit_event
from app.cases.hashing import canonical_sha256
from app.cases.router import _case_for_read, _scoped_idempotency_key
from app.config import Settings
from app.dependencies import session_dependency, settings_dependency
from app.evaluation.schemas import (
    ControlTowerSummary,
    EvaluationCaseResponse,
    EvaluationComparisonResponse,
    EvaluationGradeResponse,
    EvaluationRunPage,
    EvaluationRunRequest,
    EvaluationRunResponse,
    EvaluationSuiteCreateRequest,
    EvaluationSuitePage,
    EvaluationSuiteResponse,
    EvaluationTrialResponse,
    FeedbackRequest,
    FeedbackResponse,
    HumanGradeRequest,
    InventoryItem,
    InventoryResponse,
    ReleaseDecisionRequest,
    ReleaseDecisionResponse,
    TraceResponse,
)
from app.evaluation.service import DeterministicEvaluationRunner, target_record
from app.models import (
    AgentInvocation,
    AgentRunStatus,
    AgentVersion,
    ApprovalRequest,
    ArtifactVersion,
    Case,
    CaseRun,
    DurableActivity,
    EvaluationCase,
    EvaluationGrade,
    EvaluationRun,
    EvaluationSuite,
    EvaluationTrial,
    ImpactHypothesis,
    PlatformControl,
    PolicyDecision,
    ProcessingJob,
    ProductionFeedback,
    ReleaseApproval,
    RunEvent,
    SkillVersion,
    ToolInvocation,
    ToolVersion,
    VerificationReport,
    WorkflowTemplateVersion,
    utcnow,
)
from app.security.auth import Principal, current_principal, require_roles, view_principal

router = APIRouter(tags=["Evaluation Center and Control Tower"])

IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=16,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
EVAL_AUTHORS = require_roles("agent_developer", "system_owner")
RELEASE_APPROVERS = require_roles("system_owner")
HUMAN_GRADERS = require_roles("reviewer", "domain_sme")


async def _suite_response(session: AsyncSession, suite: EvaluationSuite) -> EvaluationSuiteResponse:
    cases = list(
        (
            await session.scalars(
                select(EvaluationCase)
                .where(EvaluationCase.suite_id == suite.id)
                .order_by(EvaluationCase.case_key)
            )
        ).all()
    )
    return EvaluationSuiteResponse(
        id=suite.id,
        suite_key=suite.suite_key,
        version=suite.version,
        name=suite.name,
        description=suite.description,
        target_kind=suite.target_kind,
        gates=suite.gates,
        suite_sha256=suite.suite_sha256,
        cases=[
            EvaluationCaseResponse(
                id=item.id,
                case_key=item.case_key,
                title=item.title,
                category=item.category,
                input=item.input,
                expected_outcome=item.expected_outcome,
                critical=item.critical,
                synthetic=True,
                case_sha256=item.case_sha256,
                created_at=item.created_at,
            )
            for item in cases
        ],
        created_by=suite.created_by,
        created_at=suite.created_at,
    )


async def _run_response(session: AsyncSession, run: EvaluationRun) -> EvaluationRunResponse:
    trials = list(
        (
            await session.scalars(
                select(EvaluationTrial)
                .where(EvaluationTrial.evaluation_run_id == run.id)
                .order_by(EvaluationTrial.evaluation_case_id, EvaluationTrial.trial_number)
            )
        ).all()
    )
    grades_by_trial: dict[str, list[EvaluationGrade]] = {}
    if trials:
        grades = list(
            (
                await session.scalars(
                    select(EvaluationGrade)
                    .where(EvaluationGrade.evaluation_trial_id.in_([item.id for item in trials]))
                    .order_by(EvaluationGrade.metric)
                )
            ).all()
        )
        for grade in grades:
            grades_by_trial.setdefault(grade.evaluation_trial_id, []).append(grade)
    return EvaluationRunResponse(
        id=run.id,
        suite_id=run.suite_id,
        target_kind=run.target_kind,
        target_version_id=run.target_version_id,
        target_sha256=run.target_sha256,
        baseline_version_id=run.baseline_version_id,
        trial_count=run.trial_count,
        status=run.status,
        metrics=run.metrics,
        total_trials=run.total_trials,
        passed_trials=run.passed_trials,
        critical_failures=run.critical_failures,
        total_cost_usd=run.total_cost_usd,
        total_latency_ms=run.total_latency_ms,
        requested_by=run.requested_by,
        started_at=run.started_at,
        completed_at=run.completed_at,
        trials=[
            EvaluationTrialResponse(
                id=trial.id,
                evaluation_case_id=trial.evaluation_case_id,
                trial_number=trial.trial_number,
                status=trial.status,
                trajectory=trial.trajectory,
                final_state=trial.final_state,
                output_sha256=trial.output_sha256,
                token_count=trial.token_count,
                cost_usd=trial.cost_usd,
                latency_ms=trial.latency_ms,
                error_code=trial.error_code,
                grades=[
                    EvaluationGradeResponse(
                        grader_type=grade.grader_type,
                        metric=grade.metric,
                        score=grade.score,
                        passed=grade.passed,
                        critical=grade.critical,
                        rationale=grade.rationale,
                        evidence=grade.evidence,
                        graded_by=grade.graded_by,
                    )
                    for grade in grades_by_trial.get(trial.id, [])
                ],
            )
            for trial in trials
        ],
    )


@router.post("/eval-suites", response_model=EvaluationSuiteResponse, status_code=201)
async def create_evaluation_suite(
    payload: EvaluationSuiteCreateRequest,
    request: Request,
    idempotency_key: IdempotencyKey,
    principal: Principal = Depends(EVAL_AUTHORS),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> EvaluationSuiteResponse:
    definition = payload.model_dump(mode="json")
    suite_sha = canonical_sha256(definition)
    existing = await session.scalar(
        select(EvaluationSuite).where(
            EvaluationSuite.suite_key == payload.suite_key,
            EvaluationSuite.version == payload.version,
        )
    )
    if existing:
        if existing.suite_sha256 != suite_sha:
            raise HTTPException(
                status_code=409,
                detail="Evaluation suite version already exists with different content",
            )
        return await _suite_response(session, existing)
    suite = EvaluationSuite(
        suite_key=payload.suite_key,
        version=payload.version,
        name=payload.name,
        description=payload.description,
        target_kind=payload.target_kind,
        gates=[item.model_dump(mode="json") for item in payload.gates],
        suite_sha256=suite_sha,
        created_by=principal.subject,
    )
    session.add(suite)
    await session.flush()
    for item in payload.cases:
        case_payload = item.model_dump(mode="json")
        session.add(
            EvaluationCase(
                suite_id=suite.id,
                case_sha256=canonical_sha256(case_payload),
                created_by=principal.subject,
                **case_payload,
            )
        )
    add_audit_event(
        session,
        principal=principal,
        request_id=request.state.request_id,
        operation="evaluation_suite.create",
        object_type="evaluation_suite",
        object_id=suite.id,
        application_version=settings.app_version,
        after={
            "suite_sha256": suite_sha,
            "idempotency_scope": _scoped_idempotency_key(principal, idempotency_key),
        },
    )
    await session.commit()
    return await _suite_response(session, suite)


@router.get("/eval-suites/{suite_id}", response_model=EvaluationSuiteResponse)
async def get_evaluation_suite(
    suite_id: UUID,
    _principal: Principal = Depends(view_principal),
    session: AsyncSession = Depends(session_dependency),
) -> EvaluationSuiteResponse:
    suite = await session.get(EvaluationSuite, str(suite_id))
    if suite is None:
        raise HTTPException(status_code=404, detail="Evaluation suite not found")
    return await _suite_response(session, suite)


@router.get("/eval-suites", response_model=EvaluationSuitePage)
async def list_evaluation_suites(
    _principal: Principal = Depends(view_principal),
    session: AsyncSession = Depends(session_dependency),
) -> EvaluationSuitePage:
    suites = list(
        (
            await session.scalars(
                select(EvaluationSuite).order_by(EvaluationSuite.created_at.desc()).limit(50)
            )
        ).all()
    )
    return EvaluationSuitePage(items=[await _suite_response(session, suite) for suite in suites])


@router.post("/eval-runs", response_model=EvaluationRunResponse, status_code=201)
async def create_evaluation_run(
    payload: EvaluationRunRequest,
    request: Request,
    idempotency_key: IdempotencyKey,
    principal: Principal = Depends(EVAL_AUTHORS),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> EvaluationRunResponse:
    key = _scoped_idempotency_key(principal, idempotency_key)
    existing = await session.scalar(
        select(EvaluationRun).where(EvaluationRun.idempotency_key == key)
    )
    if existing:
        return await _run_response(session, existing)
    suite = await session.get(EvaluationSuite, str(payload.suite_id))
    if suite is None:
        raise HTTPException(status_code=404, detail="Evaluation suite not found")
    if suite.target_kind != payload.target_kind:
        raise HTTPException(status_code=409, detail="Suite and target kinds do not match")
    _target, digest = await target_record(
        session, payload.target_kind, str(payload.target_version_id)
    )
    run = EvaluationRun(
        suite_id=suite.id,
        target_kind=payload.target_kind,
        target_version_id=str(payload.target_version_id),
        target_sha256=digest,
        baseline_version_id=str(payload.baseline_version_id)
        if payload.baseline_version_id
        else None,
        trial_count=payload.trial_count,
        status="PENDING",
        requested_by=principal.subject,
        idempotency_key=key,
        started_at=utcnow(),
    )
    session.add(run)
    await session.flush()
    await DeterministicEvaluationRunner(session).run(run, suite)
    add_audit_event(
        session,
        principal=principal,
        request_id=request.state.request_id,
        operation="evaluation_run.complete",
        object_type="evaluation_run",
        object_id=run.id,
        application_version=settings.app_version,
        after={
            "status": run.status,
            "critical_failures": run.critical_failures,
            "target_sha256": digest,
        },
    )
    await session.commit()
    return await _run_response(session, run)


@router.get("/eval-runs/{run_id}", response_model=EvaluationRunResponse)
async def get_evaluation_run(
    run_id: UUID,
    _principal: Principal = Depends(view_principal),
    session: AsyncSession = Depends(session_dependency),
) -> EvaluationRunResponse:
    run = await session.get(EvaluationRun, str(run_id))
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    return await _run_response(session, run)


@router.get("/eval-runs", response_model=EvaluationRunPage)
async def list_evaluation_runs(
    _principal: Principal = Depends(view_principal),
    session: AsyncSession = Depends(session_dependency),
) -> EvaluationRunPage:
    runs = list(
        (
            await session.scalars(
                select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(50)
            )
        ).all()
    )
    return EvaluationRunPage(items=[await _run_response(session, run) for run in runs])


@router.post("/eval-trials/{trial_id}/human-grade", response_model=EvaluationRunResponse)
async def add_human_grade(
    trial_id: UUID,
    payload: HumanGradeRequest,
    request: Request,
    principal: Principal = Depends(HUMAN_GRADERS),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> EvaluationRunResponse:
    trial = await session.get(EvaluationTrial, str(trial_id))
    if trial is None:
        raise HTTPException(status_code=404, detail="Evaluation trial not found")
    existing = await session.scalar(
        select(EvaluationGrade).where(
            EvaluationGrade.evaluation_trial_id == trial.id,
            EvaluationGrade.grader_type == "HUMAN",
            EvaluationGrade.metric == payload.metric,
        )
    )
    if existing:
        raise HTTPException(
            status_code=409, detail="Human grade is immutable; create a new evaluation run"
        )
    grade = EvaluationGrade(
        evaluation_trial_id=trial.id,
        grader_type="HUMAN",
        graded_by=principal.subject,
        **payload.model_dump(mode="json"),
    )
    session.add(grade)
    add_audit_event(
        session,
        principal=principal,
        request_id=request.state.request_id,
        operation="evaluation_trial.human_grade",
        object_type="evaluation_trial",
        object_id=trial.id,
        application_version=settings.app_version,
        after={"metric": grade.metric, "passed": grade.passed},
    )
    await session.commit()
    run = await session.get(EvaluationRun, trial.evaluation_run_id)
    assert run is not None
    return await _run_response(session, run)


@router.get(
    "/eval-runs/{candidate_run_id}/compare/{baseline_run_id}",
    response_model=EvaluationComparisonResponse,
)
async def compare_evaluation_runs(
    candidate_run_id: UUID,
    baseline_run_id: UUID,
    _principal: Principal = Depends(view_principal),
    session: AsyncSession = Depends(session_dependency),
) -> EvaluationComparisonResponse:
    candidate = await session.get(EvaluationRun, str(candidate_run_id))
    baseline = await session.get(EvaluationRun, str(baseline_run_id))
    if candidate is None or baseline is None:
        raise HTTPException(status_code=404, detail="Evaluation comparison run not found")
    keys = set(candidate.metrics).intersection(baseline.metrics)
    deltas = {
        key: float(candidate.metrics[key]) - float(baseline.metrics[key])
        for key in keys
        if isinstance(candidate.metrics[key], (int, float))
        and isinstance(baseline.metrics[key], (int, float))
    }
    regressions = sorted(
        key
        for key, value in deltas.items()
        if (key.endswith("rate") and key != "pass_rate" and value > 0)
        or (key == "pass_rate" and value < 0)
        or ("latency" in key and value > 0)
    )
    return EvaluationComparisonResponse(
        candidate_run_id=candidate.id,
        baseline_run_id=baseline.id,
        metric_deltas=deltas,
        regression_metrics=regressions,
        release_blocked=candidate.status != "PASSED" or bool(regressions),
    )


@router.post("/eval-runs/{run_id}/approve-release", response_model=ReleaseDecisionResponse)
async def decide_release(
    run_id: UUID,
    payload: ReleaseDecisionRequest,
    request: Request,
    _idempotency_key: IdempotencyKey,
    principal: Principal = Depends(RELEASE_APPROVERS),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> ReleaseDecisionResponse:
    run = await session.scalar(
        select(EvaluationRun).where(EvaluationRun.id == str(run_id)).with_for_update()
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    existing = await session.scalar(
        select(ReleaseApproval).where(ReleaseApproval.evaluation_run_id == run.id)
    )
    if existing:
        return ReleaseDecisionResponse.model_validate(existing, from_attributes=True)
    target, digest = await target_record(session, run.target_kind, run.target_version_id)
    if digest != run.target_sha256 or digest != payload.expected_target_sha256:
        raise HTTPException(status_code=409, detail="Release target binding is stale")
    approved = payload.decision == "approve"
    if approved and payload.target_status == "PRODUCTION" and settings.app_env == "production":
        # This runner grades supplied fixture outcomes. It has no independent
        # execution adapter, so its results must never qualify a live release.
        raise HTTPException(
            status_code=409,
            detail="Fixture evaluations cannot authorize production release; "
            "an independently executed and qualified evaluation adapter is required",
        )
    if approved and run.status != "PASSED":
        raise HTTPException(status_code=409, detail="Critical evaluation failures block release")
    critical_human_failure = await session.scalar(
        select(EvaluationGrade.id)
        .join(EvaluationTrial, EvaluationTrial.id == EvaluationGrade.evaluation_trial_id)
        .where(
            EvaluationTrial.evaluation_run_id == run.id,
            EvaluationGrade.grader_type == "HUMAN",
            EvaluationGrade.critical.is_(True),
            EvaluationGrade.passed.is_(False),
        )
        .limit(1)
    )
    if approved and critical_human_failure:
        raise HTTPException(status_code=409, detail="Critical human grade blocks release")
    allowed_sources = {
        "STAGING": {"DRAFT", "DEVELOPMENT", "TESTING", "APPROVED", "SUSPENDED"},
        "PRODUCTION": {"APPROVED", "STAGING"},
    }
    if approved and target.release_status not in allowed_sources[payload.target_status]:
        raise HTTPException(status_code=409, detail="Release transition is not allowed")
    model = AgentVersion if run.target_kind == "AGENT_VERSION" else WorkflowTemplateVersion
    key_field = model.agent_key if run.target_kind == "AGENT_VERSION" else model.workflow_key
    key_value = target.agent_key if run.target_kind == "AGENT_VERSION" else target.workflow_key
    rollback = await session.scalar(
        select(model)
        .where(key_field == key_value, model.release_status == "PRODUCTION", model.id != target.id)
        .order_by(model.created_at.desc())
        .limit(1)
    )
    decision = ReleaseApproval(
        evaluation_run_id=run.id,
        target_kind=run.target_kind,
        target_version_id=target.id,
        target_sha256=digest,
        target_status=payload.target_status,
        decision="APPROVED" if approved else "REJECTED",
        rollback_target_id=rollback.id if rollback else None,
        decided_by=principal.subject,
        reason=payload.reason,
    )
    session.add(decision)
    if approved:
        target.release_status = payload.target_status
    await session.flush()
    add_audit_event(
        session,
        principal=principal,
        request_id=request.state.request_id,
        operation="release.decide",
        object_type=run.target_kind.lower(),
        object_id=target.id,
        application_version=settings.app_version,
        after={
            "decision": decision.decision,
            "target_status": payload.target_status,
            "rollback_target_id": decision.rollback_target_id,
        },
    )
    await session.commit()
    return ReleaseDecisionResponse.model_validate(decision, from_attributes=True)


@router.post("/feedback", response_model=FeedbackResponse, status_code=201)
async def create_feedback(
    payload: FeedbackRequest,
    request: Request,
    principal: Principal = Depends(current_principal),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> FeedbackResponse:
    if payload.case_id:
        await _case_for_read(session, payload.case_id, principal)
    data = payload.model_dump(mode="json")
    feedback = ProductionFeedback(
        **{
            key: str(value) if key.endswith("_id") and value else value
            for key, value in data.items()
        },
        payload_sha256=canonical_sha256(data),
        submitted_by=principal.subject,
    )
    session.add(feedback)
    await session.flush()
    add_audit_event(
        session,
        principal=principal,
        request_id=request.state.request_id,
        operation="feedback.create",
        object_type="production_feedback",
        object_id=feedback.id,
        application_version=settings.app_version,
        after={"signal_type": feedback.signal_type, "payload_sha256": feedback.payload_sha256},
    )
    await session.commit()
    return FeedbackResponse.model_validate(feedback, from_attributes=True)


async def _count(session: AsyncSession, model, *clauses) -> int:
    return int(await session.scalar(select(func.count()).select_from(model).where(*clauses)) or 0)


def _percentile(values: list[float], quantile: float) -> float:
    """Return a deterministic interpolated percentile, or zero for an empty sample."""

    if not values:
        return 0
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + ((ordered[upper] - ordered[lower]) * fraction)


@router.get("/control-tower/summary", response_model=ControlTowerSummary)
async def control_tower_summary(
    _principal: Principal = Depends(view_principal),
    session: AsyncSession = Depends(session_dependency),
) -> ControlTowerSummary:
    case_total = await _count(session, Case)
    completed = await _count(session, Case, Case.status == "COMPLETED")
    hypotheses = await _count(session, ImpactHypothesis)
    accepted = await _count(session, ImpactHypothesis, ImpactHypothesis.status == "ACCEPTED")
    reports = list((await session.scalars(select(VerificationReport))).all())
    issue_codes = Counter(issue.get("code") for report in reports for issue in report.issues)
    invocations = list((await session.scalars(select(AgentInvocation))).all())
    tools = list((await session.scalars(select(ToolInvocation))).all())
    runs = list((await session.scalars(select(CaseRun))).all())
    approvals = list((await session.scalars(select(ApprovalRequest))).all())
    controls = list((await session.scalars(select(PlatformControl))).all())
    jobs = list((await session.scalars(select(ProcessingJob))).all())
    activities = list((await session.scalars(select(DurableActivity))).all())
    decisions = list((await session.scalars(select(PolicyDecision))).all())
    grades = list((await session.scalars(select(EvaluationGrade))).all())
    agent_versions = list((await session.scalars(select(AgentVersion))).all())
    tool_versions = list((await session.scalars(select(ToolVersion))).all())
    skill_versions = list((await session.scalars(select(SkillVersion))).all())
    workflow_versions = list((await session.scalars(select(WorkflowTemplateVersion))).all())
    usage = [item.usage or {} for item in invocations]
    total_cost = sum(float(item.get("cost_usd", 0)) for item in usage)
    total_tokens = sum(
        int(item.get("input_tokens", 0)) + int(item.get("output_tokens", 0)) for item in usage
    )
    failed_invocations = sum(item.status == "FAILED" for item in invocations)
    failed_tools = sum(item.status == "FAILED" for item in tools)
    tool_latencies = [float(item.latency_ms) for item in tools]
    workflow_latencies = [
        max(0.0, (item.completed_at - item.started_at).total_seconds() * 1_000)
        for item in runs
        if item.started_at is not None and item.completed_at is not None
    ]
    review_turnarounds = [
        max(0.0, (item.decided_at - item.created_at).total_seconds() / 3_600)
        for item in approvals
        if item.decided_at is not None
    ]
    citation_issue_codes = {
        "CITATION_SEMANTIC_SUPPORT_LOW",
        "EXTERNAL_CITATION_INVALID",
        "INTERNAL_CITATION_INVALID",
    }
    reports_without_citation_issues = sum(
        not any(issue.get("code") in citation_issue_codes for issue in report.issues)
        for report in reports
    )
    metric_scores: dict[str, list[float]] = {}
    for grade in grades:
        metric_scores.setdefault(grade.metric, []).append(float(grade.score))

    def mean_grade(*names: str) -> float:
        scores = [score for name in names for score in metric_scores.get(name, [])]
        return sum(scores) / len(scores) if scores else 0

    data_access_denials = sum(
        decision.effect == "DENY"
        and any("ACCESS" in str(code) or "ACL" in str(code) for code in decision.reason_codes)
        for decision in decisions
    )
    secret_or_pii_detections = sum(
        any(
            warning in {"SENSITIVE_CONTENT_REDACTED", "SECRET_DETECTED", "PII_DETECTED"}
            for warning in tool.warnings
        )
        for tool in tools
    )
    suspended_agent_ids = {
        item.id for item in agent_versions if item.release_status == "SUSPENDED"
    } | {
        item.agent_version_id
        for item in controls
        if item.scope == "AGENT" and item.suspended and item.agent_version_id is not None
    }
    owner_ids = {
        item.created_by
        for item in [*agent_versions, *skill_versions, *tool_versions, *workflow_versions]
    }
    repeated_finding_count = sum(
        occurrences > 1
        for occurrences in Counter(
            item.finding_id for item in (await session.scalars(select(ImpactHypothesis))).all()
        ).values()
    )
    return ControlTowerSummary(
        inventory={
            "agents": len(agent_versions),
            "skills": len(skill_versions),
            "mcp_servers": len({item.server_key for item in tool_versions}),
            "tools": len(tool_versions),
            "models_observed": len(
                {
                    str(item["model_id"])
                    for item in usage
                    if isinstance(item.get("model_id"), str) and item["model_id"]
                }
            ),
            "workflows": len(workflow_versions),
            "owners": len(owner_ids),
            "risk_classes": len({item.risk_class for item in tool_versions}),
            "evaluation_suites": await _count(session, EvaluationSuite),
            "datasets": await _count(session, EvaluationCase),
        },
        operational_health={
            "running_cases": await _count(session, Case, Case.status == "RUNNING"),
            "paused_runs": await _count(
                session, CaseRun, CaseRun.status == AgentRunStatus.PAUSED.value
            ),
            "failed_runs": await _count(
                session, CaseRun, CaseRun.status == AgentRunStatus.FAILED.value
            ),
            "tool_errors": failed_tools,
            "tool_error_rate": failed_tools / len(tools) if tools else 0,
            "model_errors": failed_invocations,
            "model_error_rate": failed_invocations / len(invocations) if invocations else 0,
            "queue_depth": sum(item.status in {"pending", "running"} for item in jobs),
            "retry_count": sum(max(0, item.attempt_count - 1) for item in jobs)
            + sum(max(0, item.attempts - 1) for item in activities),
            "failed_durable_activities": sum(item.status == "FAILED" for item in activities),
            "pending_approvals": sum(item.status == "PENDING" for item in approvals),
        },
        quality={
            "workflow_completion_rate": completed / case_total if case_total else 0,
            "citation_correctness_rate": (
                reports_without_citation_issues / len(reports) if reports else 0
            ),
            "reviewer_acceptance_rate": accepted / hypotheses if hypotheses else 0,
            "unsupported_claim_detections": issue_codes["CITATION_SEMANTIC_SUPPORT_LOW"]
            + issue_codes["HYPOTHESIS_HASH_MISMATCH"],
            "unsupported_claim_rate": (
                (
                    issue_codes["CITATION_SEMANTIC_SUPPORT_LOW"]
                    + issue_codes["HYPOTHESIS_HASH_MISMATCH"]
                )
                / hypotheses
                if hypotheses
                else 0
            ),
            "correction_loop_frequency": sum(report.correction_iteration > 0 for report in reports),
            "correction_loop_rate": (
                sum(report.correction_iteration > 0 for report in reports) / len(reports)
                if reports
                else 0
            ),
            "retrieval_recall": mean_grade("retrieval_recall", "retrieval_recall_at_k"),
            "agent_route_accuracy": mean_grade("agent_route_accuracy", "route_accuracy"),
        },
        security={
            "policy_denials": sum(item.effect == "DENY" for item in decisions),
            "unauthorized_tool_attempts": sum(item.status == "DENIED" for item in tools),
            "data_access_denials": data_access_denials,
            "prompt_injection_detections": issue_codes["PROMPT_INJECTION_DETECTED"]
            + sum(
                "INSTRUCTION_LIKE_CONTENT_SANITIZED" in item.warnings for item in tools
            ),
            "secret_or_pii_detections": secret_or_pii_detections,
            "suspended_agents": len(suspended_agent_ids),
            "global_suspension_active": int(
                any(item.scope == "GLOBAL" and item.suspended for item in controls)
            ),
        },
        cost_performance={
            "total_cost_usd": round(total_cost, 6),
            "cost_per_case_usd": round(total_cost / case_total, 6) if case_total else 0,
            "tokens": total_tokens,
            "tokens_per_workflow": total_tokens / len(runs) if runs else 0,
            "p50_workflow_latency_ms": round(_percentile(workflow_latencies, 0.50), 3),
            "p95_workflow_latency_ms": round(_percentile(workflow_latencies, 0.95), 3),
            "tool_latency_ms": int(sum(tool_latencies)),
            "p50_tool_latency_ms": round(_percentile(tool_latencies, 0.50), 3),
            "p95_tool_latency_ms": round(_percentile(tool_latencies, 0.95), 3),
            "cache_hit_rate": (
                sum(bool(item.get("cache_hit")) for item in usage)
                / sum("cache_hit" in item for item in usage)
                if any("cache_hit" in item for item in usage)
                else 0
            ),
        },
        business_value={
            "cases_completed": completed,
            "signals_triaged": case_total,
            "reports_accepted": await _count(
                session, ArtifactVersion, ArtifactVersion.status == "APPROVED"
            ),
            "feedback_records": await _count(session, ProductionFeedback),
            "review_turnaround_hours": (
                sum(review_turnarounds) / len(review_turnarounds) if review_turnarounds else 0
            ),
            "repeated_findings_detected": repeated_finding_count,
        },
        generated_at=utcnow(),
    )


@router.get("/control-tower/inventory", response_model=InventoryResponse)
async def control_tower_inventory(
    _principal: Principal = Depends(view_principal),
    session: AsyncSession = Depends(session_dependency),
) -> InventoryResponse:
    items: list[InventoryItem] = []
    definitions = (
        (AgentVersion, "AGENT_VERSION", "agent_key"),
        (SkillVersion, "SKILL_VERSION", "skill_key"),
        (ToolVersion, "TOOL_VERSION", "tool_key"),
        (WorkflowTemplateVersion, "WORKFLOW_VERSION", "workflow_key"),
    )
    for model, kind, key_attribute in definitions:
        rows = list((await session.scalars(select(model).order_by(model.created_at))).all())
        items.extend(
            InventoryItem(
                id=item.id,
                kind=kind,
                key=getattr(item, key_attribute),
                version=item.version,
                sha256=item.manifest_sha256,
                release_status=item.release_status,
            )
            for item in rows
        )
    return InventoryResponse(items=items)


@router.get("/control-tower/runs/{run_id}/trace", response_model=TraceResponse)
async def production_trace(
    run_id: UUID,
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(session_dependency),
) -> TraceResponse:
    run = await session.get(CaseRun, str(run_id))
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    await _case_for_read(session, UUID(run.case_id), principal)
    events = list(
        (
            await session.scalars(
                select(RunEvent).where(RunEvent.run_id == run.id).order_by(RunEvent.sequence)
            )
        ).all()
    )
    invocations = list(
        (
            await session.scalars(
                select(AgentInvocation)
                .where(AgentInvocation.run_id == run.id)
                .order_by(AgentInvocation.created_at)
            )
        ).all()
    )
    tools = list(
        (
            await session.scalars(
                select(ToolInvocation)
                .where(ToolInvocation.run_id == run.id)
                .order_by(ToolInvocation.created_at)
            )
        ).all()
    )
    approvals = list(
        (
            await session.scalars(
                select(ApprovalRequest)
                .where(ApprovalRequest.run_id == run.id)
                .order_by(ApprovalRequest.created_at)
            )
        ).all()
    )
    trace: list[dict[str, Any]] = []
    trace.extend(
        {
            "kind": "RUN_EVENT",
            "sequence": item.sequence,
            "event": item.event_type,
            "actor": item.actor_id,
            "input_hash": item.previous_event_hash,
            "output_hash": item.event_hash,
            "occurred_at": item.occurred_at.isoformat(),
        }
        for item in events
    )
    trace.extend(
        {
            "kind": "AGENT_INVOCATION",
            "step": item.step_key,
            "status": item.status,
            "agent_version_id": item.agent_version_id,
            "input_hash": item.input_sha256,
            "output_hash": item.output_sha256,
            "usage": item.usage,
        }
        for item in invocations
    )
    trace.extend(
        {
            "kind": "TOOL_INVOCATION",
            "tool": item.tool_name,
            "status": item.status,
            "policy": item.policy_effect,
            "arguments_hash": item.arguments_sha256,
            "result_hash": item.result_sha256,
            "latency_ms": item.latency_ms,
        }
        for item in tools
    )
    trace.extend(
        {
            "kind": "APPROVAL",
            "type": item.approval_type,
            "status": item.status,
            "decision_by": item.decision_by,
            "reason": item.decision_reason,
        }
        for item in approvals
    )
    return TraceResponse(run_id=run.id, case_id=run.case_id, status=run.status, trace=trace)
