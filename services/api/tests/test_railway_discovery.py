from __future__ import annotations

import json
from collections import Counter
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import func, select

from app.background_worker import schedule_ingestion
from app.database import Database
from app.discovery import ListingDiscoveryError, parse_datatables_page
from app.enums import JobStatus
from app.fda_client import FetchedSource
from app.models import DocumentVersion, WarningLetter, utcnow
from app.worker import process_next_job

COLUMNS = ["Posted Date", "Company Name"]


def row(index):
    return [
        utcnow().strftime("%m/%d/%Y"),
        f'<a href="/warning-letters/railway-{index}">Company {index}</a>',
    ]


@pytest.mark.parametrize(
    "data,total",
    [
        ([row(0), ["unlinked", "Missing URL"]], 2),
        ([row(0), row(0)], 2),
        ([row(0), {}], 2),
        ([row(0)], -1),
        ([row(0)], True),
    ],
)
def test_partial_or_malformed_datatables_page_is_not_silently_accepted(data, total):
    with pytest.raises(ListingDiscoveryError):
        parse_datatables_page(
            json.dumps({"data": data, "recordsFiltered": total}).encode(),
            source_url="https://www.fda.gov/datatables/views/ajax",
            columns=COLUMNS,
            allowed_hosts=["www.fda.gov"],
        )


@pytest.mark.parametrize("failure", [None, "empty", "repeated"])
async def test_live_pipeline_handles_page_caps_and_incremental_refresh(
    settings,
    fixture_dir,
    monkeypatch,
    failure,
):
    database = Database(settings.database_url)
    await database.create_schema()
    settings = settings.model_copy(
        update={
            "ingestion_schedule_enabled": True,
            "ingestion_worker_enabled": True,
        }
    )
    configuration = {
        "datatables": {
            "warning-letters": {
                "serverSide": True,
                "deferLoading": 3,
                "aoColumnHeaders": [{"content": title} for title in COLUMNS],
                "ajax": {"url": "/datatables/views/ajax", "data": {"total_items": 3}},
            }
        }
    }
    listing = (
        f"<script>{json.dumps(configuration)}</script>"
        "<table><tr><th>Posted Date</th><th>Company Name</th></tr>"
        f"<tr><td>{row(0)[0]}</td><td>{row(0)[1]}</td></tr></table>"
    ).encode()
    html = (fixture_dir / "drugs/cder_finished_rx.html").read_bytes()
    offsets, details = [], Counter()

    class Client:
        def __init__(self, _settings):
            pass

        async def fetch(self, url):
            content_type = "text/html"
            if url == settings.fda_listing_url:
                content = listing
            elif urlsplit(url).path == "/datatables/views/ajax":
                offset = int(parse_qs(urlsplit(url).query)["start"][0])
                offsets.append(offset)
                # FDA can cap a requested length of 1000 to two actual rows.
                data = [row(0), row(1)] if offset == 0 else [row(2)]
                if offset > 0 and failure:
                    data = [] if failure == "empty" else [row(0), row(1)]
                content = json.dumps({"data": data, "recordsFiltered": 3}).encode()
                content_type = "application/json"
            else:
                details[url] += 1
                content = html
            return FetchedSource(
                requested_url=url,
                final_url=url,
                redirect_chain=[],
                content=content,
                content_type=content_type,
                status_code=200,
                headers={},
                retrieved_monotonic=0,
            )

    monkeypatch.setattr("app.worker.FdaClient", Client)
    try:
        now = utcnow()
        assert await schedule_ingestion(database, settings, now=now)
        result = await process_next_job(database, settings)
        assert offsets == [0, 2]
        if failure:
            assert result.status == JobStatus.PENDING.value
            assert not details
            return
        assert result.status == JobStatus.SUCCEEDED.value
        assert result.metrics["fetched"] == 3
        assert len(details) == 3
        assert await schedule_ingestion(database, settings, now=now + timedelta(days=1))
        result = await process_next_job(database, settings)
        assert result.status == JobStatus.SUCCEEDED.value
        assert result.metrics["fetched"] == 0
        assert result.metrics["skipped_recent"] == 3
        assert set(details.values()) == {1}
        async with database.session_factory() as session:
            letter = await session.scalar(
                select(WarningLetter).where(
                    WarningLetter.canonical_url.endswith("railway-0"),
                )
            )
            letter.last_seen_at = now - timedelta(days=20)
            await session.commit()
        assert await schedule_ingestion(database, settings, now=now + timedelta(days=2))
        result = await process_next_job(database, settings)
        assert result.status == JobStatus.SUCCEEDED.value
        assert result.metrics["fetched"] == 1
        assert result.metrics["skipped_recent"] == 2
        assert details["https://www.fda.gov/warning-letters/railway-0"] == 2
        async with database.session_factory() as session:
            assert await session.scalar(select(func.count()).select_from(DocumentVersion)) == 3
    finally:
        await database.dispose()


async def test_shipped_read_only_probe_parses_drug_and_non_drug_details(
    settings,
    fixture_dir,
    monkeypatch,
):
    from app.fda_probe import probe

    listing = (
        b"Posted Date,Company Name,Letter URL\n"
        b"09/09/2026,Drug,https://www.fda.gov/warning-letters/drug\n"
        b"09/09/2026,Food,https://www.fda.gov/warning-letters/food\n"
    )
    settings = settings.model_copy(
        update={
            "fda_listing_url": "https://www.fda.gov/warning-letters/sample.csv",
        }
    )

    class Client:
        def __init__(self, _settings):
            pass

        async def fetch(self, url):
            content_type = "text/html"
            if url == settings.fda_listing_url:
                content, content_type = listing, "text/csv"
            else:
                filename = (
                    "drugs/cder_finished_rx.html"
                    if url.endswith("drug")
                    else ("out_of_scope/food.html")
                )
                content = (fixture_dir / filename).read_bytes()
            return FetchedSource(
                requested_url=url,
                final_url=url,
                redirect_chain=[],
                content=content,
                content_type=content_type,
                status_code=200,
                headers={},
                retrieved_monotonic=0,
            )

    monkeypatch.setattr("app.fda_probe.get_settings", lambda: settings)
    monkeypatch.setattr("app.fda_probe.FdaClient", Client)
    report = await probe(pages=1, details=2)
    assert report["read_only"]
    assert report["letters"][0]["searchable_chunks"] > 0
    assert report["letters"][1]["searchable_chunks"] == 0
