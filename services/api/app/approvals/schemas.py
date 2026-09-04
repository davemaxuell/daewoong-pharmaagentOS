from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApprovalCenterItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    case_id: UUID
    case_title: str
    plan_id: UUID
    plan_version: int
    plan_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    bound_state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    run_id: UUID | None
    step_key: str | None
    artifact_version_id: UUID | None
    approval_type: Literal["PLAN_APPROVAL", "STEP_APPROVAL", "ARTIFACT_APPROVAL"]
    status: Literal["PENDING", "APPROVED", "REJECTED", "CANCELLED", "EXPIRED"]
    requested_by: str
    assigned_reviewer_id: str | None
    decision_by: str | None
    decision_reason: str | None
    decided_at: datetime | None
    expires_at: datetime
    expired: bool
    created_at: datetime


class ApprovalCenterPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ApprovalCenterItem]
