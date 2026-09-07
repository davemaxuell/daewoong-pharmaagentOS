from __future__ import annotations

import asyncio
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql

from app.config import Settings
from app.database import Database
from app.enums import JobStatus, RunStatus, ScopeStatus
from app.fda_client import FdaSystemicAcquisitionError, FetchedSource
from app.models import (
    ChangeEvent,
    Document,
    DocumentVersion,
    IngestionRun,
    NotificationDelivery,
    ProcessingJob,
    WarningLetter,
    utcnow,
)
from app.retention import (
    is_within_discovery_window,
    retire_local_illustrative_letters,
    years_before,
)
from app.worker import (
    DiscoveryCheckpointCorrupt,
    DiscoveryCheckpointTooLarge,
    _candidate_digest,
    _claim_job_statement,
    _load_live_discovery_checkpoint,
    process_next_job,
    recover_interrupted_local_jobs,
    recover_stale_worker_jobs,
    run_worker,
)


@pytest.mark.asyncio
async def test_fixture_worker_discovers_and_scope_gates(
    settings: Settings, fixture_dir: Path
) -> None:
    database = Database(settings.database_url)
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            run = IngestionRun(
                run_type="discovery",
                source="fixture corpus",
                status=RunStatus.PENDING.value,
                requested_by="test",
                idempotency_key="worker-fixture-discovery",
                parser_version=settings.parser_version,
                scope_rule_version=settings.drug_scope_rule_version,
            )
            session.add(run)
            await session.flush()
            session.add(
                ProcessingJob(
                    ingestion_run_id=run.id,
                    job_type="discovery",
                    status=JobStatus.PENDING.value,
                    idempotency_key="worker-fixture-discovery-job",
                    payload={"fixture_dir": str(fixture_dir)},
                )
            )
            await session.commit()
        result = await process_next_job(database, settings)
        assert result is not None
        assert result.status == JobStatus.SUCCEEDED.value
        assert result.metrics["in_scope"] == 4
        assert result.metrics["out_of_scope"] == 3
        assert result.metrics["ambiguous"] == 3
        async with database.session_factory() as session:
            visible = await session.scalar(
                select(func.count(WarningLetter.id)).where(WarningLetter.current_in_scope.is_(True))
            )
            assert visible == 4
    finally:
        await database.dispose()


def test_calendar_year_discovery_cutoff_is_inclusive_and_leap_safe() -> None:
    cutoff = years_before(date(2026, 8, 30), 3)
    assert cutoff == date(2023, 8, 30)
    assert is_within_discovery_window(posted_date=date(2023, 8, 30), issue_date=None, cutoff=cutoff)
    assert not is_within_discovery_window(
        posted_date=date(2023, 8, 29), issue_date=None, cutoff=cutoff
    )
    assert years_before(date(2024, 2, 29), 1) == date(2023, 2, 28)


def test_live_discovery_checkpoint_rejects_inconsistent_counts() -> None:
    source_url = "https://www.fda.gov/warning-letters/checkpoint-source.csv"
    job = ProcessingJob(
        job_type="discovery",
        idempotency_key="invalid-checkpoint-counts",
        payload={
            "live_discovery_checkpoint": {
                "version": 1,
                "source_url": source_url,
                "cutoff_date": "2023-08-30",
                "candidate_key_version": "canonical-url-sha256-v1",
                "updated_at": utcnow().isoformat(),
                "completed_url_hashes": ["a" * 64],
                "failed_url_hashes": [],
                "metrics": {
                    "fetched": 0,
                    "in_scope": 0,
                    "out_of_scope": 0,
                    "ambiguous": 0,
                    "failed": 0,
                },
            }
        },
    )

    with pytest.raises(DiscoveryCheckpointCorrupt):
        _load_live_discovery_checkpoint(job, source_url)


def test_live_discovery_checkpoint_rejects_oversized_hash_set() -> None:
    source_url = "https://www.fda.gov/warning-letters/checkpoint-source.csv"
    completed_hashes = [f"{index:064x}" for index in range(10_001)]
    job = ProcessingJob(
        job_type="discovery",
        idempotency_key="oversized-checkpoint",
        payload={
            "live_discovery_checkpoint": {
                "version": 1,
                "source_url": source_url,
                "cutoff_date": "2023-08-30",
                "candidate_key_version": "canonical-url-sha256-v1",
                "updated_at": utcnow().isoformat(),
                "completed_url_hashes": completed_hashes,
                "failed_url_hashes": [],
                "metrics": {
                    "fetched": len(completed_hashes),
                    "in_scope": len(completed_hashes),
                    "out_of_scope": 0,
                    "ambiguous": 0,
                    "failed": 0,
                },
            }
        },
    )

    with pytest.raises(DiscoveryCheckpointTooLarge):
        _load_live_discovery_checkpoint(job, source_url)


