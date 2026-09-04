from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, event, func, select

from app.ai import AiGenerationError, ConversationTurn, GeminiGenerator, GroundedPassage
from app.config import Settings
from app.database import Database
from app.models import ChatMessage, DocumentChunk, WarningLetter
from app.rag_planner import choose_model_profile, plan_rag
from app.routes.intelligence import _company_name_matches_question, _effective_language


@pytest.mark.parametrize(
    ("requested_language", "question", "expected"),
    [
        ("auto", "What findings did FDA identify for 대웅바이오?", "en"),
        ("auto", "Sun Pharma의 주요 지적 사항은 무엇인가요?", "ko"),
        ("auto", "FDA 경고서한이란 무엇인가요?", "ko"),
        ("auto", "What is an FDA warning letter?", "en"),
        ("ko", "What is an FDA warning letter?", "ko"),
        ("en", "FDA 경고서한이란 무엇인가요?", "en"),
    ],
)
def test_effective_language_follows_question_unless_explicitly_overridden(
    requested_language: str,
    question: str,
    expected: str,
) -> None:
    assert _effective_language(requested_language, question) == expected


@pytest.mark.parametrize(
    ("question", "kwargs", "strategy", "reason"),
    [
        ("안녕하세요", {}, "none", "capability_or_greeting"),
        ("최신 경고장 발행일은?", {}, "metadata", "structured_metadata_intent"),
        (
            "이 경고장의 지적 사항은?",
            {"explicit_letter_ids": ("letter-a",)},
            "letter",
            "explicit_or_resolved_letter_scope",
        ),
        (
            "두 경고장을 비교해 주세요",
            {"explicit_letter_ids": ("letter-a", "letter-b")},
            "multi_letter",
            "explicit_or_resolved_letter_scope",
        ),
        (
            "그 경고장에서 FDA가 무엇을 요청했나요?",
            {"thread_active_letter_ids": ("letter-a",)},
            "letter",
            "follow_up_inherited_scope",
        ),
        ("전체 경고장의 공통 추세는?", {}, "corpus", "broad_corpus_analysis"),
        (
            "우리 워크플로에도 같은 문제가 있나요?",
            {"thread_active_letter_ids": ("letter-a",)},
            "letter",
            "internal_comparison_inherited_scope",
        ),
        (
            "우리 워크플로에도 같은 문제가 있나요?",
            {},
            "none",
            "internal_comparison_requires_letter_scope",
        ),
    ],
)
def test_planner_matrix(
    question: str,
    kwargs: dict[str, tuple[str, ...]],
    strategy: str,
    reason: str,
) -> None:
    plan = plan_rag(question=question, **kwargs)
    assert plan.retrieval_strategy == strategy
    assert plan.route_reason == reason


def test_model_profile_auto_matrix() -> None:
    letter = plan_rag(question="finding", explicit_letter_ids=("letter-a",))
    corpus = plan_rag(question="overall warning-letter trend")
    multi = plan_rag(
        question="compare warning letters",
        explicit_letter_ids=("letter-a", "letter-b"),
    )
    comparison = plan_rag(question="우리 workflow와 비교", thread_active_letter_ids=("letter-a",))
    assert choose_model_profile("auto", letter) == "fast"
    assert choose_model_profile("auto", corpus) == "balanced"
    assert choose_model_profile("auto", multi) == "balanced"
    assert choose_model_profile("auto", comparison) == "deep"
    assert choose_model_profile("fast", comparison) == "fast"


def test_planner_uses_model_only_for_general_conversation() -> None:
    automatic = plan_rag(question="FDA 경고서한이란 무엇인가요?")
    manual = plan_rag(
        question="경고서한의 목적을 쉽게 설명해 주세요",
        requested_mode="none",
    )

    assert automatic.retrieval_strategy == "none"
    assert automatic.route_reason == "general_conversation_no_retrieval"
    assert automatic.deterministic_response is None
    assert manual.retrieval_strategy == "none"
    assert manual.route_reason == "user_requested_no_retrieval"
    assert manual.deterministic_response is None


def test_planner_still_routes_evidence_intent_to_corpus() -> None:
    plan = plan_rag(question="FDA 공정 밸리데이션 지적 근거를 찾아주세요")

    assert plan.retrieval_strategy == "corpus"
    assert plan.route_reason == "evidence_search_intent"


@pytest.mark.parametrize(
    ("question", "kwargs", "reason"),
    [
        (
            "What went wrong at Example OTC Products?",
            {"resolved_letter_ids": ("letter-a",)},
            "explicit_or_resolved_letter_scope",
        ),
        (
            "What were the main problems?",
            {"explicit_letter_ids": ("letter-a",)},
            "explicit_or_resolved_letter_scope",
        ),
        (
            "What happened there?",
            {"thread_active_letter_ids": ("letter-a",)},
            "follow_up_inherited_scope",
        ),
    ],
)
def test_planner_accepts_natural_questions_when_letter_context_establishes_the_domain(
    question: str,
    kwargs: dict[str, tuple[str, ...]],
    reason: str,
) -> None:
    plan = plan_rag(question=question, **kwargs)

    assert plan.retrieval_strategy == "letter"
    assert plan.route_reason == reason
    assert plan.deterministic_response is None


def test_semantic_domain_signal_allows_keyword_free_pharma_conversation() -> None:
    plan = plan_rag(
        question="Why would that matter?",
        semantic_domain_relevant=True,
    )

    assert plan.retrieval_strategy == "none"
    assert plan.route_reason == "general_conversation_no_retrieval"
    assert plan.deterministic_response is None


def test_company_context_cannot_bypass_a_clearly_unrelated_profile_request() -> None:
    plan = plan_rag(
        question="Who is the CEO of Example OTC Products?",
        resolved_letter_ids=("letter-a",),
    )

    assert plan.retrieval_strategy == "none"
    assert plan.route_reason == "out_of_scope_request"
    assert plan.deterministic_response == "out_of_scope"


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"requested_mode": "corpus"},
        {"requested_mode": "letter", "explicit_letter_ids": ("letter-a",)},
        {"thread_active_letter_ids": ("letter-a",)},
    ],
)
def test_planner_refuses_unrelated_questions_even_with_retrieval_or_letter_scope(
    kwargs: dict[str, object],
) -> None:
    plan = plan_rag(question="How do I bake sourdough bread?", **kwargs)

    assert plan.retrieval_strategy == "none"
    assert plan.route_reason == "out_of_scope_request"
    assert plan.deterministic_response == "out_of_scope"


