from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.cases.hashing import artifact_evidence_manifest_sha256
from app.database import Database
from app.models import (
    AgentCaseStatus,
    AgentRunStatus,
    AgentVersion,
    ApprovalRequest,
    ApprovalStatus,
    Artifact,
    ArtifactEvidence,
    ArtifactVersion,
    ArtifactVersionStatus,
    Case,
    CaseEvent,
    CasePlan,
    CasePlanStep,
    CaseRun,
    CaseSource,
    Document,
    DocumentVersion,
    PolicyDecision,
    PolicyEffect,
    RegistryReleaseStatus,
    SkillVersion,
    ToolInvocation,
    ToolInvocationStatus,
    ToolVersion,
    WarningLetter,
)

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.asyncio
async def test_control_plane_persists_exact_source_plan_and_registry_versions(tmp_path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'agent-control-plane.db'}")
    state_hash = "1" * 64
    plan_hash = "2" * 64
    source_hash = "3" * 64
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            await session.execute(text("PRAGMA foreign_keys=ON"))
            letter = WarningLetter(
                id="00000000-0000-0000-0000-000000000001",
                canonical_url="https://www.fda.gov/test-warning-letter",
                company_name="Synthetic Pharma",
            )
            document = Document(
                id="00000000-0000-0000-0000-000000000002",
                warning_letter_id=letter.id,
                canonical_url=letter.canonical_url,
            )
            document_version = DocumentVersion(
                id="00000000-0000-0000-0000-000000000003",
                document_id=document.id,
                version_number=1,
                raw_sha256="4" * 64,
                canonical_hash=source_hash,
                source_anchors=[
                    {
                        "anchor": "section-observations-1",
                        "text": "Synthetic retained evidence.",
                        "kind": "paragraph",
                        "ordinal": 0,
                    }
                ],
                parser_version="test-parser-v1",
                scope_status="IN_SCOPE_DRUGS",
            )
            agent_version = AgentVersion(
                id="00000000-0000-0000-0000-000000000004",
                agent_key="regulatory-evidence-agent",
                version="1.0.0",
                display_name="Regulatory Evidence Agent",
                manifest={"output": "RegulatoryFindingList@2.0.0"},
                manifest_sha256="5" * 64,
                release_status=RegistryReleaseStatus.APPROVED.value,
                created_by="platform.admin",
            )
            skill_version = SkillVersion(
                id="00000000-0000-0000-0000-000000000005",
                skill_key="extract-regulatory-evidence",
                version="1.0.0",
                display_name="Extract regulatory evidence",
                manifest={"kind": "read-only"},
                manifest_sha256="6" * 64,
                release_status=RegistryReleaseStatus.APPROVED.value,
                created_by="platform.admin",
            )
            tool_version = ToolVersion(
                id="00000000-0000-0000-0000-000000000006",
                tool_key="regulatory.get_version",
                server_key="regulatory-mcp",
                version="1",
                display_name="Get retained regulatory version",
                manifest={"input": "DocumentVersionId"},
                manifest_sha256="7" * 64,
                release_status=RegistryReleaseStatus.APPROVED.value,
                created_by="platform.admin",
            )
            agent_case = Case(
                id="00000000-0000-0000-0000-000000000007",
                title="Synthetic FDA impact review",
                objective="Assess the retained public finding.",
                status=AgentCaseStatus.AWAITING_PLAN_APPROVAL.value,
                owner_subject="analyst.user",
                workflow_key="regulatory-impact-review",
                current_state_hash=state_hash,
                idempotency_key="case:create:synthetic-1",
            )
            source = CaseSource(
                id="00000000-0000-0000-0000-000000000008",
                case_id=agent_case.id,
                document_version_id=document_version.id,
                source_role="PRIMARY",
                source_sha256=source_hash,
                pinned_by="analyst.user",
            )
            event = CaseEvent(
                id="00000000-0000-0000-0000-000000000009",
                case_id=agent_case.id,
                sequence=1,
                event_type="CASE_CREATED",
                actor_type="USER",
                actor_id="analyst.user",
                request_id="request-1",
                idempotency_key="case-event:create",
                payload={"sourceVersionId": document_version.id},
                event_hash="8" * 64,
                state_hash=state_hash,
            )
            plan_generated_event = CaseEvent(
                id="00000000-0000-0000-0000-000000000014",
                case_id=agent_case.id,
                sequence=2,
                event_type="PLAN_GENERATED",
                actor_type="USER",
                actor_id="analyst.user",
                request_id="request-2",
                idempotency_key="case-event:plan-generated:v1",
                payload={"planVersion": 1, "planSha256": plan_hash},
                previous_event_hash=event.event_hash,
                event_hash="9" * 64,
                # Plan/status/history changes do not mutate the plan-input scope hash.
                state_hash=state_hash,
            )
            plan = CasePlan(
                id="00000000-0000-0000-0000-000000000010",
                case_id=agent_case.id,
                version=1,
                objective=agent_case.objective,
                plan_schema_version="case-plan-v1",
                plan_definition={"steps": [{"id": "extract_findings"}]},
                plan_sha256=plan_hash,
                based_on_state_hash=state_hash,
                created_by="analyst.user",
            )
            step = CasePlanStep(
                id="00000000-0000-0000-0000-000000000011",
                plan_id=plan.id,
                position=1,
                step_key="extract_findings",
                title="Extract findings",
                instructions="Extract cited findings from the exact retained version.",
                agent_version_id=agent_version.id,
                skill_version_ids=[skill_version.id],
                tool_version_ids=[tool_version.id],
                output_schema_ref="RegulatoryFindingList@2.0.0",
                risk_level="READ_ONLY_PUBLIC",
                limits={"maxToolCalls": 5},
            )
            approval = ApprovalRequest(
                id="00000000-0000-0000-0000-000000000012",
                case_id=agent_case.id,
                plan_id=plan.id,
                plan_version=plan.version,
                plan_sha256=plan_hash,
                bound_state_hash=state_hash,
                approval_type="PLAN_APPROVAL",
                status=ApprovalStatus.PENDING.value,
                requested_by="analyst.user",
                assigned_reviewer_id="reviewer.user",
                idempotency_key="approval:plan:synthetic-1:v1",
                expires_at=datetime.now(UTC) + timedelta(days=7),
            )
            run = CaseRun(
                id="00000000-0000-0000-0000-000000000013",
                case_id=agent_case.id,
                plan_id=plan.id,
                plan_version=plan.version,
                plan_sha256=plan_hash,
                bound_state_hash=state_hash,
                status=AgentRunStatus.PENDING.value,
                requested_by="analyst.user",
                idempotency_key="run:synthetic-1:v1",
            )
            artifact = Artifact(
                id="00000000-0000-0000-0000-000000000015",
                case_id=agent_case.id,
                artifact_key="regulatory-impact-review-package",
                artifact_type="REGULATORY_IMPACT_REVIEW_PACKAGE",
                title="Synthetic regulatory impact review package",
                created_by="analyst.user",
            )
            evidence_manifest_hash = artifact_evidence_manifest_sha256(
                [
                    {
                        "case_source_id": source.id,
                        "document_version_id": document_version.id,
                        "source_sha256": source_hash,
                        "anchor": "section-observations-1",
                        "excerpt_sha256": hashlib.sha256(
                            b"Synthetic retained evidence."
                        ).hexdigest(),
                        "evidence_role": "PRIMARY",
                    }
                ]
            )
            session.add_all(
                [
                    letter,
                    document,
                    document_version,
                    agent_version,
                    skill_version,
                    tool_version,
                    agent_case,
                    source,
                    event,
                    plan_generated_event,
                    plan,
                ]
            )
            # Plan-bound rows are normally created after plan generation has flushed its
            # immutable identity. Keep all three phases in the same atomic transaction.
            await session.flush()
            session.add_all([step, approval, run, artifact])
            await session.flush()
            artifact_version = ArtifactVersion(
                id="00000000-0000-0000-0000-000000000016",
                artifact_id=artifact.id,
                case_id=agent_case.id,
                version=1,
                plan_id=plan.id,
                plan_version=plan.version,
                plan_sha256=plan_hash,
                bound_state_hash=state_hash,
                run_id=run.id,
                content_schema_version="RegulatoryImpactReviewPackage@1.0.0",
                content={"decisionSupportOnly": True, "findings": []},
                content_sha256="a" * 64,
                evidence_manifest_sha256=evidence_manifest_hash,
                status=ArtifactVersionStatus.DRAFT.value,
                created_by="artifact-composer@1.0.0",
            )
            policy_decision = PolicyDecision(
                id="00000000-0000-0000-0000-000000000017",
                case_id=agent_case.id,
                run_id=run.id,
                bound_state_hash=state_hash,
                agent_version_id=agent_version.id,
                tool_version_id=tool_version.id,
                request_id="00000000-0000-4000-8000-000000000020",
                idempotency_key="policy:run:synthetic-1:regulatory.get_version:1",
                principal_subject="analyst.user",
                action="regulatory.get_version",
                effect=PolicyEffect.ALLOW.value,
                policy_key="mvp-read-only-regulatory",
                policy_version="1.0.0",
                policy_sha256="c" * 64,
                input_sha256="1" * 64,
                decision_sha256="e" * 64,
                reason_codes=["CASE_PLAN_ALLOWS_TOOL"],
                decision_metadata={"riskClass": "READ_ONLY_PUBLIC"},
                evaluated_by="policy-engine@1.0.0",
            )
            session.add_all([artifact_version, policy_decision])
            await session.flush()
            invocation_time = datetime.now(UTC)
            tool_invocation = ToolInvocation(
                id="00000000-0000-0000-0000-000000000020",
                case_id=agent_case.id,
                run_id=run.id,
                agent_version_id=agent_version.id,
                tool_version_id=tool_version.id,
                policy_decision_id=policy_decision.id,
                request_id="00000000-0000-4000-8000-000000000020",
                idempotency_key="tool:run:synthetic-1:get-version:1",
                principal_subject="analyst.user",
                runtime_service="pharma-agent-runtime",
                agent_name=agent_version.agent_key,
                agent_version=agent_version.version,
                tool_name=tool_version.tool_key,
                tool_version=tool_version.version,
                arguments_sha256="1" * 64,
                policy_effect=PolicyEffect.ALLOW.value,
                status=ToolInvocationStatus.SUCCEEDED.value,
                structured_result={
                    "status": "success",
                    "request_id": "00000000-0000-4000-8000-000000000020",
                    "tool_name": tool_version.tool_key,
                    "tool_version": tool_version.version,
                    "data": {"document_version_id": document_version.id},
                    "provenance": [],
                    "warnings": [],
                },
                result_sha256="2" * 64,
                provenance=[],
                warnings=[],
                latency_ms=1,
                started_at=invocation_time,
                completed_at=invocation_time,
            )
            session.add(tool_invocation)
            await session.flush()
            artifact_evidence = ArtifactEvidence(
                id="00000000-0000-0000-0000-000000000018",
                artifact_version_id=artifact_version.id,
                case_id=agent_case.id,
                case_source_id=source.id,
                document_version_id=document_version.id,
                source_sha256=source_hash,
                anchor="section-observations-1",
                excerpt_sha256=hashlib.sha256(b"Synthetic retained evidence.").hexdigest(),
                evidence_role="PRIMARY",
                created_by="artifact-composer@1.0.0",
            )
            artifact_approval = ApprovalRequest(
                id="00000000-0000-0000-0000-000000000019",
                case_id=agent_case.id,
                plan_id=plan.id,
                plan_version=plan.version,
                plan_sha256=plan_hash,
                bound_state_hash=state_hash,
                artifact_version_id=artifact_version.id,
                artifact_id=artifact.id,
                artifact_version=artifact_version.version,
                artifact_sha256=artifact_version.content_sha256,
                artifact_evidence_manifest_sha256=(artifact_version.evidence_manifest_sha256),
                approval_type="ARTIFACT_APPROVAL",
                status=ApprovalStatus.PENDING.value,
                requested_by="analyst.user",
                assigned_reviewer_id="reviewer.user",
                idempotency_key="approval:artifact:synthetic-1:v1",
                expires_at=datetime.now(UTC) + timedelta(days=7),
            )
            # Evidence membership must exist before review is bound. PostgreSQL
            # locks the draft version and verifies its canonical manifest here.
            session.add(artifact_evidence)
            await session.flush()
            session.add(artifact_approval)
            await session.commit()

            persisted = await session.scalar(
                select(Case)
                .where(Case.id == agent_case.id)
                .options(
                    selectinload(Case.sources),
                    selectinload(Case.events),
                    selectinload(Case.plans).selectinload(CasePlan.steps),
                    selectinload(Case.approvals),
                    selectinload(Case.runs),
                    selectinload(Case.policy_decisions),
                    selectinload(Case.tool_invocations),
                    selectinload(Case.artifacts)
                    .selectinload(Artifact.versions)
                    .selectinload(ArtifactVersion.evidence),
                )
            )

            assert persisted is not None
            assert persisted.sources[0].document_version_id == document_version.id
            assert persisted.sources[0].source_sha256 == document_version.canonical_hash
            assert [item.state_hash for item in persisted.events] == [state_hash, state_hash]
            assert persisted.plans[0].steps[0].agent_version_id == agent_version.id
            assert persisted.plans[0].steps[0].skill_version_ids == [skill_version.id]
            assert persisted.plans[0].steps[0].tool_version_ids == [tool_version.id]
            approvals = {item.approval_type: item for item in persisted.approvals}
            assert approvals["PLAN_APPROVAL"].plan_sha256 == persisted.plans[0].plan_sha256
            assert approvals["PLAN_APPROVAL"].bound_state_hash == persisted.current_state_hash
            assert persisted.runs[0].plan_version == persisted.plans[0].version
            assert persisted.policy_decisions[0].run_id == persisted.runs[0].id
            assert persisted.policy_decisions[0].effect == PolicyEffect.ALLOW.value
            assert persisted.tool_invocations[0].result_sha256 == "2" * 64
            assert persisted.tool_invocations[0].policy_decision_id == policy_decision.id
            artifact_revision = persisted.artifacts[0].versions[0]
            assert artifact_revision.plan_sha256 == persisted.plans[0].plan_sha256
            assert artifact_revision.run_id == persisted.runs[0].id
            assert artifact_revision.evidence[0].case_source_id == persisted.sources[0].id
            assert artifact_revision.evidence[0].source_sha256 == source_hash
            assert approvals["ARTIFACT_APPROVAL"].artifact_sha256 == (
                artifact_revision.content_sha256
            )
            assert approvals["ARTIFACT_APPROVAL"].artifact_evidence_manifest_sha256 == (
                artifact_revision.evidence_manifest_sha256
            )

            session.add(
                ApprovalRequest(
                    case_id=agent_case.id,
                    plan_id=plan.id,
                    plan_version=plan.version,
                    plan_sha256=plan_hash,
                    bound_state_hash=state_hash,
                    artifact_version_id=artifact_version.id,
                    artifact_id=artifact.id,
                    artifact_version=artifact_version.version,
                    artifact_sha256="0" * 64,
                    artifact_evidence_manifest_sha256=(artifact_version.evidence_manifest_sha256),
                    approval_type="ARTIFACT_APPROVAL",
                    requested_by="analyst.user",
                    idempotency_key="approval:artifact:drifted-hash",
                    expires_at=datetime.now(UTC) + timedelta(days=7),
                )
            )
            with pytest.raises(IntegrityError):
                await session.commit()
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_approval_composite_foreign_key_rejects_a_drifted_plan_binding(tmp_path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'approval-binding.db'}")
    state_hash = "a" * 64
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            await session.execute(text("PRAGMA foreign_keys=ON"))
            agent_case = Case(
                title="Binding test",
                objective="Keep approval authority narrow.",
                owner_subject="analyst.user",
                workflow_key="regulatory-impact-review",
                current_state_hash=state_hash,
                idempotency_key="case:create:binding-test",
            )
            plan = CasePlan(
                case=agent_case,
                version=1,
                objective=agent_case.objective,
                plan_schema_version="case-plan-v1",
                plan_definition={"steps": []},
                plan_sha256="b" * 64,
                based_on_state_hash=state_hash,
                created_by="analyst.user",
            )
            session.add_all([agent_case, plan])
            await session.commit()

            session.add(
                ApprovalRequest(
                    case_id=agent_case.id,
                    plan_id=plan.id,
                    plan_version=plan.version,
                    plan_sha256="c" * 64,
                    bound_state_hash=state_hash,
                    approval_type="PLAN_APPROVAL",
                    requested_by="analyst.user",
                    idempotency_key="approval:drifted-binding",
                    expires_at=datetime.now(UTC) + timedelta(days=7),
                )
            )
            with pytest.raises(IntegrityError):
                await session.commit()
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_sqlite_schema_exposes_policy_and_artifact_provenance_constraints(
    tmp_path,
) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'artifact-schema.db'}")
    try:
        await database.create_schema()
        async with database.engine.connect() as connection:
            schema = await connection.run_sync(
                lambda sync_connection: {
                    "tables": set(inspect(sync_connection).get_table_names()),
                    "artifact_version_fks": {
                        tuple(item["constrained_columns"])
                        for item in inspect(sync_connection).get_foreign_keys("artifact_versions")
                    },
                    "evidence_fks": {
                        tuple(item["constrained_columns"])
                        for item in inspect(sync_connection).get_foreign_keys("artifact_evidence")
                    },
                    "approval_fks": {
                        tuple(item["constrained_columns"])
                        for item in inspect(sync_connection).get_foreign_keys("approval_requests")
                    },
                    "policy_fks": {
                        tuple(item["constrained_columns"])
                        for item in inspect(sync_connection).get_foreign_keys("policy_decisions")
                    },
                    "invocation_fks": {
                        tuple(item["constrained_columns"])
                        for item in inspect(sync_connection).get_foreign_keys("tool_invocations")
                    },
                }
            )

        assert {
            "policy_decisions",
            "tool_invocations",
            "artifacts",
            "artifact_versions",
            "artifact_evidence",
        } <= schema["tables"]
        assert ("artifact_id", "case_id") in schema["artifact_version_fks"]
        assert (
            "plan_id",
            "case_id",
            "plan_version",
            "plan_sha256",
            "bound_state_hash",
        ) in schema["artifact_version_fks"]
        assert ("artifact_version_id", "case_id") in schema["evidence_fks"]
        assert (
            "case_source_id",
            "case_id",
            "document_version_id",
            "source_sha256",
        ) in schema["evidence_fks"]
        assert (
            "artifact_version_id",
            "artifact_id",
            "case_id",
            "artifact_version",
            "artifact_sha256",
            "artifact_evidence_manifest_sha256",
        ) in schema["approval_fks"]
        assert ("run_id", "case_id") in schema["policy_fks"]
        assert ("run_id", "case_id") in schema["invocation_fks"]
    finally:
        await database.dispose()


