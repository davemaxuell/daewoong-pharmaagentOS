from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.agent_platform.mcp.knowledge import (
    KnowledgeInvocationContext,
    KnowledgeMcpGateway,
)
from app.models import AgentVersion, ToolInvocation, ToolVersion
from app.security.auth import Principal
from app.worker import process_next_job

ANALYST = {"X-Dev-User": "knowledge.analyst", "X-Dev-Roles": "analyst"}
REVIEWER = {"X-Dev-User": "knowledge.reviewer", "X-Dev-Roles": "reviewer"}
DOMAIN_SME = {"X-Dev-User": "knowledge.sme", "X-Dev-Roles": "domain_sme"}


def _key(prefix: str) -> str:
    return f"{prefix}:{uuid4().hex}"


def _create_case(client: TestClient) -> dict:
    letters = client.get("/api/v1/letters", headers=ANALYST)
    assert letters.status_code == 200
    letter_id = next(
        item["id"]
        for item in letters.json()["items"]
        if item["review_state"] == "approved"
    )
    detail = client.get(f"/api/v1/letters/{letter_id}", headers=ANALYST)
    version = detail.json()["current_version"]
    response = client.post(
        "/api/v1/cases",
        headers={**ANALYST, "Idempotency-Key": _key("knowledge-case")},
        json={
            "title": "Synthetic internal impact review",
            "objective": "Compare retained FDA evidence with authorized fictional controls.",
            "workflow_key": "regulatory-impact-review",
            "warning_letter_id": letter_id,
            "document_version_id": version["id"],
            "source_role": "PRIMARY_REGULATORY",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_hybrid_retrieval_distinguishes_revisions_and_filters_acl(
    client: TestClient,
) -> None:
    case = _create_case(client)
    path = f"/api/v1/cases/{case['id']}/knowledge/search"
    current = client.get(
        path,
        headers=ANALYST,
        params={"q": "data integrity audit trail review", "limit": 20},
    )
    assert current.status_code == 200, current.text
    body = current.json()
    assert body["acl_filtered_before_ranking"] is True
    assert "demonstration" in body["corpus_notice"].lower()
    assert "SOP-DI-004" in {item["asset_key"] for item in body["items"]}
    assert "SYS-LIMS-007" not in {item["asset_key"] for item in body["items"]}
    assert all(item["effective_status"] == "EFFECTIVE" for item in body["items"])

    history_search = client.get(
        path,
        headers=ANALYST,
        params={
            "q": "audit trail review",
            "limit": 20,
            "include_obsolete": True,
        },
    )
    assert history_search.status_code == 200
    sop_revisions = [
        (item["revision"], item["effective_status"])
        for item in history_search.json()["items"]
        if item["asset_key"] == "SOP-DI-004"
    ]
    assert set(sop_revisions) == {(1, "OBSOLETE"), (2, "EFFECTIVE")}

    sop = next(item for item in body["items"] if item["asset_key"] == "SOP-DI-004")
    revision_response = client.get(
        f"/api/v1/cases/{case['id']}/knowledge/assets/{sop['asset_id']}/revisions",
        headers=ANALYST,
    )
    assert revision_response.status_code == 200
    assert [item["status"] for item in revision_response.json()["revisions"]] == [
        "EFFECTIVE",
        "OBSOLETE",
    ]

    related = client.get(
        f"/api/v1/cases/{case['id']}/knowledge/assets/{sop['asset_id']}/related",
        headers=ANALYST,
    )
    assert related.status_code == 200
    assert any(item["asset"]["asset_key"] == "FRM-DI-011" for item in related.json()["items"])
    assert all(len(item["evidence"]) >= 2 for item in related.json()["items"])

    restricted_search = client.get(
        path,
        headers=DOMAIN_SME,
        params={"q": "laboratory results immutable audit events", "limit": 20},
    )
    restricted = next(
        item
        for item in restricted_search.json()["items"]
        if item["asset_key"] == "SYS-LIMS-007"
    )
    denied = client.get(
        f"/api/v1/cases/{case['id']}/knowledge/assets/{restricted['asset_id']}",
        headers=ANALYST,
    )
    missing = client.get(
        f"/api/v1/cases/{case['id']}/knowledge/assets/{uuid4()}",
        headers=ANALYST,
    )
    assert denied.status_code == missing.status_code == 404
    assert denied.json()["detail"] == missing.json()["detail"]
    assert "LIMS" not in denied.text


def test_impact_hypotheses_have_dual_evidence_and_independent_review(
    client: TestClient,
) -> None:
    case = _create_case(client)
    generate_key = _key("impact-generate")
    response = client.post(
        f"/api/v1/cases/{case['id']}/impact/generate",
        headers={**ANALYST, "Idempotency-Key": generate_key},
        json={"query": "data integrity audit trail review", "per_finding_limit": 5},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["generated_count"] > 0
    assert body["items"]
    for item in body["items"]:
        assert item["external_evidence"]
        assert item["internal_evidence"]
        assert item["assumptions"] and item["counterevidence"] and item["unknowns"]
        assert item["decision_support_only"] is True
        assert "not a compliance" in item["statement"]

    replay = client.post(
        f"/api/v1/cases/{case['id']}/impact/generate",
        headers={**ANALYST, "Idempotency-Key": generate_key},
        json={"query": "data integrity audit trail review", "per_finding_limit": 5},
    )
    assert replay.status_code == 200
    assert {item["id"] for item in replay.json()["items"]} == {
        item["id"] for item in body["items"]
    }

    item = body["items"][0]
    decision_path = f"/api/v1/cases/{case['id']}/impact/{item['id']}/decision"
    stale = client.post(
        decision_path,
        headers={**REVIEWER, "Idempotency-Key": _key("impact-stale")},
        json={
            "decision": "accept",
            "expected_hypothesis_sha256": "0" * 64,
            "reason": "Review attempted against stale content.",
        },
    )
    assert stale.status_code == 409
    accepted = client.post(
        decision_path,
        headers={**REVIEWER, "Idempotency-Key": _key("impact-accept")},
        json={
            "decision": "accept",
            "expected_hypothesis_sha256": item["hypothesis_sha256"],
            "reason": "Both cited evidence paths support retaining this as a hypothesis.",
        },
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "ACCEPTED"
    assert accepted.json()["reviewed_by"] == REVIEWER["X-Dev-User"]


def test_knowledge_mcp_requires_exact_plan_binding_and_attributes_replay(
    client: TestClient,
) -> None:
    case = _create_case(client)

    async def registry_ids() -> tuple[str, str]:
        async with client.app.state.database.session_factory() as session:
            agent_id = await session.scalar(
                select(AgentVersion.id).where(
                    AgentVersion.agent_key == "internal-knowledge-agent",
                    AgentVersion.version == "1.1.0",
                )
            )
            tool_id = await session.scalar(
                select(ToolVersion.id).where(
                    ToolVersion.tool_key == "knowledge.search_assets",
                    ToolVersion.version == "1.0.0",
                )
            )
            assert agent_id and tool_id
            return agent_id, tool_id

    agent_id, tool_id = asyncio.run(registry_ids())
    plan = client.post(
        f"/api/v1/cases/{case['id']}/plans",
        headers={**ANALYST, "Idempotency-Key": _key("knowledge-mcp-plan")},
        json={
            "plan_schema_version": "1.0.0",
            "assigned_reviewer_id": REVIEWER["X-Dev-User"],
            "steps": [
                {
                    "step_key": "internal_knowledge",
                    "title": "Retrieve authorized internal evidence",
                    "instructions": "Use only the approved ACL-filtered knowledge tool.",
                    "depends_on": [],
                    "agent_version_id": agent_id,
                    "skill_version_ids": [],
                    "tool_version_ids": [tool_id],
                    "output_schema_ref": "InternalAssetCandidateList@1.0.0",
                    "risk_level": "R1",
                    "requires_approval": False,
                    "limits": {
                        "max_turns": 2,
                        "max_tool_calls": 5,
                        "max_input_tokens": 10000,
                        "max_output_tokens": 2000,
                        "max_runtime_seconds": 60,
                        "max_cost_usd": 1,
                    },
                }
            ],
        },
    )
    assert plan.status_code == 201, plan.text
    plan_body = plan.json()
    approved = client.post(
        f"/api/v1/cases/{case['id']}/plans/{plan_body['version']}/approve",
        headers={**REVIEWER, "Idempotency-Key": _key("knowledge-mcp-approval")},
        json={
            "decision": "approve",
            "expected_plan_sha256": plan_body["plan_sha256"],
            "expected_state_hash": plan_body["based_on_state_hash"],
            "reason": "The internal retrieval step is narrow and read-only.",
        },
    )
    assert approved.status_code == 200, approved.text
    run_response = client.post(
        f"/api/v1/cases/{case['id']}/runs",
        headers={**ANALYST, "Idempotency-Key": _key("knowledge-mcp-run")},
        json={
            "plan_version": plan_body["version"],
            "expected_plan_sha256": plan_body["plan_sha256"],
            "expected_state_hash": plan_body["based_on_state_hash"],
        },
    )
    assert run_response.status_code == 201, run_response.text
    run_id = run_response.json()["id"]
    asyncio.run(process_next_job(client.app.state.database, client.app.state.settings))

    context = KnowledgeInvocationContext(
        principal=Principal(ANALYST["X-Dev-User"], frozenset({"analyst"})),
        tenant_id="synthetic-tenant",
        case_id=case["id"],
        case_state_hash=case["current_state_hash"],
        run_id=run_id,
        agent_name="internal-knowledge-agent",
        agent_version="1.1.0",
        runtime_service="pharma-agent-runtime",
        idempotency_key=f"knowledge-search:{uuid4().hex}",
        scopes=frozenset({"knowledge:search"}),
        user_authenticated=True,
        runtime_authenticated=True,
    )

    async def invoke_twice() -> tuple[dict, dict, int]:
        async with client.app.state.database.session_factory() as session:
            gateway = KnowledgeMcpGateway(
                session, application_version=client.app.state.settings.app_version
            )
            first = await gateway.invoke(
                tool_name="knowledge.search_assets",
                arguments={
                    "query": "data integrity audit trail",
                    "limit": 10,
                    "include_obsolete": False,
                },
                context=context,
            )
        async with client.app.state.database.session_factory() as session:
            second = await KnowledgeMcpGateway(session).invoke(
                tool_name="knowledge.search_assets",
                arguments={
                    "query": "data integrity audit trail",
                    "limit": 10,
                    "include_obsolete": False,
                },
                context=context,
            )
            count = await session.scalar(
                select(func.count()).select_from(ToolInvocation).where(
                    ToolInvocation.run_id == run_id,
                    ToolInvocation.tool_name == "knowledge.search_assets",
                )
            )
        return first, second, int(count or 0)

    first, second, count = asyncio.run(invoke_twice())
    assert first["status"] == "success", first
    assert first == second
    assert count == 1
    assert first["data"]["acl_filtered_before_retrieval"] is True
    assert "SYS-LIMS-007" not in {
        item["asset_key"] for item in first["data"]["records"]
    }

    denied_context = KnowledgeInvocationContext(
        **{
            **context.__dict__,
            "agent_name": "impact-analysis-agent",
            "agent_version": "1.0.2",
            "idempotency_key": f"wrong-agent:{uuid4().hex}",
        }
    )
    async def invoke_denied() -> dict:
        async with client.app.state.database.session_factory() as session:
            return await KnowledgeMcpGateway(session).invoke(
                tool_name="knowledge.search_assets",
                arguments={"query": "audit trail", "limit": 5, "include_obsolete": False},
                context=denied_context,
            )

    denied = asyncio.run(invoke_denied())
    assert denied["status"] == "error"
    assert denied["error"]["code"] == "PERMISSION_DENIED"
