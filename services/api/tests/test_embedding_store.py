from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import Float, func, select
from sqlalchemy.dialects.postgresql.asyncpg import PGDialect_asyncpg

from app.config import Settings
from app.database import Database
from app.embedding_store import (
    chunk_content_sha256,
    embed_current_chunks,
    persist_chunk_embedding,
    postgres_cosine_distance,
    semantic_scores_for_allowed_chunks,
)
from app.embeddings import (
    EmbeddingGenerationError,
    EmbeddingJobSpecError,
    EmbeddingResult,
    active_embedding_job_spec,
    build_embedding_generator,
    build_embedding_generator_for_job,
)
from app.enums import JobStatus
from app.models import (
    ChunkEmbedding,
    Document,
    DocumentChunk,
    DocumentVersion,
    ProcessingJob,
    WarningLetter,
)
from app.seed import seed_demo
from app.worker import process_next_job


class FakeEmbeddingGenerator:
    provider = "test-embedding-provider"
    input_schema_version = "asymmetric-qa-v1"
    model_id = "gemini-embedding-2"
    dimensions = 1_536

    def __init__(
        self,
        *,
        query_axis: int = 0,
        fail_query: bool = False,
        model_id: str = "gemini-embedding-2",
        chunker_version: str = "structure-v1",
    ) -> None:
        self.query_axis = query_axis
        self.fail_query = fail_query
        self.model_id = model_id
        self.chunker_version = chunker_version
        self.document_calls = 0
        self.query_calls = 0

    @staticmethod
    def _vector(axis: int) -> list[float]:
        values = [0.0] * 1_536
        values[axis] = 1.0
        return values

    async def embed_document(self, content: str, *, title: str | None = None) -> EmbeddingResult:
        self.document_calls += 1
        return EmbeddingResult(
            values=self._vector(0),
            model_id=self.model_id,
            dimensions=self.dimensions,
            provider_input_sha256=self.document_input_sha256(content, title=title),
        )

    @staticmethod
    def document_input_sha256(content: str, *, title: str | None = None) -> str:
        normalized = " ".join(content.split())
        normalized_title = " ".join((title or "none").split()) or "none"
        prepared = f"title: {normalized_title} | text: {normalized}"
        return hashlib.sha256(prepared.encode()).hexdigest()

    async def embed_query(self, content: str) -> EmbeddingResult:
        self.query_calls += 1
        if self.fail_query:
            raise EmbeddingGenerationError("simulated provider outage")
        return EmbeddingResult(
            values=self._vector(self.query_axis),
            model_id=self.model_id,
            dimensions=self.dimensions,
            provider_input_sha256=hashlib.sha256(content.encode()).hexdigest(),
        )


def test_postgresql_cosine_distance_is_compiled_as_a_scalar() -> None:
    distance = postgres_cosine_distance([0.0] * 1_536)
    similarity = 1.0 - distance
    assert isinstance(distance.type, Float)
    assert isinstance(similarity.type, Float)
    assert isinstance(similarity.left.type, Float)
    compiled = str(select(similarity).compile(dialect=PGDialect_asyncpg()))
    assert "chunk_embeddings.embedding <=>" in compiled


def test_embedding_configuration_is_opt_in_and_schema_dimension_is_fixed() -> None:
    disabled = Settings(
        app_env="test",
        llm_provider="none",
        embedding_enabled=False,
        gemini_api_key=None,
    )
    enabled = Settings(
        app_env="test",
        llm_provider="none",
        embedding_enabled=True,
        gemini_api_key="server-only-test-key",
    )
    assert build_embedding_generator(disabled) is None
    assert build_embedding_generator(enabled) is not None
    with pytest.raises(ValidationError, match="GEMINI_API_KEY.*EMBEDDING_ENABLED"):
        Settings(
            app_env="test",
            llm_provider="none",
            embedding_enabled=True,
            gemini_api_key=None,
        )
    with pytest.raises(ValidationError, match="EMBEDDING_DIMENSIONS must be 1536"):
        Settings(app_env="test", llm_provider="none", embedding_dimensions=768)


