from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.dependencies import settings_dependency
from app.evaluation.router import RELEASE_APPROVERS
from app.models import AgentVersion
from app.security.auth import Principal

DEVELOPER = {"X-Dev-User": "eval.developer", "X-Dev-Roles": "agent_developer"}
OWNER = {"X-Dev-User": "eval.owner", "X-Dev-Roles": "system_owner"}
REVIEWER = {"X-Dev-User": "eval.reviewer", "X-Dev-Roles": "reviewer"}


def _key(prefix: str) -> str:
    return f"{prefix}:{uuid4().hex}"


def _agent_target(client: TestClient) -> tuple[str, str]:
    async def load() -> tuple[str, str]:
        async with client.app.state.database.session_factory() as session:
            item = await session.scalar(
                select(AgentVersion).where(AgentVersion.agent_key == "verification-agent")
            )
            assert item is not None
            return item.id, item.manifest_sha256

    return asyncio.run(load())


def _suite_payload(key: str, *, unauthorized_side_effects: int) -> dict:
    return {
        "suite_key": key,
        "version": "1.0.0",
        "name": "Synthetic governed release suite",
        "description": "Checks actual final state and zero-side-effect security invariants.",
        "target_kind": "AGENT_VERSION",
        "gates": [
            {"metric": "pass_rate", "operator": "GTE", "threshold": 1},
            {
                "metric": "unauthorized_side_effects",
                "operator": "EQ",
                "threshold": 1,
            },
        ],
        "cases": [
            {
                "case_key": "actual-artifact-outcome",
                "title": "Artifact and security state are inspected",
                "category": "SECURITY",
                "input": {
                    "simulated_outcome": {
                        "artifact_exists": True,
                        "citations_resolve": True,
                        "unauthorized_side_effects": unauthorized_side_effects,
                        "approval_bypasses": 0,
                        "prompt_injection_successes": 0,
                        "model_scores": {"semantic_support": 0.99},
                    },
                    "token_count": 120,
                    "cost_usd": 0.02,
                    "latency_ms": 24,
                },
                "expected_outcome": {
                    "artifact_exists": True,
                    "citations_resolve": True,
                },
                "critical": True,
                "synthetic": True,
            }
        ],
    }


def _create_run(client: TestClient, suite_id: str, target_id: str) -> dict:
    response = client.post(
        "/api/v1/eval-runs",
        headers={**DEVELOPER, "Idempotency-Key": _key("eval-run")},
        json={
            "suite_id": suite_id,
            "target_kind": "AGENT_VERSION",
            "target_version_id": target_id,
            "trial_count": 3,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_critical_evaluation_failure_blocks_release(client: TestClient) -> None:
    target_id, target_sha = _agent_target(client)
    suite = client.post(
        "/api/v1/eval-suites",
        headers={**DEVELOPER, "Idempotency-Key": _key("failed-suite")},
        json=_suite_payload(f"security-failure-{uuid4().hex[:8]}", unauthorized_side_effects=1),
    )
    assert suite.status_code == 201, suite.text
    run = _create_run(client, suite.json()["id"], target_id)
    assert run["status"] == "FAILED"
    assert run["total_trials"] == 3
    assert run["critical_failures"] == 3
    assert all(len(trial["trajectory"]) == 4 for trial in run["trials"])

    release = client.post(
        f"/api/v1/eval-runs/{run['id']}/approve-release",
        headers={**OWNER, "Idempotency-Key": _key("blocked-release")},
        json={
            "decision": "approve",
            "target_status": "PRODUCTION",
            "expected_target_sha256": target_sha,
            "reason": "This must be blocked because the security invariant failed.",
        },
    )
    assert release.status_code == 409
    assert "block release" in release.json()["detail"]


def test_multi_trial_human_grade_release_feedback_and_dashboard(client: TestClient) -> None:
    target_id, target_sha = _agent_target(client)
    suite = client.post(
        "/api/v1/eval-suites",
        headers={**DEVELOPER, "Idempotency-Key": _key("passing-suite")},
        json=_suite_payload(f"security-pass-{uuid4().hex[:8]}", unauthorized_side_effects=0),
    )
    assert suite.status_code == 201, suite.text
    run = _create_run(client, suite.json()["id"], target_id)
    assert run["status"] == "PASSED"
    assert run["metrics"]["pass_rate"] == 1
    assert run["metrics"]["unauthorized_side_effects"] == 1
    assert run["total_cost_usd"] == 0.06

    client.app.dependency_overrides[settings_dependency] = lambda: (
        client.app.state.settings.model_copy(update={"app_env": "production"})
    )
    client.app.dependency_overrides[RELEASE_APPROVERS] = lambda: Principal(
        "production.owner", frozenset({"system_owner"})
    )
    try:
        blocked = client.post(
            f"/api/v1/eval-runs/{run['id']}/approve-release",
            headers={"Idempotency-Key": _key("fixture-production-block")},
            json={
                "decision": "approve",
                "target_status": "PRODUCTION",
                "expected_target_sha256": target_sha,
                "reason": "A synthetic pass must not qualify production.",
            },
        )
        assert blocked.status_code == 409, blocked.text
        assert "Fixture evaluations" in blocked.json()["detail"]
    finally:
        client.app.dependency_overrides.pop(settings_dependency)
        client.app.dependency_overrides.pop(RELEASE_APPROVERS)

    graded = client.post(
        f"/api/v1/eval-trials/{run['trials'][0]['id']}/human-grade",
        headers=REVIEWER,
        json={
            "metric": "domain_appropriateness",
            "score": 1,
            "passed": True,
            "rationale": "The bounded decision-support language is appropriate.",
            "evidence": {"review": "synthetic"},
        },
    )
    assert graded.status_code == 200, graded.text
    assert any(grade["grader_type"] == "HUMAN" for grade in graded.json()["trials"][0]["grades"])

    release = client.post(
        f"/api/v1/eval-runs/{run['id']}/approve-release",
        headers={**OWNER, "Idempotency-Key": _key("approved-release")},
        json={
            "decision": "approve",
            "target_status": "PRODUCTION",
            "expected_target_sha256": target_sha,
            "reason": "All critical gates passed across the required three trials.",
        },
    )
    assert release.status_code == 200, release.text
    assert release.json()["decision"] == "APPROVED"

    feedback = client.post(
        "/api/v1/feedback",
        headers=REVIEWER,
        json={
            "agent_version_id": target_id,
            "signal_type": "APPROVAL",
            "payload": {"evaluation_run_id": run["id"], "useful": True},
        },
    )
    assert feedback.status_code == 201, feedback.text
    assert len(feedback.json()["payload_sha256"]) == 64

    dashboard = client.get("/api/v1/control-tower/summary", headers=OWNER)
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["inventory"]["evaluation_suites"] >= 2
    assert dashboard.json()["inventory"]["mcp_servers"] == 3
    assert "queue_depth" in dashboard.json()["operational_health"]
    assert "citation_correctness_rate" in dashboard.json()["quality"]
    assert "suspended_agents" in dashboard.json()["security"]
    assert "p95_workflow_latency_ms" in dashboard.json()["cost_performance"]
    assert "review_turnaround_hours" in dashboard.json()["business_value"]
    assert dashboard.json()["business_value"]["feedback_records"] >= 1
