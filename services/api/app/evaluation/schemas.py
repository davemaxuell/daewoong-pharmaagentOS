from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
TargetKind = Literal["AGENT_VERSION", "WORKFLOW_VERSION"]


class StrictEvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_default=True)


class MetricGate(StrictEvaluationModel):
    metric: str = Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")
    operator: Literal["GTE", "LTE", "EQ"]
    threshold: float = Field(ge=0)


class EvaluationCaseInput(StrictEvaluationModel):
    case_key: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,159}$")
    title: str = Field(min_length=1, max_length=300)
    category: Literal["REGULATORY", "INTERNAL_RETRIEVAL", "END_TO_END", "SECURITY", "RESILIENCE"]
    input: dict[str, object]
    expected_outcome: dict[str, object]
    critical: bool = False
    synthetic: Literal[True] = True


class EvaluationSuiteCreateRequest(StrictEvaluationModel):
    suite_key: str = Field(pattern=r"^[a-z][a-z0-9-]{1,159}$")
    version: str = Field(pattern=r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=2_000)
    target_kind: TargetKind
    gates: list[MetricGate] = Field(min_length=1, max_length=30)
    cases: list[EvaluationCaseInput] = Field(min_length=1, max_length=500)


class EvaluationCaseResponse(EvaluationCaseInput):
    id: UUID
    case_sha256: Sha256
    created_at: datetime


class EvaluationSuiteResponse(StrictEvaluationModel):
    id: UUID
    suite_key: str
    version: str
    name: str
    description: str
    target_kind: TargetKind
    gates: list[MetricGate]
    suite_sha256: Sha256
    cases: list[EvaluationCaseResponse]
    created_by: str
    created_at: datetime


class EvaluationSuitePage(StrictEvaluationModel):
    items: list[EvaluationSuiteResponse]


class EvaluationRunRequest(StrictEvaluationModel):
    suite_id: UUID
    target_kind: TargetKind
    target_version_id: UUID
    baseline_version_id: UUID | None = None
    trial_count: int = Field(default=3, ge=3, le=20)


class EvaluationGradeResponse(StrictEvaluationModel):
    grader_type: Literal["DETERMINISTIC", "MODEL", "HUMAN"]
    metric: str
    score: float = Field(ge=0, le=1)
    passed: bool
    critical: bool
    rationale: str
    evidence: dict[str, object]
    graded_by: str


class EvaluationTrialResponse(StrictEvaluationModel):
    id: UUID
    evaluation_case_id: UUID
    trial_number: int
    status: Literal["PASSED", "FAILED"]
    trajectory: list[dict[str, object]]
    final_state: dict[str, object]
    output_sha256: Sha256
    token_count: int
    cost_usd: float
    latency_ms: int
    error_code: str | None
    grades: list[EvaluationGradeResponse]


class EvaluationRunResponse(StrictEvaluationModel):
    id: UUID
    suite_id: UUID
    target_kind: TargetKind
    target_version_id: UUID
    target_sha256: Sha256
    baseline_version_id: UUID | None
    trial_count: int
    status: Literal["PENDING", "RUNNING", "PASSED", "FAILED"]
    metrics: dict[str, object]
    total_trials: int
    passed_trials: int
    critical_failures: int
    total_cost_usd: float
    total_latency_ms: int
    requested_by: str
    started_at: datetime
    completed_at: datetime | None
    trials: list[EvaluationTrialResponse]


class EvaluationRunPage(StrictEvaluationModel):
    items: list[EvaluationRunResponse]


class HumanGradeRequest(StrictEvaluationModel):
    metric: str = Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")
    score: float = Field(ge=0, le=1)
    passed: bool
    critical: bool = False
    rationale: str = Field(min_length=8, max_length=2_000)
    evidence: dict[str, object] = Field(default_factory=dict)


class ReleaseDecisionRequest(StrictEvaluationModel):
    decision: Literal["approve", "reject"]
    target_status: Literal["STAGING", "PRODUCTION"]
    expected_target_sha256: Sha256
    reason: str = Field(min_length=8, max_length=2_000)


class ReleaseDecisionResponse(StrictEvaluationModel):
    id: UUID
    evaluation_run_id: UUID
    target_kind: TargetKind
    target_version_id: UUID
    target_sha256: Sha256
    target_status: Literal["STAGING", "PRODUCTION"]
    decision: Literal["APPROVED", "REJECTED"]
    rollback_target_id: UUID | None
    decided_by: str
    reason: str
    decided_at: datetime


class EvaluationComparisonResponse(StrictEvaluationModel):
    candidate_run_id: UUID
    baseline_run_id: UUID
    metric_deltas: dict[str, float]
    regression_metrics: list[str]
    release_blocked: bool


class FeedbackRequest(StrictEvaluationModel):
    case_id: UUID | None = None
    run_id: UUID | None = None
    artifact_version_id: UUID | None = None
    agent_version_id: UUID | None = None
    signal_type: Literal[
        "APPROVAL",
        "REJECTION",
        "EDIT",
        "INTERRUPTION",
        "UNRESOLVED_QUESTION",
        "TOOL_FAILURE",
        "NEGATIVE_FEEDBACK",
        "INCIDENT",
    ]
    payload: dict[str, object]

    @model_validator(mode="after")
    def require_link(self) -> FeedbackRequest:
        if not any((self.case_id, self.run_id, self.artifact_version_id, self.agent_version_id)):
            raise ValueError("At least one attributable production record is required")
        return self


class FeedbackResponse(StrictEvaluationModel):
    id: UUID
    signal_type: str
    payload_sha256: Sha256
    submitted_by: str
    created_at: datetime


class ControlTowerSummary(StrictEvaluationModel):
    inventory: dict[str, int]
    operational_health: dict[str, int | float]
    quality: dict[str, int | float]
    security: dict[str, int | float]
    cost_performance: dict[str, int | float]
    business_value: dict[str, int | float]
    generated_at: datetime


class InventoryItem(StrictEvaluationModel):
    id: UUID
    kind: Literal["AGENT_VERSION", "SKILL_VERSION", "TOOL_VERSION", "WORKFLOW_VERSION"]
    key: str
    version: str
    sha256: Sha256
    release_status: str


class InventoryResponse(StrictEvaluationModel):
    items: list[InventoryItem]


class TraceResponse(StrictEvaluationModel):
    run_id: UUID
    case_id: UUID
    status: str
    trace: list[dict[str, object]]
