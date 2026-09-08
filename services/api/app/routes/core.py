from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import DOCUMENT_ANALYSIS_SCHEMA_VERSION, DOCUMENT_TRANSLATION_SCHEMA_VERSION
from app.config import Settings
from app.dependencies import session_dependency, settings_dependency
from app.enums import ChangeEventType, ReviewState, RunStatus, ScopeStatus
from app.models import (
    AiSummary,
    ChangeEvent,
    Document,
    DocumentTranslation,
    DocumentVersion,
    Finding,
    IngestionRun,
    WarningLetter,
    utcnow,
)
from app.pagination import InvalidCursor, decode_cursor, encode_cursor, page_window
from app.schemas import (
    ChangePage,
    CursorPage,
    DashboardCounts,
    DashboardResponse,
    HealthResponse,
    LetterDetail,
    VersionPage,
)
from app.security.auth import Principal, view_principal

from .serializers import (
    analysis_artifact_response,
    change_response,
    document_response,
    finding_response,
    letter_item,
    summary_response,
    translation_artifact_response,
    version_response,
)

router = APIRouter()


def _aware_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _page_parameters(settings: Settings, limit: int | None, page_size: int | None) -> int:
    requested = page_size if page_size is not None else limit
    return min(requested or settings.default_page_size, settings.max_page_size)


@router.get("/health/live", response_model=HealthResponse, tags=["Health"])
async def live(settings: Settings = Depends(settings_dependency)) -> HealthResponse:
    return HealthResponse(status="ok", service=settings.app_name, version=settings.app_version)


