from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cases.hashing import canonical_sha256
from app.models import Case, CaseRun, IntegrationOutbox
from app.security.auth import Principal

PROHIBITED_DIRECTIVE = re.compile(
    r"\b(?:open|create|initiate)\s+(?:a\s+)?capa\b|"
    r"\bdeclare\w*\s+(?:the\s+)?(?:site\s+)?(?:noncompliant|compliant)\b|"
    r"\breject\s+(?:the\s+)?batch\b|"
    r"\brevise\s+(?:the\s+)?sop\s+immediately\b",
    re.IGNORECASE,
)


def validate_draft_content(title: str, body: str) -> None:
    if PROHIBITED_DIRECTIVE.search(f"{title}\n{body}"):
        raise HTTPException(
            status_code=422,
            detail="Draft contains a prohibited autonomous quality/compliance directive",
        )


async def create_draft(
    session: AsyncSession,
    *,
    case: Case,
    principal: Principal,
    channel: str,
    destination: str,
    title: str,
    body: str,
    run_id: str | None,
    idempotency_key: str,
) -> IntegrationOutbox:
    validate_draft_content(title, body)
    existing = await session.scalar(
        select(IntegrationOutbox).where(IntegrationOutbox.idempotency_key == idempotency_key)
    )
    content = {
        "title": title.strip(),
        "body": body.strip(),
        "decision_support_only": True,
        "manual_delivery_required": True,
    }
    digest = canonical_sha256(
        {"channel": channel, "destination": destination.strip(), "content": content}
    )
    if existing:
        if existing.content_sha256 != digest or existing.case_id != case.id:
            raise HTTPException(status_code=409, detail="Integration idempotency key conflict")
        return existing
    if run_id:
        run = await session.get(CaseRun, run_id)
        if run is None or run.case_id != case.id:
            raise HTTPException(status_code=409, detail="Draft run binding is unavailable")
    draft = IntegrationOutbox(
        case_id=case.id,
        run_id=run_id,
        channel=channel,
        action="CREATE_DRAFT",
        destination=destination.strip(),
        content=content,
        content_sha256=digest,
        status="DRAFT",
        external_delivery_allowed=False,
        requested_by=principal.subject,
        idempotency_key=idempotency_key,
    )
    session.add(draft)
    await session.flush()
    return draft


def draft_public_payload(draft: IntegrationOutbox) -> dict[str, Any]:
    return {
        "id": draft.id,
        "channel": draft.channel,
        "status": draft.status,
        "content_sha256": draft.content_sha256,
        "external_delivery_allowed": False,
    }
