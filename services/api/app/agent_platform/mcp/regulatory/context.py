from __future__ import annotations

import re
from dataclasses import dataclass, field
from threading import Lock
from uuid import UUID

SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


@dataclass
class ToolCallBudget:
    """Host-owned view of the durable per-run tool-call budget.

    The gateway persists the authoritative limit and usage in ``CaseRun.checkpoint``
    while holding a row lock.  This object only lets the host request a tighter cap
    and observe the persisted usage; it is not an authorization boundary by itself.
    """

    max_tool_calls: int = 15
    used_tool_calls: int = 0
    _lock: Lock = field(default_factory=Lock, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.max_tool_calls < 1:
            raise ValueError("max_tool_calls must be positive")
        if self.used_tool_calls < 0:
            raise ValueError("used_tool_calls cannot be negative")

    def try_consume(self, *, policy_limit: int) -> bool:
        """Retained for non-persistent callers; the regulatory gateway does not use it."""

        effective_limit = min(self.max_tool_calls, policy_limit)
        with self._lock:
            if self.used_tool_calls >= effective_limit:
                return False
            self.used_tool_calls += 1
            return True

    def synchronize_used(self, used_tool_calls: int) -> None:
        """Reflect an authoritative persisted count without allowing it to decrease."""

        if used_tool_calls < 0:
            raise ValueError("used_tool_calls cannot be negative")
        with self._lock:
            self.used_tool_calls = max(self.used_tool_calls, used_tool_calls)


@dataclass(frozen=True)
class HostInvocationContext:
    """Trusted runtime fields that are never part of model-facing tool arguments."""

    user_id: str
    tenant_id: str
    case_id: str
    case_state_hash: str
    run_id: str
    agent_name: str
    agent_version: str
    runtime_service: str
    idempotency_key: str
    approval_request_id: str
    scopes: frozenset[str]
    budget: ToolCallBudget
    user_authenticated: bool
    runtime_authenticated: bool

    def __post_init__(self) -> None:
        for name in (
            "user_id",
            "tenant_id",
            "agent_name",
            "agent_version",
            "runtime_service",
            "idempotency_key",
        ):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        for name in ("case_id", "run_id", "approval_request_id"):
            try:
                UUID(getattr(self, name))
            except (TypeError, ValueError, AttributeError) as exc:
                raise ValueError(f"{name} must be a UUID") from exc
        if not SHA256_PATTERN.fullmatch(self.case_state_hash):
            raise ValueError("case_state_hash must be a lowercase SHA-256 value")
