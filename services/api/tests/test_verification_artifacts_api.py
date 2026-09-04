from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient

from app.cases.hashing import canonical_sha256
from app.models import ImpactHypothesis

ANALYST = {"X-Dev-User": "artifact.analyst", "X-Dev-Roles": "analyst"}
REVIEWER = {"X-Dev-User": "artifact.reviewer", "X-Dev-Roles": "reviewer"}


def _key(prefix: str) -> str:
    return f"{prefix}:{uuid4().hex}"


def _case_with_approved_plan(client: TestClient) -> tuple[dict, dict]:
    letters = client.get("/api/v1/letters", headers=ANALYST).json()["items"]
    letter_id = next(item["id"] for item in letters if item["review_state"] == "approved")
    version = client.get(f"/api/v1/letters/{letter_id}", headers=ANALYST).json()["current_version"]
    case_response = client.post(
        "/api/v1/cases",
        headers={**ANALYST, "Idempotency-Key": _key("artifact-case")},
        json={
            "title": "Verified regulatory impact package",
            "objective": "Prepare an evidence-bound fictional impact review package.",
            "workflow_key": "regulatory-impact-review",
            "warning_letter_id": letter_id,
            "document_version_id": version["id"],
            "source_role": "PRIMARY_REGULATORY",
        },
    )
    assert case_response.status_code == 201, case_response.text
    case = case_response.json()
    plan_response = client.post(
        f"/api/v1/cases/{case['id']}/plans",
        headers={**ANALYST, "Idempotency-Key": _key("artifact-plan")},
        json={
            "plan_schema_version": "1.0.0",
            "assigned_reviewer_id": REVIEWER["X-Dev-User"],
            "steps": [
                {
                    "step_key": "evidence_impact_verification",
                    "title": "Verify evidence-linked impact hypotheses",
                    "instructions": "Verify exact citations and prohibit compliance conclusions.",
                    "depends_on": [],
                    "agent_version_id": None,
                    "skill_version_ids": [],
                    "tool_version_ids": [],
                    "output_schema_ref": "VerificationReport@1.0.0",
                    "risk_level": "R2",
                    "requires_approval": False,
                    "limits": {
                        "max_turns": 4,
                        "max_tool_calls": 8,
                        "max_input_tokens": 20000,
                        "max_output_tokens": 5000,
                        "max_runtime_seconds": 120,
                        "max_cost_usd": 2,
                    },
                }
            ],
        },
    )
    assert plan_response.status_code == 201, plan_response.text
    plan = plan_response.json()
    approval = client.post(
        f"/api/v1/cases/{case['id']}/plans/{plan['version']}/approve",
        headers={**REVIEWER, "Idempotency-Key": _key("artifact-plan-approve")},
        json={
            "decision": "approve",
            "expected_plan_sha256": plan["plan_sha256"],
            "expected_state_hash": plan["based_on_state_hash"],
            "reason": "The evidence verification plan is bounded and reviewable.",
        },
    )
    assert approval.status_code == 200, approval.text
    return case, plan


def _accepted_hypothesis(client: TestClient, case: dict) -> dict:
    generated = client.post(
        f"/api/v1/cases/{case['id']}/impact/generate",
        headers={**ANALYST, "Idempotency-Key": _key("artifact-impact")},
        json={"per_finding_limit": 5},
    )
    assert generated.status_code == 200, generated.text
    hypothesis = generated.json()["items"][0]
    accepted = client.post(
        f"/api/v1/cases/{case['id']}/impact/{hypothesis['id']}/decision",
        headers={**REVIEWER, "Idempotency-Key": _key("artifact-impact-accept")},
        json={
            "decision": "accept",
            "expected_hypothesis_sha256": hypothesis["hypothesis_sha256"],
            "reason": "The exact external and internal anchors support human review.",
        },
    )
    assert accepted.status_code == 200, accepted.text
    return accepted.json()


