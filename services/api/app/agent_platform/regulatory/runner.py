"""Bounded Regulatory Evidence Agent harness.

The model proposes one JSON object. Application code validates policy, budgets, source pins,
exact evidence, and intended use before the result can leave this boundary.
"""

from __future__ import annotations

import re
from uuid import UUID

from .contracts import ProcessLens
from .gateway_adapter import RegulatoryGatewayError
from .interfaces import (
    AGENT_NAME,
    AGENT_VERSION,
    ALLOWED_TOOL_NAMES,
    ANCHOR_TOOL_NAME,
    MAX_CORRECTION_LOOPS,
    MAX_TOOL_CALLS,
    MAX_TURNS,
    AnchorObservation,
    PreauthorizedRegulatoryTools,
    RegulatoryAgentContext,
    RegulatoryAgentFailure,
    RegulatoryAgentResult,
    RegulatoryAgentSuccess,
    RegulatoryGenerationRequest,
    RegulatoryModelOutputProducer,
    RegulatoryRuntimeIdentity,
    RunFailureCode,
    RunLimits,
    SourcePin,
    ValidationCode,
    ValidationIssue,
)
from .validation import (
    parse_regulatory_finding_list,
    unique_evidence_lookups,
    validate_declared_output,
    validate_resolved_evidence,
)

_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_TAXONOMY_VERSION = re.compile(r"^drug-taxonomy-v[0-9]+\.[0-9]+\.[0-9]+$")
_MAX_FEEDBACK_ISSUES = 20


def _failure(
    code: RunFailureCode,
    issues: tuple[ValidationIssue, ...],
    *,
    model_attempts: int,
    correction_loops: int,
    tool_calls: int,
    retryable: bool = False,
) -> RegulatoryAgentFailure:
    return RegulatoryAgentFailure(
        code=code,
        issues=issues,
        model_attempts=model_attempts,
        correction_loops=correction_loops,
        tool_calls=tool_calls,
        retryable=retryable,
    )