@pytest.mark.parametrize(
    "question",
    [
        "Summarize the history of the Roman Empire.",
        "Tell me more about sourdough starters.",
        "프랑스 혁명을 요약해 주세요.",
    ],
)
def test_selected_letter_does_not_turn_new_subject_into_referential_followup(
    question: str,
) -> None:
    plan = plan_rag(question=question, thread_active_letter_ids=("letter-a",))

    assert plan.route_reason == "out_of_scope_request"
    assert plan.deterministic_response == "out_of_scope"


def test_explicit_letter_filter_fails_closed_when_corpus_mode_is_also_requested() -> None:
    plan = plan_rag(
        question="전체 코퍼스와 비교해 주세요",
        requested_mode="corpus",
        explicit_letter_ids=("letter-a",),
        resolved_letter_ids=("letter-b",),
    )

    assert plan.retrieval_strategy == "letter"
    assert plan.letter_ids == ("letter-a",)
    assert plan.route_reason == "explicit_letter_scope_overrides_corpus"


def test_current_request_corpus_mode_can_broaden_a_name_resolved_scope() -> None:
    plan = plan_rag(
        question="이 회사와 전체 코퍼스의 공통 추세를 비교해 주세요",
        requested_mode="corpus",
        resolved_letter_ids=("letter-a",),
    )

    assert plan.retrieval_strategy == "corpus"
    assert plan.letter_ids == ()
    assert plan.route_reason == "user_requested_corpus"


@pytest.mark.parametrize(
    ("company_name", "question", "expected"),
    [
        (
            "Tianjin Kilo Pharmaceutical Sci-tech Co., Ltd.",
            "Tianjin Kilo 경고서한의 주요 지적 사항을 알려 주세요",
            True,
        ),
        (
            "Tianjin Kilo Pharmaceutical Sci-tech Co., Ltd.",
            "Tianjin-Kilo Pharmaceutical Sci tech Co Ltd 원문을 찾아 주세요",
            True,
        ),
        (
            "Tianjin Kilo Pharmaceutical Sci-tech Co., Ltd.",
            "Tianjin 경고서한의 주요 지적 사항을 알려 주세요",
            False,
        ),
        (
            "Tianjin Kilo Pharmaceutical Sci-tech Co., Ltd.",
            "Pharmaceutical 경고서한을 찾아 주세요",
            False,
        ),
        ("Pfizer Inc.", "Pfizer 경고서한을 찾아 주세요", True),
    ],
)
def test_company_name_alias_matching_is_normalized_and_conservative(
    company_name: str,
    question: str,
    expected: bool,
) -> None:
    assert _company_name_matches_question(company_name, question) is expected