@pytest.mark.asyncio
async def test_live_local_sync_soft_retires_only_illustrative_seed_letters(
    settings: Settings,
) -> None:
    database = Database(settings.database_url)
    local_settings = settings.model_copy(update={"app_env": "development"})
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            example = WarningLetter(
                canonical_url="https://www.fda.gov/warning-letters/example-local-900001",
                company_name="Example Local Drug",
                current_in_scope=True,
                scope_status=ScopeStatus.IN_SCOPE_DRUGS.value,
            )
            official = WarningLetter(
                canonical_url=(
                    "https://www.fda.gov/inspections-compliance-enforcement-and-criminal-"
                    "investigations/warning-letters/official-drug-735001-08202026"
                ),
                company_name="Official Drug Company",
                current_in_scope=True,
                scope_status=ScopeStatus.IN_SCOPE_DRUGS.value,
            )
            session.add_all([example, official])
            await session.commit()
            assert await retire_local_illustrative_letters(session, local_settings) == 1
            await session.commit()
            assert example.current_in_scope is False
            assert example.lifecycle_status == "retired_illustrative_fixture"
            assert official.current_in_scope is True
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_embedded_worker_requeues_interrupted_running_job(settings: Settings) -> None:
    database = Database(settings.database_url)
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            run = IngestionRun(
                run_type="discovery",
                source="FDA listing",
                status=RunStatus.RUNNING.value,
                requested_by="test",
                idempotency_key="interrupted-local-run",
                parser_version=settings.parser_version,
                scope_rule_version=settings.drug_scope_rule_version,
            )
            session.add(run)
            await session.flush()
            job = ProcessingJob(
                ingestion_run_id=run.id,
                job_type="discovery",
                status=JobStatus.RUNNING.value,
                idempotency_key="interrupted-local-job",
                payload={"source": "FDA listing"},
                attempt_count=1,
            )
            session.add(job)
            await session.commit()
            assert await recover_interrupted_local_jobs(session) == 1
            await session.commit()
            assert job.status == JobStatus.PENDING.value
            assert job.attempt_count == 0
            assert job.last_error_code == "WorkerRestarted"
            assert run.status == RunStatus.PENDING.value
    finally:
        await database.dispose()


def test_postgresql_job_claim_uses_skip_locked_and_returning() -> None:
    compiled = str(
        _claim_job_statement(
            claimed_at=utcnow(),
            dialect_name="postgresql",
        ).compile(dialect=postgresql.dialect())
    ).upper()

    assert "FOR UPDATE SKIP LOCKED" in compiled
    assert "RETURNING PROCESSING_JOBS.ID" in compiled


