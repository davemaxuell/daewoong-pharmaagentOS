"""Deterministic validation for regulatory model output and retained evidence."""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections.abc import Mapping
from uuid import UUID

from pydantic import ValidationError

from .contracts import RegulatoryFinding, RegulatoryFindingList
from .interfaces import AnchorObservation, SourcePin, ValidationCode, ValidationIssue

_TOKEN = re.compile(r"[a-z0-9]+|[가-힣]{2,}", re.IGNORECASE)
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "by",
        "company",
        "did",
        "does",
        "fda",
        "finding",
        "firm",
        "for",
        "from",
        "had",
        "has",
        "have",
        "in",
        "is",
        "it",
        "its",
        "letter",
        "not",
        "of",
        "on",
        "or",
        "requested",
        "stated",
        "that",
        "the",
        "their",
        "this",
        "to",
        "under",
        "was",
        "were",
        "with",
        "your",
    }
)
_PROMPT_INJECTION_PATTERNS = (
    re.compile(r"\bignore\b.{0,40}\b(?:previous|prior|above|system|developer)\b", re.I),
    re.compile(
        r"\b(?:reveal|print|return|expose)\b.{0,40}\b(?:system prompt|secret|credential)", re.I
    ),
    re.compile(r"\b(?:call|invoke|execute|use)\b.{0,30}\b(?:tool|function|command)\b", re.I),
    re.compile(r"\b(?:system|developer)\s+(?:message|instruction|prompt)\s*:", re.I),
    re.compile(r"\b(?:begin|end)\s+(?:system|developer)\s+(?:message|prompt)\b", re.I),
)
_PROHIBITED_CONCLUSION_PATTERNS = (
    re.compile(
        r"\b(?:we|our|internal|organization|company|daewoong|site|facility)\b"
        r"[\s\S]{0,100}\b(?:non[- ]?compliant|compliant|in violation|"
        r"violat(?:e|es|ed|ing|ion|ions)|breach(?:es|ed|ing)?|"
        r"fails? to comply|c?gmp gap|deficien(?:cy|cies))\b",
        re.I,
    ),
    re.compile(
        r"\b(?:we|our|internal|organization|company|daewoong|site|facility)\b"
        r"[\s\S]{0,120}\b(?:requires?|warrants?|necessitates?|must|should|needs? to)\b"
        r"[\s\S]{0,40}\bCAPA\b",
        re.I,
    ),
    re.compile(r"\b(?:is|are|was|were)\s+(?:non[- ]?compliant|in violation)\b", re.I),
    re.compile(
        r"\b(?:must|should|needs? to|required to)\s+"
        r"(?:create|open|initiate|implement|approve)\s+(?:an?\s+)?capa\b",
        re.I,
    ),
    re.compile(r"\bcapa\s+(?:is|was|remains)\s+(?:required|necessary|approved)\b", re.I),
    re.compile(r"\b(?:revise|approve)\s+(?:the\s+|an?\s+)?sop\b", re.I),
)


def _path(location: tuple[object, ...]) -> str:
    if not location:
        return "$"
    rendered = "$"
    for item in location:
        if isinstance(item, int):
            rendered += f"[{item}]"
        else:
            rendered += f".{item}"
    return rendered


