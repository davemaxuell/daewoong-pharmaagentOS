from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.ai import (
    DOCUMENT_ANALYSIS_SCHEMA_VERSION,
    AiGenerationError,
    ConversationTurn,
    DocumentSourceSection,
    GeminiDocumentGenerator,
    GroundedPassage,
)
from app.config import Settings
from app.database import Database
from app.main import create_app
from app.models import AiSummary, DocumentTranslation, DocumentVersion, Finding, WarningLetter
from app.routes.intelligence import _validate_analysis, _validate_translation
from app.seed import seed_demo


class FakeDocumentGenerator:
    provider = "test-provider"
    model_id = "test-document-model"
    prompt_version = "letter-translation-ko-v4"

    def __init__(
        self,
        *,
        invalid_anchor: bool = False,
        invented_translation_token: str | None = None,
        invalid_analysis_attempts: int = 0,
    ) -> None:
        self.invalid_anchor = invalid_anchor
        self.invented_translation_token = invented_translation_token
        self.invalid_analysis_attempts = invalid_analysis_attempts
        self.translation_calls = 0
        self.analysis_calls = 0

    async def generate_translation(
        self, *, source_sections: list[DocumentSourceSection]
    ) -> dict[str, object]:
        self.translation_calls += 1
        self.prompt_version = "letter-translation-ko-v4"
        return {
            "sections": [
                {
                    "anchor": "unknown-anchor"
                    if self.invalid_anchor and index == 0
                    else item.anchor,
                    "heading": (
                        f"번역 {item.heading}"
                        + (
                            f" {self.invented_translation_token}"
                            if self.invented_translation_token and index == 0
                            else ""
                        )
                    ),
                    "paragraphs": [f"번역 {paragraph}" for paragraph in item.paragraphs],
                }
                for index, item in enumerate(source_sections)
            ]
        }

    async def generate_letter_analysis(
        self,
        *,
        company_name: str,
        source_sections: list[DocumentSourceSection],
        language: str,
        validation_feedback: str | None = None,
    ) -> dict[str, object]:
        self.analysis_calls += 1
        self.prompt_version = "letter-artifacts-bilingual-v2"
        evidence_section = next(
            (section for section in source_sections if section.paragraphs), source_sections[0]
        )
        anchor = (
            "unknown-anchor"
            if self.invalid_anchor or self.analysis_calls <= self.invalid_analysis_attempts
            else evidence_section.anchor
        )
        if language == "en":
            return {
                "executive_summary": f"Key FDA findings for the warning letter to {company_name}.",
                "attention_points": [
                    {
                        "title": "Internal process comparison",
                        "rationale": "Review whether a similar control gap exists internally.",
                        "source_anchors": [anchor],
                    }
                ],
                "comparison_questions": [
                    "Have internal procedures been checked for a similar control gap?"
                ],
                "disclaimer": (
                    "This supports internal comparison and is not a compliance conclusion."
                ),
                "findings": [
                    {
                        "label": "01",
                        "title": "Source-grounded FDA finding",
                        "finding": "The FDA source explicitly describes a control gap.",
                        "requested_actions": ["Review the information requested by FDA."],
                        "categories": ["Quality Unit / QA Oversight"],
                        "attention_level": "medium",
                        "evidence_anchors": [anchor],
                        "regulatory_references": [],
                    }
                ],
            }
        return {
            "executive_summary": f"{company_name} 경고서의 핵심 FDA 지적 사항입니다.",
            "attention_points": [
                {
                    "title": "내부 절차 비교 검토",
                    "rationale": "동일한 관리 공백이 있는지 중립적으로 확인합니다.",
                    "source_anchors": [anchor],
                }
            ],
            "comparison_questions": ["내부 절차에 동일한 관리 공백이 있는지 확인했습니까?"],
            "disclaimer": "대웅의 규정 준수에 대한 결론이 아닌 내부 비교 검토 자료입니다.",
            "findings": [
                {
                    "label": "01",
                    "title": "FDA 원문 기반 지적",
                    "finding": "FDA가 원문에서 명시한 관리 공백입니다.",
                    "requested_actions": ["FDA가 요청한 자료를 확인합니다."],
                    "categories": ["Quality Unit / QA Oversight"],
                    "attention_level": "medium",
                    "evidence_anchors": [anchor],
                    "regulatory_references": [],
                }
            ],
        }


