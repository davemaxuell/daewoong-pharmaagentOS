from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cases.hashing import canonical_sha256
from app.models import RegistryReleaseStatus, WorkflowTemplateVersion

_BUNDLED_WORKFLOW = "regulatory-impact-review.v1.0.0.yaml"


def bundled_workflow_path() -> Path:
    return (
        Path(__file__).resolve().parents[5]
        / "contracts"
        / "workflows"
        / _BUNDLED_WORKFLOW
    )


def load_bundled_workflow() -> dict[str, Any]:
    value = yaml.safe_load(bundled_workflow_path().read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("Bundled workflow contract is not an object")
    metadata = value.get("metadata")
    spec = value.get("spec")
    if not isinstance(metadata, dict) or not isinstance(spec, dict):
        raise RuntimeError("Bundled workflow contract is missing metadata or spec")
    canonical = deepcopy(value)
    expected = str(canonical["metadata"].pop("definitionHash", ""))
    actual = canonical_sha256(canonical)
    if expected != actual:
        raise RuntimeError("Bundled workflow definition hash does not match its content")
    return value


async def ensure_bundled_workflow_template(
    session: AsyncSession,
) -> WorkflowTemplateVersion:
    manifest = load_bundled_workflow()
    metadata = manifest["metadata"]
    workflow_key = str(metadata["name"])
    version = str(metadata["version"])
    existing = await session.scalar(
        select(WorkflowTemplateVersion).where(
            WorkflowTemplateVersion.workflow_key == workflow_key,
            WorkflowTemplateVersion.version == version,
        )
    )
    if existing:
        if existing.manifest_sha256 != metadata["definitionHash"]:
            raise RuntimeError("Persisted workflow version conflicts with bundled content")
        return existing
    template = WorkflowTemplateVersion(
        workflow_key=workflow_key,
        version=version,
        display_name="Regulatory impact review",
        manifest=manifest,
        manifest_sha256=str(metadata["definitionHash"]),
        release_status=str(metadata["releaseState"]),
        created_by="bundled-contract",
    )
    session.add(template)
    await session.flush()
    return template


async def approved_workflow_template(
    session: AsyncSession,
    workflow_key: str,
) -> WorkflowTemplateVersion | None:
    candidates = list(
        (
            await session.scalars(
                select(WorkflowTemplateVersion).where(
                    WorkflowTemplateVersion.workflow_key == workflow_key,
                    WorkflowTemplateVersion.release_status.in_(
                        [
                            RegistryReleaseStatus.APPROVED.value,
                            RegistryReleaseStatus.PRODUCTION.value,
                        ]
                    ),
                )
            )
        ).all()
    )
    executable = [
        item
        for item in candidates
        if bool(((item.manifest or {}).get("spec") or {}).get("executionEnabled"))
    ]

    def version_key(item: WorkflowTemplateVersion) -> tuple[int, int, int, str]:
        try:
            major, minor, patch = item.version.split(".", 2)
            return int(major), int(minor), int(patch.split("-", 1)[0]), item.version
        except ValueError:
            return 0, 0, 0, item.version

    return max(executable, key=version_key) if executable else None

