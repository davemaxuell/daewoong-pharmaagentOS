from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

EXPECTED_BUNDLE_HASH = "478dbf57c2b85c75e77616ce723e2b5fd771250516c91e69d26aabcec19b4952"
EMBEDDED_TOOL_POLICY = {
    "regulatory.get_version": (
        "regulatory:version:read",
        20,
        40000,
        4000,
        10,
        2,
        "TRANSIENT_ONLY",
    ),
    "regulatory.get_section": (
        "regulatory:section:read",
        20,
        40000,
        4000,
        10,
        2,
        "TRANSIENT_ONLY",
    ),
    "regulatory.get_anchor": (
        "regulatory:anchor:read",
        20,
        40000,
        4000,
        10,
        2,
        "TRANSIENT_ONLY",
    ),
    "regulatory.compare_versions": (
        "regulatory:version:compare",
        20,
        40000,
        4000,
        10,
        2,
        "TRANSIENT_ONLY",
    ),
    "regulatory.search_regulatory_references": (
        "regulatory:reference:search",
        20,
        40000,
        4000,
        10,
        2,
        "TRANSIENT_ONLY",
    ),
}


@dataclass(frozen=True)
class ToolManifest:
    name: str
    version: str
    required_scope: str
    maximum_result_characters: int
    maximum_excerpt_characters: int
    maximum_items: int
    timeout_seconds: int
    maximum_attempts: int
    retry_policy: str


@dataclass(frozen=True)
class RegulatoryToolBundle:
    name: str
    version: str
    definition_hash: str
    tools: dict[str, ToolManifest]


def _definition_hash(document: dict[str, Any]) -> str:
    canonical = deepcopy(document)
    canonical["metadata"].pop("definitionHash", None)
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _embedded_bundle() -> RegulatoryToolBundle:
    return RegulatoryToolBundle(
        name="regulatory-mcp",
        version="1.0.0",
        definition_hash=EXPECTED_BUNDLE_HASH,
        tools={
            name: ToolManifest(
                name=name,
                version="1.0.0",
                required_scope=values[0],
                maximum_items=values[1],
                maximum_result_characters=values[2],
                maximum_excerpt_characters=values[3],
                timeout_seconds=values[4],
                maximum_attempts=values[5],
                retry_policy=values[6],
            )
            for name, values in EMBEDDED_TOOL_POLICY.items()
        },
    )


@lru_cache(maxsize=1)
def load_regulatory_tool_bundle() -> RegulatoryToolBundle:
    relative_contract = Path("contracts/tools/regulatory-mcp.v1.0.0.yaml")
    path = next(
        (
            parent / relative_contract
            for parent in Path(__file__).resolve().parents
            if (parent / relative_contract).is_file()
        ),
        None,
    )
    if path is None:
        # Wheels and the API container intentionally package only ``app/``. This pinned
        # snapshot is the runtime policy; repository executions additionally prove that
        # it still matches the reviewed source contract below.
        return _embedded_bundle()
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    expected_hash = str(document["metadata"]["definitionHash"])
    if expected_hash != EXPECTED_BUNDLE_HASH or _definition_hash(document) != expected_hash:
        raise RuntimeError("regulatory-mcp contract definition hash does not match its content")
    if document.get("kind") != "ToolBundle" or document["metadata"].get("name") != "regulatory-mcp":
        raise RuntimeError("unexpected regulatory tool bundle identity")

    tools: dict[str, ToolManifest] = {}
    for raw in document["spec"]["tools"]:
        scopes = raw["permission"]["requiredScopes"]
        if len(scopes) != 1:
            raise RuntimeError(f"{raw['name']} must declare exactly one required scope")
        if raw["sideEffect"] != "NONE" or raw["riskClass"] != "R0":
            raise RuntimeError(f"{raw['name']} is not an R0 read-only tool")
        if raw["permission"]["modelMaySupplyRuntimeContext"] is not False:
            raise RuntimeError(f"{raw['name']} exposes protected runtime context")
        limits = raw["outputLimits"]
        execution = raw["execution"]
        timeout_seconds = int(execution["timeoutSeconds"])
        maximum_attempts = int(execution["maximumAttempts"])
        retry_policy = str(execution["retryPolicy"])
        if timeout_seconds < 1 or maximum_attempts < 1 or retry_policy != "TRANSIENT_ONLY":
            raise RuntimeError(f"{raw['name']} has an unsupported execution policy")
        manifest = ToolManifest(
            name=str(raw["name"]),
            version=str(raw["version"]),
            required_scope=str(scopes[0]),
            maximum_result_characters=int(limits["maximumResultCharacters"]),
            maximum_excerpt_characters=int(limits["maximumExcerptCharacters"]),
            maximum_items=int(limits["maximumItems"]),
            timeout_seconds=timeout_seconds,
            maximum_attempts=maximum_attempts,
            retry_policy=retry_policy,
        )
        if manifest.name in tools:
            raise RuntimeError(f"duplicate tool in regulatory bundle: {manifest.name}")
        tools[manifest.name] = manifest
    bundle = RegulatoryToolBundle(
        name="regulatory-mcp",
        version=str(document["metadata"]["version"]),
        definition_hash=expected_hash,
        tools=tools,
    )
    if bundle != _embedded_bundle():
        raise RuntimeError("embedded regulatory tool policy has drifted from its contract")
    return bundle