class CapturingChatGenerator:
    provider = "test-chat-provider"
    model_id = "test-chat-model"
    prompt_version = "test-chat-v1"

    def __init__(self) -> None:
        self.history: list[ConversationTurn] = []
        self.passages: list[GroundedPassage] = []

    async def generate_grounded_answer(
        self,
        *,
        question: str,
        language: str,
        passages: list[GroundedPassage],
        conversation_history: list[ConversationTurn],
    ) -> str:
        self.history = conversation_history
        self.passages = passages
        return "원문 근거를 우선하여 추가 검토 항목을 확인했습니다 [1]."


@pytest.fixture
def artifact_client(
    tmp_path: Path, fixture_dir: Path
) -> Iterator[tuple[TestClient, FakeDocumentGenerator]]:
    settings = Settings(
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'artifact.db').as_posix()}",
        object_store_path=tmp_path / "objects",
        fda_request_delay_seconds=0,
        allowed_hosts=["testserver", "localhost", "127.0.0.1"],
        llm_provider="none",
        gemini_api_key=None,
    )

    async def prepare() -> None:
        database = Database(settings.database_url)
        try:
            await database.create_schema()
            async with database.session_factory() as session:
                await seed_demo(session, settings, fixture_dir)
        finally:
            await database.dispose()

    asyncio.run(prepare())
    fake = FakeDocumentGenerator()
    app = create_app(settings)
    app.state.document_ai_generator = fake
    with TestClient(app) as client:
        yield client, fake


def _first_letter(client: TestClient, headers: dict[str, str]) -> dict[str, object]:
    response = client.get("/api/v1/letters?page_size=1", headers=headers)
    assert response.status_code == 200
    return response.json()["items"][0]


def _valid_analysis_payload(anchor: str) -> dict[str, object]:
    return {
        "executive_summary": "FDA 원문에 근거한 핵심 지적 사항 요약입니다.",
        "attention_points": [
            {
                "title": "내부 절차 비교 검토",
                "rationale": "동일한 관리 공백이 있는지 중립적으로 확인합니다.",
                "source_anchors": [anchor],
            }
        ],
        "comparison_questions": ["내부 절차에 동일한 관리 공백이 있는지 확인했습니까?"],
        "disclaimer": "대웅의 규정 준수 결론이 아닌 내부 비교 검토 자료입니다.",
        "findings": [
            {
                "label": "01",
                "title": "FDA 원문 기반 지적",
                "finding": "FDA가 원문에서 명시한 관리 공백입니다.",
                "requested_actions": ["FDA가 요청한 자료를 확인합니다."],
                "categories": ["Quality Unit / QA Oversight"],
                "attention_level": "medium",
                "evidence_anchors": [anchor],
                "regulatory_references": ["21 CFR 211.22"],
            }
        ],
    }


def _seed_legacy_korean_analysis(
    client: TestClient,
    letter_id: str,
    *,
    include_finding: bool = True,
) -> tuple[str, str | None]:
    async def seed() -> tuple[str, str | None]:
        database = Database(client.app.state.settings.database_url)
        try:
            async with database.session_factory() as session:
                letter = await session.get(WarningLetter, letter_id)
                assert letter and letter.current_version_id
                version = await session.get(DocumentVersion, letter.current_version_id)
                assert version is not None
                anchor = next(
                    (
                        str(item.get("anchor"))
                        for item in (version.source_anchors or [])
                        if item.get("kind") == "heading" and item.get("anchor")
                    ),
                    "document-start",
                )
                legacy = AiSummary(
                    document_version_id=version.id,
                    revision=1,
                    language="ko",
                    executive_summary="FDA 원문에 근거한 기존 요약입니다.",
                    structured_output={
                        "executive_summary": "FDA 원문에 근거한 기존 요약입니다.",
                        "attention_points": [
                            {
                                "title": "내부 비교 검토",
                                "rationale": "동일한 관리 공백이 있는지 중립적으로 확인합니다.",
                                "source_anchors": [anchor],
                            }
                        ],
                        "comparison_questions": ["내부 절차와 비교했습니까?"],
                        "disclaimer": "내부 비교 검토용이며 규정 준수 결론이 아닙니다.",
                        "source_hash": version.canonical_hash,
                    },
                    validation_report={"passed": True},
                    provider="legacy-provider",
                    model_id="legacy-model",
                    prompt_version="legacy-prompt-v1",
                    schema_version="letter-analysis-v1",
                    taxonomy_version=client.app.state.settings.taxonomy_version,
                    review_state="approved",
                    reviewer_id="legacy.reviewer",
                )
                session.add(legacy)
                await session.flush()
                finding_id = None
                if include_finding:
                    finding = Finding(
                        document_version_id=version.id,
                        summary_id=legacy.id,
                        label="01",
                        categories=["Quality Unit / QA Oversight"],
                        process_lenses=["retrospective"],
                        finding_text="FDA가 원문에 명시한 관리 공백입니다.",
                        regulatory_references=["21 CFR 211.22"],
                        evidence=[
                            {
                                "source_anchor": anchor,
                                "title": "FDA 원문 기반 지적",
                                "official_url": letter.canonical_url,
                            }
                        ],
                        fda_requested_actions=["FDA가 요청한 자료를 확인합니다."],
                        comparison_points=["내부 절차와 비교했습니까?"],
                        attention_level="medium",
                        confidence=0.9,
                        review_state="approved",
                    )
                    session.add(finding)
                    await session.flush()
                    finding_id = finding.id
                await session.commit()
                return legacy.id, finding_id
        finally:
            await database.dispose()

    return asyncio.run(seed())


