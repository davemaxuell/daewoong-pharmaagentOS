from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.agent_platform.temporal.activities import execute_advance_activity
from app.models import AgentVersion, DurableActivity, PlatformControl

ANALYST = {"X-Dev-User": "hardening.analyst", "X-Dev-Roles": "analyst"}
REVIEWER = {"X-Dev-User": "hardening.reviewer", "X-Dev-Roles": "reviewer"}
PLATFORM_ADMIN = {"X-Dev-User": "hardening.platform", "X-Dev-Roles": "platform_admin"}
VIEWER = {"X-Dev-User": "hardening.viewer", "X-Dev-Roles": "viewer"}


def _key(prefix: str) -> str:
    return f"{prefix}:{uuid4().hex}"


def _agent_id(client: TestClient) -> str:
    async def load() -> str:
        async with client.app.state.database.session_factory() as session:
            agent = await session.scalar(
                select(AgentVersion).where(AgentVersion.agent_key == "verification-agent")
            )
            assert agent is not None
            return agent.id

    return asyncio.run(load())


def _ready_case(client: TestClient, agent_id: str, title: str) -> tuple[dict, dict]:
    letters = client.get("/api/v1/letters", headers=ANALYST).json()["items"]
    detail = client.get(f"/api/v1/letters/{letters[0]['id']}", headers=ANALYST).json()
    source = detail["current_version"]
    created = client.post(
        "/api/v1/cases",
        headers={**ANALYST, "Idempotency-Key": _key("hardening-case")},
        json={
            "title": title,
            "objective": "Execute one bounded verification step under durable controls.",
            "workflow_key": "regulatory-impact-review",
            "warning_letter_id": letters[0]["id"],
            "document_version_id": source["id"],
            "source_role": "PRIMARY_REGULATORY",
        },
    )
    assert created.status_code == 201, created.text
    case = created.json()
    planned = client.post(
        f"/api/v1/cases/{case['id']}/plans",
        headers={**ANALYST, "Idempotency-Key": _key("hardening-plan")},
        json={
            "plan_schema_version": "1.0.0",
            "assigned_reviewer_id": "hardening.reviewer",
            "steps": [
                {
                    "step_key": "verify",
                    "title": "Verify retained evidence",
                    "instructions": "Inspect only the exact pinned evidence and return a report.",
                    "depends_on": [],
                    "agent_version_id": agent_id,
                    "skill_version_ids": [],
                    "tool_version_ids": [],
                    "output_schema_ref": "VerificationReport@1.2.1",
                    "risk_level": "R1",
                    "requires_approval": False,
                    "limits": {
                        "max_turns": 2,
                        "max_tool_calls": 2,
                        "max_input_tokens": 2000,
                        "max_output_tokens": 1000,
                        "max_runtime_seconds": 30,
                        "max_cost_usd": 0.25,
                    },
                }
            ],
        },
    )
    assert planned.status_code == 201, planned.text
    plan = planned.json()
    approved = client.post(
        f"/api/v1/cases/{case['id']}/plans/{plan['version']}/approve",
        headers={**REVIEWER, "Idempotency-Key": _key("hardening-approval")},
        json={
            "decision": "approve",
            "expected_plan_sha256": plan["plan_sha256"],
            "expected_state_hash": plan["based_on_state_hash"],
            "reason": "The single read-only step is bounded and ready.",
        },
    )
    assert approved.status_code == 200, approved.text
    return case, plan


def _start(client: TestClient, case: dict, plan: dict):
    return client.post(
        f"/api/v1/cases/{case['id']}/runs",
        headers={**ANALYST, "Idempotency-Key": _key("hardening-run")},
        json={
            "plan_version": plan["version"],
            "expected_plan_sha256": plan["plan_sha256"],
            "expected_state_hash": plan["based_on_state_hash"],
        },
    )