def parse_regulatory_finding_list(
    raw_output: Mapping[str, object] | object,
) -> tuple[RegulatoryFindingList | None, tuple[ValidationIssue, ...]]:
    """Parse an untrusted model object without preserving any undeclared provider fields."""

    if not isinstance(raw_output, Mapping):
        return None, (
            ValidationIssue(
                code=ValidationCode.SCHEMA_INVALID,
                path="$",
                message="Model output must be a JSON object.",
            ),
        )
    try:
        output = RegulatoryFindingList.model_validate(dict(raw_output))
    except ValidationError as exc:
        issues: list[ValidationIssue] = []
        for error in exc.errors(include_input=False, include_url=False):
            error_type = str(error.get("type", ""))
            if error_type == "extra_forbidden":
                code = ValidationCode.UNKNOWN_FIELD
                message = "Output contains a field that is not declared by the result contract."
            else:
                code = ValidationCode.SCHEMA_INVALID
                message = "Output does not satisfy RegulatoryFindingList@2.0.0."
            issues.append(
                ValidationIssue(
                    code=code,
                    path=_path(tuple(error.get("loc", ()))),
                    message=message,
                )
            )
        return None, tuple(issues)
    except Exception:
        return None, (
            ValidationIssue(
                code=ValidationCode.SCHEMA_INVALID,
                path="$",
                message="Model output could not be read as a bounded JSON object.",
            ),
        )
    return output, ()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _authored_text(finding: RegulatoryFinding) -> tuple[tuple[str, str], ...]:
    values: list[tuple[str, str]] = [
        ("title", finding.title),
        ("finding_text", finding.finding_text),
    ]
    values.extend(
        (f"regulatory_references[{index}].reference", item.reference)
        for index, item in enumerate(finding.regulatory_references)
    )
    values.extend(
        (f"fda_requested_actions[{index}].action", item.action)
        for index, item in enumerate(finding.fda_requested_actions)
    )
    values.extend(
        (f"extraction_warnings[{index}].message", item.message)
        for index, item in enumerate(finding.extraction_warnings)
    )
    return tuple(values)


def validate_declared_output(
    output: RegulatoryFindingList,
    *,
    source_pins: tuple[SourcePin, ...],
    taxonomy_version: str,
) -> tuple[ValidationIssue, ...]:
    """Validate source bindings, internal citations, hashes, and prohibited authored content."""

    issues: list[ValidationIssue] = []
    pin_index = {str(pin.source_version_id): pin.source_hash for pin in source_pins}
    if output.taxonomy_version != taxonomy_version:
        issues.append(
            ValidationIssue(
                code=ValidationCode.TAXONOMY_VERSION_MISMATCH,
                path="$.taxonomy_version",
                message="Output taxonomy version does not match the authorized task context.",
            )
        )

    for finding_index, finding in enumerate(output.findings):
        base = f"$.findings[{finding_index}]"
        source_version_id = str(finding.source_version_id)
        pinned_hash = pin_index.get(source_version_id)
        if pinned_hash is None:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.UNPINNED_SOURCE,
                    path=f"{base}.source_version_id",
                    message="Finding references a source version that is not pinned to the case.",
                )
            )
        elif finding.source_hash != pinned_hash:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.SOURCE_HASH_MISMATCH,
                    path=f"{base}.source_hash",
                    message="Finding source hash does not match the authorized source pin.",
                )
            )

        evidence_ids: set[str] = set()
        for evidence_index, evidence in enumerate(finding.evidence):
            evidence_base = f"{base}.evidence[{evidence_index}]"
            if evidence.anchor_id in evidence_ids:
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.DUPLICATE_ANCHOR,
                        path=f"{evidence_base}.anchor_id",
                        message="A finding may cite each exact anchor only once.",
                    )
                )
            evidence_ids.add(evidence.anchor_id)
            if evidence.source_version_id != finding.source_version_id:
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.ANCHOR_SOURCE_MISMATCH,
                        path=f"{evidence_base}.source_version_id",
                        message=(
                            "Evidence source version does not match its finding source version."
                        ),
                    )
                )
            if evidence.source_hash != finding.source_hash:
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.SOURCE_HASH_MISMATCH,
                        path=f"{evidence_base}.source_hash",
                        message="Evidence source hash does not match its finding source hash.",
                    )
                )
            if sha256_text(evidence.excerpt) != evidence.excerpt_sha256:
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.EXCERPT_HASH_MISMATCH,
                        path=f"{evidence_base}.excerpt_sha256",
                        message="Evidence excerpt hash does not match the declared exact excerpt.",
                    )
                )

        cited_groups = (
            ("regulatory_references", finding.regulatory_references),
            ("fda_requested_actions", finding.fda_requested_actions),
            ("extraction_warnings", finding.extraction_warnings),
        )
        for group_name, group in cited_groups:
            for item_index, item in enumerate(group):
                missing = set(item.evidence_anchor_ids) - evidence_ids
                if missing:
                    issues.append(
                        ValidationIssue(
                            code=ValidationCode.UNCITED_CLAIM,
                            path=f"{base}.{group_name}[{item_index}].evidence_anchor_ids",
                            message=(
                                "Cited claim references an anchor absent from the finding evidence."
                            ),
                        )
                    )

        for field_path, value in _authored_text(finding):
            if any(pattern.search(value) for pattern in _PROMPT_INJECTION_PATTERNS):
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.PROMPT_INJECTION,
                        path=f"{base}.{field_path}",
                        message=(
                            "Authored output contains instruction-like content from an "
                            "untrusted source."
                        ),
                    )
                )
            if any(pattern.search(value) for pattern in _PROHIBITED_CONCLUSION_PATTERNS):
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.PROHIBITED_CONCLUSION,
                        path=f"{base}.{field_path}",
                        message=(
                            "Output makes a prohibited compliance, CAPA, or controlled-record "
                            "conclusion."
                        ),
                    )
                )
    return tuple(issues)


