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
from app.agent_platform.mcp.workflow.schemas import (
    CollaborationDraftArguments,
    DocumentMetadataArguments,
    EmailDraftArguments,
    InternalDraftArguments,
    TaskDraftArguments,
)
from app.audit import add_audit_event
from app.cases.hashing import canonical_sha256
from app.integrations.service import create_draft
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
BUNDLE_HASH = "a0896543a821f9ee474e9ede7219cd689af09e141186908d0cf1ec5f4ea2f67c"
AGENT_HASH = "4d1df30f66219c09cbce680ef23ed439b763f65a12620f1435b5e8db1c0beb42"
ARGUMENT_MODELS: dict[str, type[BaseModel]] = {
    "workflow.create_internal_notification_draft": InternalDraftArguments,
    "workflow.create_email_draft": EmailDraftArguments,
    "workflow.create_collaboration_draft": CollaborationDraftArguments,
    "workflow.create_task_draft": TaskDraftArguments,
    "workflow.read_document_metadata": DocumentMetadataArguments,
}
TOOL_SCOPES = {
    "workflow.create_internal_notification_draft": "workflow:draft:create",
    "workflow.create_email_draft": "workflow:email-draft:create",
    "workflow.create_collaboration_draft": "workflow:collaboration-draft:create",
    "workflow.create_task_draft": "workflow:task-draft:create",
    "workflow.read_document_metadata": "workflow:document-metadata:read",
}