def test_kill_switches_quotas_and_durable_activity_replay(client: TestClient) -> None:
    agent_id = _agent_id(client)
    case, plan = _ready_case(client, agent_id, "Suspension-controlled workflow")

    assert client.get("/api/v1/control-tower/controls", headers=VIEWER).status_code == 403
    per_agent = client.put(
        f"/api/v1/control-tower/controls/agents/{agent_id}",
        headers=PLATFORM_ADMIN,
        json={
            "suspended": True,
            "reason": "Security drill suspends this exact agent version.",
        },
    )
    assert per_agent.status_code == 200, per_agent.text
    assert _start(client, case, plan).status_code == 503
    stale = client.put(
        f"/api/v1/control-tower/controls/agents/{agent_id}",
        headers=PLATFORM_ADMIN,
        json={
            "suspended": False,
            "reason": "Attempted stale control update for concurrency coverage.",
            "expected_revision": 99,
        },
    )
    assert stale.status_code == 409
    resumed_agent = client.put(
        f"/api/v1/control-tower/controls/agents/{agent_id}",
        headers=PLATFORM_ADMIN,
        json={
            "suspended": False,
            "reason": "Security drill completed and agent is cleared.",
            "expected_revision": per_agent.json()["revision"],
        },
    )
    assert resumed_agent.status_code == 200

    global_control = client.put(
        "/api/v1/control-tower/controls/global",
        headers=PLATFORM_ADMIN,
        json={"suspended": True, "reason": "Global incident-response exercise is active."},
    )
    assert global_control.status_code == 200
    assert _start(client, case, plan).status_code == 503
    cleared = client.put(
        "/api/v1/control-tower/controls/global",
        headers=PLATFORM_ADMIN,
        json={
            "suspended": False,
            "reason": "Global incident-response exercise is complete.",
            "expected_revision": global_control.json()["revision"],
        },
    )
    assert cleared.status_code == 200

    started = _start(client, case, plan)
    assert started.status_code == 201, started.text
    run = started.json()
    activity_payload = {
        "run_id": run["id"],
        "workflow_id": f"pharma-case-{run['id']}",
        "activity_key": "advance:1",
    }
    first = asyncio.run(execute_advance_activity(client.app.state.database, activity_payload))
    replay = asyncio.run(execute_advance_activity(client.app.state.database, activity_payload))
    assert first == replay
    assert first["status"] == "RUNNING"

    async def count_activities() -> int:
        async with client.app.state.database.session_factory() as session:
            return int(await session.scalar(select(func.count()).select_from(DurableActivity)) or 0)

    assert asyncio.run(count_activities()) == 1

    second_case, second_plan = _ready_case(client, agent_id, "Quota-controlled workflow")
    previous_limit = client.app.state.settings.agent_active_runs_per_subject
    client.app.state.settings.agent_active_runs_per_subject = 1
    try:
        quota_denied = _start(client, second_case, second_plan)
        assert quota_denied.status_code == 429
        assert quota_denied.headers["Retry-After"] == "60"
    finally:
        client.app.state.settings.agent_active_runs_per_subject = previous_limit


def test_durable_failure_rolls_back_partial_business_writes(client, monkeypatch):
    case, plan = _ready_case(client, _agent_id(client), "Failure atomicity")
    run = _start(client, case, plan).json()
    control_key = f"failure-canary:{uuid4().hex}"

    async def failing_advance(session, **kwargs):
        session.add(
            PlatformControl(
                control_key=control_key,
                scope="GLOBAL",
                suspended=False,
                reason="Must be rolled back",
                updated_by="test",
            )
        )
        await session.flush()
        raise RuntimeError("Injected failure after flush")

    monkeypatch.setattr("app.agent_platform.temporal.activities.advance_case_run", failing_advance)

    async def verify():
        with pytest.raises(RuntimeError, match="Durable case activity failed"):
            await execute_advance_activity(
                client.app.state.database,
                {
                    "run_id": run["id"],
                    "workflow_id": control_key,
                    "activity_key": "advance:1",
                },
            )
        async with client.app.state.database.session_factory() as session:
            assert (
                await session.scalar(
                    select(PlatformControl).where(PlatformControl.control_key == control_key)
                )
                is None
            )
            journal = await session.scalar(
                select(DurableActivity).where(DurableActivity.temporal_workflow_id == control_key)
            )
            assert journal.status == "FAILED"

    asyncio.run(verify())


@pytest.mark.skipif(
    not os.getenv("TEMPORAL_TEST_ADDRESS"), reason="requires an isolated Temporal test server"
)
def test_live_temporal_resumes_history_with_replacement_worker(client):
    from temporalio.client import Client, WorkflowFailureError
    from temporalio.worker import Worker

    from app.agent_platform.temporal.activities import CaseActivities
    from app.agent_platform.temporal.workflow import PharmaCaseOuterWorkflow

    case, plan = _ready_case(client, _agent_id(client), "Temporal worker replacement")
    run = _start(client, case, plan).json()

    async def verify():
        connection = await Client.connect(
            os.environ["TEMPORAL_TEST_ADDRESS"], namespace="pharma-agent-os"
        )
        queue = f"qualification-{uuid4().hex}"
        activities = CaseActivities(client.app.state.database)

        def worker():
            return Worker(
                connection,
                task_queue=queue,
                workflows=[PharmaCaseOuterWorkflow],
                activities=[activities.advance_case_run_activity],
            )

        async def wait_for_cycle(handle, cycle):
            async with asyncio.timeout(45):
                while (await handle.query(PharmaCaseOuterWorkflow.state))["cycle"] < cycle:
                    await asyncio.sleep(0.2)

        async with worker():
            handle = await connection.start_workflow(
                PharmaCaseOuterWorkflow.run,
                {"run_id": run["id"]},
                id=f"pharma-qualification-{uuid4().hex}",
                task_queue=queue,
            )
            await wait_for_cycle(handle, 1)
        # No worker is running: this signal must survive the worker boundary.
        await handle.signal(PharmaCaseOuterWorkflow.wake)
        async with worker():
            await wait_for_cycle(handle, 2)
            await handle.cancel()
            with pytest.raises(WorkflowFailureError):
                await handle.result()
        async with client.app.state.database.session_factory() as session:
            journals = (
                await session.scalars(
                    select(DurableActivity).where(DurableActivity.case_run_id == run["id"])
                )
            ).all()
            assert len(journals) >= 2
            assert all(item.status == "SUCCEEDED" for item in journals)
            assert all(item.attempts == 1 for item in journals)

    asyncio.run(verify())
