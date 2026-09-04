from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
AnchorId = Annotated[
    str,
    Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=256),
]
ToolName = Annotated[str, Field(pattern=r"^regulatory\.[a-z][a-z0-9_]*$")]
SemVer = Annotated[str, Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")]


class StrictToolModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_default=True)


class GetVersionArguments(StrictToolModel):
    document_version_id: UUID
    expected_source_hash: Sha256


class GetSectionArguments(GetVersionArguments):
    section_path: list[Annotated[str, Field(min_length=1, max_length=300)]] = Field(
        min_length=1, max_length=20
    )


class GetAnchorArguments(GetVersionArguments):
    anchor_id: AnchorId


class CompareVersionsArguments(StrictToolModel):
    from_document_version_id: UUID
    from_source_hash: Sha256
    to_document_version_id: UUID
    to_source_hash: Sha256


class SourceReference(StrictToolModel):
    document_version_id: UUID
    expected_source_hash: Sha256


class SearchRegulatoryReferencesArguments(StrictToolModel):
    sources: list[SourceReference] = Field(min_length=1, max_length=20)
    query: str = Field(min_length=2, max_length=500)
    limit: Annotated[int, Field(strict=True, ge=1, le=20)]

    @model_validator(mode="after")
    def sources_are_unique(self) -> SearchRegulatoryReferencesArguments:
        identities = [str(source.document_version_id) for source in self.sources]
        if len(identities) != len(set(identities)):
            raise ValueError("sources must contain unique document_version_id values")
        return self


class Provenance(StrictToolModel):
    source_version_id: str = Field(min_length=1, max_length=256)
    source_hash: Sha256
    anchor_id: str | None = Field(default=None, min_length=1, max_length=256)


class ErrorCode(StrEnum):
    INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    SOURCE_NOT_PINNED = "SOURCE_NOT_PINNED"
    SOURCE_HASH_MISMATCH = "SOURCE_HASH_MISMATCH"
    NOT_FOUND = "NOT_FOUND"
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    CONFLICT = "CONFLICT"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ToolError(StrictToolModel):
    code: ErrorCode
    message: str = Field(min_length=1, max_length=1000)
    retryable: bool


class ErrorResult(StrictToolModel):
    status: Literal["error"] = "error"
    request_id: UUID
    tool_name: ToolName
    tool_version: SemVer
    error: ToolError
    next_valid_actions: list[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")]] = Field(
        max_length=10
    )


class GetVersionData(StrictToolModel):
    document_version_id: UUID
    document_id: UUID
    version_number: Annotated[int, Field(strict=True, ge=1)]
    source_hash: Sha256
    source_url: str = Field(
        pattern=r"^https://([A-Za-z0-9-]+\.)*fda\.gov/",
        max_length=2048,
    )
    retrieved_at: datetime


class GetVersionSuccess(StrictToolModel):
    status: Literal["success"] = "success"
    request_id: UUID
    tool_name: Literal["regulatory.get_version"]
    tool_version: Literal["1.0.0"]
    data: GetVersionData
    provenance: list[Provenance] = Field(min_length=1, max_length=20)
    warnings: list[Annotated[str, Field(max_length=500)]] = Field(max_length=20)


class GetSectionData(StrictToolModel):
    document_version_id: UUID
    source_hash: Sha256
    section_path: list[Annotated[str, Field(min_length=1, max_length=300)]] = Field(
        min_length=1, max_length=20
    )
    text: str = Field(min_length=1, max_length=40000)
    anchor_ids: list[Annotated[str, Field(min_length=1, max_length=256)]] = Field(
        min_length=1, max_length=100
    )

    @model_validator(mode="after")
    def anchor_ids_are_unique(self) -> GetSectionData:
        if len(self.anchor_ids) != len(set(self.anchor_ids)):
            raise ValueError("anchor_ids must be unique")
        return self


class GetSectionSuccess(StrictToolModel):
    status: Literal["success"] = "success"
    request_id: UUID
    tool_name: Literal["regulatory.get_section"]
    tool_version: Literal["1.0.0"]
    data: GetSectionData
    provenance: list[Provenance] = Field(min_length=1, max_length=100)
    warnings: list[Annotated[str, Field(max_length=500)]] = Field(max_length=20)


class GetAnchorData(StrictToolModel):
    document_version_id: UUID
    source_hash: Sha256
    anchor_id: str = Field(min_length=1, max_length=256)
    section_path: list[Annotated[str, Field(min_length=1, max_length=300)]] = Field(max_length=20)
    excerpt: str = Field(min_length=1, max_length=4000)


class GetAnchorSuccess(StrictToolModel):
    status: Literal["success"] = "success"
    request_id: UUID
    tool_name: Literal["regulatory.get_anchor"]
    tool_version: Literal["1.0.0"]
    data: GetAnchorData
    provenance: list[Provenance] = Field(min_length=1, max_length=1)
    warnings: list[Annotated[str, Field(max_length=500)]] = Field(max_length=20)


class VersionChange(StrictToolModel):
    change_type: Literal["ADDED", "REMOVED", "MODIFIED"]
    anchor_id: str = Field(min_length=1, max_length=256)
    before_excerpt: str | None = Field(default=None, max_length=4000)
    after_excerpt: str | None = Field(default=None, max_length=4000)


class CompareVersionsData(StrictToolModel):
    from_document_version_id: UUID
    from_source_hash: Sha256
    to_document_version_id: UUID
    to_source_hash: Sha256
    changes: list[VersionChange] = Field(max_length=100)


class CompareVersionsSuccess(StrictToolModel):
    status: Literal["success"] = "success"
    request_id: UUID
    tool_name: Literal["regulatory.compare_versions"]
    tool_version: Literal["1.0.0"]
    data: CompareVersionsData
    provenance: list[Provenance] = Field(min_length=2, max_length=100)
    warnings: list[Annotated[str, Field(max_length=500)]] = Field(max_length=20)


class RegulatoryReference(StrictToolModel):
    reference: str = Field(min_length=1, max_length=500)
    citation_text: str = Field(min_length=1, max_length=4000)
    document_version_id: UUID
    source_hash: Sha256
    anchor_id: str = Field(min_length=1, max_length=256)


class SearchRegulatoryReferencesData(StrictToolModel):
    items: list[RegulatoryReference] = Field(max_length=20)
    next_cursor: str | None = Field(default=None, min_length=1, max_length=512)


class SearchRegulatoryReferencesSuccess(StrictToolModel):
    status: Literal["success"] = "success"
    request_id: UUID
    tool_name: Literal["regulatory.search_regulatory_references"]
    tool_version: Literal["1.0.0"]
    data: SearchRegulatoryReferencesData
    provenance: list[Provenance] = Field(max_length=20)
    warnings: list[Annotated[str, Field(max_length=500)]] = Field(max_length=20)