class WorkflowMcpGateway:
    """Deny-by-default gateway with draft-only and ACL-filtered read semantics."""

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
        started_at = utcnow()
        started = monotonic()
        model = ARGUMENT_MODELS.get(tool_name)
        if model is None:
            return self._error(
                request_id, tool_name, "PERMISSION_DENIED", "Tool is not allowlisted"
            )
        try:
            validated = model.model_validate(arguments)
        except ValidationError:
            return self._error(
                request_id, tool_name, "INVALID_ARGUMENTS", "Arguments do not match the contract"
            )
        try:
            access = await self._authorize(tool_name, context)
            arguments_payload = validated.model_dump(mode="json")
            arguments_sha256 = canonical_sha256(arguments_payload)
            existing = await self.session.scalar(
                select(ToolInvocation).where(
                    ToolInvocation.run_id == access["run"].id,
                    ToolInvocation.idempotency_key == self._invocation_key(context),
                )
            )
            if existing:
                if existing.arguments_sha256 != arguments_sha256 or existing.tool_name != tool_name:
                    return self._error(
                        request_id,
                        tool_name,
                        "CONFLICT",
                        "Idempotency key is bound to different arguments",
                    )
                return dict(existing.structured_result or {})
            self._consume_budget(access["run"], access["invocation"])
            result = await self._execute(
                request_id=request_id,
                tool_name=tool_name,
                arguments=validated,
                context=context,
                access=access,
            )
            policy = PolicyDecision(
                case_id=access["case"].id,
                run_id=access["run"].id,
                bound_state_hash=access["case"].current_state_hash,
                agent_version_id=access["agent"].id,
                tool_version_id=access["tool"].id,
                request_id=request_id,
                idempotency_key=f"workflow-policy:{context.run_id}:{context.idempotency_key}",
                principal_subject=context.principal.subject,
                action=tool_name,
                effect="ALLOW",
                policy_key="workflow-mcp-draft-or-read-only",
                policy_version="1.0.0",
                policy_sha256=canonical_sha256(
                    {"bundle_sha256": BUNDLE_HASH, "external_delivery_allowed": False}
                ),
                input_sha256=arguments_sha256,
                decision_sha256=canonical_sha256(
                    {"effect": "ALLOW", "action": tool_name, "input": arguments_sha256}
                ),
                reason_codes=["APPROVED_PLAN", "DRAFT_OR_READ_ONLY", "NO_EXTERNAL_DELIVERY"],
                decision_metadata={"external_delivery_allowed": False},
                evaluated_by="pharma-agent-policy-engine",
            )
            self.session.add(policy)
            await self.session.flush()
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
                arguments_sha256=arguments_sha256,
                policy_effect="ALLOW",
                status="SUCCEEDED",
                structured_result=result,
                result_sha256=canonical_sha256(result),
                provenance=[],
                warnings=list(result.get("warnings") or []),
                latency_ms=max(0, round((monotonic() - started) * 1000)),
                started_at=started_at,
                completed_at=utcnow(),
            )
            self.session.add(invocation)
            add_audit_event(
                self.session,
                principal=context.principal,
                request_id=request_id,
                operation="mcp.workflow.invoke",
                object_type="tool_invocation",
                object_id=invocation.id,
                application_version=self.application_version,
                after={"tool": tool_name, "result_sha256": invocation.result_sha256},
            )
            await self.session.commit()
            return result
        except HTTPException as exc:
            await self.session.rollback()
            code = "PROHIBITED_ACTION" if exc.status_code == 422 else "ACCESS_BLOCKED"
            return self._error(request_id, tool_name, code, str(exc.detail))
        except PermissionError as exc:
            await self.session.rollback()
            return self._error(request_id, tool_name, "PERMISSION_DENIED", str(exc))
        except Exception:
            await self.session.rollback()
            return self._error(
                request_id, tool_name, "INTERNAL_ERROR", "Workflow tool failed safely"
            )

    async def _authorize(
        self, tool_name: str, context: KnowledgeInvocationContext
    ) -> dict[str, Any]:
        if not context.user_authenticated or not context.runtime_authenticated:
            raise PermissionError("Authenticated user and runtime are required")
        if context.runtime_service != "pharma-agent-runtime":
            raise PermissionError("Runtime service identity is not authorized")
        if context.agent_name != "case-orchestrator" or context.agent_version != "1.0.0":
            raise PermissionError("Only the reviewed case orchestrator may use workflow tools")
        if TOOL_SCOPES[tool_name] not in context.scopes:
            raise PermissionError("Required workflow tool scope is absent")
        case = await self.session.get(Case, context.case_id)
        if (
            case is None
            or case.owner_subject != context.principal.subject
            or case.current_state_hash != context.case_state_hash
        ):
            raise PermissionError("Case identity or state binding is unavailable")
        run = await self.session.get(CaseRun, context.run_id)
        if run is None or run.case_id != case.id or run.status != AgentRunStatus.RUNNING.value:
            raise PermissionError("Exact active case run is unavailable")
        approval = await self.session.scalar(
            select(ApprovalRequest.id).where(
                ApprovalRequest.plan_id == run.plan_id,
                ApprovalRequest.approval_type == "PLAN_APPROVAL",
                ApprovalRequest.status == ApprovalStatus.APPROVED.value,
            )
        )
        if approval is None:
            raise PermissionError("Approved plan binding is required")
        step_key = (run.checkpoint or {}).get("step_key")
        invocation = await self.session.scalar(
            select(AgentInvocation).where(
                AgentInvocation.run_id == run.id,
                AgentInvocation.step_key == step_key,
                AgentInvocation.status == AgentInvocationStatus.RUNNING.value,
            )
        )
        if invocation is None or not invocation.agent_version_id:
            raise PermissionError("Active orchestrator invocation is unavailable")
        agent = await self.session.get(AgentVersion, invocation.agent_version_id)
        if (
            agent is None
            or agent.agent_key != "case-orchestrator"
            or agent.version != "1.0.0"
            or agent.manifest_sha256 != AGENT_HASH
            or agent.release_status not in {"APPROVED", "PRODUCTION"}
        ):
            raise PermissionError("Reviewed orchestrator binding is unavailable")
        suspension = await active_suspension(self.session, [agent.id])
        if suspension:
            raise PermissionError(f"Agent execution is suspended by {suspension.control_key}")
        step = await self.session.get(CasePlanStep, invocation.plan_step_id)
        tool = await self.session.scalar(
            select(ToolVersion).where(
                ToolVersion.id.in_(list(step.tool_version_ids or []) if step else []),
                ToolVersion.tool_key == tool_name,
                ToolVersion.version == TOOL_VERSION,
                ToolVersion.server_key == "workflow-mcp",
                ToolVersion.manifest_sha256 == BUNDLE_HASH,
                ToolVersion.release_status.in_(["APPROVED", "PRODUCTION"]),
            )
        )
        if tool is None:
            raise PermissionError("Approved plan does not bind this workflow tool")
        return {"case": case, "run": run, "invocation": invocation, "agent": agent, "tool": tool}

    @staticmethod
    def _consume_budget(run: CaseRun, invocation: AgentInvocation) -> None:
        checkpoint = deepcopy(run.checkpoint or {})
        budget = dict(checkpoint.get("budget") or {})
        used = int(budget.get("tool_calls", 0))
        maximum = int((invocation.limits or {}).get("max_tool_calls", 0))
        if maximum <= 0 or used >= maximum:
            raise PermissionError("Active workflow tool-call budget is exhausted")
        budget["tool_calls"] = used + 1
        checkpoint["budget"] = budget
        run.checkpoint = checkpoint

    async def _execute(
        self,
        *,
        request_id: str,
        tool_name: str,
        arguments: BaseModel,
        context: KnowledgeInvocationContext,
        access: dict[str, Any],
    ) -> dict[str, Any]:
        null_metadata = {
            "draft_id": None,
            "channel": None,
            "draft_status": None,
            "content_sha256": None,
            "asset_id": None,
            "asset_version_id": None,
            "asset_key": None,
            "title": None,
            "revision": None,
            "document_status": None,
        }
        if isinstance(arguments, DocumentMetadataArguments):
            asset, version = await KnowledgeRepository(
                self.session, context.principal
            ).require_version(str(arguments.asset_version_id))
            data = {
                **null_metadata,
                "resource_type": "DOCUMENT_METADATA",
                "asset_id": asset.id,
                "asset_version_id": version.id,
                "asset_key": asset.asset_key,
                "title": asset.title,
                "revision": version.revision,
                "document_status": version.status,
                "external_delivery_allowed": False,
                "access_filtered": True,
                "integration_mode": "READ_ONLY",
            }
        else:
            channel = {
                "workflow.create_internal_notification_draft": "INTERNAL",
                "workflow.create_email_draft": "EMAIL",
                "workflow.create_collaboration_draft": getattr(arguments, "platform", "SLACK"),
                "workflow.create_task_draft": getattr(arguments, "system", "TASK"),
            }[tool_name]
            draft = await create_draft(
                self.session,
                case=access["case"],
                principal=context.principal,
                channel=channel,
                destination=str(arguments.destination),
                title=str(arguments.title),
                body=str(arguments.body),
                run_id=access["run"].id,
                idempotency_key=f"workflow-draft:{context.run_id}:{context.idempotency_key}",
            )
            data = {
                **null_metadata,
                "resource_type": "INTEGRATION_DRAFT",
                "draft_id": draft.id,
                "channel": draft.channel,
                "draft_status": draft.status,
                "content_sha256": draft.content_sha256,
                "external_delivery_allowed": False,
                "access_filtered": True,
                "integration_mode": "DRAFT_ONLY",
            }
        return {
            "status": "success",
            "request_id": request_id,
            "tool_name": tool_name,
            "tool_version": TOOL_VERSION,
            "data": data,
            "warnings": ["No external delivery or controlled-system write occurred."],
        }

    @staticmethod
    def _invocation_key(context: KnowledgeInvocationContext) -> str:
        return f"workflow:{context.idempotency_key}"

    @staticmethod
    def _error(request_id: str, tool_name: str, code: str, message: str) -> dict[str, Any]:
        public_name = tool_name if tool_name in ARGUMENT_MODELS else "workflow.unknown"
        return {
            "status": "error",
            "request_id": request_id,
            "tool_name": public_name,
            "tool_version": TOOL_VERSION,
            "error": {"code": code, "message": message[:1000], "retryable": False},
            "next_valid_actions": ["inspect_run_trace"],
        }
