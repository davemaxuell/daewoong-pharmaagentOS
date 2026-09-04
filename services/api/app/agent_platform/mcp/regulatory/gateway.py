from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_platform.controls import active_suspension
from app.agent_platform.mcp.regulatory.context import HostInvocationContext
from app.agent_platform.mcp.regulatory.manifest import ToolManifest, load_regulatory_tool_bundle
from app.agent_platform.mcp.regulatory.sanitization import sanitize_untrusted_content
from app.agent_platform.mcp.regulatory.schemas import (
    CompareVersionsArguments,
    CompareVersionsSuccess,
    ErrorCode,
    ErrorResult,
    GetAnchorArguments,
    GetAnchorSuccess,
    GetSectionArguments,
    GetSectionSuccess,
    GetVersionArguments,
    GetVersionSuccess,
    SearchRegulatoryReferencesArguments,
    SearchRegulatoryReferencesSuccess,
)
from app.audit import add_audit_event
from app.cases.hashing import case_state_sha256
from app.models import (
    AgentRunStatus,
    AgentVersion,
    ApprovalRequest,
    ApprovalStatus,
    Case,
    CasePlan,
    CasePlanStep,
    CaseRun,
    CaseSource,
    DocumentVersion,
    PolicyDecision,
    ToolInvocation,
    ToolVersion,
)
from app.parsing import extract_regulatory_references
from app.security.auth import Principal

REGULATORY_AGENT_NAME = "regulatory-evidence-agent"
REGULATORY_AGENT_VERSION = "1.3.0"
REGULATORY_AGENT_MANIFEST_SHA256 = (
    "5b19303a147b12c07533523127a58577ff7fe5d27a19413443d7f32a5d775daa"
)
REGULATORY_RUNTIME_SERVICE = "pharma-agent-runtime"
AGENT_MAX_TOOL_CALLS = 15
EXECUTABLE_RELEASE_STATES = frozenset({"APPROVED", "PRODUCTION"})
ANCHOR_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FDA_SOURCE_URL_PATTERN = re.compile(r"^https://(?:[A-Za-z0-9-]+\.)*fda\.gov/")
SECTION_AGGREGATE_CHARACTER_LIMIT = 12000
REGULATORY_INVOCATION_POLICY_KEY = "regulatory-mcp-invocation"
REGULATORY_INVOCATION_POLICY_VERSION = "1.0.0"
RATE_LIMIT_AGGREGATE_CHECKPOINT_KEY = "regulatory_mcp_rate_limit"
RATE_LIMIT_AGGREGATE_SCHEMA_VERSION = "1.0.0"
RATE_LIMIT_RECENT_ATTEMPT_LIMIT = 20
RATE_LIMIT_BUCKET_LIMIT = 20
REGULATORY_INVOCATION_POLICY_DEFINITION = {
    "policy_key": REGULATORY_INVOCATION_POLICY_KEY,
    "policy_version": REGULATORY_INVOCATION_POLICY_VERSION,
    "default": "DENY",
    "controls": [
        "authenticated_runtime",
        "current_case_owner",
        "unexpired_exact_plan_approval",
        "active_run_checkpoint_step",
        "reviewed_agent_and_tool_digests",
        "exact_case_source_pins",
        "persisted_run_tool_budget",
    ],
}

ARGUMENT_MODELS: dict[str, type[BaseModel]] = {
    "regulatory.get_version": GetVersionArguments,
    "regulatory.get_section": GetSectionArguments,
    "regulatory.get_anchor": GetAnchorArguments,
    "regulatory.compare_versions": CompareVersionsArguments,
    "regulatory.search_regulatory_references": SearchRegulatoryReferencesArguments,
}
SUCCESS_MODELS: dict[str, type[BaseModel]] = {
    "regulatory.get_version": GetVersionSuccess,
    "regulatory.get_section": GetSectionSuccess,
    "regulatory.get_anchor": GetAnchorSuccess,
    "regulatory.compare_versions": CompareVersionsSuccess,
    "regulatory.search_regulatory_references": SearchRegulatoryReferencesSuccess,
}


