from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import quote

import httpx
from pydantic import SecretStr

if TYPE_CHECKING:
    from app.config import Settings

GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_EMBEDDING_PROVIDER = "google-gemini"
GEMINI_EMBEDDING_INPUT_SCHEMA_VERSION = "asymmetric-qa-v1"


class EmbeddingGenerationError(RuntimeError):
    """The embedding provider failed or returned an invalid vector."""


class EmbeddingJobSpecError(RuntimeError):
    """A queued job names an unsupported or incomplete immutable embedding space."""


@dataclass(frozen=True)
class EmbeddingResult:
    values: list[float]
    model_id: str
    dimensions: int
    provider_input_sha256: str


@dataclass(frozen=True)
class EmbeddingJobSpec:
    """Immutable vector-space coordinates captured when an embed job is queued."""

    provider: str
    model_id: str
    dimensions: int
    input_schema_version: str
    chunker_version: str
    prepared_input_manifest_sha256: str

    def as_payload(self) -> dict[str, str | int]:
        return {
            "spec_version": 1,
            "provider": self.provider,
            "model_id": self.model_id,
            "dimensions": self.dimensions,
            "input_schema_version": self.input_schema_version,
            "chunker_version": self.chunker_version,
            "prepared_input_manifest_sha256": self.prepared_input_manifest_sha256,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> EmbeddingJobSpec:
        if (
            not isinstance(payload, Mapping)
            or isinstance(payload.get("spec_version"), bool)
            or payload.get("spec_version") != 1
        ):
            raise EmbeddingJobSpecError(
                "Embedding job is missing a supported immutable space specification"
            )
        dimensions = payload.get("dimensions")
        values = {
            "provider": payload.get("provider"),
            "model_id": payload.get("model_id"),
            "input_schema_version": payload.get("input_schema_version"),
            "chunker_version": payload.get("chunker_version"),
            "prepared_input_manifest_sha256": payload.get(
                "prepared_input_manifest_sha256"
            ),
        }
        if (
            isinstance(dimensions, bool)
            or not isinstance(dimensions, int)
            or any(not isinstance(value, str) or not value.strip() for value in values.values())
        ):
            raise EmbeddingJobSpecError("Embedding job space specification is invalid")
        manifest_hash = str(values["prepared_input_manifest_sha256"])
        if len(manifest_hash) != 64 or any(
            character not in "0123456789abcdef" for character in manifest_hash
        ):
            raise EmbeddingJobSpecError("Embedding job input manifest hash is invalid")
        return cls(
            provider=str(values["provider"]),
            model_id=str(values["model_id"]),
            dimensions=dimensions,
            input_schema_version=str(values["input_schema_version"]),
            chunker_version=str(values["chunker_version"]),
            prepared_input_manifest_sha256=manifest_hash,
        )


class GeminiEmbeddingGenerator:
    """Small server-only Gemini embedding client with strict output validation."""

    provider = GEMINI_EMBEDDING_PROVIDER
    input_schema_version = GEMINI_EMBEDDING_INPUT_SCHEMA_VERSION

    def __init__(
        self,
        *,
        api_key: SecretStr,
        model_id: str = "gemini-embedding-2",
        dimensions: int = 1_536,
        chunker_version: str = "structure-v1",
        expected_input_manifest_sha256: str | None = None,
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if dimensions not in {768, 1_536, 3_072}:
            raise ValueError("Embedding dimensions must be 768, 1536, or 3072")
        model_id_valid = bool(model_id) and all(
            character.isalnum() or character in "-._" for character in model_id
        )
        if not model_id_valid:
            raise ValueError("Embedding model ID contains unsupported characters")
        if not chunker_version or len(chunker_version) > 80:
            raise ValueError("Chunker version is invalid")
        self.model_id = model_id
        self.dimensions = dimensions
        self.chunker_version = chunker_version
        self.expected_input_manifest_sha256 = expected_input_manifest_sha256
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._transport = transport

    @staticmethod
    def prepare_text(
        content: str,
        *,
        kind: Literal["query", "document"],
        title: str | None = None,
    ) -> str:
        normalized = " ".join(content.split())
        if not normalized:
            raise ValueError("Embedding content is empty")
        if kind == "query":
            return f"task: question answering | query: {normalized}"
        normalized_title = " ".join((title or "none").split()) or "none"
        return f"title: {normalized_title} | text: {normalized}"

    def document_input_sha256(self, content: str, *, title: str | None = None) -> str:
        prepared = self.prepare_text(content, kind="document", title=title)
        return hashlib.sha256(prepared.encode("utf-8")).hexdigest()

    async def embed_query(self, content: str) -> EmbeddingResult:
        return await self._embed(self.prepare_text(content, kind="query"))

    async def embed_document(self, content: str, *, title: str | None = None) -> EmbeddingResult:
        return await self._embed(self.prepare_text(content, kind="document", title=title))

    async def _embed(self, prepared_content: str) -> EmbeddingResult:
        model = quote(self.model_id, safe="-._")
        url = f"{GEMINI_API_BASE_URL}/models/{model}:embedContent"
        body = {
            "model": f"models/{self.model_id}",
            "content": {"parts": [{"text": prepared_content}]},
            # Gemini's current REST curl examples use the protobuf field spelling. The
            # MockTransport contract test locks this exact wire shape without a live call.
            "output_dimensionality": self.dimensions,
        }
        headers = {
            "x-goog-api-key": self._api_key.get_secret_value(),
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                follow_redirects=False,
                transport=self._transport,
            ) as client:
                response = await client.post(url, headers=headers, json=body)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise EmbeddingGenerationError(
                f"Gemini embedding request failed with status {exc.response.status_code}"
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise EmbeddingGenerationError(
                "Gemini embedding request could not be completed"
            ) from exc

        raw_values = (
            payload.get("embedding", {}).get("values") if isinstance(payload, dict) else None
        )
        if not isinstance(raw_values, list) or len(raw_values) != self.dimensions:
            raise EmbeddingGenerationError("Gemini returned an embedding with invalid dimensions")
        values: list[float] = []
        for raw_value in raw_values:
            if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
                raise EmbeddingGenerationError("Gemini returned a non-numeric embedding value")
            value = float(raw_value)
            if not math.isfinite(value):
                raise EmbeddingGenerationError("Gemini returned a non-finite embedding value")
            values.append(value)
        magnitude = math.sqrt(sum(value * value for value in values))
        if magnitude <= 0:
            raise EmbeddingGenerationError("Gemini returned a zero-magnitude embedding")
        return EmbeddingResult(
            values=values,
            model_id=self.model_id,
            dimensions=self.dimensions,
            provider_input_sha256=hashlib.sha256(
                prepared_content.encode("utf-8")
            ).hexdigest(),
        )


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_magnitude = math.sqrt(sum(value * value for value in left))
    right_magnitude = math.sqrt(sum(value * value for value in right))
    if left_magnitude <= 0 or right_magnitude <= 0:
        return 0.0
    return dot / (left_magnitude * right_magnitude)


def build_embedding_generator(settings: Settings) -> GeminiEmbeddingGenerator | None:
    """Build the server-only provider only when embeddings are explicitly enabled.

    The key is never accepted from a request and is never placed in application state on its
    own. Returning ``None`` for a missing key keeps local/test environments fail-safe and makes
    the lexical retriever the deterministic fallback.
    """

    if not settings.embedding_enabled or settings.gemini_api_key is None:
        return None
    return GeminiEmbeddingGenerator(
        api_key=settings.gemini_api_key,
        model_id=settings.embedding_model_id,
        dimensions=settings.embedding_dimensions,
        chunker_version=settings.chunker_version,
        timeout_seconds=settings.embedding_timeout_seconds,
    )


def active_embedding_job_spec(
    settings: Settings,
    *,
    prepared_input_manifest_sha256: str,
) -> EmbeddingJobSpec:
    """Return the exact vector space that a newly queued job must retain."""

    return EmbeddingJobSpec(
        provider=GEMINI_EMBEDDING_PROVIDER,
        model_id=settings.embedding_model_id,
        dimensions=settings.embedding_dimensions,
        input_schema_version=GEMINI_EMBEDDING_INPUT_SCHEMA_VERSION,
        chunker_version=settings.chunker_version,
        prepared_input_manifest_sha256=prepared_input_manifest_sha256,
    )


def build_embedding_generator_for_job(
    settings: Settings,
    payload: Mapping[str, Any] | None,
) -> GeminiEmbeddingGenerator | None:
    """Build the space captured by a job rather than silently using rolling config.

    A model change can be honored because the queued model ID is passed to Gemini. Provider,
    input-template, and fixed database-dimension changes require a separately deployed adapter
    or migration, so unsupported queued jobs fail closed and follow the worker's retry/DLQ path.
    """

    if not settings.embedding_enabled or settings.gemini_api_key is None:
        return None
    spec = EmbeddingJobSpec.from_payload(payload)
    if spec.provider != GEMINI_EMBEDDING_PROVIDER:
        raise EmbeddingJobSpecError("Embedding job provider is not supported by this worker")
    if spec.input_schema_version != GEMINI_EMBEDDING_INPUT_SCHEMA_VERSION:
        raise EmbeddingJobSpecError("Embedding job input schema is not supported by this worker")
    if spec.dimensions != 1_536:
        raise EmbeddingJobSpecError("Embedding job dimensions do not match the vector store")
    try:
        return GeminiEmbeddingGenerator(
            api_key=settings.gemini_api_key,
            model_id=spec.model_id,
            dimensions=spec.dimensions,
            chunker_version=spec.chunker_version,
            expected_input_manifest_sha256=spec.prepared_input_manifest_sha256,
            timeout_seconds=settings.embedding_timeout_seconds,
        )
    except ValueError as exc:
        raise EmbeddingJobSpecError("Embedding job space specification is invalid") from exc
