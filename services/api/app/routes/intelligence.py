from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import false, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai import (
    DOCUMENT_ANALYSIS_SCHEMA_VERSION,
    DOCUMENT_TRANSLATION_SCHEMA_VERSION,
    PRESERVED_SOURCE_TOKEN,
    AiGenerationError,
    AiGenerator,
    AiStreamEvent,
    ConversationTurn,
    DocumentAiGenerator,
    DocumentSourceSection,
    GroundedPassage,
    ValidatedChatGenerator,
    build_document_ai_generator,
    protected_token_multiset,
)
from app.audit import add_audit_event
from app.config import Settings
from app.dependencies import (
    ai_generator_dependency,
    embedding_generator_dependency,
    session_dependency,
    settings_dependency,
)
from app.embedding_store import SemanticRetrievalError, semantic_scores_for_allowed_chunks
from app.embeddings import EmbeddingGenerationError, GeminiEmbeddingGenerator
from app.enums import ReviewDecision, ReviewState, ScopeStatus
from app.models import (
    AiSummary,
    ChatMessage,
    ChatThread,
    Document,
    DocumentChunk,
    DocumentTranslation,
    DocumentVersion,
    Finding,
    RagQuery,
    Review,
    Subscription,
    WarningLetter,
    new_uuid,
    utcnow,
)
from app.pagination import InvalidCursor, decode_cursor, encode_cursor, page_window
from app.rag_planner import (
    RagPlan,
    choose_model_profile,
    is_clearly_out_of_scope,
    plan_rag,
)
from app.schemas import (
    CitationResponse,
    LetterAiArtifactResponse,
    LetterListItem,
    RagQueryRequest,
    RagQueryResponse,
    ReviewActionResponse,
    ReviewPatchRequest,
    ReviewQueueItem,
    ReviewQueuePage,
    SavedViewCreateRequest,
    SavedViewCriteria,
    SavedViewPage,
    SavedViewResponse,
    SavedViewUpdateRequest,
)
from app.security.auth import (
    Principal,
    rag_principal,
    reviewer_principal,
    view_principal,
)
from app.taxonomy import taxonomy_document

from .serializers import (
    analysis_artifact_response,
    letter_item,
    summary_response,
    translation_artifact_response,
)

router = APIRouter()
logger = logging.getLogger("uvicorn.error")
CHAT_PENDING_STALE_AFTER = timedelta(minutes=5)
RagStreamEmitter = Callable[[dict[str, object]], Awaitable[None]]
TOKEN_PATTERN = re.compile(r"[^\W_]{2,}", re.UNICODE)
COMPANY_NAME_TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)
HANGUL_CHARACTER_PATTERN = re.compile(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7a3]")
LATIN_CHARACTER_PATTERN = re.compile(r"[A-Za-z]")
COMPANY_CORPORATE_SUFFIX_TOKENS = {
    "ag",
    "bv",
    "co",
    "company",
    "corp",
    "corporation",
    "gmbh",
    "inc",
    "incorporated",
    "limited",
    "llc",
    "llp",
    "ltd",
    "nv",
    "plc",
    "pte",
    "sa",
    "sas",
    "spa",
}
COMPANY_GENERIC_ALIAS_TOKENS = {
    *COMPANY_CORPORATE_SUFFIX_TOKENS,
    "drug",
    "drugs",
    "health",
    "healthcare",
    "laboratories",
    "laboratory",
    "labs",
    "medicine",
    "medicines",
    "pharma",
    "pharmaceutical",
    "pharmaceuticals",
    "product",
    "products",
    "science",
    "sciences",
    "technology",
    "the",
}
STOPWORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "did",
    "do",
    "does",
    "fda",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "say",
    "said",
    "that",
    "the",
    "their",
    "this",
    "to",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "with",
}
QUERY_TOKEN_ALIASES = {
    "공정": {"process"},
    "밸리데이션": {"validation"},
    "지속적": {"continued", "continuous", "ongoing"},
    "검증": {"validation", "verification"},
    "품질": {"quality"},
    "부서": {"unit"},
    "감독": {"authority", "oversight", "review"},
    "우려": {"concern", "concerns"},
    "지적": {
        "deficiencies",
        "deficiency",
        "failure",
        "failures",
        "finding",
        "findings",
        "violation",
        "violations",
    },
    "안정성": {"stability"},
    "재시험": {"retest"},
    "근거": {"support"},
    "무균": {"aseptic", "sterile", "sterility"},
    "오염": {"contaminated", "contamination", "microbial"},
    "데이터": {"data"},
    "무결성": {"integrity"},
    "완전성": {"integrity"},
    "규정": {"cfr", "regulation", "regulations", "regulatory", "required"},
    "요청": {"provide", "request", "requested", "requests", "respond", "response"},
    "조치": {"action", "actions", "corrective", "remediation"},
    "제조업체": {"firm", "manufacturer", "manufacturing"},
}

QUERY_CONCEPT_ALIASES = {
    "cgmp지적사항": {"cgmp", "findings", "violations"},
    "데이터무결성": {"data", "integrity"},
    "품질부서": {"quality", "unit"},
    "품질감독": {"oversight", "quality"},
    "공정밸리데이션": {"process", "validation"},
    "지속적검증": {"continued", "verification"},
    "요청조치": {"actions", "provide", "requested"},
    "의약품제조및품질관리기준": {"cgmp", "manufacturing", "practice"},
    "우수제조관리기준": {"cgmp", "manufacturing", "practice"},
}

LATIN_REGULATORY_ACRONYMS = frozenset(
    {"api", "capa", "cfr", "cgmp", "gmp", "ich", "oos", "oot", "otc", "ppq"}
)
KOREAN_QUERY_PARTICLES = ("와", "과", "은", "는", "이", "가", "에", "의")
NEUTRAL_ANALYSIS_DISCLAIMERS = {
    "ko": (
        "이 자료는 FDA 원문에 근거한 내부 비교 검토 지원용이며, 대웅제약 또는 "
        "대웅바이오의 규정 준수 여부에 대한 결론이나 법률 자문이 아닙니다."
    ),
    "en": (
        "This material supports internal comparison against the FDA source. It is not a "
        "conclusion about Daewoong Pharmaceutical or Daewoong Bio's compliance and is not "
        "legal advice."
    ),
}


def _source_sections(version: DocumentVersion) -> list[DocumentSourceSection]:
    sections: list[DocumentSourceSection] = []
    current_anchor = "introduction"
    current_heading = "Introduction"
    current_paragraphs: list[str] = []
    started = False

    def flush() -> None:
        nonlocal current_paragraphs, started
        if started:
            sections.append(
                DocumentSourceSection(
                    anchor=current_anchor,
                    heading=current_heading,
                    paragraphs=current_paragraphs,
                )
            )
        current_paragraphs = []

    for raw in version.source_anchors or []:
        anchor = str(raw.get("anchor", "")).strip()
        text_value = str(raw.get("text", "")).strip()
        if not anchor or not text_value:
            continue
        if raw.get("kind") == "heading":
            flush()
            current_anchor = anchor
            current_heading = text_value
            started = True
        else:
            if not started:
                current_anchor = anchor
                started = True
            current_paragraphs.append(text_value)
    flush()
    return sections


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AiGenerationError(f"Document AI output has an invalid {field}")
    return value.strip()


