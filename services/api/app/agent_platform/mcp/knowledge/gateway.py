from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from time import monotonic
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_platform.controls import active_suspension
from app.agent_platform.mcp.knowledge.context import KnowledgeInvocationContext
from app.agent_platform.mcp.knowledge.schemas import (
    GetAnchorArguments,
    GetAssetArguments,
    GetDocumentVersionArguments,
    KnowledgeData,
    KnowledgeError,
    KnowledgeErrorCode,
    KnowledgeErrorResult,
    KnowledgeProvenance,
    KnowledgeRecord,
    KnowledgeSuccess,
    SearchAssetsArguments,
)
from app.audit import add_audit_event
from app.cases.hashing import canonical_sha256
from app.internal_knowledge.retrieval import KnowledgeRepository
from app.models import (
    AgentInvocation,
    AgentInvocationStatus,
    AgentRunStatus,
    AgentVersion,
    ApprovalRequest,
    ApprovalStatus,
    Case,
    CasePlanStep,
    CaseRun,
    PolicyDecision,
    ToolInvocation,
    ToolVersion,
    utcnow,
)

TOOL_VERSION = "1.0.0"
BUNDLE_HASH = "324b65c53afbdcaa6e9af759a467fb86eccef99de97a9703419d34d460d3e2b1"
POLICY_VERSION = "1.0.0"
POLICY_DEFINITION = {
    "policy": "knowledge-mcp-invocation",
    "version": POLICY_VERSION,
    "default": "DENY",
    "controls": [
        "authenticated_runtime",
        "exact_active_run",
        "approved_plan",
        "reviewed_agent_and_tool",
        "positive_asset_acl_before_retrieval",
        "durable_tool_budget",
    ],
}
POLICY_HASH = canonical_sha256(POLICY_DEFINITION)

ARGUMENT_MODELS: dict[str, type[BaseModel]] = {
    "knowledge.search_assets": SearchAssetsArguments,
    "knowledge.get_asset": GetAssetArguments,
    "knowledge.get_document_version": GetDocumentVersionArguments,
    "knowledge.get_anchor": GetAnchorArguments,
    "knowledge.get_revision_history": GetAssetArguments,
    "knowledge.get_related_assets": GetAssetArguments,
}
TOOL_SCOPES = {
    "knowledge.search_assets": "knowledge:search",
    "knowledge.get_asset": "knowledge:asset:read",
    "knowledge.get_document_version": "knowledge:version:read",
    "knowledge.get_anchor": "knowledge:anchor:read",
    "knowledge.get_revision_history": "knowledge:history:read",
    "knowledge.get_related_assets": "knowledge:relation:read",
}
AGENT_TOOLS = {
    ("internal-knowledge-agent", "1.1.0"): frozenset(
        {
            "knowledge.search_assets",
            "knowledge.get_document_version",
            "knowledge.get_anchor",
            "knowledge.get_revision_history",
            "knowledge.get_related_assets",
        }
    ),
    ("impact-analysis-agent", "1.0.2"): frozenset(
        {
            "knowledge.get_asset",
            "knowledge.get_related_assets",
            "knowledge.get_anchor",
        }
    ),
}
AGENT_HASHES = {
    ("internal-knowledge-agent", "1.1.0"): (
        "f1a6ff4ffed4033dd6928c974b606b1dffff7996a9f2529423fc46c6b9c335c5"
    ),
    ("impact-analysis-agent", "1.0.2"): (
        "df2372f12bb1bac165608c7722e38e3d6954dae962365ef66cbdaebab1d591f5"
    ),
}


def _reviewed_manifest_matches(value: object, expected_hash: str) -> bool:
    if not isinstance(value, Mapping):
        return False
    metadata = value.get("metadata")
    if not isinstance(metadata, Mapping) or metadata.get("definitionHash") != expected_hash:
        return False
    canonical = deepcopy(dict(value))
    canonical_metadata = dict(canonical["metadata"])
    canonical_metadata.pop("definitionHash", None)
    canonical["metadata"] = canonical_metadata
    return canonical_sha256(canonical) == expected_hash


