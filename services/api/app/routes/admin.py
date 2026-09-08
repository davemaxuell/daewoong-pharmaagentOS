from __future__ import annotations

import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import add_audit_event
from app.config import Settings
from app.dependencies import session_dependency, settings_dependency
from app.embeddings import (
    GEMINI_EMBEDDING_INPUT_SCHEMA_VERSION,
    GEMINI_EMBEDDING_PROVIDER,
)
from app.enums import JobStatus, RunStatus
from app.models import (
    Document,
    DocumentVersion,
    IngestionRun,
    NotificationDelivery,
    ProcessingJob,
    WarningLetter,
)
from app.notifications import ensure_default_email_subscription, normalize_email
from app.pagination import InvalidCursor, decode_cursor, page_window
from app.schemas import (
    IngestionRunPage,
    IngestionRunResponse,
    JobAccepted,
    NotificationSettingsPatch,
    NotificationSettingsResponse,
    ReprocessRequest,
    RuntimeConfigurationResponse,
    StartIngestionRequest,
)
from app.security.auth import (
    Principal,
    admin_auditor_principal,
    admin_principal,
)

from .serializers import ingestion_run_response

router = APIRouter()


def _fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


@router.get(
    "/admin/runtime-configuration",
    response_model=RuntimeConfigurationResponse,
    tags=["Administration"],
)
async def runtime_configuration(
    _principal: Principal = Depends(admin_auditor_principal),
    settings: Settings = Depends(settings_dependency),
) -> RuntimeConfigurationResponse:
    """Return non-secret active component versions for operational verification."""

    return RuntimeConfigurationResponse(
        application_version=settings.app_version,
        parser_version=settings.parser_version,
        scope_rule_version=settings.drug_scope_rule_version,
        taxonomy_version=settings.taxonomy_version,
        chunker_version=settings.chunker_version,
        ai_provider=settings.llm_provider,
        ai_model_id=settings.llm_model_id,
        ai_prompt_version=settings.llm_prompt_version,
        ai_configured=(settings.llm_provider == "gemini" and bool(settings.gemini_api_key))
        or (settings.llm_provider == "openai" and bool(settings.openai_api_key)),
        embedding_enabled=settings.embedding_enabled and bool(settings.gemini_api_key),
        embedding_provider=GEMINI_EMBEDDING_PROVIDER,
        embedding_model_id=settings.embedding_model_id,
        embedding_dimensions=settings.embedding_dimensions,
        embedding_input_schema_version=GEMINI_EMBEDDING_INPUT_SCHEMA_VERSION,
        corpus_backfill_years=settings.corpus_backfill_years,
        corpus_active_retention_years=settings.corpus_active_retention_years,
        smtp_delivery_enabled=settings.smtp_enabled,
        smtp_configured=bool(settings.smtp_host and settings.smtp_from_email),
    )


async def _notification_settings_response(
    session: AsyncSession, settings: Settings
) -> NotificationSettingsResponse:
    subscription = await ensure_default_email_subscription(session, settings)
    queued = await session.scalar(
        select(func.count(NotificationDelivery.id)).where(
            NotificationDelivery.subscription_id == subscription.id,
            NotificationDelivery.status == "queued",
        )
    )
    failed = await session.scalar(
        select(func.count(NotificationDelivery.id)).where(
            NotificationDelivery.subscription_id == subscription.id,
            NotificationDelivery.status == "failed",
        )
    )
    last_delivered = await session.scalar(
        select(func.max(NotificationDelivery.delivered_at)).where(
            NotificationDelivery.subscription_id == subscription.id,
            NotificationDelivery.status == "sent",
        )
    )
    return NotificationSettingsResponse(
        subscription_id=subscription.id,
        target_email=subscription.destination_id,
        enabled=subscription.active,
        event_types=["NEW", "UPDATED"],
        smtp_delivery_enabled=settings.smtp_enabled,
        smtp_configured=bool(settings.smtp_host and settings.smtp_from_email),
        queued_deliveries=queued or 0,
        failed_deliveries=failed or 0,
        last_delivered_at=last_delivered,
        updated_at=subscription.updated_at,
    )


