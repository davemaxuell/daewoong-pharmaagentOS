from __future__ import annotations

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.background_worker import run_background_worker, schedule_ingestion
from app.config import Settings
from app.database import Database
from app.discovery import ListingCandidate
from app.enums import JobStatus
from app.ingestion import CandidateMetadata, ingest_html
from app.models import IngestionRun, ProcessingJob, WarningLetter, utcnow
from app.security.secrets import RailwaySecretProvider, build_secret_provider
from app.worker import (
    INGESTION_JOB_TYPES,
    _claim_next_job,
    _recent_candidate_urls,
    recover_stale_worker_jobs,
)


def railway_values():
    return dict(
        app_env="production",
        database_url="postgresql://fixture:fixture@db.internal/fixture",
        auto_create_schema=False,
        dev_auth_enabled=False,
        oidc_issuer="portal",
        oidc_audience="api",
        oidc_public_key="synthetic-key",
        allowed_origins=["https://portal.example"],
        allowed_hosts=["localhost"],
        secret_provider="railway",
        telemetry_backend="railway_logs",
        railway_project_id="fixture-project",
        railway_environment_id="fixture-environment",
        railway_service_id="fixture-service",
        railway_public_domain="api.up.railway.app",
        railway_private_domain="api.railway.internal",
        object_store_backend="supabase",
        object_store_supabase_url="https://fixture.supabase.co",
        object_store_supabase_secret_key="synthetic-secret",
    )


def test_railway_has_managed_secrets_logs_and_exact_health_hosts():
    settings = Settings(_env_file=None, **railway_values())
    assert isinstance(build_secret_provider(settings), RailwaySecretProvider)
    assert set(settings.allowed_hosts) == {
        "localhost",
        "api.up.railway.app",
        "api.railway.internal",
        "healthcheck.railway.app",
    }
    assert settings.otel_exporter_otlp_endpoint is None


@pytest.mark.parametrize(
    "overrides,match",
    [
        ({"railway_service_id": None}, "runtime metadata"),
        ({"railway_public_domain": "*.railway.app"}, "exact hostname"),
        ({"railway_private_domain": "https://api.railway.internal"}, "exact hostname"),
        ({"object_store_backend": "local"}, "persistent remote"),
        ({"dev_auth_enabled": True}, "DEV_AUTH_ENABLED"),
        ({"auto_create_schema": True}, "AUTO_CREATE_SCHEMA"),
        ({"ingestion_schedule_enabled": True}, "INGESTION_WORKER_ENABLED"),
    ],
)
def test_railway_preserves_production_guards(overrides, match):
    with pytest.raises(ValidationError, match=match):
        Settings(_env_file=None, **(railway_values() | overrides))


async def test_daily_schedule_is_durable_and_does_not_overlap(settings):
    settings = settings.model_copy(
        update={
            "ingestion_schedule_enabled": True,
            "ingestion_worker_enabled": True,
        }
    )
    database = Database(settings.database_url)
    await database.create_schema()
    now = utcnow()
    try:
        first = await schedule_ingestion(database, settings, now=now)
        assert first
        assert await schedule_ingestion(database, settings, now=now) is None
        # A run left pending across midnight blocks a duplicate daily pass.
        assert await schedule_ingestion(database, settings, now=now + timedelta(days=1)) is None
        async with database.session_factory() as session:
            job = await session.scalar(select(ProcessingJob))
            assert "fixture_dir" not in job.payload
            assert job.payload["source"] == settings.fda_listing_url
            assert job.payload["refresh_before"] == (now - timedelta(days=14)).isoformat()
            job.status = JobStatus.SUCCEEDED.value
            await session.commit()
        assert await schedule_ingestion(database, settings, now=now) is None
        assert await schedule_ingestion(database, settings, now=now + timedelta(days=1))
        async with database.session_factory() as session:
            assert await session.scalar(select(func.count()).select_from(IngestionRun)) == 2
    finally:
        await database.dispose()


async def test_ingestion_claim_serializes_distinct_jobs_and_does_not_claim_cases(settings):
    database = Database(settings.database_url)
    await database.create_schema()
    try:
        async with database.session_factory() as session:
            session.add_all(
                [
                    ProcessingJob(job_type=kind, idempotency_key=f"claim-{index}", payload={})
                    for index, kind in enumerate(["orchestrate_case_run", "discovery", "reconcile"])
                ]
            )
            await session.commit()
        first = await _claim_next_job(database, job_types=INGESTION_JOB_TYPES, single_active=True)
        assert first
        assert (
            await _claim_next_job(
                database,
                job_types=INGESTION_JOB_TYPES,
                single_active=True,
            )
            is None
        )
        async with database.session_factory() as session:
            running = await session.get(ProcessingJob, first.job_id)
            assert running.job_type in {"discovery", "reconcile"}
            running.status = JobStatus.SUCCEEDED.value
            await session.commit()
        assert await _claim_next_job(
            database,
            job_types=INGESTION_JOB_TYPES,
            single_active=True,
        )
    finally:
        await database.dispose()