class InvocationFailure(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        next_valid_actions: tuple[str, ...],
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.next_valid_actions = next_valid_actions
        self.retryable = retryable


class AttributionCommitError(RuntimeError):
    """The gateway withheld a result because durable attribution did not commit."""


class RetryAuthorizationFailure(RuntimeError):
    """A fresh authorization check blocked a subsequent execution attempt."""

    def __init__(self, error: Exception) -> None:
        super().__init__("retry authorization could not be confirmed")
        self.error = error


@dataclass(frozen=True)
class AuthorizedInvocation:
    versions: dict[str, DocumentVersion]
    policy_tool_call_limit: int
    approval: ApprovalRequest
    plan: CasePlan
    run: CaseRun
    active_step: CasePlanStep
    agent_version: AgentVersion
    tool_version: ToolVersion


@dataclass(frozen=True)
class PredispatchDecision:
    id: str
    request_id: str
    effect: str
    input_sha256: str
    decision_sha256: str


_EXECUTION_DEADLINE: ContextVar[float | None] = ContextVar(
    "regulatory_mcp_execution_deadline",
    default=None,
)


def _check_execution_deadline() -> None:
    deadline = _EXECUTION_DEADLINE.get()
    if deadline is not None and monotonic() >= deadline:
        raise TimeoutError("regulatory MCP cooperative execution deadline exceeded")


def _canonical_hash(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            default=str,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError):
        encoded = repr(type(value)).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _reviewed_manifest_matches(payload: object, expected_hash: str) -> bool:
    """Verify a stored full contract using the checked-in definition-hash semantics."""

    if not isinstance(payload, Mapping):
        return False
    metadata = payload.get("metadata")
    if not isinstance(metadata, Mapping) or metadata.get("definitionHash") != expected_hash:
        return False
    canonical = dict(payload)
    canonical_metadata = dict(metadata)
    canonical_metadata.pop("definitionHash", None)
    canonical["metadata"] = canonical_metadata
    return _canonical_hash(canonical) == expected_hash


def _result_size(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


def _aware_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _append_warning(result: dict[str, Any], warning: str) -> None:
    warnings = result.setdefault("warnings", [])
    if warning not in warnings and len(warnings) < 20:
        warnings.append(warning)


def _source_references(arguments: BaseModel) -> list[tuple[str, str]]:
    if isinstance(arguments, (GetVersionArguments, GetSectionArguments, GetAnchorArguments)):
        return [(str(arguments.document_version_id), arguments.expected_source_hash)]
    if isinstance(arguments, CompareVersionsArguments):
        return [
            (str(arguments.from_document_version_id), arguments.from_source_hash),
            (str(arguments.to_document_version_id), arguments.to_source_hash),
        ]
    if isinstance(arguments, SearchRegulatoryReferencesArguments):
        return [
            (str(source.document_version_id), source.expected_source_hash)
            for source in arguments.sources
        ]
    raise TypeError(f"Unsupported argument model: {type(arguments)!r}")


class RegulatoryMcpGateway:
    """One deny-by-default gateway for all in-process regulatory MCP calls."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._bundle = load_regulatory_tool_bundle()
        contract_tools = set(self._bundle.tools)
        if contract_tools != set(ARGUMENT_MODELS) or contract_tools != set(SUCCESS_MODELS):
            raise RuntimeError("regulatory MCP implementation and checked-in contract have drifted")

    async def invoke(
        self,
        *,
        tool_name: str,
        arguments: Mapping[str, object] | object,
        context: HostInvocationContext,
    ) -> dict[str, Any]:
        """Execute one recoverable, durably attributed invocation.

        Phase one authorizes under database locks, reserves the durable run budget,
        and commits an exact pre-dispatch ``PolicyDecision``. Phase two reauthorizes,
        then releases all database locks before bounded execution. Phase three obtains
        fresh locks after execution and atomically commits the final observation and
        metadata audit before the result is returned.

        A same-key retry can reuse an exact orphaned pre-dispatch decision after a
        process crash or final-attribution failure without charging the budget twice.
        Callers must enter with no unrelated pending writes in ``session``.
        """

        if (
            self._session.in_transaction()
            or self._session.new
            or self._session.dirty
            or self._session.deleted
        ):
            raise RuntimeError(
                "Regulatory MCP requires a clean caller session before its transaction boundary."
            )

        started = monotonic()
        started_at = _utcnow()
        request_id = uuid4()
        manifest = self._bundle.tools.get(tool_name)
        public_tool_name = (
            tool_name
            if re.fullmatch(r"regulatory\.[a-z][a-z0-9_]*", tool_name)
            else "regulatory.unknown"
        )
        tool_version = manifest.version if manifest is not None else self._bundle.version
        validated_arguments: BaseModel | None = None

        try:
            if manifest is None:
                raise InvocationFailure(
                    ErrorCode.PERMISSION_DENIED,
                    "Tool is not available to this agent.",
                    next_valid_actions=("use_allowlisted_tool",),
                )
            self._validate_runtime_identity(context)
            self._validate_agent_identity(context)
            try:
                validated_arguments = ARGUMENT_MODELS[tool_name].model_validate(arguments)
            except ValidationError as exc:
                raise InvocationFailure(
                    ErrorCode.INVALID_ARGUMENTS,
                    "Tool arguments do not match the approved contract.",
                    next_valid_actions=("correct_arguments",),
                ) from exc
            if manifest.required_scope not in context.scopes:
                raise InvocationFailure(
                    ErrorCode.PERMISSION_DENIED,
                    "The active runtime grant does not include the required tool scope.",
                    next_valid_actions=("request_authorization",),
                )

            argument_payload = validated_arguments.model_dump(mode="json")
            arguments_hash = _canonical_hash(argument_payload)
            source_refs = _source_references(validated_arguments)
            access = await self._authorize_case_plan_and_sources(
                context=context,
                manifest=manifest,
                arguments=validated_arguments,
            )

            existing = await self._existing_invocation(context=context, access=access)
            if existing is not None:
                existing_policy = await self._policy_for_invocation(existing)
                if not self._is_exact_replay(
                    invocation=existing,
                    policy=existing_policy,
                    context=context,
                    access=access,
                    manifest=manifest,
                    arguments_hash=arguments_hash,
                ):
                    raise InvocationFailure(
                        ErrorCode.CONFLICT,
                        "The run idempotency key is already bound to a different tool call.",
                        next_valid_actions=("use_new_idempotency_key", "inspect_run_trace"),
                    )
                result = self._validated_stored_result(existing, manifest=manifest)
                await self._synchronize_context_budget(context=context, run=access.run)
                await self._commit_replay_without_new_audit()
                return result

            policy = await self._existing_policy_decision(context=context)
            if policy is not None:
                if not self._policy_matches_call(
                    policy=policy,
                    context=context,
                    access=access,
                    manifest=manifest,
                    arguments_hash=arguments_hash,
                ):
                    raise InvocationFailure(
                        ErrorCode.CONFLICT,
                        "The run idempotency key is already bound to different arguments.",
                        next_valid_actions=("use_new_idempotency_key", "inspect_run_trace"),
                    )
                request_id = UUID(policy.request_id)
                await self._synchronize_context_budget(context=context, run=access.run)
            else:
                budget_reserved = await self._reserve_persisted_budget(
                    context=context,
                    access=access,
                )
                if not budget_reserved:
                    cached_denial = await self._existing_budget_denial(
                        context=context,
                        access=access,
                        manifest=manifest,
                    )
                    if cached_denial is not None:
                        invocation, _canonical_result = cached_denial
                        return await self._persist_aggregated_budget_denial(
                            context=context,
                            access=access,
                            manifest=manifest,
                            arguments_hash=arguments_hash,
                            canonical_denial=invocation,
                        )
                policy_effect = "ALLOW" if budget_reserved else "DENY"
                policy = self._new_policy_decision(
                    context=context,
                    access=access,
                    manifest=manifest,
                    arguments_sha256=arguments_hash,
                    effect=policy_effect,
                    request_id=request_id,
                )
                self._session.add(policy)

            try:
                # Commits both a new budget reservation and its exact decision, or
                # closes the read transaction around a recovered decision.
                await self._session.commit()
            except Exception as exc:
                await self._session.rollback()
                raise AttributionCommitError(
                    "Regulatory MCP pre-dispatch decision could not be committed; "
                    "dispatch and result withheld."
                ) from exc
            binding = self._predispatch_binding(policy)
        except AttributionCommitError:
            raise
        except InvocationFailure as exc:
            result = self._error_result(
                request_id=request_id,
                tool_name=public_tool_name,
                tool_version=tool_version,
                failure=exc,
            )
            await self._persist_result(
                context=context,
                public_tool_name=public_tool_name,
                tool_version=tool_version,
                arguments=(
                    validated_arguments.model_dump(mode="json")
                    if validated_arguments is not None
                    else arguments
                ),
                source_references=(
                    _source_references(validated_arguments)
                    if validated_arguments is not None
                    else []
                ),
                result=result,
                policy_effect="DENY",
                started=started,
            )
            return result
        except Exception:
            await self._session.rollback()
            result = self._error_result(
                request_id=request_id,
                tool_name=public_tool_name,
                tool_version=tool_version,
                failure=InvocationFailure(
                    ErrorCode.INTERNAL_ERROR,
                    "The regulatory evidence tool could not complete safely.",
                    next_valid_actions=("retry_later", "inspect_run_trace"),
                ),
            )
            await self._persist_result(
                context=context,
                public_tool_name=public_tool_name,
                tool_version=tool_version,
                arguments=(
                    validated_arguments.model_dump(mode="json")
                    if validated_arguments is not None
                    else arguments
                ),
                source_references=(
                    _source_references(validated_arguments)
                    if validated_arguments is not None
                    else []
                ),
                result=result,
                policy_effect="DENY",
                started=started,
            )
            return result

        # Phase two deliberately starts after the policy/budget commit. Re-fetching
        # every mutable authorization row closes the revocation window before dispatch.
        # Its locks are committed and released before the bounded tool execution.
        assert manifest is not None
        assert validated_arguments is not None
        try:
            access = await self._authorize_case_plan_and_sources(
                context=context,
                manifest=manifest,
                arguments=validated_arguments,
            )
            policy = await self._current_policy_decision(binding.id)
            if (
                policy is None
                or not self._policy_matches_call(
                    policy=policy,
                    context=context,
                    access=access,
                    manifest=manifest,
                    arguments_hash=arguments_hash,
                )
                or (
                    policy.request_id != binding.request_id
                    or policy.effect != binding.effect
                    or policy.input_sha256 != binding.input_sha256
                    or policy.decision_sha256 != binding.decision_sha256
                )
            ):
                raise InvocationFailure(
                    ErrorCode.CONFLICT,
                    "The pre-dispatch policy decision failed its integrity check.",
                    next_valid_actions=("block_run", "inspect_run_trace"),
                )
            existing = await self._existing_invocation(context=context, access=access)
            if existing is not None:
                if not self._is_exact_replay(
                    invocation=existing,
                    policy=policy,
                    context=context,
                    access=access,
                    manifest=manifest,
                    arguments_hash=arguments_hash,
                ):
                    raise InvocationFailure(
                        ErrorCode.CONFLICT,
                        "The run idempotency key has conflicting final attribution.",
                        next_valid_actions=("block_run", "inspect_run_trace"),
                    )
                result = self._validated_stored_result(existing, manifest=manifest)
                await self._commit_replay_without_new_audit()
                return result
            await self._session.commit()
        except AttributionCommitError:
            raise
        except InvocationFailure as exc:
            await self._session.rollback()
            return await self._persist_withheld_error(
                context=context,
                binding=binding,
                public_tool_name=public_tool_name,
                tool_version=tool_version,
                failure=self._withheld_authorization_failure(
                    exc,
                    dispatch_occurred=False,
                ),
                operation="mcp.regulatory.dispatch_withheld",
                dispatch_occurred=False,
                started=started,
            )
        except Exception as exc:
            await self._session.rollback()
            return await self._persist_withheld_error(
                context=context,
                binding=binding,
                public_tool_name=public_tool_name,
                tool_version=tool_version,
                failure=self._withheld_authorization_failure(
                    exc,
                    dispatch_occurred=False,
                ),
                operation="mcp.regulatory.dispatch_withheld",
                dispatch_occurred=False,
                started=started,
            )

        dispatch_occurred = binding.effect == "ALLOW"
        if binding.effect == "DENY":
            result = self._error_result(
                request_id=UUID(binding.request_id),
                tool_name=manifest.name,
                tool_version=manifest.version,
                failure=InvocationFailure(
                    ErrorCode.RATE_LIMITED,
                    "The approved run tool-call budget is exhausted.",
                    next_valid_actions=("pause_run", "request_new_plan"),
                ),
            )
        else:
            try:
                data, provenance, warnings = await self._execute_with_policy(
                    context=context,
                    binding=binding,
                    manifest=manifest,
                    tool_name=tool_name,
                    arguments=validated_arguments,
                    arguments_hash=arguments_hash,
                    access=access,
                )
                result = self._success_result(
                    request_id=UUID(binding.request_id),
                    manifest=manifest,
                    data=data,
                    provenance=provenance,
                    warnings=warnings,
                )
                result = self._post_tool_use(manifest=manifest, result=result)
            except RetryAuthorizationFailure as exc:
                await self._session.rollback()
                return await self._persist_withheld_error(
                    context=context,
                    binding=binding,
                    public_tool_name=public_tool_name,
                    tool_version=tool_version,
                    failure=self._withheld_authorization_failure(
                        exc.error,
                        dispatch_occurred=True,
                    ),
                    operation="mcp.regulatory.result_withheld",
                    dispatch_occurred=True,
                    started=started,
                )
            except InvocationFailure as exc:
                result = self._error_result(
                    request_id=UUID(binding.request_id),
                    tool_name=manifest.name,
                    tool_version=manifest.version,
                    failure=exc,
                )
            except Exception:
                result = self._error_result(
                    request_id=UUID(binding.request_id),
                    tool_name=manifest.name,
                    tool_version=manifest.version,
                    failure=InvocationFailure(
                        ErrorCode.INTERNAL_ERROR,
                        "The regulatory evidence tool could not complete safely.",
                        next_valid_actions=("retry_later", "inspect_run_trace"),
                    ),
                )

        # Phase three rechecks every mutable authorization input after the lock-free
        # execution. A pause, cancellation, suspension, or source change withholds the
        # computed result and is durably reconstructable only through its safe audit.
        try:
            final_access = await self._authorize_case_plan_and_sources(
                context=context,
                manifest=manifest,
                arguments=validated_arguments,
            )
            final_policy = await self._current_policy_decision(binding.id)
            if (
                final_policy is None
                or not self._policy_matches_call(
                    policy=final_policy,
                    context=context,
                    access=final_access,
                    manifest=manifest,
                    arguments_hash=arguments_hash,
                )
                or (
                    final_policy.request_id != binding.request_id
                    or final_policy.effect != binding.effect
                    or final_policy.input_sha256 != binding.input_sha256
                    or final_policy.decision_sha256 != binding.decision_sha256
                )
            ):
                raise InvocationFailure(
                    ErrorCode.CONFLICT,
                    "The pre-dispatch policy decision failed its final integrity check.",
                    next_valid_actions=("block_run", "inspect_run_trace"),
                )
            existing = await self._existing_invocation(context=context, access=final_access)
            if existing is not None:
                if not self._is_exact_replay(
                    invocation=existing,
                    policy=final_policy,
                    context=context,
                    access=final_access,
                    manifest=manifest,
                    arguments_hash=arguments_hash,
                ):
                    raise InvocationFailure(
                        ErrorCode.CONFLICT,
                        "The run idempotency key has conflicting final attribution.",
                        next_valid_actions=("block_run", "inspect_run_trace"),
                    )
                stored_result = self._validated_stored_result(existing, manifest=manifest)
                await self._commit_replay_without_new_audit()
                return stored_result
        except AttributionCommitError:
            raise
        except InvocationFailure as exc:
            await self._session.rollback()
            return await self._persist_withheld_error(
                context=context,
                binding=binding,
                public_tool_name=public_tool_name,
                tool_version=tool_version,
                failure=self._withheld_authorization_failure(
                    exc,
                    dispatch_occurred=dispatch_occurred,
                ),
                operation=(
                    "mcp.regulatory.result_withheld"
                    if dispatch_occurred
                    else "mcp.regulatory.dispatch_withheld"
                ),
                dispatch_occurred=dispatch_occurred,
                started=started,
            )
        except Exception as exc:
            await self._session.rollback()
            return await self._persist_withheld_error(
                context=context,
                binding=binding,
                public_tool_name=public_tool_name,
                tool_version=tool_version,
                failure=self._withheld_authorization_failure(
                    exc,
                    dispatch_occurred=dispatch_occurred,
                ),
                operation=(
                    "mcp.regulatory.result_withheld"
                    if dispatch_occurred
                    else "mcp.regulatory.dispatch_withheld"
                ),
                dispatch_occurred=dispatch_occurred,
                started=started,
            )

        await self._persist_result(
            context=context,
            public_tool_name=public_tool_name,
            tool_version=tool_version,
            arguments=argument_payload,
            source_references=source_refs,
            result=result,
            policy_effect=final_policy.effect,
            started=started,
            access=final_access,
            manifest=manifest,
            policy=final_policy,
            started_at=started_at,
        )
        return result

    @staticmethod
    def _validate_runtime_identity(context: HostInvocationContext) -> None:
        if not context.user_authenticated:
            raise InvocationFailure(
                ErrorCode.AUTH_EXPIRED,
                "The user authentication is absent or expired.",
                next_valid_actions=("reauthenticate_user",),
            )
        if (
            not context.runtime_authenticated
            or context.runtime_service != REGULATORY_RUNTIME_SERVICE
        ):
            raise InvocationFailure(
                ErrorCode.PERMISSION_DENIED,
                "The calling runtime is not authorized for regulatory tools.",
                next_valid_actions=("use_authorized_runtime",),
            )

    @staticmethod
    def _validate_agent_identity(context: HostInvocationContext) -> None:
        if (
            context.agent_name != REGULATORY_AGENT_NAME
            or context.agent_version != REGULATORY_AGENT_VERSION
        ):
            raise InvocationFailure(
                ErrorCode.PERMISSION_DENIED,
                "The active agent version is not authorized for this tool bundle.",
                next_valid_actions=("use_approved_agent",),
            )

    async def _authorize_case_plan_and_sources(
        self,
        *,
        context: HostInvocationContext,
        manifest: ToolManifest,
        arguments: BaseModel,
    ) -> AuthorizedInvocation:
        case = await self._session.scalar(
            select(Case)
            .where(Case.id == context.case_id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
        # Case membership is owner-only until the control plane gains a membership table.
        # This intentionally denies reviewers and administrators instead of treating their
        # broader application role as implicit case access.
        if case is None or case.owner_subject != context.user_id:
            raise InvocationFailure(
                ErrorCode.PERMISSION_DENIED,
                "The invocation is not authorized for the active case.",
                next_valid_actions=("review_case_access",),
            )
        sources = list(
            (
                await self._session.scalars(
                    select(CaseSource)
                    .where(CaseSource.case_id == context.case_id)
                    .with_for_update(read=True)
                    .execution_options(populate_existing=True)
                )
            ).all()
        )
        recomputed_state_hash = case_state_sha256(
            objective=case.objective,
            workflow_key=case.workflow_key,
            source_pins=[
                {
                    "source_role": source.source_role,
                    "document_version_id": source.document_version_id,
                    "source_sha256": source.source_sha256,
                }
                for source in sources
            ],
        )
        if (
            recomputed_state_hash != case.current_state_hash
            or context.case_state_hash != case.current_state_hash
        ):
            raise InvocationFailure(
                ErrorCode.CONFLICT,
                "The case state has changed since the runtime context was created.",
                next_valid_actions=("refresh_case_context", "request_new_plan"),
            )

        (
            approval,
            plan,
            run,
            active_step,
            agent_version,
            tool_version,
            policy_limit,
        ) = await self._validate_approved_plan(
            context=context,
            case=case,
            manifest=manifest,
        )
        suspension = await active_suspension(self._session, [agent_version.id])
        if suspension:
            raise InvocationFailure(
                ErrorCode.PERMISSION_DENIED,
                f"Agent execution is suspended by {suspension.control_key}.",
                next_valid_actions=("inspect_runtime_controls",),
            )
        pins: dict[str, set[str]] = {}
        for source in sources:
            pins.setdefault(source.document_version_id, set()).add(source.source_sha256)

        references = _source_references(arguments)
        for version_id, expected_hash in references:
            if version_id not in pins:
                raise InvocationFailure(
                    ErrorCode.SOURCE_NOT_PINNED,
                    "The requested source version is not pinned to the active case.",
                    next_valid_actions=("review_case_sources",),
                )
            if expected_hash not in pins[version_id]:
                raise InvocationFailure(
                    ErrorCode.SOURCE_HASH_MISMATCH,
                    "The requested source hash does not match the exact case pin.",
                    next_valid_actions=("refresh_case_context",),
                )

        version_ids = sorted({version_id for version_id, _source_hash in references})
        versions = {
            version.id: version
            for version in (
                await self._session.scalars(
                    select(DocumentVersion)
                    .where(DocumentVersion.id.in_(version_ids))
                    .with_for_update(read=True)
                    .execution_options(populate_existing=True)
                )
            ).all()
        }
        for version_id, expected_hash in references:
            version = versions.get(version_id)
            if version is None:
                raise InvocationFailure(
                    ErrorCode.NOT_FOUND,
                    "The pinned retained source version is unavailable.",
                    next_valid_actions=("review_case_sources",),
                )
            if version.canonical_hash != expected_hash:
                raise InvocationFailure(
                    ErrorCode.SOURCE_HASH_MISMATCH,
                    "The retained source hash no longer matches the case pin.",
                    next_valid_actions=("block_run", "review_case_sources"),
                )
        return AuthorizedInvocation(
            versions=versions,
            policy_tool_call_limit=policy_limit,
            approval=approval,
            plan=plan,
            run=run,
            active_step=active_step,
            agent_version=agent_version,
            tool_version=tool_version,
        )

    async def _validate_approved_plan(
        self,
        *,
        context: HostInvocationContext,
        case: Case,
        manifest: ToolManifest,
    ) -> tuple[
        ApprovalRequest,
        CasePlan,
        CaseRun,
        CasePlanStep,
        AgentVersion,
        ToolVersion,
        int,
    ]:
        approval = await self._session.scalar(
            select(ApprovalRequest)
            .where(ApprovalRequest.id == context.approval_request_id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
        if (
            approval is None
            or approval.case_id != case.id
            or approval.approval_type != "PLAN_APPROVAL"
            or approval.status != ApprovalStatus.APPROVED.value
            or approval.expires_at is None
            or _aware_utc(approval.expires_at) <= _utcnow()
        ):
            raise InvocationFailure(
                ErrorCode.APPROVAL_REQUIRED,
                "A current plan approval is required for this tool call.",
                next_valid_actions=("request_plan_approval",),
            )
        if approval.bound_state_hash != case.current_state_hash:
            raise InvocationFailure(
                ErrorCode.CONFLICT,
                "The approved plan is stale for the active case state.",
                next_valid_actions=("request_new_plan",),
            )
        plan = await self._session.scalar(
            select(CasePlan)
            .where(CasePlan.id == approval.plan_id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
        if (
            plan is None
            or plan.case_id != case.id
            or plan.id != approval.plan_id
            or plan.version != approval.plan_version
            or plan.plan_sha256 != approval.plan_sha256
            or plan.based_on_state_hash != approval.bound_state_hash
        ):
            raise InvocationFailure(
                ErrorCode.CONFLICT,
                "The approval does not match the immutable plan binding.",
                next_valid_actions=("request_new_plan",),
            )

        run = await self._validate_active_run(context=context, case=case, plan=plan)
        checkpoint = run.checkpoint if isinstance(run.checkpoint, Mapping) else {}
        active_step_key = checkpoint.get("step_key")
        if not isinstance(active_step_key, str) or not active_step_key.strip():
            raise InvocationFailure(
                ErrorCode.CONFLICT,
                "The persisted run checkpoint does not identify an active plan step.",
                next_valid_actions=("resume_approved_run", "inspect_run_trace"),
            )
        active_step = await self._session.scalar(
            select(CasePlanStep)
            .where(
                CasePlanStep.plan_id == plan.id,
                CasePlanStep.step_key == active_step_key,
            )
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
        if active_step is None:
            raise InvocationFailure(
                ErrorCode.CONFLICT,
                "The persisted run checkpoint does not match the approved plan.",
                next_valid_actions=("resume_approved_run", "inspect_run_trace"),
            )

        agent = (
            await self._session.scalar(
                select(AgentVersion)
                .where(AgentVersion.id == active_step.agent_version_id)
                .with_for_update(read=True)
                .execution_options(populate_existing=True)
            )
            if active_step.agent_version_id
            else None
        )
        if (
            agent is None
            or agent.agent_key != context.agent_name
            or agent.version != context.agent_version
            or agent.manifest_sha256 != REGULATORY_AGENT_MANIFEST_SHA256
            or not _reviewed_manifest_matches(
                agent.manifest,
                REGULATORY_AGENT_MANIFEST_SHA256,
            )
            or agent.release_status not in EXECUTABLE_RELEASE_STATES
        ):
            raise InvocationFailure(
                ErrorCode.PERMISSION_DENIED,
                "The active plan step does not bind the reviewed agent definition.",
                next_valid_actions=("request_new_plan",),
            )

        tool_ids = {str(tool_id) for tool_id in (active_step.tool_version_ids or [])}
        tools = list(
            (
                await self._session.scalars(
                    select(ToolVersion)
                    .where(ToolVersion.id.in_(tool_ids))
                    .with_for_update(read=True)
                    .execution_options(populate_existing=True)
                )
            ).all()
        )
        matching_tools = [
            tool
            for tool in tools
            if tool.tool_key == manifest.name
            and tool.version == manifest.version
            and tool.server_key == self._bundle.name
            and tool.manifest_sha256 == self._bundle.definition_hash
            and _reviewed_manifest_matches(tool.manifest, self._bundle.definition_hash)
            and tool.risk_class == "R0"
            and not tool.side_effecting
            and tool.release_status in EXECUTABLE_RELEASE_STATES
        ]
        if len(matching_tools) != 1:
            raise InvocationFailure(
                ErrorCode.PERMISSION_DENIED,
                "The active plan step does not bind the reviewed tool definition.",
                next_valid_actions=("request_new_plan",),
            )

        raw_limit = (active_step.limits or {}).get("max_tool_calls")
        if not isinstance(raw_limit, int) or isinstance(raw_limit, bool) or raw_limit < 1:
            raise InvocationFailure(
                ErrorCode.CONFLICT,
                "The active plan step has no valid tool-call budget.",
                next_valid_actions=("request_new_plan",),
            )
        return (
            approval,
            plan,
            run,
            active_step,
            agent,
            matching_tools[0],
            min(AGENT_MAX_TOOL_CALLS, raw_limit),
        )

    async def _validate_active_run(
        self,
        *,
        context: HostInvocationContext,
        case: Case,
        plan: CasePlan,
    ) -> CaseRun:
        # PostgreSQL serializes budget reservation and idempotency checks on this row.
        # SQLite ignores FOR UPDATE but remains deterministic for the single-process
        # development/test profile.
        run = await self._session.scalar(
            select(CaseRun)
            .where(CaseRun.id == context.run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if run is None or run.case_id != case.id or run.requested_by != context.user_id:
            raise InvocationFailure(
                ErrorCode.PERMISSION_DENIED,
                "The invocation is not bound to an authorized persisted case run.",
                next_valid_actions=("start_approved_run",),
            )
        if run.status != AgentRunStatus.RUNNING.value:
            raise InvocationFailure(
                ErrorCode.CONFLICT,
                "The persisted case run is not in an executable state.",
                next_valid_actions=("resume_approved_run",),
            )
        if (
            run.plan_id != plan.id
            or run.plan_version != plan.version
            or run.plan_sha256 != plan.plan_sha256
            or run.bound_state_hash != plan.based_on_state_hash
            or run.bound_state_hash != case.current_state_hash
        ):
            raise InvocationFailure(
                ErrorCode.CONFLICT,
                "The persisted case run has a stale or altered plan binding.",
                next_valid_actions=("start_approved_run",),
            )
        return run

    async def _existing_invocation(
        self,
        *,
        context: HostInvocationContext,
        access: AuthorizedInvocation,
    ) -> ToolInvocation | None:
        return await self._session.scalar(
            select(ToolInvocation)
            .where(
                ToolInvocation.run_id == access.run.id,
                ToolInvocation.idempotency_key == context.idempotency_key,
            )
            .execution_options(populate_existing=True)
        )

    async def _existing_budget_denial(
        self,
        *,
        context: HostInvocationContext,
        access: AuthorizedInvocation,
        manifest: ToolManifest,
    ) -> tuple[ToolInvocation, dict[str, Any]] | None:
        invocation = await self._session.scalar(
            select(ToolInvocation)
            .where(
                ToolInvocation.case_id == context.case_id,
                ToolInvocation.run_id == access.run.id,
                ToolInvocation.principal_subject == context.user_id,
                ToolInvocation.runtime_service == context.runtime_service,
                ToolInvocation.agent_version_id == access.agent_version.id,
                ToolInvocation.agent_name == context.agent_name,
                ToolInvocation.agent_version == context.agent_version,
                ToolInvocation.tool_version_id == access.tool_version.id,
                ToolInvocation.tool_name == manifest.name,
                ToolInvocation.tool_version == manifest.version,
                ToolInvocation.policy_effect == "DENY",
                ToolInvocation.status == "DENIED",
            )
            .order_by(ToolInvocation.created_at.desc(), ToolInvocation.id.desc())
            .limit(1)
            .execution_options(populate_existing=True)
        )
        if invocation is None:
            return None
        policy = await self._policy_for_invocation(invocation)
        if (
            policy is None
            or not self._policy_matches_authorization(
                policy=policy,
                context=context,
                access=access,
                manifest=manifest,
                allow_runtime_budget_mismatch=True,
            )
            or policy.effect != "DENY"
            or invocation.policy_decision_id != policy.id
            or invocation.request_id != policy.request_id
            or invocation.arguments_sha256 != policy.input_sha256
        ):
            raise InvocationFailure(
                ErrorCode.CONFLICT,
                "The persisted budget-denial observation failed its policy binding.",
                next_valid_actions=("block_run", "inspect_run_trace"),
            )
        result = self._validated_stored_result(invocation, manifest=manifest)
        if result["status"] != "error" or (result.get("error") or {}).get("code") != str(
            ErrorCode.RATE_LIMITED
        ):
            raise InvocationFailure(
                ErrorCode.CONFLICT,
                "The persisted budget-denial observation failed its integrity check.",
                next_valid_actions=("block_run", "inspect_run_trace"),
            )
        return invocation, result

    async def _policy_for_invocation(
        self,
        invocation: ToolInvocation,
    ) -> PolicyDecision | None:
        return await self._current_policy_decision(invocation.policy_decision_id)

    @staticmethod
    def _policy_idempotency_key(context: HostInvocationContext) -> str:
        return "regulatory-mcp-policy:" + _canonical_hash(
            {
                "run_id": context.run_id,
                "invocation_idempotency_key": context.idempotency_key,
            }
        )

    async def _existing_policy_decision(
        self,
        *,
        context: HostInvocationContext,
    ) -> PolicyDecision | None:
        return await self._session.scalar(
            select(PolicyDecision)
            .where(PolicyDecision.idempotency_key == self._policy_idempotency_key(context))
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )

    async def _current_policy_decision(self, policy_id: str) -> PolicyDecision | None:
        return await self._session.scalar(
            select(PolicyDecision)
            .where(PolicyDecision.id == policy_id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )

    def _policy_metadata(
        self,
        *,
        context: HostInvocationContext,
        access: AuthorizedInvocation,
    ) -> dict[str, object]:
        checkpoint = access.run.checkpoint if isinstance(access.run.checkpoint, Mapping) else {}
        stored_limit, _stored_used = self._stored_budget(access.run)
        return {
            "schema_version": "1.0.0",
            "phase": "PRE_DISPATCH",
            "approval_request_id": access.approval.id,
            "approval_status": access.approval.status,
            "approval_expires_at": _aware_utc(access.approval.expires_at).isoformat(),
            "approval_bound_state_hash": access.approval.bound_state_hash,
            "plan_id": access.plan.id,
            "plan_version": access.plan.version,
            "plan_sha256": access.plan.plan_sha256,
            "active_step_id": access.active_step.id,
            "active_step_key": access.active_step.step_key,
            "checkpoint_step_key": checkpoint.get("step_key"),
            "case_state_hash": access.run.bound_state_hash,
            "contract_definition_hash": self._bundle.definition_hash,
            "agent_manifest_sha256": access.agent_version.manifest_sha256,
            "tool_manifest_sha256": access.tool_version.manifest_sha256,
            "policy_tool_call_limit": access.policy_tool_call_limit,
            "runtime_budget_limit": context.budget.max_tool_calls,
            "persisted_budget_limit": stored_limit,
        }

    @staticmethod
    def _policy_reason_codes(effect: str) -> list[str]:
        if effect == "DENY":
            return ["TOOL_CALL_BUDGET_EXHAUSTED"]
        if effect == "ALLOW":
            return [
                "CURRENT_PLAN_APPROVAL",
                "ACTIVE_CHECKPOINT_BINDING",
                "REVIEWED_REGISTRY_DIGESTS",
                "EXACT_SOURCE_PINS",
                "PERSISTED_BUDGET_RESERVED",
            ]
        raise ValueError("unsupported regulatory MCP policy effect")

    @staticmethod
    def _policy_decision_material(policy: PolicyDecision) -> dict[str, object]:
        return {
            "request_id": policy.request_id,
            "case_id": policy.case_id,
            "run_id": policy.run_id,
            "bound_state_hash": policy.bound_state_hash,
            "agent_version_id": policy.agent_version_id,
            "tool_version_id": policy.tool_version_id,
            "principal_subject": policy.principal_subject,
            "action": policy.action,
            "effect": policy.effect,
            "policy_key": policy.policy_key,
            "policy_version": policy.policy_version,
            "policy_sha256": policy.policy_sha256,
            "input_sha256": policy.input_sha256,
            "reason_codes": list(policy.reason_codes or []),
            "decision_metadata": dict(policy.decision_metadata or {}),
            "evaluated_by": policy.evaluated_by,
        }

    def _new_policy_decision(
        self,
        *,
        context: HostInvocationContext,
        access: AuthorizedInvocation,
        manifest: ToolManifest,
        arguments_sha256: str,
        effect: str,
        request_id: UUID,
    ) -> PolicyDecision:
        policy = PolicyDecision(
            id=str(uuid4()),
            case_id=context.case_id,
            run_id=context.run_id,
            bound_state_hash=access.run.bound_state_hash,
            agent_version_id=access.agent_version.id,
            tool_version_id=access.tool_version.id,
            request_id=str(request_id),
            idempotency_key=self._policy_idempotency_key(context),
            principal_subject=context.user_id,
            action=manifest.name,
            effect=effect,
            policy_key=REGULATORY_INVOCATION_POLICY_KEY,
            policy_version=REGULATORY_INVOCATION_POLICY_VERSION,
            policy_sha256=_canonical_hash(REGULATORY_INVOCATION_POLICY_DEFINITION),
            input_sha256=arguments_sha256,
            reason_codes=self._policy_reason_codes(effect),
            decision_metadata=self._policy_metadata(context=context, access=access),
            evaluated_by=context.runtime_service,
        )
        policy.decision_sha256 = _canonical_hash(self._policy_decision_material(policy))
        return policy

    @staticmethod
    def _predispatch_binding(policy: PolicyDecision) -> PredispatchDecision:
        return PredispatchDecision(
            id=policy.id,
            request_id=policy.request_id,
            effect=policy.effect,
            input_sha256=policy.input_sha256,
            decision_sha256=policy.decision_sha256,
        )

    def _policy_matches_call(
        self,
        *,
        policy: PolicyDecision,
        context: HostInvocationContext,
        access: AuthorizedInvocation,
        manifest: ToolManifest,
        arguments_hash: str,
    ) -> bool:
        return (
            self._policy_matches_authorization(
                policy=policy,
                context=context,
                access=access,
                manifest=manifest,
            )
            and policy.idempotency_key == self._policy_idempotency_key(context)
            and policy.input_sha256 == arguments_hash
        )

    def _policy_matches_authorization(
        self,
        *,
        policy: PolicyDecision,
        context: HostInvocationContext,
        access: AuthorizedInvocation,
        manifest: ToolManifest,
        allow_runtime_budget_mismatch: bool = False,
    ) -> bool:
        try:
            request_id = UUID(policy.request_id)
        except (TypeError, ValueError, AttributeError):
            return False
        expected_metadata = self._policy_metadata(context=context, access=access)
        actual_metadata = dict(policy.decision_metadata or {})
        if allow_runtime_budget_mismatch:
            expected_metadata.pop("runtime_budget_limit", None)
            actual_metadata.pop("runtime_budget_limit", None)
        expected_reason_codes = (
            self._policy_reason_codes(policy.effect)
            if policy.effect
            in {
                "ALLOW",
                "DENY",
            }
            else []
        )
        return (
            str(request_id) == policy.request_id
            and policy.case_id == context.case_id
            and policy.run_id == context.run_id
            and policy.bound_state_hash == access.run.bound_state_hash
            and policy.agent_version_id == access.agent_version.id
            and policy.tool_version_id == access.tool_version.id
            and policy.principal_subject == context.user_id
            and policy.action == manifest.name
            and policy.effect in {"ALLOW", "DENY"}
            and policy.policy_key == REGULATORY_INVOCATION_POLICY_KEY
            and policy.policy_version == REGULATORY_INVOCATION_POLICY_VERSION
            and policy.policy_sha256 == _canonical_hash(REGULATORY_INVOCATION_POLICY_DEFINITION)
            and list(policy.reason_codes or []) == expected_reason_codes
            and actual_metadata == expected_metadata
            and policy.evaluated_by == context.runtime_service
            and policy.decision_sha256 == _canonical_hash(self._policy_decision_material(policy))
        )

    def _is_exact_replay(
        self,
        *,
        invocation: ToolInvocation,
        policy: PolicyDecision | None,
        context: HostInvocationContext,
        access: AuthorizedInvocation,
        manifest: ToolManifest,
        arguments_hash: str,
    ) -> bool:
        invocation_matches = (
            invocation.case_id == context.case_id
            and invocation.run_id == context.run_id
            and invocation.principal_subject == context.user_id
            and invocation.runtime_service == context.runtime_service
            and invocation.agent_version_id == access.agent_version.id
            and invocation.agent_name == context.agent_name
            and invocation.agent_version == context.agent_version
            and invocation.tool_version_id == access.tool_version.id
            and invocation.tool_name == manifest.name
            and invocation.tool_version == manifest.version
            and invocation.arguments_sha256 == arguments_hash
        )
        if not invocation_matches or policy is None:
            return False
        return (
            self._policy_matches_call(
                policy=policy,
                context=context,
                access=access,
                manifest=manifest,
                arguments_hash=arguments_hash,
            )
            and invocation.policy_decision_id == policy.id
            and policy.case_id == invocation.case_id
            and policy.run_id == invocation.run_id
            and policy.agent_version_id == invocation.agent_version_id
            and policy.tool_version_id == invocation.tool_version_id
            and policy.request_id == invocation.request_id
            and policy.principal_subject == invocation.principal_subject
            and policy.action == invocation.tool_name
            and policy.effect == invocation.policy_effect
            and policy.input_sha256 == invocation.arguments_sha256
        )

    @staticmethod
    def _validated_stored_result(
        invocation: ToolInvocation,
        *,
        manifest: ToolManifest,
    ) -> dict[str, Any]:
        raw = invocation.structured_result
        if not isinstance(raw, Mapping) or _canonical_hash(raw) != invocation.result_sha256:
            raise InvocationFailure(
                ErrorCode.CONFLICT,
                "The persisted idempotent observation failed its integrity check.",
                next_valid_actions=("block_run", "inspect_run_trace"),
            )
        try:
            if raw.get("status") == "success":
                parsed = SUCCESS_MODELS[manifest.name].model_validate(raw)
            else:
                parsed = ErrorResult.model_validate(raw)
        except ValidationError as exc:
            raise InvocationFailure(
                ErrorCode.CONFLICT,
                "The persisted idempotent observation no longer matches its contract.",
                next_valid_actions=("block_run", "inspect_run_trace"),
            ) from exc
        result = parsed.model_dump(mode="json")
        if (
            result["request_id"] != invocation.request_id
            or result["tool_name"] != manifest.name
            or result["tool_version"] != manifest.version
        ):
            raise InvocationFailure(
                ErrorCode.CONFLICT,
                "The persisted idempotent observation has a different tool identity.",
                next_valid_actions=("block_run", "inspect_run_trace"),
            )
        return result

    @staticmethod
    def _stored_budget(run: CaseRun) -> tuple[int | None, int]:
        checkpoint = run.checkpoint if isinstance(run.checkpoint, Mapping) else {}
        raw_budget = checkpoint.get("regulatory_mcp_budget")
        if not isinstance(raw_budget, Mapping):
            return None, 0
        raw_limit = raw_budget.get("limit")
        raw_used = raw_budget.get("used")
        limit = (
            raw_limit
            if isinstance(raw_limit, int) and not isinstance(raw_limit, bool) and raw_limit > 0
            else None
        )
        used = (
            raw_used
            if isinstance(raw_used, int) and not isinstance(raw_used, bool) and raw_used >= 0
            else 0
        )
        return limit, used

    async def _authoritative_used_calls(self, *, run_id: str) -> int:
        value = await self._session.scalar(
            select(func.count(PolicyDecision.id)).where(
                PolicyDecision.run_id == run_id,
                PolicyDecision.effect == "ALLOW",
                PolicyDecision.policy_key == REGULATORY_INVOCATION_POLICY_KEY,
                PolicyDecision.policy_version == REGULATORY_INVOCATION_POLICY_VERSION,
                PolicyDecision.policy_sha256
                == _canonical_hash(REGULATORY_INVOCATION_POLICY_DEFINITION),
            )
        )
        return int(value or 0)

    @staticmethod
    def _write_budget(*, run: CaseRun, limit: int, used: int) -> None:
        checkpoint = dict(run.checkpoint or {})
        budget = {
            "schema_version": "1.0.0",
            "limit": limit,
            "used": used,
        }
        if checkpoint.get("regulatory_mcp_budget") != budget:
            checkpoint["regulatory_mcp_budget"] = budget
            run.checkpoint = checkpoint

    async def _synchronize_context_budget(
        self,
        *,
        context: HostInvocationContext,
        run: CaseRun,
    ) -> None:
        stored_limit, stored_used = self._stored_budget(run)
        observed_used = await self._authoritative_used_calls(run_id=run.id)
        used = max(stored_used, observed_used)
        if stored_limit is not None and used != stored_used:
            self._write_budget(run=run, limit=stored_limit, used=used)
        context.budget.synchronize_used(used)

    async def _reserve_persisted_budget(
        self,
        *,
        context: HostInvocationContext,
        access: AuthorizedInvocation,
    ) -> bool:
        stored_limit, stored_used = self._stored_budget(access.run)
        observed_used = await self._authoritative_used_calls(run_id=access.run.id)
        used = max(stored_used, observed_used)
        effective_limit = min(
            access.policy_tool_call_limit,
            context.budget.max_tool_calls,
            stored_limit if stored_limit is not None else AGENT_MAX_TOOL_CALLS,
        )
        if used >= effective_limit:
            self._write_budget(run=access.run, limit=effective_limit, used=used)
            context.budget.synchronize_used(used)
            return False
        used += 1
        self._write_budget(run=access.run, limit=effective_limit, used=used)
        context.budget.synchronize_used(used)
        return True

    def _record_invocation(
        self,
        *,
        context: HostInvocationContext,
        access: AuthorizedInvocation,
        manifest: ToolManifest,
        policy: PolicyDecision,
        arguments: object,
        result: dict[str, Any],
        latency_ms: int,
        started_at: datetime,
        completed_at: datetime,
    ) -> None:
        arguments_sha256 = _canonical_hash(arguments)
        if (
            not self._policy_matches_call(
                policy=policy,
                context=context,
                access=access,
                manifest=manifest,
                arguments_hash=arguments_sha256,
            )
            or str(result["request_id"]) != policy.request_id
        ):
            raise AttributionCommitError(
                "Regulatory MCP final observation does not match its pre-dispatch decision."
            )
        if policy.effect == "ALLOW":
            status = "SUCCEEDED" if result["status"] == "success" else "FAILED"
        else:
            status = "DENIED"
        self._session.add(
            ToolInvocation(
                case_id=context.case_id,
                run_id=context.run_id,
                agent_version_id=access.agent_version.id,
                tool_version_id=access.tool_version.id,
                policy_decision_id=policy.id,
                request_id=policy.request_id,
                idempotency_key=context.idempotency_key,
                principal_subject=context.user_id,
                runtime_service=context.runtime_service,
                agent_name=context.agent_name,
                agent_version=context.agent_version,
                tool_name=manifest.name,
                tool_version=manifest.version,
                arguments_sha256=arguments_sha256,
                policy_effect=policy.effect,
                status=status,
                structured_result=result,
                result_sha256=_canonical_hash(result),
                provenance=list(result.get("provenance") or []),
                warnings=list(result.get("warnings") or []),
                latency_ms=latency_ms,
                started_at=started_at,
                completed_at=completed_at,
            )
        )

    async def _persist_result(
        self,
        *,
        context: HostInvocationContext,
        public_tool_name: str,
        tool_version: str,
        arguments: object,
        source_references: list[tuple[str, str]],
        result: dict[str, Any],
        policy_effect: str,
        started: float,
        idempotency_replay: bool = False,
        access: AuthorizedInvocation | None = None,
        manifest: ToolManifest | None = None,
        policy: PolicyDecision | None = None,
        started_at: datetime | None = None,
    ) -> None:
        """Commit the exact observation and generic audit before it is returned."""

        completed_at = _utcnow()
        latency_ms = max(0, int((monotonic() - started) * 1000))
        attribution_values = (access, manifest, policy, started_at)
        try:
            if any(value is not None for value in attribution_values):
                if not all(value is not None for value in attribution_values):
                    raise AttributionCommitError(
                        "Regulatory MCP final attribution is incomplete; result withheld."
                    )
                assert access is not None
                assert manifest is not None
                assert policy is not None
                assert started_at is not None
                if policy.effect != policy_effect:
                    raise AttributionCommitError(
                        "Regulatory MCP policy attribution changed; result withheld."
                    )
                self._record_invocation(
                    context=context,
                    access=access,
                    manifest=manifest,
                    policy=policy,
                    arguments=arguments,
                    result=result,
                    latency_ms=latency_ms,
                    started_at=started_at,
                    completed_at=completed_at,
                )
            await self._audit(
                context=context,
                public_tool_name=public_tool_name,
                tool_version=tool_version,
                arguments=arguments,
                source_references=source_references,
                result=result,
                policy_effect=policy_effect,
                latency_ms=latency_ms,
                idempotency_replay=idempotency_replay,
            )
            await self._session.commit()
        except Exception as exc:
            await self._session.rollback()
            if isinstance(exc, AttributionCommitError):
                raise
            raise AttributionCommitError(
                "Regulatory MCP attribution could not be committed; result withheld."
            ) from exc

    async def _commit_replay_without_new_audit(self) -> None:
        """Close authorization locks without amplifying an exact replay's audit rows."""

        try:
            await self._session.commit()
        except Exception as exc:
            await self._session.rollback()
            raise AttributionCommitError(
                "Regulatory MCP replay state could not be committed; result withheld."
            ) from exc

    async def _persist_aggregated_budget_denial(
        self,
        *,
        context: HostInvocationContext,
        access: AuthorizedInvocation,
        manifest: ToolManifest,
        arguments_hash: str,
        canonical_denial: ToolInvocation,
    ) -> dict[str, Any]:
        """Attribute a distinct exhausted-budget call without unbounded audit rows.

        The first denial for a run/tool remains a normal policy, invocation, and audit
        record. Later distinct idempotency keys receive fresh correlation IDs and are
        retained in a bounded, hash-chained checkpoint aggregate. A retry of a recent
        exact key reconstructs the same safe error and does not increment the aggregate.
        """

        failure = self._budget_denial_failure()
        idempotency_hash = hashlib.sha256(context.idempotency_key.encode("utf-8")).hexdigest()
        bucket_identity = {
            "case_id": context.case_id,
            "run_id": access.run.id,
            "principal_subject": context.user_id,
            "runtime_service": context.runtime_service,
            "agent_version_id": access.agent_version.id,
            "tool_version_id": access.tool_version.id,
            "tool_name": manifest.name,
            "tool_version": manifest.version,
            "canonical_denial_invocation_id": canonical_denial.id,
            "canonical_denial_policy_id": canonical_denial.policy_decision_id,
            "canonical_denial_request_id": canonical_denial.request_id,
        }
        bucket_key = _canonical_hash(bucket_identity)
        checkpoint = dict(access.run.checkpoint or {})
        raw_aggregate = checkpoint.get(RATE_LIMIT_AGGREGATE_CHECKPOINT_KEY)
        if raw_aggregate is None:
            buckets: dict[str, Any] = {}
        else:
            if (
                not isinstance(raw_aggregate, Mapping)
                or raw_aggregate.get("schema_version") != RATE_LIMIT_AGGREGATE_SCHEMA_VERSION
                or not isinstance(raw_aggregate.get("buckets"), Mapping)
            ):
                raise self._corrupt_rate_limit_aggregate()
            raw_buckets = raw_aggregate["buckets"]
            if len(raw_buckets) > RATE_LIMIT_BUCKET_LIMIT or any(
                not isinstance(key, str) or not isinstance(value, Mapping)
                for key, value in raw_buckets.items()
            ):
                raise self._corrupt_rate_limit_aggregate()
            buckets = {key: dict(value) for key, value in raw_buckets.items()}

        raw_bucket = buckets.get(bucket_key)
        if raw_bucket is None:
            if len(buckets) >= RATE_LIMIT_BUCKET_LIMIT:
                raise self._corrupt_rate_limit_aggregate()
            total_count = 0
            chain_sha256 = "0" * 64
            recent_attempts: list[dict[str, Any]] = []
        else:
            if any(raw_bucket.get(key) != value for key, value in bucket_identity.items()):
                raise self._corrupt_rate_limit_aggregate()
            total_count = raw_bucket.get("total_count")
            chain_sha256 = raw_bucket.get("chain_sha256")
            raw_recent_attempts = raw_bucket.get("recent_attempts")
            if (
                not isinstance(total_count, int)
                or isinstance(total_count, bool)
                or total_count < 1
                or not self._is_sha256(chain_sha256)
                or not isinstance(raw_recent_attempts, list)
                or len(raw_recent_attempts) > RATE_LIMIT_RECENT_ATTEMPT_LIMIT
                or total_count < len(raw_recent_attempts)
                or any(not isinstance(item, Mapping) for item in raw_recent_attempts)
            ):
                raise self._corrupt_rate_limit_aggregate()
            recent_attempts = [dict(item) for item in raw_recent_attempts]
            self._validate_rate_limit_attempt_chain(
                recent_attempts=recent_attempts,
                expected_chain_sha256=chain_sha256,
                expected_identity=bucket_identity,
            )

        for attempt in recent_attempts:
            if attempt.get("idempotency_key_sha256") != idempotency_hash:
                continue
            if attempt.get("arguments_sha256") != arguments_hash:
                raise InvocationFailure(
                    ErrorCode.CONFLICT,
                    "The run idempotency key is already bound to different arguments.",
                    next_valid_actions=("use_new_idempotency_key", "inspect_run_trace"),
                )
            try:
                replay_request_id = UUID(str(attempt["request_id"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise self._corrupt_rate_limit_aggregate() from exc
            replay = self._error_result(
                request_id=replay_request_id,
                tool_name=manifest.name,
                tool_version=manifest.version,
                failure=failure,
            )
            if attempt.get("result_sha256") != _canonical_hash(replay):
                raise self._corrupt_rate_limit_aggregate()
            await self._commit_replay_without_new_audit()
            return replay

        result = self._error_result(
            request_id=uuid4(),
            tool_name=manifest.name,
            tool_version=manifest.version,
            failure=failure,
        )
        attempt_material = {
            "request_id": result["request_id"],
            "idempotency_key_sha256": idempotency_hash,
            "arguments_sha256": arguments_hash,
            "result_sha256": _canonical_hash(result),
            "tool_name": manifest.name,
            "tool_version": manifest.version,
            "principal_subject": context.user_id,
            "canonical_denial_invocation_id": canonical_denial.id,
            "canonical_denial_policy_id": canonical_denial.policy_decision_id,
            "canonical_denial_request_id": canonical_denial.request_id,
            "occurred_at": _utcnow().isoformat(),
        }
        next_chain_sha256 = _canonical_hash(
            {
                "previous_chain_sha256": chain_sha256,
                "attempt": attempt_material,
            }
        )
        attempt_record = {
            **attempt_material,
            "previous_chain_sha256": chain_sha256,
            "chain_sha256": next_chain_sha256,
        }
        recent_attempts = [
            *recent_attempts,
            attempt_record,
        ][-RATE_LIMIT_RECENT_ATTEMPT_LIMIT:]
        buckets[bucket_key] = {
            **bucket_identity,
            "total_count": total_count + 1,
            "chain_sha256": next_chain_sha256,
            "recent_attempts": recent_attempts,
        }
        checkpoint[RATE_LIMIT_AGGREGATE_CHECKPOINT_KEY] = {
            "schema_version": RATE_LIMIT_AGGREGATE_SCHEMA_VERSION,
            "buckets": buckets,
        }
        access.run.checkpoint = checkpoint
        try:
            await self._session.commit()
        except Exception as exc:
            await self._session.rollback()
            raise AttributionCommitError(
                "Regulatory MCP rate-limit attribution could not be committed; result withheld."
            ) from exc
        return result

    @staticmethod
    def _validate_rate_limit_attempt_chain(
        *,
        recent_attempts: list[dict[str, Any]],
        expected_chain_sha256: str,
        expected_identity: Mapping[str, object],
    ) -> None:
        identity_keys = (
            "tool_name",
            "tool_version",
            "principal_subject",
            "canonical_denial_invocation_id",
            "canonical_denial_policy_id",
            "canonical_denial_request_id",
        )
        previous_chain: str | None = None
        for attempt in recent_attempts:
            attempt_previous = attempt.get("previous_chain_sha256")
            attempt_chain = attempt.get("chain_sha256")
            material = {
                key: attempt.get(key)
                for key in (
                    "request_id",
                    "idempotency_key_sha256",
                    "arguments_sha256",
                    "result_sha256",
                    *identity_keys,
                    "occurred_at",
                )
            }
            try:
                UUID(str(material["request_id"]))
                occurred_at = datetime.fromisoformat(str(material["occurred_at"]))
            except (TypeError, ValueError) as exc:
                raise RegulatoryMcpGateway._corrupt_rate_limit_aggregate() from exc
            if (
                not RegulatoryMcpGateway._is_sha256(attempt_previous)
                or not RegulatoryMcpGateway._is_sha256(attempt_chain)
                or not RegulatoryMcpGateway._is_sha256(material["idempotency_key_sha256"])
                or not RegulatoryMcpGateway._is_sha256(material["arguments_sha256"])
                or not RegulatoryMcpGateway._is_sha256(material["result_sha256"])
                or not isinstance(material["request_id"], str)
                or not isinstance(material["occurred_at"], str)
                or occurred_at.tzinfo is None
                or any(material[key] != expected_identity[key] for key in identity_keys)
                or (previous_chain is not None and attempt_previous != previous_chain)
                or attempt_chain
                != _canonical_hash(
                    {
                        "previous_chain_sha256": attempt_previous,
                        "attempt": material,
                    }
                )
            ):
                raise RegulatoryMcpGateway._corrupt_rate_limit_aggregate()
            previous_chain = attempt_chain
        if recent_attempts and previous_chain != expected_chain_sha256:
            raise RegulatoryMcpGateway._corrupt_rate_limit_aggregate()

    @staticmethod
    def _is_sha256(value: object) -> bool:
        return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None

    @staticmethod
    def _corrupt_rate_limit_aggregate() -> InvocationFailure:
        return InvocationFailure(
            ErrorCode.CONFLICT,
            "The persisted budget-denial aggregate failed its integrity check.",
            next_valid_actions=("block_run", "inspect_run_trace"),
        )

    @staticmethod
    def _budget_denial_failure() -> InvocationFailure:
        return InvocationFailure(
            ErrorCode.RATE_LIMITED,
            "The approved run tool-call budget is exhausted.",
            next_valid_actions=("pause_run", "request_new_plan"),
        )

    async def _persist_withheld_error(
        self,
        *,
        context: HostInvocationContext,
        binding: PredispatchDecision,
        public_tool_name: str,
        tool_version: str,
        failure: InvocationFailure,
        operation: str,
        dispatch_occurred: bool,
        started: float,
    ) -> dict[str, Any]:
        """Persist the exact safe error when no ToolInvocation may be attributed."""

        result = self._error_result(
            request_id=UUID(binding.request_id),
            tool_name=public_tool_name,
            tool_version=tool_version,
            failure=failure,
        )
        result_sha256 = _canonical_hash(result)
        latency_ms = max(0, int((monotonic() - started) * 1000))
        try:
            add_audit_event(
                self._session,
                principal=Principal(
                    subject=f"{context.agent_name}@{context.agent_version}",
                    roles=frozenset({"service"}),
                    actor_type="agent",
                ),
                request_id=binding.request_id,
                operation=operation,
                object_type="policy_decision",
                object_id=binding.id,
                application_version=tool_version,
                result="denied",
                reason=failure.code.value,
                after={
                    "structured_error_sha256": result_sha256,
                    "dispatch_occurred": dispatch_occurred,
                },
                context={
                    "user_id": context.user_id,
                    "tenant_id": context.tenant_id,
                    "case_id": context.case_id,
                    "run_id": context.run_id,
                    "agent_name": context.agent_name,
                    "agent_version": context.agent_version,
                    "runtime_service": context.runtime_service,
                    "invocation_idempotency_key": context.idempotency_key,
                    "tool_name": public_tool_name,
                    "tool_version": tool_version,
                    "policy_decision_id": binding.id,
                    "policy_request_id": binding.request_id,
                    "policy_effect": binding.effect,
                    "policy_input_sha256": binding.input_sha256,
                    "policy_decision_sha256": binding.decision_sha256,
                    "reason_code": failure.code.value,
                    "dispatch_occurred": dispatch_occurred,
                    "dispatch_executed": dispatch_occurred,
                    "tool_invocation_created": False,
                    "structured_error": result,
                    "structured_error_sha256": result_sha256,
                    "latency_ms": latency_ms,
                },
            )
            await self._session.flush()
            await self._session.commit()
        except Exception as exc:
            await self._session.rollback()
            raise AttributionCommitError(
                "Regulatory MCP withheld-result audit could not be committed; result withheld."
            ) from exc
        return result

    @staticmethod
    def _withheld_authorization_failure(
        error: Exception,
        *,
        dispatch_occurred: bool,
    ) -> InvocationFailure:
        if isinstance(error, InvocationFailure):
            code = error.code
            next_valid_actions = error.next_valid_actions
        else:
            code = ErrorCode.INTERNAL_ERROR
            next_valid_actions = ("retry_later", "inspect_run_trace")
        subject = "result" if dispatch_occurred else "dispatch"
        return InvocationFailure(
            code,
            f"The regulatory tool {subject} was withheld because authorization "
            "could not be confirmed.",
            next_valid_actions=next_valid_actions,
        )

    async def _execute_with_policy(
        self,
        *,
        context: HostInvocationContext,
        binding: PredispatchDecision,
        manifest: ToolManifest,
        tool_name: str,
        arguments: BaseModel,
        arguments_hash: str,
        access: AuthorizedInvocation,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
        """Execute outside a DB transaction under the reviewed timeout/retry policy."""

        for attempt in range(1, manifest.maximum_attempts + 1):
            if attempt > 1:
                access = await self._authorize_retry_attempt(
                    context=context,
                    binding=binding,
                    manifest=manifest,
                    arguments=arguments,
                    arguments_hash=arguments_hash,
                )
            try:
                deadline_token = _EXECUTION_DEADLINE.set(monotonic() + manifest.timeout_seconds)
                try:
                    async with asyncio.timeout(manifest.timeout_seconds):
                        _check_execution_deadline()
                        output = await self._execute(
                            tool_name=tool_name,
                            arguments=arguments,
                            access=access,
                        )
                        # CPU-only implementations may never yield to asyncio's
                        # cancellation timer. Never accept their late output.
                        _check_execution_deadline()
                        return output
                finally:
                    _EXECUTION_DEADLINE.reset(deadline_token)
            except TimeoutError as exc:
                if attempt < manifest.maximum_attempts:
                    continue
                raise InvocationFailure(
                    ErrorCode.TIMEOUT,
                    "The regulatory evidence tool exceeded its reviewed execution timeout.",
                    next_valid_actions=("retry_later", "inspect_run_trace"),
                    retryable=True,
                ) from exc
            except InvocationFailure as exc:
                transient = exc.retryable and exc.code in {
                    ErrorCode.TIMEOUT,
                    ErrorCode.UPSTREAM_UNAVAILABLE,
                }
                if (
                    manifest.retry_policy == "TRANSIENT_ONLY"
                    and transient
                    and attempt < manifest.maximum_attempts
                ):
                    continue
                raise
        raise AssertionError("reviewed execution attempts must be positive")

    async def _authorize_retry_attempt(
        self,
        *,
        context: HostInvocationContext,
        binding: PredispatchDecision,
        manifest: ToolManifest,
        arguments: BaseModel,
        arguments_hash: str,
    ) -> AuthorizedInvocation:
        """Refresh authorization and release its locks before one retry dispatch."""

        try:
            access = await self._authorize_case_plan_and_sources(
                context=context,
                manifest=manifest,
                arguments=arguments,
            )
            policy = await self._current_policy_decision(binding.id)
            if (
                policy is None
                or not self._policy_matches_call(
                    policy=policy,
                    context=context,
                    access=access,
                    manifest=manifest,
                    arguments_hash=arguments_hash,
                )
                or (
                    policy.request_id != binding.request_id
                    or policy.effect != binding.effect
                    or policy.input_sha256 != binding.input_sha256
                    or policy.decision_sha256 != binding.decision_sha256
                )
            ):
                raise InvocationFailure(
                    ErrorCode.CONFLICT,
                    "The pre-dispatch policy decision failed its retry integrity check.",
                    next_valid_actions=("block_run", "inspect_run_trace"),
                )
            await self._session.commit()
            return access
        except Exception as exc:
            await self._session.rollback()
            raise RetryAuthorizationFailure(exc) from exc

    async def _execute(
        self,
        *,
        tool_name: str,
        arguments: BaseModel,
        access: AuthorizedInvocation,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
        _check_execution_deadline()
        if tool_name == "regulatory.get_version":
            assert isinstance(arguments, GetVersionArguments)
            return await self._get_version(arguments, access)
        if tool_name == "regulatory.get_section":
            assert isinstance(arguments, GetSectionArguments)
            return await self._get_section(arguments, access)
        if tool_name == "regulatory.get_anchor":
            assert isinstance(arguments, GetAnchorArguments)
            return self._get_anchor(arguments, access)
        if tool_name == "regulatory.compare_versions":
            assert isinstance(arguments, CompareVersionsArguments)
            return self._compare_versions(arguments, access)
        if tool_name == "regulatory.search_regulatory_references":
            assert isinstance(arguments, SearchRegulatoryReferencesArguments)
            return await self._search_regulatory_references(arguments, access)
        raise InvocationFailure(
            ErrorCode.PERMISSION_DENIED,
            "Tool is not available to this agent.",
            next_valid_actions=("use_allowlisted_tool",),
        )

    async def _get_version(
        self,
        arguments: GetVersionArguments,
        access: AuthorizedInvocation,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
        _check_execution_deadline()
        version = access.versions[str(arguments.document_version_id)]
        source_url = self._retained_source_url(version)
        provenance = self._provenance(version, anchor_id=None)
        _check_execution_deadline()
        return (
            {
                "document_version_id": version.id,
                "document_id": version.document_id,
                "version_number": version.version_number,
                "source_hash": version.canonical_hash,
                "source_url": source_url,
                "retrieved_at": version.retrieved_at,
            },
            [provenance],
            [],
        )

    @staticmethod
    def _retained_source_url(version: DocumentVersion) -> str:
        _check_execution_deadline()
        provenance = version.http_provenance
        source_url = provenance.get("final_url") if isinstance(provenance, Mapping) else None
        if not isinstance(source_url, str) or not source_url or source_url != source_url.strip():
            raise InvocationFailure(
                ErrorCode.CONFLICT,
                "The pinned source version has no exact retained FDA provenance URL.",
                next_valid_actions=("block_run", "review_case_sources"),
            )
        try:
            parsed = urlsplit(source_url)
            hostname = (parsed.hostname or "").lower()
            port = parsed.port
        except ValueError as exc:
            raise InvocationFailure(
                ErrorCode.CONFLICT,
                "The pinned source version has an invalid retained FDA provenance URL.",
                next_valid_actions=("block_run", "review_case_sources"),
            ) from exc
        if (
            not FDA_SOURCE_URL_PATTERN.match(source_url)
            or len(source_url) > 2048
            or parsed.scheme.lower() != "https"
            or not hostname
            or (hostname != "fda.gov" and not hostname.endswith(".fda.gov"))
            or parsed.username is not None
            or parsed.password is not None
            or port is not None
            or not parsed.path.startswith("/")
        ):
            raise InvocationFailure(
                ErrorCode.CONFLICT,
                "The pinned source version has an invalid retained FDA provenance URL.",
                next_valid_actions=("block_run", "review_case_sources"),
            )
        return source_url

    async def _get_section(
        self,
        arguments: GetSectionArguments,
        access: AuthorizedInvocation,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
        _check_execution_deadline()
        version = access.versions[str(arguments.document_version_id)]
        # Parser-native, case-pinned DocumentVersion anchors are the only section
        # evidence authority in M2. Multi-segment paths fail closed until the immutable
        # anchor representation natively carries a nested path.
        anchors = (
            self._section_anchors(version, arguments.section_path[0])
            if len(arguments.section_path) == 1
            else []
        )
        if not anchors:
            raise InvocationFailure(
                ErrorCode.NOT_FOUND,
                "The requested section was not found in the pinned source version.",
                next_valid_actions=("review_available_anchors",),
            )

        warnings: list[str] = ["SECTION_TEXT_IS_BOUNDED_AGGREGATE"]
        safe_anchors: list[tuple[str, str]] = []
        safe_anchor_ids: set[str] = set()
        aggregate_characters = 0
        size_omitted = False
        quarantined_omitted = False
        maximum_items = self._bundle.tools["regulatory.get_section"].maximum_items
        for anchor_id, value in anchors:
            _check_execution_deadline()
            screened, detected = sanitize_untrusted_content({"excerpt": value})
            _check_execution_deadline()
            if screened["excerpt"] != value or detected:
                warnings.extend(detected)
                quarantined_omitted = True
                continue
            separator_size = 1 if safe_anchors else 0
            if (
                anchor_id in safe_anchor_ids
                or len(safe_anchors) >= maximum_items
                or aggregate_characters + separator_size + len(value)
                > SECTION_AGGREGATE_CHARACTER_LIMIT
            ):
                size_omitted = True
                continue
            safe_anchors.append((anchor_id, value))
            safe_anchor_ids.add(anchor_id)
            aggregate_characters += separator_size + len(value)
        if quarantined_omitted:
            warnings.append("QUARANTINED_ANCHORS_OMITTED")
        if size_omitted:
            warnings.append("SECTION_ANCHORS_OMITTED_FOR_SIZE")
        anchors = safe_anchors
        if not anchors:
            raise InvocationFailure(
                ErrorCode.PERMISSION_DENIED,
                "The requested section contains only quarantined source content.",
                next_valid_actions=("review_quarantined_source",),
            )
        _check_execution_deadline()
        text = "\n".join(value for _anchor_id, value in anchors).strip()
        anchor_ids = list(dict.fromkeys(anchor_id for anchor_id, _value in anchors))
        provenance: list[dict[str, Any]] = []
        for anchor_id in anchor_ids:
            _check_execution_deadline()
            provenance.append(self._provenance(version, anchor_id=anchor_id))
        _check_execution_deadline()
        return (
            {
                "document_version_id": version.id,
                "source_hash": version.canonical_hash,
                "section_path": list(arguments.section_path),
                "text": text,
                "anchor_ids": anchor_ids,
            },
            provenance,
            warnings,
        )

    def _get_anchor(
        self,
        arguments: GetAnchorArguments,
        access: AuthorizedInvocation,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
        _check_execution_deadline()
        version = access.versions[str(arguments.document_version_id)]
        current_section: list[str] = []
        for raw in version.source_anchors or []:
            _check_execution_deadline()
            anchor_id = str(raw.get("anchor", "")).strip()
            text = str(raw.get("text", "")).strip()
            kind = str(raw.get("kind", "")).strip()
            if kind == "heading" and anchor_id:
                current_section = [anchor_id]
            if anchor_id != arguments.anchor_id or not text:
                continue
            screened, detected = sanitize_untrusted_content({"excerpt": text})
            _check_execution_deadline()
            if screened["excerpt"] != text or detected:
                raise InvocationFailure(
                    ErrorCode.PERMISSION_DENIED,
                    "The requested source anchor is quarantined from agent context.",
                    next_valid_actions=("review_quarantined_source",),
                )
            warnings: list[str] = []
            if len(text) > 4000:
                text = text[:4000]
                warnings.append("CONTENT_LIMIT_APPLIED")
            return (
                {
                    "document_version_id": version.id,
                    "source_hash": version.canonical_hash,
                    "anchor_id": anchor_id,
                    "section_path": current_section,
                    "excerpt": text,
                },
                [self._provenance(version, anchor_id=anchor_id)],
                warnings,
            )
        raise InvocationFailure(
            ErrorCode.NOT_FOUND,
            "The requested anchor was not found in the pinned source version.",
            next_valid_actions=("review_available_anchors",),
        )

    def _compare_versions(
        self,
        arguments: CompareVersionsArguments,
        access: AuthorizedInvocation,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
        _check_execution_deadline()
        before = access.versions[str(arguments.from_document_version_id)]
        after = access.versions[str(arguments.to_document_version_id)]
        if before.document_id != after.document_id:
            raise InvocationFailure(
                ErrorCode.CONFLICT,
                "Only retained versions of the same FDA document can be compared.",
                next_valid_actions=("review_case_sources",),
            )
        before_anchors = self._anchor_map(before)
        after_anchors = self._anchor_map(after)
        ordered_ids = list(before_anchors)
        for anchor_id in after_anchors:
            _check_execution_deadline()
            if anchor_id not in before_anchors:
                ordered_ids.append(anchor_id)
        changes: list[dict[str, Any]] = []
        quarantined_change = False
        for anchor_id in ordered_ids:
            _check_execution_deadline()
            before_text = before_anchors.get(anchor_id)
            after_text = after_anchors.get(anchor_id)
            if before_text == after_text:
                continue
            if before_text is None:
                change_type = "ADDED"
            elif after_text is None:
                change_type = "REMOVED"
            else:
                change_type = "MODIFIED"
            evidence_fields = {
                "before_excerpt": before_text,
                "after_excerpt": after_text,
            }
            screened, detected = sanitize_untrusted_content(evidence_fields)
            _check_execution_deadline()
            if screened != evidence_fields or detected:
                quarantined_change = True
                continue
            changes.append(
                {
                    "change_type": change_type,
                    "anchor_id": anchor_id,
                    "before_excerpt": before_text[:4000] if before_text is not None else None,
                    "after_excerpt": after_text[:4000] if after_text is not None else None,
                }
            )
        warnings: list[str] = []
        if quarantined_change:
            warnings.append("QUARANTINED_CHANGES_OMITTED")
        maximum_items = self._bundle.tools["regulatory.compare_versions"].maximum_items
        if len(changes) > maximum_items:
            changes = changes[:maximum_items]
            warnings.append("CHANGE_LIMIT_APPLIED")
        provenance: list[dict[str, Any]] = []
        seen_provenance: set[tuple[str, str | None]] = set()
        for change in changes:
            _check_execution_deadline()
            anchor_id = str(change["anchor_id"])
            for version, anchor_map in (
                (before, before_anchors),
                (after, after_anchors),
            ):
                _check_execution_deadline()
                if anchor_id not in anchor_map:
                    continue
                identity = (version.id, anchor_id)
                if identity not in seen_provenance:
                    provenance.append(self._provenance(version, anchor_id=anchor_id))
                    seen_provenance.add(identity)
        # The response contract requires at least two provenance entries even for an
        # empty diff or a one-sided single-anchor addition/removal. Document-level
        # bindings supplement (but never replace) the exact anchor provenance above.
        for version in (before, after):
            _check_execution_deadline()
            if len(provenance) >= 2:
                break
            identity = (version.id, None)
            if identity not in seen_provenance:
                provenance.append(self._provenance(version, anchor_id=None))
                seen_provenance.add(identity)
        return (
            {
                "from_document_version_id": before.id,
                "from_source_hash": before.canonical_hash,
                "to_document_version_id": after.id,
                "to_source_hash": after.canonical_hash,
                "changes": changes,
            },
            provenance,
            warnings,
        )

    async def _search_regulatory_references(
        self,
        arguments: SearchRegulatoryReferencesArguments,
        access: AuthorizedInvocation,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
        _check_execution_deadline()
        version_ids = [str(source.document_version_id) for source in arguments.sources]
        query = arguments.query.casefold()
        query_tokens = {token for token in re.findall(r"\w+", query) if len(token) >= 2}
        candidates: list[tuple[int, int, str, str, str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        quarantined_reference = False
        for version_id in version_ids:
            _check_execution_deadline()
            version = access.versions[version_id]
            for fallback_ordinal, raw_anchor in enumerate(version.source_anchors or []):
                _check_execution_deadline()
                anchor_id = str(raw_anchor.get("anchor", "")).strip()
                anchor_text = str(raw_anchor.get("text", "")).strip()
                raw_ordinal = raw_anchor.get("ordinal")
                ordinal = (
                    raw_ordinal
                    if isinstance(raw_ordinal, int) and not isinstance(raw_ordinal, bool)
                    else fallback_ordinal
                )
                if (
                    not anchor_text
                    or not ANCHOR_PATTERN.fullmatch(anchor_id)
                    or len(anchor_id) > 256
                ):
                    continue
                content_folded = anchor_text.casefold()
                references = extract_regulatory_references(anchor_text)
                _check_execution_deadline()
                for reference in references:
                    _check_execution_deadline()
                    reference = str(reference).strip()[:500]
                    if not reference:
                        continue
                    reference_folded = reference.casefold()
                    reference_match = query in reference_folded or (
                        bool(query_tokens)
                        and all(token in reference_folded for token in query_tokens)
                    )
                    content_match = query in content_folded or (
                        bool(query_tokens)
                        and all(token in content_folded for token in query_tokens)
                    )
                    if not reference_match and not content_match:
                        continue
                    identity = (version.id, anchor_id, reference)
                    if identity in seen:
                        continue
                    seen.add(identity)
                    score = 10 if reference_match else 1
                    citation_text = self._bounded_context(
                        anchor_text,
                        reference,
                        arguments.query,
                    )
                    evidence_fields = {
                        "reference": reference,
                        "citation_text": citation_text,
                    }
                    screened, detected = sanitize_untrusted_content(evidence_fields)
                    _check_execution_deadline()
                    if screened != evidence_fields or detected:
                        quarantined_reference = True
                        continue
                    candidates.append(
                        (
                            -score,
                            ordinal,
                            version.id,
                            anchor_id,
                            reference,
                            citation_text,
                        )
                    )
        _check_execution_deadline()
        candidates.sort()
        _check_execution_deadline()
        selected = candidates[: arguments.limit]
        items: list[dict[str, Any]] = []
        provenance: list[dict[str, Any]] = []
        for _score, _ordinal, version_id, anchor_id, reference, citation_text in selected:
            _check_execution_deadline()
            version = access.versions[version_id]
            items.append(
                {
                    "reference": reference,
                    "citation_text": citation_text,
                    "document_version_id": version.id,
                    "source_hash": version.canonical_hash,
                    "anchor_id": anchor_id,
                }
            )
            provenance.append(self._provenance(version, anchor_id=anchor_id))
        warnings = ["RESULT_LIMIT_APPLIED"] if len(candidates) > arguments.limit else []
        if quarantined_reference:
            warnings.append("QUARANTINED_REFERENCE_RESULTS_OMITTED")
        return ({"items": items, "next_cursor": None}, provenance, warnings)

    @staticmethod
    def _section_anchors(version: DocumentVersion, target: str) -> list[tuple[str, str]]:
        _check_execution_deadline()
        target_folded = target.casefold()
        collecting = target_folded == "introduction"
        found_heading = False
        values: list[tuple[str, str]] = []
        for raw in version.source_anchors or []:
            _check_execution_deadline()
            anchor_id = str(raw.get("anchor", "")).strip()
            text = str(raw.get("text", "")).strip()
            kind = str(raw.get("kind", "")).strip()
            if (
                not anchor_id
                or not text
                or len(anchor_id) > 256
                or not ANCHOR_PATTERN.fullmatch(anchor_id)
            ):
                continue
            if kind == "heading":
                is_target = anchor_id == target or text.casefold() == target_folded
                if collecting and (found_heading or not is_target):
                    break
                collecting = is_target
                found_heading = is_target
            if collecting:
                values.append((anchor_id, text))
        return values

    @staticmethod
    def _anchor_map(version: DocumentVersion) -> dict[str, str]:
        _check_execution_deadline()
        result: dict[str, str] = {}
        for raw in version.source_anchors or []:
            _check_execution_deadline()
            anchor_id = str(raw.get("anchor", "")).strip()
            text = str(raw.get("text", "")).strip()
            if (
                anchor_id
                and text
                and len(anchor_id) <= 256
                and ANCHOR_PATTERN.fullmatch(anchor_id)
                and anchor_id not in result
            ):
                result[anchor_id] = text
        return result

    @staticmethod
    def _bounded_context(content: str, reference: str, query: str) -> str:
        _check_execution_deadline()
        folded = content.casefold()
        position = folded.find(reference.casefold())
        if position < 0:
            position = folded.find(query.casefold())
        if position < 0:
            return content[:4000] or reference
        start = max(0, position - 1000)
        end = min(len(content), position + len(reference) + 2500)
        bounded = content[start:end].strip()[:4000] or reference
        _check_execution_deadline()
        return bounded

    @staticmethod
    def _provenance(version: DocumentVersion, *, anchor_id: str | None) -> dict[str, Any]:
        _check_execution_deadline()
        return {
            "source_version_id": version.id,
            "source_hash": version.canonical_hash,
            "anchor_id": anchor_id,
        }

    @staticmethod
    def _success_result(
        *,
        request_id: UUID,
        manifest: ToolManifest,
        data: dict[str, Any],
        provenance: list[dict[str, Any]],
        warnings: list[str],
    ) -> dict[str, Any]:
        model = SUCCESS_MODELS[manifest.name]
        return model.model_validate(
            {
                "status": "success",
                "request_id": request_id,
                "tool_name": manifest.name,
                "tool_version": manifest.version,
                "data": data,
                "provenance": provenance,
                "warnings": list(dict.fromkeys(warnings))[:20],
            }
        ).model_dump(mode="json")

    @staticmethod
    def _error_result(
        *,
        request_id: UUID,
        tool_name: str,
        tool_version: str,
        failure: InvocationFailure,
    ) -> dict[str, Any]:
        return ErrorResult.model_validate(
            {
                "status": "error",
                "request_id": request_id,
                "tool_name": tool_name,
                "tool_version": tool_version,
                "error": {
                    "code": failure.code,
                    "message": failure.message,
                    "retryable": failure.retryable,
                },
                "next_valid_actions": list(failure.next_valid_actions),
            }
        ).model_dump(mode="json")

    def _post_tool_use(
        self,
        *,
        manifest: ToolManifest,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        # Validate before transforming an adapter result, then validate the final observation.
        model = SUCCESS_MODELS[manifest.name]
        result = model.model_validate(result).model_dump(mode="json")
        sanitized_data, warnings = sanitize_untrusted_content(result["data"])
        if sanitized_data != result["data"] or warnings:
            raise InvocationFailure(
                ErrorCode.PERMISSION_DENIED,
                "The tool result was quarantined because source content was unsafe.",
                next_valid_actions=("review_quarantined_source",),
            )
        result = self._enforce_result_bound(manifest, result)
        return model.model_validate(result).model_dump(mode="json")

    @staticmethod
    def _enforce_result_bound(
        manifest: ToolManifest,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        maximum = manifest.maximum_result_characters
        if _result_size(result) <= maximum:
            return result
        _append_warning(result, "RESULT_SIZE_LIMIT_APPLIED")
        tool_name = result["tool_name"]
        if tool_name == "regulatory.search_regulatory_references":
            while result["data"]["items"] and _result_size(result) > maximum:
                result["data"]["items"].pop()
                if result["provenance"]:
                    result["provenance"].pop()
        elif tool_name == "regulatory.compare_versions":
            while result["data"]["changes"] and _result_size(result) > maximum:
                result["data"]["changes"].pop()
        elif tool_name == "regulatory.get_section":
            # Never sever section text from its returned anchor/provenance set.
            raise InvocationFailure(
                ErrorCode.INTERNAL_ERROR,
                "The bounded section aggregate exceeds its contract limit.",
                next_valid_actions=("inspect_run_trace",),
            )
        elif tool_name == "regulatory.get_anchor":
            excerpt = result["data"]["excerpt"]
            while len(excerpt) > 1 and _result_size(result) > maximum:
                excerpt = excerpt[: max(1, len(excerpt) * 3 // 4)]
                result["data"]["excerpt"] = excerpt
        if _result_size(result) > maximum:
            raise InvocationFailure(
                ErrorCode.INTERNAL_ERROR,
                "The bounded tool result exceeds its contract limit.",
                next_valid_actions=("inspect_run_trace",),
            )
        return result

    async def _audit(
        self,
        *,
        context: HostInvocationContext,
        public_tool_name: str,
        tool_version: str,
        arguments: object,
        source_references: list[tuple[str, str]],
        result: dict[str, Any],
        policy_effect: str,
        latency_ms: int,
        idempotency_replay: bool,
    ) -> None:
        result_hash = _canonical_hash(result)
        provenance = [
            {
                "source_version_id": item.get("source_version_id"),
                "source_hash": item.get("source_hash"),
                "anchor_id": item.get("anchor_id"),
            }
            for item in result.get("provenance", [])
            if isinstance(item, Mapping)
        ]
        audit_summary = {
            "status": result["status"],
            "error_code": (result.get("error") or {}).get("code"),
            "warning_codes": list(result.get("warnings") or []),
            "result_hash": result_hash,
            "result_characters": _result_size(result),
            "provenance_count": len(provenance),
        }
        add_audit_event(
            self._session,
            principal=Principal(
                subject=f"{context.agent_name}@{context.agent_version}",
                roles=frozenset({"service"}),
                actor_type="agent",
            ),
            request_id=str(result["request_id"]),
            operation="mcp.regulatory.invoke",
            object_type="mcp_tool",
            object_id=public_tool_name,
            application_version=tool_version,
            result=str(result["status"]),
            reason=(result.get("error") or {}).get("code"),
            # Generic audit storage deliberately excludes full untrusted source text.
            # The access-controlled ToolInvocation row retains the exact bounded result.
            after=audit_summary,
            context={
                "user_id": context.user_id,
                "tenant_id": context.tenant_id,
                "case_id": context.case_id,
                "run_id": context.run_id,
                "agent_name": context.agent_name,
                "agent_version": context.agent_version,
                "runtime_service": context.runtime_service,
                "idempotency_key": context.idempotency_key,
                "tool_name": public_tool_name,
                "tool_version": tool_version,
                "arguments_hash": _canonical_hash(arguments),
                "policy_decision": policy_effect,
                "idempotency_replay": idempotency_replay,
                "source_version_ids": [version_id for version_id, _ in source_references],
                "source_hashes": [source_hash for _, source_hash in source_references],
                "result_hash": result_hash,
                "result_characters": _result_size(result),
                "warning_codes": list(result.get("warnings") or []),
                "provenance": provenance,
                "latency_ms": latency_ms,
                "contract_definition_hash": self._bundle.definition_hash,
                "case_membership_policy": "OWNER_ONLY_MVP",
            },
        )
        await self._session.flush()
