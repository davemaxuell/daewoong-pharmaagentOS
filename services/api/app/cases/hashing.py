from __future__ import annotations

import hashlib
import json
from typing import Any

_ARTIFACT_EVIDENCE_MANIFEST_FIELDS = (
    "case_source_id",
    "document_version_id",
    "source_sha256",
    "anchor",
    "excerpt_sha256",
    "evidence_role",
)


def canonical_json(value: object) -> bytes:
    """Return the single JSON representation used for control-plane hashes.

    Control-plane inputs are validated JSON values before reaching this function.  Sorting
    object keys, removing insignificant whitespace, preserving Unicode, and rejecting NaN
    keep hashes stable across requests and processes.
    """

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def case_state_sha256(
    *,
    objective: str,
    workflow_key: str,
    source_pins: list[dict[str, str]],
) -> str:
    """Hash only controlled planning inputs; lifecycle status is deliberately excluded."""

    ordered_pins = sorted(
        source_pins,
        key=lambda item: (
            item["source_role"],
            item["document_version_id"],
            item["source_sha256"],
        ),
    )
    return canonical_sha256(
        {
            "schema_version": "case-state-v1",
            "objective": objective,
            "workflow_key": workflow_key,
            "source_pins": ordered_pins,
        }
    )


def artifact_evidence_manifest_sha256(
    evidence_members: list[dict[str, str]],
) -> str:
    """Hash an exact, order-independent artifact evidence membership list.

    Every UTF-8 field is length framed, so delimiters or Unicode inside an
    anchor cannot create an ambiguous serialization. PostgreSQL implements the
    same framing in ``pharma_agent_artifact_evidence_manifest_sha256`` and
    verifies it before an artifact review can be bound.
    """

    rows = sorted(
        tuple(member[field] for field in _ARTIFACT_EVIDENCE_MANIFEST_FIELDS)
        for member in evidence_members
    )
    framed = bytearray()
    for row in rows:
        for value in row:
            encoded = value.encode("utf-8")
            framed.extend(str(len(encoded)).encode("ascii"))
            framed.extend(b":")
            framed.extend(encoded)
    return hashlib.sha256(framed).hexdigest()


def event_sha256(
    *,
    case_id: str,
    sequence: int,
    event_type: str,
    actor_type: str,
    actor_id: str,
    request_id: str,
    idempotency_key: str,
    payload: dict[str, Any],
    previous_event_hash: str | None,
    state_hash: str,
) -> str:
    return canonical_sha256(
        {
            "schema_version": "case-event-v1",
            "case_id": case_id,
            "sequence": sequence,
            "event_type": event_type,
            "actor": {"type": actor_type, "id": actor_id},
            "request_id": request_id,
            "idempotency_key": idempotency_key,
            "payload": payload,
            "previous_event_hash": previous_event_hash,
            "state_hash": state_hash,
        }
    )
