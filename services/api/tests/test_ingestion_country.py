from __future__ import annotations

import pytest

from app.config import Settings
from app.database import Database
from app.ingestion import CandidateMetadata, ingest_html
from app.models import Case, CaseSource, DocumentVersion, ProcessingJob, WarningLetter
from app.parsing import parse_warning_letter_html
from app.worker import _reprocess

DETAIL_HTML = b"""
<html><body>
  <h1>Tianjin Kilo Pharmaceutical Sci-tech Co., Ltd. - 731761 - 08/06/2026</h1>
  <div class="field"><div class="field__label">Product</div>
    <div class="field__item">Drugs</div></div>
  <dl>
    <dt>Recipient:</dt>
    <dd>Wenjun Liao</dd><dd>General Manager</dd>
    <dd>Tianjin Kilo Pharmaceutical Sci-tech Co., Ltd.</dd>
    <dd><p class="address">Room 609, Building 6, no. 6 Ziyuan Road<br>
      Tianjin Shi, 300384<br><span class="country">China</span></p></dd>
  </dl>
  <dl>
    <dt>Issuing Office:</dt><dd>Center for Drug Evaluation and Research (CDER)</dd>
    <dd><span class="country">United States</span></dd>
  </dl>
  <div class="letter-body"><p><strong>FDA Review</strong></p>
    <p>The firm must address the documented deviations.</p></div>
</body></html>
"""


@pytest.mark.asyncio
async def test_ingestion_persists_recipient_country_and_extraction_metadata(
    settings: Settings,
) -> None:
    database = Database(settings.database_url)
    url = "https://www.fda.gov/warning-letters/tianjin-kilo-731761-08062026"
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            result = await ingest_html(
                session,
                settings,
                CandidateMetadata(canonical_url=url),
                DETAIL_HTML,
            )
            await session.commit()

            letter = await session.get(WarningLetter, result.warning_letter_id)
            version = await session.get(DocumentVersion, result.version_id)
            assert letter is not None and letter.country == "China"
            assert version is not None
            assert version.extraction_metadata["recipient_country"] == "China"

            # The parsed Recipient country also repairs an existing empty record even
            # when canonical source text has not changed and no new version is created.
            letter.country = None
            version.extraction_metadata = {"body_non_empty": True}
            await session.commit()
            repeated = await ingest_html(
                session,
                settings,
                CandidateMetadata(canonical_url=url),
                DETAIL_HTML,
            )
            await session.commit()
            assert repeated.version_created is False
            assert letter.country == "China"
            assert version.extraction_metadata["recipient_country"] == "China"
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_candidate_country_remains_authoritative_over_parsed_recipient_country(
    settings: Settings,
) -> None:
    database = Database(settings.database_url)
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            result = await ingest_html(
                session,
                settings,
                CandidateMetadata(
                    canonical_url="https://www.fda.gov/warning-letters/candidate-country-731762",
                    country="Republic of Korea",
                ),
                DETAIL_HTML,
            )
            await session.commit()
            letter = await session.get(WarningLetter, result.warning_letter_id)
            assert letter is not None and letter.country == "Republic of Korea"
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_parse_reprocess_repairs_current_country_and_heading_anchors(
    settings: Settings,
) -> None:
    database = Database(settings.database_url)
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            result = await ingest_html(
                session,
                settings,
                CandidateMetadata(
                    canonical_url="https://www.fda.gov/warning-letters/reprocess-country-731763"
                ),
                DETAIL_HTML,
            )
            await session.commit()
            letter = await session.get(WarningLetter, result.warning_letter_id)
            version = await session.get(DocumentVersion, result.version_id)
            assert letter is not None and version is not None

            letter.country = None
            version.source_anchors = [
                {
                    "anchor": "introduction",
                    "text": "FDA Review",
                    "kind": "paragraph",
                    "ordinal": 0,
                }
            ]
            version.extraction_metadata = {"body_non_empty": True}
            await session.flush()

            metrics = await _reprocess(
                session,
                settings,
                ProcessingJob(
                    warning_letter_id=letter.id,
                    document_version_id=version.id,
                    job_type="reprocess",
                    idempotency_key="reprocess-country-test",
                    payload={"stages": ["parse"]},
                ),
            )

            assert metrics["stages_completed"] == 1
            assert letter.country == "China"
            assert version.extraction_metadata["recipient_country"] == "China"
            assert any(
                anchor["text"] == "FDA Review" and anchor["kind"] == "heading"
                for anchor in version.source_anchors
            )
            assert "### FDA Review" in (version.normalized_markdown or "")
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_parse_reprocess_rejects_anchor_drift_for_case_pinned_source(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = Database(settings.database_url)
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            result = await ingest_html(
                session,
                settings,
                CandidateMetadata(
                    canonical_url=(
                        "https://www.fda.gov/warning-letters/"
                        "pinned-reprocess-country-731764"
                    )
                ),
                DETAIL_HTML,
            )
            version = await session.get(DocumentVersion, result.version_id)
            assert version is not None
            case = Case(
                title="Pinned evidence",
                objective="Preserve exact retained evidence anchors.",
                owner_subject="test.analyst",
                workflow_key="regulatory-impact-review",
                current_state_hash="a" * 64,
                idempotency_key="pinned-reprocess-case",
            )
            session.add(case)
            await session.flush()
            session.add(
                CaseSource(
                    case_id=case.id,
                    document_version_id=version.id,
                    source_role="PRIMARY_REGULATORY",
                    source_sha256=version.canonical_hash,
                    pinned_by="test.analyst",
                )
            )
            await session.commit()

            def parse_with_changed_anchor(raw: bytes | str):
                parsed = parse_warning_letter_html(raw)
                parsed.anchors = [
                    *parsed.anchors,
                    {
                        "anchor": "parser-drift",
                        "text": "Parser-only anchor drift",
                        "kind": "paragraph",
                        "ordinal": len(parsed.anchors),
                    },
                ]
                return parsed

            monkeypatch.setattr(
                "app.worker.parse_warning_letter_html", parse_with_changed_anchor
            )
            with pytest.raises(
                RuntimeError, match="change a case-pinned source version"
            ):
                await _reprocess(
                    session,
                    settings,
                    ProcessingJob(
                        warning_letter_id=result.warning_letter_id,
                        document_version_id=version.id,
                        job_type="reprocess",
                        idempotency_key="pinned-reprocess-job",
                        payload={"stages": ["parse"]},
                    ),
                )

            await session.refresh(version)
            assert all(
                anchor.get("anchor") != "parser-drift"
                for anchor in version.source_anchors
            )
    finally:
        await database.dispose()
