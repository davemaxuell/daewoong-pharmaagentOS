from __future__ import annotations

import json
from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import add_audit_event
from app.cases.router import (
    _append_event,
    _case_for_read,
    _event_key,
    _request_fingerprint,
    _require_case_write,
)
from app.config import Settings
from app.dependencies import session_dependency, settings_dependency
from app.internal_knowledge.retrieval import KnowledgeRepository
from app.models import (
    AgentCaseStatus,
    ApprovalRequest,
    ApprovalStatus,
    Artifact,
    ArtifactEvidence,
    ArtifactVersion,
    ArtifactVersionStatus,
    CaseEvent,
    VerificationReport,
    utcnow,
)
from app.security.auth import Principal, current_principal, require_roles
from app.verification.schemas import (
    ArtifactApprovalResponse,
    ArtifactComposeRequest,
    ArtifactDecisionRequest,
    ArtifactEvidenceResponse,
    ArtifactPageResponse,
    ArtifactVersionResponse,
    VerificationReportResponse,
)
from app.verification.service import ArtifactComposer, VerificationEngine

router = APIRouter(tags=["Verification and Artifact Review"])

IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=16,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
VERIFICATION_REQUESTERS = require_roles("analyst", "system_owner")
ARTIFACT_REVIEWERS = require_roles("reviewer")


def _verification_response(report: VerificationReport) -> VerificationReportResponse:
    return VerificationReportResponse(
        id=report.id,
        case_id=report.case_id,
        run_id=report.run_id,
        plan_id=report.plan_id,
        plan_version=report.plan_version,
        plan_sha256=report.plan_sha256,
        bound_state_hash=report.bound_state_hash,
        input_sha256=report.input_sha256,
        correction_iteration=report.correction_iteration,
        status=report.status,
        checks=report.checks,
        issues=report.issues,
        verified_hypothesis_ids=report.verified_hypothesis_ids,
        report_sha256=report.report_sha256,
        verifier_name="verification-agent",
        verifier_version="1.2.1",
        created_by=report.created_by,
        created_at=report.created_at,
    )


async def _require_artifact_acl(
    session: AsyncSession,
    principal: Principal,
    version: ArtifactVersion,
) -> None:
    repository = KnowledgeRepository(session, principal)
    hypotheses = version.content.get("impact_hypotheses", [])
    if not isinstance(hypotheses, list):
        raise HTTPException(status_code=404, detail="Artifact not found or unavailable")
    try:
        for item in hypotheses:
            if not isinstance(item, dict):
                raise HTTPException(status_code=404, detail="Artifact not found or unavailable")
            asset_id = str(item.get("asset_id", ""))
            asset_version_id = str(item.get("asset_version_id", ""))
            asset, asset_version = await repository.require_version(asset_version_id)
            if asset.id != asset_id or asset_version.asset_id != asset_id:
                raise HTTPException(status_code=404, detail="Artifact not found or unavailable")
    except HTTPException as exc:
        raise HTTPException(status_code=404, detail="Artifact not found or unavailable") from exc


