from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cases.hashing import artifact_evidence_manifest_sha256, canonical_sha256
from app.internal_knowledge.embedding import tokens
from app.internal_knowledge.seed import sha256_text
from app.models import (
    ApprovalRequest,
    ApprovalStatus,
    Artifact,
    ArtifactEvidence,
    ArtifactVersion,
    Case,
    CasePlan,
    CaseSource,
    DocumentChunk,
    DocumentVersion,
    ImpactHypothesis,
    ImpactHypothesisStatus,
    InternalAssetVersion,
    VerificationReport,
    VerificationStatus,
)
from app.security.auth import Principal

FORBIDDEN_CONCLUSIONS = (
    "is noncompliant",
    "is not compliant",
    "gmp violation",
    "capa is required",
    "must create capa",
    "must revise the sop",
    "must revise sop",
)
PROMPT_INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all instructions",
    "system prompt",
    "developer message",
    "call this tool",
)


async def latest_approved_plan(session: AsyncSession, case: Case) -> CasePlan:
    plan = await session.scalar(
        select(CasePlan)
        .join(
            ApprovalRequest,
            (ApprovalRequest.plan_id == CasePlan.id)
            & (ApprovalRequest.approval_type == "PLAN_APPROVAL")
            & (ApprovalRequest.status == ApprovalStatus.APPROVED.value),
        )
        .where(CasePlan.case_id == case.id)
        .order_by(CasePlan.version.desc())
        .limit(1)
    )
    if plan is None:
        raise HTTPException(status_code=409, detail="No approved plan is available")
    if plan.based_on_state_hash != case.current_state_hash:
        raise HTTPException(status_code=409, detail="The approved plan is stale")
    return plan


def verification_input_sha256(
    case: Case,
    plan: CasePlan,
    hypotheses: list[ImpactHypothesis],
) -> str:
    return canonical_sha256(
        {
            "schema_version": "verification-input@1.0.0",
            "case_id": case.id,
            "state_hash": case.current_state_hash,
            "plan_id": plan.id,
            "plan_sha256": plan.plan_sha256,
            "hypotheses": [
                {
                    "id": item.id,
                    "sha256": item.hypothesis_sha256,
                    "status": item.status,
                }
                for item in sorted(hypotheses, key=lambda value: value.id)
            ],
        }
    )