def test_secondary_translation_validation_accepts_exact_tokens_beside_hangul() -> None:
    source = DocumentSourceSection(
        anchor="response-request",
        heading="Response Requested",
        paragraphs=[
            "Respond within 15 working days and retain 15 records.",
            "See https://www.fda.gov/example",
        ],
    )
    output = {
        "sections": [
            {
                "anchor": source.anchor,
                "heading": "응답 요청",
                "paragraphs": [
                    "15영업일 이내에 응답하고 15개의 기록을 보존하십시오.",
                    "https://www.fda.gov/example을 참조하십시오.",
                ],
            }
        ]
    }

    translated, report = _validate_translation(output, [source])

    assert translated[0]["paragraphs"][0].startswith("15영업일")
    assert report["passed"] is True


def test_secondary_translation_validation_rejects_missing_or_moved_tokens() -> None:
    source = DocumentSourceSection(
        anchor="response-request",
        heading="Response Requested",
        paragraphs=["Respond within 15 working days.", "Keep the response concise."],
    )
    output = {
        "sections": [
            {
                "anchor": source.anchor,
                "heading": "응답 요청",
                "paragraphs": ["영업일 이내에 응답하십시오.", "15 응답은 간결해야 합니다."],
            }
        ]
    }

    with pytest.raises(AiGenerationError, match="token identity or multiplicity"):
        _validate_translation(output, [source])


@pytest.mark.parametrize(
    "invented_token",
    ["999", "21 CFR 999.1", "https://invented.invalid/path", "January 1, 2099", "[REDACTED]"],
)
def test_secondary_translation_validation_rejects_invented_protected_token(
    invented_token: str,
) -> None:
    source = DocumentSourceSection(
        anchor="fda-review",
        heading="FDA Review",
        paragraphs=["The firm failed to maintain adequate controls."],
    )
    output = {
        "sections": [
            {
                "anchor": source.anchor,
                "heading": f"FDA 검토 {invented_token}",
                "paragraphs": ["회사는 적절한 관리를 유지하지 못했습니다."],
            }
        ]
    }

    with pytest.raises(AiGenerationError, match="token identity or multiplicity"):
        _validate_translation(output, [source])


@pytest.mark.parametrize(
    ("empty_field", "error_match"),
    [
        ("findings", "invalid findings"),
        ("attention_points", "invalid attention points"),
    ],
)
def test_analysis_validation_rejects_empty_required_artifacts(
    empty_field: str,
    error_match: str,
) -> None:
    source = DocumentSourceSection(
        anchor="finding-one",
        heading="FDA Finding",
        paragraphs=["FDA explicitly described a quality-system deficiency."],
    )
    output: dict[str, object] = {
        "executive_summary": "FDA 원문 기반 요약입니다.",
        "attention_points": [
            {
                "title": "내부 비교 검토",
                "rationale": "원문에 명시된 관리 공백을 중립적으로 확인합니다.",
                "source_anchors": [source.anchor],
            }
        ],
        "comparison_questions": ["내부 절차와 비교했습니까?"],
        "disclaimer": "내부 비교 검토용입니다.",
        "findings": [
            {
                "label": "01",
                "title": "FDA 원문 기반 지적",
                "finding": "FDA가 원문에 명시한 관리 공백입니다.",
                "requested_actions": ["FDA가 요청한 자료를 확인합니다."],
                "categories": ["Quality Unit / QA Oversight"],
                "attention_level": "medium",
                "evidence_anchors": [source.anchor],
                "regulatory_references": [],
            }
        ],
    }
    output[empty_field] = []

    with pytest.raises(AiGenerationError, match=error_match):
        _validate_analysis(output, [source])