def test_queued_embedding_space_is_honored_across_rolling_configuration() -> None:
    queued_settings = Settings(
        app_env="test",
        llm_provider="none",
        embedding_enabled=True,
        gemini_api_key="server-only-test-key",
        embedding_model_id="gemini-embedding-old",
        chunker_version="structure-v1",
    )
    rolling_settings = queued_settings.model_copy(
        update={
            "embedding_model_id": "gemini-embedding-new",
            "chunker_version": "structure-v2",
        }
    )
    payload = active_embedding_job_spec(
        queued_settings,
        prepared_input_manifest_sha256="a" * 64,
    ).as_payload()
    generator = build_embedding_generator_for_job(rolling_settings, payload)

    assert generator is not None
    assert generator.model_id == "gemini-embedding-old"
    assert generator.chunker_version == "structure-v1"
    assert generator.provider == payload["provider"]
    assert generator.input_schema_version == payload["input_schema_version"]
    assert generator.expected_input_manifest_sha256 == "a" * 64

    with pytest.raises(EmbeddingJobSpecError, match="missing a supported"):
        build_embedding_generator_for_job(rolling_settings, {"model_id": "legacy"})
    with pytest.raises(EmbeddingJobSpecError, match="provider is not supported"):
        build_embedding_generator_for_job(
            rolling_settings,
            {**payload, "provider": "different-provider"},
        )