def test_verification_composition_stale_review_and_approved_export(
    client: TestClient,
) -> None:
    case, _plan = _case_with_approved_plan(client)
    hypothesis = _accepted_hypothesis(client, case)

    verification = client.post(
        f"/api/v1/cases/{case['id']}/verification",
        headers={**ANALYST, "Idempotency-Key": _key("verification")},
    )
    assert verification.status_code == 200, verification.text
    report = verification.json()
    assert report["status"] == "PASS", report["issues"]
    assert report["verified_hypothesis_ids"] == [hypothesis["id"]]
    assert report["independent_context"] is True

    composed = client.post(
        f"/api/v1/cases/{case['id']}/artifacts/compose",
        headers={**ANALYST, "Idempotency-Key": _key("artifact-compose")},
        json={
            "title": "Synthetic Data Integrity Impact Review",
            "assigned_reviewer_id": REVIEWER["X-Dev-User"],
        },
    )
    assert composed.status_code == 200, composed.text
    artifact = composed.json()
    assert artifact["status"] == "DRAFT"
    assert artifact["verification_report_id"] == report["id"]
    assert artifact["evidence"]
    assert artifact["content"]["impact_hypotheses"][0]["id"] == hypothesis["id"]

    export_path = f"/api/v1/cases/{case['id']}/artifacts/{artifact['id']}/export"
    assert client.get(export_path, headers=REVIEWER).status_code == 409
    decision_path = f"/api/v1/cases/{case['id']}/artifacts/{artifact['id']}/decision"
    stale = client.post(
        decision_path,
        headers={**REVIEWER, "Idempotency-Key": _key("artifact-stale")},
        json={
            "decision": "approve",
            "expected_content_sha256": "0" * 64,
            "expected_evidence_manifest_sha256": artifact["evidence_manifest_sha256"],
            "reason": "This decision deliberately presents a stale content hash.",
        },
    )
    assert stale.status_code == 409
    approved = client.post(
        decision_path,
        headers={**REVIEWER, "Idempotency-Key": _key("artifact-approve")},
        json={
            "decision": "approve",
            "expected_content_sha256": artifact["content_sha256"],
            "expected_evidence_manifest_sha256": artifact["evidence_manifest_sha256"],
            "reason": "The package is bound to the displayed verification and evidence hashes.",
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert (
        client.get(f"/api/v1/cases/{case['id']}", headers=ANALYST).json()["status"] == "COMPLETED"
    )

    exported = client.get(export_path, headers=REVIEWER)
    assert exported.status_code == 200
    assert exported.headers["x-artifact-sha256"] == artifact["content_sha256"]
    assert "Decision support only" in exported.text


def test_artifact_composition_is_blocked_without_pass_verification(
    client: TestClient,
) -> None:
    case, _plan = _case_with_approved_plan(client)
    _accepted_hypothesis(client, case)
    response = client.post(
        f"/api/v1/cases/{case['id']}/artifacts/compose",
        headers={**ANALYST, "Idempotency-Key": _key("artifact-without-verification")},
        json={"title": "Should not be composed"},
    )
    assert response.status_code == 409
    assert "PASS verification" in response.json()["detail"]


def test_unsupported_claims_are_detected_and_correction_loop_is_bounded(
    client: TestClient,
) -> None:
    case, _plan = _case_with_approved_plan(client)
    accepted = _accepted_hypothesis(client, case)

    async def remove_required_support() -> None:
        async with client.app.state.database.session_factory() as session:
            hypothesis = await session.get(ImpactHypothesis, accepted["id"])
            assert hypothesis is not None
            hypothesis.assumptions = []
            payload = {
                "case_id": hypothesis.case_id,
                "run_id": hypothesis.run_id,
                "finding_id": hypothesis.finding_id,
                "asset_id": hypothesis.asset_id,
                "asset_version_id": hypothesis.asset_version_id,
                "relationship_type": hypothesis.relationship_type,
                "statement": hypothesis.statement,
                "known_facts": hypothesis.known_facts,
                "derived_relationships": hypothesis.derived_relationships,
                "assumptions": hypothesis.assumptions,
                "counterevidence": hypothesis.counterevidence,
                "unknowns": hypothesis.unknowns,
                "recommended_verification": hypothesis.recommended_verification,
                "external_evidence": hypothesis.external_evidence,
                "internal_evidence": hypothesis.internal_evidence,
                "confidence": hypothesis.confidence,
                "review_priority": hypothesis.review_priority,
            }
            hypothesis.hypothesis_sha256 = canonical_sha256(payload)
            await session.commit()

    asyncio.run(remove_required_support())
    statuses: list[str] = []
    reports: list[dict] = []
    for _attempt in range(3):
        response = client.post(
            f"/api/v1/cases/{case['id']}/verification",
            headers={**ANALYST, "Idempotency-Key": _key("bounded-correction")},
        )
        assert response.status_code == 200, response.text
        reports.append(response.json())
        statuses.append(response.json()["status"])
    assert statuses == ["REVISE", "REVISE", "BLOCK"]
    assert reports[-1]["correction_iteration"] == 2
    issue_codes = {issue["code"] for report in reports for issue in report["issues"]}
    assert "REASONING_DISTINCTIONS_MISSING" in issue_codes
    assert "CORRECTION_LOOP_EXHAUSTED" in issue_codes
