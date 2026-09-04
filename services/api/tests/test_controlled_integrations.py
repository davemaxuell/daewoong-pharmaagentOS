from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import A2AExchange, IntegrationOutbox, NotificationDelivery

ANALYST = {"X-Dev-User": "integration.analyst", "X-Dev-Roles": "analyst"}
REVIEWER = {"X-Dev-User": "integration.reviewer", "X-Dev-Roles": "reviewer"}
SERVICE = {"X-Dev-User": "svc:partner-agent", "X-Dev-Roles": "service"}


def _key(prefix: str) -> str:
    return f"{prefix}:{uuid4().hex}"


def _case(client: TestClient) -> dict:
    letter = client.get("/api/v1/letters", headers=ANALYST).json()["items"][0]
    source = client.get(f"/api/v1/letters/{letter['id']}", headers=ANALYST).json()[
        "current_version"
    ]
    response = client.post(
        "/api/v1/cases",
        headers={**ANALYST, "Idempotency-Key": _key("integration-case")},
        json={
            "title": "Controlled connector demonstration",
            "objective": "Prepare bounded drafts and expose answer-only case metadata.",
            "workflow_key": "regulatory-impact-review",
            "warning_letter_id": letter["id"],
            "document_version_id": source["id"],
            "source_role": "PRIMARY_REGULATORY",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_draft_only_connectors_read_only_documents_and_answer_only_a2a(
    client: TestClient,
) -> None:
    case = _case(client)

    async def counts() -> tuple[int, int, int]:
        async with client.app.state.database.session_factory() as session:
            return (
                int(
                    await session.scalar(select(func.count()).select_from(NotificationDelivery))
                    or 0
                ),
                int(await session.scalar(select(func.count()).select_from(IntegrationOutbox)) or 0),
                int(await session.scalar(select(func.count()).select_from(A2AExchange)) or 0),
            )

    before = asyncio.run(counts())
    request_key = _key("email-draft")
    payload = {
        "channel": "EMAIL",
        "destination": "quality-review@example.invalid",
        "title": "Manual review requested",
        "body": "Please inspect the cited evidence and decide whether SME review is needed.",
    }
    created = client.post(
        f"/api/v1/cases/{case['id']}/integration-drafts",
        headers={**ANALYST, "Idempotency-Key": request_key},
        json=payload,
    )
    assert created.status_code == 201, created.text
    draft = created.json()
    assert draft["status"] == "DRAFT"
    assert draft["action"] == "CREATE_DRAFT"
    assert draft["external_delivery_allowed"] is False
    replay = client.post(
        f"/api/v1/cases/{case['id']}/integration-drafts",
        headers={**ANALYST, "Idempotency-Key": request_key},
        json=payload,
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == draft["id"]

    prohibited = client.post(
        f"/api/v1/cases/{case['id']}/integration-drafts",
        headers={**ANALYST, "Idempotency-Key": _key("prohibited-draft")},
        json={
            **payload,
            "body": "Open a CAPA and reject the batch immediately.",
        },
    )
    assert prohibited.status_code == 422

    self_review = client.post(
        f"/api/v1/integration-drafts/{draft['id']}/review",
        headers=ANALYST,
        json={
            "decision": "review_for_manual_use",
            "expected_content_sha256": draft["content_sha256"],
            "reason": "Creator cannot review this draft independently.",
        },
    )
    assert self_review.status_code == 403
    reviewed = client.post(
        f"/api/v1/integration-drafts/{draft['id']}/review",
        headers=REVIEWER,
        json={
            "decision": "review_for_manual_use",
            "expected_content_sha256": draft["content_sha256"],
            "reason": "Content is suitable for a human to deliver manually.",
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["status"] == "REVIEWED_FOR_MANUAL_USE"
    assert reviewed.json()["external_delivery_allowed"] is False

    search = client.get(
        f"/api/v1/cases/{case['id']}/knowledge/search?q=audit&limit=1",
        headers=ANALYST,
    )
    assert search.status_code == 200, search.text
    version_id = search.json()["items"][0]["asset_version_id"]
    metadata = client.get(
        f"/api/v1/cases/{case['id']}/document-metadata/{version_id}",
        headers=ANALYST,
    )
    assert metadata.status_code == 200, metadata.text
    assert metadata.json()["integration_mode"] == "READ_ONLY"
    assert metadata.json()["access_filtered"] is True
    assert "content" not in metadata.json()

    card = client.get("/.well-known/agent-card.json")
    assert card.status_code == 200
    assert card.json()["capabilities"]["tool_delegation"] is False
    task_payload = {
        "task_key": _key("a2a-task"),
        "case_id": case["id"],
        "intent": "CASE_STATUS",
        "delegated_subject": ANALYST["X-Dev-User"],
        "delegated_roles": ["analyst"],
    }
    a2a = client.post("/api/v1/a2a/tasks", headers=SERVICE, json=task_payload)
    assert a2a.status_code == 201, a2a.text
    assert a2a.json()["answer_only"] is True
    assert a2a.json()["tool_delegation_allowed"] is False
    a2a_replay = client.post("/api/v1/a2a/tasks", headers=SERVICE, json=task_payload)
    assert a2a_replay.status_code == 201
    assert a2a_replay.json()["id"] == a2a.json()["id"]

    after = asyncio.run(counts())
    assert after[0] == before[0]  # no SMTP/provider delivery row was created
    assert after[1] == before[1] + 1
    assert after[2] == before[2] + 1

    inventory = client.get(
        "/api/v1/control-tower/inventory",
        headers={"X-Dev-User": "inventory.owner", "X-Dev-Roles": "system_owner"},
    )
    assert inventory.status_code == 200
    keys = {(item["kind"], item["key"]) for item in inventory.json()["items"]}
    assert ("AGENT_VERSION", "case-orchestrator") in keys
    assert ("AGENT_VERSION", "regulatory-evidence-agent") in keys
    assert ("SKILL_VERSION", "data-integrity-lens") in keys
    assert ("SKILL_VERSION", "report-language-guidelines") in keys
    assert ("TOOL_VERSION", "regulatory.get_anchor") in keys
    assert ("TOOL_VERSION", "workflow.create_email_draft") in keys
    kinds = [item["kind"] for item in inventory.json()["items"]]
    assert kinds.count("AGENT_VERSION") == 5
    assert kinds.count("SKILL_VERSION") == 10
    assert kinds.count("TOOL_VERSION") == 16
