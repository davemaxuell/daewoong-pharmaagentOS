from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Float, select, tuple_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.embeddings import (
    EmbeddingGenerationError,
    EmbeddingJobSpecError,
    GeminiEmbeddingGenerator,
    active_embedding_job_spec,
    cosine_similarity,
)
from app.enums import JobStatus, ScopeStatus
from app.models import (
    ChunkEmbedding,
    Document,
    DocumentChunk,
    DocumentVersion,
    ProcessingJob,
    WarningLetter,
)


@dataclass(frozen=True)
class EmbeddingWriteResult:
    created: bool
    embedding_id: str


@dataclass
class EmbeddingBackfillMetrics:
    examined: int = 0
    created: int = 0
    skipped: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "chunks_examined": self.examined,
            "embeddings_created": self.created,
            "embeddings_skipped": self.skipped,
        }


class EmbeddingBackfillError(RuntimeError):
    """A resumable embedding run stopped after its completed rows were committed."""

    def __init__(self, metrics: EmbeddingBackfillMetrics) -> None:
        super().__init__("Embedding provider failed; completed chunk embeddings were retained")
        self.metrics = metrics


class SemanticRetrievalError(RuntimeError):
    """The optional vector store was unavailable; callers may use lexical retrieval."""


def postgres_cosine_distance(query_vector: list[float]) -> Any:
    """Return a scalar pgvector distance expression, never a vector-typed expression."""

    return ChunkEmbedding.embedding.op("<=>", return_type=Float())(query_vector)


