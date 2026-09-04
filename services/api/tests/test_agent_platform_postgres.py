from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.cases.hashing import artifact_evidence_manifest_sha256, canonical_sha256
from app.database import Database
from app.enums import ScopeStatus
from app.models import (
    AgentVersion,
    ApprovalRequest,
    Artifact,
    ArtifactEvidence,
    ArtifactVersion,
    Case,
    CaseEvent,
    CasePlan,
    CaseRun,
    CaseSource,
    Document,
    DocumentVersion,
    PolicyDecision,
    ToolInvocation,
    ToolVersion,
    VerificationReport,
    WarningLetter,
)

pytestmark = pytest.mark.skipif(
    os.getenv("AGENT_OS_POSTGRES_TEST") != "1",
    reason="requires the PostgreSQL migration-smoke CI service",
)


@dataclass(frozen=True)
class _ControlPlaneFixture:
    document_version: DocumentVersion
    source: CaseSource
    agent_version: AgentVersion
    tool_version: ToolVersion
    agent_case: Case
    plan: CasePlan
    run: CaseRun
    policy_decision: PolicyDecision
    excerpt: str
    excerpt_sha256: str


async def _seed_control_plane_fixture(
    session: AsyncSession,
    *,
    label: str,
) -> _ControlPlaneFixture:
    """Persist one wholly synthetic, exact-bound run for PostgreSQL guard tests."""

    nonce = uuid4().hex
    source_hash = hashlib.sha256(f"{label}:source:{nonce}".encode()).hexdigest()
    state_hash = hashlib.sha256(f"{label}:state:{nonce}".encode()).hexdigest()
    plan_hash = hashlib.sha256(f"{label}:plan:{nonce}".encode()).hexdigest()
    excerpt = "Synthetic retained evidence for database control validation."
    excerpt_sha256 = hashlib.sha256(excerpt.encode()).hexdigest()
    principal = "synthetic.migration.analyst"

    warning_letter = WarningLetter(
        id=str(uuid4()),
        canonical_url=f"https://example.invalid/{label}/{nonce}",
        company_name="Synthetic Migration Controls Fixture",
    )
    document = Document(
        id=str(uuid4()),
        warning_letter_id=warning_letter.id,
        canonical_url=warning_letter.canonical_url,
    )
    document_version = DocumentVersion(
        id=str(uuid4()),
        document_id=document.id,
        version_number=1,
        raw_sha256=hashlib.sha256(f"{label}:raw:{nonce}".encode()).hexdigest(),
        canonical_hash=source_hash,
        normalized_text=excerpt,
        source_anchors=[
            {
                "anchor": "synthetic-section-1",
                "text": excerpt,
                "kind": "paragraph",
                "ordinal": 0,
            }
        ],
        parser_version="synthetic-migration-smoke-v1",
        scope_status=ScopeStatus.IN_SCOPE_DRUGS.value,
    )
    agent_version = AgentVersion(
        id=str(uuid4()),
        agent_key=f"synthetic-regulatory-agent-{nonce}",
        version="1.0.0",
        display_name="Synthetic Regulatory Agent",
        manifest={"fixture": label},
        manifest_sha256=hashlib.sha256(f"{label}:agent:{nonce}".encode()).hexdigest(),
        release_status="APPROVED",
        created_by="synthetic.platform.admin",
    )
    tool_version = ToolVersion(
        id=str(uuid4()),
        tool_key=f"synthetic.get-version-{nonce}",
        server_key="synthetic-regulatory-mcp",
        version="1.0.0",
        display_name="Synthetic Get Version",
        manifest={"fixture": label},
        manifest_sha256=hashlib.sha256(f"{label}:tool:{nonce}".encode()).hexdigest(),
        release_status="APPROVED",
        created_by="synthetic.platform.admin",
    )
    agent_case = Case(
        id=str(uuid4()),
        title="Synthetic PostgreSQL control validation",
        objective="Exercise database controls against fictional retained evidence.",
        status="RUNNING",
        owner_subject=principal,
        workflow_key="synthetic-regulatory-review",
        current_state_hash=state_hash,
        idempotency_key=f"postgres-controls:case:{nonce}",
    )
    session.add_all(
        [
            warning_letter,
            document,
            document_version,
            agent_version,
            tool_version,
            agent_case,
        ]
    )
    await session.flush()

    source = CaseSource(
        id=str(uuid4()),
        case_id=agent_case.id,
        document_version_id=document_version.id,
        source_role="PRIMARY_REGULATORY",
        source_sha256=source_hash,
        pinned_by=principal,
    )
    plan = CasePlan(
        id=str(uuid4()),
        case_id=agent_case.id,
        version=1,
        objective=agent_case.objective,
        plan_schema_version="synthetic-case-plan-v1",
        plan_definition={"steps": []},
        plan_sha256=plan_hash,
        based_on_state_hash=state_hash,
        created_by=principal,
    )
    session.add_all([source, plan])
    await session.flush()

    run = CaseRun(
        id=str(uuid4()),
        case_id=agent_case.id,
        plan_id=plan.id,
        plan_version=plan.version,
        plan_sha256=plan.plan_sha256,
        bound_state_hash=agent_case.current_state_hash,
        status="RUNNING",
        requested_by=principal,
        idempotency_key=f"postgres-controls:run:{nonce}",
        checkpoint={"step_key": "synthetic-read"},
    )
    session.add(run)
    await session.flush()

    policy_decision = PolicyDecision(
        id=str(uuid4()),
        case_id=agent_case.id,
        run_id=run.id,
        bound_state_hash=agent_case.current_state_hash,
        agent_version_id=agent_version.id,
        tool_version_id=tool_version.id,
        request_id=f"synthetic-policy-{nonce}",
        idempotency_key=f"postgres-controls:policy:{nonce}",
        principal_subject=principal,
        action=tool_version.tool_key,
        effect="ALLOW",
        policy_key="synthetic-read-only-policy",
        policy_version="1.0.0",
        policy_sha256=hashlib.sha256(f"{label}:policy:{nonce}".encode()).hexdigest(),
        input_sha256=canonical_sha256({"document_version_id": document_version.id}),
        decision_sha256=hashlib.sha256(f"{label}:decision:{nonce}".encode()).hexdigest(),
        reason_codes=["SYNTHETIC_CASE_PLAN_ALLOWS_TOOL"],
        decision_metadata={"fixture": label},
        evaluated_by="synthetic-policy-engine@1.0.0",
    )
    session.add(policy_decision)
    await session.commit()

    return _ControlPlaneFixture(
        document_version=document_version,
        source=source,
        agent_version=agent_version,
        tool_version=tool_version,
        agent_case=agent_case,
        plan=plan,
        run=run,
        policy_decision=policy_decision,
        excerpt=excerpt,
        excerpt_sha256=excerpt_sha256,
    )


