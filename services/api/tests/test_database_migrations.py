from __future__ import annotations

import pytest

from app.database import Database
from app.models import Document, DocumentChunk, DocumentVersion, WarningLetter


@pytest.mark.asyncio
async def test_create_schema_adds_country_to_legacy_sqlite_database(tmp_path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'legacy.db'}")
    try:
        await database.create_schema()
        async with database.engine.begin() as connection:
            await connection.exec_driver_sql("ALTER TABLE warning_letters DROP COLUMN country")
            before = {
                row[1]
                for row in (
                    await connection.exec_driver_sql("PRAGMA table_info(warning_letters)")
                ).all()
            }
        assert "country" not in before

        await database.create_schema()

        async with database.engine.begin() as connection:
            after = {
                row[1]
                for row in (
                    await connection.exec_driver_sql("PRAGMA table_info(warning_letters)")
                ).all()
            }
        assert "country" in after
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_create_schema_adds_saved_view_description_to_legacy_sqlite_database(
    tmp_path,
) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'legacy-saved-views.db'}")
    try:
        await database.create_schema()
        async with database.engine.begin() as connection:
            await connection.exec_driver_sql("ALTER TABLE subscriptions DROP COLUMN description")
        await database.create_schema()
        async with database.engine.begin() as connection:
            columns = {
                row[1]
                for row in (
                    await connection.exec_driver_sql("PRAGMA table_info(subscriptions)")
                ).all()
            }
            indexes = {
                row[1]
                for row in (
                    await connection.exec_driver_sql("PRAGMA index_list(subscriptions)")
                ).all()
            }
        assert "description" in columns
        assert "uq_subscriptions_owner_name" in indexes
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_create_schema_migrates_legacy_embedding_provenance_table(tmp_path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'legacy-embeddings.db'}")
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            letter = WarningLetter(
                canonical_url="https://www.fda.gov/legacy-embedding-parent",
                company_name="Synthetic Legacy Fixture",
            )
            document = Document(
                warning_letter=letter,
                canonical_url=letter.canonical_url,
            )
            version = DocumentVersion(
                document=document,
                version_number=1,
                raw_sha256="1" * 64,
                canonical_hash="2" * 64,
                parser_version="legacy-test-parser-v1",
                scope_status="IN_SCOPE_DRUGS",
            )
            session.add_all([letter, document, version])
            await session.flush()
            session.add(
                DocumentChunk(
                    id="chunk-1",
                    document_version_id=version.id,
                    warning_letter_id=letter.id,
                    ordinal=0,
                    section_path=["legacy"],
                    source_anchor="legacy",
                    content="Synthetic legacy embedding source text.",
                    token_estimate=6,
                    chunker_version="legacy-test-chunker-v1",
                )
            )
            await session.commit()
        async with database.engine.begin() as connection:
            await connection.exec_driver_sql("DROP TABLE chunk_embeddings")
            await connection.exec_driver_sql(
                "CREATE TABLE chunk_embeddings ("
                "id VARCHAR(36) NOT NULL PRIMARY KEY, "
                "document_chunk_id VARCHAR(36) NOT NULL, "
                "provider VARCHAR(40) NOT NULL, "
                "model_id VARCHAR(120) NOT NULL, "
                "dimensions INTEGER NOT NULL, "
                "content_sha256 VARCHAR(64) NOT NULL, "
                "provider_input_sha256 VARCHAR(64) NOT NULL, "
                "embedding JSON NOT NULL, "
                "created_at DATETIME NOT NULL, "
                "UNIQUE (document_chunk_id, model_id, content_sha256))"
            )
            await connection.exec_driver_sql(
                "INSERT INTO chunk_embeddings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "embedding-legacy",
                    "chunk-1",
                    "google-gemini",
                    "gemini-embedding-2",
                    1536,
                    "a" * 64,
                    "b" * 64,
                    "[1.0]",
                    "2026-08-31 00:00:00",
                ),
            )

        await database.create_schema()

        async with database.engine.begin() as connection:
            columns = {
                row[1]
                for row in (
                    await connection.exec_driver_sql("PRAGMA table_info(chunk_embeddings)")
                ).all()
            }
            migrated = (
                await connection.exec_driver_sql(
                    "SELECT input_schema_version FROM chunk_embeddings "
                    "WHERE id = 'embedding-legacy'"
                )
            ).one()
            # The former uniqueness rule ignored provider/template input. This second row is
            # valid only after the table has been rebuilt with full space provenance.
            await connection.exec_driver_sql(
                "INSERT INTO chunk_embeddings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "embedding-current",
                    "chunk-1",
                    "google-gemini",
                    "gemini-embedding-2",
                    1536,
                    "asymmetric-qa-v1",
                    "a" * 64,
                    "c" * 64,
                    "[1.0]",
                    "2026-08-31 00:00:01",
                ),
            )
        assert "input_schema_version" in columns
        assert migrated.input_schema_version == "legacy-unknown-v0"
    finally:
        await database.dispose()