@pytest.mark.asyncio
async def test_embedding_backfill_persists_every_current_chunk_and_resumes(
    settings: Settings,
    fixture_dir: Path,
) -> None:
    database = Database(settings.database_url)
    generator = FakeEmbeddingGenerator()
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            await seed_demo(session, settings, fixture_dir)
        async with database.session_factory() as session:
            current_chunks = await session.scalar(
                select(func.count(DocumentChunk.id))
                .join(WarningLetter, WarningLetter.id == DocumentChunk.warning_letter_id)
                .where(
                    WarningLetter.current_in_scope.is_(True),
                    WarningLetter.current_version_id == DocumentChunk.document_version_id,
                )
            )
            first = await embed_current_chunks(
                session,
                generator=generator,  # type: ignore[arg-type]
                batch_size=2,
                max_items=2,
            )
            assert first.created == 2
        async with database.session_factory() as session:
            resumed = await embed_current_chunks(
                session,
                generator=generator,  # type: ignore[arg-type]
                batch_size=3,
            )
            stored = await session.scalar(select(func.count(ChunkEmbedding.id)))
            assert stored == current_chunks
            assert resumed.created == current_chunks - 2
        async with database.session_factory() as session:
            complete = await embed_current_chunks(
                session,
                generator=generator,  # type: ignore[arg-type]
                batch_size=4,
            )
            assert complete.created == 0
            assert complete.examined == 0
        assert generator.document_calls == current_chunks
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_backfill_and_retrieval_only_use_the_active_chunker_space(
    settings: Settings,
    fixture_dir: Path,
) -> None:
    database = Database(settings.database_url)
    generator = FakeEmbeddingGenerator(chunker_version=settings.chunker_version)
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            await seed_demo(session, settings, fixture_dir)
            legacy_chunk = await session.scalar(select(DocumentChunk).order_by(DocumentChunk.id))
            assert legacy_chunk is not None
            legacy_chunk.chunker_version = "structure-legacy"
            await session.commit()
        async with database.session_factory() as session:
            metrics = await embed_current_chunks(
                session,
                generator=generator,  # type: ignore[arg-type]
                batch_size=50,
            )
            stored_for_legacy = await session.scalar(
                select(func.count(ChunkEmbedding.id)).where(
                    ChunkEmbedding.document_chunk_id == legacy_chunk.id
                )
            )
            scores = await semantic_scores_for_allowed_chunks(
                session,
                question="legacy evidence",
                allowed_chunks=[legacy_chunk],
                generator=generator,  # type: ignore[arg-type]
                limit=5,
            )
        assert metrics.created > 0
        assert stored_for_legacy == 0
        assert scores == {}
        assert generator.query_calls == 0
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_title_change_creates_a_distinct_prepared_input_embedding(
    settings: Settings,
    fixture_dir: Path,
) -> None:
    database = Database(settings.database_url)
    generator = FakeEmbeddingGenerator()
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            await seed_demo(session, settings, fixture_dir)
            chunk = await session.scalar(select(DocumentChunk).order_by(DocumentChunk.id))
            assert chunk is not None
            first = await persist_chunk_embedding(
                session,
                chunk=chunk,
                title="Original FDA title",
                generator=generator,  # type: ignore[arg-type]
            )
            second = await persist_chunk_embedding(
                session,
                chunk=chunk,
                title="Corrected FDA title",
                generator=generator,  # type: ignore[arg-type]
            )
            await session.commit()
            rows = list(
                (
                    await session.scalars(
                        select(ChunkEmbedding).where(
                            ChunkEmbedding.document_chunk_id == chunk.id
                        )
                    )
                ).all()
            )
        assert first.created is True
        assert second.created is True
        assert len(rows) == 2
        assert len({row.provider_input_sha256 for row in rows}) == 2
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_queued_manifest_rejects_a_title_change_before_provider_call(
    settings: Settings,
    fixture_dir: Path,
) -> None:
    enabled = settings.model_copy(
        update={
            "embedding_enabled": True,
            "gemini_api_key": SecretStr("server-only-test-key"),
        }
    )
    database = Database(enabled.database_url)
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            await seed_demo(session, enabled, fixture_dir)
            job = await session.scalar(
                select(ProcessingJob)
                .where(ProcessingJob.job_type == "embed")
                .order_by(ProcessingJob.created_at, ProcessingJob.id)
            )
            assert job is not None
            version = await session.get(DocumentVersion, job.document_version_id)
            assert version is not None
            document = await session.get(Document, version.document_id)
            assert document is not None
            document.title = f"{document.title} corrected"
            await session.commit()
            payload = dict(job.payload)
            warning_letter_id = job.warning_letter_id
            document_version_id = job.document_version_id

        generator = build_embedding_generator_for_job(enabled, payload)
        assert generator is not None
        async with database.session_factory() as session:
            with pytest.raises(EmbeddingJobSpecError, match="manifest no longer matches"):
                await embed_current_chunks(
                    session,
                    generator=generator,
                    batch_size=10,
                    chunker_version=generator.chunker_version,
                    warning_letter_id=warning_letter_id,
                    document_version_id=document_version_id,
                )
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_semantic_ranking_does_not_call_provider_without_stored_candidates(
    settings: Settings,
    fixture_dir: Path,
) -> None:
    database = Database(settings.database_url)
    generator = FakeEmbeddingGenerator()
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            await seed_demo(session, settings, fixture_dir)
        async with database.session_factory() as session:
            chunk = await session.scalar(select(DocumentChunk).limit(1))
            assert chunk is not None
            scores = await semantic_scores_for_allowed_chunks(
                session,
                question="unembedded query",
                allowed_chunks=[chunk],
                generator=generator,  # type: ignore[arg-type]
                limit=5,
            )
            assert scores == {}
            assert generator.query_calls == 0
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_semantic_candidate_sql_requires_exact_chunk_content_pairs(
    settings: Settings,
    fixture_dir: Path,
) -> None:
    database = Database(settings.database_url)
    generator = FakeEmbeddingGenerator()
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            await seed_demo(session, settings, fixture_dir)
            rows = list(
                (
                    await session.execute(
                        select(DocumentChunk, Document.title)
                        .join(
                            DocumentVersion,
                            DocumentVersion.id == DocumentChunk.document_version_id,
                        )
                        .join(Document, Document.id == DocumentVersion.document_id)
                        .order_by(DocumentChunk.id)
                        .limit(2)
                    )
                ).all()
            )
            assert len(rows) == 2
            (first, first_title), (second, second_title) = rows
            # Each hash exists in the allowed set, but is paired with the wrong chunk. An
            # independent id IN (...) + hash IN (...) filter would incorrectly admit both.
            session.add_all(
                [
                    ChunkEmbedding(
                        document_chunk_id=first.id,
                        provider=generator.provider,
                        model_id=generator.model_id,
                        dimensions=generator.dimensions,
                        input_schema_version=generator.input_schema_version,
                        content_sha256=chunk_content_sha256(second.content),
                        provider_input_sha256=generator.document_input_sha256(
                            first.content,
                            title=first_title,
                        ),
                        embedding=generator._vector(0),
                    ),
                    ChunkEmbedding(
                        document_chunk_id=second.id,
                        provider=generator.provider,
                        model_id=generator.model_id,
                        dimensions=generator.dimensions,
                        input_schema_version=generator.input_schema_version,
                        content_sha256=chunk_content_sha256(first.content),
                        provider_input_sha256=generator.document_input_sha256(
                            second.content,
                            title=second_title,
                        ),
                        embedding=generator._vector(1),
                    ),
                ]
            )
            await session.commit()
            scores = await semantic_scores_for_allowed_chunks(
                session,
                question="must not call provider",
                allowed_chunks=[first, second],
                generator=generator,  # type: ignore[arg-type]
                limit=2,
            )
        assert scores == {}
        assert generator.query_calls == 0
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_new_ingestion_queues_idempotent_embedding_jobs_and_worker_persists_vectors(
    settings: Settings,
    fixture_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enabled = settings.model_copy(
        update={
            "embedding_enabled": True,
            "gemini_api_key": SecretStr("server-only-test-key"),
        }
    )
    database = Database(enabled.database_url)
    generator = FakeEmbeddingGenerator()
    monkeypatch.setattr(
        "app.worker.build_embedding_generator_for_job",
        lambda _settings, _payload: generator,
    )
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            await seed_demo(session, enabled, fixture_dir)
            queued = await session.scalar(
                select(func.count(ProcessingJob.id)).where(ProcessingJob.job_type == "embed")
            )
            assert queued == 4
            jobs = list(
                (
                    await session.scalars(
                        select(ProcessingJob).where(ProcessingJob.job_type == "embed")
                    )
                ).all()
            )
            assert all(
                {
                    "spec_version",
                    "provider",
                    "model_id",
                    "dimensions",
                    "input_schema_version",
                    "chunker_version",
                    "prepared_input_manifest_sha256",
                }.issubset(job.payload)
                for job in jobs
            )
        result = await process_next_job(database, enabled)
        assert result is not None
        assert result.status == JobStatus.SUCCEEDED.value
        assert result.metrics["embeddings_created"] > 0
        async with database.session_factory() as session:
            stored = await session.scalar(select(func.count(ChunkEmbedding.id)))
            assert stored == result.metrics["embeddings_created"]
    finally:
        await database.dispose()


def test_no_retrieval_and_metadata_routes_never_call_embedding_provider(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    generator = FakeEmbeddingGenerator()
    previous = client.app.state.embedding_generator
    client.app.state.embedding_generator = generator
    try:
        greeting = client.post(
            "/api/v1/rag/query",
            headers=viewer_headers,
            json={"question": "안녕하세요"},
        )
        metadata = client.post(
            "/api/v1/rag/query",
            headers=viewer_headers,
            json={"question": "최신 경고장 발행일은?"},
        )
    finally:
        client.app.state.embedding_generator = previous
    assert greeting.status_code == 200
    assert greeting.json()["retrieval_strategy"] == "none"
    assert metadata.status_code == 200
    assert metadata.json()["retrieval_strategy"] == "metadata"
    assert generator.query_calls == 0


def test_semantic_provider_failure_falls_back_to_lexical_retrieval(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    settings = client.app.state.settings

    async def persist_one() -> None:
        database = Database(settings.database_url)
        try:
            async with database.session_factory() as session:
                row = (
                    await session.execute(
                        select(DocumentChunk, Document.title)
                        .join(
                            DocumentVersion,
                            DocumentVersion.id == DocumentChunk.document_version_id,
                        )
                        .join(Document, Document.id == DocumentVersion.document_id)
                        .where(DocumentChunk.content.ilike("%process validation%"))
                    )
                ).first()
                assert row is not None
                chunk, title = row
                generator = FakeEmbeddingGenerator()
                from app.embedding_store import persist_chunk_embedding

                await persist_chunk_embedding(
                    session,
                    chunk=chunk,
                    title=title,
                    generator=generator,  # type: ignore[arg-type]
                )
                await session.commit()
        finally:
            await database.dispose()

    import asyncio

    asyncio.run(persist_one())
    generator = FakeEmbeddingGenerator(fail_query=True)
    previous = client.app.state.embedding_generator
    client.app.state.embedding_generator = generator
    try:
        response = client.post(
            "/api/v1/rag/query",
            headers=viewer_headers,
            json={"question": "process validation"},
        )
    finally:
        client.app.state.embedding_generator = previous
    assert response.status_code == 200
    assert response.json()["citations"]
    assert response.json()["evidence_sufficiency"] == "sufficient"
    assert generator.query_calls == 1


def test_acl_is_applied_before_semantic_candidates(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    settings = client.app.state.settings
    model_id = "acl-isolation-embedding"
    generator = FakeEmbeddingGenerator(model_id=model_id)
    private_id = ""

    async def arrange() -> None:
        nonlocal private_id
        database = Database(settings.database_url)
        try:
            async with database.session_factory() as session:
                chunk_rows = list(
                    (
                        await session.execute(
                            select(DocumentChunk, Document.title)
                            .join(
                                DocumentVersion,
                                DocumentVersion.id == DocumentChunk.document_version_id,
                            )
                            .join(Document, Document.id == DocumentVersion.document_id)
                            .order_by(DocumentChunk.id)
                            .limit(2)
                        )
                    ).all()
                )
                assert len(chunk_rows) == 2
                (private, private_title), (public, public_title) = chunk_rows
                private_id = private.id
                private.acl = {"roles": ["admin"]}
                public.acl = {"roles": ["viewer"]}
                session.add_all(
                    [
                        ChunkEmbedding(
                            document_chunk_id=private.id,
                            provider=generator.provider,
                            model_id=model_id,
                            dimensions=1_536,
                            input_schema_version=generator.input_schema_version,
                            content_sha256=chunk_content_sha256(private.content),
                            provider_input_sha256=generator.document_input_sha256(
                                private.content,
                                title=private_title,
                            ),
                            embedding=generator._vector(0),
                        ),
                        ChunkEmbedding(
                            document_chunk_id=public.id,
                            provider=generator.provider,
                            model_id=model_id,
                            dimensions=1_536,
                            input_schema_version=generator.input_schema_version,
                            content_sha256=chunk_content_sha256(public.content),
                            provider_input_sha256=generator.document_input_sha256(
                                public.content,
                                title=public_title,
                            ),
                            embedding=generator._vector(1),
                        ),
                    ]
                )
                await session.commit()
        finally:
            await database.dispose()

    import asyncio

    asyncio.run(arrange())
    previous = client.app.state.embedding_generator
    client.app.state.embedding_generator = generator
    try:
            response = client.post(
                "/api/v1/rag/query",
                headers=viewer_headers,
                json={
                        "question": "FDA warning-letter evidence about xylophone quasar zeppelin",
                    "retrieval_mode": "corpus",
                },
            )
    finally:
        client.app.state.embedding_generator = previous
    assert response.status_code == 200
    assert private_id not in {item["chunk_id"] for item in response.json()["citations"]}
    assert generator.query_calls == 1