def _context_failure(context: RegulatoryAgentContext) -> RegulatoryAgentFailure | None:
    issues: list[ValidationIssue] = []
    identity = context.identity
    if not isinstance(identity, RegulatoryRuntimeIdentity):
        return _failure(
            RunFailureCode.INVALID_CONTEXT,
            (
                ValidationIssue(
                    code=ValidationCode.INVALID_CONTEXT,
                    path="$.context.identity",
                    message="Runtime identity has an invalid type.",
                ),
            ),
            model_attempts=0,
            correction_loops=0,
            tool_calls=0,
        )
    identity_values = {
        "user_id": identity.user_id,
        "tenant_id": identity.tenant_id,
        "case_id": identity.case_id,
        "run_id": identity.run_id,
        "idempotency_key": identity.idempotency_key,
        "runtime_service": identity.runtime_service,
    }
    for name, value in identity_values.items():
        if not isinstance(value, str) or not value.strip():
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_CONTEXT,
                    path=f"$.context.identity.{name}",
                    message="Runtime attribution context is incomplete.",
                )
            )
    for name in ("case_id", "run_id"):
        try:
            UUID(getattr(identity, name))
        except (TypeError, ValueError, AttributeError):
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_CONTEXT,
                    path=f"$.context.identity.{name}",
                    message="Runtime case and run identifiers must be UUIDs.",
                )
            )
    if identity.agent_name != AGENT_NAME or identity.agent_version != AGENT_VERSION:
        issues.append(
            ValidationIssue(
                code=ValidationCode.POLICY_DENIED,
                path="$.context.identity.agent_version",
                message="Runtime agent identity is not the registered immutable version.",
            )
        )
    if not isinstance(context.case_objective, str) or not context.case_objective.strip():
        issues.append(
            ValidationIssue(
                code=ValidationCode.INVALID_CONTEXT,
                path="$.context.case_objective",
                message="A non-empty case objective is required.",
            )
        )
    if not isinstance(context.taxonomy_version, str) or not _TAXONOMY_VERSION.fullmatch(
        context.taxonomy_version
    ):
        issues.append(
            ValidationIssue(
                code=ValidationCode.INVALID_CONTEXT,
                path="$.context.taxonomy_version",
                message="Authorized taxonomy version is invalid.",
            )
        )
    source_pins = context.source_pins if isinstance(context.source_pins, tuple) else ()
    if not isinstance(context.source_pins, tuple):
        issues.append(
            ValidationIssue(
                code=ValidationCode.INVALID_CONTEXT,
                path="$.context.source_pins",
                message="Source pins must use the immutable tuple contract.",
            )
        )
    if not source_pins:
        issues.append(
            ValidationIssue(
                code=ValidationCode.UNPINNED_SOURCE,
                path="$.context.source_pins",
                message="At least one exact source pin is required.",
            )
        )
    seen_versions: set[UUID] = set()
    for index, pin in enumerate(source_pins):
        if not isinstance(pin, SourcePin):
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_CONTEXT,
                    path=f"$.context.source_pins[{index}]",
                    message="Source pin has an invalid type.",
                )
            )
            continue
        if not isinstance(pin.source_version_id, UUID):
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_CONTEXT,
                    path=f"$.context.source_pins[{index}].source_version_id",
                    message="Pinned source version ID must be a UUID.",
                )
            )
        elif pin.source_version_id in seen_versions:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_CONTEXT,
                    path=f"$.context.source_pins[{index}].source_version_id",
                    message="A source version may be pinned only once.",
                )
            )
        else:
            seen_versions.add(pin.source_version_id)
        if not isinstance(pin.source_hash, str) or not _SHA256.fullmatch(pin.source_hash):
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_CONTEXT,
                    path=f"$.context.source_pins[{index}].source_hash",
                    message="Pinned source hash must be a lowercase SHA-256 digest.",
                )
            )
    requested_lenses = (
        context.requested_lenses if isinstance(context.requested_lenses, tuple) else ()
    )
    if not isinstance(context.requested_lenses, tuple) or not all(
        isinstance(lens, ProcessLens) for lens in requested_lenses
    ):
        issues.append(
            ValidationIssue(
                code=ValidationCode.INVALID_CONTEXT,
                path="$.context.requested_lenses",
                message="Requested process lenses must use the controlled vocabulary.",
            )
        )
    elif len(requested_lenses) != len(set(requested_lenses)):
        issues.append(
            ValidationIssue(
                code=ValidationCode.INVALID_CONTEXT,
                path="$.context.requested_lenses",
                message="Requested process lenses must be unique.",
            )
        )
    allowed_tool_names = (
        context.allowed_tool_names
        if isinstance(context.allowed_tool_names, frozenset)
        and all(isinstance(name, str) for name in context.allowed_tool_names)
        else frozenset()
    )
    if not allowed_tool_names:
        issues.append(
            ValidationIssue(
                code=ValidationCode.INVALID_CONTEXT,
                path="$.context.allowed_tool_names",
                message="Authorized tool names have an invalid type or are empty.",
            )
        )
    elif not allowed_tool_names.issubset(ALLOWED_TOOL_NAMES):
        issues.append(
            ValidationIssue(
                code=ValidationCode.POLICY_DENIED,
                path="$.context.allowed_tool_names",
                message="Context grants a tool outside the registered regulatory allowlist.",
            )
        )
    if ANCHOR_TOOL_NAME not in allowed_tool_names:
        issues.append(
            ValidationIssue(
                code=ValidationCode.POLICY_DENIED,
                path="$.context.allowed_tool_names",
                message="Exact anchor resolution is not authorized for this run.",
            )
        )
    if issues:
        failure_code = (
            RunFailureCode.POLICY_DENIED
            if any(issue.code == ValidationCode.POLICY_DENIED for issue in issues)
            else RunFailureCode.INVALID_CONTEXT
        )
        return _failure(
            failure_code,
            tuple(issues),
            model_attempts=0,
            correction_loops=0,
            tool_calls=0,
        )

    limits = context.limits
    if not isinstance(limits, RunLimits) or any(
        isinstance(value, bool) or not isinstance(value, int)
        for value in (
            getattr(limits, "max_turns", None),
            getattr(limits, "max_tool_calls", None),
            getattr(limits, "max_correction_loops", None),
        )
    ):
        return _failure(
            RunFailureCode.INVALID_CONTEXT,
            (
                ValidationIssue(
                    code=ValidationCode.INVALID_CONTEXT,
                    path="$.context.limits",
                    message="Run limits must be integer values in the registered limit type.",
                ),
            ),
            model_attempts=0,
            correction_loops=0,
            tool_calls=0,
        )
    invalid_budget = (
        limits.max_turns < 1
        or limits.max_turns > MAX_TURNS
        or limits.max_tool_calls < 1
        or limits.max_tool_calls > MAX_TOOL_CALLS
        or limits.max_correction_loops < 0
        or limits.max_correction_loops > MAX_CORRECTION_LOOPS
        or limits.max_correction_loops + 1 > limits.max_turns
    )
    if invalid_budget:
        return _failure(
            RunFailureCode.BUDGET_EXCEEDED,
            (
                ValidationIssue(
                    code=ValidationCode.BUDGET_EXCEEDED,
                    path="$.context.limits",
                    message="Requested limits exceed the registered agent budget.",
                ),
            ),
            model_attempts=0,
            correction_loops=0,
            tool_calls=0,
        )
    return None