def chunk_content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def embedding_input_manifest_sha256(
    entries: list[tuple[str, str, str]],
) -> str:
    """Fingerprint an ordered version-level set of chunk/content/prepared-input identities."""

    encoded = json.dumps(sorted(entries), separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


async def queue_embedding_job(
    session: AsyncSession,
    settings: Settings,
    *,
    warning_letter_id: str,
    document_version_id: str,
) -> ProcessingJob | None:
    """Queue one idempotent version-level embedding job when a provider is configured."""

    if not settings.embedding_enabled or settings.gemini_api_key is None:
        return None
    # Chunks use Python-side normalization for provider input, so capture their exact
    # version-level manifest after pending ORM rows have stable IDs.
    await session.flush()
    rows = list(
        (
            await session.execute(
                select(DocumentChunk, Document.title)
                .join(
                    DocumentVersion,
                    DocumentVersion.id == DocumentChunk.document_version_id,
                )
                .join(Document, Document.id == DocumentVersion.document_id)
                .where(
                    DocumentChunk.document_version_id == document_version_id,
                    DocumentChunk.chunker_version == settings.chunker_version,
                )
                .order_by(DocumentChunk.id)
            )
        ).all()
    )
    if not rows:
        return None
    manifest_entries = [
        (
            str(chunk.id),
            chunk_content_sha256(chunk.content),
            hashlib.sha256(
                GeminiEmbeddingGenerator.prepare_text(
                    chunk.content,
                    kind="document",
                    title=str(title or "FDA warning letter"),
                ).encode()
            ).hexdigest(),
        )
        for chunk, title in rows
    ]
    spec = active_embedding_job_spec(
        settings,
        prepared_input_manifest_sha256=embedding_input_manifest_sha256(manifest_entries),
    )
    payload = spec.as_payload()
    identity = hashlib.sha256(
        f"{document_version_id}:".encode()
        + json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    idempotency_key = f"embed-version-v2:{identity}"
    existing = await session.scalar(
        select(ProcessingJob).where(ProcessingJob.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return existing
    job = ProcessingJob(
        warning_letter_id=warning_letter_id,
        document_version_id=document_version_id,
        job_type="embed",
        status=JobStatus.PENDING.value,
        idempotency_key=idempotency_key,
        payload=payload,
        max_attempts=5,
    )
    session.add(job)
    return job


async def persist_chunk_embedding(
    session: AsyncSession,
    *,
    chunk: DocumentChunk,
    title: str,
    generator: GeminiEmbeddingGenerator,
) -> EmbeddingWriteResult:
    """Persist one immutable model/content embedding, safely tolerating retry races."""

    content_hash = chunk_content_sha256(chunk.content)
    provider_input_hash = generator.document_input_sha256(chunk.content, title=title)
    existing = await session.scalar(
        select(ChunkEmbedding).where(
            ChunkEmbedding.document_chunk_id == chunk.id,
            ChunkEmbedding.provider == generator.provider,
            ChunkEmbedding.model_id == generator.model_id,
            ChunkEmbedding.dimensions == generator.dimensions,
            ChunkEmbedding.input_schema_version == generator.input_schema_version,
            ChunkEmbedding.content_sha256 == content_hash,
            ChunkEmbedding.provider_input_sha256 == provider_input_hash,
        )
    )
    if existing is not None:
        return EmbeddingWriteResult(created=False, embedding_id=existing.id)

    result = await generator.embed_document(chunk.content, title=title)
    if (
        result.model_id != generator.model_id
        or result.dimensions != 1_536
        or result.provider_input_sha256 != provider_input_hash
    ):
        raise EmbeddingGenerationError("Embedding result does not match the active vector space")
    embedding = ChunkEmbedding(
        document_chunk_id=chunk.id,
        provider=generator.provider,
        model_id=result.model_id,
        dimensions=result.dimensions,
        input_schema_version=generator.input_schema_version,
        content_sha256=content_hash,
        provider_input_sha256=result.provider_input_sha256,
        embedding=result.values,
    )
    try:
        async with session.begin_nested():
            session.add(embedding)
            await session.flush()
    except IntegrityError:
        # Another worker completed the same immutable key between our read and insert. The
        # savepoint contains the conflict so the ingestion/worker transaction stays usable.
        winner = await session.scalar(
            select(ChunkEmbedding).where(
                ChunkEmbedding.document_chunk_id == chunk.id,
                ChunkEmbedding.provider == generator.provider,
                ChunkEmbedding.model_id == generator.model_id,
                ChunkEmbedding.dimensions == generator.dimensions,
                ChunkEmbedding.input_schema_version == generator.input_schema_version,
                ChunkEmbedding.content_sha256 == content_hash,
                ChunkEmbedding.provider_input_sha256 == provider_input_hash,
            )
        )
        if winner is None:
            raise
        return EmbeddingWriteResult(created=False, embedding_id=winner.id)
    return EmbeddingWriteResult(created=True, embedding_id=embedding.id)


def _current_chunks_statement(
    chunker_version: str,
    *,
    warning_letter_id: str | None,
    document_version_id: str | None,
) -> Any:
    statement = (
        select(DocumentChunk, Document.title)
        .join(WarningLetter, WarningLetter.id == DocumentChunk.warning_letter_id)
        .join(DocumentVersion, DocumentVersion.id == DocumentChunk.document_version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(
            DocumentChunk.corpus_id == "fda-drugs",
            WarningLetter.current_in_scope.is_(True),
            WarningLetter.scope_status == ScopeStatus.IN_SCOPE_DRUGS.value,
            WarningLetter.current_version_id == DocumentChunk.document_version_id,
            Document.warning_letter_id == WarningLetter.id,
            Document.current_version_id == DocumentVersion.id,
            Document.current_in_scope.is_(True),
            Document.source_available.is_(True),
            DocumentVersion.scope_status == ScopeStatus.IN_SCOPE_DRUGS.value,
            DocumentChunk.chunker_version == chunker_version,
        )
        .order_by(DocumentChunk.id)
    )
    if warning_letter_id:
        statement = statement.where(DocumentChunk.warning_letter_id == warning_letter_id)
    if document_version_id:
        statement = statement.where(DocumentChunk.document_version_id == document_version_id)
    return statement


async def _existing_candidate_inputs(
    session: AsyncSession,
    *,
    candidates: list[tuple[str, str, str]],
    generator: GeminiEmbeddingGenerator,
) -> set[tuple[str, str, str]]:
    """Fetch exact chunk/content/prepared-input matches within one immutable space."""

    if not candidates:
        return set()
    statement = select(
        ChunkEmbedding.document_chunk_id,
        ChunkEmbedding.content_sha256,
        ChunkEmbedding.provider_input_sha256,
    ).where(
        ChunkEmbedding.provider == generator.provider,
        ChunkEmbedding.model_id == generator.model_id,
        ChunkEmbedding.dimensions == generator.dimensions,
        ChunkEmbedding.input_schema_version == generator.input_schema_version,
        tuple_(
            ChunkEmbedding.document_chunk_id,
            ChunkEmbedding.content_sha256,
            ChunkEmbedding.provider_input_sha256,
        ).in_(candidates),
    )
    return {
        (str(chunk_id), str(content_hash), str(provider_input_hash))
        for chunk_id, content_hash, provider_input_hash in (await session.execute(statement)).all()
    }


async def embed_current_chunks(
    session: AsyncSession,
    *,
    generator: GeminiEmbeddingGenerator,
    batch_size: int,
    chunker_version: str | None = None,
    max_items: int | None = None,
    warning_letter_id: str | None = None,
    document_version_id: str | None = None,
) -> EmbeddingBackfillMetrics:
    """Embed current authorized chunks and commit each result for resumable backfills."""

    if generator.dimensions != 1_536:
        raise ValueError("The active embedding store requires 1536 dimensions")
    active_chunker_version = chunker_version or generator.chunker_version
    if active_chunker_version != generator.chunker_version:
        raise ValueError("Chunker version does not match the queued embedding space")
    expected_manifest = getattr(generator, "expected_input_manifest_sha256", None)
    if expected_manifest is not None:
        manifest_rows = list(
            (
                await session.execute(
                    _current_chunks_statement(
                        active_chunker_version,
                        warning_letter_id=warning_letter_id,
                        document_version_id=document_version_id,
                    )
                )
            ).all()
        )
        manifest_entries = [
            (
                str(chunk.id),
                chunk_content_sha256(chunk.content),
                generator.document_input_sha256(
                    chunk.content,
                    title=str(title or "FDA warning letter"),
                ),
            )
            for chunk, title in manifest_rows
        ]
        if embedding_input_manifest_sha256(manifest_entries) != expected_manifest:
            raise EmbeddingJobSpecError(
                "Queued embedding input manifest no longer matches the current document"
            )
    metrics = EmbeddingBackfillMetrics()
    cursor: str | None = None
    scan_size = min(max(1, batch_size), 100)
    while max_items is None or metrics.examined < max_items:
        statement = _current_chunks_statement(
            active_chunker_version,
            warning_letter_id=warning_letter_id,
            document_version_id=document_version_id,
        )
        if cursor is not None:
            statement = statement.where(DocumentChunk.id > cursor)
        rows = list(
            (await session.execute(statement.limit(scan_size))).all()
        )
        if not rows:
            break
        cursor = str(rows[-1][0].id)
        candidate_inputs = [
            (
                str(chunk.id),
                chunk_content_sha256(chunk.content),
                generator.document_input_sha256(
                    chunk.content,
                    title=str(title or "FDA warning letter"),
                ),
            )
            for chunk, title in rows
        ]
        existing_inputs = await _existing_candidate_inputs(
            session,
            candidates=candidate_inputs,
            generator=generator,
        )
        for (chunk, title), candidate_input in zip(rows, candidate_inputs, strict=True):
            if candidate_input in existing_inputs:
                continue
            if max_items is not None and metrics.examined >= max_items:
                return metrics
            metrics.examined += 1
            try:
                result = await persist_chunk_embedding(
                    session,
                    chunk=chunk,
                    title=str(title or "FDA warning letter"),
                    generator=generator,
                )
                if result.created:
                    metrics.created += 1
                else:
                    metrics.skipped += 1
                # A provider outage after this point must not spend tokens for this chunk again.
                await session.commit()
            except EmbeddingGenerationError as exc:
                await session.rollback()
                raise EmbeddingBackfillError(metrics) from exc
    return metrics


async def semantic_scores_for_allowed_chunks(
    session: AsyncSession,
    *,
    question: str,
    allowed_chunks: list[DocumentChunk],
    generator: GeminiEmbeddingGenerator,
    limit: int,
) -> dict[str, float]:
    """Rank only pre-authorized chunks; an empty embedding set avoids a provider call."""

    if not allowed_chunks or generator.dimensions != 1_536:
        return {}
    active_chunks = {
        str(chunk.id): chunk
        for chunk in allowed_chunks
        if chunk.chunker_version == generator.chunker_version
    }
    if not active_chunks:
        return {}
    try:
        async with session.begin_nested():
            title_rows = (
                await session.execute(
                    select(DocumentChunk.id, Document.title)
                    .join(DocumentVersion, DocumentVersion.id == DocumentChunk.document_version_id)
                    .join(Document, Document.id == DocumentVersion.document_id)
                    .where(
                        DocumentChunk.id.in_(tuple(active_chunks)),
                        DocumentChunk.chunker_version == generator.chunker_version,
                    )
                )
            ).all()
    except SQLAlchemyError as exc:
        raise SemanticRetrievalError("Vector provenance lookup failed") from exc

    titles = {str(chunk_id): str(title or "FDA warning letter") for chunk_id, title in title_rows}
    content_hashes = {
        chunk_id: chunk_content_sha256(chunk.content)
        for chunk_id, chunk in active_chunks.items()
        if chunk_id in titles
    }
    provider_input_hashes = {
        chunk_id: generator.document_input_sha256(chunk.content, title=titles[chunk_id])
        for chunk_id, chunk in active_chunks.items()
        if chunk_id in titles
    }
    allowed_ids = tuple(content_hashes)
    if not allowed_ids:
        return {}
    content_pairs = tuple((chunk_id, content_hashes[chunk_id]) for chunk_id in allowed_ids)
    provider_input_pairs = tuple(
        (chunk_id, provider_input_hashes[chunk_id]) for chunk_id in allowed_ids
    )
    base_filters = (
        ChunkEmbedding.provider == generator.provider,
        ChunkEmbedding.model_id == generator.model_id,
        ChunkEmbedding.dimensions == generator.dimensions,
        ChunkEmbedding.input_schema_version == generator.input_schema_version,
        DocumentChunk.chunker_version == generator.chunker_version,
        tuple_(
            ChunkEmbedding.document_chunk_id,
            ChunkEmbedding.content_sha256,
        ).in_(content_pairs),
        tuple_(
            ChunkEmbedding.document_chunk_id,
            ChunkEmbedding.provider_input_sha256,
        ).in_(provider_input_pairs),
    )
    try:
        async with session.begin_nested():
            has_embedding = await session.scalar(
                select(ChunkEmbedding.id)
                .join(DocumentChunk, DocumentChunk.id == ChunkEmbedding.document_chunk_id)
                .where(*base_filters)
                .limit(1)
            )
    except SQLAlchemyError as exc:
        raise SemanticRetrievalError("Vector store availability check failed") from exc
    if has_embedding is None:
        return {}

    query = await generator.embed_query(question)
    if query.model_id != generator.model_id or query.dimensions != 1_536:
        raise EmbeddingGenerationError("Query embedding does not match the active vector space")

    requested_limit = max(1, min(limit, len(allowed_ids)))
    dialect_name = session.get_bind().dialect.name
    if dialect_name == "postgresql":
        distance = postgres_cosine_distance(query.values)
        statement = (
            select(
                ChunkEmbedding.document_chunk_id,
                ChunkEmbedding.content_sha256,
                ChunkEmbedding.provider_input_sha256,
                (1.0 - distance).label("similarity"),
            )
            .join(DocumentChunk, DocumentChunk.id == ChunkEmbedding.document_chunk_id)
            .where(*base_filters)
            .order_by(distance, ChunkEmbedding.document_chunk_id)
            .limit(requested_limit * 2)
        )
        try:
            async with session.begin_nested():
                rows = (await session.execute(statement)).all()
        except SQLAlchemyError as exc:
            raise SemanticRetrievalError("PostgreSQL vector ranking failed") from exc
        scores: dict[str, float] = {}
        for chunk_id, content_hash, provider_input_hash, similarity in rows:
            chunk_id = str(chunk_id)
            if (
                content_hashes.get(chunk_id) != content_hash
                or provider_input_hashes.get(chunk_id) != provider_input_hash
            ):
                continue
            scores[chunk_id] = max(scores.get(chunk_id, -1.0), float(similarity))
        return dict(
            sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:requested_limit]
        )

    try:
        async with session.begin_nested():
            embeddings = list(
                (
                    await session.scalars(
                        select(ChunkEmbedding)
                        .join(
                            DocumentChunk,
                            DocumentChunk.id == ChunkEmbedding.document_chunk_id,
                        )
                        .where(*base_filters)
                    )
                ).all()
            )
    except SQLAlchemyError as exc:
        raise SemanticRetrievalError("Local vector ranking failed") from exc
    scores = {}
    for embedding in embeddings:
        if (
            content_hashes.get(embedding.document_chunk_id) != embedding.content_sha256
            or provider_input_hashes.get(embedding.document_chunk_id)
            != embedding.provider_input_sha256
        ):
            continue
        score = cosine_similarity(query.values, embedding.embedding)
        scores[embedding.document_chunk_id] = max(
            scores.get(embedding.document_chunk_id, -1.0), score
        )
    return dict(sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:requested_limit])
