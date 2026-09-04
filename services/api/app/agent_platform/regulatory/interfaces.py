"""Provider-neutral interfaces and typed outcomes for the regulatory agent boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal, Protocol
from uuid import UUID

from .contracts import ProcessLens, RegulatoryFindingList

AGENT_NAME = "regulatory-evidence-agent"
AGENT_VERSION = "1.3.0"
ANCHOR_TOOL_NAME = "regulatory.get_anchor"
ALLOWED_TOOL_NAMES = frozenset(
    {
        "regulatory.get_version",
        "regulatory.get_section",
        ANCHOR_TOOL_NAME,
        "regulatory.search_regulatory_references",
        "regulatory.compare_versions",
    }
)
MAX_TURNS = 8
MAX_TOOL_CALLS = 15
MAX_CORRECTION_LOOPS = 1


class ValidationCode(StrEnum):
    INVALID_CONTEXT = "INVALID_CONTEXT"
    POLICY_DENIED = "POLICY_DENIED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    UNKNOWN_FIELD = "UNKNOWN_FIELD"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    DUPLICATE_ANCHOR = "DUPLICATE_ANCHOR"
    UNPINNED_SOURCE = "UNPINNED_SOURCE"
    SOURCE_HASH_MISMATCH = "SOURCE_HASH_MISMATCH"
    UNRESOLVED_ANCHOR = "UNRESOLVED_ANCHOR"
    ANCHOR_SOURCE_MISMATCH = "ANCHOR_SOURCE_MISMATCH"
    EXCERPT_MISMATCH = "EXCERPT_MISMATCH"
    EXCERPT_HASH_MISMATCH = "EXCERPT_HASH_MISMATCH"
    DERIVATIVE_EVIDENCE = "DERIVATIVE_EVIDENCE"
    ACCESS_DENIED = "ACCESS_DENIED"
    UNCITED_CLAIM = "UNCITED_CLAIM"
    UNSUPPORTED_CLAIM = "UNSUPPORTED_CLAIM"
    PROHIBITED_CONCLUSION = "PROHIBITED_CONCLUSION"
    PROMPT_INJECTION = "PROMPT_INJECTION"
    TAXONOMY_VERSION_MISMATCH = "TAXONOMY_VERSION_MISMATCH"


@dataclass(frozen=True)
class ValidationIssue:
    code: ValidationCode
    path: str
    message: str


class RunFailureCode(StrEnum):
    INVALID_CONTEXT = "INVALID_CONTEXT"
    POLICY_DENIED = "POLICY_DENIED"
    MODEL_OUTPUT_ERROR = "MODEL_OUTPUT_ERROR"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    TOOL_FAILURE = "TOOL_FAILURE"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    CORRECTION_LIMIT_REACHED = "CORRECTION_LIMIT_REACHED"


@dataclass(frozen=True)
class SourcePin:
    source_version_id: UUID
    source_hash: str


@dataclass(frozen=True)
class RegulatoryRuntimeIdentity:
    user_id: str
    tenant_id: str
    case_id: str
    run_id: str
    idempotency_key: str
    runtime_service: str = "pharma-agent-runtime"
    agent_name: str = AGENT_NAME
    agent_version: str = AGENT_VERSION


@dataclass(frozen=True)
class RunLimits:
    max_turns: int = MAX_TURNS
    max_tool_calls: int = MAX_TOOL_CALLS
    max_correction_loops: int = MAX_CORRECTION_LOOPS


@dataclass(frozen=True)
class RegulatoryAgentContext:
    identity: RegulatoryRuntimeIdentity
    case_objective: str
    taxonomy_version: str
    source_pins: tuple[SourcePin, ...]
    requested_lenses: tuple[ProcessLens, ...] = ()
    allowed_tool_names: frozenset[str] = field(
        default_factory=lambda: frozenset({ANCHOR_TOOL_NAME})
    )
    limits: RunLimits = field(default_factory=RunLimits)


@dataclass(frozen=True)
class RegulatoryGenerationRequest:
    case_objective: str
    taxonomy_version: str
    source_pins: tuple[SourcePin, ...]
    requested_lenses: tuple[ProcessLens, ...]
    attempt: int
    validation_feedback: tuple[ValidationIssue, ...]


@dataclass(frozen=True)
class AnchorObservation:
    source_version_id: UUID
    source_hash: str
    anchor_id: str
    excerpt: str
    evidence_class: Literal["PRIMARY_AUTHORITATIVE", "DERIVATIVE"]
    access_allowed: bool = True


class RegulatoryModelOutputProducer(Protocol):
    """Generate only the documented JSON object; hidden reasoning is never accepted or returned."""

    async def produce(
        self,
        *,
        request: RegulatoryGenerationRequest,
    ) -> Mapping[str, object]: ...


class PreauthorizedRegulatoryTools(Protocol):
    """Narrow read-only view over a gateway that has already made its policy decision."""

    async def get_anchor(
        self,
        *,
        source_version_id: UUID,
        expected_source_hash: str,
        anchor_id: str,
        identity: RegulatoryRuntimeIdentity,
    ) -> AnchorObservation | None: ...


@dataclass(frozen=True)
class RegulatoryAgentSuccess:
    output: RegulatoryFindingList
    model_attempts: int
    correction_loops: int
    tool_calls: int
    status: Literal["success"] = field(init=False, default="success")


@dataclass(frozen=True)
class RegulatoryAgentFailure:
    code: RunFailureCode
    issues: tuple[ValidationIssue, ...]
    model_attempts: int
    correction_loops: int
    tool_calls: int
    retryable: bool
    status: Literal["failure"] = field(init=False, default="failure")


RegulatoryAgentResult = RegulatoryAgentSuccess | RegulatoryAgentFailure