@router.get("/health/ready", response_model=HealthResponse, tags=["Health"])
async def ready(
    request: Request,
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> HealthResponse:
    checks = {"database": "ok", "object_store": "ok"}
    status = "ok"
    try:
        # A connection-only check can report ready before controlled migrations
        # have created the application schema. Touch a required business table.
        await session.execute(select(WarningLetter.id).limit(1))
    except Exception:
        checks["database"] = "schema_unavailable"
        status = "degraded"
    try:
        await asyncio.to_thread(request.app.state.object_store.healthcheck)
    except Exception:
        checks["object_store"] = "unavailable"
        status = "degraded"
    return HealthResponse(
        status=status,
        service=settings.app_name,
        version=settings.app_version,
        checks=checks,
    )


async def _letter_context(
    session: AsyncSession, letters: list[WarningLetter]
) -> tuple[
    dict[str, list[Document]],
    dict[str, AiSummary],
    dict[str, list[Finding]],
]:
    if not letters:
        return {}, {}, {}
    ids = [letter.id for letter in letters]
    documents = list(
        (await session.scalars(select(Document).where(Document.warning_letter_id.in_(ids)))).all()
    )
    by_letter: dict[str, list[Document]] = defaultdict(list)
    for document in documents:
        by_letter[document.warning_letter_id].append(document)
    version_ids = [letter.current_version_id for letter in letters if letter.current_version_id]
    summaries: dict[str, AiSummary] = {}
    findings: dict[str, list[Finding]] = defaultdict(list)
    if version_ids:
        rows = list(
            (
                await session.scalars(
                    select(AiSummary)
                    .where(AiSummary.document_version_id.in_(version_ids))
                    .order_by(AiSummary.created_at.desc(), AiSummary.revision.desc())
                )
            ).all()
        )
        for item in rows:
            summaries.setdefault(item.document_version_id, item)
        selected_summary_ids = {item.id for item in summaries.values()}
        if selected_summary_ids:
            for finding in (
                await session.scalars(
                    select(Finding)
                    .where(Finding.summary_id.in_(selected_summary_ids))
                    .order_by(Finding.created_at, Finding.id)
                )
            ).all():
                findings[finding.document_version_id].append(finding)
    return by_letter, summaries, findings


@router.get("/letters/catalog", response_model=CursorPage, tags=["Letters"])
async def letter_catalog(
    cursor: str | None = Query(default=None, max_length=2_048),
    limit: int = Query(default=1_000, ge=1, le=1_000),
    _principal: Principal = Depends(view_principal),
    session: AsyncSession = Depends(session_dependency),
) -> CursorPage:
    """Bounded metadata batches for the portal's local search and facet controls.

    Paginate in SQL before loading document/summary context. Unlike full document
    reads, this returns only the existing list-item contract, with the same scope
    boundary and stable ordering as /letters. Nothing is cached across principals.
    """
    try:
        offset = decode_cursor(cursor)
    except InvalidCursor as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    query = (
        select(WarningLetter)
        .where(
            WarningLetter.current_in_scope.is_(True),
            WarningLetter.scope_status == ScopeStatus.IN_SCOPE_DRUGS.value,
        )
        .order_by(
            WarningLetter.posted_date.desc(), WarningLetter.last_seen_at.desc(), WarningLetter.id
        )
        .offset(offset)
        .limit(limit + 1)
    )
    rows = list((await session.scalars(query)).all())
    has_more = len(rows) > limit
    letters = rows[:limit]
    docs, summaries, findings = await _letter_context(session, letters)
    return CursorPage(
        items=[
            letter_item(
                letter,
                documents=docs.get(letter.id, []),
                summary=summaries.get(letter.current_version_id or ""),
                findings=findings.get(letter.current_version_id or "", []),
            )
            for letter in letters
        ],
        has_more=has_more,
        next_cursor=encode_cursor(offset + limit) if has_more else None,
    )


@router.get("/letters", response_model=CursorPage, tags=["Letters"])
async def list_letters(
    cursor: str | None = Query(default=None, max_length=2_048),
    limit: int | None = Query(default=None, ge=1, le=100),
    page_size: int | None = Query(default=None, ge=1, le=100),
    posted_from: date | None = None,
    posted_to: date | None = None,
    issuing_office: str | None = Query(default=None, max_length=300),
    company: str | None = Query(default=None, max_length=300),
    drug_subtype: str | None = Query(default=None, max_length=200),
    category: str | None = Query(default=None, max_length=300),
    process_lens: str | None = Query(default=None, max_length=40),
    regulatory_reference: str | None = Query(default=None, max_length=200),
    has_response: bool | None = None,
    has_closeout: bool | None = None,
    review_state: str | None = Query(default=None, max_length=40),
    lifecycle_state: str | None = Query(default=None, max_length=40),
    _principal: Principal = Depends(view_principal),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> CursorPage:
    try:
        offset = decode_cursor(cursor)
    except InvalidCursor as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    query = select(WarningLetter).where(
        WarningLetter.current_in_scope.is_(True),
        WarningLetter.scope_status == ScopeStatus.IN_SCOPE_DRUGS.value,
    )
    if posted_from:
        query = query.where(WarningLetter.posted_date >= posted_from)
    if posted_to:
        query = query.where(WarningLetter.posted_date <= posted_to)
    if company:
        query = query.where(WarningLetter.company_name.ilike(f"%{company}%"))
    if lifecycle_state:
        query = query.where(WarningLetter.lifecycle_status == lifecycle_state)
    query = query.order_by(
        WarningLetter.posted_date.desc(), WarningLetter.last_seen_at.desc(), WarningLetter.id
    )
    letters = list((await session.scalars(query)).all())
    docs, summaries, findings = await _letter_context(session, letters)
    items = []
    for letter in letters:
        summary = summaries.get(letter.current_version_id or "")
        letter_findings = findings.get(letter.current_version_id or "", [])
        item = letter_item(
            letter,
            documents=docs.get(letter.id, []),
            summary=summary,
            findings=letter_findings,
        )
        if issuing_office and not any(
            issuing_office.casefold() in office.casefold() for office in item.issuing_offices
        ):
            continue
        if drug_subtype and drug_subtype not in item.drug_subtypes:
            continue
        if category and category not in item.categories:
            continue
        if process_lens and not any(
            process_lens in value.process_lenses for value in letter_findings
        ):
            continue
        if regulatory_reference and not any(
            regulatory_reference in value.regulatory_references for value in letter_findings
        ):
            continue
        if has_response is not None and item.has_response != has_response:
            continue
        if has_closeout is not None and item.has_closeout != has_closeout:
            continue
        if review_state and item.review_state != review_state:
            continue
        items.append(item)
    page, next_cursor, has_more = page_window(
        items, offset=offset, limit=_page_parameters(settings, limit, page_size)
    )
    return CursorPage(items=page, next_cursor=next_cursor, has_more=has_more)


async def _visible_letter(session: AsyncSession, letter_id: UUID) -> WarningLetter:
    letter = await session.scalar(
        select(WarningLetter).where(
            WarningLetter.id == str(letter_id),
            WarningLetter.current_in_scope.is_(True),
            WarningLetter.scope_status == ScopeStatus.IN_SCOPE_DRUGS.value,
        )
    )
    if not letter:
        raise HTTPException(status_code=404, detail="Drug warning letter not found")
    return letter


@router.get("/letters/{letter_id}", response_model=LetterDetail, tags=["Letters"])
async def get_letter(
    letter_id: UUID,
    _principal: Principal = Depends(view_principal),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> LetterDetail:
    letter = await _visible_letter(session, letter_id)
    documents = list(
        (
            await session.scalars(
                select(Document)
                .where(Document.warning_letter_id == letter.id)
                .order_by(Document.created_at)
            )
        ).all()
    )
    version = (
        await session.get(DocumentVersion, letter.current_version_id)
        if letter.current_version_id
        else None
    )
    summary = None
    findings: list[Finding] = []
    ai_artifacts = []
    if version:
        summary = await session.scalar(
            select(AiSummary)
            .where(AiSummary.document_version_id == version.id)
            .order_by(AiSummary.created_at.desc(), AiSummary.revision.desc())
        )
        if summary:
            findings = list(
                (
                    await session.scalars(
                        select(Finding)
                        .where(Finding.summary_id == summary.id)
                        .order_by(Finding.created_at, Finding.id)
                    )
                ).all()
            )
        translation = await session.scalar(
            select(DocumentTranslation)
            .where(
                DocumentTranslation.document_version_id == version.id,
                DocumentTranslation.language == "ko",
                DocumentTranslation.source_hash == version.canonical_hash,
                DocumentTranslation.schema_version == DOCUMENT_TRANSLATION_SCHEMA_VERSION,
                DocumentTranslation.prompt_version == settings.document_translation_prompt_version,
            )
            .order_by(DocumentTranslation.created_at.desc(), DocumentTranslation.id)
        )
        if translation:
            ai_artifacts.append(translation_artifact_response(translation))
        analysis_summaries = list(
            (
                await session.scalars(
                    select(AiSummary)
                    .where(
                        AiSummary.document_version_id == version.id,
                        AiSummary.language.in_(["en", "ko"]),
                        AiSummary.schema_version == DOCUMENT_ANALYSIS_SCHEMA_VERSION,
                        AiSummary.prompt_version == settings.document_ai_prompt_version,
                    )
                    .order_by(AiSummary.created_at.desc(), AiSummary.revision.desc())
                )
            ).all()
        )
        current_analysis_by_language: dict[str, AiSummary] = {}
        for candidate in analysis_summaries:
            if candidate.language in current_analysis_by_language:
                continue
            if (
                str((candidate.structured_output or {}).get("source_hash", ""))
                == version.canonical_hash
            ):
                current_analysis_by_language[candidate.language] = candidate
        for analysis_summary in current_analysis_by_language.values():
            analysis_findings = list(
                (
                    await session.scalars(
                        select(Finding)
                        .where(Finding.summary_id == analysis_summary.id)
                        .order_by(Finding.created_at, Finding.id)
                    )
                ).all()
            )
            ai_artifacts.extend(
                [
                    analysis_artifact_response(
                        analysis_summary, analysis_findings, artifact_type="findings"
                    ),
                    analysis_artifact_response(
                        analysis_summary, analysis_findings, artifact_type="summary"
                    ),
                ]
            )
    events = list(
        (
            await session.scalars(
                select(ChangeEvent)
                .where(ChangeEvent.warning_letter_id == letter.id)
                .order_by(ChangeEvent.detected_at.desc())
            )
        ).all()
    )
    warning_document = next(
        (item for item in documents if item.document_type == "warning_letter"), None
    )
    return LetterDetail(
        id=letter.id,
        company_name=letter.company_name,
        country=letter.country,
        subject=letter.subject,
        canonical_url=letter.canonical_url,
        marcs_cms_number=letter.marcs_cms_number,
        fda_reference_number=letter.fda_reference_number,
        posted_date=letter.posted_date,
        issue_date=letter.issue_date,
        issuing_offices=letter.issuing_offices or [],
        fda_product_raw=letter.fda_product_raw or [],
        normalized_product_classes=letter.normalized_product_classes or [],
        scope_status=letter.scope_status,
        drug_subtypes=letter.drug_subtypes or [],
        lifecycle_status=letter.lifecycle_status,
        documents=[document_response(item) for item in documents],
        current_version=(
            version_response(version, warning_document) if version and warning_document else None
        ),
        normalized_markdown=version.normalized_markdown if version else None,
        summary=summary_response(summary) if summary else None,
        findings=[finding_response(item) for item in findings],
        ai_artifacts=ai_artifacts,
        lifecycle=[change_response(item, letter.company_name) for item in events],
    )


@router.get("/letters/{letter_id}/versions", response_model=VersionPage, tags=["Letters"])
async def list_versions(
    letter_id: UUID,
    cursor: str | None = Query(default=None, max_length=2_048),
    limit: int | None = Query(default=None, ge=1, le=100),
    page_size: int | None = Query(default=None, ge=1, le=100),
    _principal: Principal = Depends(view_principal),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> VersionPage:
    letter = await _visible_letter(session, letter_id)
    try:
        offset = decode_cursor(cursor)
    except InvalidCursor as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    rows = (
        await session.execute(
            select(DocumentVersion, Document)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(Document.warning_letter_id == letter.id)
            .order_by(DocumentVersion.retrieved_at.desc(), DocumentVersion.id)
        )
    ).all()
    items = [version_response(version, document) for version, document in rows]
    page, next_cursor, has_more = page_window(
        items, offset=offset, limit=_page_parameters(settings, limit, page_size)
    )
    return VersionPage(items=page, next_cursor=next_cursor, has_more=has_more)


@router.get("/changes", response_model=ChangePage, tags=["Changes"])
async def list_changes(
    cursor: str | None = Query(default=None, max_length=2_048),
    limit: int | None = Query(default=None, ge=1, le=100),
    page_size: int | None = Query(default=None, ge=1, le=100),
    event_type: ChangeEventType | None = None,
    detected_from: datetime | None = None,
    detected_to: datetime | None = None,
    _principal: Principal = Depends(view_principal),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> ChangePage:
    try:
        offset = decode_cursor(cursor)
    except InvalidCursor as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    query = (
        select(ChangeEvent, WarningLetter)
        .join(WarningLetter, WarningLetter.id == ChangeEvent.warning_letter_id)
        .where(
            WarningLetter.current_in_scope.is_(True),
            WarningLetter.scope_status == ScopeStatus.IN_SCOPE_DRUGS.value,
        )
    )
    if event_type:
        query = query.where(ChangeEvent.event_type == event_type.value)
    if detected_from:
        query = query.where(ChangeEvent.detected_at >= detected_from)
    if detected_to:
        query = query.where(ChangeEvent.detected_at <= detected_to)
    rows = (
        await session.execute(query.order_by(ChangeEvent.detected_at.desc(), ChangeEvent.id))
    ).all()
    items = [change_response(event, letter.company_name) for event, letter in rows]
    page, next_cursor, has_more = page_window(
        items, offset=offset, limit=_page_parameters(settings, limit, page_size)
    )
    return ChangePage(items=page, next_cursor=next_cursor, has_more=has_more)


@router.get("/dashboard", response_model=DashboardResponse, tags=["Letters"])
async def dashboard(
    _principal: Principal = Depends(view_principal),
    session: AsyncSession = Depends(session_dependency),
) -> DashboardResponse:
    letters = list(
        (
            await session.scalars(
                select(WarningLetter).where(
                    WarningLetter.current_in_scope.is_(True),
                    WarningLetter.scope_status == ScopeStatus.IN_SCOPE_DRUGS.value,
                )
            )
        ).all()
    )
    letter_ids = [item.id for item in letters]
    events: list[ChangeEvent] = []
    if letter_ids:
        events = list(
            (
                await session.scalars(
                    select(ChangeEvent)
                    .where(ChangeEvent.warning_letter_id.in_(letter_ids))
                    .order_by(ChangeEvent.detected_at.desc())
                )
            ).all()
        )
    recent_threshold = utcnow() - timedelta(days=30)
    event_counts = Counter(
        item.event_type for item in events if _aware_utc(item.detected_at) >= recent_threshold
    )
    docs, _summaries, findings = await _letter_context(session, letters)
    pending = await session.scalar(
        select(func.count(AiSummary.id)).where(
            AiSummary.review_state.in_(
                [ReviewState.PENDING.value, ReviewState.NEEDS_REVISION.value]
            )
        )
    )
    exceptions = await session.scalar(
        select(func.count(WarningLetter.id)).where(
            WarningLetter.scope_status.in_(
                [ScopeStatus.AMBIGUOUS.value, ScopeStatus.UNVERIFIED.value]
            )
        )
    )
    last_discovery = await session.scalar(
        select(func.max(IngestionRun.completed_at)).where(
            IngestionRun.run_type == "discovery",
            IngestionRun.status == RunStatus.SUCCEEDED.value,
        )
    )
    category_counts = Counter(
        category
        for values in findings.values()
        for finding in values
        for category in (finding.categories or [])
    )
    office_counts = Counter(office for letter in letters for office in letter.issuing_offices)
    company_by_id = {letter.id: letter.company_name for letter in letters}
    return DashboardResponse(
        counts=DashboardCounts(
            total_drug_letters=len(letters),
            new_letters=event_counts[ChangeEventType.NEW.value],
            updated_letters=event_counts[ChangeEventType.UPDATED.value],
            responses_added=event_counts[ChangeEventType.RESPONSE_ADDED.value],
            closeouts_added=event_counts[ChangeEventType.CLOSEOUT_ADDED.value],
            pending_reviews=int(pending or 0),
            scope_exceptions=int(exceptions or 0),
        ),
        last_successful_discovery=last_discovery,
        recent_events=[
            change_response(item, company_by_id[item.warning_letter_id]) for item in events[:10]
        ],
        category_distribution=[
            {"category": key, "count": value} for key, value in category_counts.most_common()
        ],
        issuing_office_distribution=[
            {"issuing_office": key, "count": value} for key, value in office_counts.most_common()
        ],
    )