@pytest.mark.parametrize(
    "english_field",
    [
        "executive_summary",
        "attention_title",
        "attention_rationale",
        "comparison_question",
        "disclaimer",
        "finding_title",
        "finding_text",
        "requested_action",
    ],
)
def test_analysis_validation_rejects_english_only_user_facing_prose(
    english_field: str,
) -> None:
    source = DocumentSourceSection(
        anchor="finding-one",
        heading="FDA Finding",
        paragraphs=["FDA explicitly described a quality-system deficiency."],
    )
    output = _valid_analysis_payload(source.anchor)
    english_text = "This user-facing regulatory explanation is entirely in English."
    if english_field == "executive_summary":
        output["executive_summary"] = english_text
    elif english_field == "attention_title":
        output["attention_points"][0]["title"] = english_text  # type: ignore[index]
    elif english_field == "attention_rationale":
        output["attention_points"][0]["rationale"] = english_text  # type: ignore[index]
    elif english_field == "comparison_question":
        output["comparison_questions"] = [f"{english_text}?"]
    elif english_field == "disclaimer":
        output["disclaimer"] = english_text
    elif english_field == "finding_title":
        output["findings"][0]["title"] = english_text  # type: ignore[index]
    elif english_field == "finding_text":
        output["findings"][0]["finding"] = english_text  # type: ignore[index]
    else:
        output["findings"][0]["requested_actions"] = [english_text]  # type: ignore[index]

    with pytest.raises(AiGenerationError, match="insufficient Korean"):
        _validate_analysis(output, [source])


def test_analysis_validation_accepts_korean_with_official_english_annotations() -> None:
    source = DocumentSourceSection(
        anchor="finding-one",
        heading="FDA Finding",
        paragraphs=["FDA explicitly described a quality-system deficiency under 21 CFR 211.22."],
    )
    output = _valid_analysis_payload(source.anchor)
    output["executive_summary"] = (
        "Tianjin Kilo Pharmaceutical Sci-tech Co., Ltd. 경고서의 FDA 지적을 한국어로 요약합니다."
    )
    output["attention_points"][0]["title"] = "FDA Review 내부 검토"  # type: ignore[index]
    output["attention_points"][0]["rationale"] = (  # type: ignore[index]
        "21 CFR 211.22 및 Quality Unit 관련 사항을 내부 절차와 비교 검토합니다."
    )
    output["findings"][0]["title"] = "공정 밸리데이션(Process Validation) 지적"  # type: ignore[index]
    output["findings"][0]["finding"] = (  # type: ignore[index]
        "FDA가 Quality Unit 관리 공백을 원문에서 명시했습니다."
    )

    summary, findings, report = _validate_analysis(output, [source])

    assert summary["executive_summary"].startswith("Tianjin Kilo")
    assert findings[0]["title"].startswith("공정 밸리데이션")
    assert report["passed"] is True


def test_translation_is_validated_persisted_and_returned_from_cache(
    artifact_client: tuple[TestClient, FakeDocumentGenerator],
    viewer_headers: dict[str, str],
) -> None:
    client, generator = artifact_client
    letter = _first_letter(client, viewer_headers)
    path = f"/api/v1/letters/{letter['id']}/ai-artifacts/translation"

    first = client.post(path, headers=viewer_headers)
    second = client.post(path, headers=viewer_headers)

    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert generator.translation_calls == 1
    artifact = first.json()
    assert artifact["artifact_type"] == "translation"
    assert artifact["language"] == "ko"
    assert artifact["content"]["sections"]
    assert artifact["source_hash"]
    detail = client.get(f"/api/v1/letters/{letter['id']}", headers=viewer_headers)
    assert any(item["id"] == artifact["id"] for item in detail.json()["ai_artifacts"])


