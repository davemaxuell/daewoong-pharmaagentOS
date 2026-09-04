from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
WorkflowKey = Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{1,159}$")]
StepKey = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")]


class StrictCaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_default=True)


class CaseCreateRequest(StrictCaseModel):
    title: str = Field(min_length=1, max_length=300)
    objective: str = Field(min_length=1, max_length=4_000)
    workflow_key: WorkflowKey = "regulatory-impact-review"
    warning_letter_id: UUID
    document_version_id: UUID
    source_role: Literal["PRIMARY_REGULATORY", "SUPPORTING_REGULATORY"] = "PRIMARY_REGULATORY"


class CaseSourceResponse(StrictCaseModel):
    id: UUID
    case_id: UUID
    warning_letter_id: UUID
    document_id: UUID
    document_version_id: UUID
    document_version_number: int
    source_role: str
    source_sha256: Sha256
    source_url: str
    pinned_by: str
    created_at: datetime
    immutable: Literal[True] = True


class CaseResponse(StrictCaseModel):
    id: UUID
    title: str
    objective: str
    status: str
    owner_subject: str
    workflow_key: str
    current_state_hash: Sha256
    sources: list[CaseSourceResponse]
    created_at: datetime
    updated_at: datetime


class CasePage(StrictCaseModel):
    items: list[CaseResponse]
    next_cursor: str | None
    has_more: bool


class StepLimits(StrictCaseModel):
    max_turns: int = Field(default=5, ge=1, le=100)
    max_tool_calls: int = Field(default=20, ge=0, le=500)
    max_input_tokens: int = Field(default=100_000, ge=1, le=2_000_000)
    max_output_tokens: int = Field(default=20_000, ge=1, le=200_000)
    max_runtime_seconds: int = Field(default=300, ge=1, le=86_400)
    max_cost_usd: float = Field(default=5.0, ge=0, le=10_000)


class PlanStepCreate(StrictCaseModel):
    step_key: StepKey
    title: str = Field(min_length=1, max_length=300)
    instructions: str = Field(min_length=1, max_length=4_000)
    depends_on: list[StepKey] = Field(default_factory=list, max_length=20)
    agent_version_id: UUID | None = None
    skill_version_ids: list[UUID] = Field(default_factory=list, max_length=20)
    tool_version_ids: list[UUID] = Field(default_factory=list, max_length=30)
    output_schema_ref: str = Field(min_length=1, max_length=255)
    risk_level: Literal["R0", "R1", "R2", "R3"]
    requires_approval: bool = False
    limits: StepLimits = Field(default_factory=StepLimits)

    @model_validator(mode="after")
    def unique_version_references(self) -> PlanStepCreate:
        if len(set(self.depends_on)) != len(self.depends_on):
            raise ValueError("depends_on entries must be unique")
        if len(set(self.skill_version_ids)) != len(self.skill_version_ids):
            raise ValueError("skill_version_ids entries must be unique")
        if len(set(self.tool_version_ids)) != len(self.tool_version_ids):
            raise ValueError("tool_version_ids entries must be unique")
        return self


class CasePlanCreateRequest(StrictCaseModel):
    objective: str | None = Field(default=None, min_length=1, max_length=4_000)
    plan_schema_version: Literal["1.0.0"] = "1.0.0"
    steps: list[PlanStepCreate] = Field(min_length=1, max_length=100)
    assigned_reviewer_id: str | None = Field(default=None, min_length=1, max_length=255)

    @model_validator(mode="after")
    def valid_step_graph(self) -> CasePlanCreateRequest:
        keys = [step.step_key for step in self.steps]
        if len(set(keys)) != len(keys):
            raise ValueError("step_key values must be unique")
        prior: set[str] = set()
        for step in self.steps:
            unknown_or_forward = set(step.depends_on) - prior
            if unknown_or_forward:
                values = ", ".join(sorted(unknown_or_forward))
                raise ValueError(f"depends_on must reference preceding steps: {values}")
            prior.add(step.step_key)
        return self


class PlanStepResponse(StrictCaseModel):
    id: UUID
    position: int
    step_key: str
    title: str
    instructions: str
    depends_on: list[str]
    agent_version_id: UUID | None
    skill_version_ids: list[UUID]
    tool_version_ids: list[UUID]
    output_schema_ref: str
    risk_level: str
    requires_approval: bool
    limits: StepLimits
    created_at: datetime


class ApprovalResponse(StrictCaseModel):
    id: UUID
    approval_type: str
    status: str
    requested_by: str
    assigned_reviewer_id: str | None
    decision_by: str | None
    decision_reason: str | None
    decided_at: datetime | None
    expires_at: datetime
    plan_sha256: Sha256
    bound_state_hash: Sha256
    created_at: datetime


class CasePlanResponse(StrictCaseModel):
    id: UUID
    case_id: UUID
    version: int
    objective: str
    plan_schema_version: str
    plan_sha256: Sha256
    based_on_state_hash: Sha256
    workflow_template_version_id: UUID | None
    prohibited_actions: list[str]
    created_by: str
    created_at: datetime
    steps: list[PlanStepResponse]
    approval: ApprovalResponse


class PlanDecisionRequest(StrictCaseModel):
    decision: Literal["approve", "reject"]
    expected_plan_sha256: Sha256
    expected_state_hash: Sha256
    reason: str = Field(min_length=1, max_length=2_000)


class CaseEventResponse(StrictCaseModel):
    id: UUID
    case_id: UUID
    sequence: int
    event_type: str
    actor_type: str
    actor_id: str
    request_id: str
    payload: dict[str, object]
    previous_event_hash: Sha256 | None
    event_hash: Sha256
    state_hash: Sha256
    occurred_at: datetime


class CaseEventPage(StrictCaseModel):
    items: list[CaseEventResponse]
    next_cursor: str | None
    has_more: bool
