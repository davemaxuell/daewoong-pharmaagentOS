import pytest
from sqlalchemy.pool import NullPool, StaticPool

from app.config import Settings
from app.database import Database, async_engine_options, normalize_async_database_url


def test_managed_postgres_urls_use_the_asyncpg_driver() -> None:
    assert normalize_async_database_url("postgres://user:secret@db/name") == (
        "postgresql+asyncpg://user:secret@db/name"
    )
    assert normalize_async_database_url("postgresql://user:secret@db/name") == (
        "postgresql+asyncpg://user:secret@db/name"
    )
    assert normalize_async_database_url("postgresql+asyncpg://user:secret@db/name") == (
        "postgresql+asyncpg://user:secret@db/name"
    )


def test_managed_postgres_sslmode_is_translated_for_asyncpg() -> None:
    normalized = normalize_async_database_url(
        "postgres://user:p%40ss@db.example:6543/postgres?sslmode=require&supa=base-pooler"
    )

    assert normalized == (
        "postgresql+asyncpg://user:p%40ss@db.example:6543/postgres?ssl=require"
    )


def test_supabase_transaction_pooler_disables_local_and_statement_pools() -> None:
    options = async_engine_options(
        "postgresql+asyncpg://postgres.project:secret@aws-0-region.pooler.supabase.com:6543/postgres"
    )

    assert options["poolclass"] is NullPool
    assert options["connect_args"] == {
        "prepared_statement_cache_size": 0,
        "statement_cache_size": 0,
    }


def test_non_transaction_endpoints_keep_application_pooling() -> None:
    options = async_engine_options(
        "postgresql+asyncpg://postgres.project:secret@aws-0-region.pooler.supabase.com:5432/postgres"
    )

    assert "poolclass" not in options
    assert "connect_args" not in options


def test_sqlite_memory_database_keeps_one_static_connection() -> None:
    assert async_engine_options("sqlite+aiosqlite:///:memory:")["poolclass"] is StaticPool


@pytest.mark.asyncio
async def test_sqlite_connections_enforce_declared_foreign_keys() -> None:
    database = Database("sqlite+aiosqlite:///:memory:")
    try:
        async with database.engine.connect() as connection:
            enabled = await connection.exec_driver_sql("PRAGMA foreign_keys")
            assert enabled.scalar_one() == 1
    finally:
        await database.dispose()


def test_vercel_supabase_postgres_url_is_accepted(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv(
        "POSTGRES_URL",
        "postgres://postgres.project:secret@aws-0-region.pooler.supabase.com:6543/postgres",
    )

    settings = Settings(_env_file=None)

    assert settings.database_url.endswith("pooler.supabase.com:6543/postgres")
