from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEvent
from app.security.auth import Principal


def value_hash(value: object | None) -> str | None:
    if value is None:
        return None
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(payload).hexdigest()


def add_audit_event(
    session: AsyncSession,
    *,
    principal: Principal,
    request_id: str,
    operation: str,
    object_type: str,
    object_id: str | None,
    application_version: str,
    result: str = "success",
    reason: str | None = None,
    before: object | None = None,
    after: object | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditEvent(
            actor_type=principal.actor_type,
            actor_id=principal.subject,
            request_id=request_id,
            operation=operation,
            object_type=object_type,
            object_id=object_id,
            before_hash=value_hash(before),
            after_hash=value_hash(after),
            result=result,
            reason=reason,
            application_version=application_version,
            context=context or {},
        )
    )
