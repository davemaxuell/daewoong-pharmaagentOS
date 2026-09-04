from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
RunStatus = Literal[
    "PENDING",
    "RUNNING",
    "PAUSED",
    "WAITING_FOR_APPROVAL",
    "COMPLETED",
    "BLOCKED",
    "FAILED",
    "CANCELLED",
]
InvocationStatus = Literal[
    "PENDING",
    "RUNNING",
    "WAITING_FOR_APPROVAL",
    "COMPLETED",
    "BLOCKED",
    "FAILED",
    "CANCELLED",
]


class StrictRuntimeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_default=True)


class RunStartRequest(StrictRuntimeModel):
    plan_version: int = Field(ge=1)
    expected_plan_sha256: Sha256
    expected_state_hash: Sha256


class RunControlRequest(StrictRuntimeModel):
    reason: str = Field(min_length=1, max_length=2_000)


class InvocationUsage(StrictRuntimeModel):
    turns: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    runtime_seconds: float = Field(default=0, ge=0)
    cost_usd: float = Field(default=0, ge=0)


class StepResultRequest(StrictRuntimeModel):
    expected_invocation_id: UUID
    output: dict[str, object]
    usage: InvocationUsage = Field(default_factory=InvocationUsage)


class StepApprovalDecisionRequest(StrictRuntimeModel):
    decision: Literal["approve", "reject"]
    expected_approval_id: UUID
    reason: str = Field(min_length=1, max_length=2_000)


class WorkflowBindingResponse(StrictRuntimeModel):
    id: UUID
    workflow_key: str
    version: str
    manifest_sha256: Sha256


class RunStepStateResponse(StrictRuntimeModel):
    status: InvocationStatus
    attempt: int
    invocation_id: UUID | None
    approval_id: UUID | None
    output_sha256: Sha256 | None
    usage: InvocationUsage


class RunCheckpointResponse(StrictRuntimeModel):
    schema_version: Literal["pharmaagent-run-state@1.0.0"]
    checkpoint_version: int
    step_key: str | None
    workflow_template: WorkflowBindingResponse
    steps: dict[str, RunStepStateResponse]
    budget: InvocationUsage
    pause_requested: bool
    cancel_requested: bool


class AgentInvocationResponse(StrictRuntimeModel):
    id: UUID
    run_id: UUID
    case_id: UUID
    plan_step_id: UUID
    step_key: str
    attempt: int
    agent_version_id: UUID | None
    status: InvocationStatus
    output_schema_ref: str
    input_sha256: Sha256
    output_sha256: Sha256 | None
    limits: dict[str, object]
    usage: InvocationUsage
    error_code: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class CaseRunResponse(StrictRuntimeModel):
    id: UUID
    case_id: UUID
    plan_id: UUID
    plan_version: int
    plan_sha256: Sha256
    bound_state_hash: Sha256
    status: RunStatus
    requested_by: str
    checkpoint: RunCheckpointResponse
    active_invocation: AgentInvocationResponse | None
    error_code: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class RunEventResponse(StrictRuntimeModel):
    id: UUID
    run_id: UUID
    case_id: UUID
    sequence: int
    event_type: str
    actor_type: str
    actor_id: str
    request_id: str
    payload: dict[str, object]
    previous_event_hash: Sha256 | None
    event_hash: Sha256
    occurred_at: datetime


class RunEventPage(StrictRuntimeModel):
    items: list[RunEventResponse]
    next_cursor: str | None
    has_more: bool