async def _artifact_response(
    session: AsyncSession,
    principal: Principal,
    artifact: Artifact,
    version: ArtifactVersion,
) -> ArtifactVersionResponse:
    await _require_artifact_acl(session, principal, version)
    evidence = list(
        (
            await session.scalars(
                select(ArtifactEvidence)
                .where(ArtifactEvidence.artifact_version_id == version.id)
                .order_by(ArtifactEvidence.created_at, ArtifactEvidence.id)
            )
        ).all()
    )
    approval = await session.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.artifact_version_id == version.id,
            ApprovalRequest.approval_type == "ARTIFACT_APPROVAL",
        )
    )
    if approval is None or version.verification_report_id is None:
        raise RuntimeError("Artifact revision has no complete review binding")
    return ArtifactVersionResponse(
        id=version.id,
        artifact_id=artifact.id,
        case_id=version.case_id,
        artifact_key=artifact.artifact_key,
        artifact_type=artifact.artifact_type,
        title=artifact.title,
        version=version.version,
        plan_id=version.plan_id,
        plan_version=version.plan_version,
        plan_sha256=version.plan_sha256,
        bound_state_hash=version.bound_state_hash,
        run_id=version.run_id,
        verification_report_id=version.verification_report_id,
        content_schema_version=version.content_schema_version,
        content=version.content,
        content_sha256=version.content_sha256,
        evidence_manifest_sha256=version.evidence_manifest_sha256,
        status=version.status,
        created_by=version.created_by,
        created_at=version.created_at,
        evidence=[
            ArtifactEvidenceResponse(
                id=item.id,
                case_source_id=item.case_source_id,
                document_version_id=item.document_version_id,
                source_sha256=item.source_sha256,
                anchor=item.anchor,
                excerpt_sha256=item.excerpt_sha256,
                evidence_role=item.evidence_role,
            )
            for item in evidence
        ],
        approval=ArtifactApprovalResponse(
            id=approval.id,
            status=approval.status,
            requested_by=approval.requested_by,
            assigned_reviewer_id=approval.assigned_reviewer_id,
            decision_by=approval.decision_by,
            decision_reason=approval.decision_reason,
            decided_at=approval.decided_at,
            expires_at=approval.expires_at,
        ),
    )


@router.get(
    "/cases/{case_id}/verification/latest",
    response_model=VerificationReportResponse | None,
)
async def get_latest_verification(
    case_id: UUID,
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(session_dependency),
) -> VerificationReportResponse | None:
    await _case_for_read(session, case_id, principal)
    report = await session.scalar(
        select(VerificationReport)
        .where(VerificationReport.case_id == str(case_id))
        .order_by(VerificationReport.created_at.desc())
        .limit(1)
    )
    return _verification_response(report) if report else None


