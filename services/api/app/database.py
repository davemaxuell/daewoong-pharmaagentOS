from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import MetaData, event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool, StaticPool

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def normalize_async_database_url(url: str) -> str:
    """Accept managed-Postgres URLs while keeping SQLAlchemy on the asyncpg driver."""
    if url.startswith("postgres://"):
        url = f"postgresql+asyncpg://{url.removeprefix('postgres://')}"
    elif url.startswith("postgresql://"):
        url = f"postgresql+asyncpg://{url.removeprefix('postgresql://')}"

    parsed = make_url(url)
    sslmode = parsed.query.get("sslmode")
    if parsed.drivername == "postgresql+asyncpg" and (sslmode or "supa" in parsed.query):
        # Managed providers commonly emit libpq-style `sslmode=require`.
        # asyncpg receives URL query parameters as connect() keyword arguments
        # and names the equivalent option `ssl`. Vercel's Supabase integration
        # also appends `supa`, which is provider metadata rather than a driver
        # option and must not reach asyncpg.connect().
        removed = [name for name in ("sslmode", "supa") if name in parsed.query]
        parsed = parsed.difference_update_query(removed)
        if sslmode:
            parsed = parsed.update_query_dict({"ssl": sslmode})
        return parsed.render_as_string(hide_password=False)
    return url


def async_engine_options(url: str) -> dict[str, object]:
    """Return safe SQLAlchemy options for the configured database endpoint.

    Supabase's transaction pooler uses port 6543. It owns connection reuse and
    does not support prepared statements, so serverless callers must not layer a
    process-local pool or asyncpg statement caches on top of it.
    """
    options: dict[str, object] = {"pool_pre_ping": True}
    parsed = make_url(url)
    if parsed.drivername.startswith("sqlite") and parsed.database == ":memory:":
        options["poolclass"] = StaticPool
    elif parsed.drivername == "postgresql+asyncpg" and parsed.port == 6543:
        options["poolclass"] = NullPool
        options["connect_args"] = {
            "prepared_statement_cache_size": 0,
            "statement_cache_size": 0,
        }
    return options


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """Make local SQLite enforce the same declared relationships as PostgreSQL."""

    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


