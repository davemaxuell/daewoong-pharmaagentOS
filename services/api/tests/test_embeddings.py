from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from app.embeddings import (
    EmbeddingGenerationError,
    GeminiEmbeddingGenerator,
    cosine_similarity,
)


@pytest.mark.asyncio
async def test_gemini_embedding_uses_asymmetric_qa_format_and_validates_dimensions() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["key"] = request.headers.get("x-goog-api-key")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"embedding": {"values": [0.5] * 768}})

    generator = GeminiEmbeddingGenerator(
        api_key=SecretStr("server-secret"),
        model_id="gemini-embedding-2",
        dimensions=768,
        transport=httpx.MockTransport(handler),
    )
    result = await generator.embed_query("What did FDA say about process validation?")

    assert captured["key"] == "server-secret"
    assert captured["url"].endswith("/models/gemini-embedding-2:embedContent")
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["output_dimensionality"] == 768
    assert body["content"]["parts"][0]["text"].startswith(
        "task: question answering | query:"
    )
    assert result.values == [0.5] * 768
    assert result.model_id == "gemini-embedding-2"
    assert len(result.provider_input_sha256) == 64


@pytest.mark.asyncio
async def test_gemini_embedding_rejects_invalid_provider_vector() -> None:
    generator = GeminiEmbeddingGenerator(
        api_key=SecretStr("server-secret"),
        dimensions=768,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"embedding": {"values": [1.0]}})
        ),
    )

    with pytest.raises(EmbeddingGenerationError, match="invalid dimensions"):
        await generator.embed_document("FDA source text", title="Example letter")


def test_cosine_similarity_is_safe_for_mismatched_and_zero_vectors() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0], [1.0, 0.0]) == 0.0
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0