def _strings(value: object, field: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise AiGenerationError(f"Document AI output has an invalid {field}")
    return [_string(item, field) for item in value]


def _require_korean_prose(value: str, field: str, *, minimum_hangul: int) -> None:
    # Citations, numbers, URLs, dates, and redactions are intentionally preserved in their source
    # language and therefore do not count against Korean coverage. Official names may remain in
    # English, but substantive user-facing prose must still contain enough Korean that an English
    # source copy with a token Korean prefix cannot pass.
    visible = PRESERVED_SOURCE_TOKEN.sub(" ", value)
    hangul_count = len(re.findall(r"[가-힣]", visible))
    latin_count = len(re.findall(r"[A-Za-z]", visible))
    required_hangul = max(
        minimum_hangul,
        min(8, (latin_count + 7) // 8) if latin_count >= 12 else minimum_hangul,
    )
    if hangul_count < required_hangul:
        raise AiGenerationError(f"Document AI output has insufficient Korean in {field}")


def _require_english_prose(value: str, field: str, *, minimum_latin: int) -> None:
    visible = PRESERVED_SOURCE_TOKEN.sub(" ", value)
    latin_count = len(re.findall(r"[A-Za-z]", visible))
    hangul_count = len(re.findall(r"[가-힣]", visible))
    if latin_count < minimum_latin or (hangul_count >= 8 and latin_count < hangul_count):
        raise AiGenerationError(f"Document AI output has insufficient English in {field}")


def _require_analysis_prose(
    value: str,
    field: str,
    *,
    language: Literal["en", "ko"],
    minimum: int,
) -> None:
    if language == "ko":
        _require_korean_prose(value, field, minimum_hangul=minimum)
    else:
        _require_english_prose(value, field, minimum_latin=max(4, minimum * 2))


def _validate_translation(
    output: dict[str, Any],
    source_sections: list[DocumentSourceSection],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw_sections = output.get("sections")
    if not isinstance(raw_sections, list) or len(raw_sections) != len(source_sections):
        raise AiGenerationError("Translation section structure did not match the source")
    translated: list[dict[str, Any]] = []
    for index, (raw, source) in enumerate(zip(raw_sections, source_sections, strict=True)):
        if not isinstance(raw, dict):
            raise AiGenerationError("Translation section structure did not match the source")
        anchor = _string(raw.get("anchor"), f"sections[{index}].anchor")
        if anchor != source.anchor:
            raise AiGenerationError("Translation anchor did not match the source")
        heading = _string(raw.get("heading"), f"sections[{index}].heading")
        paragraphs = _strings(raw.get("paragraphs"), f"sections[{index}].paragraphs")
        if len(paragraphs) != len(source.paragraphs):
            raise AiGenerationError("Translation paragraph structure did not match the source")
        source_units = [source.heading, *source.paragraphs]
        translated_units = [heading, *paragraphs]
        for source_unit, translated_unit in zip(source_units, translated_units, strict=True):
            # Re-running the English token regex over Korean text is not reliable: its numeric
            # branch uses a word boundary, while an exactly restored digit can legitimately sit
            # beside Hangul (both are Unicode word characters). Compare exact token identity and
            # multiplicity within the paired immutable unit instead. This remains fail-closed for
            # omission and cross-paragraph movement; the generator's placeholder contract
            # separately rejects duplication before these plain-text sections are reconstructed.
            expected_tokens = protected_token_multiset(source_unit)
            actual_tokens = protected_token_multiset(translated_unit)
            if actual_tokens != expected_tokens:
                raise AiGenerationError(
                    "Translation did not preserve source token identity or multiplicity"
                )
        translated.append({"anchor": anchor, "heading": heading, "paragraphs": paragraphs})
    return translated, {
        "passed": True,
        "checks": [
            "section_order",
            "source_anchors",
            "paragraph_boundaries",
            "citations_numbers_redactions",
        ],
        "section_count": len(translated),
    }


def _validate_analysis(
    output: dict[str, Any],
    source_sections: list[DocumentSourceSection],
    *,
    language: Literal["en", "ko"] = "ko",
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    valid_anchors = {section.anchor for section in source_sections}
    executive_summary = _string(output.get("executive_summary"), "executive_summary")
    _require_analysis_prose(executive_summary, "executive_summary", language=language, minimum=4)
    raw_attention = output.get("attention_points")
    if not isinstance(raw_attention, list) or not raw_attention:
        raise AiGenerationError("Document AI output has invalid attention points")
    attention_points: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_attention):
        if not isinstance(raw, dict):
            raise AiGenerationError("Document AI output has invalid attention points")
        anchors = _strings(
            raw.get("source_anchors"),
            f"attention_points[{index}].source_anchors",
            allow_empty=False,
        )
        if not set(anchors).issubset(valid_anchors):
            raise AiGenerationError("Attention point referenced an unknown source anchor")
        title = _string(raw.get("title"), f"attention_points[{index}].title")
        rationale = _string(raw.get("rationale"), f"attention_points[{index}].rationale")
        _require_analysis_prose(
            title, f"attention_points[{index}].title", language=language, minimum=2
        )
        _require_analysis_prose(
            rationale, f"attention_points[{index}].rationale", language=language, minimum=4
        )
        attention_points.append({"title": title, "rationale": rationale, "source_anchors": anchors})
    comparison_questions = _strings(
        output.get("comparison_questions"), "comparison_questions", allow_empty=False
    )
    if any(
        "?" not in item and (language != "ko" or "까요" not in item)
        for item in comparison_questions
    ):
        raise AiGenerationError("Internal comparison items must remain neutral questions")
    for index, question in enumerate(comparison_questions):
        _require_analysis_prose(
            question, f"comparison_questions[{index}]", language=language, minimum=4
        )
    # Require the model field for schema discipline, but persist a controlled disclaimer so
    # untrusted source content cannot weaken or rewrite this safety boundary.
    supplied_disclaimer = _string(output.get("disclaimer"), "disclaimer")
    _require_analysis_prose(supplied_disclaimer, "disclaimer", language=language, minimum=4)
    disclaimer = NEUTRAL_ANALYSIS_DISCLAIMERS[language]

    raw_findings = output.get("findings")
    if not isinstance(raw_findings, list) or not raw_findings:
        raise AiGenerationError("Document AI output has invalid findings")
    findings: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_findings):
        if not isinstance(raw, dict):
            raise AiGenerationError("Document AI output has invalid findings")
        anchors = _strings(
            raw.get("evidence_anchors"),
            f"findings[{index}].evidence_anchors",
            allow_empty=False,
        )
        if not set(anchors).issubset(valid_anchors):
            raise AiGenerationError("Finding referenced an unknown source anchor")
        attention_level = _string(raw.get("attention_level"), f"findings[{index}].attention_level")
        if attention_level not in {"high", "medium", "routine"}:
            raise AiGenerationError("Finding has an invalid attention level")
        title = _string(raw.get("title"), f"findings[{index}].title")
        finding_text = _string(raw.get("finding"), f"findings[{index}].finding")
        requested_actions = _strings(
            raw.get("requested_actions"), f"findings[{index}].requested_actions"
        )
        _require_analysis_prose(
            title, f"findings[{index}].title", language=language, minimum=2
        )
        _require_analysis_prose(
            finding_text, f"findings[{index}].finding", language=language, minimum=4
        )
        for action_index, action in enumerate(requested_actions):
            _require_analysis_prose(
                action,
                f"findings[{index}].requested_actions[{action_index}]",
                language=language,
                minimum=4,
            )
        findings.append(
            {
                "label": _string(raw.get("label"), f"findings[{index}].label"),
                "title": title,
                "finding": finding_text,
                "requested_actions": requested_actions,
                "categories": _strings(raw.get("categories"), f"findings[{index}].categories"),
                "attention_level": attention_level,
                "evidence_anchors": anchors,
                "regulatory_references": _strings(
                    raw.get("regulatory_references"),
                    f"findings[{index}].regulatory_references",
                ),
            }
        )
    summary = {
        "executive_summary": executive_summary,
        "attention_points": attention_points,
        "comparison_questions": comparison_questions,
        "disclaimer": disclaimer,
    }
    report = {
        "passed": True,
        "checks": [
            "schema",
            "current_version_anchors",
            "neutral_comparison_questions",
            f"{language}_user_facing_prose",
        ],
        "finding_count": len(findings),
        "attention_point_count": len(attention_points),
    }
    return summary, findings, report


def _tokens(value: str) -> set[str]:
    tokens = {
        token
        for match in TOKEN_PATTERN.finditer(value)
        if (token := match.group(0).casefold()) not in STOPWORDS
    }
    aliases = {
        alias
        for token in tokens
        for korean_term, mapped in QUERY_TOKEN_ALIASES.items()
        if token.startswith(korean_term)
        for alias in mapped
    }
    return tokens | aliases


def _query_tokens(value: str) -> set[str]:
    tokens = _tokens(value)
    for token in tuple(tokens):
        for particle in KOREAN_QUERY_PARTICLES:
            if not token.endswith(particle):
                continue
            acronym = token[: -len(particle)]
            if acronym in LATIN_REGULATORY_ACRONYMS:
                tokens.add(acronym)
            break
    compact_value = re.sub(r"\s+", "", value.casefold())
    tokens.update(
        alias
        for concept, mapped in QUERY_CONCEPT_ALIASES.items()
        if concept in compact_value
        for alias in mapped
    )
    return tokens


def _acl_allows(acl: dict[str, object] | None, principal: Principal) -> bool:
    roles = set(str(item) for item in ((acl or {}).get("roles") or []))
    if not roles or "viewer" in roles:
        return True
    return bool(roles.intersection(principal.roles))


async def _derived_query_hints(
    session: AsyncSession,
    *,
    version_ids: set[str],
    question_tokens: set[str],
) -> tuple[set[str], set[str], str | None]:
    """Return pointers into source chunks; derived text never becomes cited evidence."""
    if not version_ids:
        return set(), set(), None
    versions = list(
        (
            await session.scalars(
                select(DocumentVersion).where(DocumentVersion.id.in_(version_ids))
            )
        ).all()
    )
    candidates: list[tuple[str, set[str]]] = []
    context_packages: list[dict[str, Any]] = []
    for version in versions:
        summary, findings = await _cached_analysis(session, version)
        if not summary:
            continue
        structured = summary.structured_output or {}
        context_packages.append(
            {
                "document_version_id": version.id,
                "executive_summary": summary.executive_summary,
                "attention_points": structured.get("attention_points", []),
                "comparison_questions": structured.get("comparison_questions", []),
                "disclaimer": structured.get("disclaimer", ""),
                "findings": [
                    {
                        "finding": finding.finding_text,
                        "requested_actions": finding.fda_requested_actions or [],
                        "categories": finding.categories or [],
                        "regulatory_references": finding.regulatory_references or [],
                        "evidence_anchors": [
                            item.get("source_anchor")
                            for item in (finding.evidence or [])
                            if item.get("source_anchor")
                        ],
                    }
                    for finding in findings
                ],
            }
        )
        for point in structured.get("attention_points", []):
            if not isinstance(point, dict):
                continue
            anchors = {
                str(value) for value in point.get("source_anchors", []) if isinstance(value, str)
            }
            candidates.append(
                (
                    " ".join([str(point.get("title", "")), str(point.get("rationale", ""))]),
                    anchors,
                )
            )
        for finding in findings:
            anchors = {
                str(item.get("source_anchor"))
                for item in (finding.evidence or [])
                if item.get("source_anchor")
            }
            candidates.append(
                (
                    " ".join(
                        [
                            finding.finding_text,
                            *(finding.categories or []),
                            *(finding.regulatory_references or []),
                            *(finding.fda_requested_actions or []),
                        ]
                    ),
                    anchors,
                )
            )
    related = [item for item in candidates if question_tokens.intersection(_query_tokens(item[0]))]
    selected = related or candidates
    priority_anchors = {anchor for _text, anchors in selected for anchor in anchors}
    expansion_tokens = {
        token for text_value, _anchors in selected for token in _query_tokens(text_value)
    }
    derived_context = None
    if context_packages:
        serialized = json.dumps(context_packages, ensure_ascii=False, separators=(",", ":"))
        derived_context = (
            "UNTRUSTED DERIVED ARTIFACT CONTEXT. This cached Korean summary/findings package "
            "is query context only, not FDA evidence or authority. Never cite it; verify every "
            f"claim against authorized original passages:\n{serialized[:40_000]}"
        )
    return priority_anchors, expansion_tokens, derived_context


@router.get("/taxonomy", tags=["Taxonomy"])
async def get_taxonomy(
    _principal: Principal = Depends(view_principal),
) -> dict[str, object]:
    return taxonomy_document()


async def _artifact_context(
    session: AsyncSession, letter_id: UUID
) -> tuple[WarningLetter, DocumentVersion, list[DocumentSourceSection]]:
    letter = await session.scalar(
        select(WarningLetter).where(
            WarningLetter.id == str(letter_id),
            WarningLetter.current_in_scope.is_(True),
            WarningLetter.scope_status == ScopeStatus.IN_SCOPE_DRUGS.value,
        )
    )
    if not letter or not letter.current_version_id:
        raise HTTPException(status_code=404, detail="Drug warning letter not found")
    version = await session.get(DocumentVersion, letter.current_version_id)
    if not version or not version.normalized_text:
        raise HTTPException(status_code=409, detail="Current FDA source text is unavailable")
    sections = _source_sections(version)
    if not sections:
        raise HTTPException(status_code=409, detail="Current FDA source sections are unavailable")
    return letter, version, sections


async def _cached_translation(
    session: AsyncSession,
    version: DocumentVersion,
    *,
    prompt_version: str,
) -> DocumentTranslation | None:
    return await session.scalar(
        select(DocumentTranslation)
        .where(
            DocumentTranslation.document_version_id == version.id,
            DocumentTranslation.language == "ko",
            DocumentTranslation.source_hash == version.canonical_hash,
            DocumentTranslation.schema_version == DOCUMENT_TRANSLATION_SCHEMA_VERSION,
            DocumentTranslation.prompt_version == prompt_version,
        )
        .order_by(DocumentTranslation.created_at.desc(), DocumentTranslation.id)
    )


async def _cached_analysis(
    session: AsyncSession,
    version: DocumentVersion,
    *,
    language: Literal["en", "ko"] = "ko",
    prompt_version: str | None = None,
) -> tuple[AiSummary | None, list[Finding]]:
    conditions = [
        AiSummary.document_version_id == version.id,
        AiSummary.language == language,
        AiSummary.schema_version == DOCUMENT_ANALYSIS_SCHEMA_VERSION,
    ]
    if prompt_version:
        conditions.append(AiSummary.prompt_version == prompt_version)
    summaries = list(
        (
            await session.scalars(
                select(AiSummary)
                .where(*conditions)
                .order_by(AiSummary.created_at.desc(), AiSummary.revision.desc())
            )
        ).all()
    )
    summary = next(
        (
            item
            for item in summaries
            if str((item.structured_output or {}).get("source_hash", "")) == version.canonical_hash
        ),
        None,
    )
    if not summary:
        return None, []
    findings = list(
        (
            await session.scalars(
                select(Finding)
                .where(Finding.summary_id == summary.id)
                .order_by(Finding.created_at, Finding.id)
            )
        ).all()
    )
    return summary, findings


def _persisted_analysis_output(summary: AiSummary, findings: list[Finding]) -> dict[str, Any]:
    structured = summary.structured_output or {}
    return {
        "executive_summary": summary.executive_summary,
        "attention_points": structured.get("attention_points", []),
        "comparison_questions": structured.get("comparison_questions", []),
        "disclaimer": structured.get("disclaimer", ""),
        "findings": [
            {
                "label": finding.label,
                "title": next(
                    (
                        str(item.get("title"))
                        for item in (finding.evidence or [])
                        if item.get("title")
                    ),
                    finding.label,
                ),
                "finding": finding.finding_text,
                "requested_actions": finding.fda_requested_actions or [],
                "categories": finding.categories or [],
                "attention_level": finding.attention_level or "routine",
                "evidence_anchors": [
                    str(item["source_anchor"])
                    for item in (finding.evidence or [])
                    if item.get("source_anchor")
                ],
                "regulatory_references": finding.regulatory_references or [],
            }
            for finding in findings
        ],
    }


async def _validated_legacy_analysis(
    session: AsyncSession,
    version: DocumentVersion,
    source_sections: list[DocumentSourceSection],
    *,
    language: Literal["en", "ko"],
) -> (
    tuple[
        AiSummary,
        list[Finding],
        dict[str, Any],
        list[dict[str, Any]],
        dict[str, Any],
    ]
    | None
):
    """Find legacy current-source artifacts that satisfy the stronger v2 contract unchanged."""

    candidates = list(
        (
            await session.scalars(
                select(AiSummary)
                .where(
                    AiSummary.document_version_id == version.id,
                    AiSummary.language == language,
                    AiSummary.schema_version != DOCUMENT_ANALYSIS_SCHEMA_VERSION,
                )
                .order_by(AiSummary.created_at.desc(), AiSummary.revision.desc())
            )
        ).all()
    )
    for legacy in candidates:
        if str((legacy.structured_output or {}).get("source_hash", "")) != version.canonical_hash:
            continue
        legacy_findings = list(
            (
                await session.scalars(
                    select(Finding)
                    .where(Finding.summary_id == legacy.id)
                    .order_by(Finding.created_at, Finding.id)
                )
            ).all()
        )
        try:
            summary_content, validated_findings, report = _validate_analysis(
                _persisted_analysis_output(legacy, legacy_findings),
                source_sections,
                language=language,
            )
        except AiGenerationError:
            continue
        return legacy, legacy_findings, summary_content, validated_findings, report
    return None


async def _persist_analysis_artifact(
    session: AsyncSession,
    *,
    version_id: str,
    source_hash: str,
    source_url: str,
    summary_content: dict[str, Any],
    generated_findings: list[dict[str, Any]],
    validation_report: dict[str, Any],
    provider: str,
    model_id: str,
    prompt_version: str,
    taxonomy_version: str,
    language: Literal["en", "ko"],
    parent_summary: AiSummary | None = None,
    source_findings: list[Finding] | None = None,
) -> tuple[AiSummary, list[Finding]]:
    last_revision = await session.scalar(
        select(AiSummary.revision)
        .where(
            AiSummary.document_version_id == version_id,
            AiSummary.language == language,
        )
        .order_by(AiSummary.revision.desc())
    )
    summary = AiSummary(
        document_version_id=version_id,
        parent_summary_id=parent_summary.id if parent_summary else None,
        revision=int(last_revision or 0) + 1,
        language=language,
        executive_summary=summary_content["executive_summary"],
        structured_output={
            **summary_content,
            "source_hash": source_hash,
            "artifact_schema_version": DOCUMENT_ANALYSIS_SCHEMA_VERSION,
        },
        validation_report=validation_report,
        provider=provider,
        model_id=model_id,
        prompt_version=prompt_version,
        schema_version=DOCUMENT_ANALYSIS_SCHEMA_VERSION,
        taxonomy_version=taxonomy_version,
        review_state=(parent_summary.review_state if parent_summary else ReviewState.PENDING.value),
        reviewer_id=parent_summary.reviewer_id if parent_summary else None,
        reviewed_at=parent_summary.reviewed_at if parent_summary else None,
    )
    session.add(summary)
    await session.flush()
    findings: list[Finding] = []
    for index, generated in enumerate(generated_findings):
        source_finding = source_findings[index] if source_findings else None
        evidence = (
            [dict(item) for item in (source_finding.evidence or [])]
            if source_finding
            else [
                {
                    "source_anchor": anchor,
                    "official_url": source_url,
                    "title": generated["title"],
                }
                for anchor in generated["evidence_anchors"]
            ]
        )
        finding = Finding(
            document_version_id=version_id,
            summary_id=summary.id,
            label=generated["label"],
            categories=generated["categories"],
            process_lenses=list(source_finding.process_lenses or []) if source_finding else [],
            finding_text=generated["finding"],
            regulatory_references=generated["regulatory_references"],
            evidence=evidence,
            fda_requested_actions=generated["requested_actions"],
            comparison_points=(
                list(source_finding.comparison_points or [])
                if source_finding
                else summary_content["comparison_questions"]
            ),
            attention_level=generated["attention_level"],
            confidence=source_finding.confidence if source_finding else None,
            review_state=(
                source_finding.review_state if source_finding else ReviewState.PENDING.value
            ),
        )
        session.add(finding)
        findings.append(finding)
    await session.flush()
    return summary, findings


def _document_generator(request: Request, settings: Settings) -> DocumentAiGenerator | None:
    configured = getattr(request.app.state, "document_ai_generator", None)
    return configured or build_document_ai_generator(settings)


@asynccontextmanager
async def _artifact_generation_guard(
    request: Request,
    session: AsyncSession,
    *,
    key: str,
):
    """Coalesce equal work while allowing unrelated artifacts to run concurrently."""

    locks: dict[str, asyncio.Lock] | None = getattr(
        request.app.state, "document_ai_artifact_locks", None
    )
    if locks is None:
        locks = {}
        request.app.state.document_ai_artifact_locks = locks
    lock = locks.setdefault(key, asyncio.Lock())
    async with lock:
        bind = session.get_bind()
        if bind.dialect.name == "postgresql":
            lock_id = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big") % (2**63 - 1)
            await session.execute(select(func.pg_advisory_xact_lock(lock_id)))
        yield


@router.post(
    "/letters/{letter_id}/ai-artifacts/{artifact_type}",
    response_model=LetterAiArtifactResponse,
    tags=["Letters"],
)
async def generate_letter_ai_artifact(
    letter_id: UUID,
    artifact_type: Literal["translation", "findings", "summary"],
    request: Request,
    language: Literal["en", "ko"] = Query(default="ko"),
    principal: Principal = Depends(rag_principal),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> LetterAiArtifactResponse:
    if artifact_type == "translation" and language != "ko":
        raise HTTPException(status_code=422, detail="Full-letter translation supports Korean only")
    request.app.state.rate_limiter.check(
        f"document-ai:{principal.subject}", settings.document_ai_rate_limit_per_minute
    )
    artifact_family = "translation" if artifact_type == "translation" else f"analysis:{language}"
    guard_key = f"{letter_id}:{artifact_family}"
    async with _artifact_generation_guard(request, session, key=guard_key):
        letter, version, source_sections = await _artifact_context(session, letter_id)
        version_id = version.id
        source_hash = version.canonical_hash
        source_url = letter.canonical_url
        cached: LetterAiArtifactResponse | None = None
        if artifact_type == "translation":
            translation = await _cached_translation(
                session,
                version,
                prompt_version=settings.document_translation_prompt_version,
            )
            if translation:
                cached = translation_artifact_response(translation)
        else:
            summary, findings = await _cached_analysis(
                session,
                version,
                language=language,
                prompt_version=settings.document_ai_prompt_version,
            )
            if summary:
                cached = analysis_artifact_response(
                    summary, findings, artifact_type=artifact_type
                )
        if cached:
            add_audit_event(
                session,
                principal=principal,
                request_id=request.state.request_id,
                operation=f"letter.ai_artifact.{artifact_type}",
                object_type="document_version",
                object_id=version_id,
                application_version=settings.app_version,
                after={
                    "artifact_id": str(cached.id),
                    "artifact_type": artifact_type,
                    "language": cached.language,
                    "cached": True,
                    "source_hash": source_hash,
                    "provider": cached.provider,
                    "model_id": cached.model_id,
                    "prompt_version": cached.prompt_version,
                },
            )
            await session.commit()
            return cached

        if artifact_type in {"findings", "summary"}:
            legacy = await _validated_legacy_analysis(
                session, version, source_sections, language=language
            )
            if legacy:
                (
                    legacy_summary,
                    legacy_findings,
                    summary_content,
                    validated_findings,
                    validation_report,
                ) = legacy
                promoted_summary, promoted_findings = await _persist_analysis_artifact(
                    session,
                    version_id=version_id,
                    source_hash=source_hash,
                    source_url=source_url,
                    summary_content=summary_content,
                    generated_findings=validated_findings,
                    validation_report={
                        **validation_report,
                        "promoted_from_summary_id": legacy_summary.id,
                        "promoted_from_schema_version": legacy_summary.schema_version,
                    },
                    provider=legacy_summary.provider,
                    model_id=legacy_summary.model_id,
                    prompt_version=settings.document_ai_prompt_version,
                    taxonomy_version=legacy_summary.taxonomy_version,
                    language=language,
                    parent_summary=legacy_summary,
                    source_findings=legacy_findings,
                )
                artifact = analysis_artifact_response(
                    promoted_summary,
                    promoted_findings,
                    artifact_type=artifact_type,
                )
                add_audit_event(
                    session,
                    principal=principal,
                    request_id=request.state.request_id,
                    operation=f"letter.ai_artifact.{artifact_type}",
                    object_type="document_version",
                    object_id=version_id,
                    application_version=settings.app_version,
                    after={
                        "artifact_id": str(artifact.id),
                        "artifact_type": artifact_type,
                        "language": language,
                        "cached": False,
                        "promoted": True,
                        "promoted_from_summary_id": legacy_summary.id,
                        "source_hash": source_hash,
                        "provider": artifact.provider,
                        "model_id": artifact.model_id,
                        "prompt_version": artifact.prompt_version,
                    },
                )
                await session.commit()
                return artifact

        generator = _document_generator(request, settings)
        if not generator:
            raise HTTPException(status_code=503, detail="Document AI generation is not configured")
        try:
            if artifact_type == "translation":
                output = await generator.generate_translation(source_sections=source_sections)
                translated_sections, validation_report = _validate_translation(
                    output, source_sections
                )
                translation = DocumentTranslation(
                    document_version_id=version_id,
                    language="ko",
                    source_hash=source_hash,
                    translated_sections=translated_sections,
                    validation_report=validation_report,
                    provider=generator.provider,
                    model_id=generator.model_id,
                    prompt_version=generator.prompt_version,
                    schema_version=DOCUMENT_TRANSLATION_SCHEMA_VERSION,
                )
                session.add(translation)
                await session.flush()
                artifact = translation_artifact_response(translation)
            else:
                validation_feedback: str | None = None
                for validation_attempt in range(1, settings.document_ai_validation_attempts + 1):
                    output = await generator.generate_letter_analysis(
                        company_name=letter.company_name,
                        source_sections=source_sections,
                        language=language,
                        validation_feedback=validation_feedback,
                    )
                    try:
                        summary_content, generated_findings, validation_report = (
                            _validate_analysis(output, source_sections, language=language)
                        )
                        validation_report["generation_attempts"] = validation_attempt
                        break
                    except AiGenerationError as exc:
                        validation_feedback = str(exc)
                        logger.warning(
                            "document_analysis_validation_failed language=%s attempt=%d/%d "
                            "model=%s reason=%s",
                            language,
                            validation_attempt,
                            settings.document_ai_validation_attempts,
                            generator.model_id,
                            validation_feedback[:160],
                        )
                        if validation_attempt == settings.document_ai_validation_attempts:
                            raise
                summary, findings = await _persist_analysis_artifact(
                    session,
                    version_id=version_id,
                    source_hash=source_hash,
                    source_url=source_url,
                    summary_content=summary_content,
                    generated_findings=generated_findings,
                    validation_report=validation_report,
                    provider=generator.provider,
                    model_id=generator.model_id,
                    prompt_version=generator.prompt_version,
                    taxonomy_version=settings.taxonomy_version,
                    language=language,
                )
                artifact = analysis_artifact_response(
                    summary, findings, artifact_type=artifact_type
                )
        except AiGenerationError:
            await session.rollback()
            add_audit_event(
                session,
                principal=principal,
                request_id=request.state.request_id,
                operation=f"letter.ai_artifact.{artifact_type}",
                object_type="document_version",
                object_id=version_id,
                application_version=settings.app_version,
                result="failed",
                reason="provider_or_validation_failure",
                context={
                    "artifact_type": artifact_type,
                    "language": language,
                    "source_hash": source_hash,
                },
            )
            await session.commit()
            raise HTTPException(
                status_code=502, detail="Document AI output could not be safely validated"
            ) from None

        add_audit_event(
            session,
            principal=principal,
            request_id=request.state.request_id,
            operation=f"letter.ai_artifact.{artifact_type}",
            object_type="document_version",
            object_id=version_id,
            application_version=settings.app_version,
            after={
                "artifact_id": str(artifact.id),
                "artifact_type": artifact_type,
                "language": artifact.language,
                "cached": False,
                "source_hash": source_hash,
                "provider": artifact.provider,
                "model_id": artifact.model_id,
                "prompt_version": artifact.prompt_version,
            },
        )
        await session.commit()
        return artifact


def _question_language(question: str) -> Literal["en", "ko"]:
    """Infer Korean or English from the user's wording, not the portal locale.

    A question may legitimately mix a Korean company name with English prose, or English
    company and regulatory names with Korean prose. Hangul therefore wins unless Latin text
    clearly dominates it by more than two to one.
    """

    hangul_count = len(HANGUL_CHARACTER_PATTERN.findall(question))
    if hangul_count == 0:
        return "en"
    latin_count = len(LATIN_CHARACTER_PATTERN.findall(question))
    return "en" if latin_count > hangul_count * 2 else "ko"


def _effective_language(language: str, question: str) -> Literal["en", "ko"]:
    return language if language in {"en", "ko"} else _question_language(question)


def _deterministic_no_retrieval_answer(plan: RagPlan, language: str) -> str:
    if plan.deterministic_response == "scope_required":
        return (
            "내부 파이프라인 또는 워크플로와 비교하려면 먼저 비교할 FDA 경고장을 "
            "선택해 주세요. 선택된 원문 근거로 점검 질문은 만들 수 있지만 규정 준수 "
            "여부를 단정하지는 않습니다."
            if language == "ko"
            else (
                "Select the FDA warning letter to compare with the internal pipeline or "
                "workflow. I can frame evidence-grounded review questions, but I will not "
                "make a compliance conclusion."
            )
        )
    if plan.deterministic_response == "out_of_scope":
        return (
            "이 서비스는 FDA 의약품 경고장 조사에만 답변합니다. 경고장, 지적 사항, "
            "발행 정보, 규정 근거 또는 내부 비교 검토에 관해 질문해 주세요."
            if language == "ko"
            else (
                "This service is limited to FDA Drug warning-letter research. Ask about a "
                "letter, finding, source metadata, regulatory evidence, or a neutral internal "
                "comparison review."
            )
        )
    return (
        "FDA 의약품 경고장을 검색하고, 특정 경고장 근거를 설명하며, 여러 경고장의 "
        "패턴을 비교하고, 원문 인용과 함께 내부 점검 질문을 정리할 수 있습니다. 특정 "
        "경고장을 열고 질문하면 이후 질문도 그 문서 범위에서 이어집니다."
        if language == "ko"
        else (
            "I can search FDA Drug warning letters, answer from one selected letter, compare "
            "patterns across letters, and frame neutral internal-review questions with official "
            "citations. Open a letter before asking to keep follow-ups scoped to that document."
        )
    )


def _model_unavailable_no_retrieval_answer(language: str) -> str:
    return (
        "이 질문에는 문서 검색이 필요하지 않지만 현재 AI 모델 응답을 안전하게 사용할 수 "
        "없습니다. 잠시 후 다시 시도하거나, 공식 근거가 필요한 질문이라면 근거 범위를 "
        "자동 또는 전체 코퍼스로 변경해 주세요."
        if language == "ko"
        else (
            "This question does not require document search, but a safe AI model response is "
            "not currently available. Try again shortly, or choose Auto or All letters when "
            "official evidence is required."
        )
    )


def _company_filters(payload: RagQueryRequest) -> list[str]:
    return [
        *payload.filters.companies,
        *([payload.filters.company] if payload.filters.company else []),
    ]


def _company_name_tokens(value: str) -> tuple[str, ...]:
    return tuple(COMPANY_NAME_TOKEN_PATTERN.findall(value.casefold()))


def _contains_token_sequence(
    tokens: tuple[str, ...],
    candidate: tuple[str, ...],
) -> bool:
    if not candidate or len(candidate) > len(tokens):
        return False
    width = len(candidate)
    return any(
        tokens[index : index + width] == candidate for index in range(len(tokens) - width + 1)
    )


def _company_name_matches_question(company_name: str, question: str) -> bool:
    """Match an explicit legal name or a conservative leading company alias.

    Company names and questions are token-normalized so punctuation such as ``Sci-tech``
    versus ``Sci tech`` and corporate suffix punctuation do not affect matching. Short
    aliases must be a contiguous leading prefix with at least two tokens. The only
    supported one-token alias is the complete legal stem of a one-word company, such as
    ``Pfizer Inc.``; generic industry words never qualify on their own.
    """

    company_tokens = _company_name_tokens(company_name)
    question_tokens = _company_name_tokens(question)
    if not company_tokens or not question_tokens:
        return False

    # Preserve full legal-name resolution while making it punctuation-insensitive and
    # token-bounded ("Acme Co., Ltd." will not match as part of a longer word).
    if _contains_token_sequence(question_tokens, company_tokens):
        return True

    legal_stem = list(company_tokens)
    while legal_stem and legal_stem[-1] in COMPANY_CORPORATE_SUFFIX_TOKENS:
        legal_stem.pop()
    if not legal_stem:
        return False

    if len(legal_stem) == 1:
        token = legal_stem[0]
        return (
            len(token) >= 4
            and token not in COMPANY_GENERIC_ALIAS_TOKENS
            and _contains_token_sequence(question_tokens, (token,))
        )

    # A two-or-more-token prefix supports familiar names such as "Tianjin Kilo" without
    # allowing a broad single token such as "Tianjin" or "Pharmaceutical" to seize scope.
    for width in range(2, len(legal_stem) + 1):
        alias = tuple(legal_stem[:width])
        if not any(token not in COMPANY_GENERIC_ALIAS_TOKENS for token in alias):
            continue
        if sum(len(token) for token in alias) < 6:
            continue
        if _contains_token_sequence(question_tokens, alias):
            return True
    return False


def _apply_warning_sql_filters(statement: Any, payload: RagQueryRequest) -> Any:
    filters = payload.filters
    companies = _company_filters(payload)
    if companies:
        escaped_companies = [
            value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            for value in companies
        ]
        statement = statement.where(
            or_(
                *(
                    WarningLetter.company_name.ilike(f"%{value}%", escape="\\")
                    for value in escaped_companies
                )
            )
        )
    if filters.issue_date_from:
        statement = statement.where(WarningLetter.issue_date >= filters.issue_date_from)
    if filters.issue_date_to:
        statement = statement.where(WarningLetter.issue_date <= filters.issue_date_to)
    if filters.posted_from:
        statement = statement.where(WarningLetter.posted_date >= filters.posted_from)
    if filters.posted_to:
        statement = statement.where(WarningLetter.posted_date <= filters.posted_to)
    return statement


async def _authorized_letter_sources(
    session: AsyncSession,
    *,
    letter_ids: tuple[str, ...] | list[str],
    principal: Principal,
    chunker_version: str,
) -> dict[str, tuple[DocumentChunk, Document, DocumentVersion]]:
    """Return one current, available, ACL-authorized source chunk per letter."""

    normalized_ids = tuple(dict.fromkeys(str(item) for item in letter_ids if item))
    if not normalized_ids:
        return {}
    rows = (
        await session.execute(
            select(DocumentChunk, Document, DocumentVersion)
            .join(WarningLetter, WarningLetter.id == DocumentChunk.warning_letter_id)
            .join(DocumentVersion, DocumentVersion.id == DocumentChunk.document_version_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(
                WarningLetter.id.in_(normalized_ids),
                WarningLetter.current_in_scope.is_(True),
                WarningLetter.scope_status == ScopeStatus.IN_SCOPE_DRUGS.value,
                WarningLetter.current_version_id == DocumentVersion.id,
                Document.warning_letter_id == WarningLetter.id,
                Document.current_version_id == DocumentVersion.id,
                Document.current_in_scope.is_(True),
                Document.source_available.is_(True),
                DocumentVersion.scope_status == ScopeStatus.IN_SCOPE_DRUGS.value,
                DocumentChunk.corpus_id == "fda-drugs",
                DocumentChunk.chunker_version == chunker_version,
            )
            .order_by(DocumentChunk.warning_letter_id, DocumentChunk.ordinal, DocumentChunk.id)
        )
    ).all()
    sources: dict[str, tuple[DocumentChunk, Document, DocumentVersion]] = {}
    for chunk, document, version in rows:
        if chunk.warning_letter_id not in sources and _acl_allows(chunk.acl, principal):
            sources[chunk.warning_letter_id] = (chunk, document, version)
    return sources


async def _resolve_question_letter_ids(
    session: AsyncSession,
    payload: RagQueryRequest,
    *,
    principal: Principal,
    chunker_version: str,
) -> tuple[str, ...]:
    statement = select(
        WarningLetter.id,
        WarningLetter.company_name,
        WarningLetter.marcs_cms_number,
    ).where(
        WarningLetter.current_in_scope.is_(True),
        WarningLetter.scope_status == ScopeStatus.IN_SCOPE_DRUGS.value,
    )
    statement = _apply_warning_sql_filters(statement, payload)
    rows = (await session.execute(statement)).all()
    if _company_filters(payload):
        candidates = tuple(row.id for row in rows)
    else:
        candidates = tuple(
            row.id
            for row in rows
            if _company_name_matches_question(str(row.company_name), payload.question)
            or (
                (marcs := str(row.marcs_cms_number or "").strip().casefold())
                and marcs in payload.question.casefold()
            )
        )
    authorized = await _authorized_letter_sources(
        session,
        letter_ids=candidates,
        principal=principal,
        chunker_version=chunker_version,
    )
    return tuple(letter_id for letter_id in candidates if letter_id in authorized)


async def _metadata_answer(
    session: AsyncSession,
    *,
    payload: RagQueryRequest,
    plan: RagPlan,
    language: str,
    principal: Principal,
    chunker_version: str,
) -> tuple[str, list[CitationResponse], str]:
    statement = select(WarningLetter).where(
        WarningLetter.current_in_scope.is_(True),
        WarningLetter.scope_status == ScopeStatus.IN_SCOPE_DRUGS.value,
    )
    if plan.letter_ids:
        statement = statement.where(WarningLetter.id.in_(plan.letter_ids))
    statement = _apply_warning_sql_filters(statement, payload)
    office_filters = [
        *payload.filters.issuing_offices,
        *([payload.filters.issuing_office] if payload.filters.issuing_office else []),
    ]
    rows = list(
        (
            await session.scalars(
                statement.order_by(
                    WarningLetter.posted_date.desc().nullslast(),
                    WarningLetter.issue_date.desc().nullslast(),
                    WarningLetter.id,
                )
            )
        ).all()
    )
    if office_filters:
        rows = [
            letter
            for letter in rows
            if any(
                requested.casefold() in office.casefold()
                for requested in office_filters
                for office in (letter.issuing_offices or [])
            )
        ]
    authorized_sources = await _authorized_letter_sources(
        session,
        letter_ids=[letter.id for letter in rows],
        principal=principal,
        chunker_version=chunker_version,
    )
    rows = [letter for letter in rows if letter.id in authorized_sources]
    total = len(rows)
    displayed = rows[: payload.max_sources]
    citations: list[CitationResponse] = []
    for letter in displayed:
        chunk, document, version = authorized_sources[letter.id]
        citations.append(
            CitationResponse(
                chunk_id=chunk.id,
                warning_letter_id=letter.id,
                company_name=letter.company_name,
                title=document.title,
                document_type=document.document_type,
                issue_date=letter.issue_date,
                posted_date=letter.posted_date,
                source_anchor=chunk.source_anchor,
                excerpt=chunk.content[:800],
                source_url=document.canonical_url,
                score=1.0,
                document_version_id=chunk.document_version_id,
                source_version=f"v{version.version_number}",
                source_hash=version.canonical_hash,
            )
        )
    if not displayed:
        answer = (
            "현재 필터와 문서 범위에 맞는 FDA 의약품 경고장 메타데이터가 없습니다."
            if language == "ko"
            else "No FDA Drug warning-letter metadata matched the current filters and scope."
        )
        return answer, citations, "insufficient"
    lines: list[str] = []
    for letter in displayed:
        unknown = "미확인" if language == "ko" else "Not specified"
        issue = letter.issue_date.isoformat() if letter.issue_date else unknown
        posted = letter.posted_date.isoformat() if letter.posted_date else unknown
        country = letter.country or ("미확인" if language == "ko" else "Not specified")
        offices = ", ".join(letter.issuing_offices or []) or (
            "미확인" if language == "ko" else "Not specified"
        )
        if language == "ko":
            lines.append(
                f"- {letter.company_name}: 발행일 {issue}, 게시일 {posted}, 수신인 국가 "
                f"{country}, 발행 부서 {offices}, FDA 원문 {letter.canonical_url}"
            )
        else:
            lines.append(
                f"- {letter.company_name}: issued {issue}, posted {posted}, recipient country "
                f"{country}, issuing office {offices}, FDA source {letter.canonical_url}"
            )
    prefix = (
        f"조건에 맞는 FDA 의약품 경고장은 총 {total}건입니다."
        if language == "ko"
        else f"There are {total} FDA Drug warning letters matching the current scope."
    )
    return f"{prefix}\n\n" + "\n".join(lines), citations, "sufficient"


def _chat_request_snapshot(payload: RagQueryRequest) -> dict[str, object]:
    """Return the exact material request fields needed for durable retries."""

    return payload.model_dump(
        mode="json",
        exclude={"thread_id", "client_message_id"},
    )


def _chat_request_fingerprint(payload: RagQueryRequest) -> str:
    """Hash every client-controlled field that can materially change a threaded answer."""

    material = _chat_request_snapshot(payload)
    canonical = json.dumps(
        {"version": 1, "request": material},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _pending_is_stale(message: ChatMessage, now: datetime) -> bool:
    heartbeat = message.updated_at or message.created_at
    return _as_utc(heartbeat) <= _as_utc(now) - CHAT_PENDING_STALE_AFTER


def _pending_chat_content(language: str) -> str:
    return "답변을 생성하고 있습니다." if language == "ko" else "Generating the response."


def _failed_chat_content(language: str) -> str:
    return (
        "답변 생성 중 일시적인 오류가 발생했습니다. 다시 시도해 주세요."
        if language == "ko"
        else "A temporary error interrupted response generation. Please retry."
    )


async def _mark_pending_assistant_failed(
    session: AsyncSession,
    *,
    assistant_message_id: str,
    language: str,
    attempted_model_id: str | None,
) -> None:
    """Persist a recoverable failure after an unexpected provider exception."""

    await session.rollback()
    message = await session.get(ChatMessage, assistant_message_id)
    if message is None or message.status != "pending":
        return
    route_metadata = dict(message.route_metadata or {})
    route_metadata.update(
        {
            "failure_code": "generation_failed",
            "failed_at": utcnow().isoformat(),
        }
    )
    model_metadata = dict(message.model_metadata or {})
    model_metadata.update(
        {
            "generation_used": False,
            "attempted_model_id": attempted_model_id,
            "effective_model_id": None,
            "model_id": None,
        }
    )
    message.content = _failed_chat_content(language)
    message.status = "failed"
    message.route_metadata = route_metadata
    message.model_metadata = model_metadata
    message.updated_at = utcnow()
    await session.commit()


def _response_from_message(message: ChatMessage) -> RagQueryResponse:
    route = message.route_metadata or {}
    model = message.model_metadata or {}
    generation = model.get("generation")
    generation = generation if isinstance(generation, dict) else {}
    legacy_model_id = model.get("model_id")
    inferred_generation_used = bool(
        legacy_model_id
        and generation.get("provider") != "deterministic-source-fallback"
        and not generation.get("fallback")
    )
    generation_used = bool(model.get("generation_used", inferred_generation_used))
    attempted_model_id = model.get("attempted_model_id")
    if attempted_model_id is None and generation.get("provider") != "deterministic-source-fallback":
        attempted_model_id = generation.get("model_id") or legacy_model_id
    effective_model_id = model.get("effective_model_id")
    if effective_model_id is None and generation_used:
        effective_model_id = legacy_model_id
    return RagQueryResponse(
        query_id=message.rag_query_id,
        answer=message.content,
        interpretation_label=route["interpretation_label"],
        filters_applied=route.get("filters_applied", {}),
        evidence_sufficiency=route["evidence_sufficiency"],
        citations=message.citations or [],
        notice=route["notice"],
        thread_id=message.thread_id,
        user_message_id=message.in_reply_to_id,
        assistant_message_id=message.id,
        retrieval_strategy=route["retrieval_strategy"],
        route_reason=route["route_reason"],
        requested_model_profile=model["requested_profile"],
        effective_model_profile=model["effective_profile"],
        generation_used=generation_used,
        attempted_model_id=attempted_model_id,
        effective_model_id=effective_model_id,
        focused_document_version_id=route.get("focused_document_version_id"),
        generated_at=route["generated_at"],
    )


async def _stream_ai_answer(
    generator: AiGenerator,
    *,
    method_name: Literal["stream_conversational_answer", "stream_grounded_answer"],
    stream_emitter: RagStreamEmitter,
    arguments: dict[str, object],
) -> str:
    """Relay provisional provider text and return only the provider-validated answer."""

    await stream_emitter({"type": "phase", "phase": "generating"})
    stream_method = getattr(generator, method_name, None)
    if stream_method is None:
        # Non-Gemini test/development generators retain compatibility. Their normal method has
        # already completed its own validation before its answer is exposed as one fast draft.
        fallback_name = f"generate_{method_name.removeprefix('stream_')}"
        fallback_method = getattr(generator, fallback_name)
        answer = await fallback_method(**arguments)
        await stream_emitter({"type": "draft_delta", "attempt": 1, "text": answer})
        await stream_emitter({"type": "phase", "phase": "validating"})
        return answer

    validated_answer: str | None = None
    async for event in stream_method(**arguments):
        if not isinstance(event, AiStreamEvent):
            raise AiGenerationError("AI streaming generator returned an invalid event")
        if event.kind == "delta":
            if event.text:
                await stream_emitter(
                    {
                        "type": "draft_delta",
                        "attempt": event.attempt,
                        "text": event.text,
                    }
                )
        elif event.kind == "reset":
            await stream_emitter({"type": "draft_reset", "attempt": event.attempt})
        elif event.kind == "validating":
            await stream_emitter({"type": "phase", "phase": "validating"})
        elif event.kind == "complete":
            validated_answer = event.text
    if not validated_answer:
        raise AiGenerationError("AI streaming generator completed without a validated answer")
    return validated_answer


def _chat_generator_candidates(
    generator: AiGenerator | None,
    *,
    settings: Settings,
    effective_profile: Literal["fast", "balanced", "deep"],
) -> list[AiGenerator]:
    if generator is None:
        return []
    if not isinstance(generator, ValidatedChatGenerator):
        return [generator]

    fallback_profiles: dict[str, tuple[Literal["fast", "balanced", "deep"], ...]] = {
        "fast": ("fast", "balanced"),
        "balanced": ("balanced", "fast"),
        "deep": ("deep", "balanced", "fast"),
    }
    thinking_levels: dict[str, Literal["minimal", "low", "medium", "high"]] = {
        "fast": "minimal",
        "balanced": "low",
        "deep": "medium",
    }
    candidates: list[AiGenerator] = []
    seen_models: set[str] = set()
    for profile in fallback_profiles[effective_profile]:
        model_id = settings.chat_model_id(profile)
        if model_id in seen_models:
            continue
        seen_models.add(model_id)
        candidates.append(
            generator.with_model(model_id, thinking_level=thinking_levels[profile])
        )
    return candidates


async def _semantic_scope_is_relevant(
    generators: list[AiGenerator],
    *,
    question: str,
    conversation_history: list[ConversationTurn],
) -> bool:
    """Use an allowlisted model only when deterministic scope signals are inconclusive."""

    for index, generator in enumerate(generators):
        classifier = getattr(generator, "classify_question_scope", None)
        if not callable(classifier):
            continue
        try:
            decision = await classifier(
                question=question,
                conversation_history=conversation_history,
            )
        except AiGenerationError as exc:
            logger.warning(
                "chat_scope_classification_failed model=%s reason=%s fallback=%s",
                generator.model_id,
                str(exc)[:160],
                index + 1 < len(generators),
            )
            continue
        return decision == "in_scope"
    return False


async def _generate_ai_with_fallback(
    generators: list[AiGenerator],
    *,
    method_name: Literal["stream_conversational_answer", "stream_grounded_answer"],
    arguments: dict[str, object],
    stream_emitter: RagStreamEmitter | None,
) -> tuple[str, AiGenerator, tuple[str, ...]]:
    """Try only server-allowlisted profile models and return the generator that succeeded."""

    attempted: list[str] = []
    last_error: AiGenerationError | None = None
    for index, generator in enumerate(generators):
        attempted.append(generator.model_id)
        try:
            if stream_emitter is not None:
                answer = await _stream_ai_answer(
                    generator,
                    method_name=method_name,
                    stream_emitter=stream_emitter,
                    arguments=arguments,
                )
            else:
                method = getattr(
                    generator,
                    f"generate_{method_name.removeprefix('stream_')}",
                )
                answer = await method(**arguments)
            return answer, generator, tuple(attempted)
        except AiGenerationError as exc:
            last_error = exc
            has_fallback = index + 1 < len(generators)
            logger.warning(
                "chat_model_attempt_failed model=%s reason=%s fallback=%s",
                generator.model_id,
                str(exc)[:160],
                has_fallback,
            )
            if stream_emitter is not None and has_fallback:
                # Discard every provisional delta from the exhausted model before a different
                # allowlisted model starts. Attempt numbers are display-only monotonic markers.
                await stream_emitter({"type": "draft_reset", "attempt": (index + 1) * 2})
    if last_error is not None:
        raise last_error
    raise AiGenerationError("No chat generation model is configured")


async def _query_rag_impl(
    payload: RagQueryRequest,
    request: Request,
    principal: Principal,
    settings: Settings,
    ai_generator: AiGenerator | None,
    embedding_generator: GeminiEmbeddingGenerator | None,
    session: AsyncSession,
    stream_emitter: RagStreamEmitter | None = None,
) -> RagQueryResponse:
    request.app.state.rate_limiter.check(
        f"rag:{principal.subject}", settings.rag_rate_limit_per_minute
    )
    if stream_emitter is not None:
        await stream_emitter({"type": "phase", "phase": "retrieving"})
    started = time.perf_counter()
    generated_at = utcnow()
    request_snapshot = _chat_request_snapshot(payload)
    request_fingerprint = _chat_request_fingerprint(payload)
    processing_attempt_id = new_uuid()
    thread: ChatThread | None = None
    persisted_history: list[ChatMessage] = []
    prior_citation_ids: tuple[str, ...] = ()
    user_message: ChatMessage | None = None
    assistant_message: ChatMessage | None = None
    if payload.thread_id:
        thread = (
            await session.execute(
                select(ChatThread)
                .options(selectinload(ChatThread.focus))
                .where(
                    ChatThread.id == str(payload.thread_id),
                    ChatThread.owner_subject == principal.subject,
                )
            )
        ).scalar_one_or_none()
        if thread is None:
            raise HTTPException(status_code=404, detail="Chat thread was not found")
        if thread.archived_at is not None:
            raise HTTPException(status_code=409, detail="Archived chat threads are read-only")
        persisted_history = list(
            (
                await session.scalars(
                    select(ChatMessage)
                    .where(ChatMessage.thread_id == thread.id)
                    .order_by(ChatMessage.sequence.desc(), ChatMessage.id.desc())
                    .limit(12)
                )
            ).all()
        )
        if payload.client_message_id:
            existing_user = (
                await session.execute(
                    select(ChatMessage)
                    .where(
                        ChatMessage.thread_id == thread.id,
                        ChatMessage.client_message_id == payload.client_message_id,
                        ChatMessage.role == "user",
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if existing_user:
                stored_fingerprint = (existing_user.route_metadata or {}).get("request_fingerprint")
                if stored_fingerprint != request_fingerprint:
                    raise HTTPException(
                        status_code=409,
                        detail="client_message_id is already bound to a different request",
                    )
                assistant_message = (
                    await session.execute(
                        select(ChatMessage)
                        .where(
                            ChatMessage.thread_id == thread.id,
                            ChatMessage.in_reply_to_id == existing_user.id,
                            ChatMessage.role == "assistant",
                        )
                        .order_by(ChatMessage.sequence, ChatMessage.id)
                        .limit(1)
                        .with_for_update()
                    )
                ).scalar_one_or_none()
                if assistant_message and assistant_message.status == "completed":
                    return _response_from_message(assistant_message)
                if (
                    assistant_message
                    and assistant_message.status == "pending"
                    and not _pending_is_stale(assistant_message, generated_at)
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="Chat message is already processing",
                    )
                user_message = existing_user
                excluded_ids = {
                    existing_user.id,
                    *([assistant_message.id] if assistant_message else []),
                }
                persisted_history = [
                    message for message in persisted_history if message.id not in excluded_ids
                ]

        latest_assistant = next(
            (
                message
                for message in persisted_history
                if message.role == "assistant" and message.status == "completed"
            ),
            None,
        )
        if latest_assistant:
            prior_citation_ids = tuple(
                dict.fromkeys(
                    str(citation.get("warning_letter_id", ""))
                    for citation in (latest_assistant.citations or [])
                    if citation.get("warning_letter_id")
                )
            )

    explicit_letter_ids = tuple(
        dict.fromkeys(
            [str(item) for item in payload.filters.letter_ids]
            + ([str(payload.filters.letter_id)] if payload.filters.letter_id else [])
        )
    )
    thread_letter_ids = tuple(thread.active_letter_ids or []) if thread else ()
    prior_user_questions = tuple(
        message.content
        for message in (persisted_history if thread else payload.conversation_history)
        if message.role == "user"
    )
    # Greetings and clearly unrelated requests stop before any corpus lookup. Ambiguous wording
    # continues to authorized company/MARCS resolution: naming a company that exists in this
    # corpus is application context even when the user does not repeat regulatory keywords.
    scope_probe = plan_rag(
        question=payload.question,
        requested_mode=payload.retrieval_mode,
        explicit_letter_ids=explicit_letter_ids,
        thread_active_letter_ids=thread_letter_ids,
        prior_citation_letter_ids=prior_citation_ids,
        prior_user_questions=prior_user_questions,
    )
    if scope_probe.deterministic_response == "capabilities" or (
        scope_probe.deterministic_response == "out_of_scope"
        and is_clearly_out_of_scope(payload.question)
    ):
        plan = scope_probe
    else:
        resolved_letter_ids = await _resolve_question_letter_ids(
            session,
            payload,
            principal=principal,
            chunker_version=settings.chunker_version,
        )
        planning_mode = payload.retrieval_mode
        # A persisted preference is a convenience default, never permission to widen a concrete
        # scope supplied by this request (including IDs resolved from an Ask-from-letter prompt).
        # An explicitly selected current-request mode still reaches the planner unchanged.
        has_current_letter_scope = bool(explicit_letter_ids or resolved_letter_ids)
        if (
            planning_mode == "auto"
            and thread
            and thread.retrieval_preference != "auto"
            and not has_current_letter_scope
        ):
            planning_mode = thread.retrieval_preference
        plan = plan_rag(
            question=payload.question,
            requested_mode=planning_mode,
            explicit_letter_ids=explicit_letter_ids,
            resolved_letter_ids=resolved_letter_ids,
            thread_active_letter_ids=thread_letter_ids,
            prior_citation_letter_ids=prior_citation_ids,
            prior_user_questions=prior_user_questions,
        )
        if plan.deterministic_response == "out_of_scope":
            scope_history = (
                [
                    ConversationTurn(role=message.role, content=message.content)
                    for message in reversed(persisted_history[:8])
                    if message.status == "completed" and message.role in {"user", "assistant"}
                ]
                if thread
                else [
                    ConversationTurn(role=message.role, content=message.content)
                    for message in payload.conversation_history[-8:]
                ]
            )
            semantic_domain_relevant = await _semantic_scope_is_relevant(
                _chat_generator_candidates(
                    ai_generator,
                    settings=settings,
                    effective_profile="fast",
                ),
                question=payload.question,
                conversation_history=scope_history,
            )
            if semantic_domain_relevant:
                plan = plan_rag(
                    question=payload.question,
                    requested_mode=planning_mode,
                    explicit_letter_ids=explicit_letter_ids,
                    resolved_letter_ids=resolved_letter_ids,
                    thread_active_letter_ids=thread_letter_ids,
                    prior_citation_letter_ids=prior_citation_ids,
                    prior_user_questions=prior_user_questions,
                    semantic_domain_relevant=True,
                )
    focused_document_version_id = (
        thread.focus.document_version_id
        if thread
        and thread.focus
        and plan.retrieval_strategy == "letter"
        and tuple(plan.letter_ids) == (thread.focus.warning_letter_id,)
        else None
    )
    profile_preference = payload.model_profile
    if profile_preference == "auto" and thread and thread.model_preference != "auto":
        profile_preference = thread.model_preference
    effective_profile = choose_model_profile(profile_preference, plan)
    attempted_model_id: str | None = None
    effective_model_id: str | None = None
    generation_used = False
    selected_generators = _chat_generator_candidates(
        ai_generator,
        settings=settings,
        effective_profile=effective_profile,
    )
    selected_generator = selected_generators[0] if selected_generators else None

    if thread:
        if user_message is None:
            next_sequence = (
                await session.scalar(
                    select(func.max(ChatMessage.sequence)).where(ChatMessage.thread_id == thread.id)
                )
                or 0
            ) + 1
            user_message = ChatMessage(
                id=new_uuid(),
                thread_id=thread.id,
                sequence=next_sequence,
                role="user",
                content=payload.question,
                status="completed",
                client_message_id=payload.client_message_id,
                route_metadata={
                    "request_fingerprint": request_fingerprint,
                    "request_snapshot": request_snapshot,
                    "filters_applied": payload.filters.model_dump(mode="json", exclude_none=True),
                    "requested_retrieval_mode": payload.retrieval_mode,
                    "planned_strategy": plan.retrieval_strategy,
                },
                model_metadata={"requested_profile": payload.model_profile},
            )
            session.add(user_message)
            assistant_message = ChatMessage(
                id=new_uuid(),
                thread_id=thread.id,
                sequence=next_sequence + 1,
                role="assistant",
                content=_pending_chat_content(
                    _effective_language(payload.language, payload.question)
                ),
                status="pending",
                in_reply_to_id=user_message.id,
                route_metadata={
                    "request_fingerprint": request_fingerprint,
                    "request_snapshot": request_snapshot,
                    "filters_applied": payload.filters.model_dump(mode="json", exclude_none=True),
                    "requested_retrieval_mode": payload.retrieval_mode,
                    "planned_strategy": plan.retrieval_strategy,
                    "processing_attempt_id": processing_attempt_id,
                    "generated_at": generated_at.isoformat(),
                },
                model_metadata={
                    "requested_profile": payload.model_profile,
                    "effective_profile": effective_profile,
                    "generation_used": False,
                    "attempted_model_id": None,
                    "effective_model_id": None,
                    "model_id": None,
                },
            )
            session.add(assistant_message)
        else:
            # A failed or stale placeholder has already passed the fingerprint and row-lock
            # checks above. Reuse both message IDs so retry never duplicates a user turn.
            if assistant_message is None:
                assistant_message = ChatMessage(
                    id=new_uuid(),
                    thread_id=thread.id,
                    sequence=user_message.sequence + 1,
                    role="assistant",
                    content=_pending_chat_content(
                        _effective_language(payload.language, payload.question)
                    ),
                    status="pending",
                    in_reply_to_id=user_message.id,
                )
                session.add(assistant_message)
            assistant_message.content = _pending_chat_content(
                _effective_language(payload.language, payload.question)
            )
            assistant_message.status = "pending"
            assistant_message.rag_query_id = None
            assistant_message.citations = []
            assistant_message.route_metadata = {
                "request_fingerprint": request_fingerprint,
                "request_snapshot": request_snapshot,
                "filters_applied": payload.filters.model_dump(mode="json", exclude_none=True),
                "requested_retrieval_mode": payload.retrieval_mode,
                "planned_strategy": plan.retrieval_strategy,
                "processing_attempt_id": processing_attempt_id,
                "generated_at": generated_at.isoformat(),
            }
            assistant_message.model_metadata = {
                "requested_profile": payload.model_profile,
                "effective_profile": effective_profile,
                "generation_used": False,
                "attempted_model_id": None,
                "effective_model_id": None,
                "model_id": None,
            }
            assistant_message.updated_at = generated_at
        thread.last_message_at = generated_at
        if thread.title == "새 대화":
            thread.title = payload.question[:80]
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(
                status_code=409,
                detail="Chat message is already processing or its sequence changed",
            ) from None

    effective_language = _effective_language(payload.language, payload.question)
    interpretation_label = "internal_comparison" if plan.internal_comparison else "source_facts"
    citations: list[CitationResponse] = []
    evidence_sufficiency = "insufficient"
    priority_anchors: set[str] = set()
    derived_artifact_context: str | None = None
    generation_context: dict[str, object] = {
        "provider": "deterministic-source-fallback",
        "model_id": "none",
        "prompt_version": "not-applicable",
    }
    semantic_retrieval_used = False
    semantic_candidate_count = 0
    semantic_fallback: str | None = None
    stream_validation_completed = False

    if plan.retrieval_strategy == "none":
        # The planner runs before this branch; no document-chunk statement is issued.
        if plan.deterministic_response is not None:
            answer = _deterministic_no_retrieval_answer(plan, effective_language)
        elif selected_generator is not None:
            attempted_model_id = selected_generator.model_id
            model_history = (
                [
                    ConversationTurn(role=message.role, content=message.content)
                    for message in reversed(persisted_history[:8])
                    if message.status == "completed" and message.role in {"user", "assistant"}
                ]
                if thread
                else [
                    ConversationTurn(role=message.role, content=message.content)
                    for message in payload.conversation_history
                ]
            )
            try:
                answer, effective_generator, attempted_models = (
                    await _generate_ai_with_fallback(
                        selected_generators,
                        method_name="stream_conversational_answer",
                        stream_emitter=stream_emitter,
                        arguments={
                            "question": payload.question,
                            "language": effective_language,
                            "conversation_history": model_history,
                        },
                    )
                )
                if stream_emitter is not None:
                    stream_validation_completed = True
                interpretation_label = "ai_synthesis"
                generation_used = True
                effective_model_id = effective_generator.model_id
                generation_context = {
                    "provider": effective_generator.provider,
                    "model_id": effective_generator.model_id,
                    "prompt_version": effective_generator.prompt_version,
                    "retrieval": "none",
                    "attempted_model_ids": list(attempted_models),
                    "fallback_used": len(attempted_models) > 1,
                }
            except AiGenerationError:
                answer = _model_unavailable_no_retrieval_answer(effective_language)
                generation_context = {
                    "provider": selected_generator.provider,
                    "model_id": selected_generator.model_id,
                    "prompt_version": selected_generator.prompt_version,
                    "fallback": "model_unavailable_no_retrieval",
                }
            except Exception as exc:
                if assistant_message is not None:
                    await _mark_pending_assistant_failed(
                        session,
                        assistant_message_id=assistant_message.id,
                        language=effective_language,
                        attempted_model_id=attempted_model_id,
                    )
                logger.exception(
                    "Conversational response generation failed after the pending turn was persisted"
                )
                raise HTTPException(
                    status_code=502,
                    detail="Chat response generation failed; retry the same message",
                ) from exc
        else:
            answer = _model_unavailable_no_retrieval_answer(effective_language)
            generation_context = {
                "provider": "unavailable",
                "model_id": "none",
                "prompt_version": "not-applicable",
                "fallback": "model_not_configured_no_retrieval",
            }
    elif plan.retrieval_strategy == "metadata":
        answer, citations, evidence_sufficiency = await _metadata_answer(
            session,
            payload=payload,
            plan=plan,
            language=effective_language,
            principal=principal,
            chunker_version=settings.chunker_version,
        )
    else:
        # Corpus/scope/current-version and, critically, selected-letter authorization are pushed
        # into SQL before lexical ranking. A missing requested letter scope fails closed.
        statement = (
            select(DocumentChunk, WarningLetter, Document)
            .join(WarningLetter, WarningLetter.id == DocumentChunk.warning_letter_id)
            .join(DocumentVersion, DocumentVersion.id == DocumentChunk.document_version_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(
                DocumentChunk.corpus_id == "fda-drugs",
                WarningLetter.current_in_scope.is_(True),
                WarningLetter.scope_status == ScopeStatus.IN_SCOPE_DRUGS.value,
                WarningLetter.current_version_id == DocumentChunk.document_version_id,
                Document.warning_letter_id == WarningLetter.id,
                Document.current_version_id == DocumentVersion.id,
                Document.current_in_scope.is_(True),
                Document.source_available.is_(True),
                DocumentVersion.scope_status == ScopeStatus.IN_SCOPE_DRUGS.value,
                DocumentChunk.chunker_version == settings.chunker_version,
            )
        )
        if plan.retrieval_strategy in {"letter", "multi_letter"}:
            statement = (
                statement.where(WarningLetter.id.in_(plan.letter_ids))
                if plan.letter_ids
                else statement.where(false())
            )
        if focused_document_version_id:
            statement = statement.where(
                DocumentChunk.document_version_id == focused_document_version_id
            )
        statement = _apply_warning_sql_filters(statement, payload)
        rows = (await session.execute(statement)).all()
        filters = payload.filters
        allowed_letter_ids = set(plan.letter_ids)
        # ACL and every non-SQL filter are applied before a chunk ID is ever passed to the
        # vector store. This is the semantic retrieval authorization boundary.
        authorized_rows: list[tuple[DocumentChunk, WarningLetter, Document]] = []
        for chunk, letter, document in rows:
            if not _acl_allows(chunk.acl, principal):
                continue
            if allowed_letter_ids and letter.id not in allowed_letter_ids:
                continue
            office_filters = [
                *filters.issuing_offices,
                *([filters.issuing_office] if filters.issuing_office else []),
            ]
            if office_filters and not any(
                requested.casefold() in office.casefold()
                for requested in office_filters
                for office in (letter.issuing_offices or [])
            ):
                continue
            category_filters = [
                *filters.categories,
                *([filters.category] if filters.category else []),
            ]
            if category_filters and not any(
                value in (chunk.categories or []) for value in category_filters
            ):
                continue
            regulation_filters = [
                *filters.regulatory_references,
                *([filters.regulation] if filters.regulation else []),
            ]
            if regulation_filters and not any(
                requested.casefold() in value.casefold()
                for requested in regulation_filters
                for value in (chunk.regulatory_references or [])
            ):
                continue
            subtype_filters = [
                *filters.drug_subtypes,
                *([filters.drug_subtype] if filters.drug_subtype else []),
            ]
            if subtype_filters and not any(
                value in (chunk.drug_subtypes or []) for value in subtype_filters
            ):
                continue
            authorized_rows.append((chunk, letter, document))
        # Threadless requests retain the legacy browser-history behavior. Authenticated threads
        # never use historical prose as a retrieval query; they inherit only server-owned scope.
        prior_user_messages = (
            [message.content for message in payload.conversation_history if message.role == "user"]
            if thread is None
            else []
        )
        retrieval_text = "\n".join([*prior_user_messages, payload.question])
        question_tokens = _query_tokens(retrieval_text)
        korean_query = re.search(r"[가-힣]", retrieval_text) is not None
        constrained_version_ids = {
            chunk.document_version_id
            for chunk, _letter, _document in authorized_rows
            if plan.retrieval_strategy in {"letter", "multi_letter"}
        }
        priority_anchors, expansion_tokens, derived_artifact_context = await _derived_query_hints(
            session,
            version_ids=constrained_version_ids,
            question_tokens=question_tokens,
        )
        semantic_scores: dict[str, float] = {}
        if embedding_generator is not None and authorized_rows:
            try:
                semantic_scores = await semantic_scores_for_allowed_chunks(
                    session,
                    question=retrieval_text,
                    allowed_chunks=[chunk for chunk, _letter, _document in authorized_rows],
                    generator=embedding_generator,
                    limit=max(24, payload.max_sources * 8),
                )
                semantic_retrieval_used = bool(semantic_scores)
                semantic_candidate_count = len(semantic_scores)
            except (EmbeddingGenerationError, SemanticRetrievalError, ValueError) as exc:
                # Semantic retrieval is an optional ranking signal. Official-source lexical
                # retrieval remains available and its authorization boundary is unchanged.
                semantic_fallback = type(exc).__name__
                logger.warning(
                    "Semantic retrieval fell back to lexical ranking: %s", type(exc).__name__
                )
        ranked: list[tuple[float, int, DocumentChunk, WarningLetter, Document]] = []
        for chunk, letter, document in authorized_rows:
            content_tokens = _tokens(chunk.content)
            overlap = question_tokens.intersection(content_tokens)
            expansion_overlap = expansion_tokens.intersection(content_tokens)
            anchor_priority = chunk.source_anchor in priority_anchors
            semantic_score = semantic_scores.get(chunk.id)
            minimum_overlap = 1 if korean_query else min(2, len(question_tokens))
            direct_match = bool(overlap) and len(overlap) >= minimum_overlap
            if direct_match:
                density = len(overlap) / max(1, len(question_tokens))
                score = density + min(0.25, len(overlap) * 0.025)
                overlap_count = len(overlap)
            elif anchor_priority:
                score = 0.45 + min(0.2, len(expansion_overlap) * 0.02)
                overlap_count = 1
            elif expansion_overlap:
                score = 0.2 + min(0.15, len(expansion_overlap) * 0.015)
                overlap_count = 1
            elif plan.retrieval_strategy in {"letter", "multi_letter"}:
                score = 0.05
                overlap_count = 1
            elif semantic_score is not None and semantic_score >= 0.25:
                score = 0.0
                overlap_count = 0
            else:
                continue
            if anchor_priority:
                score += 1.0
            if semantic_score is not None:
                score += max(0.0, semantic_score) * 0.5
            ranked.append((score, overlap_count, chunk, letter, document))
        ranked.sort(
            key=lambda item: (
                -item[0],
                -(item[3].posted_date or item[3].issue_date or date.min).toordinal(),
                item[2].id,
            )
        )
        selected = ranked[: payload.max_sources]
        selected_version_ids = {
            chunk.document_version_id for _score, _overlap, chunk, _letter, _document in selected
        }
        version_by_id = {
            version.id: version
            for version in (
                await session.scalars(
                    select(DocumentVersion).where(DocumentVersion.id.in_(selected_version_ids))
                )
            ).all()
        }
        citations = [
            CitationResponse(
                chunk_id=chunk.id,
                warning_letter_id=letter.id,
                company_name=letter.company_name,
                title=document.title,
                document_type=document.document_type,
                issue_date=letter.issue_date,
                posted_date=letter.posted_date,
                source_anchor=chunk.source_anchor,
                excerpt=chunk.content[:800],
                source_url=document.canonical_url,
                score=round(score, 4),
                document_version_id=chunk.document_version_id,
                source_version=(
                    f"v{version_by_id[chunk.document_version_id].version_number}"
                    if chunk.document_version_id in version_by_id
                    else None
                ),
                source_hash=(
                    version_by_id[chunk.document_version_id].canonical_hash
                    if chunk.document_version_id in version_by_id
                    else None
                ),
            )
            for score, _overlap_count, chunk, letter, document in selected
        ]
        evidence_sufficiency = (
            "sufficient"
            if any(overlap_count >= 2 for _score, overlap_count, *_rest in selected)
            else ("partial" if citations else "insufficient")
        )
        if citations:
            passages = "\n\n".join(
                f"[{index}] {citation.company_name}: {citation.excerpt}"
                for index, citation in enumerate(citations, start=1)
            )
            answer = (
                f"승인된 FDA 의약품 코퍼스에서 다음 원문 구절을 직접 검색했습니다:\n\n{passages}"
                if effective_language == "ko"
                else (
                    "The authorized FDA Drug corpus contains the following directly retrieved "
                    f"source passages:\n\n{passages}"
                )
            )
            if selected_generator:
                attempted_model_id = selected_generator.model_id
                model_history = (
                    [
                        ConversationTurn(role=message.role, content=message.content)
                        for message in reversed(persisted_history[:8])
                        if message.status == "completed" and message.role in {"user", "assistant"}
                    ]
                    if thread
                    else [
                        ConversationTurn(role=message.role, content=message.content)
                        for message in payload.conversation_history
                    ]
                )
                try:
                    generation_arguments: dict[str, object] = {
                        "question": payload.question,
                        "language": effective_language,
                        "conversation_history": (
                            [ConversationTurn(role="assistant", content=derived_artifact_context)]
                            if derived_artifact_context
                            else []
                        )
                        + model_history,
                        "passages": [
                            GroundedPassage(
                                index=index,
                                company_name=citation.company_name,
                                source_anchor=citation.source_anchor,
                                excerpt=citation.excerpt,
                            )
                            for index, citation in enumerate(citations, start=1)
                        ],
                    }
                    answer, effective_generator, attempted_models = (
                        await _generate_ai_with_fallback(
                            selected_generators,
                            method_name="stream_grounded_answer",
                            stream_emitter=stream_emitter,
                            arguments=generation_arguments,
                        )
                    )
                    if stream_emitter is not None:
                        stream_validation_completed = True
                    interpretation_label = (
                        "internal_comparison" if plan.internal_comparison else "ai_synthesis"
                    )
                    generation_used = True
                    effective_model_id = effective_generator.model_id
                    generation_context = {
                        "provider": effective_generator.provider,
                        "model_id": effective_generator.model_id,
                        "prompt_version": effective_generator.prompt_version,
                        "attempted_model_ids": list(attempted_models),
                        "fallback_used": len(attempted_models) > 1,
                    }
                except AiGenerationError:
                    generation_context = {
                        "provider": selected_generator.provider,
                        "model_id": selected_generator.model_id,
                        "prompt_version": selected_generator.prompt_version,
                        "fallback": "source_facts",
                    }
                except Exception as exc:
                    if assistant_message is not None:
                        await _mark_pending_assistant_failed(
                            session,
                            assistant_message_id=assistant_message.id,
                            language=effective_language,
                            attempted_model_id=attempted_model_id,
                        )
                    logger.exception(
                        "Chat response generation failed after the pending turn was persisted"
                    )
                    raise HTTPException(
                        status_code=502,
                        detail="Chat response generation failed; retry the same message",
                    ) from exc
        else:
            answer = (
                "이 질문과 필터 조건을 뒷받침할 충분한 근거를 승인된 FDA Product: Drugs "
                "코퍼스에서 찾지 못했습니다."
                if effective_language == "ko"
                else (
                    "Insufficient evidence was found in the authorized FDA Product: Drugs "
                    "corpus for this question and filter set."
                )
            )

    if stream_emitter is not None and not stream_validation_completed:
        await stream_emitter({"type": "phase", "phase": "validating"})

    if assistant_message is not None:
        async with request.app.state.database.session_factory() as verification_session:
            persisted_attempt = (
                await verification_session.execute(
                    select(ChatMessage.status, ChatMessage.route_metadata).where(
                        ChatMessage.id == assistant_message.id
                    )
                )
            ).one_or_none()
        persisted_status = persisted_attempt[0] if persisted_attempt else None
        persisted_route = persisted_attempt[1] if persisted_attempt else {}
        if (
            persisted_status != "pending"
            or (persisted_route or {}).get("processing_attempt_id") != processing_attempt_id
        ):
            await session.rollback()
            raise HTTPException(
                status_code=409,
                detail="Chat response was cancelled or superseded by a retry",
            )

    evidence_sufficient = bool(citations)
    query_log = RagQuery(
        actor_id=principal.subject,
        query_sha256=hashlib.sha256(payload.question.encode("utf-8")).hexdigest(),
        query_length=len(payload.question),
        language=payload.language,
        filters=payload.filters.model_dump(mode="json", exclude_none=True),
        retrieved_chunk_ids=[str(item.chunk_id) for item in citations],
        evidence_sufficient=evidence_sufficient,
        latency_ms=int((time.perf_counter() - started) * 1_000),
    )
    session.add(query_log)
    await session.flush()
    add_audit_event(
        session,
        principal=principal,
        request_id=request.state.request_id,
        operation="rag.query",
        object_type="rag_query",
        object_id=query_log.id,
        application_version=settings.app_version,
        after={
            "evidence_sufficient": evidence_sufficient,
            "evidence_sufficiency": evidence_sufficiency,
            "citation_count": len(citations),
            "conversation_message_count": (
                len(persisted_history) if thread else len(payload.conversation_history)
            ),
            "retrieval_user_message_count": (
                0
                if thread
                else len([item for item in payload.conversation_history if item.role == "user"])
            ),
            "derived_anchor_hint_count": len(priority_anchors),
            "derived_artifact_context_used": bool(derived_artifact_context),
            "letter_constrained": plan.retrieval_strategy in {"letter", "multi_letter"},
            "retrieval_strategy": plan.retrieval_strategy,
            "route_reason": plan.route_reason,
            "focused_document_version_id": focused_document_version_id,
            "processing_attempt_id": processing_attempt_id,
            "internal_comparison": plan.internal_comparison,
            "semantic_retrieval": {
                "configured": embedding_generator is not None,
                "used": semantic_retrieval_used,
                "candidate_count": semantic_candidate_count,
                "fallback": semantic_fallback,
                "model_id": (
                    embedding_generator.model_id if embedding_generator is not None else None
                ),
            },
            "generation": generation_context,
        },
    )
    notice = (
        "Decision support only. Verify every statement against the linked official FDA "
        "source; no compliance conclusion is generated."
    )
    await session.flush()
    response = RagQueryResponse(
        query_id=query_log.id,
        answer=answer,
        interpretation_label=interpretation_label,
        filters_applied=payload.filters.model_dump(mode="json", exclude_none=True),
        evidence_sufficiency=evidence_sufficiency,
        citations=citations,
        notice=notice,
        thread_id=thread.id if thread else None,
        user_message_id=user_message.id if user_message else None,
        assistant_message_id=None,
        retrieval_strategy=plan.retrieval_strategy,
        route_reason=plan.route_reason,
        requested_model_profile=payload.model_profile,
        effective_model_profile=effective_profile,
        generation_used=generation_used,
        attempted_model_id=attempted_model_id,
        effective_model_id=effective_model_id,
        focused_document_version_id=focused_document_version_id,
        generated_at=generated_at,
    )
    if thread and user_message and assistant_message:
        completed_route_metadata = {
            "request_fingerprint": request_fingerprint,
            "request_snapshot": request_snapshot,
            "interpretation_label": interpretation_label,
            "filters_applied": payload.filters.model_dump(mode="json", exclude_none=True),
            "evidence_sufficiency": evidence_sufficiency,
            "retrieval_strategy": plan.retrieval_strategy,
            "route_reason": plan.route_reason,
            "focused_document_version_id": focused_document_version_id,
            "internal_comparison": plan.internal_comparison,
            "notice": notice,
            "generated_at": generated_at.isoformat(),
        }
        completed_model_metadata = {
            "requested_profile": payload.model_profile,
            "effective_profile": effective_profile,
            "generation_used": generation_used,
            "attempted_model_id": attempted_model_id,
            "effective_model_id": effective_model_id,
            # Retained during the response-field migration for existing readers.
            "model_id": effective_model_id,
            "generation": generation_context,
        }
        completion = await session.execute(
            update(ChatMessage)
            .where(
                ChatMessage.id == assistant_message.id,
                ChatMessage.status == "pending",
                ChatMessage.route_metadata["processing_attempt_id"].as_string()
                == processing_attempt_id,
            )
            .values(
                content=answer,
                status="completed",
                rag_query_id=query_log.id,
                citations=[item.model_dump(mode="json") for item in citations],
                route_metadata=completed_route_metadata,
                model_metadata=completed_model_metadata,
                updated_at=generated_at,
            )
            .execution_options(synchronize_session=False)
        )
        if completion.rowcount != 1:
            await session.rollback()
            raise HTTPException(
                status_code=409,
                detail="Chat response was cancelled or superseded by a retry",
            )
        if plan.letter_ids and plan.retrieval_strategy in {"letter", "multi_letter", "metadata"}:
            thread.active_letter_ids = list(plan.letter_ids)
            if thread.focus and tuple(plan.letter_ids) != (thread.focus.warning_letter_id,):
                thread.focus = None
        thread.last_message_at = generated_at
        thread.updated_at = generated_at
        await session.flush()
        response.assistant_message_id = UUID(assistant_message.id)
    await session.commit()
    return response


@router.post("/rag/query", response_model=RagQueryResponse, tags=["RAG"])
async def query_rag(
    payload: RagQueryRequest,
    request: Request,
    principal: Principal = Depends(rag_principal),
    settings: Settings = Depends(settings_dependency),
    ai_generator: AiGenerator | None = Depends(ai_generator_dependency),
    embedding_generator: GeminiEmbeddingGenerator | None = Depends(embedding_generator_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> RagQueryResponse:
    """Stable JSON RAG contract retained for non-streaming clients."""

    return await _query_rag_impl(
        payload,
        request,
        principal,
        settings,
        ai_generator,
        embedding_generator,
        session,
    )


def _stream_error(exc: Exception) -> dict[str, object]:
    if isinstance(exc, HTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else "The request could not be completed"
        if exc.status_code == status.HTTP_409_CONFLICT and (
            "cancelled" in detail.casefold() or "superseded" in detail.casefold()
        ):
            code = "cancelled_or_superseded"
        elif exc.status_code == status.HTTP_409_CONFLICT:
            code = "request_conflict"
        elif exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            code = "rate_limited"
        else:
            code = f"request_{exc.status_code}"
        return {"type": "error", "code": code, "message": detail}
    return {
        "type": "error",
        "code": "generation_failed",
        "message": "Chat response generation failed; retry the same message",
    }


@router.post("/rag/query/stream", tags=["RAG"])
async def query_rag_stream(
    payload: RagQueryRequest,
    request: Request,
    principal: Principal = Depends(rag_principal),
    settings: Settings = Depends(settings_dependency),
    ai_generator: AiGenerator | None = Depends(ai_generator_dependency),
    embedding_generator: GeminiEmbeddingGenerator | None = Depends(embedding_generator_dependency),
) -> StreamingResponse:
    """Stream provisional drafts as NDJSON; publish authority only after durable commit."""

    async def event_stream():
        queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue(maxsize=16)

        async def emit(event: dict[str, object]) -> None:
            await queue.put(event)

        async def produce() -> None:
            try:
                async with request.app.state.database.session_factory() as stream_session:
                    response = await _query_rag_impl(
                        payload,
                        request,
                        principal,
                        settings,
                        ai_generator,
                        embedding_generator,
                        stream_session,
                        stream_emitter=emit,
                    )
                # _query_rag_impl returns only after its cancellation/supersession check and DB
                # commit. This is the sole point where authoritative answer data is emitted.
                await emit(
                    {
                        "type": "complete",
                        "data": response.model_dump(mode="json"),
                    }
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if not isinstance(exc, HTTPException):
                    logger.exception("Streaming RAG response failed")
                await emit(_stream_error(exc))
            finally:
                try:
                    queue.put_nowait(None)
                except asyncio.QueueFull:
                    # A full queue is already a wake-up signal. The consumer also observes the
                    # completed producer after draining, so cancellation cannot deadlock here.
                    pass

        producer = asyncio.create_task(produce())
        try:
            while True:
                if await request.is_disconnected():
                    producer.cancel()
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.25)
                except TimeoutError:
                    if producer.done() and queue.empty():
                        break
                    continue
                if event is None:
                    break
                yield (
                    json.dumps(
                        event,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode("utf-8")
                    + b"\n"
                )
        finally:
            if not producer.done():
                producer.cancel()
            try:
                await producer
            except asyncio.CancelledError:
                pass

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={
            "Content-Type": "application/x-ndjson; charset=utf-8",
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/reviews", response_model=ReviewQueuePage, tags=["Reviews"])
async def review_queue(
    state: str | None = Query(default=None, max_length=40),
    view: Literal["open", "high_attention", "all"] = Query(default="open"),
    cursor: str | None = Query(default=None, max_length=2_048),
    limit: int | None = Query(default=None, ge=1, le=100),
    page_size: int | None = Query(default=None, ge=1, le=100),
    _principal: Principal = Depends(reviewer_principal),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> ReviewQueuePage:
    try:
        offset = decode_cursor(cursor)
    except InvalidCursor as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    allowed_states = {item.value for item in ReviewState}
    if state is not None and state not in allowed_states:
        raise HTTPException(status_code=422, detail="Unsupported review state")
    query = (
        select(AiSummary, WarningLetter, Document)
        .join(DocumentVersion, DocumentVersion.id == AiSummary.document_version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .join(WarningLetter, WarningLetter.id == Document.warning_letter_id)
        .where(
            WarningLetter.current_in_scope.is_(True),
            WarningLetter.scope_status == ScopeStatus.IN_SCOPE_DRUGS.value,
        )
    )
    if state is not None:
        query = query.where(AiSummary.review_state == state)
    elif view in {"open", "high_attention"}:
        query = query.where(
            AiSummary.review_state.in_(
                [ReviewState.PENDING.value, ReviewState.NEEDS_REVISION.value]
            )
        )
    rows = (
        await session.execute(query.order_by(AiSummary.created_at.desc(), AiSummary.id.desc()))
    ).all()
    source_ids = [summary.id for summary, _letter, _document in rows]
    superseded_ids = (
        set(
            await session.scalars(
                select(AiSummary.parent_summary_id).where(
                    AiSummary.parent_summary_id.in_(source_ids)
                )
            )
        )
        if source_ids
        else set()
    )
    rows = [row for row in rows if row[0].id not in superseded_ids]

    def review_metadata(summary: AiSummary) -> tuple[list[str], float | None, bool]:
        report = summary.validation_report or {}
        raw_failed_checks = report.get("failed_checks", [])
        failed_checks = (
            [str(item) for item in raw_failed_checks] if isinstance(raw_failed_checks, list) else []
        )
        raw_confidence = report.get("confidence", report.get("overall_confidence"))
        confidence = (
            float(raw_confidence)
            if not isinstance(raw_confidence, bool)
            and isinstance(raw_confidence, (float, int))
            and 0 <= raw_confidence <= 1
            else None
        )
        high_attention = bool(failed_checks) or (confidence is not None and confidence < 0.9)
        return failed_checks, confidence, high_attention

    if state is None and view == "high_attention":
        rows = [row for row in rows if review_metadata(row[0])[2]]
    related_counts: dict[str, int] = {}
    for summary, _letter, _document in rows:
        related_counts[summary.document_version_id] = (
            related_counts.get(summary.document_version_id, 0) + 1
        )
    items = [
        ReviewQueueItem(
            summary=summary_response(summary),
            company_name=letter.company_name,
            warning_letter_id=letter.id,
            source_url=document.canonical_url,
            failed_checks=review_metadata(summary)[0],
            marcs_cms_number=letter.marcs_cms_number,
            related_open_items=related_counts[summary.document_version_id],
            confidence=review_metadata(summary)[1],
            high_attention=review_metadata(summary)[2],
        )
        for summary, letter, document in rows
    ]
    requested = page_size if page_size is not None else limit
    effective_page_size = min(requested or settings.default_page_size, settings.max_page_size)
    page, next_cursor, has_more = page_window(
        items,
        offset=offset,
        limit=effective_page_size,
    )
    previous_cursor = encode_cursor(max(0, offset - effective_page_size)) if offset > 0 else None
    return ReviewQueuePage(
        items=page,
        next_cursor=next_cursor,
        previous_cursor=previous_cursor,
        has_more=has_more,
        total=len(items),
        page=(offset // effective_page_size) + 1,
        page_size=effective_page_size,
    )


@router.patch("/reviews/{summary_id}", response_model=ReviewActionResponse, tags=["Reviews"])
async def review_summary(
    summary_id: UUID,
    payload: ReviewPatchRequest,
    request: Request,
    principal: Principal = Depends(reviewer_principal),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> ReviewActionResponse:
    source = await session.scalar(
        select(AiSummary).where(AiSummary.id == str(summary_id)).with_for_update()
    )
    if not source:
        raise HTTPException(status_code=404, detail="Summary not found")
    successor_id = await session.scalar(
        select(AiSummary.id).where(AiSummary.parent_summary_id == source.id).limit(1)
    )
    if successor_id:
        raise HTTPException(status_code=409, detail="Summary version has been superseded")
    if source.review_state not in {
        ReviewState.PENDING.value,
        ReviewState.NEEDS_REVISION.value,
    }:
        raise HTTPException(status_code=409, detail="Summary has already reached a terminal state")
    if payload.expected_summary_version and payload.expected_summary_version not in {
        str(source.revision),
        source.id,
    }:
        raise HTTPException(status_code=409, detail="Summary version no longer matches")
    state_map = {
        ReviewDecision.APPROVE: ReviewState.APPROVED,
        ReviewDecision.NEEDS_REVISION: ReviewState.NEEDS_REVISION,
        ReviewDecision.REJECT: ReviewState.REJECTED,
    }
    target_state = state_map[payload.decision]
    before = {
        "review_state": source.review_state,
        "revision": source.revision,
        "document_version_id": source.document_version_id,
        "executive_summary": source.executive_summary,
        "structured_output": source.structured_output,
    }
    resulting = source
    edited_structured = (
        payload.edited_structured_output
        if payload.edited_structured_output is not None
        else payload.edited_output
    )
    edited_summary = (
        payload.edited_executive_summary.strip()
        if payload.edited_executive_summary is not None
        else None
    )
    content_changed = (
        edited_summary is not None and edited_summary != source.executive_summary
    ) or (edited_structured is not None and edited_structured != source.structured_output)
    if content_changed:
        if payload.decision != ReviewDecision.APPROVE:
            raise HTTPException(status_code=409, detail="Edited output may only be approved")
        resulting = AiSummary(
            document_version_id=source.document_version_id,
            parent_summary_id=source.id,
            revision=source.revision + 1,
            language=source.language,
            executive_summary=edited_summary or source.executive_summary,
            structured_output=(
                edited_structured if edited_structured is not None else source.structured_output
            ),
            validation_report=source.validation_report,
            provider=source.provider,
            model_id=source.model_id,
            prompt_version=source.prompt_version,
            schema_version=source.schema_version,
            taxonomy_version=source.taxonomy_version,
            review_state=ReviewState.APPROVED.value,
            reviewer_id=principal.subject,
            reviewed_at=utcnow(),
        )
        source.review_state = ReviewState.NEEDS_REVISION.value
        session.add(resulting)
        await session.flush()
    else:
        source.review_state = target_state.value
        source.reviewer_id = principal.subject
        source.reviewed_at = utcnow()
    after = {
        "review_state": resulting.review_state,
        "revision": resulting.revision,
        "document_version_id": resulting.document_version_id,
        "executive_summary": resulting.executive_summary,
        "structured_output": resulting.structured_output,
    }
    review = Review(
        summary_id=source.id,
        resulting_summary_id=resulting.id,
        reviewer_id=principal.subject,
        decision=payload.decision.value,
        reason=payload.reason,
        before_value=before,
        after_value=after,
    )
    session.add(review)
    await session.flush()
    add_audit_event(
        session,
        principal=principal,
        request_id=request.state.request_id,
        operation="summary.review",
        object_type="ai_summary",
        object_id=source.id,
        application_version=settings.app_version,
        reason=payload.reason,
        before=before,
        after=after,
        context={
            "review_id": review.id,
            "resulting_summary_id": resulting.id,
            "source_document_version_id": source.document_version_id,
            "content_changed": content_changed,
            "change_ticket": payload.change_ticket,
        },
    )
    await session.commit()
    reviewed_at = resulting.reviewed_at or utcnow()
    return ReviewActionResponse(
        review_id=review.id,
        source_summary_id=source.id,
        resulting_summary_id=resulting.id,
        source_document_version_id=source.document_version_id,
        resulting_revision=resulting.revision,
        review_state=resulting.review_state,
        reviewed_by=principal.subject,
        reviewed_at=reviewed_at,
        content_changed=content_changed,
        request_id=request.state.request_id,
    )


_SAVED_VIEW_CRITERIA_FIELDS = {
    "query",
    "drug_subtype",
    "category",
    "country",
    "lifecycle_state",
    "review_state",
    "linked_document",
    "posted_from",
    "posted_to",
}
_SAVED_VIEW_URL_FIELDS = {
    "query": "q",
    "drug_subtype": "subtype",
    "category": "category",
    "country": "country",
    "lifecycle_state": "lifecycle",
    "review_state": "review",
    "linked_document": "document",
    "posted_from": "postedFrom",
    "posted_to": "postedTo",
}


def _controlled_saved_view_criteria(value: dict[str, Any] | None) -> SavedViewCriteria:
    """Drop legacy/system subscription keys before returning a portal-owned view."""

    controlled = {
        key: entry
        for key, entry in (value or {}).items()
        if key in _SAVED_VIEW_CRITERIA_FIELDS and entry not in (None, "")
    }
    return SavedViewCriteria.model_validate(controlled)


async def _saved_view_letter_records(
    session: AsyncSession,
) -> list[tuple[LetterListItem, list[str]]]:
    letters = list(
        (
            await session.scalars(
                select(WarningLetter)
                .where(
                    WarningLetter.current_in_scope.is_(True),
                    WarningLetter.scope_status == ScopeStatus.IN_SCOPE_DRUGS.value,
                )
                .order_by(
                    WarningLetter.posted_date.desc(),
                    WarningLetter.last_seen_at.desc(),
                    WarningLetter.id,
                )
            )
        ).all()
    )
    if not letters:
        return []

    letter_ids = [letter.id for letter in letters]
    documents = list(
        (
            await session.scalars(
                select(Document).where(Document.warning_letter_id.in_(letter_ids))
            )
        ).all()
    )
    documents_by_letter: dict[str, list[Document]] = defaultdict(list)
    for document in documents:
        documents_by_letter[document.warning_letter_id].append(document)

    version_ids = [letter.current_version_id for letter in letters if letter.current_version_id]
    summaries: dict[str, AiSummary] = {}
    findings_by_version: dict[str, list[Finding]] = defaultdict(list)
    if version_ids:
        for summary in (
            await session.scalars(
                select(AiSummary)
                .where(AiSummary.document_version_id.in_(version_ids))
                .order_by(AiSummary.created_at.desc(), AiSummary.revision.desc())
            )
        ).all():
            summaries.setdefault(summary.document_version_id, summary)
        summary_ids = [summary.id for summary in summaries.values()]
        if summary_ids:
            for finding in (
                await session.scalars(
                    select(Finding)
                    .where(Finding.summary_id.in_(summary_ids))
                    .order_by(Finding.created_at, Finding.id)
                )
            ).all():
                findings_by_version[finding.document_version_id].append(finding)

    records: list[tuple[LetterListItem, list[str]]] = []
    for letter in letters:
        version_id = letter.current_version_id or ""
        findings = findings_by_version.get(version_id, [])
        item = letter_item(
            letter,
            documents=documents_by_letter.get(letter.id, []),
            summary=summaries.get(version_id),
            findings=findings,
        )
        regulations = sorted(
            {
                reference
                for finding in findings
                for reference in (finding.regulatory_references or [])
            }
        )
        records.append((item, regulations))
    return records


def _saved_view_matches(
    criteria: SavedViewCriteria,
    item: LetterListItem,
    regulations: list[str],
) -> bool:
    query = (criteria.query or "").casefold()
    if query:
        haystack = " ".join(
            [
                item.company_name,
                item.marcs_cms_number or "",
                item.subject or "",
                item.country or "",
                *item.issuing_offices,
                *item.categories,
                *regulations,
            ]
        ).casefold()
        if query not in haystack:
            return False
    if criteria.drug_subtype and criteria.drug_subtype not in item.drug_subtypes:
        return False
    if criteria.category and criteria.category not in item.categories:
        return False
    if criteria.country and (item.country or "").casefold() != criteria.country.casefold():
        return False
    if criteria.lifecycle_state and (
        item.lifecycle_status.casefold() != criteria.lifecycle_state.casefold()
    ):
        return False
    if criteria.review_state and item.review_state != criteria.review_state:
        return False
    if criteria.linked_document == "response" and not item.has_response:
        return False
    if criteria.linked_document == "closeout" and not item.has_closeout:
        return False
    if criteria.linked_document == "open" and item.has_closeout:
        return False
    if criteria.posted_from and (
        item.posted_date is None or item.posted_date < criteria.posted_from
    ):
        return False
    if criteria.posted_to and (item.posted_date is None or item.posted_date > criteria.posted_to):
        return False
    return True


def _saved_view_open_url(criteria: SavedViewCriteria) -> str:
    values = criteria.model_dump(mode="json", exclude_none=True)
    query = urlencode(
        {
            _SAVED_VIEW_URL_FIELDS[key]: value
            for key, value in values.items()
            if key in _SAVED_VIEW_URL_FIELDS and value not in (None, "")
        }
    )
    return f"/drug-letters?{query}" if query else "/drug-letters"


def _saved_view_alert_state(subscription: Subscription, settings: Settings) -> str:
    if not subscription.active:
        return "off"
    if subscription.frequency != "immediate":
        return "digest_scheduler_unavailable"
    if not (settings.smtp_enabled and settings.smtp_host and settings.smtp_from_email):
        return "delivery_unavailable"
    return "ready"


def _saved_view_response(
    subscription: Subscription,
    *,
    settings: Settings,
    records: list[tuple[LetterListItem, list[str]]],
) -> SavedViewResponse:
    criteria = _controlled_saved_view_criteria(subscription.criteria)
    matches = [
        item for item, regulations in records if _saved_view_matches(criteria, item, regulations)
    ]
    dates = [item.posted_date for item in matches if item.posted_date]
    frequency = (
        subscription.frequency
        if subscription.frequency in {"immediate", "daily", "weekly"}
        else "immediate"
    )
    return SavedViewResponse(
        id=subscription.id,
        name=subscription.name,
        description=subscription.description,
        criteria=criteria,
        frequency=frequency,
        channel=subscription.channel,
        active=subscription.active,
        alert_state=_saved_view_alert_state(subscription, settings),
        result_count=len(matches),
        last_matched=max(dates) if dates else None,
        owner_id=subscription.owner_id,
        open_url=_saved_view_open_url(criteria),
        created_at=subscription.created_at,
        updated_at=subscription.updated_at,
    )


async def _owned_saved_view(
    session: AsyncSession,
    *,
    saved_view_id: UUID,
    owner_id: str,
) -> Subscription:
    subscription = await session.scalar(
        select(Subscription).where(
            Subscription.id == str(saved_view_id),
            Subscription.owner_id == owner_id,
        )
    )
    if not subscription:
        raise HTTPException(status_code=404, detail="Saved view not found")
    return subscription


@router.get("/saved-views", response_model=SavedViewPage, tags=["Letters"])
async def saved_views(
    cursor: str | None = Query(default=None, max_length=2_048),
    limit: int | None = Query(default=None, ge=1, le=100),
    page_size: int | None = Query(default=None, ge=1, le=100),
    principal: Principal = Depends(view_principal),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> SavedViewPage:
    try:
        offset = decode_cursor(cursor)
    except InvalidCursor as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    rows = list(
        (
            await session.scalars(
                select(Subscription)
                .where(Subscription.owner_id == principal.subject)
                .order_by(Subscription.updated_at.desc(), Subscription.id.desc())
            )
        ).all()
    )
    requested = page_size if page_size is not None else limit
    page_rows, next_cursor, has_more = page_window(
        rows,
        offset=offset,
        limit=min(requested or settings.default_page_size, settings.max_page_size),
    )
    records = await _saved_view_letter_records(session) if page_rows else []
    page = [_saved_view_response(item, settings=settings, records=records) for item in page_rows]
    return SavedViewPage(items=page, next_cursor=next_cursor, has_more=has_more)


@router.post(
    "/saved-views",
    response_model=SavedViewResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Letters"],
)
async def create_saved_view(
    payload: SavedViewCreateRequest,
    request: Request,
    principal: Principal = Depends(view_principal),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> SavedViewResponse:
    duplicate = await session.scalar(
        select(Subscription.id).where(
            Subscription.owner_id == principal.subject,
            func.lower(Subscription.name) == payload.name.casefold(),
        )
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="A saved view with this name already exists")

    enabled = payload.cadence != "off"
    subscription = Subscription(
        owner_id=principal.subject,
        name=payload.name,
        description=payload.description,
        criteria=payload.criteria.model_dump(mode="json", exclude_none=True),
        frequency=payload.cadence if enabled else "immediate",
        channel="email",
        destination_id=settings.notification_default_recipient,
        active=enabled,
    )
    session.add(subscription)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="A saved view with this name already exists",
        ) from exc
    add_audit_event(
        session,
        principal=principal,
        request_id=request.state.request_id,
        operation="saved_view.create",
        object_type="subscription",
        object_id=subscription.id,
        application_version=settings.app_version,
        after={
            "name": subscription.name,
            "criteria": subscription.criteria,
            "frequency": subscription.frequency,
            "active": subscription.active,
        },
    )
    await session.commit()
    records = await _saved_view_letter_records(session)
    return _saved_view_response(subscription, settings=settings, records=records)


@router.patch(
    "/saved-views/{saved_view_id}",
    response_model=SavedViewResponse,
    tags=["Letters"],
)
async def update_saved_view(
    saved_view_id: UUID,
    payload: SavedViewUpdateRequest,
    request: Request,
    principal: Principal = Depends(view_principal),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> SavedViewResponse:
    subscription = await _owned_saved_view(
        session,
        saved_view_id=saved_view_id,
        owner_id=principal.subject,
    )
    before = {
        "name": subscription.name,
        "description": subscription.description,
        "criteria": subscription.criteria,
        "frequency": subscription.frequency,
        "active": subscription.active,
    }
    changed = payload.model_fields_set
    if "name" in changed and payload.name is not None:
        duplicate = await session.scalar(
            select(Subscription.id).where(
                Subscription.owner_id == principal.subject,
                Subscription.id != subscription.id,
                func.lower(Subscription.name) == payload.name.casefold(),
            )
        )
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail="A saved view with this name already exists",
            )
        subscription.name = payload.name
    if "description" in changed and payload.description is not None:
        subscription.description = payload.description
    if "criteria" in changed and payload.criteria is not None:
        subscription.criteria = payload.criteria.model_dump(mode="json", exclude_none=True)
    if "cadence" in changed and payload.cadence is not None:
        subscription.active = payload.cadence != "off"
        if payload.cadence != "off":
            subscription.frequency = payload.cadence
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="A saved view with this name already exists",
        ) from exc
    after = {
        "name": subscription.name,
        "description": subscription.description,
        "criteria": subscription.criteria,
        "frequency": subscription.frequency,
        "active": subscription.active,
    }
    add_audit_event(
        session,
        principal=principal,
        request_id=request.state.request_id,
        operation="saved_view.update",
        object_type="subscription",
        object_id=subscription.id,
        application_version=settings.app_version,
        before=before,
        after=after,
    )
    await session.commit()
    records = await _saved_view_letter_records(session)
    return _saved_view_response(subscription, settings=settings, records=records)


@router.delete(
    "/saved-views/{saved_view_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Letters"],
)
async def delete_saved_view(
    saved_view_id: UUID,
    request: Request,
    principal: Principal = Depends(view_principal),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> Response:
    subscription = await _owned_saved_view(
        session,
        saved_view_id=saved_view_id,
        owner_id=principal.subject,
    )
    before = {
        "name": subscription.name,
        "criteria": subscription.criteria,
        "frequency": subscription.frequency,
        "active": subscription.active,
    }
    add_audit_event(
        session,
        principal=principal,
        request_id=request.state.request_id,
        operation="saved_view.delete",
        object_type="subscription",
        object_id=subscription.id,
        application_version=settings.app_version,
        before=before,
    )
    await session.delete(subscription)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
