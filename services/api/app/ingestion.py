from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.embedding_store import queue_embedding_job
from app.enums import ChangeEventType, DocumentType, ScopeStatus
from app.models import (
    ChangeEvent,
    Document,
    DocumentChunk,
    DocumentVersion,
    ScopeDecision,
    WarningLetter,
    utcnow,
)
from app.parsing import ParsedDocument, build_chunks, parse_warning_letter_html
from app.security.urls import UnsafeUrlError, canonicalize_fda_url
from app.storage import ImmutableObjectStore, build_object_store


@dataclass(frozen=True)
class CandidateMetadata:
    canonical_url: str
    posted_date: date | None = None
    issue_date: date | None = None
    company_name: str | None = None
    country: str | None = None
    subject: str | None = None
    issuing_office: str | None = None
    marcs_cms_number: str | None = None
    fda_reference_number: str | None = None
    http_provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IngestionResult:
    warning_letter_id: str
    document_id: str
    version_id: str
    scope_status: ScopeStatus
    version_created: bool
    events: list[ChangeEventType]
    chunks_created: int


def _metadata_first(parsed: ParsedDocument, *keys: str) -> str | None:
    for key in keys:
        values = parsed.metadata.get(key, [])
        if values:
            return values[0]
    return None


def _json_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


async def _add_event(
    session: AsyncSession,
    *,
    letter: WarningLetter,
    document: Document | None,
    version: DocumentVersion | None,
    event_type: ChangeEventType,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    suffix: str,
) -> ChangeEvent | None:
    dedupe = hashlib.sha256(f"{letter.id}:{event_type.value}:{suffix}".encode()).hexdigest()
    existing = await session.scalar(
        select(ChangeEvent).where(ChangeEvent.deduplication_key == dedupe)
    )
    if existing:
        return None
    event = ChangeEvent(
        warning_letter_id=letter.id,
        document_id=document.id if document else None,
        source_version_id=version.id if version else None,
        previous_source_version_id=letter.current_version_id,
        event_type=event_type.value,
        before_state=before,
        after_state=after,
        deduplication_key=dedupe,
        published_at=utcnow() if letter.current_in_scope else None,
    )
    session.add(event)
    await session.flush()
    if event_type in {ChangeEventType.NEW, ChangeEventType.UPDATED}:
        # Import locally to keep the ingestion core independent of SMTP details.
        from app.notifications import queue_event_notifications

        await queue_event_notifications(session, event=event, letter=letter)
    return event


async def _ensure_child_documents(
    session: AsyncSession,
    settings: Settings,
    letter: WarningLetter,
    parent: Document,
    parsed: ParsedDocument,
    current_version: DocumentVersion,
) -> list[ChangeEventType]:
    events: list[ChangeEventType] = []
    for link in parsed.source_links:
        label = link["label"].casefold()
        if "closeout" in label:
            doc_type = DocumentType.CLOSEOUT
            event_type = ChangeEventType.CLOSEOUT_ADDED
        elif "response" in label:
            doc_type = DocumentType.RESPONSE
            event_type = ChangeEventType.RESPONSE_ADDED
        else:
            continue
        try:
            child_url = canonicalize_fda_url(
                urljoin(parent.canonical_url, link["url"]), settings.fda_allowed_hosts
            )
        except UnsafeUrlError:
            continue
        child = await session.scalar(select(Document).where(Document.canonical_url == child_url))
        if child:
            continue
        child = Document(
            warning_letter_id=letter.id,
            parent_document_id=parent.id,
            document_type=doc_type.value,
            canonical_url=child_url,
            title=link["label"] or doc_type.value.replace("_", " ").title(),
            current_in_scope=False,
        )
        session.add(child)
        await session.flush()
        created = await _add_event(
            session,
            letter=letter,
            document=child,
            version=current_version,
            event_type=event_type,
            before=None,
            after={"url": child_url, "document_type": doc_type.value},
            suffix=child_url,
        )
        if created:
            events.append(event_type)
    return events