def unique_evidence_lookups(
    output: RegulatoryFindingList,
) -> tuple[tuple[UUID, str, str], ...]:
    """Return stable, de-duplicated `(version, hash, anchor)` lookups for budget checks."""

    ordered: dict[tuple[UUID, str, str], None] = {}
    for finding in output.findings:
        for evidence in finding.evidence:
            ordered[(evidence.source_version_id, evidence.source_hash, evidence.anchor_id)] = None
    return tuple(ordered)


def _normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _material_tokens(value: str) -> set[str]:
    return {
        token
        for token in _TOKEN.findall(unicodedata.normalize("NFKC", value).casefold())
        if token not in _STOPWORDS and (len(token) >= 2 or token.isdigit())
    }


def _is_supported(claim: str, excerpts: list[str], *, minimum_ratio: float = 0.5) -> bool:
    normalized_claim = _normalized(claim)
    normalized_evidence = _normalized(" ".join(excerpts))
    if normalized_claim in normalized_evidence:
        return True
    claim_tokens = _material_tokens(claim)
    evidence_tokens = _material_tokens(normalized_evidence)
    if not claim_tokens:
        return False
    overlap = len(claim_tokens & evidence_tokens)
    required = max(
        1 if len(claim_tokens) <= 2 else 2,
        math.ceil(len(claim_tokens) * minimum_ratio),
    )
    return overlap >= required


def _all_claim_units_supported(
    claim: str,
    excerpts: list[str],
    *,
    minimum_ratio: float = 0.5,
) -> bool:
    """Require support for every sentence/line so a supported tail cannot mask fabrication."""

    units = [
        unit.strip() for unit in re.split(r"(?<=[.!?])\s+|\r?\n+", claim) if _material_tokens(unit)
    ]
    return bool(units) and all(
        _is_supported(unit, excerpts, minimum_ratio=minimum_ratio) for unit in units
    )