async def _refresh_fixture(
    session: AsyncSession,
    fixture: _ControlPlaneFixture,
    *additional_rows: object,
) -> None:
    """Reload rows expired by an expected PostgreSQL transaction rollback."""

    rows = (
        fixture.document_version,
        fixture.source,
        fixture.agent_version,
        fixture.tool_version,
        fixture.agent_case,
        fixture.plan,
        fixture.run,
        fixture.policy_decision,
        *additional_rows,
    )
    for row in rows:
        await session.refresh(row)


def _plan_approval_values(
    fixture: _ControlPlaneFixture,
    *,
    approval_id: str,
    idempotency_key: str,
    status: str = "PENDING",
) -> dict[str, object]:
    values: dict[str, object] = {
        "id": approval_id,
        "case_id": fixture.agent_case.id,
        "plan_id": fixture.plan.id,
        "plan_version": fixture.plan.version,
        "plan_sha256": fixture.plan.plan_sha256,
        "bound_state_hash": fixture.agent_case.current_state_hash,
        "approval_type": "PLAN_APPROVAL",
        "status": status,
        "requested_by": fixture.agent_case.owner_subject,
        "assigned_reviewer_id": "synthetic.migration.reviewer",
        "idempotency_key": idempotency_key,
        "expires_at": datetime.now(UTC) + timedelta(days=1),
    }
    if status in {"APPROVED", "REJECTED"}:
        values.update(
            {
                "decision_by": "synthetic.migration.reviewer",
                "decision_reason": "Synthetic invalid initial decision state.",
                "decided_at": datetime.now(UTC),
            }
        )
    return values


