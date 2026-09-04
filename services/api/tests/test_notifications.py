from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.config import Settings
from app.database import Database
from app.models import ChangeEvent, NotificationDelivery, Subscription, WarningLetter
from app.notifications import (
    dispatch_pending_notifications,
    ensure_default_email_subscription,
    queue_event_notifications,
)


@pytest.mark.asyncio
async def test_smtp_outbox_records_success_and_failure_without_real_network(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    smtp_settings = settings.model_copy(
        update={
            "smtp_enabled": True,
            "smtp_host": "smtp.example.test",
            "smtp_from_email": "fda-alerts@example.com",
        }
    )
    database = Database(settings.database_url)
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            await ensure_default_email_subscription(session, smtp_settings)
            letter = WarningLetter(
                canonical_url="https://www.fda.gov/warning-letters/email-outbox-test-1",
                company_name="Email Outbox Test Company",
                issue_date=date(2026, 8, 30),
                current_in_scope=True,
            )
            session.add(letter)
            await session.flush()
            event = ChangeEvent(
                warning_letter_id=letter.id,
                event_type="NEW",
                deduplication_key="email-outbox-event-new",
            )
            session.add(event)
            await session.flush()
            assert await queue_event_notifications(session, event=event, letter=letter) == 1
            await session.commit()

        messages = []

        def fake_send(_settings, message):
            messages.append(message)
            return "provider-message-1"

        monkeypatch.setattr("app.notifications._send_smtp", fake_send)
        async with database.session_factory() as session:
            metrics = await dispatch_pending_notifications(session, smtp_settings)
        assert metrics["notifications_sent"] == 1
        assert messages[0]["To"] == "grisellacrystabel@gmail.com"
        assert "FDA 경고장 업데이트" in str(messages[0]["Subject"])

        async with database.session_factory() as session:
            sent = await session.scalar(select(NotificationDelivery))
            sent_event = await session.get(ChangeEvent, sent.change_event_id if sent else "")
            assert sent is not None and sent.status == "sent"
            assert sent.provider_message_id == "provider-message-1"
            assert sent_event is not None and sent_event.notification_state == "sent"
            letter = await session.scalar(select(WarningLetter))
            assert letter is not None
            failed_event = ChangeEvent(
                warning_letter_id=letter.id,
                event_type="UPDATED",
                deduplication_key="email-outbox-event-updated",
            )
            session.add(failed_event)
            await session.flush()
            assert await queue_event_notifications(session, event=failed_event, letter=letter) == 1
            await session.commit()

        def fail_send(_settings, _message):
            raise TimeoutError("simulated provider timeout")

        monkeypatch.setattr("app.notifications._send_smtp", fail_send)
        async with database.session_factory() as session:
            metrics = await dispatch_pending_notifications(session, smtp_settings)
        assert metrics["notifications_failed"] == 1
        async with database.session_factory() as session:
            failed = await session.scalar(
                select(NotificationDelivery).where(NotificationDelivery.status == "failed")
            )
            failed_state = await session.get(ChangeEvent, failed.change_event_id if failed else "")
            assert failed is not None and failed.error_code == "TimeoutError"
            assert failed_state is not None and failed_state.notification_state == "failed"
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_immediate_saved_view_queues_only_matching_owner_alerts(settings: Settings) -> None:
    database = Database(settings.database_url)
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            await ensure_default_email_subscription(session, settings)
            session.add_all(
                [
                    Subscription(
                        owner_id="matching.user",
                        name="Matching country watch",
                        criteria={"country": "South Korea"},
                        frequency="immediate",
                        channel="email",
                        destination_id="matching@example.com",
                        active=True,
                    ),
                    Subscription(
                        owner_id="nonmatching.user",
                        name="Different country watch",
                        criteria={"country": "Canada"},
                        frequency="immediate",
                        channel="email",
                        destination_id="nonmatching@example.com",
                        active=True,
                    ),
                    Subscription(
                        owner_id="digest.user",
                        name="Persisted daily watch",
                        criteria={"country": "South Korea"},
                        frequency="daily",
                        channel="email",
                        destination_id="digest@example.com",
                        active=True,
                    ),
                ]
            )
            letter = WarningLetter(
                canonical_url="https://www.fda.gov/warning-letters/saved-view-alert-test",
                company_name="Matching Saved View Company",
                country="South Korea",
                posted_date=date(2026, 8, 31),
                current_in_scope=True,
            )
            session.add(letter)
            await session.flush()
            event = ChangeEvent(
                warning_letter_id=letter.id,
                event_type="NEW",
                deduplication_key="saved-view-alert-event",
            )
            session.add(event)
            await session.flush()

            # The system-wide update email and one matching immediate owner view are queued.
            # The non-match and unsupported daily digest are deliberately not represented as active.
            assert await queue_event_notifications(session, event=event, letter=letter) == 2
            await session.commit()

        async with database.session_factory() as session:
            destinations = set(
                (
                    await session.scalars(
                        select(NotificationDelivery.destination_identifier)
                    )
                ).all()
            )
        assert destinations == {"grisellacrystabel@gmail.com", "matching@example.com"}
    finally:
        await database.dispose()
