from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.database import Database
from app.models import PlatformControl


@pytest.mark.asyncio
async def test_local_backup_restores_control_plane_schema_and_canary(tmp_path: Path) -> None:
    source_path = tmp_path / "source.db"
    restored_path = tmp_path / "restored.db"
    database = Database(f"sqlite+aiosqlite:///{source_path.as_posix()}")
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            session.add(
                PlatformControl(
                    control_key="global",
                    scope="GLOBAL",
                    suspended=False,
                    reason="Automated restore integrity canary",
                    revision=1,
                    updated_by="backup-test",
                )
            )
            await session.commit()
    finally:
        await database.dispose()

    with sqlite3.connect(source_path) as source, sqlite3.connect(restored_path) as target:
        source.backup(target)

    with sqlite3.connect(restored_path) as restored:
        tables = {
            row[0]
            for row in restored.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        canary = restored.execute(
            "SELECT scope, suspended, reason, revision FROM platform_controls "
            "WHERE control_key = 'global'"
        ).fetchone()

    assert {
        "agent_cases",
        "case_runs",
        "approval_requests",
        "artifact_versions",
        "durable_activities",
        "integration_outbox",
        "a2a_exchanges",
    } <= tables
    assert canary == ("GLOBAL", 0, "Automated restore integrity canary", 1)
