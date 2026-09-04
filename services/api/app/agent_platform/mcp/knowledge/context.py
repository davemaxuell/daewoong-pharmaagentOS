from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.security.auth import Principal


@dataclass(frozen=True)
class KnowledgeInvocationContext:
    """Trusted host fields; none are accepted from model-facing tool arguments."""

    principal: Principal
    tenant_id: str
    case_id: str
    case_state_hash: str
    run_id: str
    agent_name: str
    agent_version: str
    runtime_service: str
    idempotency_key: str
    scopes: frozenset[str]
    user_authenticated: bool
    runtime_authenticated: bool

    def __post_init__(self) -> None:
        for field_name in ("case_id", "run_id"):
            try:
                UUID(getattr(self, field_name))
            except (TypeError, ValueError, AttributeError) as exc:
                raise ValueError(f"{field_name} must be a UUID") from exc
        if len(self.case_state_hash) != 64:
            raise ValueError("case_state_hash must be a SHA-256 digest")
        if not self.idempotency_key.strip() or len(self.idempotency_key) > 200:
            raise ValueError("idempotency_key is required and bounded")
        if self.principal.subject != self.principal.subject.strip():
            raise ValueError("principal subject must be normalized")
