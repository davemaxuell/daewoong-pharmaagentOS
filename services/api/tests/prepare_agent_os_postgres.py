"""Create only the legacy tables required by the Agent OS forward migration.

This helper is intentionally narrower than ``fda-intel init-db``.  The CI job
must leave every Agent OS table absent so the forward migration exercises its
own ``CREATE TABLE`` and foreign-key definitions.
"""

from __future__ import annotations

import asyncio
import os

from sqlalchemy import inspect
from sqlalchemy.engine import Connection

from app.database import Base, Database
from app.models import Document, DocumentVersion, WarningLetter

PREREQUISITE_TABLES = (
    WarningLetter.__table__,
    Document.__table__,
    DocumentVersion.__table__,
)

AGENT_OS_TABLE_NAMES = frozenset(
    {
        "agent_cases",
        "agent_versions",
        "approval_requests",
        "artifact_evidence",
        "artifact_versions",
        "artifacts",
        "case_events",
        "case_plan_steps",
        "case_plans",
        "case_runs",
        "case_sources",
        "policy_decisions",
        "skill_versions",
        "tool_invocations",
        "tool_versions",
    }
)


def _public_table_names(connection: Connection) -> set[str]:
    return set(inspect(connection).get_table_names(schema="public"))


async def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")

    database = Database(database_url)
    try:
        async with database.engine.begin() as connection:
            if connection.dialect.name != "postgresql":
                raise RuntimeError("Migration prerequisite setup requires PostgreSQL")

            before = await connection.run_sync(_public_table_names)
            preexisting_agent_tables = before & AGENT_OS_TABLE_NAMES
            if preexisting_agent_tables:
                names = ", ".join(sorted(preexisting_agent_tables))
                raise RuntimeError(f"Agent OS tables must be absent before migration: {names}")

            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection,
                    tables=list(PREREQUISITE_TABLES),
                    checkfirst=True,
                )
            )

            after = await connection.run_sync(_public_table_names)
            missing = {table.name for table in PREREQUISITE_TABLES} - after
            if missing:
                names = ", ".join(sorted(missing))
                raise RuntimeError(f"Failed to create migration prerequisites: {names}")

            accidentally_created = after & AGENT_OS_TABLE_NAMES
            if accidentally_created:
                names = ", ".join(sorted(accidentally_created))
                raise RuntimeError(f"Prerequisite setup created Agent OS tables: {names}")
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
