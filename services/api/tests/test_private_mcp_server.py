from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.agent_platform.mcp.server import PrivateInvocationRequest, create_private_mcp_app
from app.config import Settings


def test_private_mcp_inventory_requires_service_identity_and_lists_three_servers(
    settings: Settings,
) -> None:
    app = create_private_mcp_app(settings)
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/mcp/v1/tools").status_code == 401
        response = client.get(
            "/mcp/v1/tools",
            headers={"X-Dev-User": "svc:orchestrator", "X-Dev-Roles": "service"},
        )
    assert response.status_code == 200
    servers = {item["server"]: item for item in response.json()["servers"]}
    assert set(servers) == {"regulatory-mcp", "knowledge-mcp", "workflow-mcp"}
    assert sum(len(item["tools"]) for item in servers.values()) == 16
    assert "knowledge.get_revision_history" in servers["knowledge-mcp"]["tools"]
    assert "workflow.create_email_draft" in servers["workflow-mcp"]["tools"]


def test_private_mcp_contract_accepts_only_named_workflow_tools() -> None:
    payload = {
        "server": "workflow-mcp",
        "tool_name": "workflow.create_email_draft",
        "arguments": {},
        "user_id": "analyst.user",
        "user_roles": ["analyst"],
        "tenant_id": "default",
        "case_id": str(uuid4()),
        "case_state_hash": "a" * 64,
        "run_id": str(uuid4()),
        "agent_name": "case-orchestrator",
        "agent_version": "1.0.0",
        "idempotency_key": f"private-mcp:{uuid4().hex}",
        "scopes": ["workflow:email-draft:create"],
    }
    assert PrivateInvocationRequest.model_validate(payload).tool_name.startswith("workflow.")
