from __future__ import annotations

import asyncio
import hashlib
import re
import smtplib
from datetime import date
from email.message import EmailMessage
from email.utils import formataddr

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.enums import ChangeEventType
from app.models import (
    AiSummary,
    ChangeEvent,
    Document,
    Finding,
    NotificationDelivery,
    Subscription,
    WarningLetter,
    utcnow,
)

SYSTEM_SUBSCRIPTION_OWNER = "system"
SYSTEM_SUBSCRIPTION_NAME = "FDA warning letter update email"
NOTIFIABLE_EVENTS = {ChangeEventType.NEW.value, ChangeEventType.UPDATED.value}
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(value: str) -> str:
    value = value.strip()
    if len(value) > 320 or not EMAIL_PATTERN.fullmatch(value):
        raise ValueError("A valid email address is required")
    local_part, domain = value.rsplit("@", 1)
    return f"{local_part}@{domain.casefold()}"


async def ensure_default_email_subscription(
    session: AsyncSession, settings: Settings
) -> Subscription:
    subscription = await session.scalar(
        select(Subscription).where(
            Subscription.owner_id == SYSTEM_SUBSCRIPTION_OWNER,
            Subscription.name == SYSTEM_SUBSCRIPTION_NAME,
        )
    )
    if subscription:
        return subscription
    subscription = Subscription(
        owner_id=SYSTEM_SUBSCRIPTION_OWNER,
        name=SYSTEM_SUBSCRIPTION_NAME,
        criteria={
            "scope": "FDA Product: Drugs",
            "event_types": sorted(NOTIFIABLE_EVENTS),
        },
        frequency="immediate",
        channel="email",
        destination_id=normalize_email(settings.notification_default_recipient),
        active=True,
    )
    session.add(subscription)
    await session.flush()
    return subscription