def validate_resolved_evidence(
    output: RegulatoryFindingList,
    observations: Mapping[tuple[UUID, str, str], AnchorObservation | None],
) -> tuple[ValidationIssue, ...]:
    """Verify exact retained anchors and bounded deterministic claim support."""

    issues: list[ValidationIssue] = []
    for finding_index, finding in enumerate(output.findings):
        base = f"$.findings[{finding_index}]"
        valid_excerpts: dict[str, str] = {}
        for evidence_index, evidence in enumerate(finding.evidence):
            evidence_base = f"{base}.evidence[{evidence_index}]"
            key = (evidence.source_version_id, evidence.source_hash, evidence.anchor_id)
            observation = observations.get(key)
            if not isinstance(observation, AnchorObservation):
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.UNRESOLVED_ANCHOR,
                        path=f"{evidence_base}.anchor_id",
                        message="Evidence anchor could not be resolved from the retained source.",
                    )
                )
                continue
            if not observation.access_allowed:
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.ACCESS_DENIED,
                        path=f"{evidence_base}.anchor_id",
                        message="Runtime policy did not permit access to the cited anchor.",
                    )
                )
                continue
            if observation.evidence_class != "PRIMARY_AUTHORITATIVE":
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.DERIVATIVE_EVIDENCE,
                        path=f"{evidence_base}.evidence_class",
                        message=(
                            "Derivative content cannot be represented as primary "
                            "regulatory evidence."
                        ),
                    )
                )
                continue
            if (
                observation.source_version_id != evidence.source_version_id
                or observation.anchor_id != evidence.anchor_id
            ):
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.ANCHOR_SOURCE_MISMATCH,
                        path=f"{evidence_base}.anchor_id",
                        message=(
                            "Resolved anchor identity does not match the declared "
                            "evidence identity."
                        ),
                    )
                )
                continue
            if observation.source_hash != evidence.source_hash:
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.SOURCE_HASH_MISMATCH,
                        path=f"{evidence_base}.source_hash",
                        message=(
                            "Resolved anchor source hash does not match the pinned source hash."
                        ),
                    )
                )
                continue
            if observation.excerpt != evidence.excerpt:
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.EXCERPT_MISMATCH,
                        path=f"{evidence_base}.excerpt",
                        message=(
                            "Evidence excerpt has changed or does not exactly match "
                            "the retained anchor."
                        ),
                    )
                )
                continue
            if sha256_text(observation.excerpt) != evidence.excerpt_sha256:
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.EXCERPT_HASH_MISMATCH,
                        path=f"{evidence_base}.excerpt_sha256",
                        message="Resolved excerpt does not match the declared excerpt hash.",
                    )
                )
                continue
            valid_excerpts[evidence.anchor_id] = observation.excerpt

        if not valid_excerpts:
            continue
        excerpts = list(valid_excerpts.values())
        if not _all_claim_units_supported(finding.title, excerpts):
            issues.append(
                ValidationIssue(
                    code=ValidationCode.UNSUPPORTED_CLAIM,
                    path=f"{base}.title",
                    message="Finding title lacks deterministic support in its cited evidence.",
                )
            )
        if not _all_claim_units_supported(finding.finding_text, excerpts):
            issues.append(
                ValidationIssue(
                    code=ValidationCode.UNSUPPORTED_CLAIM,
                    path=f"{base}.finding_text",
                    message=(
                        "Material finding lacks deterministic lexical support in "
                        "its cited evidence."
                    ),
                )
            )
        for reference_index, reference in enumerate(finding.regulatory_references):
            excerpts = [
                valid_excerpts[anchor_id]
                for anchor_id in reference.evidence_anchor_ids
                if anchor_id in valid_excerpts
            ]
            if excerpts and not _is_supported(reference.reference, excerpts, minimum_ratio=0.6):
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.UNSUPPORTED_CLAIM,
                        path=f"{base}.regulatory_references[{reference_index}].reference",
                        message="Regulatory reference is not supported by its cited evidence.",
                    )
                )
        for action_index, action in enumerate(finding.fda_requested_actions):
            excerpts = [
                valid_excerpts[anchor_id]
                for anchor_id in action.evidence_anchor_ids
                if anchor_id in valid_excerpts
            ]
            if excerpts and not _is_supported(action.action, excerpts):
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.UNSUPPORTED_CLAIM,
                        path=f"{base}.fda_requested_actions[{action_index}].action",
                        message="Requested action is not supported by its cited evidence.",
                    )
                )
    return tuple(issues)
