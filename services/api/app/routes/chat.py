from __future__ import annotations

import unicodedata
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.dependencies import session_dependency, settings_dependency
from app.enums import ScopeStatus
from app.models import (
    ChatMessage,
    ChatThread,
    ChatThreadFocus,
    Document,
    DocumentChunk,
    DocumentVersion,
    WarningLetter,
    utcnow,
)
from app.schemas import (
    ChatDocumentFocusResponse,
    ChatDocumentFocusSelect,
    ChatMessageResponse,
    ChatThreadCreate,
    ChatThreadDetail,
    ChatThreadPage,
    ChatThreadPatch,
    ChatThreadSummary,
)
from app.security.auth import Principal, rag_principal

router = APIRouter(prefix="/chat/threads", tags=["Chat"])


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _normalized_search_query(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _escaped_like_fragment(value: str) -> str:
    # Backslash is the explicit SQL LIKE escape character below. Escape it
    # first, then protect the two LIKE wildcard characters so user input is
    # always treated as literal text.
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def thread_summary(thread: ChatThread) -> ChatThreadSummary:
    focus = thread.focus
    return ChatThreadSummary(
        id=thread.id,
        title=thread.title,
        model_preference=thread.model_preference,
        retrieval_preference=thread.retrieval_preference,
        active_letter_ids=thread.active_letter_ids or [],
        focus=(
            ChatDocumentFocusResponse(
                warning_letter_id=focus.warning_letter_id,
                document_id=focus.document_id,
                document_version_id=focus.document_version_id,
                source_chunk_id=focus.source_chunk_id,
                source_message_id=focus.source_message_id,
                selected_at=_as_utc(focus.selected_at),
            )
            if focus is not None
            else None
        ),
        archived_at=_as_utc(thread.archived_at),
        last_message_at=_as_utc(thread.last_message_at),
        created_at=_as_utc(thread.created_at),
        updated_at=_as_utc(thread.updated_at),
    )


def message_response(message: ChatMessage) -> ChatMessageResponse:
    return ChatMessageResponse(
        id=message.id,
        sequence=message.sequence,
        role=message.role,
        content=message.content,
        status=message.status,
        client_message_id=message.client_message_id,
        rag_query_id=message.rag_query_id,
        citations=message.citations or [],
        route_metadata=message.route_metadata or {},
        model_metadata=message.model_metadata or {},
        created_at=_as_utc(message.created_at),
        updated_at=_as_utc(message.updated_at),
    )


async def owned_thread_or_404(
    session: AsyncSession,
    thread_id: UUID | str,
    owner_subject: str,
    *,
    for_update: bool = False,
) -> ChatThread:
    statement = (
        select(ChatThread)
        .options(selectinload(ChatThread.focus))
        .where(
            ChatThread.id == str(thread_id),
            ChatThread.owner_subject == owner_subject,
        )
    )
    if for_update:
        statement = statement.with_for_update()
    thread = (await session.execute(statement)).scalar_one_or_none()
    if thread is None:
        # Deliberately conceal whether another user owns this identifier.
        raise HTTPException(status_code=404, detail="Chat thread was not found")
    return thread


def _acl_allows(acl: dict[str, object] | None, principal: Principal) -> bool:
    roles = {str(item) for item in ((acl or {}).get("roles") or [])}
    return not roles or "viewer" in roles or bool(roles.intersection(principal.roles))


async def _validated_active_letter_ids(
    session: AsyncSession,
    requested_ids: list[UUID],
    *,
    principal: Principal,
    chunker_version: str,
) -> list[str]:
    normalized = list(dict.fromkeys(str(item) for item in requested_ids))
    if not normalized:
        return []
    rows = (
        await session.execute(
            select(DocumentChunk, WarningLetter)
            .join(WarningLetter, WarningLetter.id == DocumentChunk.warning_letter_id)
            .join(DocumentVersion, DocumentVersion.id == DocumentChunk.document_version_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(
                WarningLetter.id.in_(normalized),
                WarningLetter.current_in_scope.is_(True),
                WarningLetter.scope_status == ScopeStatus.IN_SCOPE_DRUGS.value,
                WarningLetter.current_version_id == DocumentChunk.document_version_id,
                Document.warning_letter_id == WarningLetter.id,
                Document.current_version_id == DocumentVersion.id,
                Document.current_in_scope.is_(True),
                Document.source_available.is_(True),
                DocumentVersion.scope_status == ScopeStatus.IN_SCOPE_DRUGS.value,
                DocumentChunk.corpus_id == "fda-drugs",
                DocumentChunk.chunker_version == chunker_version,
            )
        )
    ).all()
    authorized = {
        str(letter.id)
        for chunk, letter in rows
        if _acl_allows(chunk.acl, principal)
    }
    if any(item not in authorized for item in normalized):
        raise HTTPException(status_code=422, detail="Active letter scope is not available")
    return normalized


def _clear_focus(thread: ChatThread) -> None:
    thread.focus = None


async def _thread_detail(session: AsyncSession, thread: ChatThread) -> ChatThreadDetail:
    messages = (
        await session.execute(
            select(ChatMessage)
            .where(ChatMessage.thread_id == thread.id)
            .order_by(ChatMessage.sequence, ChatMessage.id)
        )
    ).scalars()
    return ChatThreadDetail(
        **thread_summary(thread).model_dump(),
        messages=[message_response(message) for message in messages],
    )


@router.get("", response_model=ChatThreadPage)
async def list_threads(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    include_archived: bool = Query(default=False),
    q: str | None = Query(default=None, max_length=200),
    principal: Principal = Depends(rag_principal),
    session: AsyncSession = Depends(session_dependency),
) -> ChatThreadPage:
    predicates = [ChatThread.owner_subject == principal.subject]
    if not include_archived:
        predicates.append(ChatThread.archived_at.is_(None))
    normalized_query = _normalized_search_query(q)
    if normalized_query:
        pattern = f"%{_escaped_like_fragment(normalized_query)}%"
        message_match = (
            select(ChatMessage.id)
            .where(
                ChatMessage.thread_id == ChatThread.id,
                ChatMessage.content.ilike(pattern, escape="\\"),
            )
            .exists()
        )
        predicates.append(
            or_(
                ChatThread.title.ilike(pattern, escape="\\"),
                message_match,
            )
        )
    total = (
        await session.execute(select(func.count(ChatThread.id)).where(*predicates))
    ).scalar_one()
    threads = (
        await session.execute(
            select(ChatThread)
            .options(selectinload(ChatThread.focus))
            .where(*predicates)
            .order_by(
                ChatThread.last_message_at.desc().nullslast(),
                ChatThread.updated_at.desc(),
                ChatThread.id,
            )
            .offset((page - 1) * limit)
            .limit(limit)
        )
    ).scalars()
    items = [thread_summary(thread) for thread in threads]
    return ChatThreadPage(
        items=items,
        page=page,
        limit=limit,
        total=total,
        has_more=page * limit < total,
    )


@router.post("", response_model=ChatThreadDetail, status_code=status.HTTP_201_CREATED)
async def create_thread(
    payload: ChatThreadCreate,
    principal: Principal = Depends(rag_principal),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> ChatThreadDetail:
    active_letter_ids = (
        []
        if payload.retrieval_preference in {"corpus", "none"}
        else await _validated_active_letter_ids(
            session,
            payload.active_letter_ids,
            principal=principal,
            chunker_version=settings.chunker_version,
        )
    )
    thread = ChatThread(
        owner_subject=principal.subject,
        title=payload.title,
        model_preference=payload.model_preference,
        retrieval_preference=payload.retrieval_preference,
        active_letter_ids=active_letter_ids,
        focus=None,
    )
    session.add(thread)
    await session.commit()
    return ChatThreadDetail(**thread_summary(thread).model_dump(), messages=[])


@router.get("/{thread_id}", response_model=ChatThreadDetail)
async def get_thread(
    thread_id: UUID,
    principal: Principal = Depends(rag_principal),
    session: AsyncSession = Depends(session_dependency),
) -> ChatThreadDetail:
    thread = await owned_thread_or_404(session, thread_id, principal.subject)
    # Import locally to avoid coupling router import order while sharing the exact recovery
    # threshold used by POST /rag/query. Row locks and the status predicate prevent a read-side
    # reconciliation from overwriting a response that completed concurrently.
    from app.routes.intelligence import CHAT_PENDING_STALE_AFTER

    now = utcnow()
    stale_pending = list(
        (
            await session.scalars(
                select(ChatMessage)
                .where(
                    ChatMessage.thread_id == thread.id,
                    ChatMessage.role == "assistant",
                    ChatMessage.status == "pending",
                    ChatMessage.updated_at <= now - CHAT_PENDING_STALE_AFTER,
                )
                .with_for_update()
            )
        ).all()
    )
    for message in stale_pending:
        route_metadata = dict(message.route_metadata or {})
        route_metadata.update(
            {
                "failure_code": "stale_pending",
                "failed_at": now.isoformat(),
            }
        )
        model_metadata = dict(message.model_metadata or {})
        model_metadata.update(
            {
                "generation_used": False,
                "effective_model_id": None,
                "model_id": None,
            }
        )
        message.status = "failed"
        message.content = (
            "답변 생성이 중단되었습니다. 다시 시도해 주세요."
            if any("가" <= character <= "힣" for character in message.content)
            else "Response generation stopped. Please retry."
        )
        message.route_metadata = route_metadata
        message.model_metadata = model_metadata
        message.updated_at = now
    if stale_pending:
        thread.updated_at = now
        await session.commit()
    return await _thread_detail(session, thread)


@router.patch("/{thread_id}", response_model=ChatThreadDetail)
async def patch_thread(
    thread_id: UUID,
    payload: ChatThreadPatch,
    principal: Principal = Depends(rag_principal),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> ChatThreadDetail:
    thread = await owned_thread_or_404(
        session, thread_id, principal.subject, for_update=True
    )
    changes = payload.model_dump(exclude_unset=True)
    if thread.archived_at is not None and changes != {"archived": False}:
        raise HTTPException(status_code=409, detail="Archived chat threads are read-only")
    if "title" in changes:
        thread.title = changes["title"]
    if "model_preference" in changes:
        thread.model_preference = changes["model_preference"]
    next_retrieval_preference = changes.get(
        "retrieval_preference", thread.retrieval_preference
    )
    if "active_letter_ids" in changes:
        if next_retrieval_preference in {"corpus", "none"}:
            thread.active_letter_ids = []
        else:
            thread.active_letter_ids = await _validated_active_letter_ids(
                session,
                changes["active_letter_ids"],
                principal=principal,
                chunker_version=settings.chunker_version,
            )
            if thread.focus and thread.active_letter_ids != [thread.focus.warning_letter_id]:
                _clear_focus(thread)
    if "retrieval_preference" in changes:
        thread.retrieval_preference = next_retrieval_preference
    if next_retrieval_preference in {"corpus", "none"}:
        thread.active_letter_ids = []
        _clear_focus(thread)
    if "archived" in changes:
        thread.archived_at = utcnow() if changes["archived"] else None
    thread.updated_at = utcnow()
    await session.commit()
    return await _thread_detail(session, thread)


@router.put("/{thread_id}/focus", response_model=ChatThreadDetail)
async def focus_thread_on_citation(
    thread_id: UUID,
    payload: ChatDocumentFocusSelect,
    principal: Principal = Depends(rag_principal),
    session: AsyncSession = Depends(session_dependency),
) -> ChatThreadDetail:
    thread = await owned_thread_or_404(
        session, thread_id, principal.subject, for_update=True
    )
    if thread.archived_at is not None:
        raise HTTPException(status_code=409, detail="Archived chat threads are read-only")

    assistant_message = (
        await session.execute(
            select(ChatMessage)
            .where(
                ChatMessage.id == str(payload.assistant_message_id),
                ChatMessage.thread_id == thread.id,
                ChatMessage.role == "assistant",
                ChatMessage.status == "completed",
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if assistant_message is None:
        raise HTTPException(status_code=404, detail="Cited assistant answer was not found")

    chunk_id = str(payload.chunk_id)
    citation = next(
        (
            item
            for item in (assistant_message.citations or [])
            if isinstance(item, dict) and str(item.get("chunk_id") or "") == chunk_id
        ),
        None,
    )
    if citation is None:
        raise HTTPException(status_code=404, detail="Citation was not found in this answer")

    source_row = (
        await session.execute(
            select(DocumentChunk, DocumentVersion, Document, WarningLetter)
            .join(
                DocumentVersion,
                DocumentVersion.id == DocumentChunk.document_version_id,
            )
            .join(Document, Document.id == DocumentVersion.document_id)
            .join(WarningLetter, WarningLetter.id == DocumentChunk.warning_letter_id)
            .where(
                DocumentChunk.id == chunk_id,
                DocumentChunk.corpus_id == "fda-drugs",
                Document.warning_letter_id == WarningLetter.id,
                Document.current_version_id == DocumentVersion.id,
                Document.current_in_scope.is_(True),
                Document.source_available.is_(True),
                DocumentVersion.scope_status == ScopeStatus.IN_SCOPE_DRUGS.value,
                WarningLetter.current_version_id == DocumentVersion.id,
                WarningLetter.current_in_scope.is_(True),
                WarningLetter.scope_status == ScopeStatus.IN_SCOPE_DRUGS.value,
            )
            .with_for_update()
        )
    ).first()
    if source_row is None:
        raise HTTPException(status_code=409, detail="Cited document is no longer current")
    chunk, version, document, letter = source_row
    if not _acl_allows(chunk.acl, principal):
        raise HTTPException(status_code=404, detail="Citation was not found in this answer")
    if str(citation.get("warning_letter_id") or "") != letter.id:
        raise HTTPException(status_code=409, detail="Stored citation provenance is inconsistent")

    focus_matches = thread.focus is not None and (
        thread.focus.warning_letter_id,
        thread.focus.document_id,
        thread.focus.document_version_id,
        thread.focus.source_chunk_id,
        thread.focus.source_message_id,
    ) == (letter.id, document.id, version.id, chunk.id, assistant_message.id)
    thread_scope_matches = (
        thread.active_letter_ids == [letter.id]
        and thread.retrieval_preference == "letter"
    )
    if focus_matches and thread_scope_matches:
        return await _thread_detail(session, thread)

    now = utcnow()
    if thread.focus is None:
        thread.focus = ChatThreadFocus(
            thread_id=thread.id,
            warning_letter_id=letter.id,
            document_id=document.id,
            document_version_id=version.id,
            source_chunk_id=chunk.id,
            source_message_id=assistant_message.id,
            selected_at=now,
        )
    elif not focus_matches:
        thread.focus.warning_letter_id = letter.id
        thread.focus.document_id = document.id
        thread.focus.document_version_id = version.id
        thread.focus.source_chunk_id = chunk.id
        thread.focus.source_message_id = assistant_message.id
        thread.focus.selected_at = now
    if not thread_scope_matches:
        thread.active_letter_ids = [letter.id]
        thread.retrieval_preference = "letter"
    thread.updated_at = now
    await session.commit()
    return await _thread_detail(session, thread)


@router.delete("/{thread_id}/focus", response_model=ChatThreadDetail)
async def clear_thread_focus(
    thread_id: UUID,
    principal: Principal = Depends(rag_principal),
    session: AsyncSession = Depends(session_dependency),
) -> ChatThreadDetail:
    thread = await owned_thread_or_404(
        session, thread_id, principal.subject, for_update=True
    )
    if thread.archived_at is not None:
        raise HTTPException(status_code=409, detail="Archived chat threads are read-only")
    _clear_focus(thread)
    thread.active_letter_ids = []
    if thread.retrieval_preference == "letter":
        thread.retrieval_preference = "auto"
    thread.updated_at = utcnow()
    await session.commit()
    return await _thread_detail(session, thread)


@router.post(
    "/{thread_id}/messages/{client_message_id}/cancel",
    response_model=ChatMessageResponse,
)
async def cancel_pending_message(
    thread_id: UUID,
    client_message_id: str,
    principal: Principal = Depends(rag_principal),
    session: AsyncSession = Depends(session_dependency),
) -> ChatMessageResponse:
    """Idempotently cancel the pending assistant turn owned by one client message."""

    normalized_client_id = client_message_id.strip()
    if not normalized_client_id or len(normalized_client_id) > 100:
        raise HTTPException(status_code=422, detail="Invalid client message ID")
    thread = await owned_thread_or_404(
        session, thread_id, principal.subject, for_update=True
    )
    user_message = (
        await session.execute(
            select(ChatMessage)
            .where(
                ChatMessage.thread_id == thread.id,
                ChatMessage.role == "user",
                ChatMessage.client_message_id == normalized_client_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if user_message is None:
        raise HTTPException(status_code=404, detail="Chat message was not found")
    assistant_message = (
        await session.execute(
            select(ChatMessage)
            .where(
                ChatMessage.thread_id == thread.id,
                ChatMessage.role == "assistant",
                ChatMessage.in_reply_to_id == user_message.id,
            )
            .order_by(ChatMessage.sequence, ChatMessage.id)
            .limit(1)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if assistant_message is None:
        raise HTTPException(status_code=404, detail="Assistant response was not found")
    if assistant_message.status != "pending":
        return message_response(assistant_message)

    now = utcnow()
    route_metadata = dict(assistant_message.route_metadata or {})
    route_metadata.update(
        {
            "failure_code": "user_cancelled",
            "cancelled_at": now.isoformat(),
        }
    )
    model_metadata = dict(assistant_message.model_metadata or {})
    model_metadata.update(
        {
            "generation_used": False,
            "effective_model_id": None,
            "model_id": None,
        }
    )
    korean = any("가" <= character <= "힣" for character in user_message.content)
    assistant_message.status = "cancelled"
    assistant_message.content = (
        "사용자가 답변 요청을 중지했습니다. 다시 시도할 수 있습니다."
        if korean
        else "The answer request was stopped by the user. It can be retried."
    )
    assistant_message.route_metadata = route_metadata
    assistant_message.model_metadata = model_metadata
    assistant_message.updated_at = now
    thread.updated_at = now
    await session.commit()
    return message_response(assistant_message)


@router.delete("/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_thread(
    thread_id: UUID,
    principal: Principal = Depends(rag_principal),
    session: AsyncSession = Depends(session_dependency),
) -> Response:
    thread = await owned_thread_or_404(session, thread_id, principal.subject)
    thread.archived_at = utcnow()
    thread.updated_at = utcnow()
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