async def ingest_html(
    session: AsyncSession,
    settings: Settings,
    candidate: CandidateMetadata,
    html: bytes,
    *,
    object_store: ImmutableObjectStore | None = None,
) -> IngestionResult:
    """Parse, scope, version, and chunk one canonical FDA source atomically."""
    canonical_url = canonicalize_fda_url(candidate.canonical_url, settings.fda_allowed_hosts)
    parsed = parse_warning_letter_html(html)
    now = utcnow()
    raw_sha = hashlib.sha256(html).hexdigest()
    store = object_store or build_object_store(settings)

    letter = await session.scalar(
        select(WarningLetter).where(WarningLetter.canonical_url == canonical_url)
    )
    is_new_letter = letter is None
    if letter is None:
        letter = WarningLetter(
            canonical_url=canonical_url,
            company_name=candidate.company_name or parsed.company_name,
            country=candidate.country or parsed.recipient_country,
            marcs_cms_number=candidate.marcs_cms_number
            or _metadata_first(parsed, "marcs-cms number", "marcs cms"),
            fda_reference_number=candidate.fda_reference_number
            or _metadata_first(parsed, "reference number"),
            subject=candidate.subject or parsed.title,
            posted_date=candidate.posted_date,
            issue_date=candidate.issue_date or parsed.issue_date,
            issuing_offices=[candidate.issuing_office] if candidate.issuing_office else [],
            first_seen_at=now,
            last_seen_at=now,
        )
        session.add(letter)
        await session.flush()

    previous_scope = letter.scope_status
    previous_products = list(letter.normalized_product_classes or [])
    previous_version_id = letter.current_version_id
    letter.last_seen_at = now
    letter.company_name = candidate.company_name or parsed.company_name or letter.company_name
    letter.country = candidate.country or parsed.recipient_country or letter.country
    letter.subject = candidate.subject or parsed.title or letter.subject
    letter.issue_date = candidate.issue_date or parsed.issue_date or letter.issue_date
    letter.posted_date = candidate.posted_date or letter.posted_date
    if candidate.issuing_office and candidate.issuing_office not in letter.issuing_offices:
        letter.issuing_offices = [*letter.issuing_offices, candidate.issuing_office]

    document = await session.scalar(select(Document).where(Document.canonical_url == canonical_url))
    if document is None:
        document = Document(
            warning_letter_id=letter.id,
            document_type=DocumentType.WARNING_LETTER.value,
            canonical_url=canonical_url,
            title=parsed.title,
            issue_date=candidate.issue_date or parsed.issue_date,
        )
        session.add(document)
        await session.flush()

    previous_version = None
    if document.current_version_id:
        previous_version = await session.get(DocumentVersion, document.current_version_id)
    version_created = previous_version is None or (
        previous_version.canonical_hash != parsed.canonical_hash
    )
    if version_created:
        version_number = (
            await session.scalar(
                select(func.count(DocumentVersion.id)).where(
                    DocumentVersion.document_id == document.id
                )
            )
            or 0
        ) + 1
        eligible_body = parsed.scope.status == ScopeStatus.IN_SCOPE_DRUGS and bool(
            parsed.normalized_text
        )
        raw_key: str | None = None
        if eligible_body:
            raw_key, raw_sha = store.put("fda-html", html)
        version = DocumentVersion(
            document_id=document.id,
            version_number=version_number,
            raw_object_key=raw_key,
            raw_sha256=raw_sha,
            canonical_hash=parsed.canonical_hash,
            normalized_markdown=parsed.normalized_markdown if eligible_body else None,
            normalized_text=parsed.normalized_text if eligible_body else None,
            source_anchors=parsed.anchors if eligible_body else [],
            source_links=parsed.source_links if eligible_body else [],
            http_provenance={
                "final_url": canonical_url,
                "retrieved_at": now.isoformat(),
                **candidate.http_provenance,
            },
            parser_version=settings.parser_version,
            parser_warnings=parsed.warnings,
            fda_product_raw=parsed.scope.raw_values,
            normalized_product_classes=parsed.scope.normalized_classes,
            scope_status=parsed.scope.status.value,
            extraction_metadata={
                "title": parsed.title,
                "company_name": parsed.company_name,
                "recipient_country": parsed.recipient_country,
                "body_non_empty": bool(parsed.normalized_text),
            },
            retrieved_at=now,
            last_seen_at=now,
        )
        session.add(version)
        await session.flush()
        document.current_version_id = version.id
    else:
        version = previous_version
        assert version is not None
        version.last_seen_at = now
        extraction_metadata = dict(version.extraction_metadata or {})
        if (
            parsed.recipient_country
            and extraction_metadata.get("recipient_country") != parsed.recipient_country
        ):
            extraction_metadata["recipient_country"] = parsed.recipient_country
            version.extraction_metadata = extraction_metadata

    fingerprint = _json_hash(
        {
            "version": version.id,
            "raw": parsed.scope.raw_values,
            "normalized": parsed.scope.normalized_classes,
            "status": parsed.scope.status.value,
            "rule": settings.drug_scope_rule_version,
        }
    )
    prior_decision = await session.scalar(
        select(ScopeDecision).where(ScopeDecision.decision_fingerprint == fingerprint)
    )
    if not prior_decision:
        session.add(
            ScopeDecision(
                warning_letter_id=letter.id,
                source_version_id=version.id,
                canonical_url=canonical_url,
                fda_product_raw=parsed.scope.raw_values,
                normalized_product_classes=parsed.scope.normalized_classes,
                scope_status=parsed.scope.status.value,
                scope_rule_version=settings.drug_scope_rule_version,
                scope_source_anchor=parsed.scope.source_anchor,
                decision_fingerprint=fingerprint,
                rationale=parsed.scope.rationale,
                decided_at=now,
            )
        )

    eligible = parsed.scope.status == ScopeStatus.IN_SCOPE_DRUGS and bool(parsed.normalized_text)
    letter.fda_product_raw = parsed.scope.raw_values
    letter.normalized_product_classes = parsed.scope.normalized_classes
    letter.scope_status = parsed.scope.status.value
    letter.scope_rule_version = settings.drug_scope_rule_version
    letter.scope_source_anchor = parsed.scope.source_anchor
    letter.scope_decided_at = now
    letter.current_in_scope = eligible
    document.current_in_scope = eligible
    if eligible:
        letter.current_version_id = version.id
        if not letter.first_in_scope_version_id:
            letter.first_in_scope_version_id = version.id

    events: list[ChangeEventType] = []
    if is_new_letter:
        created = await _add_event(
            session,
            letter=letter,
            document=document,
            version=version,
            event_type=ChangeEventType.NEW,
            before=None,
            after={"scope_status": parsed.scope.status.value},
            suffix=version.id,
        )
        if created:
            events.append(ChangeEventType.NEW)
    elif version_created:
        created = await _add_event(
            session,
            letter=letter,
            document=document,
            version=version,
            event_type=ChangeEventType.UPDATED,
            before={"source_version_id": previous_version_id},
            after={"source_version_id": version.id},
            suffix=version.id,
        )
        if created:
            events.append(ChangeEventType.UPDATED)

    scope_changed = (not is_new_letter) and (
        previous_scope != parsed.scope.status.value
        or previous_products != parsed.scope.normalized_classes
    )
    if scope_changed:
        created = await _add_event(
            session,
            letter=letter,
            document=document,
            version=version,
            event_type=ChangeEventType.SCOPE_CHANGED,
            before={"scope_status": previous_scope, "product": previous_products},
            after={
                "scope_status": parsed.scope.status.value,
                "product": parsed.scope.normalized_classes,
            },
            suffix=fingerprint,
        )
        if created:
            events.append(ChangeEventType.SCOPE_CHANGED)

    if not parsed.normalized_text:
        created = await _add_event(
            session,
            letter=letter,
            document=document,
            version=version,
            event_type=ChangeEventType.PARSE_FAILED,
            before=None,
            after={"reason": "empty canonical body"},
            suffix=f"{version.id}:empty",
        )
        if created:
            events.append(ChangeEventType.PARSE_FAILED)

    chunks_created = 0
    if eligible and version_created:
        for chunk in build_chunks(parsed.anchors):
            session.add(
                DocumentChunk(
                    document_version_id=version.id,
                    warning_letter_id=letter.id,
                    ordinal=chunk["ordinal"],
                    section_path=chunk["section_path"],
                    source_anchor=chunk["source_anchor"],
                    content=chunk["content"],
                    token_estimate=chunk["token_estimate"],
                    drug_subtypes=letter.drug_subtypes,
                    regulatory_references=chunk["regulatory_references"],
                    chunker_version=settings.chunker_version,
                )
            )
            chunks_created += 1
        if chunks_created:
            await queue_embedding_job(
                session,
                settings,
                warning_letter_id=letter.id,
                document_version_id=version.id,
            )
        events.extend(
            await _ensure_child_documents(session, settings, letter, document, parsed, version)
        )

    await session.flush()
    return IngestionResult(
        warning_letter_id=letter.id,
        document_id=document.id,
        version_id=version.id,
        scope_status=parsed.scope.status,
        version_created=version_created,
        events=events,
        chunks_created=chunks_created,
    )


async def ingest_fixture(
    session: AsyncSession,
    settings: Settings,
    fixture_path: Path,
    *,
    canonical_url: str | None = None,
    object_store: ImmutableObjectStore | None = None,
) -> IngestionResult:
    html = fixture_path.read_bytes()
    url = canonical_url
    if not url:
        slug = fixture_path.stem.lower().replace("_", "-")
        url = f"https://www.fda.gov/warning-letters/{slug}"
    return await ingest_html(
        session,
        settings,
        CandidateMetadata(canonical_url=url),
        html,
        object_store=object_store,
    )
