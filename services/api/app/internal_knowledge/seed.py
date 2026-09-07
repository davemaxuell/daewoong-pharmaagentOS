from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.internal_knowledge.embedding import deterministic_embedding
from app.models import (
    AssetRelation,
    AssetRelationStatus,
    InternalAsset,
    InternalAssetAcl,
    InternalAssetVersion,
    RelationEvidence,
)
from app.resource_paths import resource_root

CORPUS_PATH = (
    resource_root()
    / "fixtures"
    / "internal_quality"
    / "synthetic_quality_system.v1.yaml"
)
SEED_ACTOR = "synthetic-corpus-seeder"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_synthetic_corpus(path: Path = CORPUS_PATH) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != "1.0.0":
        raise ValueError("Synthetic internal corpus schema is unsupported")
    notice = str(value.get("notice", "")).casefold()
    if "demonstration data only" not in notice or "fictional" not in notice:
        raise ValueError("Synthetic internal corpus must carry its safety notice")
    return value


def _version_search_text(asset: dict[str, Any], version: dict[str, Any]) -> str:
    anchor_text = " ".join(str(item.get("excerpt", "")) for item in version["anchors"])
    return " ".join(
        (
            str(asset["asset_key"]),
            str(asset["asset_type"]),
            str(asset["title"]),
            str(asset["domain"]),
            str(version["content"]),
            anchor_text,
        )
    )


async def ensure_synthetic_internal_corpus(
    session: AsyncSession, path: Path = CORPUS_PATH
) -> dict[str, int]:
    """Idempotently materialize the checked-in fictional quality-system corpus."""

    corpus = load_synthetic_corpus(path)
    asset_rows: dict[str, InternalAsset] = {}
    version_rows: dict[tuple[str, int], InternalAssetVersion] = {}
    created = {"assets": 0, "versions": 0, "acl_grants": 0, "relations": 0}

    for definition in corpus["assets"]:
        key = str(definition["asset_key"])
        asset = await session.scalar(select(InternalAsset).where(InternalAsset.asset_key == key))
        if asset is None:
            asset = InternalAsset(
                asset_key=key,
                asset_type=str(definition["asset_type"]),
                title=str(definition["title"]),
                domain=str(definition["domain"]),
                classification=str(definition["classification"]),
                synthetic=True,
                lifecycle_status="ACTIVE",
                created_by=SEED_ACTOR,
            )
            session.add(asset)
            await session.flush()
            created["assets"] += 1
        elif not asset.synthetic:
            raise ValueError(f"Seed key conflicts with non-synthetic asset: {key}")
        asset_rows[key] = asset

        effective: InternalAssetVersion | None = None
        for version_definition in definition["versions"]:
            revision = int(version_definition["revision"])
            content = str(version_definition["content"])
            content_sha256 = sha256_text(content)
            version = await session.scalar(
                select(InternalAssetVersion).where(
                    InternalAssetVersion.asset_id == asset.id,
                    InternalAssetVersion.revision == revision,
                )
            )
            if version is None:
                search_text = _version_search_text(definition, version_definition)
                version = InternalAssetVersion(
                    asset_id=asset.id,
                    revision=revision,
                    status=str(version_definition["status"]),
                    effective_from=(
                        date.fromisoformat(str(version_definition["effective_from"]))
                        if version_definition.get("effective_from")
                        else None
                    ),
                    effective_to=(
                        date.fromisoformat(str(version_definition["effective_to"]))
                        if version_definition.get("effective_to")
                        else None
                    ),
                    content=content,
                    content_sha256=content_sha256,
                    anchors=list(version_definition["anchors"]),
                    asset_metadata={
                        "corpus_key": corpus["corpus_key"],
                        "notice": corpus["notice"],
                    },
                    search_text=search_text,
                    embedding=deterministic_embedding(search_text),
                    created_by=SEED_ACTOR,
                )
                session.add(version)
                await session.flush()
                created["versions"] += 1
            elif version.content_sha256 != content_sha256:
                raise ValueError(f"Immutable synthetic revision drift: {key} rev {revision}")
            version_rows[(key, revision)] = version
            if version.status == "EFFECTIVE" and (
                effective is None or version.revision > effective.revision
            ):
                effective = version
        if effective is None:
            raise ValueError(f"Synthetic asset has no effective revision: {key}")
        asset.current_version_id = effective.id

        existing_grants = set(
            (
                await session.scalars(
                    select(InternalAssetAcl.principal_value).where(
                        InternalAssetAcl.asset_id == asset.id,
                        InternalAssetAcl.principal_kind == "ROLE",
                        InternalAssetAcl.permission == "READ",
                    )
                )
            ).all()
        )
        for role in definition["acl_roles"]:
            if role not in existing_grants:
                session.add(
                    InternalAssetAcl(
                        asset_id=asset.id,
                        principal_kind="ROLE",
                        principal_value=str(role),
                        permission="READ",
                        created_by=SEED_ACTOR,
                    )
                )
                created["acl_grants"] += 1

    await session.flush()
    for definition in corpus["relations"]:
        source = asset_rows[str(definition["source"])]
        target = asset_rows[str(definition["target"])]
        relation_type = str(definition["relation_type"])
        relation = await session.scalar(
            select(AssetRelation).where(
                AssetRelation.source_asset_id == source.id,
                AssetRelation.target_asset_id == target.id,
                AssetRelation.relation_type == relation_type,
            )
        )
        if relation is None:
            relation = AssetRelation(
                source_asset_id=source.id,
                target_asset_id=target.id,
                relation_type=relation_type,
                status=AssetRelationStatus.APPROVED.value,
                confidence=float(definition["confidence"]),
                rationale=str(definition["rationale"]),
                proposed_by=SEED_ACTOR,
                reviewed_by=SEED_ACTOR,
                review_reason="Approved fictional corpus relationship",
            )
            session.add(relation)
            await session.flush()
            created["relations"] += 1
        for item in definition["evidence"]:
            version = version_rows[(str(item["asset"]), int(item["revision"]))]
            anchor_id = str(item["anchor"])
            anchor = next(
                (entry for entry in version.anchors if entry.get("id") == anchor_id), None
            )
            if anchor is None:
                raise ValueError(f"Relation evidence anchor is missing: {anchor_id}")
            exists = await session.scalar(
                select(RelationEvidence.id).where(
                    RelationEvidence.relation_id == relation.id,
                    RelationEvidence.asset_version_id == version.id,
                    RelationEvidence.anchor == anchor_id,
                )
            )
            if exists is None:
                session.add(
                    RelationEvidence(
                        relation_id=relation.id,
                        asset_version_id=version.id,
                        content_sha256=version.content_sha256,
                        anchor=anchor_id,
                        excerpt_sha256=sha256_text(str(anchor["excerpt"])),
                        evidence_role=(
                            "SOURCE" if version.asset_id == source.id else "TARGET"
                        ),
                    )
                )
    await session.flush()
    return created
