from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI
from pydantic import BaseModel, ConfigDict, Field

from app.agent_platform.mcp.knowledge.context import KnowledgeInvocationContext
from app.agent_platform.mcp.knowledge.gateway import KnowledgeMcpGateway
from app.agent_platform.mcp.regulatory.context import HostInvocationContext, ToolCallBudget
from app.agent_platform.mcp.regulatory.gateway import RegulatoryMcpGateway
from app.agent_platform.mcp.regulatory.manifest import load_regulatory_tool_bundle
from app.agent_platform.mcp.workflow.gateway import WorkflowMcpGateway
from app.config import Settings, get_settings
from app.database import Database
from app.middleware import RequestContextMiddleware
from app.observability import configure_telemetry
from app.security.auth import Principal, require_roles


class PrivateInvocationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    server: Literal["regulatory-mcp", "knowledge-mcp", "workflow-mcp"]
    tool_name: str = Field(pattern=r"^(regulatory|knowledge|workflow)\.[a-z][a-z0-9_]*$")
    arguments: dict = Field(default_factory=dict)
    user_id: str = Field(min_length=1, max_length=255)
    user_roles: list[str] = Field(default_factory=list, max_length=20)
    tenant_id: str = Field(min_length=1, max_length=120)
    case_id: UUID
    case_state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    run_id: UUID
    agent_name: str = Field(min_length=1, max_length=160)
    agent_version: str = Field(min_length=1, max_length=80)
    idempotency_key: str = Field(min_length=16, max_length=200)
    approval_request_id: UUID | None = None
    scopes: list[str] = Field(min_length=1, max_length=30)
    maximum_tool_calls: int = Field(default=20, ge=1, le=100)


def create_private_mcp_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    database = Database(resolved.database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if resolved.auto_create_schema:
            await database.create_schema()
        try:
            yield
        finally:
            await database.dispose()

    app = FastAPI(
        title="PharmaAgent OS Private MCP Gateway",
        version=resolved.app_version,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = resolved
    app.add_middleware(RequestContextMiddleware, max_request_bytes=resolved.max_request_bytes)
    configure_telemetry(app, resolved)
    service_principal = require_roles("service")

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/mcp/v1/tools")
    async def list_tools(
        _principal: Principal = Depends(service_principal),
    ) -> dict[str, object]:
        regulatory = load_regulatory_tool_bundle()
        return {
            "servers": [
                {
                    "server": "regulatory-mcp",
                    "version": regulatory.version,
                    "definition_hash": regulatory.definition_hash,
                    "tools": sorted(regulatory.tools),
                },
                {
                    "server": "knowledge-mcp",
                    "version": "1.0.0",
                    "definition_hash": (
                        "324b65c53afbdcaa6e9af759a467fb86eccef99de97a9703419d34d460d3e2b1"
                    ),
                    "tools": [
                        "knowledge.get_anchor",
                        "knowledge.get_asset",
                        "knowledge.get_document_version",
                        "knowledge.get_related_assets",
                        "knowledge.get_revision_history",
                        "knowledge.search_assets",
                    ],
                },
                {
                    "server": "workflow-mcp",
                    "version": "1.0.0",
                    "definition_hash": (
                        "a0896543a821f9ee474e9ede7219cd689af09e141186908d0cf1ec5f4ea2f67c"
                    ),
                    "tools": [
                        "workflow.create_collaboration_draft",
                        "workflow.create_email_draft",
                        "workflow.create_internal_notification_draft",
                        "workflow.create_task_draft",
                        "workflow.read_document_metadata",
                    ],
                },
            ]
        }

    @app.post("/mcp/v1/invoke")
    async def invoke(
        payload: PrivateInvocationRequest,
        _principal: Principal = Depends(service_principal),
    ) -> dict:
        runtime_service = "pharma-agent-runtime"
        async with database.session_factory() as session:
            if payload.server == "regulatory-mcp":
                if payload.approval_request_id is None:
                    return {
                        "error": {
                            "code": "APPROVAL_REQUIRED",
                            "message": "The regulatory plan approval binding is required.",
                        }
                    }
                context = HostInvocationContext(
                    user_id=payload.user_id,
                    tenant_id=payload.tenant_id,
                    case_id=str(payload.case_id),
                    case_state_hash=payload.case_state_hash,
                    run_id=str(payload.run_id),
                    agent_name=payload.agent_name,
                    agent_version=payload.agent_version,
                    runtime_service=runtime_service,
                    idempotency_key=payload.idempotency_key,
                    approval_request_id=str(payload.approval_request_id),
                    scopes=frozenset(payload.scopes),
                    budget=ToolCallBudget(max_tool_calls=payload.maximum_tool_calls),
                    user_authenticated=True,
                    runtime_authenticated=True,
                )
                return await RegulatoryMcpGateway(session).invoke(
                    tool_name=payload.tool_name,
                    arguments=payload.arguments,
                    context=context,
                )
            context = KnowledgeInvocationContext(
                principal=Principal(payload.user_id, frozenset(payload.user_roles)),
                tenant_id=payload.tenant_id,
                case_id=str(payload.case_id),
                case_state_hash=payload.case_state_hash,
                run_id=str(payload.run_id),
                agent_name=payload.agent_name,
                agent_version=payload.agent_version,
                runtime_service=runtime_service,
                idempotency_key=payload.idempotency_key,
                scopes=frozenset(payload.scopes),
                user_authenticated=True,
                runtime_authenticated=True,
            )
            if payload.server == "knowledge-mcp":
                return await KnowledgeMcpGateway(
                    session, application_version=resolved.app_version
                ).invoke(
                    tool_name=payload.tool_name,
                    arguments=payload.arguments,
                    context=context,
                )
            return await WorkflowMcpGateway(
                session, application_version=resolved.app_version
            ).invoke(
                tool_name=payload.tool_name,
                arguments=payload.arguments,
                context=context,
            )

    return app


private_mcp_app = create_private_mcp_app()
