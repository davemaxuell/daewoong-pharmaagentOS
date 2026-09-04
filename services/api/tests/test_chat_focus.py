from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.models import ChatMessage


def _create_thread(client: TestClient, headers: dict[str, str]) -> dict[str, object]:
    response = client.post(
        "/api/v1/chat/threads",
        headers=headers,
        json={"title": f"문서 포커스 {uuid4()}"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_cited_answer(
    client: TestClient,
    headers: dict[str, str],
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    letter_page = client.get("/api/v1/letters", headers=headers)
    assert letter_page.status_code == 200, letter_page.text
    letter = letter_page.json()["items"][0]
    thread = _create_thread(client, headers)
    response = client.post(
        "/api/v1/rag/query",
        headers=headers,
        json={
            "thread_id": thread["id"],
            "client_message_id": f"focus-source-{uuid4()}",
            "question": "이 경고장의 공정 밸리데이션 지적 사항은 무엇인가요?",
            "filters": {"letter_id": letter["id"]},
            "retrieval_mode": "letter",
            "language": "ko",
        },
    )
    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["assistant_message_id"]
    assert answer["citations"]
    assert all(item["document_version_id"] for item in answer["citations"])
    return thread, answer, answer["citations"][0]


def _focus_payload(answer: dict[str, object], citation: dict[str, object]) -> dict[str, object]:
    return {
        "assistant_message_id": answer["assistant_message_id"],
        "chunk_id": citation["chunk_id"],
    }


def test_focus_resolves_and_persists_exact_server_side_provenance(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    thread, answer, citation = _create_cited_answer(client, viewer_headers)

    response = client.put(
        f"/api/v1/chat/threads/{thread['id']}/focus",
        headers=viewer_headers,
        json=_focus_payload(answer, citation),
    )

    assert response.status_code == 200, response.text
    focused = response.json()
    provenance = focused["focus"]
    assert focused["retrieval_preference"] == "letter"
    assert focused["active_letter_ids"] == [citation["warning_letter_id"]]
    assert provenance["warning_letter_id"] == citation["warning_letter_id"]
    assert provenance["source_chunk_id"] == citation["chunk_id"]
    assert provenance["source_message_id"] == answer["assistant_message_id"]
    assert provenance["document_id"]
    assert provenance["document_version_id"]
    assert provenance["selected_at"]

    persisted = client.get(
        f"/api/v1/chat/threads/{thread['id']}", headers=viewer_headers
    )
    assert persisted.status_code == 200, persisted.text
    assert persisted.json()["focus"] == provenance

    repeated = client.put(
        f"/api/v1/chat/threads/{thread['id']}/focus",
        headers=viewer_headers,
        json=_focus_payload(answer, citation),
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["focus"] == provenance

    listed = client.get("/api/v1/chat/threads", headers=viewer_headers)
    assert listed.status_code == 200, listed.text
    listed_thread = next(
        item for item in listed.json()["items"] if item["id"] == thread["id"]
    )
    assert listed_thread["focus"] == provenance


def test_clear_focus_removes_scope_atomically(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    thread, answer, citation = _create_cited_answer(client, viewer_headers)
    focused = client.put(
        f"/api/v1/chat/threads/{thread['id']}/focus",
        headers=viewer_headers,
        json=_focus_payload(answer, citation),
    )
    assert focused.status_code == 200, focused.text

    cleared = client.delete(
        f"/api/v1/chat/threads/{thread['id']}/focus", headers=viewer_headers
    )

    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["focus"] is None
    assert cleared.json()["active_letter_ids"] == []
    assert cleared.json()["retrieval_preference"] == "auto"


def test_cancel_pending_message_is_owned_durable_and_idempotent(
    client: TestClient,
    viewer_headers: dict[str, str],
    reviewer_headers: dict[str, str],
) -> None:
    thread = _create_thread(client, viewer_headers)
    client_message_id = f"cancel-{uuid4()}"

    async def create_pending_turn() -> None:
        async with client.app.state.database.session_factory() as session:
            user = ChatMessage(
                thread_id=thread["id"],
                sequence=1,
                role="user",
                content="이 요청을 중지해 주세요.",
                status="completed",
                client_message_id=client_message_id,
            )
            session.add(user)
            await session.flush()
            session.add(
                ChatMessage(
                    thread_id=thread["id"],
                    sequence=2,
                    role="assistant",
                    content="답변을 준비하고 있습니다.",
                    status="pending",
                    in_reply_to_id=user.id,
                    route_metadata={"processing_attempt_id": str(uuid4())},
                )
            )
            await session.commit()

    asyncio.run(create_pending_turn())
    url = f"/api/v1/chat/threads/{thread['id']}/messages/{client_message_id}/cancel"
    assert client.post(url, headers=reviewer_headers).status_code == 404

    cancelled = client.post(url, headers=viewer_headers)
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["route_metadata"]["failure_code"] == "user_cancelled"
    assert cancelled.json()["route_metadata"]["cancelled_at"]

    repeated = client.post(url, headers=viewer_headers)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json() == cancelled.json()

    persisted = client.get(
        f"/api/v1/chat/threads/{thread['id']}", headers=viewer_headers
    )
    assistant = next(
        message for message in persisted.json()["messages"] if message["role"] == "assistant"
    )
    assert assistant["status"] == "cancelled"


def test_focused_follow_up_uses_the_persisted_exact_document_version(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    thread, answer, citation = _create_cited_answer(client, viewer_headers)
    focused = client.put(
        f"/api/v1/chat/threads/{thread['id']}/focus",
        headers=viewer_headers,
        json=_focus_payload(answer, citation),
    )
    assert focused.status_code == 200, focused.text
    focus = focused.json()["focus"]

    follow_up_client_message_id = f"focused-follow-up-{uuid4()}"
    follow_up = client.post(
        "/api/v1/rag/query",
        headers=viewer_headers,
        json={
            "thread_id": thread["id"],
            "client_message_id": follow_up_client_message_id,
            "question": "그 문서에서 FDA가 요구한 조치를 원문 근거와 함께 알려주세요.",
            "retrieval_mode": "auto",
            "language": "ko",
        },
    )
    assert follow_up.status_code == 200, follow_up.text
    body = follow_up.json()
    assert body["citations"]
    assert body["focused_document_version_id"] == focus["document_version_id"]
    assert {
        item["warning_letter_id"] for item in body["citations"]
    } == {focus["warning_letter_id"]}

    repeated = client.post(
        "/api/v1/rag/query",
        headers=viewer_headers,
        json={
            "thread_id": thread["id"],
            "client_message_id": follow_up_client_message_id,
            "question": "그 문서에서 FDA가 요구한 조치를 원문 근거와 함께 알려주세요.",
            "retrieval_mode": "auto",
            "language": "ko",
        },
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["focused_document_version_id"] == focus["document_version_id"]

    persisted = client.get(
        f"/api/v1/chat/threads/{thread['id']}", headers=viewer_headers
    )
    assert persisted.status_code == 200, persisted.text
    assistant = next(
        message
        for message in persisted.json()["messages"]
        if message["id"] == body["assistant_message_id"]
    )
    assert (
        assistant["route_metadata"]["focused_document_version_id"]
        == focus["document_version_id"]
    )


@pytest.mark.parametrize("preference", ["corpus", "none"])
def test_switching_to_unscoped_retrieval_clears_stale_focus_atomically(
    preference: str,
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    thread, answer, citation = _create_cited_answer(client, viewer_headers)
    focused = client.put(
        f"/api/v1/chat/threads/{thread['id']}/focus",
        headers=viewer_headers,
        json=_focus_payload(answer, citation),
    )
    assert focused.status_code == 200, focused.text

    patched = client.patch(
        f"/api/v1/chat/threads/{thread['id']}",
        headers=viewer_headers,
        json={"retrieval_preference": preference},
    )

    assert patched.status_code == 200, patched.text
    assert patched.json()["retrieval_preference"] == preference
    assert patched.json()["focus"] is None
    assert patched.json()["active_letter_ids"] == []


def test_focus_rejects_cross_thread_cross_owner_and_uncited_chunk_ids(
    client: TestClient,
    viewer_headers: dict[str, str],
    reviewer_headers: dict[str, str],
) -> None:
    thread, answer, citation = _create_cited_answer(client, viewer_headers)
    other_thread = _create_thread(client, viewer_headers)
    payload = _focus_payload(answer, citation)

    assert (
        client.put(
            f"/api/v1/chat/threads/{thread['id']}/focus",
            headers=reviewer_headers,
            json=payload,
        ).status_code
        == 404
    )
    assert (
        client.put(
            f"/api/v1/chat/threads/{other_thread['id']}/focus",
            headers=viewer_headers,
            json=payload,
        ).status_code
        == 404
    )
    uncited = client.put(
        f"/api/v1/chat/threads/{thread['id']}/focus",
        headers=viewer_headers,
        json={
            "assistant_message_id": answer["assistant_message_id"],
            "chunk_id": str(uuid4()),
        },
    )
    assert uncited.status_code == 404


def test_archived_thread_cannot_gain_or_clear_focus(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    thread, answer, citation = _create_cited_answer(client, viewer_headers)
    archived = client.delete(
        f"/api/v1/chat/threads/{thread['id']}", headers=viewer_headers
    )
    assert archived.status_code == 204

    focus = client.put(
        f"/api/v1/chat/threads/{thread['id']}/focus",
        headers=viewer_headers,
        json=_focus_payload(answer, citation),
    )
    clear = client.delete(
        f"/api/v1/chat/threads/{thread['id']}/focus", headers=viewer_headers
    )
    patch = client.patch(
        f"/api/v1/chat/threads/{thread['id']}",
        headers=viewer_headers,
        json={"retrieval_preference": "corpus"},
    )
    assert focus.status_code == 409
    assert clear.status_code == 409
    assert patch.status_code == 409


def test_active_letter_scope_rejects_unknown_ids_but_unscoped_modes_discard_them(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    unavailable_id = str(uuid4())
    rejected = client.post(
        "/api/v1/chat/threads",
        headers=viewer_headers,
        json={
            "title": "잘못된 범위",
            "retrieval_preference": "letter",
            "active_letter_ids": [unavailable_id],
        },
    )
    assert rejected.status_code == 422

    discarded = client.post(
        "/api/v1/chat/threads",
        headers=viewer_headers,
        json={
            "title": "전체 코퍼스",
            "retrieval_preference": "corpus",
            "active_letter_ids": [unavailable_id],
        },
    )
    assert discarded.status_code == 201, discarded.text
    assert discarded.json()["active_letter_ids"] == []
    assert discarded.json()["focus"] is None
