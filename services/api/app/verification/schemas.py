from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class StrictVerificationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_default=True)


class VerificationIssue(StrictVerificationModel):
    severity: Literal["CRITICAL", "MAJOR", "MINOR"]
    code: str
    affected_claim: str
    reason: str
    supporting_evidence: list[str]
    required_correction: str
    responsible_agent: str


class VerificationCheck(StrictVerificationModel):
    check: str
    status: Literal["PASS", "FAIL"]
    detail: str


class VerificationReportResponse(StrictVerificationModel):
    id: UUID
    case_id: UUID
    run_id: UUID | None
    plan_id: UUID
    plan_version: int
    plan_sha256: Sha256
    bound_state_hash: Sha256
    input_sha256: Sha256
    correction_iteration: int = Field(ge=0, le=2)
    status: Literal["PASS", "REVISE", "BLOCK"]
    checks: list[VerificationCheck]
    issues: list[VerificationIssue]
    verified_hypothesis_ids: list[UUID]
    report_sha256: Sha256
    verifier_name: Literal["verification-agent"]
    verifier_version: Literal["1.2.1"]
    created_by: str
    created_at: datetime
    independent_context: Literal[True] = True


class ArtifactComposeRequest(StrictVerificationModel):
    title: str = Field(default="Regulatory Impact Review Package", min_length=1, max_length=300)
    assigned_reviewer_id: str | None = Field(default=None, min_length=1, max_length=255)


class ArtifactEvidenceResponse(StrictVerificationModel):
    id: UUID
    case_source_id: UUID
    document_version_id: UUID
    source_sha256: Sha256
    anchor: str
    excerpt_sha256: Sha256
    evidence_role: str


class ArtifactApprovalResponse(StrictVerificationModel):
    id: UUID
    status: str
    requested_by: str
    assigned_reviewer_id: str | None
    decision_by: str | None
    decision_reason: str | None
    decided_at: datetime | None
    expires_at: datetime


class ArtifactVersionResponse(StrictVerificationModel):
    id: UUID
    artifact_id: UUID
    case_id: UUID
    artifact_key: str
    artifact_type: str
    title: str
    version: int
    plan_id: UUID
    plan_version: int
    plan_sha256: Sha256
    bound_state_hash: Sha256
    run_id: UUID | None
    verification_report_id: UUID
    content_schema_version: str
    content: dict[str, object]
    content_sha256: Sha256
    evidence_manifest_sha256: Sha256
    status: Literal["DRAFT", "APPROVED", "REJECTED"]
    created_by: str
    created_at: datetime
    evidence: list[ArtifactEvidenceResponse]
    approval: ArtifactApprovalResponse


class ArtifactPageResponse(StrictVerificationModel):
    items: list[ArtifactVersionResponse]


class ArtifactDecisionRequest(StrictVerificationModel):
    decision: Literal["approve", "reject", "request_revision"]
    expected_content_sha256: Sha256
    expected_evidence_manifest_sha256: Sha256
    reason: str = Field(min_length=8, max_length=2_000)
