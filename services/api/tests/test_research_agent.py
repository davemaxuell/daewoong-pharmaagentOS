import asyncio
import json
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.ai import AiGenerationError
from app.models import DocumentChunk, ResearchRun, utcnow
from app.research.provider import ToolProposal
from app.research.schemas import MAX_MODEL_CALLS, EvidenceCheck
from app.research.tools import evidence_is_current, read_sources, search_sources
from app.research.worker import LeaseLost, claim, mutate, run_research_slice


def proposal(name, args):
    call_id = "call_" + uuid4().hex
    return ToolProposal(
        name,
        args,
        call_id,
        [
            {
                "type": "function_call",
                "call_id": call_id,
                "name": name,
                "arguments": json.dumps(args),
            }
        ],
        100,
    )


class ScriptedModel:
    """Harness fixture only; hosted qualification uses actual OpenAI calls."""

    model_id = "scripted-test"

    def __init__(self, *, reject_first=False, fail_once=False, bad_citation=False):
        self.reject_first = reject_first
        self.fail_once = fail_once
        self.bad_citation = bad_citation
        self.checks = 0
        self.calls = 0

    async def propose(self, conversation, remaining):
        self.calls += 1
        if self.fail_once:
            self.fail_once = False
            raise AiGenerationError("fixture outage")
        outputs = [
            json.loads(item["output"])
            for item in conversation
            if item.get("type") == "function_call_output"
        ]
        if not outputs:
            return proposal(
                "plan_research", {"steps": ["Search FDA passages", "Read and cite findings"]}
            )
        if len(outputs) == 1:
            return proposal("search_sources", {"query": "validation"})
        if len(outputs) == 2:
            return proposal("read_sources", {"chunk_ids": [outputs[-1]["matches"][0]["chunk_id"]]})
        return proposal(
            "submit_brief",
            {
                "title": "FDA validation review brief",
                "findings": [
                    {
                        "statement": "The source company received an FDA validation finding.",
                        "citation_ids": ["S999" if self.bad_citation else "S1"],
                    }
                ],
                "review_questions": ["Which validation controls should our team review?"],
                "limitations": [
                    "These public FDA observations do not establish our company's compliance."
                ],
            },
        )

    async def verify(self, brief, evidence, language):
        self.checks += 1
        if self.reject_first and self.checks == 1:
            return EvidenceCheck(
                supported=False, issues=["Attribute the finding more precisely"]
            ), 100
        return EvidenceCheck(supported=True, issues=[]), 100


@pytest.fixture
def research(client, monkeypatch):
    monkeypatch.setattr(client.app.state.settings, "research_agent_enabled", True)
    monkeypatch.setattr(client.app.state, "research_model", ScriptedModel())
    headers = {"X-Dev-User": "research-" + uuid4().hex, "X-Dev-Roles": "viewer"}
    yield client, headers, client.app.state.database
    for run in client.get("/api/v1/research/runs", headers=headers).json()["items"]:
        if run["status"] in {"queued", "running"}:
            client.post(f"/api/v1/research/runs/{run['id']}/stop", headers=headers)


