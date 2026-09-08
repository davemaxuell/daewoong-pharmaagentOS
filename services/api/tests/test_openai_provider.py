from __future__ import annotations

import json

import httpx
import pytest
from pydantic import ValidationError

from app.ai import (
    AiGenerationError,
    GroundedPassage,
    build_ai_generator,
    build_document_ai_generator,
)
from app.config import Settings
from app.openai_provider import OpenAIDocumentGenerator, OpenAIGenerator
from app.routes.admin import runtime_configuration


def settings(**overrides):
    return Settings(
        _env_file=None,
        app_env="test",
        llm_provider="openai",
        openai_api_key="test-openai-secret",
        **overrides,
    )


def completed(text):
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
    }


def stream(text, *, finish=True, final=None):
    events = [
        {"type": "response.reasoning_summary_text.delta", "delta": "private reasoning"},
        {"type": "response.output_text.delta", "delta": text},
    ]
    if finish:
        events.append({"type": "response.completed", "response": completed(final or text)})
    return httpx.Response(200, text="".join(f"data: {json.dumps(e)}\n\n" for e in events))


def test_openai_requires_key_and_uses_provider_defaults():
    with pytest.raises(ValidationError, match="OPENAI_API_KEY"):
        Settings(_env_file=None, llm_provider="openai", openai_api_key=None)
    config = settings()
    assert config.llm_model_id == config.document_ai_model_id == "gpt-5-mini"
    assert config.chat_model_id("deep") == "gpt-5-mini"
    assert config.document_ai_fallback_model_ids == []
    assert config.document_translation_fallback_model_ids == []
    assert "test-openai-secret" not in repr(config)
    assert isinstance(build_ai_generator(config), OpenAIGenerator)
    assert isinstance(build_document_ai_generator(config), OpenAIDocumentGenerator)
    assert settings(llm_model_id="gpt-5-mini-2025-08-07").llm_model_id.endswith("2025-08-07")


async def test_runtime_reports_openai_without_exposing_secret():
    runtime = await runtime_configuration(_principal=None, settings=settings())
    assert runtime.ai_provider == "openai" and runtime.ai_configured
    assert "test-openai-secret" not in runtime.model_dump_json()


async def test_openai_validated_stream_uses_only_official_transport():
    def handler(request):
        assert str(request.url) == "https://api.openai.com/v1/responses"
        assert request.headers["authorization"] == "Bearer test-openai-secret"
        assert "x-goog-api-key" not in request.headers
        body = json.loads(request.content)
        assert body["store"] is False and body["stream"] is True
        assert body["reasoning"]["effort"] == "low"
        return stream("The supplied evidence describes a quality review [1].")

    generator = OpenAIGenerator(settings(), transport=httpx.MockTransport(handler))
    clone = generator.with_model("gpt-5-mini", thinking_level="low")
    assert generator.thinking_level == "minimal"
    answer = await clone.generate_grounded_answer(
        question="What does the evidence describe?",
        language="en",
        passages=[GroundedPassage(1, "Example", "p1", "A quality review.")],
        conversation_history=[],
    )
    assert answer.endswith("[1].") and "private reasoning" not in answer


async def test_invalid_citations_are_reset_and_never_completed():
    calls = []

    def handler(request):
        calls.append(request)
        return stream("Unsupported claim [99].")

    generator = OpenAIGenerator(settings(), transport=httpx.MockTransport(handler))
    events = []
    with pytest.raises(AiGenerationError, match="citation validation"):
        async for event in generator.stream_grounded_answer(
            question="Summarize",
            language="en",
            conversation_history=[],
            passages=[GroundedPassage(1, "Example", "p1", "Quality review")],
        ):
            events.append(event)
    assert len(calls) == 2
    assert sum(e.kind == "reset" for e in events) == 2
    assert all(e.kind != "complete" for e in events)


@pytest.mark.parametrize(
    "response", [stream("Partial", finish=False), stream("Partial", final="Different")]
)
async def test_partial_or_mismatched_stream_is_discarded(response):
    generator = OpenAIGenerator(settings(), transport=httpx.MockTransport(lambda _: response))
    events = []
    with pytest.raises(AiGenerationError):
        async for event in generator.stream_conversational_answer(
            question="Explain quality",
            language="en",
            conversation_history=[],
        ):
            events.append(event)
    assert [e.kind for e in events] == ["delta", "reset"]


async def test_korean_language_retry_retains_validation():
    responses = iter([stream("English draft"), stream("품질 검토에 대한 설명입니다.")])
    generator = OpenAIGenerator(
        settings(),
        transport=httpx.MockTransport(lambda _: next(responses)),
    )
    answer = await generator.generate_conversational_answer(
        question="품질 검토란?",
        language="ko",
        conversation_history=[],
    )
    assert answer == "품질 검토에 대한 설명입니다."


@pytest.mark.parametrize("status", [302, 401, 429, 500])
async def test_errors_do_not_expose_key_or_provider_body(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            text="test-openai-secret provider internal details",
            headers={"location": "https://example.org"},
        )

    generator = OpenAIGenerator(settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(AiGenerationError) as error:
        await generator.generate_conversational_answer(
            question="Quality?",
            language="en",
            conversation_history=[],
        )
    assert "test-openai-secret" not in str(error.value)
    assert "internal details" not in str(error.value)
    assert len(calls) == 1


async def test_scope_uses_strict_schema_and_validates_enum():
    def handler(request):
        body = json.loads(request.content)
        schema = body["text"]["format"]["schema"]
        assert schema["additionalProperties"] is False
        assert schema["required"] == ["decision"]
        return httpx.Response(200, json=completed('{"decision":"in_scope"}'))

    generator = OpenAIGenerator(settings(), transport=httpx.MockTransport(handler))
    assert (
        await generator.classify_question_scope(
            question="FDA quality systems?",
            conversation_history=[],
        )
        == "in_scope"
    )


@pytest.mark.parametrize("status", ["incomplete", "failed"])
async def test_noncompleted_response_is_rejected(status):
    generator = OpenAIGenerator(
        settings(),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"status": status, "output": []}),
        ),
    )
    with pytest.raises(AiGenerationError, match="did not complete"):
        await generator.classify_question_scope(question="Quality?", conversation_history=[])


async def test_document_transport_retries_and_converts_nested_schema():
    calls = []

    def handler(request):
        calls.append(request)
        body = json.loads(request.content)
        schema = body["text"]["format"]["schema"]
        assert schema["properties"]["result"]["additionalProperties"] is False
        assert schema["properties"]["result"]["required"] == ["text"]
        assert body["store"] is False
        if len(calls) == 1:
            return httpx.Response(429)
        return httpx.Response(200, json=completed('{"result":{"text":"review"}}'))

    generator = OpenAIDocumentGenerator(
        settings(document_ai_rate_limit_backoff_seconds=0),
        transport=httpx.MockTransport(handler),
    )
    result = await generator._generate_structured(
        system_instruction="Use supplied source only",
        task="Summarize",
        payload={},
        response_schema={
            "type": "OBJECT",
            "properties": {
                "result": {
                    "type": "OBJECT",
                    "properties": {"text": {"type": "STRING"}},
                }
            },
        },
    )
    assert result == {"result": {"text": "review"}} and len(calls) == 2
