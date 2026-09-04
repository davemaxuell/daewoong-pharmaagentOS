from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PlatformControl


@dataclass(frozen=True)
class Suspension:
    control_key: str
    reason: str


async def active_suspension(
    session: AsyncSession,
    agent_version_ids: Iterable[str] = (),
) -> Suspension | None:
    """Resolve the strongest active runtime control without trusting cached registry state."""

    global_control = await session.scalar(
        select(PlatformControl).where(
            PlatformControl.control_key == "global",
            PlatformControl.suspended.is_(True),
        )
    )
    if global_control:
        return Suspension(global_control.control_key, global_control.reason)
    identifiers = sorted(set(agent_version_ids))
    if not identifiers:
        return None
    agent_control = await session.scalar(
        select(PlatformControl)
        .where(
            PlatformControl.agent_version_id.in_(identifiers),
            PlatformControl.suspended.is_(True),
        )
        .order_by(PlatformControl.control_key)
        .limit(1)
    )
    if agent_control:
        return Suspension(agent_control.control_key, agent_control.reason)
    return None
