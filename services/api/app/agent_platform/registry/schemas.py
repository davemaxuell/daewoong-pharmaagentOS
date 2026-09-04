from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
ReleaseStatus = Literal[
    "DRAFT",
    "DEVELOPMENT",
    "TESTING",
    "STAGING",
    "APPROVED",
    "PRODUCTION",
    "SUSPENDED",
    "RETIRED",
]


class StrictRegistryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_default=True)


class WorkflowTemplateCreateRequest(StrictRegistryModel):
    workflow_key: str = Field(pattern=r"^[a-z][a-z0-9-]{1,159}$")
    version: str = Field(pattern=r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
    display_name: str = Field(min_length=1, max_length=255)
    manifest: dict[str, object]


class WorkflowTemplatePromotionRequest(StrictRegistryModel):
    target_status: Literal["APPROVED", "PRODUCTION", "SUSPENDED", "RETIRED"]
    reason: str = Field(min_length=1, max_length=2_000)


class WorkflowTemplateResponse(StrictRegistryModel):
    id: UUID
    workflow_key: str
    version: str
    display_name: str
    manifest: dict[str, object]
    manifest_sha256: Sha256
    release_status: ReleaseStatus
    created_by: str
    created_at: datetime


class WorkflowTemplatePage(StrictRegistryModel):
    items: list[WorkflowTemplateResponse]

