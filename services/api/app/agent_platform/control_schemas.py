from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ControlUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suspended: bool
    reason: str = Field(min_length=8, max_length=2_000)
    expected_revision: int | None = Field(default=None, ge=1)


class PlatformControlResponse(BaseModel):
    id: UUID
    control_key: str
    scope: Literal["GLOBAL", "AGENT"]
    agent_version_id: UUID | None
    suspended: bool
    reason: str
    revision: int
    updated_by: str
    updated_at: datetime


class PlatformControlPage(BaseModel):
    items: list[PlatformControlResponse]