def test_forward_migration_enforces_append_only_history_and_stale_approval_guards() -> None:
    migration = (
        WORKSPACE_ROOT / "infra" / "migrations" / "20260904_agent_os_control_plane.sql"
    ).read_text(encoding="utf-8")

    assert "trg_case_events_append_only" in migration
    assert "trg_case_sources_immutable" in migration
    assert "trg_case_plans_immutable" in migration
    assert "trg_case_plan_steps_immutable" in migration
    assert "trg_case_plan_steps_guard_insert" in migration
    assert "trg_policy_decisions_append_only" in migration
    assert "trg_policy_decisions_validate_binding" in migration
    assert "trg_artifacts_immutable" in migration
    assert "trg_artifact_versions_validate_insert" in migration
    assert "trg_artifact_versions_protect" in migration
    assert "trg_document_versions_protect_case_pins" in migration
    assert "CREATE TABLE IF NOT EXISTS public.tool_invocations" in migration
    assert "policy_decision_id varchar(36) NOT NULL" in migration
    assert "uq_tool_invocations_policy_decision" in migration
    assert "p.request_id = NEW.request_id" in migration
    assert "p.input_sha256 = NEW.arguments_sha256" in migration
    assert "trg_tool_invocations_validate" in migration
    assert "trg_tool_invocations_append_only" in migration
    assert "trg_artifact_evidence_validate_insert" in migration
    assert "trg_artifact_evidence_immutable" in migration
    assert "pharma_agent_artifact_evidence_manifest_sha256" in migration
    assert "artifact approval evidence manifest does not match membership" in migration
    assert "trg_approval_requests_prevent_delete" in migration
    assert "new approval requests must begin in PENDING" in migration
    assert "new approval requests require a future expiry" in migration
    assert "expired approval requests cannot receive a review decision" in migration
    assert "artifact status requires a matching terminal review decision" in migration
    assert "artifact evidence cannot be appended after review binding" in migration
    assert "artifact evidence anchor is absent from retained document version" in migration
    assert "artifact evidence excerpt hash does not match retained anchor text" in migration
    assert "independently recomputes the canonical manifest" in migration
    assert "approval references a stale case state" in migration
    assert "source pin hash does not match retained document version" in migration
    assert "FOR SHARE" in migration


def test_runtime_roles_allow_agent_attribution_but_hide_case_data_from_readonly() -> None:
    policy = (WORKSPACE_ROOT / "infra" / "policies" / "postgres-runtime-roles.sql").read_text(
        encoding="utf-8"
    )

    assert "public.policy_decisions" in policy
    assert "public.tool_invocations" in policy
    assert "GRANT UPDATE ON public.case_runs TO fda_worker_runtime" in policy
    assert "FROM fda_readonly_runtime" in policy
