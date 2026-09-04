from __future__ import annotations

import hashlib
from datetime import date

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.enums import ChangeEventType
from app.models import ChangeEvent, Document, WarningLetter, utcnow


def years_before(reference_date: date, years: int) -> date:
    """Return a calendar-year cutoff, including a deterministic leap-day rule."""

    try:
        return reference_date.replace(year=reference_date.year - years)
    except ValueError:
        # February 29 becomes February 28 in a non-leap cutoff year.
        return reference_date.replace(year=reference_date.year - years, day=28)


def letter_effective_date(letter: WarningLetter) -> date | None:
    return letter.issue_date or letter.posted_date


def is_within_discovery_window(
    *, posted_date: date | None, issue_date: date | None, cutoff: date
) -> bool:
    effective_date = issue_date or posted_date
    # Unknown dates are fetched so the detail parser can establish the date;
    # the retention sweep still fails closed once a date is known.
    return effective_date is None or effective_date >= cutoff


async def retire_expired_letters(
    session: AsyncSession,
    settings: Settings,
    *,
    reference_date: date,
) -> int:
    """Soft-retire active letters at least N calendar years old.

    Raw objects, source versions, chunks, scope decisions, and events remain
    available for audit. The current-in-scope gates remove retired letters from
    every browsing and RAG query without destructive deletion.
    """

    cutoff = years_before(reference_date, settings.corpus_active_retention_years)
    candidates = list(
        (
            await session.scalars(
                select(WarningLetter).where(WarningLetter.current_in_scope.is_(True))
            )
        ).all()
    )
    retired = 0
    for letter in candidates:
        effective_date = letter_effective_date(letter)
        if effective_date is None or effective_date > cutoff:
            continue
        before = {
            "current_in_scope": letter.current_in_scope,
            "lifecycle_status": letter.lifecycle_status,
        }
        letter.current_in_scope = False
        letter.lifecycle_status = "retired_by_retention"
        await session.execute(
            update(Document)
            .where(Document.warning_letter_id == letter.id)
            .values(current_in_scope=False)
        )
        dedupe = hashlib.sha256(
            f"{letter.id}:{ChangeEventType.CORPUS_RETIRED.value}:{cutoff.isoformat()}".encode()
        ).hexdigest()
        existing = await session.scalar(
            select(ChangeEvent.id).where(ChangeEvent.deduplication_key == dedupe)
        )
        if not existing:
            session.add(
                ChangeEvent(
                    warning_letter_id=letter.id,
                    source_version_id=letter.current_version_id,
                    event_type=ChangeEventType.CORPUS_RETIRED.value,
                    before_state=before,
                    after_state={
                        "current_in_scope": False,
                        "lifecycle_status": "retired_by_retention",
                        "effective_date": effective_date.isoformat(),
                        "cutoff_date": cutoff.isoformat(),
                        "retention_years": settings.corpus_active_retention_years,
                    },
                    deduplication_key=dedupe,
                    detected_at=utcnow(),
                    published_at=utcnow(),
                    notification_state="suppressed",
                )
            )
        retired += 1
    await session.flush()
    return retired


async def retire_local_illustrative_letters(
    session: AsyncSession,
    settings: Settings,
) -> int:
    """Remove deterministic seed examples from the active corpus after live sync starts.

    The rows and every evidence artifact remain available for local audit. This
    guard is deliberately unavailable in staging/production, where fixture data
    must never be seeded in the first place.
    """

    if settings.app_env not in {"local", "development"}:
        return 0
    examples = list(
        (
            await session.scalars(
                select(WarningLetter).where(
                    WarningLetter.current_in_scope.is_(True),
                    WarningLetter.canonical_url.like(
                        "https://www.fda.gov/warning-letters/example-%"
                    ),
                )
            )
        ).all()
    )
    retired = 0
    for letter in examples:
        letter.current_in_scope = False
        letter.lifecycle_status = "retired_illustrative_fixture"
        await session.execute(
            update(Document)
            .where(Document.warning_letter_id == letter.id)
            .values(current_in_scope=False)
        )
        dedupe = hashlib.sha256(f"{letter.id}:illustrative-fixture-retired".encode()).hexdigest()
        existing = await session.scalar(
            select(ChangeEvent.id).where(ChangeEvent.deduplication_key == dedupe)
        )
        if not existing:
            session.add(
                ChangeEvent(
                    warning_letter_id=letter.id,
                    source_version_id=letter.current_version_id,
                    event_type=ChangeEventType.CORPUS_RETIRED.value,
                    before_state={"current_in_scope": True},
                    after_state={
                        "current_in_scope": False,
                        "lifecycle_status": "retired_illustrative_fixture",
                        "reason": "live_source_sync_started",
                    },
                    deduplication_key=dedupe,
                    detected_at=utcnow(),
                    published_at=utcnow(),
                    notification_state="suppressed",
                )
            )
        retired += 1
    await session.flush()
    return retired