def test_outdated_translation_prompt_is_not_served_or_reused(
    artifact_client: tuple[TestClient, FakeDocumentGenerator],
    viewer_headers: dict[str, str],
) -> None:
    client, generator = artifact_client
    letter = _first_letter(client, viewer_headers)

    async def seed_outdated_translation() -> str:
        database = Database(client.app.state.settings.database_url)
        try:
            async with database.session_factory() as session:
                warning_letter = await session.get(WarningLetter, str(letter["id"]))
                assert warning_letter is not None
                version = await session.get(DocumentVersion, warning_letter.current_version_id)
                assert version is not None
                outdated = DocumentTranslation(
                    document_version_id=version.id,
                    language="ko",
                    source_hash=version.canonical_hash,
                    translated_sections=[
                        {"anchor": "outdated", "heading": "이전 번역", "paragraphs": []}
                    ],
                    validation_report={"passed": True},
                    provider="google-gemini",
                    model_id="gemini-3.5-flash",
                    prompt_version="letter-artifacts-ko-v1",
                    schema_version="document-translation-v1",
                )
                session.add(outdated)
                await session.commit()
                return outdated.id
        finally:
            await database.dispose()

    outdated_id = asyncio.run(seed_outdated_translation())
    detail_before = client.get(f"/api/v1/letters/{letter['id']}", headers=viewer_headers).json()
    assert all(item["id"] != outdated_id for item in detail_before["ai_artifacts"])

    generated = client.post(
        f"/api/v1/letters/{letter['id']}/ai-artifacts/translation",
        headers=viewer_headers,
    )

    assert generated.status_code == 200
    assert generated.json()["id"] != outdated_id
    assert generated.json()["prompt_version"] == "letter-translation-ko-v4"
    assert generator.translation_calls == 1


def test_valid_legacy_analysis_is_immutably_promoted_and_cached_without_model_call(
    artifact_client: tuple[TestClient, FakeDocumentGenerator],
    viewer_headers: dict[str, str],
) -> None:
    client, generator = artifact_client
    letter = _first_letter(client, viewer_headers)
    legacy_id, legacy_finding_id = _seed_legacy_korean_analysis(client, str(letter["id"]))
    base = f"/api/v1/letters/{letter['id']}/ai-artifacts"

    findings_response = client.post(f"{base}/findings", headers=viewer_headers)
    summary_response = client.post(f"{base}/summary", headers=viewer_headers)

    assert findings_response.status_code == summary_response.status_code == 200
    assert generator.analysis_calls == 0
    assert findings_response.json()["id"] == summary_response.json()["id"]
    assert findings_response.json()["id"] != legacy_id
    assert findings_response.json()["model_id"] == "legacy-model"
    assert findings_response.json()["content"]["findings"][0]["evidence_anchors"]

    async def promoted_state() -> tuple[AiSummary, AiSummary, list[Finding]]:
        database = Database(client.app.state.settings.database_url)
        try:
            async with database.session_factory() as session:
                legacy = await session.get(AiSummary, legacy_id)
                promoted = await session.get(AiSummary, findings_response.json()["id"])
                assert legacy is not None and promoted is not None
                promoted_findings = list(
                    (
                        await session.scalars(
                            select(Finding)
                            .where(Finding.summary_id == promoted.id)
                            .order_by(Finding.created_at, Finding.id)
                        )
                    ).all()
                )
                return legacy, promoted, promoted_findings
        finally:
            await database.dispose()

    legacy, promoted, promoted_findings = asyncio.run(promoted_state())
    assert legacy.schema_version == "letter-analysis-v1"
    assert legacy.id == legacy_id
    assert promoted.schema_version == DOCUMENT_ANALYSIS_SCHEMA_VERSION
    assert promoted.parent_summary_id == legacy_id
    assert promoted.revision == legacy.revision + 1
    assert promoted.validation_report["promoted_from_summary_id"] == legacy_id
    assert len(promoted_findings) == 1
    assert promoted_findings[0].id != legacy_finding_id
    assert promoted_findings[0].summary_id == promoted.id
    assert promoted_findings[0].process_lenses == ["retrospective"]


