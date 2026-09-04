from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

from fastapi.testclient import TestClient

from app.ai import AiGenerationError, AiStreamEvent
from app.routes.intelligence import _generate_ai_with_fallback


def _ndjson(response: Any) -> list[dict[str, Any]]:
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def _create_thread(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = client.post(
        "/api/v1/chat/threads",
        headers=headers,
        json={"title": "Streaming contract test"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_stream_complete_uses_exact_json_response_contract(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    payload = {
        "question": "What can this service do?",
        "language": "en",
        "retrieval_mode": "none",
    }
    json_response = client.post("/api/v1/rag/query", headers=viewer_headers, json=payload)
    stream_response = client.post(
        "/api/v1/rag/query/stream",
        headers=viewer_headers,
        json=payload,
    )

    assert json_response.status_code == stream_response.status_code == 200
    assert (
        stream_response.headers["content-type"]
        == "application/x-ndjson; charset=utf-8"
    )
    events = _ndjson(stream_response)
    assert events[0] == {"type": "phase", "phase": "retrieving"}
    assert events[-1]["type"] == "complete"
    complete = events[-1]["data"]
    assert complete.keys() == json_response.json().keys()
    for stable_field in (
        "answer",
        "interpretation_label",
        "scope_label",
        "filters_applied",
        "evidence_sufficiency",
        "citations",
        "notice",
        "retrieval_strategy",
        "route_reason",
        "requested_model_profile",
        "effective_model_profile",
        "generation_used",
        "attempted_model_id",
        "effective_model_id",
        "focused_document_version_id",
    ):
        assert complete[stable_field] == json_response.json()[stable_field]


def test_stream_retries_with_reset_before_authoritative_complete(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    class RetryingGenerator:
        provider = "test-provider"
        model_id = "test-stream-model"
        prompt_version = "test-stream-prompt"

        async def stream_grounded_answer(self, **_kwargs: object):
            yield AiStreamEvent(kind="delta", attempt=1, text="Unsupported draft [99].")
            yield AiStreamEvent(kind="validating", attempt=1)
            yield AiStreamEvent(kind="reset", attempt=1)
            yield AiStreamEvent(kind="delta", attempt=2, text="Validated FDA answer [1].")
            yield AiStreamEvent(kind="validating", attempt=2)
            yield AiStreamEvent(kind="complete", attempt=2, text="Validated FDA answer [1].")

    previous = client.app.state.ai_generator
    client.app.state.ai_generator = RetryingGenerator()
    try:
        response = client.post(
            "/api/v1/rag/query/stream",
            headers=viewer_headers,
            json={"question": "process validation", "language": "en"},
        )
    finally:
        client.app.state.ai_generator = previous

    assert response.status_code == 200
    events = _ndjson(response)
    event_types = [event["type"] for event in events]
    assert event_types == [
        "phase",
        "phase",
        "draft_delta",
        "phase",
        "draft_reset",
        "draft_delta",
        "phase",
        "complete",
    ]
    assert events[2] == {
        "type": "draft_delta",
        "attempt": 1,
        "text": "Unsupported draft [99].",
    }
    assert events[4] == {"type": "draft_reset", "attempt": 1}
    assert events[-1]["data"]["answer"] == "Validated FDA answer [1]."


def test_stream_model_fallback_resets_exhausted_model_draft() -> None:
    class ExhaustedGenerator:
        provider = "test-provider"
        model_id = "deep-model"
        prompt_version = "test-prompt"

        async def stream_conversational_answer(self, **_kwargs: object):
            yield AiStreamEvent(kind="delta", attempt=1, text="discard this")
            raise AiGenerationError("provider status 429")

    class WorkingGenerator:
        provider = "test-provider"
        model_id = "balanced-model"
        prompt_version = "test-prompt"

        async def stream_conversational_answer(self, **_kwargs: object):
            yield AiStreamEvent(kind="delta", attempt=1, text="verified answer")
            yield AiStreamEvent(kind="validating", attempt=1)
            yield AiStreamEvent(kind="complete", attempt=1, text="verified answer")

    emitted: list[dict[str, object]] = []

    async def run() -> tuple[str, object, tuple[str, ...]]:
        async def emit(event: dict[str, object]) -> None:
            emitted.append(event)

        return await _generate_ai_with_fallback(
            [ExhaustedGenerator(), WorkingGenerator()],  # type: ignore[list-item]
            method_name="stream_conversational_answer",
            arguments={
                "question": "What is an FDA Drug warning letter?",
                "language": "en",
                "conversation_history": [],
            },
            stream_emitter=emit,
        )

    answer, effective_generator, attempted = asyncio.run(run())

    assert answer == "verified answer"
    assert effective_generator.model_id == "balanced-model"
    assert attempted == ("deep-model", "balanced-model")
    assert {"type": "draft_reset", "attempt": 2} in emitted
    reset_index = emitted.index({"type": "draft_reset", "attempt": 2})
    assert emitted[reset_index - 1]["text"] == "discard this"
    assert emitted[reset_index + 1] == {"type": "phase", "phase": "generating"}


def test_stream_cancel_never_emits_complete_and_does_not_persist_partial_text(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    provider_started = threading.Event()
    allow_provider_to_finish = threading.Event()

    class BlockingGenerator:
        provider = "test-provider"
        model_id = "test-blocking-model"
        prompt_version = "test-blocking-prompt"

        async def stream_grounded_answer(self, **_kwargs: object):
            yield AiStreamEvent(kind="delta", attempt=1, text="PROVISIONAL-NOT-PERSISTED")
            provider_started.set()
            while not allow_provider_to_finish.is_set():
                await asyncio.sleep(0.01)
            yield AiStreamEvent(kind="validating", attempt=1)
            yield AiStreamEvent(kind="complete", attempt=1, text="Final answer [1].")

    letter = client.get("/api/v1/letters", headers=viewer_headers).json()["items"][0]
    thread = _create_thread(client, viewer_headers)
    client_message_id = "cancel-stream-attempt"
    payload = {
        "thread_id": thread["id"],
        "client_message_id": client_message_id,
        "question": "What did this letter say about process validation?",
        "language": "en",
        "filters": {"letter_id": letter["id"]},
    }
    captured: dict[str, Any] = {}

    def send_stream() -> None:
        captured["response"] = client.post(
            "/api/v1/rag/query/stream",
            headers=viewer_headers,
            json=payload,
        )

    previous = client.app.state.ai_generator
    client.app.state.ai_generator = BlockingGenerator()
    request_thread = threading.Thread(target=send_stream)
    try:
        request_thread.start()
        assert provider_started.wait(timeout=5)
        cancelled = client.post(
            f"/api/v1/chat/threads/{thread['id']}/messages/{client_message_id}/cancel",
            headers=viewer_headers,
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "cancelled"
        allow_provider_to_finish.set()
        request_thread.join(timeout=5)
        assert not request_thread.is_alive()
    finally:
        allow_provider_to_finish.set()
        request_thread.join(timeout=5)
        client.app.state.ai_generator = previous

    events = _ndjson(captured["response"])
    assert any(event["type"] == "draft_delta" for event in events)
    assert events[-1]["type"] == "error"
    assert events[-1]["code"] == "cancelled_or_superseded"
    assert not any(event["type"] == "complete" for event in events)
    detail = client.get(
        f"/api/v1/chat/threads/{thread['id']}",
        headers=viewer_headers,
    ).json()
    assistant = detail["messages"][1]
    assert assistant["status"] == "cancelled"
    assert "PROVISIONAL-NOT-PERSISTED" not in assistant["content"]
