from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cases.hashing import canonical_sha256
from app.models import AgentVersion, SkillVersion, ToolVersion

ROOT = Path(__file__).resolve().parents[5]
AGENT_FILES = (
    "regulatory-evidence-agent.v1.3.0.yaml",
    "case-orchestrator.v1.0.0.yaml",
    "internal-knowledge-agent.v1.1.0.yaml",
    "impact-analysis-agent.v1.0.2.yaml",
    "verification-agent.v1.2.1.yaml",
)
TOOL_BUNDLE_FILES = (
    "regulatory-mcp.v1.0.0.yaml",
    "knowledge-mcp.v1.0.0.yaml",
    "workflow-mcp.v1.0.0.yaml",
)
SKILL_LIBRARY_FILE = "initial-skills.v1.0.0.yaml"


def _load_versioned_contract(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("metadata"), dict):
        raise RuntimeError(f"Bundled registry contract is invalid: {path.name}")
    canonical = deepcopy(value)
    expected = str(canonical["metadata"].pop("definitionHash", ""))
    if canonical_sha256(canonical) != expected:
        raise RuntimeError(f"Bundled registry contract hash mismatch: {path.name}")
    return value


async def ensure_internal_agent_registry(session: AsyncSession) -> dict[str, int]:
    created = {"agents": 0, "skills": 0, "tools": 0}
    for filename in AGENT_FILES:
        manifest = _load_versioned_contract(ROOT / "contracts" / "agents" / filename)
        metadata = manifest["metadata"]
        existing = await session.scalar(
            select(AgentVersion).where(
                AgentVersion.agent_key == metadata["name"],
                AgentVersion.version == metadata["version"],
            )
        )
        if existing is None:
            session.add(
                AgentVersion(
                    agent_key=metadata["name"],
                    version=metadata["version"],
                    display_name=str(metadata["name"]).replace("-", " ").title(),
                    manifest=manifest,
                    manifest_sha256=metadata["definitionHash"],
                    release_status=metadata["releaseState"],
                    created_by="bundled-contract",
                )
            )
            created["agents"] += 1
        elif existing.manifest_sha256 != metadata["definitionHash"]:
            raise RuntimeError(f"Persisted agent version conflicts with {filename}")

    library = yaml.safe_load(
        (ROOT / "contracts" / "skills" / SKILL_LIBRARY_FILE).read_text(encoding="utf-8")
    )
    if library.get("apiVersion") != "pharmaagent.io/v1" or library.get("kind") != "SkillLibrary":
        raise RuntimeError("Bundled skill library contract is invalid")
    library_metadata = library["metadata"]
    for definition in library["skills"]:
        manifest = {
            "apiVersion": library["apiVersion"],
            "kind": "Skill",
            "metadata": {
                "name": definition["name"],
                "version": definition["version"],
                "owner": library_metadata["owner"],
                "releaseState": library_metadata["releaseState"],
            },
            "spec": {
                "intendedUse": definition["intendedUse"],
                "requiredOutput": definition["requiredOutput"],
                "prohibitedBehavior": definition["prohibitedBehavior"],
                "instructions": definition["instructions"],
            },
        }
        digest = canonical_sha256(manifest)
        existing = await session.scalar(
            select(SkillVersion).where(
                SkillVersion.skill_key == definition["name"],
                SkillVersion.version == definition["version"],
            )
        )
        if existing is None:
            session.add(
                SkillVersion(
                    skill_key=definition["name"],
                    version=definition["version"],
                    display_name=definition["displayName"],
                    manifest=manifest,
                    manifest_sha256=digest,
                    release_status=library_metadata["releaseState"],
                    created_by="bundled-contract",
                )
            )
            created["skills"] += 1
        elif existing.manifest_sha256 != digest:
            raise RuntimeError(
                f"Persisted skill version conflicts with {definition['name']}"
            )

    for filename in TOOL_BUNDLE_FILES:
        bundle = _load_versioned_contract(ROOT / "contracts" / "tools" / filename)
        metadata = bundle["metadata"]
        for tool in bundle["spec"]["tools"]:
            existing = await session.scalar(
                select(ToolVersion).where(
                    ToolVersion.tool_key == tool["name"],
                    ToolVersion.version == tool["version"],
                )
            )
            if existing is None:
                session.add(
                    ToolVersion(
                        tool_key=tool["name"],
                        server_key=bundle["spec"]["server"],
                        version=tool["version"],
                        display_name=tool["name"],
                        manifest=bundle,
                        manifest_sha256=metadata["definitionHash"],
                        risk_class=tool["riskClass"],
                        side_effecting=tool["sideEffect"] != "NONE",
                        release_status=metadata["releaseState"],
                        created_by="bundled-contract",
                    )
                )
                created["tools"] += 1
            elif existing.manifest_sha256 != metadata["definitionHash"]:
                raise RuntimeError(f"Persisted tool version conflicts with {tool['name']}")
    await session.flush()
    return created