class VerificationEngine:
    name = "verification-agent"
    version = "1.2.1"

    def __init__(self, session: AsyncSession, principal: Principal) -> None:
        self.session = session
        self.principal = principal

    async def verify(self, case: Case) -> VerificationReport:
        plan = await latest_approved_plan(self.session, case)
        hypotheses = list(
            (
                await self.session.scalars(
                    select(ImpactHypothesis)
                    .where(
                        ImpactHypothesis.case_id == case.id,
                        ImpactHypothesis.status == ImpactHypothesisStatus.ACCEPTED.value,
                    )
                    .order_by(ImpactHypothesis.created_at, ImpactHypothesis.id)
                )
            ).all()
        )
        if not hypotheses:
            raise HTTPException(
                status_code=409,
                detail="At least one independently accepted impact hypothesis is required",
            )
        input_sha256 = verification_input_sha256(case, plan, hypotheses)
        prior = await self.session.scalar(
            select(VerificationReport)
            .where(
                VerificationReport.case_id == case.id,
                VerificationReport.input_sha256 == input_sha256,
            )
            .order_by(VerificationReport.correction_iteration.desc())
            .limit(1)
        )
        if prior and prior.status in {
            VerificationStatus.PASS.value,
            VerificationStatus.BLOCK.value,
        }:
            return prior
        iteration = (prior.correction_iteration + 1) if prior else 0
        if iteration > 2:
            raise HTTPException(status_code=409, detail="Correction-loop limit is exhausted")

        issues: list[dict[str, Any]] = []
        checks: list[dict[str, str]] = []
        for hypothesis in hypotheses:
            await self._verify_hypothesis(case, hypothesis, issues, checks)
        self._detect_contradictions(hypotheses, issues, checks)
        status = self._status(issues)
        if status == VerificationStatus.REVISE.value and iteration == 2:
            issues.append(
                self._issue(
                    "CRITICAL",
                    "CORRECTION_LOOP_EXHAUSTED",
                    "Verification report",
                    "Two targeted correction attempts did not resolve all material issues.",
                    [],
                    "Stop automatic correction and route the case to human investigation.",
                    "case-orchestrator",
                )
            )
            status = VerificationStatus.BLOCK.value
        report_payload = {
            "case_id": case.id,
            "plan_id": plan.id,
            "plan_version": plan.version,
            "plan_sha256": plan.plan_sha256,
            "bound_state_hash": case.current_state_hash,
            "input_sha256": input_sha256,
            "correction_iteration": iteration,
            "status": status,
            "checks": checks,
            "issues": issues,
            "verified_hypothesis_ids": [item.id for item in hypotheses],
            "verifier_name": self.name,
            "verifier_version": self.version,
        }
        report = VerificationReport(
            **report_payload,
            report_sha256=canonical_sha256(report_payload),
            created_by=f"{self.name}@{self.version}",
        )
        self.session.add(report)
        await self.session.flush()
        return report

    async def _verify_hypothesis(
        self,
        case: Case,
        hypothesis: ImpactHypothesis,
        issues: list[dict[str, Any]],
        checks: list[dict[str, str]],
    ) -> None:
        issue_start = len(issues)
        expected_hash = canonical_sha256(
            {
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
        )
        if expected_hash != hypothesis.hypothesis_sha256:
            issues.append(
                self._issue(
                    "CRITICAL",
                    "HYPOTHESIS_HASH_MISMATCH",
                    hypothesis.statement,
                    "The persisted hypothesis no longer matches its content hash.",
                    [hypothesis.hypothesis_sha256, expected_hash],
                    "Block the record and restore it from an attributable immutable revision.",
                    "case-orchestrator",
                )
            )
        if not hypothesis.external_evidence or not hypothesis.internal_evidence:
            issues.append(
                self._issue(
                    "CRITICAL",
                    "MISSING_DUAL_EVIDENCE",
                    hypothesis.statement,
                    "A material relationship lacks external or internal evidence.",
                    [],
                    "Attach exact external and internal source-version anchors.",
                    "impact-analysis-agent",
                )
            )
        for evidence in hypothesis.external_evidence:
            await self._verify_external(case, hypothesis, evidence, issues)
        for evidence in hypothesis.internal_evidence:
            await self._verify_internal(hypothesis, evidence, issues)

        statement_folded = hypothesis.statement.casefold()
        boundary_terms = [term for term in FORBIDDEN_CONCLUSIONS if term in statement_folded]
        if boundary_terms:
            issues.append(
                self._issue(
                    "CRITICAL",
                    "COMPLIANCE_BOUNDARY_VIOLATION",
                    hypothesis.statement,
                    "The claim makes a prohibited compliance or remediation decision.",
                    boundary_terms,
                    "Rewrite as a bounded hypothesis and human verification question.",
                    "impact-analysis-agent",
                )
            )
        if not hypothesis.assumptions or not hypothesis.counterevidence or not hypothesis.unknowns:
            issues.append(
                self._issue(
                    "MAJOR",
                    "REASONING_DISTINCTIONS_MISSING",
                    hypothesis.statement,
                    "Assumptions, counterevidence, and unknowns must remain explicit.",
                    [],
                    "Restore every required reasoning distinction.",
                    "impact-analysis-agent",
                )
            )
        source_words = set()
        for evidence in [*hypothesis.external_evidence, *hypothesis.internal_evidence]:
            source_words.update(tokens(str(evidence.get("excerpt", ""))))
        claim_words = set(
            tokens(
                " ".join(
                    [
                        hypothesis.statement,
                        *hypothesis.known_facts,
                        *hypothesis.derived_relationships,
                    ]
                )
            )
        )
        semantic_overlap = len(source_words.intersection(claim_words)) / max(1, len(claim_words))
        if semantic_overlap < 0.03:
            issues.append(
                self._issue(
                    "MAJOR",
                    "CITATION_SEMANTIC_SUPPORT_LOW",
                    hypothesis.statement,
                    "The cited excerpts do not share enough material vocabulary with the claim.",
                    [f"lexical_entailment_proxy={semantic_overlap:.3f}"],
                    "Narrow the claim or provide a directly supporting evidence anchor.",
                    "impact-analysis-agent",
                )
            )
        checks.append(
            {
                "check": f"hypothesis:{hypothesis.id}",
                "status": "PASS" if len(issues) == issue_start else "FAIL",
                "detail": "Dual-source, boundary, distinction, and semantic checks completed.",
            }
        )

    async def _verify_external(
        self,
        case: Case,
        hypothesis: ImpactHypothesis,
        evidence: dict[str, Any],
        issues: list[dict[str, Any]],
    ) -> None:
        version_id = str(evidence.get("source_version_id", ""))
        source_hash = str(evidence.get("source_hash", ""))
        anchor_id = str(evidence.get("anchor_id", ""))
        source = await self.session.scalar(
            select(CaseSource).where(
                CaseSource.case_id == case.id,
                CaseSource.document_version_id == version_id,
                CaseSource.source_sha256 == source_hash,
            )
        )
        chunk = await self.session.scalar(
            select(DocumentChunk).where(
                DocumentChunk.document_version_id == version_id,
                DocumentChunk.source_anchor == anchor_id,
            )
        )
        excerpt = str(evidence.get("excerpt", ""))
        valid = source is not None and chunk is not None and excerpt in chunk.content
        if not valid:
            issues.append(
                self._issue(
                    "CRITICAL",
                    "EXTERNAL_CITATION_INVALID",
                    hypothesis.statement,
                    "The regulatory citation does not resolve through the exact case source pin.",
                    [anchor_id],
                    "Replace it with an exact retained case-source anchor and excerpt.",
                    "regulatory-evidence-agent",
                )
            )
        if any(marker in excerpt.casefold() for marker in PROMPT_INJECTION_MARKERS):
            issues.append(
                self._issue(
                    "CRITICAL",
                    "PROMPT_INJECTION_DETECTED",
                    hypothesis.statement,
                    "Instruction-like content was detected inside untrusted source evidence.",
                    [anchor_id],
                    "Isolate the source as quoted data and require human review.",
                    "verification-agent",
                )
            )

    async def _verify_internal(
        self,
        hypothesis: ImpactHypothesis,
        evidence: dict[str, Any],
        issues: list[dict[str, Any]],
    ) -> None:
        version_id = str(evidence.get("source_version_id", ""))
        version = await self.session.get(InternalAssetVersion, version_id)
        anchor_id = str(evidence.get("anchor_id", ""))
        excerpt = str(evidence.get("excerpt", ""))
        anchor = next(
            (item for item in (version.anchors if version else []) if item.get("id") == anchor_id),
            None,
        )
        valid = (
            version is not None
            and version.id == hypothesis.asset_version_id
            and version.content_sha256 == evidence.get("source_hash")
            and anchor is not None
            and str(anchor.get("excerpt", "")) == excerpt
        )
        if not valid:
            issues.append(
                self._issue(
                    "CRITICAL",
                    "INTERNAL_CITATION_INVALID",
                    hypothesis.statement,
                    "The internal citation does not match the exact asset revision and anchor.",
                    [anchor_id],
                    "Retrieve the exact authorized revision and anchor again.",
                    "internal-knowledge-agent",
                )
            )
        if version is not None and version.status != "EFFECTIVE":
            issues.append(
                self._issue(
                    "MAJOR",
                    "OBSOLETE_INTERNAL_REVISION",
                    hypothesis.statement,
                    "The relationship relies on a revision that is not effective.",
                    [f"revision={version.revision}", f"status={version.status}"],
                    "Confirm current applicability or cite the effective revision.",
                    "internal-knowledge-agent",
                )
            )
        if any(marker in excerpt.casefold() for marker in PROMPT_INJECTION_MARKERS):
            issues.append(
                self._issue(
                    "CRITICAL",
                    "PROMPT_INJECTION_DETECTED",
                    hypothesis.statement,
                    "Instruction-like content was detected inside internal evidence.",
                    [anchor_id],
                    "Isolate the record and require security review.",
                    "verification-agent",
                )
            )

    @staticmethod
    def _detect_contradictions(
        hypotheses: list[ImpactHypothesis],
        issues: list[dict[str, Any]],
        checks: list[dict[str, str]],
    ) -> None:
        groups: defaultdict[tuple[str, str], list[ImpactHypothesis]] = defaultdict(list)
        for item in hypotheses:
            groups[(item.finding_id, item.asset_id)].append(item)
        conflicts = [values for values in groups.values() if len(values) > 1]
        for values in conflicts:
            issues.append(
                VerificationEngine._issue(
                    "MAJOR",
                    "CONTRADICTORY_RELATIONSHIPS",
                    values[0].statement,
                    "Multiple accepted relationship types target the same finding and asset.",
                    [item.relationship_type for item in values],
                    "Reconcile the relationship type before composing an artifact.",
                    "impact-analysis-agent",
                )
            )
        checks.append(
            {
                "check": "cross-hypothesis-contradictions",
                "status": "FAIL" if conflicts else "PASS",
                "detail": f"{len(conflicts)} contradictory relationship groups detected.",
            }
        )

    @staticmethod
    def _status(issues: list[dict[str, Any]]) -> str:
        if any(item["severity"] == "CRITICAL" for item in issues):
            return VerificationStatus.BLOCK.value
        if issues:
            return VerificationStatus.REVISE.value
        return VerificationStatus.PASS.value

    @staticmethod
    def _issue(
        severity: str,
        code: str,
        affected_claim: str,
        reason: str,
        supporting_evidence: list[str],
        required_correction: str,
        responsible_agent: str,
    ) -> dict[str, Any]:
        return {
            "severity": severity,
            "code": code,
            "affected_claim": affected_claim,
            "reason": reason,
            "supporting_evidence": supporting_evidence,
            "required_correction": required_correction,
            "responsible_agent": responsible_agent,
        }


class ArtifactComposer:
    """Pure-template report composer; it never invents or retrieves new claims."""

    name = "artifact-composer"
    version = "1.0.0"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def compose(
        self,
        case: Case,
        *,
        requested_by: str,
        title: str,
        assigned_reviewer_id: str | None,
        approval_idempotency_key: str,
        expires_at: Any,
    ) -> tuple[Artifact, ArtifactVersion, ApprovalRequest]:
        plan = await latest_approved_plan(self.session, case)
        hypotheses = list(
            (
                await self.session.scalars(
                    select(ImpactHypothesis)
                    .where(
                        ImpactHypothesis.case_id == case.id,
                        ImpactHypothesis.status == ImpactHypothesisStatus.ACCEPTED.value,
                    )
                    .order_by(ImpactHypothesis.created_at, ImpactHypothesis.id)
                )
            ).all()
        )
        input_sha = verification_input_sha256(case, plan, hypotheses)
        verification = await self.session.scalar(
            select(VerificationReport)
            .where(
                VerificationReport.case_id == case.id,
                VerificationReport.input_sha256 == input_sha,
                VerificationReport.status == VerificationStatus.PASS.value,
            )
            .order_by(VerificationReport.created_at.desc())
            .limit(1)
        )
        if verification is None:
            raise HTTPException(
                status_code=409,
                detail="An exact PASS verification report is required before composition",
            )
        artifact = await self.session.scalar(
            select(Artifact).where(
                Artifact.case_id == case.id,
                Artifact.artifact_key == "regulatory-impact-review-package",
            )
        )
        if artifact is None:
            artifact = Artifact(
                case_id=case.id,
                artifact_key="regulatory-impact-review-package",
                artifact_type="REGULATORY_IMPACT_REVIEW",
                title=title,
                created_by=requested_by,
            )
            self.session.add(artifact)
            await self.session.flush()
        next_version = int(
            await self.session.scalar(
                select(func.coalesce(func.max(ArtifactVersion.version), 0)).where(
                    ArtifactVersion.artifact_id == artifact.id
                )
            )
            or 0
        ) + 1
        content = {
            "schema_version": "regulatory-impact-review-package@1.0.0",
            "title": title,
            "notice": (
                "Decision support only. This report does not determine compliance, "
                "require CAPA, or authorize controlled-system changes."
            ),
            "case": {
                "id": case.id,
                "objective": case.objective,
                "state_sha256": case.current_state_hash,
            },
            "plan": {
                "id": plan.id,
                "version": plan.version,
                "sha256": plan.plan_sha256,
            },
            "verification": {
                "id": verification.id,
                "status": verification.status,
                "sha256": verification.report_sha256,
                "agent": f"{verification.verifier_name}@{verification.verifier_version}",
            },
            "impact_hypotheses": [
                {
                    "id": item.id,
                    "sha256": item.hypothesis_sha256,
                    "asset_id": item.asset_id,
                    "asset_version_id": item.asset_version_id,
                    "relationship_type": item.relationship_type,
                    "statement": item.statement,
                    "known_facts": item.known_facts,
                    "derived_relationships": item.derived_relationships,
                    "assumptions": item.assumptions,
                    "counterevidence": item.counterevidence,
                    "unknowns": item.unknowns,
                    "recommended_verification": item.recommended_verification,
                    "external_evidence": item.external_evidence,
                    "internal_evidence": item.internal_evidence,
                }
                for item in hypotheses
            ],
        }
        evidence_members = await self._external_evidence_members(case, hypotheses)
        if not evidence_members:
            raise HTTPException(status_code=409, detail="Artifact evidence cannot be empty")
        evidence_hash = artifact_evidence_manifest_sha256(evidence_members)
        version = ArtifactVersion(
            artifact_id=artifact.id,
            case_id=case.id,
            version=next_version,
            plan_id=plan.id,
            plan_version=plan.version,
            plan_sha256=plan.plan_sha256,
            bound_state_hash=case.current_state_hash,
            run_id=None,
            verification_report_id=verification.id,
            content_schema_version="RegulatoryImpactReviewPackage@1.0.0",
            content=content,
            content_sha256=canonical_sha256(content),
            evidence_manifest_sha256=evidence_hash,
            status="DRAFT",
            created_by=f"{self.name}@{self.version}",
        )
        self.session.add(version)
        await self.session.flush()
        for member in evidence_members:
            self.session.add(
                ArtifactEvidence(
                    artifact_version_id=version.id,
                    case_id=case.id,
                    created_by=f"{self.name}@{self.version}",
                    **member,
                )
            )
        approval = ApprovalRequest(
            case_id=case.id,
            plan_id=plan.id,
            plan_version=plan.version,
            plan_sha256=plan.plan_sha256,
            bound_state_hash=case.current_state_hash,
            artifact_version_id=version.id,
            artifact_id=artifact.id,
            artifact_version=version.version,
            artifact_sha256=version.content_sha256,
            artifact_evidence_manifest_sha256=evidence_hash,
            approval_type="ARTIFACT_APPROVAL",
            status=ApprovalStatus.PENDING.value,
            requested_by=requested_by,
            assigned_reviewer_id=assigned_reviewer_id,
            idempotency_key=approval_idempotency_key,
            expires_at=expires_at,
        )
        self.session.add(approval)
        await self.session.flush()
        return artifact, version, approval

    async def _external_evidence_members(
        self,
        case: Case,
        hypotheses: list[ImpactHypothesis],
    ) -> list[dict[str, str]]:
        members: dict[tuple[str, str], dict[str, str]] = {}
        for hypothesis in hypotheses:
            for evidence in hypothesis.external_evidence:
                version_id = str(evidence["source_version_id"])
                source_hash = str(evidence["source_hash"])
                anchor_id = str(evidence["anchor_id"])
                source = await self.session.scalar(
                    select(CaseSource).where(
                        CaseSource.case_id == case.id,
                        CaseSource.document_version_id == version_id,
                        CaseSource.source_sha256 == source_hash,
                    )
                )
                version = await self.session.get(DocumentVersion, version_id)
                anchor = next(
                    (
                        item
                        for item in (version.source_anchors if version else [])
                        if item.get("anchor") == anchor_id
                    ),
                    None,
                )
                if source is None or anchor is None:
                    raise HTTPException(
                        status_code=409,
                        detail="Verified external evidence no longer resolves",
                    )
                members[(source.id, anchor_id)] = {
                    "case_source_id": source.id,
                    "document_version_id": version_id,
                    "source_sha256": source_hash,
                    "anchor": anchor_id,
                    "excerpt_sha256": sha256_text(str(anchor["text"])),
                    "evidence_role": "SUPPORTING",
                }
        return sorted(
            members.values(),
            key=lambda item: (item["case_source_id"], item["anchor"]),
        )
