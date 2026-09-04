"""Deny-by-default internal knowledge MCP boundary."""

from app.agent_platform.mcp.knowledge.context import KnowledgeInvocationContext
from app.agent_platform.mcp.knowledge.gateway import KnowledgeMcpGateway

__all__ = ["KnowledgeInvocationContext", "KnowledgeMcpGateway"]