class GatewayDenied(RuntimeError):
    def __init__(
        self,
        code: KnowledgeErrorCode,
        message: str,
        *actions: str,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.actions = list(actions)


class KnowledgeMcpGateway:
    """Private, attributable MCP-like boundary over the internal repository."""

    def __init__(self, session: AsyncSession, *, application_version: str = "unknown") -> None:
        self.session = session
        self.application_version = application_version

    async def invoke(
        self,
        *,
        tool_name: str,
        arguments: Mapping[str, object] | object,
        context: KnowledgeInvocationContext,
    ) -> dict[str, Any]:
        request_id = str(uuid4())
        started = monotonic()
        started_at = utcnow()
        public_tool_name = tool_name if tool_name in ARGUMENT_MODELS else "knowledge.unknown"
        try:
            argument_model = ARGUMENT_MODELS.get(tool_name)
            if argument_model is None:
                raise GatewayDenied(
                    KnowledgeErrorCode.PERMISSION_DENIED,
                    "Tool is not available to this agent.",
                    "use_allowlisted_tool",
                )
            try:
                validated = argument_model.model_validate(arguments)
            except ValidationError as exc:
                raise GatewayDenied(
                    KnowledgeErrorCode.INVALID_ARGUMENTS,
                    "Tool arguments do not match the approved contract.",
                    "correct_arguments",
                ) from exc
            argument_payload = validated.model_dump(mode="json")
            arguments_hash = canonical_sha256(argument_payload)
            access = await self._authorize(
                tool_name=tool_name,
                context=context,
                arguments_hash=arguments_hash,
            )
            replay = await self.session.scalar(
                select(ToolInvocation).where(
                    ToolInvocation.run_id == access["run"].id,
                    ToolInvocation.idempotency_key == self._invocation_key(context),
                )
            )
            if replay is not None:
                if (
                    replay.arguments_sha256 != arguments_hash
                    or replay.tool_name != tool_name
                    or replay.agent_name != context.agent_name
                ):
                    raise GatewayDenied(
                        KnowledgeErrorCode.CONFLICT,
                        "Idempotency key was already used with different arguments.",
                        "use_new_idempotency_key",
                    )
                return dict(replay.structured_result)

            self._consume_budget(access["run"], access["invocation"])
            try:
                data, provenance, warnings = await self._execute(
                    tool_name=tool_name,
                    arguments=validated,
                    context=context,
                )
                result = KnowledgeSuccess(
                    request_id=request_id,
                    tool_name=tool_name,
                    data=data,
                    provenance=provenance,
                    warnings=warnings,
                ).model_dump(mode="json")
                effect = "ALLOW"
                status = "SUCCEEDED"
                reason_codes = ["ACTIVE_APPROVED_PLAN", "ASSET_ACL_APPLIED"]
            except HTTPException as exc:
                # The public error is intentionally uniform for absent and inaccessible IDs.
                result = KnowledgeErrorResult(
                    request_id=request_id,
                    tool_name=tool_name,
                    error=KnowledgeError(
                        code=KnowledgeErrorCode.ACCESS_BLOCKED,
                        message="The internal asset is unavailable to the active identity.",
                    ),
                    next_valid_actions=["review_asset_access"],
                ).model_dump(mode="json")
                effect = "DENY"
                status = "DENIED"
                reason_codes = ["ASSET_NOT_FOUND_OR_ACCESS_BLOCKED", str(exc.status_code)]
                provenance = []
                warnings = []

            policy = PolicyDecision(
                case_id=access["case"].id,
                run_id=access["run"].id,
                bound_state_hash=access["case"].current_state_hash,
                agent_version_id=access["agent"].id,
                tool_version_id=access["tool"].id,
                request_id=request_id,
                idempotency_key=self._policy_key(context),
                principal_subject=context.principal.subject,
                action=tool_name,
                effect=effect,
                policy_key="knowledge-mcp-invocation",
                policy_version=POLICY_VERSION,
                policy_sha256=POLICY_HASH,
                input_sha256=arguments_hash,
                decision_sha256=canonical_sha256(
                    {
                        "effect": effect,
                        "input_sha256": arguments_hash,
                        "policy_sha256": POLICY_HASH,
                        "reason_codes": reason_codes,
                    }
                ),
                reason_codes=reason_codes,
                decision_metadata={
                    "acl_filtered_before_retrieval": True,
                    "agent_name": context.agent_name,
                    "tool_name": tool_name,
                },
                evaluated_by="pharma-agent-policy-engine",
            )
            self.session.add(policy)
            await self.session.flush()
            completed_at = utcnow()
            serialized_provenance = [
                item.model_dump(mode="json") if isinstance(item, BaseModel) else item
                for item in provenance
            ]
            invocation = ToolInvocation(
                case_id=access["case"].id,
                run_id=access["run"].id,
                agent_version_id=access["agent"].id,
                tool_version_id=access["tool"].id,
                policy_decision_id=policy.id,
                request_id=request_id,
                idempotency_key=self._invocation_key(context),
                principal_subject=context.principal.subject,
                runtime_service=context.runtime_service,
                agent_name=context.agent_name,
                agent_version=context.agent_version,
                tool_name=tool_name,
                tool_version=TOOL_VERSION,
                arguments_sha256=arguments_hash,
                policy_effect=effect,
                status=status,
                structured_result=result,
                result_sha256=canonical_sha256(result),
                provenance=serialized_provenance,
                warnings=warnings,
                latency_ms=max(0, round((monotonic() - started) * 1000)),
                started_at=started_at,
                completed_at=completed_at,
            )
            self.session.add(invocation)
            add_audit_event(
                self.session,
                principal=context.principal,
                request_id=request_id,
                operation="mcp.knowledge.invoke",
                object_type="tool_invocation",
                object_id=invocation.id,
                application_version=self.application_version,
                result="success" if status == "SUCCEEDED" else "denied",
                after={
                    "tool": tool_name,
                    "status": status,
                    "result_sha256": invocation.result_sha256,
                },
            )
            await self.session.commit()
            return result
        except GatewayDenied as exc:
            await self.session.rollback()
            return KnowledgeErrorResult(
                request_id=request_id,
                tool_name=public_tool_name,
                error=KnowledgeError(code=exc.code, message=exc.message),
                next_valid_actions=exc.actions,
            ).model_dump(mode="json")
        except Exception:
            await self.session.rollback()
            return KnowledgeErrorResult(
                request_id=request_id,
                tool_name=public_tool_name,
                error=KnowledgeError(
                    code=KnowledgeErrorCode.INTERNAL_ERROR,
                    message="The internal knowledge tool failed without releasing content.",
                    retryable=False,
                ),
                next_valid_actions=["inspect_run_trace"],
            ).model_dump(mode="json")

    async def _authorize(
        self,
        *,
        tool_name: str,
        context: KnowledgeInvocationContext,
        arguments_hash: str,
    ) -> dict[str, Any]:
        del arguments_hash
        if not context.user_authenticated:
            raise GatewayDenied(
                KnowledgeErrorCode.AUTH_EXPIRED,
                "The user authentication is absent or expired.",
                "reauthenticate_user",
            )
        if not context.runtime_authenticated or context.runtime_service != "pharma-agent-runtime":
            raise GatewayDenied(
                KnowledgeErrorCode.PERMISSION_DENIED,
                "The calling runtime is not authorized.",
                "use_authorized_runtime",
            )
        allowed = AGENT_TOOLS.get((context.agent_name, context.agent_version))
        if allowed is None or tool_name not in allowed:
            raise GatewayDenied(
                KnowledgeErrorCode.PERMISSION_DENIED,
                "The active agent version is not authorized for this tool.",
                "use_approved_agent",
            )
        if TOOL_SCOPES[tool_name] not in context.scopes:
            raise GatewayDenied(
                KnowledgeErrorCode.PERMISSION_DENIED,
                "The required tool scope is not active.",
                "request_authorization",
            )

        case = await self.session.scalar(
            select(Case).where(Case.id == context.case_id).with_for_update()
        )
        if (
            case is None
            or case.owner_subject != context.principal.subject
            or case.current_state_hash != context.case_state_hash
        ):
            raise GatewayDenied(
                KnowledgeErrorCode.CONFLICT,
                "The active case binding is unavailable or stale.",
                "refresh_case_context",
            )
        run = await self.session.scalar(
            select(CaseRun)
            .where(CaseRun.id == context.run_id, CaseRun.case_id == case.id)
            .with_for_update()
        )
        if (
            run is None
            or run.bound_state_hash != case.current_state_hash
            or run.status != AgentRunStatus.RUNNING.value
        ):
            raise GatewayDenied(
                KnowledgeErrorCode.CONFLICT,
                "The exact active run is unavailable.",
                "inspect_run_trace",
            )
        approval = await self.session.scalar(
            select(ApprovalRequest).where(
                ApprovalRequest.case_id == case.id,
                ApprovalRequest.plan_id == run.plan_id,
                ApprovalRequest.approval_type == "PLAN_APPROVAL",
                ApprovalRequest.status == ApprovalStatus.APPROVED.value,
            )
        )
        if approval is None:
            raise GatewayDenied(
                KnowledgeErrorCode.APPROVAL_REQUIRED,
                "A current approved plan is required.",
                "request_plan_approval",
            )
        checkpoint = run.checkpoint or {}
        step_key = checkpoint.get("step_key")
        invocation = await self.session.scalar(
            select(AgentInvocation).where(
                AgentInvocation.run_id == run.id,
                AgentInvocation.step_key == step_key,
                AgentInvocation.status == AgentInvocationStatus.RUNNING.value,
            )
        )
        if invocation is None or not invocation.agent_version_id:
            raise GatewayDenied(
                KnowledgeErrorCode.CONFLICT,
                "The active agent invocation is not bound to a reviewed agent.",
                "inspect_run_trace",
            )
        agent = await self.session.get(AgentVersion, invocation.agent_version_id)
        if (
            agent is None
            or agent.agent_key != context.agent_name
            or agent.version != context.agent_version
            or agent.manifest_sha256
            != AGENT_HASHES[(context.agent_name, context.agent_version)]
            or not _reviewed_manifest_matches(
                agent.manifest,
                AGENT_HASHES[(context.agent_name, context.agent_version)],
            )
            or agent.release_status not in {"APPROVED", "PRODUCTION"}
        ):
            raise GatewayDenied(
                KnowledgeErrorCode.PERMISSION_DENIED,
                "The bound agent definition is not executable.",
                "use_approved_agent",
            )
        suspension = await active_suspension(self.session, [agent.id])
        if suspension:
            raise GatewayDenied(
                KnowledgeErrorCode.PERMISSION_DENIED,
                f"Agent execution is suspended by {suspension.control_key}.",
                "inspect_runtime_controls",
            )
        step = await self.session.get(CasePlanStep, invocation.plan_step_id)
        tool_ids = {str(value) for value in (step.tool_version_ids if step else [])}
        tools = list(
            (
                await self.session.scalars(
                    select(ToolVersion).where(ToolVersion.id.in_(tool_ids))
                )
            ).all()
        )
        matching = [
            tool
            for tool in tools
            if tool.tool_key == tool_name
            and tool.version == TOOL_VERSION
            and tool.server_key == "knowledge-mcp"
            and tool.manifest_sha256 == BUNDLE_HASH
            and _reviewed_manifest_matches(tool.manifest, BUNDLE_HASH)
            and tool.release_status in {"APPROVED", "PRODUCTION"}
            and not tool.side_effecting
        ]
        if len(matching) != 1:
            raise GatewayDenied(
                KnowledgeErrorCode.PERMISSION_DENIED,
                "The approved plan does not bind this reviewed tool version.",
                "request_new_plan",
            )
        return {
            "case": case,
            "run": run,
            "invocation": invocation,
            "agent": agent,
            "tool": matching[0],
        }

    @staticmethod
    def _consume_budget(run: CaseRun, invocation: AgentInvocation) -> None:
        checkpoint = deepcopy(run.checkpoint or {})
        budget = dict(checkpoint.get("budget") or {})
        used = int(budget.get("tool_calls", 0))
        maximum = int((invocation.limits or {}).get("max_tool_calls", 0))
        if maximum <= 0 or used >= maximum:
            raise GatewayDenied(
                KnowledgeErrorCode.RATE_LIMITED,
                "The active step tool-call budget is exhausted.",
                "pause_and_review_budget",
            )
        budget["tool_calls"] = used + 1
        checkpoint["budget"] = budget
        checkpoint["knowledge_mcp_tool_calls"] = int(
            checkpoint.get("knowledge_mcp_tool_calls", 0)
        ) + 1
        run.checkpoint = checkpoint

    async def _execute(
        self,
        *,
        tool_name: str,
        arguments: BaseModel,
        context: KnowledgeInvocationContext,
    ) -> tuple[KnowledgeData, list[KnowledgeProvenance], list[str]]:
        repository = KnowledgeRepository(self.session, context.principal)
        records: list[KnowledgeRecord] = []
        provenance: list[KnowledgeProvenance] = []
        warnings = ["Synthetic portfolio demonstration data; not a controlled record."]
        resource_type = "SEARCH_RESULTS"

        if isinstance(arguments, SearchAssetsArguments):
            response = await repository.search(
                arguments.query,
                limit=arguments.limit,
                include_obsolete=arguments.include_obsolete,
            )
            for item in response.items:
                version = await repository.get_document_version(str(item.asset_version_id))
                anchor = (
                    item.internal_evidence_anchors[0]
                    if item.internal_evidence_anchors
                    else None
                )
                records.append(
                    KnowledgeRecord(
                        asset_id=item.asset_id,
                        asset_version_id=item.asset_version_id,
                        asset_key=item.asset_key,
                        asset_type=item.asset_type,
                        title=item.title,
                        domain=item.domain,
                        revision=item.revision,
                        status=item.effective_status,
                        content=None,
                        content_sha256=version.content_sha256,
                        anchor_id=anchor.id if anchor else None,
                        excerpt=anchor.excerpt if anchor else None,
                        relation_type=item.relationship_signal,
                        score=item.retrieval_score,
                    )
                )
                provenance.append(
                    KnowledgeProvenance(
                        source_version_id=item.asset_version_id,
                        source_hash=version.content_sha256,
                        anchor_id=anchor.id if anchor else None,
                    )
                )
        elif tool_name == "knowledge.get_asset":
            assert isinstance(arguments, GetAssetArguments)
            resource_type = "ASSET"
            asset = await repository.get_asset(str(arguments.asset_id))
            records.append(self._version_record(asset, asset.current_version))
            provenance.extend(self._version_provenance(asset.current_version))
        elif isinstance(arguments, GetAnchorArguments):
            resource_type = "ANCHOR"
            asset, version = await repository.require_version(str(arguments.asset_version_id))
            anchor = await repository.get_anchor(
                str(arguments.asset_version_id), arguments.anchor_id
            )
            records.append(
                KnowledgeRecord(
                    asset_id=asset.id,
                    asset_version_id=version.id,
                    asset_key=asset.asset_key,
                    asset_type=asset.asset_type,
                    title=asset.title,
                    domain=asset.domain,
                    revision=version.revision,
                    status=version.status,
                    content=None,
                    content_sha256=version.content_sha256,
                    anchor_id=anchor.id,
                    excerpt=anchor.excerpt,
                    relation_type=None,
                    score=None,
                )
            )
            provenance.append(
                KnowledgeProvenance(
                    source_version_id=version.id,
                    source_hash=version.content_sha256,
                    anchor_id=anchor.id,
                )
            )
        elif tool_name == "knowledge.get_document_version":
            assert isinstance(arguments, GetDocumentVersionArguments)
            resource_type = "DOCUMENT_VERSION"
            asset, _version = await repository.require_version(str(arguments.asset_version_id))
            version = await repository.get_document_version(str(arguments.asset_version_id))
            records.append(self._version_record(asset, version))
            provenance.extend(self._version_provenance(version))
        elif tool_name == "knowledge.get_revision_history":
            assert isinstance(arguments, GetAssetArguments)
            resource_type = "REVISION_HISTORY"
            asset = await repository.require_asset(str(arguments.asset_id))
            history = await repository.revision_history(str(arguments.asset_id))
            for revision in history.revisions:
                records.append(
                    KnowledgeRecord(
                        asset_id=asset.id,
                        asset_version_id=revision.id,
                        asset_key=asset.asset_key,
                        asset_type=asset.asset_type,
                        title=asset.title,
                        domain=asset.domain,
                        revision=revision.revision,
                        status=revision.status,
                        content=None,
                        content_sha256=revision.content_sha256,
                        anchor_id=None,
                        excerpt=None,
                        relation_type=None,
                        score=None,
                    )
                )
                provenance.append(
                    KnowledgeProvenance(
                        source_version_id=revision.id,
                        source_hash=revision.content_sha256,
                        anchor_id=None,
                    )
                )
        else:
            assert isinstance(arguments, GetAssetArguments)
            resource_type = "RELATED_ASSETS"
            related = await repository.related_assets(str(arguments.asset_id))
            for relation in related.items:
                item = relation.asset
                version = await repository.get_document_version(str(item.asset_version_id))
                anchor = item.internal_evidence_anchors[0]
                records.append(
                    KnowledgeRecord(
                        asset_id=item.asset_id,
                        asset_version_id=item.asset_version_id,
                        asset_key=item.asset_key,
                        asset_type=item.asset_type,
                        title=item.title,
                        domain=item.domain,
                        revision=item.revision,
                        status=item.effective_status,
                        content=None,
                        content_sha256=version.content_sha256,
                        anchor_id=anchor.id,
                        excerpt=anchor.excerpt,
                        relation_type=relation.relation_type,
                        score=relation.confidence,
                    )
                )
                provenance.extend(
                    KnowledgeProvenance(
                        source_version_id=evidence.asset_version_id,
                        source_hash=evidence.content_sha256,
                        anchor_id=evidence.anchor,
                    )
                    for evidence in relation.evidence
                )
        return (
            KnowledgeData(resource_type=resource_type, records=records),
            provenance,
            warnings,
        )

    @staticmethod
    def _version_record(asset: Any, version: Any) -> KnowledgeRecord:
        anchor = version.anchors[0] if version.anchors else None
        return KnowledgeRecord(
            asset_id=asset.id,
            asset_version_id=version.id,
            asset_key=asset.asset_key,
            asset_type=asset.asset_type,
            title=asset.title,
            domain=asset.domain,
            revision=version.revision,
            status=version.status,
            content=version.content,
            content_sha256=version.content_sha256,
            anchor_id=anchor.id if anchor else None,
            excerpt=anchor.excerpt if anchor else None,
            relation_type=None,
            score=None,
        )

    @staticmethod
    def _version_provenance(version: Any) -> list[KnowledgeProvenance]:
        return [
            KnowledgeProvenance(
                source_version_id=version.id,
                source_hash=version.content_sha256,
                anchor_id=anchor.id,
            )
            for anchor in version.anchors
        ] or [
            KnowledgeProvenance(
                source_version_id=version.id,
                source_hash=version.content_sha256,
                anchor_id=None,
            )
        ]

    @staticmethod
    def _policy_key(context: KnowledgeInvocationContext) -> str:
        return "knowledge-mcp-policy:" + canonical_sha256(
            {"run_id": context.run_id, "idempotency_key": context.idempotency_key}
        )

    @staticmethod
    def _invocation_key(context: KnowledgeInvocationContext) -> str:
        return "knowledge-mcp:" + canonical_sha256(
            {"run_id": context.run_id, "idempotency_key": context.idempotency_key}
        )
