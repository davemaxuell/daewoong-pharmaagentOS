"""Narrow adapter from the governed regulatory MCP gateway to anchor validation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Protocol
from uuid import UUID

from app.agent_platform.mcp.regulatory import HostInvocationContext
from app.agent_platform.mcp.regulatory.schemas import ErrorCode, ErrorResult, GetAnchorSuccess

from .interfaces import AnchorObservation, RegulatoryRuntimeIdentity


class _GatewayInvoker(Protocol):
    async def invoke(
        self,
        *,
        tool_name: str,
        arguments: Mapping[str, object] | object,
        context: HostInvocationContext,
    ) -> dict[str, object]: ...


class RegulatoryGatewayError(RuntimeError):
    """A safe structured MCP error; source content and provider internals are excluded."""

    def __init__(self, code: ErrorCode, *, retryable: bool) -> None:
        super().__init__(str(code))
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class RegulatoryMcpAnchorTools:
    """Expose only exact anchor reads from one host-authorized MCP invocation context."""

    gateway: _GatewayInvoker
    context: HostInvocationContext

    def _identity_matches(self, identity: RegulatoryRuntimeIdentity) -> bool:
        return (
            identity.user_id == self.context.user_id
            and identity.tenant_id == self.context.tenant_id
            and identity.case_id == self.context.case_id
            and identity.run_id == self.context.run_id
            and identity.agent_name == self.context.agent_name
            and identity.agent_version == self.context.agent_version
            and identity.runtime_service == self.context.runtime_service
            and identity.idempotency_key == self.context.idempotency_key
        )

    async def get_anchor(
        self,
        *,
        source_version_id: UUID,
        expected_source_hash: str,
        anchor_id: str,
        identity: RegulatoryRuntimeIdentity,
    ) -> AnchorObservation | None:
        if not self._identity_matches(identity):
            raise RegulatoryGatewayError(ErrorCode.PERMISSION_DENIED, retryable=False)
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "base_idempotency_key": self.context.idempotency_key,
                    "document_version_id": str(source_version_id),
                    "expected_source_hash": expected_source_hash,
                    "anchor_id": anchor_id,
                },
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        invocation_context = replace(
            self.context,
            idempotency_key=f"regulatory-anchor:{fingerprint}",
        )
        result = await self.gateway.invoke(
            tool_name="regulatory.get_anchor",
            arguments={
                "document_version_id": str(source_version_id),
                "expected_source_hash": expected_source_hash,
                "anchor_id": anchor_id,
            },
            context=invocation_context,
        )
        if result.get("status") == "error":
            error = ErrorResult.model_validate(result)
            if error.error.code == ErrorCode.NOT_FOUND:
                return None
            raise RegulatoryGatewayError(
                error.error.code,
                retryable=error.error.retryable,
            )
        success = GetAnchorSuccess.model_validate(result)
        return AnchorObservation(
            source_version_id=success.data.document_version_id,
            source_hash=success.data.source_hash,
            anchor_id=success.data.anchor_id,
            excerpt=success.data.excerpt,
            evidence_class="PRIMARY_AUTHORITATIVE",
            access_allowed=True,
        )