def _artifact_evidence_values(
    fixture: _ControlPlaneFixture,
    *,
    artifact_version: ArtifactVersion,
    evidence_id: str,
    anchor: str = "synthetic-section-1",
    excerpt_sha256: str | None = None,
) -> dict[str, object]:
    return {
        "id": evidence_id,
        "artifact_version_id": artifact_version.id,
        "case_id": fixture.agent_case.id,
        "case_source_id": fixture.source.id,
        "document_version_id": fixture.document_version.id,
        "source_sha256": fixture.source.source_sha256,
        "anchor": anchor,
        "excerpt_sha256": excerpt_sha256 or fixture.excerpt_sha256,
        "evidence_role": "PRIMARY",
        "created_by": "synthetic-artifact-composer@1.0.0",
    }


def _artifact_approval_values(
    fixture: _ControlPlaneFixture,
    *,
    artifact: Artifact,
    artifact_version: ArtifactVersion,
    approval_id: str,
    idempotency_key: str,
) -> dict[str, object]:
    return {
        "id": approval_id,
        "case_id": fixture.agent_case.id,
        "plan_id": fixture.plan.id,
        "plan_version": fixture.plan.version,
        "plan_sha256": fixture.plan.plan_sha256,
        "bound_state_hash": fixture.agent_case.current_state_hash,
        "artifact_version_id": artifact_version.id,
        "artifact_id": artifact.id,
        "artifact_version": artifact_version.version,
        "artifact_sha256": artifact_version.content_sha256,
        "artifact_evidence_manifest_sha256": artifact_version.evidence_manifest_sha256,
        "approval_type": "ARTIFACT_APPROVAL",
        "status": "PENDING",
        "requested_by": fixture.agent_case.owner_subject,
        "assigned_reviewer_id": "synthetic.migration.reviewer",
        "idempotency_key": idempotency_key,
        "expires_at": datetime.now(UTC) + timedelta(days=1),
    }


def _tool_invocation_values(
    fixture: _ControlPlaneFixture,
    *,
    invocation_id: str,
    request_id: str,
    idempotency_key: str,
    agent_name: str | None = None,
    tool_name: str | None = None,
    arguments_sha256: str | None = None,
    policy_effect: str = "ALLOW",
    status: str = "SUCCEEDED",
) -> dict[str, object]:
    effective_tool_name = tool_name or fixture.tool_version.tool_key
    result = {
        "status": "success" if status == "SUCCEEDED" else "error",
        "request_id": request_id,
        "tool_name": effective_tool_name,
        "tool_version": fixture.tool_version.version,
        "data": {"document_version_id": fixture.document_version.id},
        "provenance": [],
        "warnings": [],
    }
    invocation_time = datetime.now(UTC)
    return {
        "id": invocation_id,
        "case_id": fixture.agent_case.id,
        "run_id": fixture.run.id,
        "agent_version_id": fixture.agent_version.id,
        "tool_version_id": fixture.tool_version.id,
        "policy_decision_id": fixture.policy_decision.id,
        "request_id": request_id,
        "idempotency_key": idempotency_key,
        "principal_subject": fixture.agent_case.owner_subject,
        "runtime_service": "synthetic-pharma-agent-runtime",
        "agent_name": agent_name or fixture.agent_version.agent_key,
        "agent_version": fixture.agent_version.version,
        "tool_name": effective_tool_name,
        "tool_version": fixture.tool_version.version,
        "arguments_sha256": arguments_sha256
        or canonical_sha256({"document_version_id": fixture.document_version.id}),
        "policy_effect": policy_effect,
        "status": status,
        "structured_result": result,
        "result_sha256": canonical_sha256(result),
        "provenance": [],
        "warnings": [],
        "latency_ms": 1,
        "started_at": invocation_time,
        "completed_at": invocation_time,
    }


