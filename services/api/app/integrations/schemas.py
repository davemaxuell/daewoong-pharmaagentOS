from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DraftCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: Literal["INTERNAL", "EMAIL", "SLACK", "TEAMS", "NOTION", "TASK"]
    destination: str = Field(min_length=1, max_length=320)
    title: str = Field(min_length=3, max_length=300)
    body: str = Field(min_length=8, max_length=10_000)
    run_id: UUID | None = None


class DraftReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["review_for_manual_use", "cancel"]
    expected_content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: str = Field(min_length=8, max_length=2_000)


class IntegrationDraftResponse(BaseModel):
    id: UUID
    case_id: UUID
    run_id: UUID | None
    channel: str
    action: Literal["CREATE_DRAFT"]
    destination: str
    content: dict
    content_sha256: str
    status: Literal["DRAFT", "REVIEWED_FOR_MANUAL_USE", "CANCELLED"]
    external_delivery_allowed: Literal[False]
    requested_by: str
    reviewed_by: str | None
    review_reason: str | None
    reviewed_at: datetime | None
    created_at: datetime


class IntegrationDraftPage(BaseModel):
    items: list[IntegrationDraftResponse]


class DocumentMetadataResponse(BaseModel):
    asset_id: UUID
    asset_version_id: UUID
    asset_key: str
    title: str
    asset_type: str
    domain: str
    revision: int
    effective_date: str | None
    status: str
    content_sha256: str
    access_filtered: Literal[True] = True
    integration_mode: Literal["READ_ONLY"] = "READ_ONLY"


class A2ATaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_key: str = Field(min_length=16, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    case_id: UUID
    intent: Literal["CASE_STATUS", "APPROVED_ARTIFACT_METADATA"]
    delegated_subject: str = Field(min_length=1, max_length=255)
    delegated_roles: list[str] = Field(min_length=1, max_length=10)


class A2ATaskResponse(BaseModel):
    id: UUID
    task_key: str
    case_id: UUID
    intent: str
    status: Literal["COMPLETED"]
    response: dict
    request_sha256: str
    response_sha256: str
    answer_only: Literal[True] = True
    tool_delegation_allowed: Literal[False] = False
    created_at: datetime
