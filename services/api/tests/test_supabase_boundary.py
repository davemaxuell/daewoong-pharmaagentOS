import os
import re
from pathlib import Path

import asyncpg
import pytest

from app import models  # noqa: F401
from app.database import Base

ROOT = Path(__file__).resolve().parents[3]
BOUNDARY = (ROOT / "infra/deployment/vercel/supabase-data-api-boundary.sql").read_text()


def test_data_api_boundary_covers_every_application_table():
    declaration = BOUNDARY.split("app_tables text[] := ARRAY[", 1)[1].split("]", 1)[0]
    assert set(re.findall(r"'([a-z0-9_]+)'", declaration)) == set(Base.metadata.tables)


@pytest.mark.skipif(
    os.getenv("AGENT_OS_SUPABASE_TEST") != "1",
    reason="requires isolated migrated PostgreSQL and explicit Supabase boundary opt-in",
)
@pytest.mark.asyncio
async def test_boundary_denies_browser_roles_preserves_runtime_and_unrelated_tables():
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://", 1)
    connection = await asyncpg.connect(url)
    transaction = connection.transaction()
    await transaction.start()
    try:
        # All DDL, including synthetic Supabase roles, is rolled back after this test.
        for role in ("anon", "authenticated"):
            if not await connection.fetchval("SELECT 1 FROM pg_roles WHERE rolname=$1", role):
                await connection.execute(f"CREATE ROLE {role} NOLOGIN")
        await connection.execute("CREATE TABLE public.pharma_boundary_unrelated (id integer)")
        await connection.execute("GRANT SELECT ON public.pharma_boundary_unrelated TO anon")
        script = BOUNDARY.replace("BEGIN;", "", 1).rsplit("COMMIT;", 1)[0]
        await connection.execute(script)
        assert await connection.fetchval(
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' AND c.relkind='r' AND c.relrowsecurity"
        ) == len(Base.metadata.tables)
        for role in ("anon", "authenticated"):
            assert not await connection.fetchval(
                "SELECT has_table_privilege($1, 'public.agent_cases', 'SELECT')", role
            )
            await connection.execute(f"SET LOCAL ROLE {role}")
            try:
                with pytest.raises(asyncpg.InsufficientPrivilegeError):
                    async with connection.transaction():
                        await connection.fetch("SELECT * FROM public.agent_cases")
            finally:
                await connection.execute("RESET ROLE")
        assert await connection.fetchval(
            "SELECT has_table_privilege('anon', 'public.pharma_boundary_unrelated', 'SELECT')"
        )
        expected = await connection.fetchval("SELECT count(*) FROM public.warning_letters")
        assert expected > 0, "Use a seeded isolated database to verify RLS visibility"
        for role in ("fda_api_runtime", "fda_worker_runtime"):
            await connection.execute(f"SET LOCAL ROLE {role}")
            assert (
                await connection.fetchval("SELECT count(*) FROM public.warning_letters") == expected
            )
            assert not await connection.fetchval(
                "SELECT has_table_privilege(current_user, 'public.document_versions', 'DELETE')"
            )
            await connection.execute("RESET ROLE")
    finally:
        await transaction.rollback()
        await connection.close()