def create(research, **overrides):
    client, headers, _ = research
    body = {
        "objective": "Prepare an FDA validation briefing",
        "language": "en",
        "client_request_id": str(uuid4()),
        **overrides,
    }
    response = client.post("/api/v1/research/runs", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json(), body


def test_disabled_model_blocks_resume_but_allows_stop(research, monkeypatch):
    client, headers, _ = research
    run, _ = create(research)
    monkeypatch.setattr(client.app.state, "research_model", None)
    path = f"/api/v1/research/runs/{run['id']}"
    assert client.post(path + "/stop", headers=headers).status_code == 200
    assert client.post(path + "/resume", headers=headers).status_code == 503
    assert client.get(path, headers=headers).json()["status"] == "stopped"


def get(research, run_id, after=0):
    client, headers, _ = research
    return client.get(f"/api/v1/research/runs/{run_id}?after={after}", headers=headers).json()


def execute(research, model=None):
    client, _, database = research
    return asyncio.run(
        run_research_slice(database, client.app.state.settings, model=model or ScriptedModel())
    )


def test_session_ownership_idempotency_and_private_checkpoint(research):
    client, headers, _ = research
    run, body = create(research)
    repeated = client.post("/api/v1/research/runs", json=body, headers=headers)
    assert repeated.json()["id"] == run["id"]
    assert "no-store" in repeated.headers["cache-control"]
    assert "checkpoint" not in run and "owner_id" not in run
    assert (
        client.post(
            "/api/v1/research/runs",
            json={**body, "objective": "Different objective"},
            headers=headers,
        ).status_code
        == 409
    )
    stranger = {**headers, "X-Dev-User": "another-session"}
    path = f"/api/v1/research/runs/{run['id']}"
    for suffix in ("", "/stop", "/resume"):
        method = client.get if not suffix else client.post
        assert method(path + suffix, headers=stranger).status_code == 404
    assert client.get("/api/v1/research/runs", headers=stranger).json()["items"] == []
    assert client.get(path).status_code == 401
    client.post(path + "/stop", headers=headers)


def test_agent_runs_real_tools_and_persists_checked_brief(research):
    run, _ = create(research)
    model = ScriptedModel(reject_first=True)
    execute(research, model)
    result = get(research, run["id"])
    assert result["status"] == "completed"
    assert model.checks == 2
    assert result["result"]["sources"][0]["id"] == "S1"
    kinds = [event["kind"] for event in result["events"]]
    assert "search_started" in kinds and "read_completed" in kinds
    assert "check_needs_revision" in kinds and kinds[-1] == "completed"
    assert len({event["sequence"] for event in result["events"]}) == len(kinds)
    assert get(research, run["id"], result["revision"])["events"] == []
    assert "conversation" not in json.dumps(result)


def test_invalid_citations_cannot_complete_and_budget_is_enforced(research):
    run, _ = create(research)
    model = ScriptedModel(bad_citation=True)
    execute(research, model)
    result = get(research, run["id"])
    assert result["status"] == "limit_reached"
    assert result["result"] is None
    assert result["model_calls"] == MAX_MODEL_CALLS
    assert model.checks == 0
    assert not result["can_resume"]


def test_model_outage_can_resume_from_saved_progress(research):
    client, headers, _ = research
    run, _ = create(research)
    execute(research, ScriptedModel(fail_once=True))
    assert get(research, run["id"])["status"] == "failed"
    response = client.post(f"/api/v1/research/runs/{run['id']}/resume", headers=headers)
    assert response.status_code == 200
    execute(research)
    assert get(research, run["id"])["status"] == "completed"


def test_stop_fences_inflight_worker_and_preserves_state(research):
    client, headers, database = research
    run, _ = create(research)
    claimed = asyncio.run(claim(database))
    assert claimed.id == run["id"]
    assert (
        client.post(f"/api/v1/research/runs/{run['id']}/stop", headers=headers).status_code == 200
    )

    async def late_write():
        with pytest.raises(LeaseLost):
            await mutate(
                database,
                claimed.id,
                claimed.lease_id,
                lambda _session, current: setattr(current, "status", "completed"),
            )

    asyncio.run(late_write())
    assert get(research, run["id"])["status"] == "stopped"


def test_expired_worker_lease_is_reclaimed_with_a_new_fence(research):
    _, _, database = research
    run, _ = create(research)

    async def recover():
        first = await claim(database)
        await mutate(
            database,
            first.id,
            first.lease_id,
            lambda _s, current: setattr(
                current, "lease_expires_at", utcnow() - timedelta(seconds=1)
            ),
        )
        second = await claim(database)
        assert second.id == first.id and second.lease_id != first.lease_id
        with pytest.raises(LeaseLost):
            await mutate(database, first.id, first.lease_id, lambda _s, _r: None)
        return second

    asyncio.run(recover())
    client, headers, _ = research
    client.post(f"/api/v1/research/runs/{run['id']}/stop", headers=headers)


def test_source_tools_enforce_current_public_scope_and_integrity(research):
    _, _, database = research

    async def check():
        found = await search_sources(database, "validation")
        assert found
        sources = await read_sources(database, [found[0]["chunk_id"]])
        assert await evidence_is_current(database, sources)
        async with database.session_factory() as session:
            chunk = await session.get(DocumentChunk, found[0]["chunk_id"])
            old_acl = chunk.acl
            chunk.acl = {"roles": ["reviewer"]}
            await session.commit()
        try:
            assert not await read_sources(database, [found[0]["chunk_id"]])
            assert not await evidence_is_current(database, sources)
            assert all(
                item["chunk_id"] != found[0]["chunk_id"]
                for item in await search_sources(database, "validation")
            )
        finally:
            async with database.session_factory() as session:
                chunk = await session.get(DocumentChunk, found[0]["chunk_id"])
                chunk.acl = old_acl
                await session.commit()

    asyncio.run(check())


def test_active_task_admission_limit(research):
    client, headers, _ = research
    first, _ = create(research)
    second, _ = create(research)
    response = client.post(
        "/api/v1/research/runs",
        json={
            "objective": "Prepare another research brief",
            "language": "en",
            "client_request_id": str(uuid4()),
        },
        headers=headers,
    )
    assert response.status_code == 429
    for run in (first, second):
        client.post(f"/api/v1/research/runs/{run['id']}/stop", headers=headers)


def test_unconfigured_research_fails_without_creating_a_task(research, monkeypatch):
    client, headers, database = research
    monkeypatch.setattr(client.app.state, "research_model", None)
    response = client.post(
        "/api/v1/research/runs",
        json={
            "objective": "Prepare an FDA briefing",
            "language": "en",
            "client_request_id": str(uuid4()),
        },
        headers=headers,
    )
    assert response.status_code == 503

    async def count():
        async with database.session_factory() as session:
            return (
                await session.scalars(
                    select(ResearchRun).where(ResearchRun.owner_id == headers["X-Dev-User"])
                )
            ).all()

    assert not asyncio.run(count())