@pytest.mark.asyncio
async def test_concurrent_workers_claim_embedding_job_only_once(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = Database(settings.database_url)
    provider_started = asyncio.Event()
    release_provider = asyncio.Event()
    provider_calls = 0

    async def fake_embed_current_chunks(*_args, **_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        provider_started.set()
        await release_provider.wait()
        return SimpleNamespace(as_dict=lambda: {"embeddings_created": 1})

    generator = SimpleNamespace(chunker_version="structure-v1")
    monkeypatch.setattr(
        "app.worker.build_embedding_generator_for_job",
        lambda _settings, _payload: generator,
    )
    monkeypatch.setattr("app.worker.embed_current_chunks", fake_embed_current_chunks)
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            session.add(
                ProcessingJob(
                    job_type="embed",
                    status=JobStatus.PENDING.value,
                    idempotency_key="single-atomic-embedding-claim",
                    payload={"spec_version": 1},
                )
            )
            await session.commit()

        first_worker = asyncio.create_task(process_next_job(database, settings))
        await asyncio.wait_for(provider_started.wait(), timeout=2)
        second_result = await process_next_job(database, settings)
        assert second_result is None
        assert provider_calls == 1
        release_provider.set()
        first_result = await asyncio.wait_for(first_worker, timeout=2)
        assert first_result is not None
        assert first_result.status == JobStatus.SUCCEEDED.value

        async with database.session_factory() as session:
            job = await session.scalar(
                select(ProcessingJob).where(
                    ProcessingJob.idempotency_key == "single-atomic-embedding-claim"
                )
            )
            assert job is not None
            assert job.attempt_count == 1
            assert job.status == JobStatus.SUCCEEDED.value
    finally:
        release_provider.set()
        await database.dispose()


@pytest.mark.asyncio
async def test_standalone_worker_recovers_stale_leases_and_dead_letters_exhausted_jobs(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = Database(settings.database_url)
    now = utcnow()
    observed_statuses: dict[str, str] = {}

    async def observe_recovery(_database: Database, _settings: Settings):
        async with _database.session_factory() as session:
            rows = (
                await session.execute(select(ProcessingJob.idempotency_key, ProcessingJob.status))
            ).all()
            observed_statuses.update(dict(rows))
        return None

    monkeypatch.setattr("app.worker.process_next_job", observe_recovery)
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            session.add_all(
                [
                    ProcessingJob(
                        job_type="embed",
                        status=JobStatus.RUNNING.value,
                        idempotency_key="stale-recoverable-job",
                        attempt_count=1,
                        max_attempts=3,
                        started_at=now - timedelta(minutes=10),
                        available_at=now - timedelta(seconds=1),
                    ),
                    ProcessingJob(
                        job_type="embed",
                        status=JobStatus.RUNNING.value,
                        idempotency_key="stale-exhausted-job",
                        attempt_count=3,
                        max_attempts=3,
                        started_at=now - timedelta(minutes=10),
                        available_at=now - timedelta(seconds=1),
                    ),
                    ProcessingJob(
                        job_type="embed",
                        status=JobStatus.RUNNING.value,
                        idempotency_key="live-leased-job",
                        attempt_count=1,
                        max_attempts=3,
                        started_at=now,
                        available_at=now + timedelta(minutes=4),
                    ),
                ]
            )
            await session.commit()

        assert await run_worker(database, settings, once=True) == 0
        assert observed_statuses == {
            "live-leased-job": JobStatus.RUNNING.value,
            "stale-exhausted-job": JobStatus.DEAD_LETTER.value,
            "stale-recoverable-job": JobStatus.PENDING.value,
        }

        async with database.session_factory() as session:
            recoverable = await session.scalar(
                select(ProcessingJob).where(
                    ProcessingJob.idempotency_key == "stale-recoverable-job"
                )
            )
            exhausted = await session.scalar(
                select(ProcessingJob).where(ProcessingJob.idempotency_key == "stale-exhausted-job")
            )
            assert recoverable is not None
            assert recoverable.attempt_count == 1
            assert recoverable.started_at is None
            assert recoverable.last_error_code == "StaleLeaseExpired"
            assert exhausted is not None
            assert exhausted.last_error_code == "StaleLeaseExhausted"
            assert exhausted.completed_at is not None
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_stale_lease_recovery_is_bounded(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = Database(settings.database_url)
    now = utcnow()
    monkeypatch.setattr("app.worker._STALE_JOB_RECOVERY_LIMIT", 1)
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            session.add_all(
                [
                    ProcessingJob(
                        job_type="embed",
                        status=JobStatus.RUNNING.value,
                        idempotency_key=f"bounded-stale-job-{index}",
                        attempt_count=1,
                        max_attempts=3,
                        started_at=now - timedelta(minutes=10),
                        available_at=now - timedelta(seconds=1),
                    )
                    for index in range(2)
                ]
            )
            await session.commit()

        assert await recover_stale_worker_jobs(database, recovered_at=now) == 1
        async with database.session_factory() as session:
            running_count = await session.scalar(
                select(func.count(ProcessingJob.id)).where(
                    ProcessingJob.status == JobStatus.RUNNING.value
                )
            )
            assert running_count == 1
    finally:
        await database.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("continuation", [False, True])
async def test_live_discovery_resume_skips_completed_details_and_preserves_metrics(
    settings: Settings,
    fixture_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    continuation: bool,
) -> None:
    listing_url = "https://www.fda.gov/warning-letters/resume-regression.csv"
    detail_urls = [
        "https://www.fda.gov/warning-letters/resume-in-scope-1",
        "https://www.fda.gov/warning-letters/resume-out-of-scope-2",
        "https://www.fda.gov/warning-letters/resume-ambiguous-3",
        "https://www.fda.gov/warning-letters/resume-in-scope-4",
    ]
    listing = (
        "Posted Date,Letter Issue Date,Company Name,Letter URL\n"
        f'08/29/2026,08/28/2026,"Resume Drug Company","{detail_urls[0]}"\n'
        f'08/27/2026,08/26/2026,"Resume Food Company","{detail_urls[1]}"\n'
        f'08/25/2026,08/24/2026,"Resume Ambiguous Company","{detail_urls[2]}"\n'
        f'08/23/2026,08/22/2026,"Resume OTC Company","{detail_urls[3]}"\n'
    ).encode()
    detail_documents = {
        detail_urls[0]: (fixture_dir / "drugs" / "cder_finished_rx.html").read_bytes(),
        detail_urls[1]: (fixture_dir / "out_of_scope" / "food.html").read_bytes(),
        detail_urls[2]: (fixture_dir / "ambiguous" / "missing_product.html").read_bytes(),
        detail_urls[3]: (fixture_dir / "drugs" / "cder_otc.html").read_bytes(),
    }
    database = Database(settings.database_url)
    run_id = ""
    state: dict[str, object] = {
        "phase": 1,
        "interrupted": False,
        "ordinary_failure_raised": False,
        "detail_attempts": [],
        "resume_first_detail": None,
        "resume_metrics": None,
    }

    def fetched_source(url: str, content: bytes, content_type: str) -> FetchedSource:
        return FetchedSource(
            requested_url=url,
            final_url=url,
            redirect_chain=[],
            content=content,
            content_type=content_type,
            status_code=200,
            headers={},
            retrieved_monotonic=0.0,
        )

    class FakeFdaClient:
        def __init__(self, _settings: Settings) -> None:
            pass

        async def fetch(self, url: str) -> FetchedSource:
            if url == listing_url:
                return fetched_source(url, listing, "text/csv")

            attempts = state["detail_attempts"]
            assert isinstance(attempts, list)
            attempts.append(url)

            if state["phase"] == 2 and state["resume_first_detail"] is None:
                state["resume_first_detail"] = url
                async with database.session_factory() as observer:
                    persisted_run = await observer.get(IngestionRun, run_id)
                    assert persisted_run is not None
                    state["resume_metrics"] = dict(persisted_run.metrics or {})

            if (
                url == detail_urls[2]
                and state["phase"] == 1
                and not state["ordinary_failure_raised"]
            ):
                state["ordinary_failure_raised"] = True
                raise RuntimeError("Simulated transient detail failure")

            if url == detail_urls[3] and state["phase"] == 1 and not state["interrupted"]:
                state["interrupted"] = True
                raise asyncio.CancelledError()

            content = detail_documents.get(url)
            if content is None:
                raise RuntimeError(f"Unexpected FDA detail URL: {url}")
            return fetched_source(url, content, "text/html")

    monkeypatch.setattr("app.worker.FdaClient", FakeFdaClient)

    try:
        await database.create_schema()
        async with database.session_factory() as session:
            run = IngestionRun(
                run_type="discovery",
                source=listing_url,
                status=RunStatus.PENDING.value,
                requested_by="test",
                idempotency_key="worker-live-resume",
                parser_version=settings.parser_version,
                scope_rule_version=settings.drug_scope_rule_version,
            )
            session.add(run)
            await session.flush()
            run_id = run.id
            job = ProcessingJob(
                ingestion_run_id=run.id,
                job_type="discovery",
                status=JobStatus.PENDING.value,
                idempotency_key="worker-live-resume-job",
                payload={"source": listing_url},
            )
            session.add(job)
            await session.commit()
            job_id = job.id

        with pytest.raises(asyncio.CancelledError):
            await process_next_job(
                database,
                settings,
                reference_date=date(2026, 8, 30),
                continuation_on_cancel=continuation,
            )

        async with database.session_factory() as session:
            interrupted_run = await session.get(IngestionRun, run_id)
            interrupted_job = await session.get(ProcessingJob, job_id)
            assert interrupted_run is not None
            assert interrupted_job is not None
            assert interrupted_run.status == RunStatus.PENDING.value
            assert interrupted_job.status == JobStatus.PENDING.value
            assert interrupted_job.attempt_count == 1
            assert interrupted_job.max_attempts == 3 + int(continuation)
            assert interrupted_job.last_error_code == (
                "WorkerTimeSlice" if continuation else "WorkerCancelled"
            )
            checkpoint_metrics = dict(interrupted_run.metrics or {})
            assert checkpoint_metrics["fetched"] == 2
            assert checkpoint_metrics["in_scope"] == 1
            assert checkpoint_metrics["out_of_scope"] == 1
            assert checkpoint_metrics["ambiguous"] == 0
            assert checkpoint_metrics["failed"] == 1
            interrupted_job.available_at = utcnow()
            await session.commit()

        state["phase"] = 2
        result = await process_next_job(database, settings, reference_date=date(2026, 8, 30))
        assert result is not None
        assert result.status == JobStatus.SUCCEEDED.value

        attempts = state["detail_attempts"]
        assert isinstance(attempts, list)
        assert Counter(attempts) == Counter(
            {
                detail_urls[0]: 1,
                detail_urls[1]: 1,
                detail_urls[2]: 2,
                detail_urls[3]: 2,
            }
        )
        assert state["resume_first_detail"] == detail_urls[2]

        resume_metrics = state["resume_metrics"]
        assert isinstance(resume_metrics, dict)
        cumulative_metrics = (
            "outside_backfill_window",
            "fetched",
            "in_scope",
            "out_of_scope",
            "ambiguous",
        )
        for metric in cumulative_metrics:
            assert int(resume_metrics.get(metric, 0)) >= int(checkpoint_metrics.get(metric, 0))
            assert int(result.metrics.get(metric, 0)) >= int(resume_metrics.get(metric, 0))
        assert resume_metrics["failed"] == 1

        assert result.metrics["listing_rows"] == 4
        assert result.metrics["listing_total"] == 4
        assert result.metrics["fetched"] == 4
        assert result.metrics["in_scope"] == 2
        assert result.metrics["out_of_scope"] == 1
        assert result.metrics["ambiguous"] == 1
        assert result.metrics["failed"] == 0

        async with database.session_factory() as session:
            final_run = await session.get(IngestionRun, run_id)
            assert final_run is not None
            assert final_run.status == RunStatus.SUCCEEDED.value
            assert final_run.metrics["fetched"] == 4
            assert final_run.metrics["failed"] == 0
            assert await session.scalar(select(func.count(WarningLetter.id))) == 4
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_systemic_acquisition_outage_circuit_breaks_without_failure_avalanche(
    settings: Settings,
    fixture_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    listing_url = "https://www.fda.gov/warning-letters/systemic-outage.csv"
    detail_urls = [
        f"https://www.fda.gov/warning-letters/systemic-outage-{index}" for index in range(1, 5)
    ]
    listing = (
        "Posted Date,Letter Issue Date,Company Name,Letter URL\n"
        + "".join(
            f'08/2{index}/2026,08/1{index}/2026,"Outage Company {index}","{url}"\n'
            for index, url in enumerate(detail_urls, start=1)
        )
    ).encode()
    detail_html = (fixture_dir / "drugs" / "cder_finished_rx.html").read_bytes()
    detail_attempts: list[str] = []

    def fetched_source(url: str, content: bytes, content_type: str) -> FetchedSource:
        return FetchedSource(
            requested_url=url,
            final_url=url,
            redirect_chain=[],
            content=content,
            content_type=content_type,
            status_code=200,
            headers={},
            retrieved_monotonic=0.0,
        )

    class FakeFdaClient:
        def __init__(self, _settings: Settings) -> None:
            pass

        async def fetch(self, url: str) -> FetchedSource:
            if url == listing_url:
                return fetched_source(url, listing, "text/csv")
            detail_attempts.append(url)
            if url == detail_urls[1]:
                raise FdaSystemicAcquisitionError("dns_preflight_unavailable")
            return fetched_source(url, detail_html, "text/html")

    monkeypatch.setattr("app.worker.FdaClient", FakeFdaClient)
    database = Database(settings.database_url)
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            run = IngestionRun(
                run_type="discovery",
                source=listing_url,
                status=RunStatus.PENDING.value,
                requested_by="test",
                idempotency_key="systemic-outage-run",
                parser_version=settings.parser_version,
                scope_rule_version=settings.drug_scope_rule_version,
            )
            session.add(run)
            await session.flush()
            job = ProcessingJob(
                ingestion_run_id=run.id,
                job_type="discovery",
                status=JobStatus.PENDING.value,
                idempotency_key="systemic-outage-job",
                payload={"source": listing_url},
            )
            session.add(job)
            await session.commit()
            run_id = run.id
            job_id = job.id

        with caplog.at_level("WARNING", logger="uvicorn.error"):
            result = await process_next_job(database, settings, reference_date=date(2026, 8, 30))
        assert result is not None
        assert result.status == JobStatus.PENDING.value
        assert detail_attempts == detail_urls[:2]
        assert "reason=dns_preflight_unavailable" in caplog.text
        assert f"candidate_hash={_candidate_digest(detail_urls[1])}" in caplog.text
        assert detail_urls[1] not in caplog.text

        async with database.session_factory() as session:
            persisted_run = await session.get(IngestionRun, run_id)
            persisted_job = await session.get(ProcessingJob, job_id)
            assert persisted_run is not None
            assert persisted_job is not None
            assert persisted_run.status == RunStatus.PENDING.value
            assert persisted_job.status == JobStatus.PENDING.value
            assert persisted_job.last_error_code == "FdaSystemicAcquisitionError"
            _, completed, failed, metrics, valid = _load_live_discovery_checkpoint(
                persisted_job, listing_url
            )
            assert valid is True
            assert completed == {_candidate_digest(detail_urls[0])}
            assert failed == set()
            assert metrics["fetched"] == 1
            assert metrics["failed"] == 0
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_unresolved_candidate_failure_automatically_retries_same_checkpointed_job(
    settings: Settings,
    fixture_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listing_url = "https://www.fda.gov/warning-letters/partial-auto-retry.csv"
    detail_urls = [
        "https://www.fda.gov/warning-letters/partial-auto-retry-one",
        "https://www.fda.gov/warning-letters/partial-auto-retry-two",
    ]
    listing = (
        "Posted Date,Letter Issue Date,Company Name,Letter URL\n"
        f'08/29/2026,08/28/2026,"Retry One","{detail_urls[0]}"\n'
        f'08/27/2026,08/26/2026,"Retry Two","{detail_urls[1]}"\n'
    ).encode()
    detail_html = (fixture_dir / "drugs" / "cder_finished_rx.html").read_bytes()
    attempts: Counter[str] = Counter()

    def fetched_source(url: str, content: bytes, content_type: str) -> FetchedSource:
        return FetchedSource(
            requested_url=url,
            final_url=url,
            redirect_chain=[],
            content=content,
            content_type=content_type,
            status_code=200,
            headers={},
            retrieved_monotonic=0.0,
        )

    class FakeFdaClient:
        def __init__(self, _settings: Settings) -> None:
            pass

        async def fetch(self, url: str) -> FetchedSource:
            if url == listing_url:
                return fetched_source(url, listing, "text/csv")
            attempts[url] += 1
            if url == detail_urls[1] and attempts[url] < 3:
                raise RuntimeError("candidate-local parse/acquisition failure")
            return fetched_source(url, detail_html, "text/html")

    monkeypatch.setattr("app.worker.FdaClient", FakeFdaClient)
    database = Database(settings.database_url)
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            run = IngestionRun(
                run_type="discovery",
                source=listing_url,
                status=RunStatus.PENDING.value,
                requested_by="test",
                idempotency_key="partial-auto-retry-run",
                parser_version=settings.parser_version,
                scope_rule_version=settings.drug_scope_rule_version,
            )
            session.add(run)
            await session.flush()
            job = ProcessingJob(
                ingestion_run_id=run.id,
                job_type="discovery",
                status=JobStatus.PENDING.value,
                idempotency_key="partial-auto-retry-job",
                payload={"source": listing_url},
            )
            session.add(job)
            await session.commit()
            run_id = run.id
            job_id = job.id

        for expected_attempt in (1, 2):
            result = await process_next_job(database, settings, reference_date=date(2026, 8, 30))
            assert result is not None
            assert result.status == JobStatus.PENDING.value
            assert result.metrics["failed"] == 1
            async with database.session_factory() as session:
                pending_run = await session.get(IngestionRun, run_id)
                pending_job = await session.get(ProcessingJob, job_id)
                assert pending_run is not None
                assert pending_job is not None
                assert pending_run.status == RunStatus.PENDING.value
                assert pending_job.status == JobStatus.PENDING.value
                assert pending_job.attempt_count == expected_attempt
                pending_job.available_at = utcnow()
                await session.commit()

        result = await process_next_job(database, settings, reference_date=date(2026, 8, 30))
        assert result is not None
        assert result.status == JobStatus.SUCCEEDED.value
        assert result.metrics["failed"] == 0
        assert attempts == Counter({detail_urls[1]: 3, detail_urls[0]: 1})
        async with database.session_factory() as session:
            final_run = await session.get(IngestionRun, run_id)
            final_job = await session.get(ProcessingJob, job_id)
            assert final_run is not None
            assert final_job is not None
            assert final_run.status == RunStatus.SUCCEEDED.value
            assert final_job.status == JobStatus.SUCCEEDED.value
            _, completed, failed, _, _ = _load_live_discovery_checkpoint(final_job, listing_url)
            assert len(completed) == 2
            assert failed == set()
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_live_discovery_bootstraps_legacy_progress_without_refetching(
    settings: Settings,
    fixture_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listing_url = "https://www.fda.gov/warning-letters/legacy-resume.csv"
    completed_url = "https://www.fda.gov/warning-letters/legacy-completed-1"
    remaining_url = "https://www.fda.gov/warning-letters/legacy-remaining-2"
    listing = (
        "Posted Date,Letter Issue Date,Company Name,Letter URL\n"
        f'08/29/2026,08/28/2026,"Legacy Completed Company","{completed_url}"\n'
        f'08/27/2026,08/26/2026,"Legacy Remaining Company","{remaining_url}"\n'
    ).encode()
    remaining_document = (fixture_dir / "drugs" / "cder_finished_rx.html").read_bytes()
    detail_attempts: list[str] = []

    def fetched_source(url: str, content: bytes, content_type: str) -> FetchedSource:
        return FetchedSource(
            requested_url=url,
            final_url=url,
            redirect_chain=[],
            content=content,
            content_type=content_type,
            status_code=200,
            headers={},
            retrieved_monotonic=0.0,
        )

    class FakeFdaClient:
        def __init__(self, _settings: Settings) -> None:
            pass

        async def fetch(self, url: str) -> FetchedSource:
            if url == listing_url:
                return fetched_source(url, listing, "text/csv")
            detail_attempts.append(url)
            if url != remaining_url:
                raise RuntimeError(f"Unexpected FDA detail URL: {url}")
            return fetched_source(url, remaining_document, "text/html")

    monkeypatch.setattr("app.worker.FdaClient", FakeFdaClient)
    database = Database(settings.database_url)
    started_at = utcnow() - timedelta(minutes=10)
    seen_at = started_at + timedelta(minutes=5)

    try:
        await database.create_schema()
        async with database.session_factory() as session:
            run = IngestionRun(
                run_type="discovery",
                source=listing_url,
                status=RunStatus.PENDING.value,
                requested_by="test",
                idempotency_key="worker-legacy-live-resume",
                parser_version=settings.parser_version,
                scope_rule_version=settings.drug_scope_rule_version,
                started_at=started_at,
                metrics={
                    "listing_rows": 2,
                    "listing_total": 2,
                    "outside_backfill_window": 0,
                    "fetched": 1,
                    "in_scope": 1,
                    "out_of_scope": 0,
                    "ambiguous": 0,
                    "failed": 0,
                },
            )
            session.add(run)
            await session.flush()
            run_id = run.id
            completed_letter = WarningLetter(
                canonical_url=completed_url,
                company_name="Legacy Completed Company",
                posted_date=date(2026, 8, 29),
                issue_date=date(2026, 8, 28),
                normalized_product_classes=["Drugs"],
                scope_status=ScopeStatus.IN_SCOPE_DRUGS.value,
                current_in_scope=True,
                first_seen_at=seen_at,
                last_seen_at=seen_at,
            )
            session.add(completed_letter)
            await session.flush()
            completed_document = Document(
                warning_letter_id=completed_letter.id,
                canonical_url=completed_url,
                title="Legacy Completed Company warning letter",
                issue_date=date(2026, 8, 28),
                current_in_scope=True,
            )
            session.add(completed_document)
            await session.flush()
            completed_version = DocumentVersion(
                document_id=completed_document.id,
                version_number=1,
                raw_sha256="1" * 64,
                canonical_hash="2" * 64,
                parser_version=settings.parser_version,
                fda_product_raw=["Drugs"],
                normalized_product_classes=["Drugs"],
                scope_status=ScopeStatus.IN_SCOPE_DRUGS.value,
                retrieved_at=seen_at,
                last_seen_at=seen_at,
                created_at=seen_at,
            )
            session.add(completed_version)
            await session.flush()
            completed_document.current_version_id = completed_version.id
            completed_letter.current_version_id = completed_version.id
            completed_letter.first_in_scope_version_id = completed_version.id
            job = ProcessingJob(
                ingestion_run_id=run.id,
                job_type="discovery",
                status=JobStatus.PENDING.value,
                idempotency_key="worker-legacy-live-resume-job",
                payload={"source": listing_url},
            )
            session.add(job)
            await session.commit()
            job_id = job.id

        result = await process_next_job(database, settings, reference_date=date(2026, 8, 30))
        assert result is not None
        assert result.status == JobStatus.SUCCEEDED.value
        assert detail_attempts == [remaining_url]
        assert result.metrics["fetched"] == 2
        assert result.metrics["in_scope"] == 2
        assert result.metrics["out_of_scope"] == 0
        assert result.metrics["ambiguous"] == 0
        assert result.metrics["failed"] == 0

        async with database.session_factory() as session:
            final_run = await session.get(IngestionRun, run_id)
            final_job = await session.get(ProcessingJob, job_id)
            assert final_run is not None
            assert final_job is not None
            assert final_run.metrics["fetched"] == 2
            assert final_run.metrics["in_scope"] == 2
            assert "live_discovery_checkpoint" in final_job.payload
            assert await session.scalar(select(func.count(WarningLetter.id))) == 2
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_discovery_worker_fetches_only_configured_three_year_window(
    settings: Settings, fixture_dir: Path, tmp_path: Path
) -> None:
    bounded_fixtures = tmp_path / "bounded-fixtures"
    bounded_fixtures.mkdir()
    source_html = fixture_dir / "drugs" / "cder_finished_rx.html"
    (bounded_fixtures / "recent-drug.html").write_bytes(source_html.read_bytes())
    (bounded_fixtures / "old-drug.html").write_bytes(source_html.read_bytes())
    (bounded_fixtures / "listing_export.csv").write_text(
        "Posted Date,Letter Issue Date,Company Name,Letter URL\n"
        '08/30/2023,08/30/2023,"Recent Drug",'
        '"https://www.fda.gov/warning-letters/recent-drug"\n'
        '08/29/2023,08/29/2023,"Old Drug",'
        '"https://www.fda.gov/warning-letters/old-drug"\n',
        encoding="utf-8",
    )
    database = Database(settings.database_url)
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            run = IngestionRun(
                run_type="backfill",
                source="bounded fixture corpus",
                status=RunStatus.PENDING.value,
                requested_by="test",
                idempotency_key="worker-three-year-backfill",
                parser_version=settings.parser_version,
                scope_rule_version=settings.drug_scope_rule_version,
            )
            session.add(run)
            await session.flush()
            session.add(
                ProcessingJob(
                    ingestion_run_id=run.id,
                    job_type="backfill",
                    status=JobStatus.PENDING.value,
                    idempotency_key="worker-three-year-backfill-job",
                    payload={"fixture_dir": str(bounded_fixtures)},
                )
            )
            await session.commit()
        result = await process_next_job(database, settings, reference_date=date(2026, 8, 30))
        assert result is not None
        assert result.metrics["listing_rows"] == 2
        assert result.metrics["outside_backfill_window"] == 1
        assert result.metrics["fetched"] == 1
        async with database.session_factory() as session:
            urls = set((await session.scalars(select(WarningLetter.canonical_url))).all())
            assert "https://www.fda.gov/warning-letters/recent-drug" in urls
            assert "https://www.fda.gov/warning-letters/old-drug" not in urls
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_worker_soft_retires_five_year_old_letters_and_tracks_email_outbox(
    settings: Settings, fixture_dir: Path
) -> None:
    database = Database(settings.database_url)
    reference_date = date(2026, 8, 30)
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            expired = WarningLetter(
                canonical_url="https://www.fda.gov/warning-letters/expired-drug-letter-1",
                company_name="Expired Drug Company",
                issue_date=date(2021, 8, 30),
                normalized_product_classes=["Drugs"],
                scope_status=ScopeStatus.IN_SCOPE_DRUGS.value,
                current_in_scope=True,
            )
            still_active = WarningLetter(
                canonical_url="https://www.fda.gov/warning-letters/recent-drug-letter-1",
                company_name="Recent Drug Company",
                issue_date=date(2021, 8, 31),
                normalized_product_classes=["Drugs"],
                scope_status=ScopeStatus.IN_SCOPE_DRUGS.value,
                current_in_scope=True,
            )
            session.add_all([expired, still_active])
            run = IngestionRun(
                run_type="discovery",
                source="fixture corpus",
                status=RunStatus.PENDING.value,
                requested_by="test",
                idempotency_key="worker-retention-discovery",
                parser_version=settings.parser_version,
                scope_rule_version=settings.drug_scope_rule_version,
            )
            session.add(run)
            await session.flush()
            session.add(
                ProcessingJob(
                    ingestion_run_id=run.id,
                    job_type="discovery",
                    status=JobStatus.PENDING.value,
                    idempotency_key="worker-retention-discovery-job",
                    payload={"fixture_dir": str(fixture_dir)},
                )
            )
            await session.commit()

        result = await process_next_job(database, settings, reference_date=reference_date)
        assert result is not None
        assert result.status == JobStatus.SUCCEEDED.value
        assert result.metrics["retired_from_active_corpus"] == 1
        # SMTP is off in tests, so delivery attempts are explicitly suppressed
        # and never leave the process.
        assert result.metrics["notifications_sent"] == 0
        assert result.metrics["notifications_suppressed"] == 4

        async with database.session_factory() as session:
            expired_row = await session.get(WarningLetter, expired.id)
            recent_row = await session.get(WarningLetter, still_active.id)
            assert expired_row is not None
            assert expired_row.current_in_scope is False
            assert expired_row.lifecycle_status == "retired_by_retention"
            assert recent_row is not None and recent_row.current_in_scope is True
            retirement_event = await session.scalar(
                select(ChangeEvent).where(
                    ChangeEvent.warning_letter_id == expired.id,
                    ChangeEvent.event_type == "CORPUS_RETIRED",
                )
            )
            assert retirement_event is not None
            assert retirement_event.after_state["cutoff_date"] == "2021-08-30"
            deliveries = list((await session.scalars(select(NotificationDelivery))).all())
            assert len(deliveries) == 4
            assert {delivery.status for delivery in deliveries} == {"suppressed"}
            assert {delivery.destination_identifier for delivery in deliveries} == {
                "grisellacrystabel@gmail.com"
            }
    finally:
        await database.dispose()
