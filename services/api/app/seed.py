from __future__ import annotations

import re
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.enums import ReviewState, RunStatus, ScopeStatus
from app.ingestion import IngestionResult, ingest_fixture
from app.models import (
    AiSummary,
    DocumentChunk,
    Finding,
    IngestionRun,
    Subscription,
    WarningLetter,
    utcnow,
)
from app.parsing import extract_regulatory_references


def _fixture_manifest(fixture_dir: Path) -> dict[str, str]:
    manifest: dict[str, str] = {}
    for name in ("fixture_manifest.yaml", "fixture_manifest.yml", "manifest.yaml"):
        path = fixture_dir / name
        if not path.exists():
            continue
        value = yaml.safe_load(path.read_text(encoding="utf-8"))

        def visit(node: object) -> None:
            if isinstance(node, dict):
                file_value = node.get("file") or node.get("path") or node.get("fixture")
                url_value = node.get("canonical_url") or node.get("url")
                if file_value and url_value:
                    manifest[str(file_value).replace("\\", "/")] = str(url_value)
                for child in node.values():
                    visit(child)
            elif isinstance(node, list):
                for child in node:
                    visit(child)

        visit(value)
    return manifest


def _fixture_url(path: Path, fixture_dir: Path, manifest: dict[str, str]) -> str:
    relative = path.relative_to(fixture_dir).as_posix()
    if relative in manifest:
        return manifest[relative]
    if path.name in manifest:
        return manifest[path.name]
    slug = re.sub(r"[^a-z0-9]+", "-", path.stem.casefold()).strip("-")
    digest = abs(hash(relative)) % 1_000_000
    return (
        "https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/"
        f"warning-letters/{slug}-{digest:06d}"
    )


def _classify(text: str) -> tuple[list[str], list[str]]:
    folded = text.casefold()
    subtypes: list[str] = []
    categories: list[str] = []
    if "active pharmaceutical ingredient" in folded or "api" in folded:
        subtypes.append("API")
        categories.append("API Manufacturing / ICH Q7-related CGMP")
    if "over-the-counter" in folded or "otc" in folded:
        subtypes.append("OTC drug")
    if "steril" in folded or "aseptic" in folded:
        subtypes.append("Sterile drug")
        categories.append("Aseptic Processing / Sterility Assurance / Media Fill")
    if "quality unit" in folded:
        categories.append("Quality Unit / QA Oversight")
    if "data integrity" in folded or "audit trail" in folded:
        categories.append("Data Integrity / Computerized Systems / Audit Trail")
    if "validation" in folded:
        categories.append("Process Validation / PPQ / Continued Process Verification")
    if not subtypes:
        subtypes.append("Finished pharmaceutical")
    if not categories:
        categories.append("Other Drug Regulatory / CGMP")
    return list(dict.fromkeys(subtypes)), list(dict.fromkeys(categories))


async def ensure_derived_content(
    session: AsyncSession,
    settings: Settings,
    letter: WarningLetter,
    *,
    review_state: ReviewState = ReviewState.APPROVED,
) -> AiSummary | None:
    if not letter.current_version_id or letter.scope_status != ScopeStatus.IN_SCOPE_DRUGS.value:
        return None
    chunks = list(
        (
            await session.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_version_id == letter.current_version_id)
                .order_by(DocumentChunk.ordinal)
            )
        ).all()
    )
    if not chunks:
        return None
    combined = "\n".join(chunk.content for chunk in chunks)
    subtypes, categories = _classify(combined)
    letter.drug_subtypes = subtypes
    for chunk in chunks:
        chunk.drug_subtypes = subtypes
        chunk.categories = categories
    summary = await session.scalar(
        select(AiSummary)
        .where(
            AiSummary.document_version_id == letter.current_version_id,
            AiSummary.language == "en",
        )
        .order_by(AiSummary.revision.desc())
    )
    if summary:
        return summary
    first = chunks[0]
    excerpt = first.content[:600]
    summary = AiSummary(
        document_version_id=letter.current_version_id,
        executive_summary=(
            f"FDA issued a Drug warning letter to {letter.company_name}. "
            f"The retained source begins: {excerpt[:350]}"
        ),
        structured_output={
            "product_types": ["Drugs"],
            "drug_subtypes": subtypes,
            "categories": categories,
            "source_version_id": letter.current_version_id,
        },
        validation_report={"passed": True, "failed_checks": []},
        taxonomy_version=settings.taxonomy_version,
        review_state=review_state.value,
    )
    session.add(summary)
    await session.flush()
    session.add(
        Finding(
            document_version_id=letter.current_version_id,
            summary_id=summary.id,
            label="01",
            categories=categories,
            process_lenses=["retrospective"],
            finding_text=excerpt,
            regulatory_references=extract_regulatory_references(excerpt),
            evidence=[
                {
                    "source_anchor": first.source_anchor,
                    "excerpt": excerpt,
                    "official_url": letter.canonical_url,
                }
            ],
            fda_requested_actions=[],
            comparison_points=[
                "Compare the source-backed observation with the applicable internal control."
            ],
            attention_level="unknown",
            confidence=1.0,
            review_state=review_state.value,
        )
    )
    return summary


