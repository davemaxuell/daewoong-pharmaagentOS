"""Host-owned completion checks shared by HTTP and future worker executors."""

from __future__ import annotations

from datetime import UTC

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_platform.controls import active_suspension
from app.agent_platform.regulatory.contracts import RegulatoryFindingList
from app.agent_platform.runtime.schemas import InvocationUsage
from app.models import (
    AgentInvocation,
    AgentVersion,
    ApprovalRequest,
    ApprovalStatus,
    Case,
    CasePlan,
    CasePlanStep,
    CaseRun,
    RegistryReleaseStatus,
    SkillVersion,
    ToolVersion,
    WorkflowTemplateVersion,
    utcnow,
)
from app.verification.schemas import VerificationReportResponse

# Exact, reviewed contracts only. Never resolve a caller-provided import or path.
OUTPUT_CONTRACTS = {
    "RegulatoryFindingList@2.0.0": RegulatoryFindingList,
    "VerificationReport@1.0.0": VerificationReportResponse,
}


def validate_completion_payload(
    schema_ref: str, output: dict[str, object], usage: dict[str, int | float]
) -> dict[str, int | float]:
    contract = OUTPUT_CONTRACTS.get(schema_ref)
    if contract is None:
        raise HTTPException(status_code=409, detail="Step output contract is not implemented")
    try:
        contract.model_validate(output)
        validated_usage = InvocationUsage.model_validate(usage)
    except ValidationError as exc:
        # Validation errors can contain source text or sensitive model output.
        raise HTTPException(
            status_code=422, detail="Step output or usage violates its contract"
        ) from exc
    return validated_usage.model_dump(mode="json")


async def validate_completion_binding(
    session: AsyncSession, *, run: CaseRun, case: Case, invocation: AgentInvocation
) -> None:
    checkpoint = run.checkpoint or {}
    state = (checkpoint.get("steps") or {}).get(invocation.step_key) or {}
    step = await session.get(CasePlanStep, invocation.plan_step_id, populate_existing=True)
    plan = await session.get(CasePlan, run.plan_id, populate_existing=True)
    if (
        invocation.run_id != run.id
        or invocation.case_id != case.id
        or state.get("invocation_id") != invocation.id
        or state.get("attempt") != invocation.attempt
        or state.get("status") != "RUNNING"
        or not step
        or step.plan_id != run.plan_id
        or step.step_key != invocation.step_key
        or step.agent_version_id != invocation.agent_version_id
        or step.output_schema_ref != invocation.output_schema_ref
        or step.limits != invocation.limits
        or not plan
        or plan.case_id != case.id
        or plan.version != run.plan_version
        or plan.plan_sha256 != run.plan_sha256
        or plan.based_on_state_hash != run.bound_state_hash
        or case.current_state_hash != run.bound_state_hash
    ):
        raise HTTPException(status_code=409, detail="Step completion binding is stale or invalid")
    control = checkpoint.get("control") or {}
    if control.get("pause_requested") or control.get("cancel_requested"):
        raise HTTPException(status_code=409, detail="Run control prevents step completion")
    if await active_suspension(
        session, [step.agent_version_id] if step.agent_version_id else []
    ):
        raise HTTPException(status_code=409, detail="Runtime is suspended")

    approved = {RegistryReleaseStatus.APPROVED.value, RegistryReleaseStatus.PRODUCTION.value}
    template = await session.get(
        WorkflowTemplateVersion, plan.workflow_template_version_id, populate_existing=True
    )
    workflow = checkpoint.get("workflow_template") or {}
    if (
        not template
        or template.id != workflow.get("id")
        or template.manifest_sha256 != workflow.get("manifest_sha256")
        or template.release_status not in approved
        or not ((template.manifest or {}).get("spec") or {}).get("executionEnabled")
    ):
        raise HTTPException(status_code=409, detail="Workflow release binding is unavailable")
    for model, identifiers in (
        (AgentVersion, [step.agent_version_id] if step.agent_version_id else []),
        (SkillVersion, step.skill_version_ids or []),
        (ToolVersion, step.tool_version_ids or []),
    ):
        for identifier in identifiers:
            release = await session.get(model, identifier, populate_existing=True)
            if not release or release.release_status not in approved:
                raise HTTPException(status_code=409, detail="Step release binding is unavailable")

    approval = await session.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.plan_id == plan.id,
            ApprovalRequest.approval_type == "PLAN_APPROVAL",
        ).execution_options(populate_existing=True)
    )
    approvals = [approval]
    if step.requires_approval:
        step_approval = await session.get(
            ApprovalRequest, state.get("approval_id") or "", populate_existing=True
        )
        if (
            not step_approval
            or step_approval.approval_type != "STEP_APPROVAL"
            or step_approval.run_id != run.id
            or step_approval.plan_step_id != step.id
            or step_approval.step_key != step.step_key
            or not step_approval.decision_by
            or step_approval.decision_by in {
                case.owner_subject, run.requested_by, step_approval.requested_by
            }
        ):
            raise HTTPException(status_code=409, detail="Step approval binding is unavailable")
        approvals.append(step_approval)
    for item in approvals:
        if (
            not item
            or item.status != ApprovalStatus.APPROVED.value
            or item.case_id != case.id
            or item.plan_id != plan.id
            or item.plan_version != plan.version
            or item.plan_sha256 != run.plan_sha256
            or item.bound_state_hash != run.bound_state_hash
            or item.expires_at.replace(tzinfo=item.expires_at.tzinfo or UTC) <= utcnow()
        ):
            raise HTTPException(
                status_code=409, detail="Completion requires current bound approval"
            )