def _exhausted_failure_code(
    *,
    issues: tuple[ValidationIssue, ...],
    correction_loops: int,
    maximum_corrections: int,
) -> RunFailureCode:
    if maximum_corrections > 0 and correction_loops >= maximum_corrections:
        return RunFailureCode.CORRECTION_LIMIT_REACHED
    if issues and all(
        issue.code in {ValidationCode.SCHEMA_INVALID, ValidationCode.UNKNOWN_FIELD}
        for issue in issues
    ):
        return RunFailureCode.SCHEMA_INVALID
    return RunFailureCode.VALIDATION_FAILED


async def run_regulatory_evidence_agent(
    *,
    producer: RegulatoryModelOutputProducer,
    tools: PreauthorizedRegulatoryTools,
    context: RegulatoryAgentContext,
) -> RegulatoryAgentResult:
    """Run bounded generation and deterministic verification with at most one correction loop."""

    context_failure = _context_failure(context)
    if context_failure is not None:
        return context_failure

    model_attempts = 0
    correction_loops = 0
    tool_calls = 0
    feedback: tuple[ValidationIssue, ...] = ()
    observation_cache: dict[tuple[UUID, str, str], AnchorObservation | None] = {}

    while model_attempts < context.limits.max_correction_loops + 1:
        model_attempts += 1
        request = RegulatoryGenerationRequest(
            case_objective=context.case_objective,
            taxonomy_version=context.taxonomy_version,
            source_pins=context.source_pins,
            requested_lenses=context.requested_lenses,
            attempt=model_attempts,
            validation_feedback=feedback,
        )
        try:
            raw_output = await producer.produce(request=request)
        except Exception:
            return _failure(
                RunFailureCode.MODEL_OUTPUT_ERROR,
                (
                    ValidationIssue(
                        code=ValidationCode.SCHEMA_INVALID,
                        path="$",
                        message="Model output producer failed before returning a result object.",
                    ),
                ),
                model_attempts=model_attempts,
                correction_loops=correction_loops,
                tool_calls=tool_calls,
                retryable=True,
            )

        output, issues = parse_regulatory_finding_list(raw_output)
        if output is not None:
            issues = validate_declared_output(
                output,
                source_pins=context.source_pins,
                taxonomy_version=context.taxonomy_version,
            )
            if not issues:
                lookups = unique_evidence_lookups(output)
                pending_lookups = [key for key in lookups if key not in observation_cache]
                if tool_calls + len(pending_lookups) > context.limits.max_tool_calls:
                    return _failure(
                        RunFailureCode.BUDGET_EXCEEDED,
                        (
                            ValidationIssue(
                                code=ValidationCode.BUDGET_EXCEEDED,
                                path="$.findings[*].evidence",
                                message=(
                                    "Exact anchor validation would exceed the tool-call budget."
                                ),
                            ),
                        ),
                        model_attempts=model_attempts,
                        correction_loops=correction_loops,
                        tool_calls=tool_calls,
                    )
                for source_version_id, source_hash, anchor_id in pending_lookups:
                    try:
                        observation = await tools.get_anchor(
                            source_version_id=source_version_id,
                            expected_source_hash=source_hash,
                            anchor_id=anchor_id,
                            identity=context.identity,
                        )
                    except RegulatoryGatewayError as exc:
                        return _failure(
                            RunFailureCode.TOOL_FAILURE,
                            (
                                ValidationIssue(
                                    code=ValidationCode.UNRESOLVED_ANCHOR,
                                    path="$.findings[*].evidence",
                                    message="Governed regulatory gateway rejected anchor lookup.",
                                ),
                            ),
                            model_attempts=model_attempts,
                            correction_loops=correction_loops,
                            tool_calls=tool_calls + 1,
                            retryable=exc.retryable,
                        )
                    except Exception:
                        return _failure(
                            RunFailureCode.TOOL_FAILURE,
                            (
                                ValidationIssue(
                                    code=ValidationCode.UNRESOLVED_ANCHOR,
                                    path="$.findings[*].evidence",
                                    message="Authorized anchor lookup failed.",
                                ),
                            ),
                            model_attempts=model_attempts,
                            correction_loops=correction_loops,
                            tool_calls=tool_calls + 1,
                            retryable=True,
                        )
                    tool_calls += 1
                    observation_cache[(source_version_id, source_hash, anchor_id)] = observation
                issues = validate_resolved_evidence(output, observation_cache)
            if not issues:
                return RegulatoryAgentSuccess(
                    output=output,
                    model_attempts=model_attempts,
                    correction_loops=correction_loops,
                    tool_calls=tool_calls,
                )

        if correction_loops >= context.limits.max_correction_loops:
            return _failure(
                _exhausted_failure_code(
                    issues=issues,
                    correction_loops=correction_loops,
                    maximum_corrections=context.limits.max_correction_loops,
                ),
                issues,
                model_attempts=model_attempts,
                correction_loops=correction_loops,
                tool_calls=tool_calls,
            )
        correction_loops += 1
        feedback = issues[:_MAX_FEEDBACK_ISSUES]

    raise AssertionError("bounded regulatory agent loop terminated without a typed result")