@router.get(
    "/admin/notification-settings",
    response_model=NotificationSettingsResponse,
    tags=["Administration"],
)
async def get_notification_settings(
    _principal: Principal = Depends(admin_auditor_principal),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> NotificationSettingsResponse:
    response = await _notification_settings_response(session, settings)
    await session.commit()
    return response


@router.patch(
    "/admin/notification-settings",
    response_model=NotificationSettingsResponse,
    tags=["Administration"],
)
async def update_notification_settings(
    payload: NotificationSettingsPatch,
    request: Request,
    principal: Principal = Depends(admin_principal),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> NotificationSettingsResponse:
    request.app.state.rate_limiter.check(
        f"admin:{principal.subject}", settings.admin_rate_limit_per_minute
    )
    subscription = await ensure_default_email_subscription(session, settings)
    before = {"target_email": subscription.destination_id, "enabled": subscription.active}
    if payload.target_email is not None:
        subscription.destination_id = normalize_email(payload.target_email)
    if payload.enabled is not None:
        subscription.active = payload.enabled
    await session.flush()
    after = {"target_email": subscription.destination_id, "enabled": subscription.active}
    add_audit_event(
        session,
        principal=principal,
        request_id=request.state.request_id,
        operation="notification.settings.update",
        object_type="subscription",
        object_id=subscription.id,
        application_version=settings.app_version,
        before=before,
        after=after,
    )
    response = await _notification_settings_response(session, settings)
    await session.commit()
    return response


@router.get("/admin/ingestion-runs", response_model=IngestionRunPage, tags=["Administration"])
async def list_ingestion_runs(
    cursor: str | None = Query(default=None, max_length=2_048),
    limit: int | None = Query(default=None, ge=1, le=100),
    page_size: int | None = Query(default=None, ge=1, le=100),
    status: str | None = Query(default=None, max_length=40),
    _principal: Principal = Depends(admin_auditor_principal),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> IngestionRunPage:
    try:
        offset = decode_cursor(cursor)
    except InvalidCursor as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    query = select(IngestionRun)
    if status:
        query = query.where(IngestionRun.status == status)
    rows = list(
        (
            await session.scalars(query.order_by(IngestionRun.created_at.desc(), IngestionRun.id))
        ).all()
    )
    requested = page_size if page_size is not None else limit
    page, next_cursor, has_more = page_window(
        [ingestion_run_response(item) for item in rows],
        offset=offset,
        limit=min(requested or settings.default_page_size, settings.max_page_size),
    )
    return IngestionRunPage(items=page, next_cursor=next_cursor, has_more=has_more)


@router.post(
    "/admin/ingestion-runs",
    response_model=IngestionRunResponse,
    status_code=202,
    tags=["Administration"],
)
async def create_ingestion_run(
    payload: StartIngestionRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
    principal: Principal = Depends(admin_principal),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> IngestionRunResponse:
    request.app.state.rate_limiter.check(
        f"admin:{principal.subject}", settings.admin_rate_limit_per_minute
    )
    request_fingerprint = _fingerprint(payload.model_dump(mode="json"))
    existing = await session.scalar(
        select(IngestionRun).where(IngestionRun.idempotency_key == idempotency_key)
    )
    if existing:
        prior_job = await session.scalar(
            select(ProcessingJob).where(ProcessingJob.ingestion_run_id == existing.id)
        )
        if (
            existing.run_type != payload.run_type
            or existing.source != payload.source
            or not prior_job
            or prior_job.payload.get("request_fingerprint") != request_fingerprint
        ):
            raise HTTPException(status_code=409, detail="Idempotency key payload conflict")
        return ingestion_run_response(existing)
    run = IngestionRun(
        run_type=payload.run_type,
        source=payload.source,
        status=RunStatus.PENDING.value,
        requested_by=principal.subject,
        idempotency_key=idempotency_key,
        parser_version=settings.parser_version,
        scope_rule_version=settings.drug_scope_rule_version,
        metrics={},
    )
    session.add(run)
    await session.flush()
    session.add(
        ProcessingJob(
            ingestion_run_id=run.id,
            job_type=payload.run_type,
            status=JobStatus.PENDING.value,
            idempotency_key=f"run:{run.id}:{payload.run_type}",
            payload={
                "source": payload.source,
                "reason": payload.reason,
                "change_ticket": payload.change_ticket,
                "options": payload.options,
                "request_fingerprint": request_fingerprint,
            },
        )
    )
    add_audit_event(
        session,
        principal=principal,
        request_id=request.state.request_id,
        operation="ingestion.queue",
        object_type="ingestion_run",
        object_id=run.id,
        application_version=settings.app_version,
        after={"run_type": run.run_type, "source": run.source},
    )
    await session.commit()
    return ingestion_run_response(run)


@router.post(
    "/admin/letters/{letter_id}/reprocess",
    response_model=JobAccepted,
    status_code=202,
    tags=["Administration"],
)
async def reprocess_letter(
    letter_id: str,
    payload: ReprocessRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
    principal: Principal = Depends(admin_principal),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> JobAccepted:
    request.app.state.rate_limiter.check(
        f"admin:{principal.subject}", settings.admin_rate_limit_per_minute
    )
    normalized_identifier = letter_id.strip()
    letter: WarningLetter | None = None
    try:
        letter = await session.get(WarningLetter, str(UUID(normalized_identifier)))
    except ValueError:
        letter = await session.scalar(
            select(WarningLetter).where(WarningLetter.marcs_cms_number == normalized_identifier)
        )
    if not letter:
        raise HTTPException(status_code=404, detail="Warning letter not found")
    version_id = letter.current_version_id
    if payload.source_version_id:
        target = await session.scalar(
            select(DocumentVersion)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(
                DocumentVersion.id == str(payload.source_version_id),
                Document.warning_letter_id == letter.id,
            )
        )
        if not target:
            raise HTTPException(status_code=404, detail="Source version not found for letter")
        version_id = target.id
    existing = await session.scalar(
        select(ProcessingJob).where(ProcessingJob.idempotency_key == idempotency_key)
    )
    expected = {
        "letter_id": letter.id,
        "stages": sorted(set(payload.stages)),
        "reason": payload.reason,
        "source_version_id": version_id,
        "change_ticket": payload.change_ticket,
    }
    if existing:
        if existing.payload.get("fingerprint") != _fingerprint(expected):
            raise HTTPException(status_code=409, detail="Idempotency key payload conflict")
        return JobAccepted(job_id=existing.id)
    job = ProcessingJob(
        warning_letter_id=letter.id,
        document_version_id=version_id,
        job_type="reprocess",
        status=JobStatus.PENDING.value,
        idempotency_key=idempotency_key,
        payload={**expected, "fingerprint": _fingerprint(expected)},
    )
    session.add(job)
    await session.flush()
    add_audit_event(
        session,
        principal=principal,
        request_id=request.state.request_id,
        operation="letter.reprocess.queue",
        object_type="processing_job",
        object_id=job.id,
        application_version=settings.app_version,
        reason=payload.reason,
        after=expected,
    )
    await session.commit()
    return JobAccepted(job_id=job.id)