def test_invalid_legacy_analysis_falls_through_to_fresh_generation(
    artifact_client: tuple[TestClient, FakeDocumentGenerator],
    viewer_headers: dict[str, str],
) -> None:
    client, generator = artifact_client
    letter = _first_letter(client, viewer_headers)
    legacy_id, _finding_id = _seed_legacy_korean_analysis(
        client,
        str(letter["id"]),
        include_finding=False,
    )

    response = client.post(
        f"/api/v1/letters/{letter['id']}/ai-artifacts/summary",
        headers=viewer_headers,
    )

    assert response.status_code == 200
    assert response.json()["id"] != legacy_id
    assert response.json()["model_id"] == generator.model_id
    assert generator.analysis_calls == 1


def test_successful_analysis_fallback_model_id_is_persisted_and_reported(
    artifact_client: tuple[TestClient, FakeDocumentGenerator],
    viewer_headers: dict[str, str],
) -> None:
    client, _fake = artifact_client

    def handler(request: httpx.Request) -> httpx.Response:
        if any(model in request.url.path for model in ("gemini-3.7-flash", "gemini-3.6-flash")):
            return httpx.Response(503, json={"error": {"message": "temporarily unavailable"}})
        request_body = json.loads(request.content)
        prompt = request_body["contents"][0]["parts"][0]["text"]
        payload = json.loads(prompt.split("\n", maxsplit=1)[1])
        anchor = payload["source_sections"][0]["anchor"]
        output = {
            "executive_summary": "FDA 원문 기반 요약입니다.",
            "attention_points": [
                {
                    "title": "내부 비교 검토",
                    "rationale": "명시된 FDA 지적을 확인합니다.",
                    "source_anchors": [anchor],
                }
            ],
            "comparison_questions": ["내부 절차와 비교했습니까?"],
            "disclaimer": "내부 비교 검토용입니다.",
            "findings": [
                {
                    "label": "01",
                    "title": "FDA 원문 기반 지적",
                    "finding": "FDA가 원문에 명시한 관리 공백입니다.",
                    "requested_actions": ["FDA가 요청한 자료를 확인합니다."],
                    "categories": ["Quality Unit / QA Oversight"],
                    "attention_level": "medium",
                    "evidence_anchors": [anchor],
                    "regulatory_references": [],
                }
            ],
        }
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": json.dumps(output)}]}}]},
        )

    generator_settings = Settings(
        app_env="test",
        llm_provider="gemini",
        gemini_api_key="test-only-key",
        document_ai_retry_backoff_seconds=0,
    )
    client.app.state.document_ai_generator = GeminiDocumentGenerator(
        generator_settings, transport=httpx.MockTransport(handler)
    )
    letter = _first_letter(client, viewer_headers)

    generated = client.post(
        f"/api/v1/letters/{letter['id']}/ai-artifacts/summary",
        headers=viewer_headers,
    )

    assert generated.status_code == 200
    assert generated.json()["model_id"] == "gemini-3.5-flash"
    detail = client.get(f"/api/v1/letters/{letter['id']}", headers=viewer_headers).json()
    summary = next(item for item in detail["ai_artifacts"] if item["artifact_type"] == "summary")
    assert summary["model_id"] == "gemini-3.5-flash"


