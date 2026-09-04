from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

CONTENT_FIELDS = {
    "after_excerpt",
    "before_excerpt",
    "citation_text",
    "excerpt",
    "reference",
    "text",
}

INSTRUCTION_PATTERN = re.compile(
    r"(?:"
    r"ignore\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|system|developer)\s+instructions?"
    r"|reveal\s+(?:the\s+)?(?:system\s+prompt|secret|credentials?)"
    r"|(?:system|developer|assistant)\s*(?:message|prompt)\s*:"
    r"|(?:call|invoke|use)\s+(?:the\s+)?(?:internal\s+)?(?:tool|function)\b"
    r"|execute\s+(?:a\s+)?(?:shell|sql|command)\b"
    r"|jailbreak\b"
    r")",
    re.IGNORECASE,
)
ACTIVE_CONTENT_PATTERN = re.compile(
    r"(?:<\s*/?\s*(?:script|iframe|object|embed)\b|javascript\s*:|data\s*:\s*text/html|"
    r"\bon(?:error|load|click)\s*=)",
    re.IGNORECASE,
)
SECRET_PATTERN = re.compile(
    r"(?:-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}|\bsk-[A-Za-z0-9_-]{16,})",
    re.IGNORECASE,
)
CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _sanitize_text(value: str) -> tuple[str, set[str]]:
    warnings: set[str] = set()
    cleaned = CONTROL_PATTERN.sub("", value)
    if cleaned != value:
        warnings.add("CONTROL_CHARACTERS_REMOVED")

    segments = re.split(r"(?<=[.!?])\s+|\r?\n+", cleaned)
    retained: list[str] = []
    for segment in segments:
        if not segment:
            continue
        if ACTIVE_CONTENT_PATTERN.search(segment):
            retained.append("[active source content removed]")
            warnings.add("ACTIVE_CONTENT_SANITIZED")
            continue
        if SECRET_PATTERN.search(segment):
            retained.append("[sensitive source token redacted]")
            warnings.add("SENSITIVE_CONTENT_REDACTED")
            continue
        if INSTRUCTION_PATTERN.search(segment):
            retained.append("[instruction-like source content removed]")
            warnings.add("INSTRUCTION_LIKE_CONTENT_SANITIZED")
            continue
        retained.append(segment)
    result = "\n".join(retained).strip()
    if not result:
        result = "[source content removed]"
    return result, warnings


def sanitize_untrusted_content(value: Any) -> tuple[Any, list[str]]:
    """Sanitize content-bearing result fields without rewriting identifiers or metadata."""

    warnings: set[str] = set()

    def visit(node: Any, field_name: str | None = None) -> Any:
        if isinstance(node, Mapping):
            return {str(key): visit(item, str(key)) for key, item in node.items()}
        if isinstance(node, list):
            return [visit(item, field_name) for item in node]
        if isinstance(node, str) and field_name in CONTENT_FIELDS:
            sanitized, detected = _sanitize_text(node)
            warnings.update(detected)
            return sanitized
        return node

    return visit(value), sorted(warnings)