@router.post(
    "/cases/{case_id}/verification",
    response_model=VerificationReportResponse,
)
async def verify_case_impact(
    case_id: UUID,
    request: Request,
    idempotency_key: IdempotencyKey,
    principal: Principal = Depends(VERIFICATION_REQUESTERS),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> VerificationReportResponse:
    case = await _case_for_read(session, case_id, principal, lock=True)
    _require_case_write(case, principal)
    event_key = _event_key("verification-run", principal, idempotency_key)
    prior_event = await session.scalar(
        select(CaseEvent).where(
            CaseEvent.case_id == case.id,
            CaseEvent.idempotency_key == event_key,
        )
    )
    if prior_event is not None:
        report = await session.get(
            VerificationReport, str(prior_event.payload.get("verification_report_id", ""))
        )
        if report is None:
            raise HTTPException(status_code=409, detail="Verification replay target is missing")
        return _verification_response(report)
    report = await VerificationEngine(session, principal).verify(case)
    case.status = {
        "PASS": AgentCaseStatus.READY.value,
        "REVISE": AgentCaseStatus.NEEDS_REVISION.value,
        "BLOCK": AgentCaseStatus.BLOCKED.value,
    }[report.status]
    await _append_event(
        session,
        case=case,
        event_type=f"VERIFICATION_{report.status}",
        principal=principal,
        request_id=request.state.request_id,
        idempotency_key=event_key,
        payload={
            "verification_report_id": report.id,
            "report_sha256": report.report_sha256,
            "status": report.status,
            "correction_iteration": report.correction_iteration,
            "issue_count": len(report.issues),
        },
    )
    add_audit_event(
        session,
        principal=principal,
        request_id=request.state.request_id,
        operation="case.verification.run",
        object_type="verification_report",
        object_id=report.id,
        application_version=settings.app_version,
        after={"status": report.status, "report_sha256": report.report_sha256},
    )
    await session.commit()
    return _verification_response(report)


@router.get("/cases/{case_id}/artifacts", response_model=ArtifactPageResponse)
async def list_case_artifacts(
    case_id: UUID,
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(session_dependency),
) -> ArtifactPageResponse:
    await _case_for_read(session, case_id, principal)
    rows = (
        await session.execute(
            select(Artifact, ArtifactVersion)
            .join(ArtifactVersion, ArtifactVersion.artifact_id == Artifact.id)
            .where(Artifact.case_id == str(case_id))
            .order_by(ArtifactVersion.version.desc())
        )
    ).all()
    return ArtifactPageResponse(
        items=[
            await _artifact_response(session, principal, artifact, version)
            for artifact, version in rows
        ]
    )


@router.post(
    "/cases/{case_id}/artifacts/compose",
    response_model=ArtifactVersionResponse,
)
async def compose_case_artifact(
    case_id: UUID,
    payload: ArtifactComposeRequest,
    request: Request,
    idempotency_key: IdempotencyKey,
    principal: Principal = Depends(VERIFICATION_REQUESTERS),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> ArtifactVersionResponse:
    case = await _case_for_read(session, case_id, principal, lock=True)
    _require_case_write(case, principal)
    event_key = _event_key("artifact-compose", principal, idempotency_key)
    fingerprint = _request_fingerprint(payload.model_dump(mode="json"))
    prior = await session.scalar(
        select(CaseEvent).where(
            CaseEvent.case_id == case.id,
            CaseEvent.idempotency_key == event_key,
        )
    )
    if prior is not None:
        if prior.payload.get("request_fingerprint") != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency key payload conflict")
        version = await session.get(
            ArtifactVersion, str(prior.payload.get("artifact_version_id", ""))
        )
        artifact = await session.get(Artifact, version.artifact_id if version else "")
        if version is None or artifact is None:
            raise HTTPException(status_code=409, detail="Artifact replay target is missing")
        return await _artifact_response(session, principal, artifact, version)
    artifact, version, approval = await ArtifactComposer(session).compose(
        case,
        requested_by=principal.subject,
        title=payload.title,
        assigned_reviewer_id=payload.assigned_reviewer_id,
        approval_idempotency_key=_event_key(
            "artifact-approval-request", principal, idempotency_key
        ),
        expires_at=utcnow() + timedelta(days=7),
    )
    case.status = AgentCaseStatus.WAITING_FOR_REVIEW.value
    await _append_event(
        session,
        case=case,
        event_type="ARTIFACT_COMPOSED",
        principal=principal,
        request_id=request.state.request_id,
        idempotency_key=event_key,
        payload={
            "request_fingerprint": fingerprint,
            "artifact_id": artifact.id,
            "artifact_version_id": version.id,
            "version": version.version,
            "content_sha256": version.content_sha256,
            "evidence_manifest_sha256": version.evidence_manifest_sha256,
            "approval_id": approval.id,
        },
    )
    add_audit_event(
        session,
        principal=principal,
        request_id=request.state.request_id,
        operation="case.artifact.compose",
        object_type="artifact_version",
        object_id=version.id,
        application_version=settings.app_version,
        after={
            "content_sha256": version.content_sha256,
            "evidence_manifest_sha256": version.evidence_manifest_sha256,
        },
    )
    await session.commit()
    return await _artifact_response(session, principal, artifact, version)


@router.post(
    "/cases/{case_id}/artifacts/{artifact_version_id}/decision",
    response_model=ArtifactVersionResponse,
)
async def decide_case_artifact(
    case_id: UUID,
    artifact_version_id: UUID,
    payload: ArtifactDecisionRequest,
    request: Request,
    idempotency_key: IdempotencyKey,
    principal: Principal = Depends(ARTIFACT_REVIEWERS),
    settings: Settings = Depends(settings_dependency),
    session: AsyncSession = Depends(session_dependency),
) -> ArtifactVersionResponse:
    case = await _case_for_read(session, case_id, principal, lock=True)
    version = await session.scalar(
        select(ArtifactVersion)
        .where(
            ArtifactVersion.id == str(artifact_version_id),
            ArtifactVersion.case_id == case.id,
        )
        .with_for_update()
    )
    if version is None:
        raise HTTPException(status_code=404, detail="Artifact version not found")
    artifact = await session.get(Artifact, version.artifact_id)
    approval = await session.scalar(
        select(ApprovalRequest)
        .where(
            ApprovalRequest.artifact_version_id == version.id,
            ApprovalRequest.approval_type == "ARTIFACT_APPROVAL",
        )
        .with_for_update()
    )
    if artifact is None or approval is None:
        raise HTTPException(status_code=409, detail="Artifact review binding is incomplete")
    event_key = _event_key("artifact-decision", principal, idempotency_key)
    fingerprint = _request_fingerprint(payload.model_dump(mode="json"))
    prior = await session.scalar(
        select(CaseEvent).where(
            CaseEvent.case_id == case.id,
            CaseEvent.idempotency_key == event_key,
        )
    )
    if prior is None:
        if approval.assigned_reviewer_id and approval.assigned_reviewer_id != principal.subject:
            raise HTTPException(status_code=403, detail="Artifact is assigned to another reviewer")
        if approval.requested_by == principal.subject:
            raise HTTPException(status_code=403, detail="Independent artifact review is required")
        if approval.status != ApprovalStatus.PENDING.value or version.status != "DRAFT":
            raise HTTPException(status_code=409, detail="Artifact review is already terminal")
        if (
            version.content_sha256 != payload.expected_content_sha256
            or version.evidence_manifest_sha256
            != payload.expected_evidence_manifest_sha256
            or approval.artifact_sha256 != payload.expected_content_sha256
            or approval.artifact_evidence_manifest_sha256
            != payload.expected_evidence_manifest_sha256
            or version.bound_state_hash != case.current_state_hash
        ):
            raise HTTPException(status_code=409, detail="Artifact review binding is stale")
        approved = payload.decision == "approve"
        approval.status = (
            ApprovalStatus.APPROVED.value if approved else ApprovalStatus.REJECTED.value
        )
        approval.decision_by = principal.subject
        approval.decision_reason = payload.reason
        approval.decided_at = utcnow()
        version.status = (
            ArtifactVersionStatus.APPROVED.value
            if approved
            else ArtifactVersionStatus.REJECTED.value
        )
        case.status = (
            AgentCaseStatus.COMPLETED.value
            if approved
            else AgentCaseStatus.NEEDS_REVISION.value
        )
        await _append_event(
            session,
            case=case,
            event_type="ARTIFACT_APPROVED" if approved else "ARTIFACT_REJECTED",
            principal=principal,
            request_id=request.state.request_id,
            idempotency_key=event_key,
            payload={
                "request_fingerprint": fingerprint,
                "artifact_version_id": version.id,
                "content_sha256": version.content_sha256,
                "evidence_manifest_sha256": version.evidence_manifest_sha256,
                "decision": payload.decision,
                "reason": payload.reason,
            },
        )
        add_audit_event(
            session,
            principal=principal,
            request_id=request.state.request_id,
            operation="case.artifact.decision",
            object_type="artifact_version",
            object_id=version.id,
            application_version=settings.app_version,
            after={"status": version.status, "reason": payload.reason},
        )
        await session.commit()
    elif prior.payload.get("request_fingerprint") != fingerprint:
        raise HTTPException(status_code=409, detail="Idempotency key payload conflict")
    return await _artifact_response(session, principal, artifact, version)


@router.get("/cases/{case_id}/artifacts/{artifact_version_id}/export")
async def export_case_artifact(
    case_id: UUID,
    artifact_version_id: UUID,
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(session_dependency),
) -> Response:
    await _case_for_read(session, case_id, principal)
    version = await session.scalar(
        select(ArtifactVersion).where(
            ArtifactVersion.id == str(artifact_version_id),
            ArtifactVersion.case_id == str(case_id),
        )
    )
    if version is None:
        raise HTTPException(status_code=404, detail="Artifact version not found")
    await _require_artifact_acl(session, principal, version)
    if version.status != ArtifactVersionStatus.APPROVED.value:
        raise HTTPException(status_code=409, detail="Only an approved artifact can be exported")
    payload = json.dumps(version.content, ensure_ascii=False, indent=2, sort_keys=True)
    return Response(
        payload,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="regulatory-impact-review-v{version.version}.json"'
            ),
            "X-Artifact-SHA256": version.content_sha256,
            "X-Evidence-Manifest-SHA256": version.evidence_manifest_sha256,
        },
    )