async def test_recovery_leaves_case_lane_untouched(settings):
    database = Database(settings.database_url)
    await database.create_schema()
    try:
        async with database.session_factory() as session:
            session.add_all(
                [
                    ProcessingJob(
                        job_type=kind,
                        idempotency_key=f"recover-{kind}",
                        status=JobStatus.RUNNING.value,
                        attempt_count=1,
                        available_at=utcnow() - timedelta(minutes=1),
                    )
                    for kind in ["discovery", "orchestrate_case_run"]
                ]
            )
            await session.commit()
        assert await recover_stale_worker_jobs(database, job_types=INGESTION_JOB_TYPES) == 1
        async with database.session_factory() as session:
            case = await session.scalar(
                select(ProcessingJob).where(
                    ProcessingJob.job_type == "orchestrate_case_run",
                )
            )
            assert case.status == JobStatus.RUNNING.value
    finally:
        await database.dispose()


async def test_incremental_refresh_rechecks_changed_stale_and_unknown_letters(
    settings, fixture_dir
):
    database = Database(settings.database_url)
    await database.create_schema()
    url = "https://www.fda.gov/warning-letters/refresh-example"
    html = (fixture_dir / "drugs/cder_finished_rx.html").read_bytes()
    cutoff = (utcnow() - timedelta(days=14)).isoformat()
    try:
        async with database.session_factory() as session:
            result = await ingest_html(
                session,
                settings,
                CandidateMetadata(canonical_url=url, company_name="Fixture"),
                html,
            )
            await session.commit()
            candidate = ListingCandidate(canonical_url=url, company_name="Fixture")
            unknown = ListingCandidate(canonical_url=url + "-new")
            assert await _recent_candidate_urls(session, [candidate, unknown], cutoff) == {url}
            changed = ListingCandidate(canonical_url=url, company_name="Changed company")
            assert not await _recent_candidate_urls(session, [changed], cutoff)
            closeout = ListingCandidate(canonical_url=url, closeout_url=url + "/closeout")
            assert not await _recent_candidate_urls(session, [closeout], cutoff)
            letter = await session.get(WarningLetter, result.warning_letter_id)
            letter.last_seen_at = utcnow() - timedelta(days=15)
            await session.commit()
            assert not await _recent_candidate_urls(session, [candidate], cutoff)
            assert not await _recent_candidate_urls(session, [candidate], None)
    finally:
        await database.dispose()


async def test_background_lanes_run_independently_and_cancel_cleanly(settings, monkeypatch):
    database = Database(settings.database_url)
    await database.create_schema()
    await database.dispose()
    stop = asyncio.Event()
    ingestion_started = asyncio.Event()
    cancelled = []

    async def long_ingestion(*_):
        ingestion_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append("ingestion")

    async def short_research(*_):
        await ingestion_started.wait()
        stop.set()

    monkeypatch.setattr("app.background_worker.ingestion_loop", long_ingestion)
    monkeypatch.setattr("app.background_worker.research_loop", short_research)
    settings = settings.model_copy(
        update={
            "ingestion_worker_enabled": True,
            "research_agent_enabled": True,
            "llm_provider": "openai",
        }
    )
    await asyncio.wait_for(run_background_worker(settings, stop=stop), timeout=5)
    assert cancelled == ["ingestion"]


async def test_background_worker_recovers_from_transient_database_failure(settings, monkeypatch):
    from app.background_worker import ingestion_loop

    recover = AsyncMock(side_effect=[RuntimeError("private connection details"), 0])
    process = AsyncMock(side_effect=asyncio.CancelledError)
    monkeypatch.setattr("app.background_worker.recover_stale_worker_jobs", recover)
    monkeypatch.setattr("app.background_worker.process_next_job", process)
    settings = settings.model_copy(update={"background_poll_seconds": 0.001})
    with pytest.raises(asyncio.CancelledError):
        await ingestion_loop(object(), settings)
    assert recover.await_count == 2
    assert process.await_count == 1
