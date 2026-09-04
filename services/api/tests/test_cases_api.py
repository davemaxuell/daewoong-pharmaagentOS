from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.cases import router as cases_router
from app.models import AuditEvent
from app.worker import process_next_job

ANALYST = {"X-Dev-User": "case.analyst", "X-Dev-Roles": "analyst"}
OTHER_ANALYST = {"X-Dev-User": "other.case.analyst", "X-Dev-Roles": "analyst"}
REVIEWER = {"X-Dev-User": "case.reviewer", "X-Dev-Roles": "reviewer"}
DOMAIN_SME = {"X-Dev-User": "case.sme", "X-Dev-Roles": "domain_sme"}
AUDITOR = {"X-Dev-User": "case.auditor", "X-Dev-Roles": "auditor"}
SYSTEM_OWNER = {"X-Dev-User": "case.owner", "X-Dev-Roles": "system_owner"}
ADMIN = {"X-Dev-User": "case.admin", "X-Dev-Roles": "admin"}
PLATFORM_ADMIN = {"X-Dev-User": "platform.admin", "X-Dev-Roles": "platform_admin"}
VIEWER = {"X-Dev-User": "case.viewer", "X-Dev-Roles": "viewer"}


def _idempotency(prefix: str) -> str:
    return f"{prefix}:{uuid4().hex}"


def _source(client: TestClient) -> tuple[str, dict[str, object]]:
    letters_response = client.get("/api/v1/letters", headers=ANALYST)
    assert letters_response.status_code == 200
    letter_id = letters_response.json()["items"][0]["id"]
    detail_response = client.get(f"/api/v1/letters/{letter_id}", headers=ANALYST)
    assert detail_response.status_code == 200
    version = detail_response.json()["current_version"]
    assert version is not None
    return letter_id, version


def _case_payload(client: TestClient, *, title: str = "Regulatory impact review") -> dict:
    letter_id, version = _source(client)
    return {
        "title": title,
        "objective": "Assess the retained FDA evidence and prepare a bounded review plan.",
        "workflow_key": "regulatory-impact-review",
        "warning_letter_id": letter_id,
        "document_version_id": version["id"],
        "source_role": "PRIMARY_REGULATORY",
    }