async def seed_demo(
    session: AsyncSession,
    settings: Settings,
    fixture_dir: Path,
) -> list[IngestionResult]:
    from app.agent_platform.registry.bundled import ensure_internal_agent_registry
    from app.agent_platform.registry.workflows import ensure_bundled_workflow_template
    from app.internal_knowledge.seed import ensure_synthetic_internal_corpus

    fixture_dir = fixture_dir.resolve()
    if not fixture_dir.is_dir():
        raise FileNotFoundError(fixture_dir)
    manifest = _fixture_manifest(fixture_dir)
    paths = sorted(
        path for path in fixture_dir.rglob("*.html") if "listing" not in path.stem.casefold()
    )
    if not paths:
        raise FileNotFoundError(f"No detail HTML fixtures under {fixture_dir}")
    results: list[IngestionResult] = []
    for path in paths:
        result = await ingest_fixture(
            session,
            settings,
            path,
            canonical_url=_fixture_url(path, fixture_dir, manifest),
        )
        results.append(result)
    await session.flush()
    in_scope = list(
        (
            await session.scalars(
                select(WarningLetter)
                .where(WarningLetter.current_in_scope.is_(True))
                .order_by(WarningLetter.created_at, WarningLetter.id)
            )
        ).all()
    )
    for index, letter in enumerate(in_scope):
        state = ReviewState.PENDING if index == len(in_scope) - 1 else ReviewState.APPROVED
        await ensure_derived_content(session, settings, letter, review_state=state)
    await ensure_bundled_workflow_template(session)
    await ensure_internal_agent_registry(session)
    await ensure_synthetic_internal_corpus(session)
    existing_view = await session.scalar(
        select(Subscription).where(
            Subscription.owner_id == "local.user",
            Subscription.name == "New FDA Drug warning letters",
        )
    )
    if not existing_view:
        session.add(
            Subscription(
                owner_id="local.user",
                name="New FDA Drug warning letters",
                description="Example saved view; alerts remain off until explicitly enabled.",
                criteria={},
                frequency="immediate",
                channel="email",
                destination_id=settings.notification_default_recipient,
                active=False,
            )
        )
    elif set((existing_view.criteria or {}).keys()).intersection({"scope", "event_type"}):
        # Earlier demo databases represented this example as an active subscription even
        # though the saved-view UI could not persist edits. Convert only that legacy shape;
        # never disable a real user-authored controlled view.
        existing_view.description = (
            "Example saved view; alerts remain off until explicitly enabled."
        )
        existing_view.criteria = {}
        existing_view.active = False
    demo_run = await session.scalar(
        select(IngestionRun).where(IngestionRun.idempotency_key == "seed-demo-v1")
    )
    if not demo_run:
        now = utcnow()
        session.add(
            IngestionRun(
                run_type="discovery",
                source="Synthetic FDA-compatible fixture corpus",
                status=RunStatus.SUCCEEDED.value,
                requested_by="seed-demo",
                idempotency_key="seed-demo-v1",
                parser_version=settings.parser_version,
                scope_rule_version=settings.drug_scope_rule_version,
                started_at=now,
                completed_at=now,
                metrics={
                    "fixtures": len(results),
                    "in_scope": sum(
                        result.scope_status == ScopeStatus.IN_SCOPE_DRUGS for result in results
                    ),
                },
            )
        )
    await session.commit()
    return results
