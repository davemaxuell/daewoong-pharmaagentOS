from __future__ import annotations

import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.agent_platform.runtime.validation import validate_completion_payload
from app.models import (
    AgentInvocation,
    ApprovalRequest,
    Case,
    CaseRun,
    PlatformControl,
    ProcessingJob,
    RunEvent,
    WorkflowTemplateVersion,
    utcnow,
)
from tests.test_cases_api import (
    ANALYST,
    SYSTEM_OWNER,
    _approve_plan,
    _create_case,
    _create_plan,
    _idempotency,
    _regulatory_output,
    _run_one_worker_job,
    _start_run,
)


@pytest.mark.parametrize("usage", [
    {"cost_usd": float("nan")}, {"cost_usd": float("inf")},
    {"cost_usd": -1}, {"turns": True}, {"turns": 0.5},
    {"tool_calls": "0"}, {"unreported_resource": 1},
])
def test_internal_completion_rejects_invalid_usage(usage):
    with pytest.raises(HTTPException) as error:
        validate_completion_payload("RegulatoryFindingList@2.0.0", _regulatory_output(), usage)
    assert error.value.status_code == 422


@pytest.mark.parametrize("schema,output,status", [
    ("RegulatoryFindingList@2.0.0", {"findings": []}, 422),
    ("VerificationReport@1.0.0", {"valid": True, "issues": []}, 422),
    ("RegulatoryFindingList@9.0.0", {}, 409),
    ("../../untrusted.py", {}, 409),
])
def test_completion_contract_allowlist(schema, output, status):
    with pytest.raises(HTTPException) as error:
        validate_completion_payload(schema, output, {})
    assert error.value.status_code == status


@pytest.mark.parametrize("mutation", [
    "stale_case", "expired_approval", "revoked_approval", "wrong_attempt",
    "wrong_invocation", "suspended", "withdrawn_workflow", "malformed_output",
])
def test_rejected_completion_cannot_persist_output_or_queue_work(client, mutation, monkeypatch):
    case, _, _ = _create_case(client, title=f"Completion rejection {mutation}")
    plan, _, _ = _create_plan(client, case)
    _approve_plan(client, case, plan)
    run = _start_run(client, case, plan)
    _run_one_worker_job(client)
    active = client.get(f"/api/v1/runs/{run['id']}", headers=ANALYST).json()
    invocation_id = active["active_invocation"]["id"]

    async def counts(session):
        return (
            await session.scalar(select(func.count()).select_from(ProcessingJob)),
            await session.scalar(select(func.count()).select_from(RunEvent)),
        )

    async def exercise():
        async with client.app.state.database.session_factory() as session:
            bound_run = await session.get(CaseRun, run["id"])
            control = None
            if mutation == "stale_case":
                row = await session.get(Case, case["id"])
                row.current_state_hash = "f" * 64
            elif mutation in {"expired_approval", "revoked_approval"}:
                row = await session.scalar(select(ApprovalRequest).where(
                    ApprovalRequest.plan_id == plan["id"],
                    ApprovalRequest.approval_type == "PLAN_APPROVAL",
                ))
                if mutation == "expired_approval":
                    future = utcnow() + timedelta(days=8)
                    monkeypatch.setattr(
                        "app.agent_platform.runtime.validation.utcnow", lambda: future
                    )
                else:
                    row.status = "CANCELLED"
            elif mutation in {"wrong_attempt", "wrong_invocation"}:
                checkpoint = dict(bound_run.checkpoint)
                states = {key: dict(value) for key, value in checkpoint["steps"].items()}
                state = states["extract_evidence"]
                if mutation == "wrong_attempt":
                    state["attempt"] += 1
                else:
                    state["invocation_id"] = str(uuid4())
                checkpoint["steps"] = states
                bound_run.checkpoint = checkpoint
            elif mutation == "suspended":
                control = PlatformControl(
                    control_key="global", scope="GLOBAL", suspended=True,
                    reason="Completion rejection test",
                    updated_by="test-fixture",
                )
                session.add(control)
            elif mutation == "withdrawn_workflow":
                row = await session.get(
                    WorkflowTemplateVersion, bound_run.checkpoint["workflow_template"]["id"]
                )
                row.release_status = "SUSPENDED"
            await session.commit()
            before = await counts(session)
            return before, control.id if control else None

    before, control_id = asyncio.run(exercise())
    try:
        output = {"sensitive": "must not be echoed"} if mutation == "malformed_output" else (
            _regulatory_output()
        )
        response = client.post(
            f"/api/v1/runs/{run['id']}/steps/extract_evidence/result",
            headers={**SYSTEM_OWNER, "Idempotency-Key": _idempotency("rejected-result")},
            json={"expected_invocation_id": invocation_id, "output": output},
        )
        assert response.status_code == (422 if mutation == "malformed_output" else 409), (
            response.text
        )
        assert "must not be echoed" not in response.text

        async def verify():
            async with client.app.state.database.session_factory() as session:
                invocation = await session.get(AgentInvocation, invocation_id)
                assert invocation.status == "RUNNING"
                assert invocation.output_sha256 is None
                assert not invocation.output_payload
                assert await counts(session) == before
        asyncio.run(verify())
    finally:
        async def restore():
            async with client.app.state.database.session_factory() as session:
                if control_id:
                    control = await session.get(PlatformControl, control_id)
                    control.suspended = False
                if mutation == "withdrawn_workflow":
                    bound_run = await session.get(CaseRun, run["id"])
                    workflow = await session.get(
                        WorkflowTemplateVersion, bound_run.checkpoint["workflow_template"]["id"]
                    )
                    workflow.release_status = "APPROVED"
                await session.commit()
        asyncio.run(restore())
        cancelled = client.post(
            f"/api/v1/runs/{run['id']}/cancel",
            headers={**ANALYST, "Idempotency-Key": _idempotency("test-cleanup")},
            json={"reason": "Completion boundary test finished."},
        )
        assert cancelled.status_code == 200, cancelled.text