class Database:
    def __init__(self, url: str) -> None:
        url = normalize_async_database_url(url)
        self.engine: AsyncEngine = create_async_engine(url, **async_engine_options(url))
        if make_url(url).get_backend_name() == "sqlite":
            event.listen(self.engine.sync_engine, "connect", _enable_sqlite_foreign_keys)
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    async def create_schema(self) -> None:
        # Importing models registers every table on Base.metadata.
        from app import models  # noqa: F401

        async with self.engine.begin() as connection:
            if connection.dialect.name == "postgresql":
                # This path is for the explicit one-off bootstrap/init command. Production
                # application instances keep AUTO_CREATE_SCHEMA=false after migrations.
                await connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
            await connection.run_sync(Base.metadata.create_all)
            # create_all intentionally does not mutate existing tables. Keep the
            # zero-dependency local SQLite profile forward-compatible for this
            # prototype; deployed PostgreSQL uses the controlled schema migration.
            if connection.dialect.name == "sqlite":
                snapshot_columns = {
                    row[1]
                    for row in (
                        await connection.exec_driver_sql("PRAGMA table_info(discovery_snapshots)")
                    ).all()
                }
                if "raw_object_key" not in snapshot_columns:
                    await connection.exec_driver_sql(
                        "ALTER TABLE discovery_snapshots "
                        "ADD COLUMN raw_object_key VARCHAR(1024) NOT NULL DEFAULT ''"
                    )
                letter_columns = {
                    row[1]
                    for row in (
                        await connection.exec_driver_sql("PRAGMA table_info(warning_letters)")
                    ).all()
                }
                if "country" not in letter_columns:
                    await connection.exec_driver_sql(
                        "ALTER TABLE warning_letters ADD COLUMN country VARCHAR(120)"
                    )
                subscription_columns = {
                    row[1]
                    for row in (
                        await connection.exec_driver_sql("PRAGMA table_info(subscriptions)")
                    ).all()
                }
                if subscription_columns and "description" not in subscription_columns:
                    await connection.exec_driver_sql(
                        "ALTER TABLE subscriptions ADD COLUMN description "
                        "VARCHAR(1000) NOT NULL DEFAULT ''"
                    )
                if subscription_columns:
                    await connection.exec_driver_sql(
                        "CREATE UNIQUE INDEX IF NOT EXISTS uq_subscriptions_owner_name "
                        "ON subscriptions (owner_id, name)"
                    )
                plan_columns = {
                    row[1]
                    for row in (
                        await connection.exec_driver_sql("PRAGMA table_info(case_plans)")
                    ).all()
                }
                if plan_columns and "workflow_template_version_id" not in plan_columns:
                    await connection.exec_driver_sql(
                        "ALTER TABLE case_plans ADD COLUMN "
                        "workflow_template_version_id VARCHAR(36)"
                    )
                    await connection.exec_driver_sql(
                        "CREATE INDEX IF NOT EXISTS "
                        "ix_case_plans_workflow_template_version_id "
                        "ON case_plans (workflow_template_version_id)"
                    )
                approval_columns = {
                    row[1]
                    for row in (
                        await connection.exec_driver_sql("PRAGMA table_info(approval_requests)")
                    ).all()
                }
                for column_name, column_type in (
                    ("run_id", "VARCHAR(36)"),
                    ("plan_step_id", "VARCHAR(36)"),
                    ("step_key", "VARCHAR(160)"),
                ):
                    if approval_columns and column_name not in approval_columns:
                        await connection.exec_driver_sql(
                            f"ALTER TABLE approval_requests ADD COLUMN "
                            f"{column_name} {column_type}"
                        )
                embedding_columns = {
                    row[1]
                    for row in (
                        await connection.exec_driver_sql("PRAGMA table_info(chunk_embeddings)")
                    ).all()
                }
                if embedding_columns and "input_schema_version" not in embedding_columns:
                    # SQLite cannot drop the legacy three-column UNIQUE constraint in place.
                    # Rebuild this leaf table transactionally, retaining old vectors under a
                    # non-active provenance marker so the current space is safely backfilled.
                    await connection.exec_driver_sql(
                        "CREATE TABLE chunk_embeddings_provenance_migration ("
                        "id VARCHAR(36) NOT NULL PRIMARY KEY, "
                        "document_chunk_id VARCHAR(36) NOT NULL REFERENCES "
                        "document_chunks(id) ON DELETE CASCADE, "
                        "provider VARCHAR(40) NOT NULL, "
                        "model_id VARCHAR(120) NOT NULL, "
                        "dimensions INTEGER NOT NULL, "
                        "input_schema_version VARCHAR(80) NOT NULL, "
                        "content_sha256 VARCHAR(64) NOT NULL, "
                        "provider_input_sha256 VARCHAR(64) NOT NULL, "
                        "embedding JSON NOT NULL, "
                        "created_at DATETIME NOT NULL, "
                        "CONSTRAINT uq_chunk_embedding_space_input UNIQUE ("
                        "document_chunk_id, provider, model_id, dimensions, "
                        "input_schema_version, content_sha256, provider_input_sha256))"
                    )
                    await connection.exec_driver_sql(
                        "INSERT INTO chunk_embeddings_provenance_migration ("
                        "id, document_chunk_id, provider, model_id, dimensions, "
                        "input_schema_version, content_sha256, provider_input_sha256, "
                        "embedding, created_at) "
                        "SELECT id, document_chunk_id, provider, model_id, dimensions, "
                        "'legacy-unknown-v0', content_sha256, provider_input_sha256, "
                        "embedding, created_at FROM chunk_embeddings"
                    )
                    await connection.exec_driver_sql("DROP TABLE chunk_embeddings")
                    await connection.exec_driver_sql(
                        "ALTER TABLE chunk_embeddings_provenance_migration "
                        "RENAME TO chunk_embeddings"
                    )
                    await connection.exec_driver_sql(
                        "CREATE INDEX ix_chunk_embeddings_document_chunk_id "
                        "ON chunk_embeddings (document_chunk_id)"
                    )
                    await connection.exec_driver_sql(
                        "CREATE INDEX ix_chunk_embeddings_space ON chunk_embeddings "
                        "(provider, model_id, dimensions, input_schema_version)"
                    )

    async def drop_schema(self) -> None:
        from app import models  # noqa: F401

        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)

    async def dispose(self) -> None:
        await self.engine.dispose()

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            yield session
