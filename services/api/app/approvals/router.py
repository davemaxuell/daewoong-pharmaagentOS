from __future__ import annotations

from datetime import UTC
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.approvals.schemas import ApprovalCenterItem, ApprovalCenterPage
from app.cases.router import GLOBAL_CASE_READ_ROLES, _require_case_read, _require_list_access
from app.dependencies import session_dependency
from app.models import ApprovalRequest, Case, utcnow
from app.security.auth import Principal, current_principal

router = APIRouter(prefix="/approvals", tags=["Approval Center"])


def _aware(value):
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _response(approval: ApprovalRequest, case: Case) -> ApprovalCenterItem:
    return ApprovalCenterItem(
        id=approval.id,
        case_id=approval.case_id,
        case_title=case.title,
        plan_id=approval.plan_id,
        plan_version=approval.plan_version,
        plan_sha256=approval.plan_sha256,
        bound_state_hash=approval.bound_state_hash,
        run_id=approval.run_id,
        step_key=approval.step_key,
        artifact_version_id=approval.artifact_version_id,
        approval_type=approval.approval_type,
        status=approval.status,
        requested_by=approval.requested_by,
        assigned_reviewer_id=approval.assigned_reviewer_id,
        decision_by=approval.decision_by,
        decision_reason=approval.decision_reason,
        decided_at=approval.decided_at,
        expires_at=approval.expires_at,
        expired=approval.status == "PENDING" and _aware(approval.expires_at) <= utcnow(),
        created_at=approval.created_at,
    )


@router.get("", response_model=ApprovalCenterPage)
async def list_approvals(
    approval_status: Literal["PENDING", "APPROVED", "REJECTED", "CANCELLED", "EXPIRED"]
    | None = Query(default=None, alias="status"),
    approval_type: Literal["PLAN_APPROVAL", "STEP_APPROVAL", "ARTIFACT_APPROVAL"]
    | None = Query(default=None, alias="type"),
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(session_dependency),
) -> ApprovalCenterPage:
    _require_list_access(principal)
    statement = select(ApprovalRequest, Case).join(Case, Case.id == ApprovalRequest.case_id)
    if not principal.has_any(GLOBAL_CASE_READ_ROLES):
        statement = statement.where(Case.owner_subject == principal.subject)
    if approval_status:
        statement = statement.where(ApprovalRequest.status == approval_status)
    if approval_type:
        statement = statement.where(ApprovalRequest.approval_type == approval_type)
    rows = (
        await session.execute(statement.order_by(ApprovalRequest.created_at.desc()).limit(200))
    ).all()
    return ApprovalCenterPage(items=[_response(approval, case) for approval, case in rows])


@router.get("/{approval_id}", response_model=ApprovalCenterItem)
async def get_approval(
    approval_id: UUID,
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(session_dependency),
) -> ApprovalCenterItem:
    row = (
        await session.execute(
            select(ApprovalRequest, Case)
            .join(Case, Case.id == ApprovalRequest.case_id)
            .where(ApprovalRequest.id == str(approval_id))
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    approval, case = row
    _require_case_read(case, principal)
    return _response(approval, case)
