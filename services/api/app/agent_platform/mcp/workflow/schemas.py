from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InternalDraftArguments(StrictArguments):
    destination: str = Field(min_length=1, max_length=320)
    title: str = Field(min_length=3, max_length=300)
    body: str = Field(min_length=8, max_length=10_000)


class EmailDraftArguments(StrictArguments):
    destination: str = Field(
        min_length=3,
        max_length=320,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    title: str = Field(min_length=3, max_length=300)
    body: str = Field(min_length=8, max_length=10_000)


class CollaborationDraftArguments(InternalDraftArguments):
    platform: Literal["SLACK", "TEAMS"]


class TaskDraftArguments(InternalDraftArguments):
    system: Literal["NOTION", "TASK"]


class DocumentMetadataArguments(StrictArguments):
    asset_version_id: UUID