def test_quality_guarded_translation_fallback_model_id_is_persisted_and_reported(
    artifact_client: tuple[TestClient, FakeDocumentGenerator],
    viewer_headers: dict[str, str],
) -> None:
    client, _fake = artifact_client
    requested_models: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        model_id = request.url.path.split("/models/", maxsplit=1)[1].split(":")[0]
        requested_models.append(model_id)
        if model_id in {"gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash"}:
            return httpx.Response(503, json={"error": {"message": "temporarily unavailable"}})
        request_body = json.loads(request.content)
        prompt = request_body["contents"][0]["parts"][0]["text"]
        units = json.loads(prompt.split("\n", maxsplit=1)[1])["translation_units"]
        output = {
            "units": [
                {
                    "unit_id": item["unit_id"],
                    "translated_text": (
                        "FDA 원문을 생략 없이 충실하게 번역한 한국어 문장입니다. "
                        + " ".join(re.findall(r"\{\{FDA_TOKEN_\d{6}\}\}", item["text"]))
                    ),
                }
                for item in units
            ]
        }
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": json.dumps(output)}]}}]},
        )

    generator_settings = Settings(
        app_env="test",
        llm_provider="gemini",
        gemini_api_key="test-only-key",
        document_ai_attempts_per_model=1,
        document_ai_retry_backoff_seconds=0,
    )
    client.app.state.document_ai_generator = GeminiDocumentGenerator(
        generator_settings, transport=httpx.MockTransport(handler)
    )
    letter = _first_letter(client, viewer_headers)

    generated = client.post(
        f"/api/v1/letters/{letter['id']}/ai-artifacts/translation",
        headers=viewer_headers,
    )

    assert generated.status_code == 200
    assert generated.json()["model_id"] == "gemini-3.1-flash-lite"
    assert generated.json()["prompt_version"] == "letter-translation-ko-v4"
    assert requested_models == [
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.1-flash-lite",
    ]
    detail = client.get(f"/api/v1/letters/{letter['id']}", headers=viewer_headers).json()
    translation = next(
        item for item in detail["ai_artifacts"] if item["artifact_type"] == "translation"
    )
    assert translation["model_id"] == "gemini-3.1-flash-lite"


def test_findings_and_summary_share_one_cached_analysis_call(
    artifact_client: tuple[TestClient, FakeDocumentGenerator],
    viewer_headers: dict[str, str],
) -> None:
    client, generator = artifact_client
    letter = _first_letter(client, viewer_headers)
    base = f"/api/v1/letters/{letter['id']}/ai-artifacts"

    findings = client.post(f"{base}/findings", headers=viewer_headers)
    summary = client.post(f"{base}/summary", headers=viewer_headers)

    assert findings.status_code == summary.status_code == 200
    assert generator.analysis_calls == 1
    assert findings.json()["id"] == summary.json()["id"]
    assert findings.json()["content"]["findings"][0]["evidence_anchors"]
    assert summary.json()["content"]["executive_summary"]
    assert summary.json()["content"]["attention_points"][0]["source_anchors"]
    assert summary.json()["content"]["comparison_questions"]
    detail = client.get(f"/api/v1/letters/{letter['id']}", headers=viewer_headers).json()
    assert {item["artifact_type"] for item in detail["ai_artifacts"]} == {
        "findings",
        "summary",
    }


def test_analysis_artifacts_are_cached_independently_in_english_and_korean(
    artifact_client: tuple[TestClient, FakeDocumentGenerator],
    viewer_headers: dict[str, str],
) -> None:
    client, generator = artifact_client
    letter = _first_letter(client, viewer_headers)
    base = f"/api/v1/letters/{letter['id']}/ai-artifacts"

    english_findings = client.post(f"{base}/findings?language=en", headers=viewer_headers)
    english_summary = client.post(f"{base}/summary?language=en", headers=viewer_headers)
    korean_findings = client.post(f"{base}/findings?language=ko", headers=viewer_headers)
    korean_summary = client.post(f"{base}/summary?language=ko", headers=viewer_headers)

    assert all(
        response.status_code == 200
        for response in [english_findings, english_summary, korean_findings, korean_summary]
    )
    assert generator.analysis_calls == 2
    assert english_findings.json()["language"] == "en"
    assert korean_findings.json()["language"] == "ko"
    assert re.search(r"[A-Za-z]", english_summary.json()["content"]["executive_summary"])
    assert re.search(r"[가-힣]", korean_summary.json()["content"]["executive_summary"])

    detail = client.get(f"/api/v1/letters/{letter['id']}", headers=viewer_headers).json()
    assert {
        (item["artifact_type"], item["language"])
        for item in detail["ai_artifacts"]
    } == {
        ("findings", "en"),
        ("summary", "en"),
        ("findings", "ko"),
        ("summary", "ko"),
    }


def test_equal_concurrent_analysis_requests_are_coalesced(
    artifact_client: tuple[TestClient, FakeDocumentGenerator],
    viewer_headers: dict[str, str],
) -> None:
    client, generator = artifact_client
    letter = _first_letter(client, viewer_headers)
    base = f"/api/v1/letters/{letter['id']}/ai-artifacts"

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda artifact_type: client.post(
                    f"{base}/{artifact_type}?language=ko", headers=viewer_headers
                ),
                ["findings", "summary"],
            )
        )

    assert all(response.status_code == 200 for response in responses)
    assert generator.analysis_calls == 1
    assert responses[0].json()["id"] == responses[1].json()["id"]


