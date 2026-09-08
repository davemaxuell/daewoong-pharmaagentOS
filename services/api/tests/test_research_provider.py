import json

import httpx
import pytest

from app.ai import AiGenerationError
from app.research.provider import INSTRUCTIONS, OpenAIResearchModel


@pytest.mark.asyncio
async def test_native_tool_calls_are_strict_bounded_and_not_stored(settings):
    configured = settings.model_copy(update={"openai_api_key": "unused"})
    # Revalidate the secret field rather than passing a raw string to the adapter.
    from pydantic import SecretStr

    configured.openai_api_key = SecretStr("fixture-key")
    configured.llm_model_id = "gpt-5-mini"
    seen = []

    def transport(request):
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "usage": {"total_tokens": 120},
                "output": [
                    {
                        "type": "reasoning",
                        "id": "r1",
                        "summary": [],
                        "encrypted_content": "opaque-test",
                    },
                    {
                        "type": "function_call",
                        "call_id": "call1",
                        "name": "plan_research",
                        "arguments": json.dumps({"steps": ["Search sources", "Check evidence"]}),
                    },
                ],
            },
        )

    model = OpenAIResearchModel(configured, transport=httpx.MockTransport(transport))
    result = await model.propose([{"role": "user", "content": "FDA validation brief"}], 11)
    assert result.name == "plan_research" and result.tokens == 120
    assert result.output[0]["encrypted_content"] == "opaque-test"
    assert seen[0]["store"] is False
    assert seen[0]["parallel_tool_calls"] is False
    assert seen[0]["tool_choice"] == "required"
    assert seen[0]["model"] == "gpt-5-mini"
    assert all(tool["strict"] for tool in seen[0]["tools"])
    assert "untrusted DATA" in INSTRUCTIONS
    assert seen[0]["max_output_tokens"] == 4_000


@pytest.mark.asyncio
async def test_model_errors_do_not_expose_provider_payloads(settings):
    from pydantic import SecretStr

    settings.openai_api_key = SecretStr("fixture-key")
    model = OpenAIResearchModel(
        settings,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(429, json={"error": "private-provider-payload"})
        ),
    )
    with pytest.raises(AiGenerationError) as error:
        await model.propose([], 5)
    assert "private-provider-payload" not in str(error.value)
    assert "fixture-key" not in str(error.value)


@pytest.mark.asyncio
async def test_incomplete_response_cannot_be_used_as_a_tool_action(settings):
    from pydantic import SecretStr

    settings.openai_api_key = SecretStr("fixture-key")
    model = OpenAIResearchModel(
        settings,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"status": "incomplete", "output": []})
        ),
    )
    with pytest.raises(AiGenerationError):
        await model.propose([], 5)


@pytest.mark.asyncio
async def test_evidence_check_receives_readable_korean_and_bounds_feedback(settings):
    from pydantic import SecretStr

    settings.openai_api_key = SecretStr("fixture-key")

    def transport(request):
        body = json.loads(request.content)
        assert "세척 밸리데이션" in body["input"]
        assert "\\u" not in body["input"]
        assert body["text"]["format"]["schema"]["properties"]["issues"]["items"]["maxLength"] == 500
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "usage": {"total_tokens": 100},
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": '{"supported":true,"issues":[]}'}
                        ],
                    }
                ],
            },
        )

    model = OpenAIResearchModel(settings, transport=httpx.MockTransport(transport))
    checked, tokens = await model.verify({"title": "세척 밸리데이션"}, [], "ko")
    assert checked.supported and tokens == 100