@pytest.mark.asyncio
async def test_postgres_migration_enforces_control_plane_guards() -> None:
    """Exercise guards that SQLite cannot model and create_all cannot install."""

    database = Database(os.environ["DATABASE_URL"])
    try:
        async with database.session_factory() as session:
            warning_letter = WarningLetter(
                canonical_url=f"https://www.fda.gov/postgres-agent-platform-smoke/{uuid4().hex}",
                company_name="Synthetic Migration Fixture",
            )
            document = Document(
                warning_letter=warning_letter,
                canonical_url=warning_letter.canonical_url,
            )
            document_version = DocumentVersion(
                document=document,
                version_number=1,
                raw_sha256="1" * 64,
                canonical_hash="2" * 64,
                parser_version="migration-smoke-v1",
                scope_status=ScopeStatus.IN_SCOPE_DRUGS.value,
            )
            agent_case = Case(
                title="PostgreSQL migration guard smoke test",
                objective="Verify database-enforced immutability and stale approval binding.",
                owner_subject="migration-smoke.analyst",
                workflow_key="regulatory-impact-review",
                current_state_hash="3" * 64,
                idempotency_key=f"postgres-migration-smoke-case:{uuid4().hex}",
            )
            session.add_all([warning_letter, document, document_version, agent_case])
            await session.flush()
            source = CaseSource(
                case_id=agent_case.id,
                document_version_id=document_version.id,
                source_role="PRIMARY_REGULATORY",
                source_sha256=document_version.canonical_hash,
                pinned_by=agent_case.owner_subject,
            )
            event = CaseEvent(
                case_id=agent_case.id,
                sequence=1,
                event_type="CASE_CREATED",
                actor_type="user",
                actor_id=agent_case.owner_subject,
                request_id="migration-smoke-request",
                idempotency_key="migration-smoke-event-v1",
                payload={"fixture": True},
                event_hash=canonical_sha256({"smoke": uuid4().hex}),
                state_hash=agent_case.current_state_hash,
            )
            plan = CasePlan(
                case_id=agent_case.id,
                version=1,
                objective=agent_case.objective,
                plan_schema_version="1.0.0",
                plan_definition={"steps": []},
                plan_sha256="5" * 64,
                based_on_state_hash=agent_case.current_state_hash,
                created_by=agent_case.owner_subject,
            )
            session.add_all([source, event, plan])
            await session.commit()

            persisted_event = await session.scalar(
                select(CaseEvent).where(CaseEvent.id == event.id)
            )
            assert persisted_event is not None
            persisted_event.payload = {"tampered": True}
            with pytest.raises(DBAPIError, match="append-only|immutable"):
                await session.commit()
            await session.rollback()
            await session.refresh(agent_case)
            await session.refresh(plan)

            # The plan remains bound to the old planning scope. A later scope change
            # must make a newly inserted approval for that plan fail at the database.
            await session.execute(
                text("UPDATE agent_cases SET current_state_hash = :new_hash WHERE id = :case_id"),
                {"new_hash": "6" * 64, "case_id": agent_case.id},
            )
            await session.commit()
            with pytest.raises(DBAPIError, match="stale case state"):
                await session.execute(
                    text(
                        "INSERT INTO approval_requests ("
                        "id, case_id, plan_id, plan_version, plan_sha256, "
                        "bound_state_hash, approval_type, status, requested_by, "
                        "idempotency_key, expires_at, created_at"
                        ") VALUES ("
                        ":id, :case_id, :plan_id, 1, :plan_hash, :state_hash, "
                        "'PLAN_APPROVAL', 'PENDING', :requested_by, :idempotency_key, "
                        "now() + interval '1 day', now()"
                        ")"
                    ),
                    {
                        "id": "00000000-0000-0000-0000-000000000099",
                        "case_id": agent_case.id,
                        "plan_id": plan.id,
                        "plan_hash": plan.plan_sha256,
                        "state_hash": plan.based_on_state_hash,
                        "requested_by": agent_case.owner_subject,
                        "idempotency_key": "postgres-migration-smoke-approval-v1",
                    },
                )
                await session.commit()
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_postgres_rejects_pinned_evidence_mutation_and_invalid_approval_lifecycle() -> None:
    database = Database(os.environ["DATABASE_URL"])
    try:
        async with database.session_factory() as session:
            fixture = await _seed_control_plane_fixture(
                session,
                label="pinned-evidence-and-approval-lifecycle",
            )

            with pytest.raises(
                DBAPIError,
                match="case-pinned document version evidence is immutable",
            ):
                await session.execute(
                    update(DocumentVersion)
                    .where(DocumentVersion.id == fixture.document_version.id)
                    .values(
                        source_anchors=[
                            {
                                "anchor": "synthetic-section-rewritten",
                                "text": "Synthetic evidence was replaced in place.",
                                "kind": "paragraph",
                                "ordinal": 0,
                            }
                        ]
                    )
                )
            await session.rollback()
            await _refresh_fixture(session, fixture)

            expired_values = _plan_approval_values(
                fixture,
                approval_id=str(uuid4()),
                idempotency_key=f"postgres-controls:expired-on-arrival:{uuid4().hex}",
            )
            expired_values.update(
                {
                    "created_at": datetime.now(UTC) - timedelta(days=2),
                    "expires_at": datetime.now(UTC) - timedelta(days=1),
                }
            )
            with pytest.raises(
                DBAPIError,
                match="new approval requests require a future expiry",
            ):
                await session.execute(insert(ApprovalRequest).values(**expired_values))
            await session.rollback()
            await _refresh_fixture(session, fixture)

            with pytest.raises(
                DBAPIError,
                match="new approval requests must begin in PENDING",
            ):
                await session.execute(
                    insert(ApprovalRequest).values(
                        **_plan_approval_values(
                            fixture,
                            approval_id=str(uuid4()),
                            idempotency_key=f"postgres-controls:nonpending:{uuid4().hex}",
                            status="APPROVED",
                        )
                    )
                )
            await session.rollback()
            await _refresh_fixture(session, fixture)

            approval_id = str(uuid4())
            await session.execute(
                insert(ApprovalRequest).values(
                    **_plan_approval_values(
                        fixture,
                        approval_id=approval_id,
                        idempotency_key=f"postgres-controls:pending:{uuid4().hex}",
                    )
                )
            )
            await session.commit()

            with pytest.raises(DBAPIError, match="approval scope bindings are immutable"):
                await session.execute(
                    update(ApprovalRequest)
                    .where(ApprovalRequest.id == approval_id)
                    .values(expires_at=datetime.now(UTC) + timedelta(days=2))
                )
            await session.rollback()
            await _refresh_fixture(session, fixture)

            with pytest.raises(DBAPIError, match="append-only|immutable"):
                await session.execute(
                    delete(ApprovalRequest).where(ApprovalRequest.id == approval_id)
                )
            await session.rollback()
            await _refresh_fixture(session, fixture)

            assert (
                await session.scalar(
                    select(ApprovalRequest.id).where(ApprovalRequest.id == approval_id)
                )
                == approval_id
            )
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_postgres_validates_artifact_evidence_and_canonical_review_manifest() -> None:
    database = Database(os.environ["DATABASE_URL"])
    try:
        async with database.session_factory() as session:
            fixture = await _seed_control_plane_fixture(
                session,
                label="artifact-evidence-and-review-manifest",
            )
            evidence_member = {
                "case_source_id": fixture.source.id,
                "document_version_id": fixture.document_version.id,
                "source_sha256": fixture.source.source_sha256,
                "anchor": "synthetic-section-1",
                "excerpt_sha256": fixture.excerpt_sha256,
                "evidence_role": "PRIMARY",
            }
            canonical_manifest = artifact_evidence_manifest_sha256([evidence_member])
            incorrect_manifest = "f" * 64
            assert canonical_manifest != incorrect_manifest

            incorrect_artifact = Artifact(
                id=str(uuid4()),
                case_id=fixture.agent_case.id,
                artifact_key=f"synthetic-incorrect-manifest-{uuid4().hex}",
                artifact_type="SYNTHETIC_REGULATORY_REVIEW",
                title="Synthetic artifact with an incorrect declared manifest",
                created_by=fixture.agent_case.owner_subject,
            )
            correct_artifact = Artifact(
                id=str(uuid4()),
                case_id=fixture.agent_case.id,
                artifact_key=f"synthetic-canonical-manifest-{uuid4().hex}",
                artifact_type="SYNTHETIC_REGULATORY_REVIEW",
                title="Synthetic artifact with a canonical evidence manifest",
                created_by=fixture.agent_case.owner_subject,
            )
            session.add_all([incorrect_artifact, correct_artifact])
            await session.flush()

            verification = VerificationReport(
                id=str(uuid4()),
                case_id=fixture.agent_case.id,
                run_id=fixture.run.id,
                plan_id=fixture.plan.id,
                plan_version=fixture.plan.version,
                plan_sha256=fixture.plan.plan_sha256,
                bound_state_hash=fixture.agent_case.current_state_hash,
                input_sha256=canonical_sha256({"fixture": fixture.agent_case.id}),
                status="PASS",
                checks=[],
                issues=[],
                verified_hypothesis_ids=[],
                report_sha256=canonical_sha256({"verification": fixture.agent_case.id}),
                verifier_name="synthetic-verifier",
                verifier_version="1.0.0",
                created_by="synthetic-verifier",
            )
            session.add(verification)
            await session.flush()

            incorrect_version = ArtifactVersion(
                id=str(uuid4()),
                artifact_id=incorrect_artifact.id,
                case_id=fixture.agent_case.id,
                version=1,
                plan_id=fixture.plan.id,
                plan_version=fixture.plan.version,
                plan_sha256=fixture.plan.plan_sha256,
                bound_state_hash=fixture.agent_case.current_state_hash,
                run_id=fixture.run.id,
                content_schema_version="SyntheticArtifact@1.0.0",
                content={"decisionSupportOnly": True},
                content_sha256=hashlib.sha256(b"synthetic-incorrect-artifact").hexdigest(),
                verification_report_id=verification.id,
                evidence_manifest_sha256=incorrect_manifest,
                status="DRAFT",
                created_by="synthetic-artifact-composer@1.0.0",
            )
            correct_version = ArtifactVersion(
                id=str(uuid4()),
                artifact_id=correct_artifact.id,
                case_id=fixture.agent_case.id,
                version=1,
                plan_id=fixture.plan.id,
                plan_version=fixture.plan.version,
                plan_sha256=fixture.plan.plan_sha256,
                bound_state_hash=fixture.agent_case.current_state_hash,
                run_id=fixture.run.id,
                content_schema_version="SyntheticArtifact@1.0.0",
                content={"decisionSupportOnly": True},
                content_sha256=hashlib.sha256(b"synthetic-canonical-artifact").hexdigest(),
                verification_report_id=verification.id,
                evidence_manifest_sha256=canonical_manifest,
                status="DRAFT",
                created_by="synthetic-artifact-composer@1.0.0",
            )
            session.add_all([incorrect_version, correct_version])
            await session.commit()

            with pytest.raises(
                DBAPIError,
                match="artifact evidence anchor is absent",
            ):
                await session.execute(
                    insert(ArtifactEvidence).values(
                        **_artifact_evidence_values(
                            fixture,
                            artifact_version=correct_version,
                            evidence_id=str(uuid4()),
                            anchor="synthetic-missing-anchor",
                        )
                    )
                )
            await session.rollback()
            await _refresh_fixture(
                session,
                fixture,
                incorrect_artifact,
                correct_artifact,
                incorrect_version,
                correct_version,
            )

            with pytest.raises(
                DBAPIError,
                match="artifact evidence excerpt hash does not match",
            ):
                await session.execute(
                    insert(ArtifactEvidence).values(
                        **_artifact_evidence_values(
                            fixture,
                            artifact_version=correct_version,
                            evidence_id=str(uuid4()),
                            excerpt_sha256="0" * 64,
                        )
                    )
                )
            await session.rollback()
            await _refresh_fixture(
                session,
                fixture,
                incorrect_artifact,
                correct_artifact,
                incorrect_version,
                correct_version,
            )

            for artifact_version in (incorrect_version, correct_version):
                await session.execute(
                    insert(ArtifactEvidence).values(
                        **_artifact_evidence_values(
                            fixture,
                            artifact_version=artifact_version,
                            evidence_id=str(uuid4()),
                        )
                    )
                )
            await session.commit()

            sql_manifest = await session.scalar(
                text(
                    "SELECT public.pharma_agent_artifact_evidence_manifest_sha256("
                    ":artifact_version_id)"
                ),
                {"artifact_version_id": correct_version.id},
            )
            assert sql_manifest == canonical_manifest

            with pytest.raises(
                DBAPIError,
                match="artifact approval evidence manifest does not match membership",
            ):
                await session.execute(
                    insert(ApprovalRequest).values(
                        **_artifact_approval_values(
                            fixture,
                            artifact=incorrect_artifact,
                            artifact_version=incorrect_version,
                            approval_id=str(uuid4()),
                            idempotency_key=(
                                f"postgres-controls:incorrect-artifact-review:{uuid4().hex}"
                            ),
                        )
                    )
                )
            await session.rollback()
            await _refresh_fixture(
                session,
                fixture,
                incorrect_artifact,
                correct_artifact,
                incorrect_version,
                correct_version,
            )

            valid_approval_id = str(uuid4())
            await session.execute(
                insert(ApprovalRequest).values(
                    **_artifact_approval_values(
                        fixture,
                        artifact=correct_artifact,
                        artifact_version=correct_version,
                        approval_id=valid_approval_id,
                        idempotency_key=(
                            f"postgres-controls:canonical-artifact-review:{uuid4().hex}"
                        ),
                    )
                )
            )
            await session.commit()

            assert (
                await session.scalar(
                    select(ApprovalRequest.status).where(ApprovalRequest.id == valid_approval_id)
                )
                == "PENDING"
            )
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_postgres_requires_exact_tool_attribution_and_immutable_observations() -> None:
    database = Database(os.environ["DATABASE_URL"])
    try:
        async with database.session_factory() as session:
            fixture = await _seed_control_plane_fixture(
                session,
                label="tool-invocation-attribution",
            )

            with pytest.raises(
                DBAPIError,
                match="tool invocation agent identity does not match registry",
            ):
                await session.execute(
                    insert(ToolInvocation).values(
                        **_tool_invocation_values(
                            fixture,
                            invocation_id=str(uuid4()),
                            request_id=fixture.policy_decision.request_id,
                            idempotency_key=f"postgres-controls:wrong-agent:{uuid4().hex}",
                            agent_name="synthetic-unregistered-agent",
                        )
                    )
                )
            await session.rollback()
            await _refresh_fixture(session, fixture)

            with pytest.raises(
                DBAPIError,
                match="tool invocation tool identity does not match registry",
            ):
                await session.execute(
                    insert(ToolInvocation).values(
                        **_tool_invocation_values(
                            fixture,
                            invocation_id=str(uuid4()),
                            request_id=fixture.policy_decision.request_id,
                            idempotency_key=f"postgres-controls:wrong-tool:{uuid4().hex}",
                            tool_name="synthetic.unregistered-tool",
                        )
                    )
                )
            await session.rollback()
            await _refresh_fixture(session, fixture)

            with pytest.raises(
                DBAPIError,
                match="tool invocation policy decision attribution is invalid",
            ):
                await session.execute(
                    insert(ToolInvocation).values(
                        **_tool_invocation_values(
                            fixture,
                            invocation_id=str(uuid4()),
                            request_id=fixture.policy_decision.request_id,
                            idempotency_key=f"postgres-controls:wrong-policy:{uuid4().hex}",
                            policy_effect="DENY",
                            status="DENIED",
                        )
                    )
                )
            await session.rollback()
            await _refresh_fixture(session, fixture)

            with pytest.raises(
                DBAPIError,
                match="tool invocation policy decision attribution is invalid",
            ):
                await session.execute(
                    insert(ToolInvocation).values(
                        **_tool_invocation_values(
                            fixture,
                            invocation_id=str(uuid4()),
                            request_id=fixture.policy_decision.request_id,
                            idempotency_key=(f"postgres-controls:wrong-policy-input:{uuid4().hex}"),
                            arguments_sha256="0" * 64,
                        )
                    )
                )
            await session.rollback()
            await _refresh_fixture(session, fixture)

            fixture.run.status = "PAUSED"
            await session.commit()
            with pytest.raises(
                DBAPIError,
                match="tool invocation does not match its active run principal",
            ):
                await session.execute(
                    insert(ToolInvocation).values(
                        **_tool_invocation_values(
                            fixture,
                            invocation_id=str(uuid4()),
                            request_id=fixture.policy_decision.request_id,
                            idempotency_key=f"postgres-controls:paused-run:{uuid4().hex}",
                        )
                    )
                )
            await session.rollback()
            await _refresh_fixture(session, fixture)
            fixture.run.status = "RUNNING"
            await session.commit()

            fixture.agent_version.release_status = "SUSPENDED"
            await session.commit()
            with pytest.raises(
                DBAPIError,
                match="tool invocation agent identity does not match registry",
            ):
                await session.execute(
                    insert(ToolInvocation).values(
                        **_tool_invocation_values(
                            fixture,
                            invocation_id=str(uuid4()),
                            request_id=fixture.policy_decision.request_id,
                            idempotency_key=(f"postgres-controls:suspended-agent:{uuid4().hex}"),
                        )
                    )
                )
            await session.rollback()
            await _refresh_fixture(session, fixture)
            fixture.agent_version.release_status = "APPROVED"
            await session.commit()

            invocation_id = str(uuid4())
            await session.execute(
                insert(ToolInvocation).values(
                    **_tool_invocation_values(
                        fixture,
                        invocation_id=invocation_id,
                        request_id=fixture.policy_decision.request_id,
                        idempotency_key=f"postgres-controls:exact-tool:{uuid4().hex}",
                    )
                )
            )
            await session.commit()

            with pytest.raises(DBAPIError, match="append-only|immutable"):
                await session.execute(
                    update(ToolInvocation)
                    .where(ToolInvocation.id == invocation_id)
                    .values(warnings=["Synthetic post-hoc mutation."])
                )
            await session.rollback()
            await _refresh_fixture(session, fixture)

            with pytest.raises(DBAPIError, match="append-only|immutable"):
                await session.execute(
                    delete(ToolInvocation).where(ToolInvocation.id == invocation_id)
                )
            await session.rollback()
            await _refresh_fixture(session, fixture)

            assert (
                await session.scalar(
                    select(ToolInvocation.id).where(ToolInvocation.id == invocation_id)
                )
                == invocation_id
            )
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_postgres_runtime_roles_enforce_agent_control_plane_boundaries() -> None:
    database = Database(os.environ["DATABASE_URL"])
    try:
        async with database.session_factory() as session:
            privileges = {
                "api_policy_insert": await session.scalar(
                    text(
                        "SELECT has_table_privilege('fda_api_runtime', "
                        "'public.policy_decisions', 'INSERT')"
                    )
                ),
                "api_invocation_insert": await session.scalar(
                    text(
                        "SELECT has_table_privilege('fda_api_runtime', "
                        "'public.tool_invocations', 'INSERT')"
                    )
                ),
                "worker_run_update": await session.scalar(
                    text(
                        "SELECT has_table_privilege('fda_worker_runtime', "
                        "'public.case_runs', 'UPDATE')"
                    )
                ),
                "readonly_case_select": await session.scalar(
                    text(
                        "SELECT has_table_privilege('fda_readonly_runtime', "
                        "'public.agent_cases', 'SELECT')"
                    )
                ),
                "readonly_invocation_select": await session.scalar(
                    text(
                        "SELECT has_table_privilege('fda_readonly_runtime', "
                        "'public.tool_invocations', 'SELECT')"
                    )
                ),
            }

            assert privileges == {
                "api_policy_insert": True,
                "api_invocation_insert": True,
                "worker_run_update": True,
                "readonly_case_select": False,
                "readonly_invocation_select": False,
            }
    finally:
        await database.dispose()