def _date_value(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _subscription_matches(
    subscription: Subscription,
    event: ChangeEvent,
    letter: WarningLetter,
    *,
    categories: set[str],
    regulations: set[str],
    review_state: str | None,
    document_types: set[str],
) -> bool:
    if not subscription.active or subscription.channel != "email":
        return False
    if subscription.frequency != "immediate" or event.event_type not in NOTIFIABLE_EVENTS:
        return False
    criteria = subscription.criteria or {}
    configured = criteria.get("event_types", criteria.get("event_type"))
    if isinstance(configured, str):
        event_types = {configured}
    elif isinstance(configured, list):
        event_types = {str(item) for item in configured}
    else:
        event_types = NOTIFIABLE_EVENTS
    if event.event_type not in event_types:
        return False

    query = str(criteria.get("query") or "").strip().casefold()
    if query:
        haystack = " ".join(
            [
                letter.company_name,
                letter.marcs_cms_number or "",
                letter.subject or "",
                letter.country or "",
                *(letter.issuing_offices or []),
                *categories,
                *regulations,
            ]
        ).casefold()
        if query not in haystack:
            return False
    subtype = criteria.get("drug_subtype")
    if subtype and str(subtype) not in (letter.drug_subtypes or []):
        return False
    category = criteria.get("category")
    if category and str(category) not in categories:
        return False
    country = str(criteria.get("country") or "").strip()
    if country and (letter.country or "").casefold() != country.casefold():
        return False
    lifecycle_state = str(criteria.get("lifecycle_state") or "").strip()
    if lifecycle_state and letter.lifecycle_status.casefold() != lifecycle_state.casefold():
        return False
    requested_review = str(criteria.get("review_state") or "").strip()
    if requested_review and review_state != requested_review:
        return False
    linked_document = str(criteria.get("linked_document") or "").strip()
    if linked_document == "response" and "response" not in document_types:
        return False
    if linked_document == "closeout" and "closeout" not in document_types:
        return False
    if linked_document == "open" and "closeout" in document_types:
        return False
    posted_from = _date_value(criteria.get("posted_from"))
    if posted_from and (letter.posted_date is None or letter.posted_date < posted_from):
        return False
    posted_to = _date_value(criteria.get("posted_to"))
    if posted_to and (letter.posted_date is None or letter.posted_date > posted_to):
        return False
    return True


async def queue_event_notifications(
    session: AsyncSession,
    *,
    event: ChangeEvent,
    letter: WarningLetter,
) -> int:
    """Create idempotent delivery rows in the ingestion transaction."""

    if event.event_type not in NOTIFIABLE_EVENTS or not letter.current_in_scope:
        event.notification_state = "suppressed"
        return 0
    subscriptions = list(
        (
            await session.scalars(
                select(Subscription).where(
                    Subscription.active.is_(True),
                    Subscription.channel == "email",
                    Subscription.frequency == "immediate",
                )
            )
        ).all()
    )
    documents = list(
        (
            await session.scalars(
                select(Document).where(Document.warning_letter_id == letter.id)
            )
        ).all()
    )
    document_types = {document.document_type for document in documents}
    summary = None
    findings: list[Finding] = []
    if letter.current_version_id:
        summary = await session.scalar(
            select(AiSummary)
            .where(AiSummary.document_version_id == letter.current_version_id)
            .order_by(AiSummary.created_at.desc(), AiSummary.revision.desc())
        )
        if summary:
            findings = list(
                (
                    await session.scalars(
                        select(Finding).where(Finding.summary_id == summary.id)
                    )
                ).all()
            )
    categories = {
        category for finding in findings for category in (finding.categories or [])
    }
    regulations = {
        reference
        for finding in findings
        for reference in (finding.regulatory_references or [])
    }
    queued = 0
    for subscription in subscriptions:
        if not _subscription_matches(
            subscription,
            event,
            letter,
            categories=categories,
            regulations=regulations,
            review_state=summary.review_state if summary else None,
            document_types=document_types,
        ):
            continue
        idempotency_key = hashlib.sha256(f"email:{event.id}:{subscription.id}".encode()).hexdigest()
        existing = await session.scalar(
            select(NotificationDelivery.id).where(
                NotificationDelivery.idempotency_key == idempotency_key
            )
        )
        if existing:
            continue
        session.add(
            NotificationDelivery(
                change_event_id=event.id,
                subscription_id=subscription.id,
                status="queued",
                destination_identifier=normalize_email(subscription.destination_id),
                idempotency_key=idempotency_key,
            )
        )
        queued += 1
    event.notification_state = "pending" if queued else "suppressed"
    await session.flush()
    return queued


def _message_for(
    settings: Settings,
    delivery: NotificationDelivery,
    event: ChangeEvent,
    letter: WarningLetter,
) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = f"[FDA 경고장 업데이트] {event.event_type} · {letter.company_name}"
    message["From"] = formataddr((settings.smtp_from_name, settings.smtp_from_email or ""))
    message["To"] = delivery.destination_identifier
    message["Message-ID"] = f"<{delivery.id}@daewoong-fda-warning-letter-update>"
    effective_date = letter.issue_date or letter.posted_date
    effective_date_label = effective_date.isoformat() if effective_date else "Unknown"
    message.set_content(
        "\n".join(
            [
                "FDA 경고장 업데이트가 감지되었습니다.",
                "An FDA warning-letter update was detected.",
                "",
                f"변경 유형 / Event: {event.event_type}",
                f"회사 / Company: {letter.company_name}",
                f"발행일 / Issue date: {effective_date_label}",
                f"FDA 원문 / Official source: {letter.canonical_url}",
                "",
                "본 알림은 변경 감지용입니다. 규제 판단에는 FDA 원문을 확인하세요.",
                "This alert is for change detection; use the official FDA source as authoritative.",
            ]
        )
    )
    return message


def _send_smtp(settings: Settings, message: EmailMessage) -> str:
    if not settings.smtp_host or not settings.smtp_from_email:
        raise RuntimeError("SMTP is enabled but not fully configured")
    smtp_class = smtplib.SMTP_SSL if settings.smtp_use_ssl else smtplib.SMTP
    with smtp_class(
        settings.smtp_host,
        settings.smtp_port,
        timeout=settings.smtp_timeout_seconds,
    ) as client:
        client.ehlo()
        if settings.smtp_starttls:
            client.starttls()
            client.ehlo()
        if settings.smtp_username:
            password = settings.smtp_password.get_secret_value() if settings.smtp_password else ""
            client.login(settings.smtp_username, password)
        refused = client.send_message(message)
        if refused:
            raise RuntimeError("SMTP server refused one or more recipients")
    return str(message["Message-ID"])


async def _refresh_event_state(session: AsyncSession, event: ChangeEvent) -> None:
    await session.flush()
    statuses = list(
        (
            await session.scalars(
                select(NotificationDelivery.status).where(
                    NotificationDelivery.change_event_id == event.id
                )
            )
        ).all()
    )
    if not statuses:
        event.notification_state = "suppressed"
    elif "queued" in statuses:
        event.notification_state = "pending"
    elif "failed" in statuses:
        event.notification_state = "failed"
    elif "sent" in statuses:
        event.notification_state = "sent"
    else:
        event.notification_state = "suppressed"


async def dispatch_pending_notifications(
    session: AsyncSession,
    settings: Settings,
    *,
    limit: int = 100,
) -> dict[str, int]:
    """Deliver queued messages and persist every suppressed/failure outcome."""

    deliveries = list(
        (
            await session.scalars(
                select(NotificationDelivery)
                .where(NotificationDelivery.status == "queued")
                .order_by(NotificationDelivery.created_at, NotificationDelivery.id)
                .limit(max(1, min(limit, 1_000)))
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    metrics = {
        "notifications_queued": len(deliveries),
        "notifications_sent": 0,
        "notifications_failed": 0,
        "notifications_suppressed": 0,
    }
    for delivery in deliveries:
        event = await session.get(ChangeEvent, delivery.change_event_id)
        letter = await session.get(WarningLetter, event.warning_letter_id) if event else None
        delivery.attempt += 1
        if not event or not letter:
            delivery.status = "failed"
            delivery.error_code = "source_event_missing"
            metrics["notifications_failed"] += 1
            continue
        if not settings.smtp_enabled:
            delivery.status = "suppressed"
            delivery.error_code = "smtp_disabled"
            metrics["notifications_suppressed"] += 1
            await _refresh_event_state(session, event)
            continue
        try:
            provider_id = await asyncio.to_thread(
                _send_smtp, settings, _message_for(settings, delivery, event, letter)
            )
        except Exception as exc:
            delivery.status = "failed"
            delivery.error_code = type(exc).__name__[:120]
            metrics["notifications_failed"] += 1
        else:
            delivery.status = "sent"
            delivery.provider_message_id = provider_id[:500]
            delivery.delivered_at = utcnow()
            delivery.error_code = None
            metrics["notifications_sent"] += 1
        await _refresh_event_state(session, event)
    await session.commit()
    return metrics