def _create_case(
    client: TestClient,
    *,
    headers: dict[str, str] = ANALYST,
    title: str = "Regulatory impact review",
    request_id: str | None = None,
) -> tuple[dict, str, dict]:
    payload = _case_payload(client, title=title)
    key = _idempotency("case-create")
    request_headers = {**headers, "Idempotency-Key": key}
    if request_id:
        request_headers["X-Request-ID"] = request_id
    response = client.post("/api/v1/cases", headers=request_headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json(), key, payload


def _plan_payload(*, reviewer: str | None = "case.reviewer") -> dict:
    payload = {
        "plan_schema_version": "1.0.0",
        "steps": [
            {
                "step_key": "extract_evidence",
                "title": "Extract evidence",
                "instructions": (
                    "Read only the pinned source and produce cited structured evidence."
                ),
                "depends_on": [],
                "agent_version_id": None,
                "skill_version_ids": [],
                "tool_version_ids": [],
                "output_schema_ref": "RegulatoryFindingList@2.0.0",
                "risk_level": "R1",
                "requires_approval": False,
                "limits": {
                    "max_turns": 4,
                    "max_tool_calls": 12,
                    "max_input_tokens": 80000,
                    "max_output_tokens": 12000,
                    "max_runtime_seconds": 240,
                    "max_cost_usd": 3.5,
                },
            },
            {
                "step_key": "verify_evidence",
                "title": "Verify evidence",
                "instructions": "Independently validate every exact citation anchor.",
                "depends_on": ["extract_evidence"],
                "agent_version_id": None,
                "skill_version_ids": [],
                "tool_version_ids": [],
                "output_schema_ref": "VerificationReport@1.0.0",
                "risk_level": "R2",
                "requires_approval": True,
                "limits": {
                    "max_turns": 3,
                    "max_tool_calls": 8,
                    "max_input_tokens": 50000,
                    "max_output_tokens": 8000,
                    "max_runtime_seconds": 180,
                    "max_cost_usd": 2.0,
                },
            },
        ],
    }
    if reviewer is not None:
        payload["assigned_reviewer_id"] = reviewer
    return payload


def _create_plan(client: TestClient, case: dict, *, headers: dict[str, str] = ANALYST):
    key = _idempotency("plan-create")
    payload = _plan_payload()
    response = client.post(
        f"/api/v1/cases/{case['id']}/plans",
        headers={**headers, "Idempotency-Key": key},
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json(), key, payload


def _approve_plan(client: TestClient, case: dict, plan: dict) -> dict:
    response = client.post(
        f"/api/v1/cases/{case['id']}/plans/{plan['version']}/approve",
        headers={**REVIEWER, "Idempotency-Key": _idempotency("approve-plan")},
        json={
            "decision": "approve",
            "expected_plan_sha256": plan["plan_sha256"],
            "expected_state_hash": plan["based_on_state_hash"],
            "reason": "The bounded evidence workflow is ready for execution.",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _start_run(client: TestClient, case: dict, plan: dict) -> dict:
    response = client.post(
        f"/api/v1/cases/{case['id']}/runs",
        headers={**ANALYST, "Idempotency-Key": _idempotency("start-run")},
        json={
            "plan_version": plan["version"],
            "expected_plan_sha256": plan["plan_sha256"],
            "expected_state_hash": plan["based_on_state_hash"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _run_one_worker_job(client: TestClient):
    return asyncio.run(
        process_next_job(client.app.state.database, client.app.state.settings)
    )


def test_case_creation_requires_case_role_and_exact_in_scope_version(
    client: TestClient,
) -> None:
    payload = _case_payload(client)
    forbidden = client.post(
        "/api/v1/cases",
        headers={**VIEWER, "Idempotency-Key": _idempotency("viewer-case")},
        json=payload,
    )
    assert forbidden.status_code == 403

    missing_version = client.post(
        "/api/v1/cases",
        headers={**ANALYST, "Idempotency-Key": _idempotency("bad-source")},
        json={**payload, "document_version_id": str(uuid4())},
    )
    assert missing_version.status_code == 404


def test_create_case_pins_hash_and_is_idempotent(client: TestClient) -> None:
    request_id = f"case-test-{uuid4().hex}"
    case, key, payload = _create_case(client, request_id=request_id)
    assert case["status"] == "DRAFT"
    assert case["owner_subject"] == ANALYST["X-Dev-User"]
    assert len(case["current_state_hash"]) == 64
    assert len(case["sources"]) == 1
    source = case["sources"][0]
    assert source["document_version_id"] == payload["document_version_id"]
    assert source["immutable"] is True
    assert len(source["source_sha256"]) == 64

    replay = client.post(
        "/api/v1/cases",
        headers={**ANALYST, "Idempotency-Key": key},
        json=payload,
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == case["id"]

    conflict = client.post(
        "/api/v1/cases",
        headers={**ANALYST, "Idempotency-Key": key},
        json={**payload, "title": "Different case"},
    )
    assert conflict.status_code == 409

    same_client_key_other_subject = client.post(
        "/api/v1/cases",
        headers={**OTHER_ANALYST, "Idempotency-Key": key},
        json=payload,
    )
    assert same_client_key_other_subject.status_code == 201
    assert same_client_key_other_subject.json()["id"] != case["id"]

    async def audit_event() -> AuditEvent | None:
        async with client.app.state.database.session_factory() as session:
            return await session.scalar(
                select(AuditEvent).where(
                    AuditEvent.request_id == request_id,
                    AuditEvent.operation == "case.create",
                )
            )

    persisted_audit = asyncio.run(audit_event())
    assert persisted_audit is not None
    assert persisted_audit.object_id == case["id"]


def test_case_read_scope_separates_owner_from_review_roles(client: TestClient) -> None:
    case, _key, _payload = _create_case(client, title="Read scope case")
    assert client.get(f"/api/v1/cases/{case['id']}", headers=OTHER_ANALYST).status_code == 403
    for headers in (REVIEWER, DOMAIN_SME, AUDITOR, SYSTEM_OWNER):
        response = client.get(f"/api/v1/cases/{case['id']}", headers=headers)
        assert response.status_code == 200
    assert client.get(f"/api/v1/cases/{case['id']}", headers=ADMIN).status_code == 403
    assert client.get("/api/v1/cases", headers=PLATFORM_ADMIN).status_code == 403

    owner_list = client.get("/api/v1/cases", headers=ANALYST)
    assert owner_list.status_code == 200
    assert case["id"] in {item["id"] for item in owner_list.json()["items"]}


def test_plan_is_typed_versioned_hashed_and_idempotent(client: TestClient) -> None:
    case, _key, _payload = _create_case(client, title="Plan case")
    plan, key, payload = _create_plan(client, case)
    assert plan["version"] == 1
    assert plan["based_on_state_hash"] == case["current_state_hash"]
    assert len(plan["plan_sha256"]) == 64
    assert plan["approval"]["status"] == "PENDING"
    assert plan["approval"]["approval_type"] == "PLAN_APPROVAL"
    assert plan["approval"]["expires_at"] is not None
    assert plan["approval"]["plan_sha256"] == plan["plan_sha256"]
    assert plan["approval"]["bound_state_hash"] == case["current_state_hash"]
    assert [step["position"] for step in plan["steps"]] == [1, 2]
    assert "UPDATE_QMS_RECORD" in plan["prohibited_actions"]

    replay = client.post(
        f"/api/v1/cases/{case['id']}/plans",
        headers={**ANALYST, "Idempotency-Key": key},
        json=payload,
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == plan["id"]
    fetched = client.get(
        f"/api/v1/cases/{case['id']}/plans/1",
        headers=DOMAIN_SME,
    )
    assert fetched.status_code == 200
    assert fetched.json()["plan_sha256"] == plan["plan_sha256"]

    owner_approvals = client.get("/api/v1/approvals?status=PENDING", headers=ANALYST)
    assert owner_approvals.status_code == 200
    approval = next(
        item
        for item in owner_approvals.json()["items"]
        if item["id"] == plan["approval"]["id"]
    )
    assert approval["case_title"] == case["title"]
    assert approval["plan_sha256"] == plan["plan_sha256"]
    assert approval["approval_type"] == "PLAN_APPROVAL"
    assert client.get(f"/api/v1/approvals/{approval['id']}", headers=DOMAIN_SME).status_code == 200
    assert client.get(f"/api/v1/approvals/{approval['id']}", headers=VIEWER).status_code == 403
    unrelated = client.get("/api/v1/approvals", headers=OTHER_ANALYST)
    assert approval["id"] not in {item["id"] for item in unrelated.json()["items"]}

    invalid_graph = _plan_payload()
    invalid_graph["steps"][0]["depends_on"] = ["verify_evidence"]
    invalid = client.post(
        f"/api/v1/cases/{case['id']}/plans",
        headers={**ANALYST, "Idempotency-Key": _idempotency("invalid-plan")},
        json=invalid_graph,
    )
    assert invalid.status_code == 422


def test_only_independent_reviewer_can_approve_exact_current_binding(
    client: TestClient,
) -> None:
    case, _key, _payload = _create_case(client, title="Approval case")
    plan, _plan_key, _plan_payload_value = _create_plan(client, case)
    decision = {
        "decision": "approve",
        "expected_plan_sha256": plan["plan_sha256"],
        "expected_state_hash": plan["based_on_state_hash"],
        "reason": "Evidence-only plan is bounded and reviewable.",
    }
    path = f"/api/v1/cases/{case['id']}/plans/{plan['version']}/approve"
    for headers in (ADMIN, PLATFORM_ADMIN, ANALYST):
        denied = client.post(
            path,
            headers={**headers, "Idempotency-Key": _idempotency("denied-decision")},
            json=decision,
        )
        assert denied.status_code == 403

    stale = client.post(
        path,
        headers={**REVIEWER, "Idempotency-Key": _idempotency("stale-decision")},
        json={**decision, "expected_state_hash": "0" * 64},
    )
    assert stale.status_code == 409

    decision_key = _idempotency("approve-plan")
    approved = client.post(
        path,
        headers={**REVIEWER, "Idempotency-Key": decision_key},
        json=decision,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["approval"]["status"] == "APPROVED"
    assert approved.json()["approval"]["decision_by"] == REVIEWER["X-Dev-User"]
    assert client.get(f"/api/v1/cases/{case['id']}", headers=ANALYST).json()["status"] == "READY"

    replay = client.post(
        path,
        headers={**REVIEWER, "Idempotency-Key": decision_key},
        json=decision,
    )
    assert replay.status_code == 200
    assert replay.json()["approval"]["status"] == "APPROVED"


def test_reviewer_cannot_self_approve_and_can_reject_with_reason(client: TestClient) -> None:
    dual_role = {"X-Dev-User": "dual.role", "X-Dev-Roles": "analyst,reviewer"}
    self_case, _key, _payload = _create_case(
        client,
        headers=dual_role,
        title="Self approval case",
    )
    self_plan_key = _idempotency("self-plan")
    self_plan_response = client.post(
        f"/api/v1/cases/{self_case['id']}/plans",
        headers={**dual_role, "Idempotency-Key": self_plan_key},
        json=_plan_payload(reviewer=None),
    )
    assert self_plan_response.status_code == 201
    self_plan = self_plan_response.json()
    denied = client.post(
        f"/api/v1/cases/{self_case['id']}/plans/1/approve",
        headers={**dual_role, "Idempotency-Key": _idempotency("self-decision")},
        json={
            "decision": "approve",
            "expected_plan_sha256": self_plan["plan_sha256"],
            "expected_state_hash": self_plan["based_on_state_hash"],
            "reason": "I created this plan.",
        },
    )
    assert denied.status_code == 403

    case, _key, _payload = _create_case(client, title="Rejected plan case")
    plan, _plan_key, _plan_payload_value = _create_plan(client, case)
    rejected = client.post(
        f"/api/v1/cases/{case['id']}/plans/1/approve",
        headers={**REVIEWER, "Idempotency-Key": _idempotency("reject-plan")},
        json={
            "decision": "reject",
            "expected_plan_sha256": plan["plan_sha256"],
            "expected_state_hash": plan["based_on_state_hash"],
            "reason": "The verification step needs a narrower source scope.",
        },
    )
    assert rejected.status_code == 200
    assert rejected.json()["approval"]["status"] == "REJECTED"
    assert client.get(f"/api/v1/cases/{case['id']}", headers=ANALYST).json()["status"] == (
        "NEEDS_REVISION"
    )


def test_expired_plan_approval_is_persistently_closed(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, _key, _payload = _create_case(client, title="Expired approval case")
    plan, _plan_key, _plan_payload_value = _create_plan(client, case)
    approval_expiry = datetime.fromisoformat(
        str(plan["approval"]["expires_at"]).replace("Z", "+00:00")
    )
    monkeypatch.setattr(
        cases_router,
        "utcnow",
        lambda: approval_expiry + timedelta(seconds=1),
    )
    response = client.post(
        f"/api/v1/cases/{case['id']}/plans/1/approve",
        headers={**REVIEWER, "Idempotency-Key": _idempotency("expired-decision")},
        json={
            "decision": "approve",
            "expected_plan_sha256": plan["plan_sha256"],
            "expected_state_hash": plan["based_on_state_hash"],
            "reason": "This arrives after the approval window.",
        },
    )
    assert response.status_code == 409
    assert "expired" in response.json()["detail"].lower()
    refreshed = client.get(f"/api/v1/cases/{case['id']}", headers=ANALYST)
    assert refreshed.json()["status"] == "NEEDS_REVISION"
    fetched_plan = client.get(f"/api/v1/cases/{case['id']}/plans/1", headers=ANALYST)
    assert fetched_plan.json()["approval"]["status"] == "EXPIRED"


def test_case_history_is_ordered_and_hash_chained(client: TestClient) -> None:
    case, _key, _payload = _create_case(client, title="History case")
    plan, _plan_key, _plan_payload_value = _create_plan(client, case)
    approved = client.post(
        f"/api/v1/cases/{case['id']}/plans/1/approve",
        headers={**REVIEWER, "Idempotency-Key": _idempotency("history-approval")},
        json={
            "decision": "approve",
            "expected_plan_sha256": plan["plan_sha256"],
            "expected_state_hash": plan["based_on_state_hash"],
            "reason": "Approved for history validation.",
        },
    )
    assert approved.status_code == 200

    response = client.get(f"/api/v1/cases/{case['id']}/events", headers=AUDITOR)
    assert response.status_code == 200
    events = response.json()["items"]
    assert [item["sequence"] for item in events] == list(range(1, len(events) + 1))
    assert [item["event_type"] for item in events] == [
        "CASE_CREATED",
        "SOURCE_PINNED",
        "PLAN_GENERATED",
        "APPROVAL_REQUESTED",
        "PLAN_APPROVED",
    ]
    assert events[0]["previous_event_hash"] is None
    for previous, current in zip(events[:-1], events[1:], strict=True):
        assert current["previous_event_hash"] == previous["event_hash"]
    assert events[-1]["state_hash"] == case["current_state_hash"]


def test_run_starts_from_exact_approved_plan_and_dispatches_durably(
    client: TestClient,
) -> None:
    case, _key, _payload = _create_case(client, title="Durable run case")
    plan, _plan_key, _plan_payload_value = _create_plan(client, case)
    _approve_plan(client, case, plan)

    stale = client.post(
        f"/api/v1/cases/{case['id']}/runs",
        headers={**ANALYST, "Idempotency-Key": _idempotency("stale-run")},
        json={
            "plan_version": plan["version"],
            "expected_plan_sha256": "0" * 64,
            "expected_state_hash": plan["based_on_state_hash"],
        },
    )
    assert stale.status_code == 409

    run = _start_run(client, case, plan)
    assert run["status"] == "PENDING"
    assert run["checkpoint"]["schema_version"] == "pharmaagent-run-state@1.0.0"
    assert run["checkpoint"]["workflow_template"]["workflow_key"] == (
        "regulatory-impact-review"
    )

    result = _run_one_worker_job(client)
    assert result is not None
    assert result.metrics["steps_dispatched"] == 1
    dispatched = client.get(f"/api/v1/runs/{run['id']}", headers=ANALYST)
    assert dispatched.status_code == 200
    state = dispatched.json()
    assert state["status"] == "RUNNING"
    assert state["checkpoint"]["step_key"] == "extract_evidence"
    assert state["active_invocation"]["status"] == "RUNNING"

    events = client.get(
        f"/api/v1/runs/{run['id']}/events",
        headers={**AUDITOR, "Accept": "application/x-ndjson"},
    )
    assert events.status_code == 200
    parsed = [json.loads(line) for line in events.text.splitlines()]
    assert [item["event_type"] for item in parsed] == ["RUN_STARTED", "AGENT_STARTED"]
    assert parsed[1]["previous_event_hash"] == parsed[0]["event_hash"]


def test_run_pause_resume_step_approval_and_completion(client: TestClient) -> None:
    case, _key, _payload = _create_case(client, title="Controllable run case")
    plan, _plan_key, _plan_payload_value = _create_plan(client, case)
    _approve_plan(client, case, plan)
    run = _start_run(client, case, plan)
    _run_one_worker_job(client)
    active = client.get(f"/api/v1/runs/{run['id']}", headers=ANALYST).json()

    paused = client.post(
        f"/api/v1/runs/{run['id']}/pause",
        headers={**ANALYST, "Idempotency-Key": _idempotency("pause-run")},
        json={"reason": "Inspect the current evidence boundary."},
    )
    assert paused.status_code == 200
    assert paused.json()["status"] == "PAUSED"
    resumed = client.post(
        f"/api/v1/runs/{run['id']}/resume",
        headers={**ANALYST, "Idempotency-Key": _idempotency("resume-run")},
        json={"reason": "The evidence boundary is confirmed."},
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "RUNNING"
    assert resumed.json()["active_invocation"]["id"] == active["active_invocation"]["id"]

    first_result = client.post(
        f"/api/v1/runs/{run['id']}/steps/extract_evidence/result",
        headers={**SYSTEM_OWNER, "Idempotency-Key": _idempotency("first-result")},
        json={
            "expected_invocation_id": active["active_invocation"]["id"],
            "output": {"findings": [], "incomplete_evidence": True},
            "usage": {
                "turns": 1,
                "tool_calls": 2,
                "input_tokens": 200,
                "output_tokens": 40,
                "runtime_seconds": 1.5,
                "cost_usd": 0.01,
            },
        },
    )
    assert first_result.status_code == 200, first_result.text
    _run_one_worker_job(client)
    waiting = client.get(f"/api/v1/runs/{run['id']}", headers=REVIEWER).json()
    assert waiting["status"] == "WAITING_FOR_APPROVAL"
    assert waiting["checkpoint"]["step_key"] == "verify_evidence"
    approval_id = waiting["checkpoint"]["steps"]["verify_evidence"]["approval_id"]

    self_approval = client.post(
        f"/api/v1/runs/{run['id']}/steps/verify_evidence/approval",
        headers={**ANALYST, "Idempotency-Key": _idempotency("bad-step-approval")},
        json={
            "decision": "approve",
            "expected_approval_id": approval_id,
            "reason": "Owner cannot approve.",
        },
    )
    assert self_approval.status_code == 403
    approved = client.post(
        f"/api/v1/runs/{run['id']}/steps/verify_evidence/approval",
        headers={**REVIEWER, "Idempotency-Key": _idempotency("step-approval")},
        json={
            "decision": "approve",
            "expected_approval_id": approval_id,
            "reason": "Independent review authorizes the verification step.",
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "RUNNING"
    second_invocation = approved.json()["active_invocation"]

    second_result = client.post(
        f"/api/v1/runs/{run['id']}/steps/verify_evidence/result",
        headers={**SYSTEM_OWNER, "Idempotency-Key": _idempotency("second-result")},
        json={
            "expected_invocation_id": second_invocation["id"],
            "output": {"valid": True, "issues": []},
            "usage": {
                "turns": 1,
                "tool_calls": 1,
                "input_tokens": 150,
                "output_tokens": 30,
                "runtime_seconds": 1,
                "cost_usd": 0.01,
            },
        },
    )
    assert second_result.status_code == 200, second_result.text
    _run_one_worker_job(client)
    completed = client.get(f"/api/v1/runs/{run['id']}", headers=ANALYST).json()
    assert completed["status"] == "COMPLETED"
    assert completed["checkpoint"]["step_key"] is None
    assert completed["checkpoint"]["budget"]["tool_calls"] == 3
    assert client.get(f"/api/v1/cases/{case['id']}", headers=ANALYST).json()["status"] == (
        "COMPLETED"
    )


def test_runtime_rejects_over_limit_result_and_blocks_further_work(
    client: TestClient,
) -> None:
    case, _key, _payload = _create_case(client, title="Bounded run case")
    plan, _plan_key, _plan_payload_value = _create_plan(client, case)
    _approve_plan(client, case, plan)
    run = _start_run(client, case, plan)
    _run_one_worker_job(client)
    active = client.get(f"/api/v1/runs/{run['id']}", headers=ANALYST).json()
    blocked = client.post(
        f"/api/v1/runs/{run['id']}/steps/extract_evidence/result",
        headers={**SYSTEM_OWNER, "Idempotency-Key": _idempotency("over-limit")},
        json={
            "expected_invocation_id": active["active_invocation"]["id"],
            "output": {"findings": []},
            "usage": {
                "turns": 5,
                "tool_calls": 0,
                "input_tokens": 10,
                "output_tokens": 10,
                "runtime_seconds": 1,
                "cost_usd": 0,
            },
        },
    )
    assert blocked.status_code == 409
    state = client.get(f"/api/v1/runs/{run['id']}", headers=ANALYST).json()
    assert state["status"] == "BLOCKED"
    assert state["error_code"] == "RUNTIME_LIMIT_EXCEEDED"
    assert state["active_invocation"] is None