def _create_thread(
    client: TestClient,
    headers: dict[str, str],
    **overrides: object,
) -> dict[str, object]:
    payload: dict[str, object] = {"title": "규제 검토 대화"}
    payload.update(overrides)
    response = client.post("/api/v1/chat/threads", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_thread_crud_is_owner_scoped_and_delete_archives(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    thread = _create_thread(
        client,
        viewer_headers,
        model_preference="balanced",
        retrieval_preference="letter",
    )
    thread_id = thread["id"]
    assert thread["messages"] == []
    assert thread["model_preference"] == "balanced"

    other_headers = {"X-Dev-User": "other.user", "X-Dev-Roles": "viewer"}
    assert client.get(f"/api/v1/chat/threads/{thread_id}", headers=other_headers).status_code == 404
    assert (
        client.patch(
            f"/api/v1/chat/threads/{thread_id}",
            headers=other_headers,
            json={"title": "stolen"},
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/v1/chat/threads/{thread_id}", headers=other_headers).status_code == 404
    )

    patched = client.patch(
        f"/api/v1/chat/threads/{thread_id}",
        headers=viewer_headers,
        json={"title": "변경된 제목", "model_preference": "deep"},
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "변경된 제목"
    assert patched.json()["model_preference"] == "deep"

    deleted = client.delete(f"/api/v1/chat/threads/{thread_id}", headers=viewer_headers)
    assert deleted.status_code == 204
    active = client.get("/api/v1/chat/threads", headers=viewer_headers).json()["items"]
    assert thread_id not in {item["id"] for item in active}
    archived = client.get(
        "/api/v1/chat/threads?include_archived=true", headers=viewer_headers
    ).json()["items"]
    assert thread_id in {item["id"] for item in archived}


def test_thread_search_matches_normalized_title(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    matching = _create_thread(client, viewer_headers, title="CAPA 검색 기록")
    nonmatching = _create_thread(client, viewer_headers, title="일반 규제 기록")

    response = client.get(
        "/api/v1/chat/threads",
        headers=viewer_headers,
        params={"q": "  capa   검색  "},
    )

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["items"]}
    assert matching["id"] in ids
    assert nonmatching["id"] not in ids


def test_thread_search_matches_persisted_message_content(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    thread = _create_thread(client, viewer_headers, title="메시지 검색 테스트")
    query = client.post(
        "/api/v1/rag/query",
        headers=viewer_headers,
        json={
            "thread_id": thread["id"],
            "client_message_id": "history-message-search-source",
            "question": "배치기록 무결성 고유검색어를 설명해 주세요",
            "language": "ko",
            "retrieval_mode": "none",
        },
    )
    assert query.status_code == 200, query.text

    response = client.get(
        "/api/v1/chat/threads",
        headers=viewer_headers,
        params={"q": "무결성 고유검색어"},
    )

    assert response.status_code == 200
    assert {item["id"] for item in response.json()["items"]} == {thread["id"]}


def test_thread_search_excludes_archived_threads_unless_requested(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    thread = _create_thread(client, viewer_headers, title="보관 검색 전용 문구")
    assert (
        client.delete(f"/api/v1/chat/threads/{thread['id']}", headers=viewer_headers).status_code
        == 204
    )

    active = client.get(
        "/api/v1/chat/threads",
        headers=viewer_headers,
        params={"q": "보관 검색 전용"},
    )
    including_archived = client.get(
        "/api/v1/chat/threads",
        headers=viewer_headers,
        params={"q": "보관 검색 전용", "include_archived": "true"},
    )

    assert active.status_code == 200
    assert thread["id"] not in {item["id"] for item in active.json()["items"]}
    assert including_archived.status_code == 200
    assert thread["id"] in {item["id"] for item in including_archived.json()["items"]}


def test_thread_search_never_leaks_another_owners_match(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    other_headers = {"X-Dev-User": "search.other.user", "X-Dev-Roles": "viewer"}
    other_thread = _create_thread(
        client,
        other_headers,
        title="교차 사용자 일반 대화",
    )
    message = client.post(
        "/api/v1/rag/query",
        headers=other_headers,
        json={
            "thread_id": other_thread["id"],
            "client_message_id": "cross-owner-search-source",
            "question": "교차 사용자 비밀 검색 문구",
            "language": "ko",
            "retrieval_mode": "none",
        },
    )
    assert message.status_code == 200, message.text

    owner_response = client.get(
        "/api/v1/chat/threads",
        headers=other_headers,
        params={"q": "비밀 검색 문구"},
    )
    viewer_response = client.get(
        "/api/v1/chat/threads",
        headers=viewer_headers,
        params={"q": "비밀 검색 문구", "include_archived": "true"},
    )

    assert owner_response.status_code == 200
    assert {item["id"] for item in owner_response.json()["items"]} == {other_thread["id"]}
    assert viewer_response.status_code == 200
    assert other_thread["id"] not in {item["id"] for item in viewer_response.json()["items"]}


@pytest.mark.parametrize(
    ("literal", "matching_title", "control_title"),
    [
        ("%", "LIKE literal % marker", "LIKE literal X marker"),
        ("_", "LIKE literal _ marker", "LIKE literal X marker"),
        ("\\", "LIKE literal \\ marker", "LIKE literal X marker"),
    ],
    ids=["percent", "underscore", "backslash"],
)
def test_thread_search_treats_sql_wildcards_as_literal_text(
    literal: str,
    matching_title: str,
    control_title: str,
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    matching = _create_thread(client, viewer_headers, title=matching_title)
    control = _create_thread(client, viewer_headers, title=control_title)

    response = client.get(
        "/api/v1/chat/threads",
        headers=viewer_headers,
        params={"q": literal},
    )

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["items"]}
    assert matching["id"] in ids
    assert control["id"] not in ids


def test_thread_search_rejects_queries_longer_than_200_characters(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    response = client.get(
        "/api/v1/chat/threads",
        headers=viewer_headers,
        params={"q": "x" * 201},
    )

    assert response.status_code == 422


def test_no_retrieval_route_never_queries_document_chunks(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    statements: list[str] = []

    def capture_sql(
        _conn: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement.casefold())

    engine = client.app.state.database.engine.sync_engine
    event.listen(engine, "before_cursor_execute", capture_sql)
    try:
        response = client.post(
            "/api/v1/rag/query",
            headers=viewer_headers,
            json={"question": "안녕하세요", "retrieval_mode": "none"},
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture_sql)
    assert response.status_code == 200
    body = response.json()
    assert body["retrieval_strategy"] == "none"
    assert body["citations"] == []
    assert body["generation_used"] is False
    assert body["attempted_model_id"] is None
    assert body["effective_model_id"] is None
    assert not any("document_chunks" in statement for statement in statements)


def test_unrelated_request_never_calls_provider_or_corpus_even_with_selected_letter(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    scoped_headers = {**viewer_headers, "X-Dev-User": "scope-boundary.user"}
    letter = client.get("/api/v1/letters", headers=scoped_headers).json()["items"][0]
    statements: list[str] = []

    class FailingIfCalledGenerator:
        provider = "test-provider"
        model_id = "must-not-run"
        prompt_version = "must-not-run"

        async def generate_conversational_answer(self, **_kwargs: object) -> str:
            raise AssertionError("out-of-scope request must not call conversational generation")

        async def generate_grounded_answer(self, **_kwargs: object) -> str:
            raise AssertionError("out-of-scope request must not call grounded generation")

    def capture_sql(
        _conn: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement.casefold())

    previous = client.app.state.ai_generator
    client.app.state.ai_generator = FailingIfCalledGenerator()
    engine = client.app.state.database.engine.sync_engine
    event.listen(engine, "before_cursor_execute", capture_sql)
    try:
        response = client.post(
            "/api/v1/rag/query",
            headers=scoped_headers,
            json={
                "question": "How do I bake sourdough bread?",
                "filters": {"letter_id": letter["id"]},
                "retrieval_mode": "corpus",
            },
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture_sql)
        client.app.state.ai_generator = previous

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["retrieval_strategy"] == "none"
    assert body["route_reason"] == "out_of_scope_request"
    assert body["generation_used"] is False
    assert body["citations"] == []
    assert not any("document_chunks" in statement for statement in statements)


def test_company_name_establishes_letter_scope_without_regulatory_keywords(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    scoped_headers = {**viewer_headers, "X-Dev-User": "natural-company-scope.user"}
    letters = client.get("/api/v1/letters", headers=scoped_headers).json()["items"]
    letter = next(item for item in letters if item["company_name"] == "Example OTC Products, LLC")

    response = client.post(
        "/api/v1/rag/query",
        headers=scoped_headers,
        json={"question": "What went wrong at Example OTC Products?"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["retrieval_strategy"] == "letter"
    assert body["route_reason"] == "explicit_or_resolved_letter_scope"
    assert body["citations"]
    assert {citation["warning_letter_id"] for citation in body["citations"]} == {letter["id"]}


def test_semantic_scope_check_uses_conversation_context_for_keyword_free_pharma_followup(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    calls: list[tuple[str, list[ConversationTurn]]] = []
    scoped_headers = {**viewer_headers, "X-Dev-User": "semantic-scope.user"}

    class ContextAwareGenerator:
        provider = "test-provider"
        model_id = "test-context-model"
        prompt_version = "test-context-prompt"

        async def classify_question_scope(
            self,
            *,
            question: str,
            conversation_history: list[ConversationTurn],
        ) -> str:
            calls.append((question, conversation_history))
            return "in_scope"

        async def generate_conversational_answer(self, **_kwargs: object) -> str:
            return "Repeated failures can indicate a systemic control weakness."

        async def generate_grounded_answer(self, **_kwargs: object) -> str:
            raise AssertionError("keyword-free conceptual follow-up must not invent retrieval")

    previous = client.app.state.ai_generator
    client.app.state.ai_generator = ContextAwareGenerator()
    try:
        response = client.post(
            "/api/v1/rag/query",
            headers=scoped_headers,
            json={
                "question": "Why would that matter?",
                "conversation_history": [
                    {
                        "role": "user",
                        "content": (
                            "We were discussing recurring production failures and systemic "
                            "control weaknesses in medicine manufacturing."
                        ),
                    }
                ],
            },
        )
    finally:
        client.app.state.ai_generator = previous

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["retrieval_strategy"] == "none"
    assert body["route_reason"] == "general_conversation_no_retrieval"
    assert body["generation_used"] is True
    assert body["answer"] == "Repeated failures can indicate a systemic control weakness."
    assert calls == [
        (
            "Why would that matter?",
            [
                ConversationTurn(
                    role="user",
                    content=(
                        "We were discussing recurring production failures and systemic control "
                        "weaknesses in medicine manufacturing."
                    ),
                )
            ],
        )
    ]


def test_model_only_route_calls_selected_ai_without_document_retrieval(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    calls: list[tuple[str, str, list[ConversationTurn]]] = []
    statements: list[str] = []

    class ConversationalGenerator:
        provider = "test-provider"
        model_id = "test-conversation-model"
        prompt_version = "test-conversation-prompt"

        async def generate_conversational_answer(
            self,
            *,
            question: str,
            language: str,
            conversation_history: list[ConversationTurn],
        ) -> str:
            calls.append((question, language, conversation_history))
            return "FDA 경고서한의 일반적인 목적을 설명하는 대화형 답변입니다."

        async def generate_grounded_answer(self, **_kwargs: object) -> str:
            raise AssertionError("model-only route must not call grounded generation")

    def capture_sql(
        _conn: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement.casefold())

    thread = _create_thread(client, viewer_headers)
    previous = client.app.state.ai_generator
    client.app.state.ai_generator = ConversationalGenerator()
    engine = client.app.state.database.engine.sync_engine
    event.listen(engine, "before_cursor_execute", capture_sql)
    try:
        response = client.post(
            "/api/v1/rag/query",
            headers=viewer_headers,
            json={
                "thread_id": thread["id"],
                "client_message_id": "model-only-general-question",
                "question": "FDA 경고서한이란 무엇인가요?",
                "language": "ko",
                "retrieval_mode": "none",
                "model_profile": "deep",
                "max_sources": 4,
            },
        )
        greeting = client.post(
            "/api/v1/rag/query",
            headers=viewer_headers,
            json={
                "thread_id": thread["id"],
                "client_message_id": "deterministic-greeting-after-model-only",
                "question": "안녕하세요",
                "language": "ko",
                "retrieval_mode": "none",
            },
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture_sql)
        client.app.state.ai_generator = previous

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["retrieval_strategy"] == "none"
    assert body["route_reason"] == "user_requested_no_retrieval"
    assert body["citations"] == []
    assert body["generation_used"] is True
    assert body["effective_model_profile"] == "deep"
    assert body["attempted_model_id"] == "test-conversation-model"
    assert body["effective_model_id"] == "test-conversation-model"
    assert calls == [("FDA 경고서한이란 무엇인가요?", "ko", [])]
    assert not any("document_chunks" in statement for statement in statements)
    assert greeting.status_code == 200
    assert greeting.json()["generation_used"] is False
    assert len(calls) == 1

    detail = client.get(f"/api/v1/chat/threads/{thread['id']}", headers=viewer_headers).json()
    user_message, assistant_message = detail["messages"][:2]
    snapshot = user_message["route_metadata"]["request_snapshot"]
    assert snapshot["filters"]["letter_id"] is None
    assert snapshot["filters"]["company"] is None
    assert snapshot["language"] == "ko"
    assert snapshot["max_sources"] == 4
    assert snapshot["retrieval_mode"] == "none"
    assert snapshot["model_profile"] == "deep"
    assert assistant_message["model_metadata"]["generation_used"] is True


def test_auto_language_sends_each_questions_detected_language_to_generation(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    calls: list[tuple[str, str]] = []
    language_headers = {**viewer_headers, "X-Dev-User": "auto-language.user"}

    class LanguageAwareGenerator:
        provider = "test-provider"
        model_id = "test-language-model"
        prompt_version = "test-language-prompt"

        async def generate_conversational_answer(
            self,
            *,
            question: str,
            language: str,
            conversation_history: list[ConversationTurn],
        ) -> str:
            assert conversation_history == []
            calls.append((question, language))
            return (
                "FDA 경고서한의 일반적인 목적을 설명하는 답변입니다."
                if language == "ko"
                else "This answer explains the general purpose of an FDA warning letter."
            )

        async def generate_grounded_answer(self, **_kwargs: object) -> str:
            raise AssertionError("general language checks must not use document retrieval")

    previous = client.app.state.ai_generator
    client.app.state.ai_generator = LanguageAwareGenerator()
    try:
        english = client.post(
            "/api/v1/rag/query",
            headers=language_headers,
            json={
                "question": "What is an FDA warning letter?",
                "language": "auto",
                "retrieval_mode": "none",
            },
        )
        korean = client.post(
            "/api/v1/rag/query",
            headers=language_headers,
            json={
                "question": "FDA 경고서한이란 무엇인가요?",
                "language": "auto",
                "retrieval_mode": "none",
            },
        )
    finally:
        client.app.state.ai_generator = previous

    assert english.status_code == 200, english.text
    assert korean.status_code == 200, korean.text
    assert english.json()["answer"].startswith("This answer")
    assert korean.json()["answer"].startswith("FDA 경고서한")
    assert calls == [
        ("What is an FDA warning letter?", "en"),
        ("FDA 경고서한이란 무엇인가요?", "ko"),
    ]


def test_auto_general_question_uses_model_only_instead_of_corpus(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    class ConversationalGenerator:
        provider = "test-provider"
        model_id = "test-auto-conversation-model"
        prompt_version = "test-conversation-prompt"

        async def generate_conversational_answer(self, **_kwargs: object) -> str:
            return "A warning letter is an FDA regulatory communication."

        async def generate_grounded_answer(self, **_kwargs: object) -> str:
            raise AssertionError("general auto question must not retrieve documents")

    previous = client.app.state.ai_generator
    client.app.state.ai_generator = ConversationalGenerator()
    try:
        response = client.post(
            "/api/v1/rag/query",
            headers=viewer_headers,
            json={"question": "What is an FDA warning letter?", "language": "en"},
        )
    finally:
        client.app.state.ai_generator = previous

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["retrieval_strategy"] == "none"
    assert body["route_reason"] == "general_conversation_no_retrieval"
    assert body["citations"] == []
    assert body["generation_used"] is True


def test_deep_profile_falls_back_to_allowlisted_balanced_model_on_provider_quota(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    attempted_models: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        model_id = request.url.path.split("/models/", maxsplit=1)[1].split(":", maxsplit=1)[0]
        attempted_models.append(model_id)
        body = json.loads(request.content)
        assert "temperature" not in body["generationConfig"]
        if model_id == "gemini-3.7-flash":
            assert body["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "medium"
            return httpx.Response(429, json={"error": {"message": "quota exhausted"}})
        assert model_id == "gemini-3.5-flash"
        assert body["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "low"
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": (
                                        "An FDA Drug warning letter communicates the agency's "
                                        "regulatory concerns."
                                    )
                                }
                            ]
                        }
                    }
                ]
            },
        )

    values = client.app.state.settings.model_dump()
    values.update(
        {
            "llm_provider": "gemini",
            "gemini_api_key": "test-only-key",
            "chat_fast_model_id": "gemini-3.1-flash-lite",
            "chat_balanced_model_id": "gemini-3.5-flash",
            "chat_deep_model_id": "gemini-3.7-flash",
        }
    )
    generator = GeminiGenerator(
        Settings(**values),
        transport=httpx.MockTransport(handler),
    )
    previous = client.app.state.ai_generator
    client.app.state.ai_generator = generator
    try:
        response = client.post(
            "/api/v1/rag/query",
            headers={**viewer_headers, "X-Dev-User": "deep-fallback.user"},
            json={
                "question": "What is an FDA Drug warning letter?",
                "retrieval_mode": "none",
                "model_profile": "deep",
                "language": "en",
            },
        )
    finally:
        client.app.state.ai_generator = previous

    assert response.status_code == 200, response.text
    body = response.json()
    assert attempted_models == ["gemini-3.7-flash", "gemini-3.5-flash"]
    assert body["generation_used"] is True
    assert body["attempted_model_id"] == "gemini-3.7-flash"
    assert body["effective_model_id"] == "gemini-3.5-flash"
    assert body["effective_model_profile"] == "deep"


def test_lexical_retrieval_ignores_chunks_from_an_inactive_chunker(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    letter = client.get("/api/v1/letters", headers=viewer_headers).json()["items"][0]
    database_url = client.app.state.settings.database_url
    sentinel = "stalechunkeruniqueterm"

    async def insert_stale_chunk() -> str:
        database = Database(database_url)
        try:
            async with database.session_factory() as session:
                current = await session.scalar(
                    select(DocumentChunk)
                    .where(DocumentChunk.warning_letter_id == letter["id"])
                    .order_by(DocumentChunk.ordinal, DocumentChunk.id)
                    .limit(1)
                )
                assert current is not None
                stale = DocumentChunk(
                    document_version_id=current.document_version_id,
                    warning_letter_id=current.warning_letter_id,
                    ordinal=current.ordinal,
                    section_path=["stale"],
                    source_anchor="stale-chunker-anchor",
                    content=f"{sentinel} must never enter active retrieval",
                    token_estimate=8,
                    corpus_id="fda-drugs",
                    acl={"roles": ["viewer"]},
                    chunker_version="structure-retired",
                )
                session.add(stale)
                await session.commit()
                return stale.id
        finally:
            await database.dispose()

    async def remove_stale_chunk(chunk_id: str) -> None:
        database = Database(database_url)
        try:
            async with database.session_factory() as session:
                await session.execute(delete(DocumentChunk).where(DocumentChunk.id == chunk_id))
                await session.commit()
        finally:
            await database.dispose()

    stale_id = asyncio.run(insert_stale_chunk())
    try:
        response = client.post(
            "/api/v1/rag/query",
            headers=viewer_headers,
            json={
                "question": f"Find {sentinel}",
                "filters": {"letter_id": letter["id"]},
                "retrieval_mode": "letter",
            },
        )
    finally:
        asyncio.run(remove_stale_chunk(stale_id))

    assert response.status_code == 200, response.text
    assert response.json()["citations"]
    assert all(sentinel not in item["excerpt"] for item in response.json()["citations"])


def test_metadata_citation_respects_chunk_acl(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    letter = client.get("/api/v1/letters", headers=viewer_headers).json()["items"][0]
    database_url = client.app.state.settings.database_url

    async def set_first_chunk_acl(acl: dict[str, list[str]]) -> tuple[str, dict[str, object]]:
        database = Database(database_url)
        try:
            async with database.session_factory() as session:
                chunk = await session.scalar(
                    select(DocumentChunk)
                    .where(
                        DocumentChunk.warning_letter_id == letter["id"],
                        DocumentChunk.chunker_version == client.app.state.settings.chunker_version,
                    )
                    .order_by(DocumentChunk.ordinal, DocumentChunk.id)
                    .limit(1)
                )
                assert chunk is not None
                previous = dict(chunk.acl or {})
                chunk.acl = acl
                await session.commit()
                return chunk.id, previous
        finally:
            await database.dispose()

    chunk_id, previous_acl = asyncio.run(set_first_chunk_acl({"roles": ["admin"]}))
    try:
        response = client.post(
            "/api/v1/rag/query",
            headers=viewer_headers,
            json={
                "question": "이 경고장의 발행일과 원문 링크는?",
                "filters": {"letter_id": letter["id"]},
                "retrieval_mode": "metadata",
                "language": "ko",
            },
        )
    finally:

        async def restore_acl() -> None:
            database = Database(database_url)
            try:
                async with database.session_factory() as session:
                    chunk = await session.get(DocumentChunk, chunk_id)
                    assert chunk is not None
                    chunk.acl = previous_acl
                    await session.commit()
            finally:
                await database.dispose()

        asyncio.run(restore_acl())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["retrieval_strategy"] == "metadata"
    assert body["citations"]
    assert body["citations"][0]["chunk_id"] != chunk_id
    assert body["generation_used"] is False
    assert body["attempted_model_id"] is None
    assert body["effective_model_id"] is None


def test_metadata_excludes_letter_when_no_source_chunk_is_authorized(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    scoped_headers = {**viewer_headers, "X-Dev-User": "metadata-acl.user"}
    letter = client.get("/api/v1/letters", headers=scoped_headers).json()["items"][0]
    database_url = client.app.state.settings.database_url

    async def restrict_chunks() -> dict[str, dict[str, object]]:
        database = Database(database_url)
        try:
            async with database.session_factory() as session:
                chunks = list(
                    (
                        await session.scalars(
                            select(DocumentChunk).where(
                                DocumentChunk.warning_letter_id == letter["id"],
                                DocumentChunk.chunker_version
                                == client.app.state.settings.chunker_version,
                            )
                        )
                    ).all()
                )
                assert chunks
                previous = {chunk.id: dict(chunk.acl or {}) for chunk in chunks}
                for chunk in chunks:
                    chunk.acl = {"roles": ["admin"]}
                await session.commit()
                return previous
        finally:
            await database.dispose()

    previous_acls = asyncio.run(restrict_chunks())
    try:
        response = client.post(
            "/api/v1/rag/query",
            headers=scoped_headers,
            json={
                "question": "What is this warning letter's issue date and source link?",
                "filters": {"letter_id": letter["id"]},
                "retrieval_mode": "metadata",
            },
        )
    finally:

        async def restore_chunks() -> None:
            database = Database(database_url)
            try:
                async with database.session_factory() as session:
                    chunks = list(
                        (
                            await session.scalars(
                                select(DocumentChunk).where(
                                    DocumentChunk.id.in_(previous_acls)
                                )
                            )
                        ).all()
                    )
                    for chunk in chunks:
                        chunk.acl = previous_acls[chunk.id]
                    await session.commit()
            finally:
                await database.dispose()

        asyncio.run(restore_chunks())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["retrieval_strategy"] == "metadata"
    assert body["citations"] == []
    assert body["evidence_sufficiency"] == "insufficient"
    assert "No FDA Drug warning-letter metadata matched" in body["answer"]


@pytest.mark.parametrize("company_filter", ["%", "_", "\\"])
def test_rag_company_filter_treats_sql_wildcards_as_literal_text(
    company_filter: str,
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    scoped_headers = {
        **viewer_headers,
        "X-Dev-User": f"rag-company-literal-{ord(company_filter)}.user",
    }
    response = client.post(
        "/api/v1/rag/query",
        headers=scoped_headers,
        json={
            "question": "Show FDA Drug warning-letter issue dates and source links.",
            "filters": {"company": company_filter},
            "retrieval_mode": "metadata",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["retrieval_strategy"] == "metadata"
    assert body["citations"] == []
    assert body["evidence_sufficiency"] == "insufficient"


def test_unresolved_manual_letter_scope_fails_closed_without_corpus_fallback(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    thread = _create_thread(client, viewer_headers)
    response = client.post(
        "/api/v1/rag/query",
        headers=viewer_headers,
        json={
            "thread_id": thread["id"],
            "client_message_id": "missing-letter-scope",
            "question": "이 경고장의 지적 사항을 설명해 주세요",
            "retrieval_mode": "letter",
            "language": "ko",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["retrieval_strategy"] == "letter"
    assert body["route_reason"] == "user_requested_letter_scope"
    assert body["citations"] == []
    assert body["evidence_sufficiency"] == "insufficient"
    assert body["generation_used"] is False
    assert body["attempted_model_id"] is None
    assert body["effective_model_id"] is None


def test_current_letter_filter_overrides_persisted_corpus_preference(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    letters = client.get("/api/v1/letters", headers=viewer_headers).json()["items"]
    selected = letters[0]
    thread = _create_thread(client, viewer_headers, retrieval_preference="corpus")

    response = client.post(
        "/api/v1/rag/query",
        headers=viewer_headers,
        json={
            "thread_id": thread["id"],
            "client_message_id": "ask-from-letter-overrides-corpus-default",
            "question": "이 경고장의 지적 사항과 주의점을 설명해 주세요",
            "language": "ko",
            "filters": {"letter_id": selected["id"]},
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["retrieval_strategy"] == "letter"
    assert body["route_reason"] == "explicit_or_resolved_letter_scope"
    assert body["citations"]
    assert {item["warning_letter_id"] for item in body["citations"]} == {selected["id"]}


def test_resolved_letter_name_overrides_persisted_corpus_preference(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    selected = client.get("/api/v1/letters", headers=viewer_headers).json()["items"][0]
    thread = _create_thread(client, viewer_headers, retrieval_preference="corpus")

    response = client.post(
        "/api/v1/rag/query",
        headers=viewer_headers,
        json={
            "thread_id": thread["id"],
            "client_message_id": "resolved-letter-overrides-corpus-default",
            "question": f"{selected['company_name']} 경고장에서 FDA가 요청한 조치는 무엇인가요?",
            "language": "ko",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["retrieval_strategy"] == "letter"
    assert body["route_reason"] == "explicit_or_resolved_letter_scope"
    assert body["citations"]
    assert {item["warning_letter_id"] for item in body["citations"]} == {selected["id"]}


def test_short_company_alias_routes_to_the_specific_warning_letter(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    alias_headers = {**viewer_headers, "X-Dev-User": "alias-route.user"}
    selected = client.get("/api/v1/letters", headers=alias_headers).json()["items"][0]
    database_url = client.app.state.settings.database_url

    async def rename_company(company_name: str) -> None:
        database = Database(database_url)
        try:
            async with database.session_factory() as session:
                letter = await session.get(WarningLetter, selected["id"])
                assert letter is not None
                letter.company_name = company_name
                await session.commit()
        finally:
            await database.dispose()

    original_name = str(selected["company_name"])
    asyncio.run(rename_company("Tianjin Kilo Pharmaceutical Sci-tech Co., Ltd."))
    try:
        response = client.post(
            "/api/v1/rag/query",
            headers=alias_headers,
            json={
                "question": "Tianjin Kilo 경고서한의 주요 지적 사항을 알려 주세요",
                "language": "ko",
            },
        )
    finally:
        asyncio.run(rename_company(original_name))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["retrieval_strategy"] == "letter"
    assert body["route_reason"] == "explicit_or_resolved_letter_scope"
    assert body["citations"]
    assert {item["warning_letter_id"] for item in body["citations"]} == {selected["id"]}


def test_thread_messages_are_persisted_idempotently_and_follow_up_stays_letter_scoped(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    letter = client.get("/api/v1/letters", headers=viewer_headers).json()["items"][0]
    thread = _create_thread(client, viewer_headers, active_letter_ids=[letter["id"]])
    payload = {
        "thread_id": thread["id"],
        "client_message_id": "browser-message-1",
        "question": "이 경고장의 공정 밸리데이션 지적 사항은 무엇인가요?",
        "language": "ko",
        "filters": {"letter_id": letter["id"]},
    }
    first = client.post("/api/v1/rag/query", headers=viewer_headers, json=payload)
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["retrieval_strategy"] == "letter"
    assert first_body["effective_model_profile"] == "fast"
    assert first_body["generation_used"] is False
    assert first_body["attempted_model_id"] is None
    assert first_body["effective_model_id"] is None
    assert first_body["user_message_id"]
    assert first_body["assistant_message_id"]
    assert all(item["warning_letter_id"] == letter["id"] for item in first_body["citations"])

    repeated = client.post("/api/v1/rag/query", headers=viewer_headers, json=payload)
    assert repeated.status_code == 200
    assert repeated.json()["user_message_id"] == first_body["user_message_id"]
    assert repeated.json()["assistant_message_id"] == first_body["assistant_message_id"]

    detail = client.get(f"/api/v1/chat/threads/{thread['id']}", headers=viewer_headers).json()
    assert [message["role"] for message in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["route_metadata"]["retrieval_strategy"] == "letter"

    follow_up = client.post(
        "/api/v1/rag/query",
        headers=viewer_headers,
        json={
            "thread_id": thread["id"],
            "client_message_id": "browser-message-2",
            "question": "그 경고장에서 FDA가 추가로 요청한 조치는 무엇인가요?",
            "language": "ko",
        },
    )
    assert follow_up.status_code == 200, follow_up.text
    follow_body = follow_up.json()
    assert follow_body["retrieval_strategy"] == "letter"
    assert follow_body["route_reason"] in {
        "follow_up_inherited_scope",
        "thread_active_letter_scope",
    }
    assert follow_body["citations"]
    assert all(item["warning_letter_id"] == letter["id"] for item in follow_body["citations"])


def test_persisted_user_message_exists_before_generation_and_profiles_are_reported(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    letter = client.get("/api/v1/letters", headers=viewer_headers).json()["items"][0]
    thread = _create_thread(client, viewer_headers, active_letter_ids=[letter["id"]])
    database_url = client.app.state.settings.database_url
    observed: dict[str, bool] = {}

    class ObservingGenerator:
        provider = "test-provider"
        model_id = "test-grounded-model"
        prompt_version = "test-prompt"

        async def generate_grounded_answer(
            self,
            *,
            question: str,
            language: str,
            passages: list[GroundedPassage],
            conversation_history: list[ConversationTurn],
        ) -> str:
            database = Database(database_url)
            try:
                async with database.session_factory() as session:
                    messages = list(
                        (
                            await session.scalars(
                                select(ChatMessage)
                                .where(ChatMessage.thread_id == thread["id"])
                                .order_by(ChatMessage.sequence)
                            )
                        ).all()
                    )
                    user_count = await session.scalar(
                        select(func.count(ChatMessage.id)).where(
                            ChatMessage.thread_id == thread["id"],
                            ChatMessage.role == "user",
                            ChatMessage.client_message_id == "persist-before-provider",
                        )
                    )
                    pending = [
                        message
                        for message in messages
                        if message.role == "assistant" and message.status == "pending"
                    ]
                    observed["persisted"] = user_count == 1
                    observed["pending_assistant"] = len(pending) == 1 and bool(
                        pending[0].content.strip()
                    )
            finally:
                await database.dispose()
            assert question
            assert language == "ko"
            assert passages
            return "FDA 원문 근거를 바탕으로 내부 비교 질문을 구성해야 합니다 [1]."

    previous = client.app.state.ai_generator
    client.app.state.ai_generator = ObservingGenerator()
    try:
        response = client.post(
            "/api/v1/rag/query",
            headers=viewer_headers,
            json={
                "thread_id": thread["id"],
                "client_message_id": "persist-before-provider",
                "question": "우리 워크플로에 같은 공정 문제가 있는지 비교해 주세요",
                "language": "ko",
                "model_profile": "auto",
            },
        )
    finally:
        client.app.state.ai_generator = previous
    assert response.status_code == 200, response.text
    body = response.json()
    assert observed == {"persisted": True, "pending_assistant": True}
    assert body["interpretation_label"] == "internal_comparison"
    assert body["effective_model_profile"] == "deep"
    assert body["generation_used"] is True
    assert body["attempted_model_id"] == "test-grounded-model"
    assert body["effective_model_id"] == "test-grounded-model"

    manual = client.post(
        "/api/v1/rag/query",
        headers=viewer_headers,
        json={
            "thread_id": thread["id"],
            "client_message_id": "manual-deep",
            "question": "이 경고장의 다른 지적도 설명해 주세요",
            "language": "ko",
            "model_profile": "deep",
        },
    )
    assert manual.status_code == 200
    assert manual.json()["requested_model_profile"] == "deep"
    assert manual.json()["effective_model_profile"] == "deep"
    assert manual.json()["generation_used"] is False
    assert manual.json()["attempted_model_id"] is None
    assert manual.json()["effective_model_id"] is None


def test_generation_exception_marks_placeholder_failed_and_same_key_retry_resumes(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    letter = client.get("/api/v1/letters", headers=viewer_headers).json()["items"][0]
    thread = _create_thread(client, viewer_headers, active_letter_ids=[letter["id"]])

    class FlakyGenerator:
        provider = "test-provider"
        model_id = "test-recovery-model"
        prompt_version = "test-recovery-prompt"
        calls = 0

        async def generate_grounded_answer(
            self,
            *,
            question: str,
            language: str,
            passages: list[GroundedPassage],
            conversation_history: list[ConversationTurn],
        ) -> str:
            self.calls += 1
            assert question and language == "ko" and passages
            if self.calls == 1:
                raise RuntimeError("simulated transient provider failure")
            return "재시도 후 FDA 원문 근거에 기반한 답변을 완료했습니다 [1]."

    generator = FlakyGenerator()
    payload = {
        "thread_id": thread["id"],
        "client_message_id": "recover-same-idempotency-key",
        "question": "이 경고장의 공정 밸리데이션 지적 사항은 무엇인가요?",
        "language": "ko",
        "filters": {"letter_id": letter["id"]},
    }
    previous = client.app.state.ai_generator
    client.app.state.ai_generator = generator
    try:
        failed = client.post("/api/v1/rag/query", headers=viewer_headers, json=payload)
        assert failed.status_code == 502, failed.text

        failed_reload = client.get(
            f"/api/v1/chat/threads/{thread['id']}", headers=viewer_headers
        ).json()
        assert len(failed_reload["messages"]) == 2
        failed_user, failed_assistant = failed_reload["messages"]
        assert failed_user["role"] == "user"
        assert failed_assistant["role"] == "assistant"
        assert failed_assistant["status"] == "failed"
        assert failed_assistant["content"].strip()
        assert failed_assistant["model_metadata"]["generation_used"] is False
        assert failed_assistant["model_metadata"]["attempted_model_id"] == "test-recovery-model"

        recovered = client.post("/api/v1/rag/query", headers=viewer_headers, json=payload)
    finally:
        client.app.state.ai_generator = previous

    assert recovered.status_code == 200, recovered.text
    body = recovered.json()
    assert body["user_message_id"] == failed_user["id"]
    assert body["assistant_message_id"] == failed_assistant["id"]
    assert body["generation_used"] is True
    assert body["attempted_model_id"] == "test-recovery-model"
    assert body["effective_model_id"] == "test-recovery-model"
    assert generator.calls == 2

    completed_reload = client.get(
        f"/api/v1/chat/threads/{thread['id']}", headers=viewer_headers
    ).json()
    assert len(completed_reload["messages"]) == 2
    assert [message["status"] for message in completed_reload["messages"]] == [
        "completed",
        "completed",
    ]


def test_ai_validation_fallback_reports_attempt_without_effective_generation(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    letter = client.get("/api/v1/letters", headers=viewer_headers).json()["items"][0]
    thread = _create_thread(client, viewer_headers, active_letter_ids=[letter["id"]])

    class InvalidGenerator:
        provider = "test-provider"
        model_id = "test-invalid-model"
        prompt_version = "test-invalid-prompt"

        async def generate_grounded_answer(
            self,
            *,
            question: str,
            language: str,
            passages: list[GroundedPassage],
            conversation_history: list[ConversationTurn],
        ) -> str:
            raise AiGenerationError("simulated local output validation failure")

    previous = client.app.state.ai_generator
    client.app.state.ai_generator = InvalidGenerator()
    try:
        response = client.post(
            "/api/v1/rag/query",
            headers=viewer_headers,
            json={
                "thread_id": thread["id"],
                "client_message_id": "validated-fallback-model-state",
                "question": "이 경고장의 품질 지적 사항은 무엇인가요?",
                "language": "ko",
                "filters": {"letter_id": letter["id"]},
            },
        )
    finally:
        client.app.state.ai_generator = previous

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["generation_used"] is False
    assert body["attempted_model_id"] == "test-invalid-model"
    assert body["effective_model_id"] is None
    detail = client.get(f"/api/v1/chat/threads/{thread['id']}", headers=viewer_headers).json()
    assistant = detail["messages"][1]
    assert assistant["status"] == "completed"
    assert assistant["model_metadata"]["generation_used"] is False
    assert assistant["model_metadata"]["attempted_model_id"] == "test-invalid-model"
    assert assistant["model_metadata"]["effective_model_id"] is None


def test_active_pending_placeholder_rejects_duplicate_request(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    thread = _create_thread(client, viewer_headers)
    payload = {
        "thread_id": thread["id"],
        "client_message_id": "active-pending-key",
        "question": "안녕하세요",
        "retrieval_mode": "none",
    }
    completed = client.post("/api/v1/rag/query", headers=viewer_headers, json=payload)
    assert completed.status_code == 200, completed.text
    assistant_id = completed.json()["assistant_message_id"]
    database_url = client.app.state.settings.database_url

    async def make_pending() -> None:
        database = Database(database_url)
        try:
            async with database.session_factory() as session:
                assistant = await session.get(ChatMessage, assistant_id)
                assert assistant is not None
                assistant.status = "pending"
                assistant.updated_at = datetime.now(UTC)
                await session.commit()
        finally:
            await database.dispose()

    asyncio.run(make_pending())
    active_reload = client.get(f"/api/v1/chat/threads/{thread['id']}", headers=viewer_headers)
    assert active_reload.status_code == 200
    assert active_reload.json()["messages"][1]["status"] == "pending"
    duplicate = client.post("/api/v1/rag/query", headers=viewer_headers, json=payload)
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Chat message is already processing"


def test_stale_pending_placeholder_is_resumed_without_duplicate_messages(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    thread = _create_thread(client, viewer_headers)
    payload = {
        "thread_id": thread["id"],
        "client_message_id": "stale-pending-key",
        "question": "안녕하세요",
        "retrieval_mode": "none",
    }
    completed = client.post("/api/v1/rag/query", headers=viewer_headers, json=payload)
    assert completed.status_code == 200, completed.text
    first_body = completed.json()
    database_url = client.app.state.settings.database_url

    async def make_stale() -> None:
        database = Database(database_url)
        try:
            async with database.session_factory() as session:
                assistant = await session.get(ChatMessage, first_body["assistant_message_id"])
                assert assistant is not None
                assistant.status = "pending"
                assistant.updated_at = datetime.now(UTC) - timedelta(minutes=10)
                await session.commit()
        finally:
            await database.dispose()

    asyncio.run(make_stale())
    stale_reload = client.get(f"/api/v1/chat/threads/{thread['id']}", headers=viewer_headers)
    assert stale_reload.status_code == 200
    stale_assistant = stale_reload.json()["messages"][1]
    assert stale_assistant["status"] == "failed"
    assert stale_assistant["route_metadata"]["failure_code"] == "stale_pending"
    assert stale_assistant["content"].strip()

    resumed = client.post("/api/v1/rag/query", headers=viewer_headers, json=payload)
    assert resumed.status_code == 200, resumed.text
    resumed_body = resumed.json()
    assert resumed_body["user_message_id"] == first_body["user_message_id"]
    assert resumed_body["assistant_message_id"] == first_body["assistant_message_id"]
    detail = client.get(f"/api/v1/chat/threads/{thread['id']}", headers=viewer_headers).json()
    assert len(detail["messages"]) == 2
    assert detail["messages"][1]["status"] == "completed"


@pytest.mark.parametrize(
    "changed_fields",
    [
        {"question": "감사합니다"},
        {"retrieval_mode": "metadata"},
        {"model_profile": "deep"},
        {"filters": {"company": "Different Company"}},
    ],
    ids=["question", "retrieval-mode", "model-profile", "filters"],
)
def test_same_client_message_id_rejects_material_payload_change(
    changed_fields: dict[str, object],
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    thread = _create_thread(client, viewer_headers)
    payload: dict[str, object] = {
        "thread_id": thread["id"],
        "client_message_id": f"fingerprint-conflict-{next(iter(changed_fields))}",
        "question": "안녕하세요",
        "retrieval_mode": "none",
        "model_profile": "fast",
        "filters": {},
    }
    completed = client.post("/api/v1/rag/query", headers=viewer_headers, json=payload)
    assert completed.status_code == 200, completed.text

    changed_payload = {**payload, **changed_fields}
    conflict = client.post("/api/v1/rag/query", headers=viewer_headers, json=changed_payload)
    assert conflict.status_code == 409
    assert "different request" in conflict.json()["detail"]

    detail = client.get(f"/api/v1/chat/threads/{thread['id']}", headers=viewer_headers).json()
    assert len(detail["messages"]) == 2


def test_client_cannot_supply_thread_owner(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    response = client.post(
        "/api/v1/chat/threads",
        headers=viewer_headers,
        json={"title": "invalid", "owner_subject": "attacker"},
    )
    assert response.status_code == 422