def test_analysis_validation_failure_is_retried_before_failing_closed(
    artifact_client: tuple[TestClient, FakeDocumentGenerator],
    viewer_headers: dict[str, str],
) -> None:
    client, _generator = artifact_client
    recovering_generator = FakeDocumentGenerator(invalid_analysis_attempts=1)
    client.app.state.document_ai_generator = recovering_generator
    letter = _first_letter(client, viewer_headers)

    response = client.post(
        f"/api/v1/letters/{letter['id']}/ai-artifacts/findings?language=ko",
        headers=viewer_headers,
    )

    assert response.status_code == 200
    assert recovering_generator.analysis_calls == 2
    assert response.json()["content"]["findings"][0]["evidence_anchors"]


@pytest.mark.parametrize("artifact_type", ["translation", "findings"])
def test_unknown_model_anchor_is_rejected_without_partial_artifact(
    artifact_client: tuple[TestClient, FakeDocumentGenerator],
    viewer_headers: dict[str, str],
    artifact_type: str,
) -> None:
    client, _generator = artifact_client
    invalid = FakeDocumentGenerator(invalid_anchor=True)
    client.app.state.document_ai_generator = invalid
    letter = _first_letter(client, viewer_headers)

    response = client.post(
        f"/api/v1/letters/{letter['id']}/ai-artifacts/{artifact_type}",
        headers=viewer_headers,
    )

    assert response.status_code == 502
    detail = client.get(f"/api/v1/letters/{letter['id']}", headers=viewer_headers).json()
    assert detail["ai_artifacts"] == []

    if artifact_type == "translation":

        async def translation_count() -> int:
            database = Database(client.app.state.settings.database_url)
            try:
                async with database.session_factory() as session:
                    return int(
                        await session.scalar(select(func.count(DocumentTranslation.id))) or 0
                    )
            finally:
                await database.dispose()

        assert asyncio.run(translation_count()) == 0


def test_custom_generator_invented_token_is_rejected_without_persistence(
    artifact_client: tuple[TestClient, FakeDocumentGenerator],
    viewer_headers: dict[str, str],
) -> None:
    client, _generator = artifact_client
    client.app.state.document_ai_generator = FakeDocumentGenerator(invented_translation_token="999")
    letter = _first_letter(client, viewer_headers)

    response = client.post(
        f"/api/v1/letters/{letter['id']}/ai-artifacts/translation",
        headers=viewer_headers,
    )

    assert response.status_code == 502
    detail = client.get(f"/api/v1/letters/{letter['id']}", headers=viewer_headers).json()
    assert detail["ai_artifacts"] == []

    async def translation_count() -> int:
        database = Database(client.app.state.settings.database_url)
        try:
            async with database.session_factory() as session:
                return int(await session.scalar(select(func.count(DocumentTranslation.id))) or 0)
        finally:
            await database.dispose()

    assert asyncio.run(translation_count()) == 0


def test_letter_constrained_rag_uses_derived_context_but_cites_original_chunks(
    artifact_client: tuple[TestClient, FakeDocumentGenerator],
    viewer_headers: dict[str, str],
) -> None:
    client, document_generator = artifact_client
    letter = _first_letter(client, viewer_headers)
    generated = client.post(
        f"/api/v1/letters/{letter['id']}/ai-artifacts/summary",
        headers=viewer_headers,
    )
    assert generated.status_code == 200
    assert document_generator.analysis_calls == 1
    chat_generator = CapturingChatGenerator()
    client.app.state.ai_generator = chat_generator

    response = client.post(
        "/api/v1/rag/query",
        headers=viewer_headers,
        json={
            "question": "이 경고서에서 추가로 무엇을 검토해야 하나요?",
            "language": "ko",
            "filters": {"letter_id": letter["id"]},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["citations"]
    assert {item["warning_letter_id"] for item in body["citations"]} == {letter["id"]}
    assert chat_generator.passages
    assert chat_generator.history
    derived = chat_generator.history[0].content
    assert "UNTRUSTED DERIVED ARTIFACT CONTEXT" in derived
    assert "not FDA evidence or authority" in derived
    assert "핵심 FDA 지적 사항" in derived
    assert all(passage.excerpt for passage in chat_generator.passages)
