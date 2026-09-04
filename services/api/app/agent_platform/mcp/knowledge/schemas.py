from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class StrictToolModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_default=True)


class SearchAssetsArguments(StrictToolModel):
    query: str = Field(min_length=2, max_length=500)
    limit: int = Field(default=10, ge=1, le=20)
    include_obsolete: bool = False


class GetAssetArguments(StrictToolModel):
    asset_id: UUID


class GetDocumentVersionArguments(StrictToolModel):
    asset_version_id: UUID


class GetAnchorArguments(GetDocumentVersionArguments):
    anchor_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=256)


class KnowledgeRecord(StrictToolModel):
    asset_id: UUID
    asset_version_id: UUID | None
    asset_key: str = Field(min_length=1, max_length=160)
    asset_type: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=500)
    domain: str = Field(min_length=1, max_length=160)
    revision: int | None = Field(default=None, ge=1)
    status: str = Field(min_length=1, max_length=32)
    content: str | None = Field(default=None, max_length=40_000)
    content_sha256: Sha256 | None = None
    anchor_id: str | None = Field(default=None, min_length=1, max_length=256)
    excerpt: str | None = Field(default=None, max_length=4_000)
    relation_type: str | None = Field(default=None, min_length=1, max_length=80)
    score: float | None = Field(default=None, ge=0, le=1)


class KnowledgeProvenance(StrictToolModel):
    source_version_id: UUID
    source_hash: Sha256
    anchor_id: str | None = None


class KnowledgeData(StrictToolModel):
    resource_type: Literal[
        "SEARCH_RESULTS",
        "ASSET",
        "DOCUMENT_VERSION",
        "ANCHOR",
        "REVISION_HISTORY",
        "RELATED_ASSETS",
    ]
    records: list[KnowledgeRecord] = Field(max_length=20)
    acl_filtered_before_retrieval: Literal[True] = True


class KnowledgeSuccess(StrictToolModel):
    status: Literal["success"] = "success"
    request_id: UUID
    tool_name: str = Field(pattern=r"^knowledge\.[a-z][a-z0-9_]*$")
    tool_version: Literal["1.0.0"] = "1.0.0"
    data: KnowledgeData
    provenance: list[KnowledgeProvenance] = Field(max_length=100)
    warnings: list[str] = Field(max_length=20)


class KnowledgeErrorCode(StrEnum):
    INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    ACCESS_BLOCKED = "ACCESS_BLOCKED"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class KnowledgeError(StrictToolModel):
    code: KnowledgeErrorCode
    message: str = Field(min_length=1, max_length=1_000)
    retryable: bool = False


class KnowledgeErrorResult(StrictToolModel):
    status: Literal["error"] = "error"
    request_id: UUID
    tool_name: str = Field(pattern=r"^knowledge\.[a-z][a-z0-9_]*$")
    tool_version: Literal["1.0.0"] = "1.0.0"
    error: KnowledgeError
    next_valid_actions: list[str] = Field(max_length=10)
