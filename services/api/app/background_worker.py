"""Long-running ingestion and research consumers for container hosting.

Run separately from the API: python -m app.background_worker.
All work is saved in PostgreSQL; no HTTP trigger or local volume is required.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import signal
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.config import Settings, get_settings
from app.database import Database
from app.enums import JobStatus, RunStatus
from app.models import IngestionRun, ProcessingJob, ResearchRun, utcnow
from app.research.worker import run_research_slice
from app.storage import build_object_store
from app.worker import (
    INGESTION_CLAIM_LOCK,
    INGESTION_JOB_TYPES,
    process_next_job,
    recover_stale_worker_jobs,
)

logger = logging.getLogger("pharma.background")


def log_event(event: str, **fields: object) -> None:
    # Deliberately exclude exception messages, URLs with credentials, and document bodies.
    logger.info(json.dumps({"event": event, **fields}, separators=(",", ":")))


async def schedule_ingestion(
    database: Database,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> str | None:
    if not settings.ingestion_schedule_enabled:
        return None
    now = now or utcnow()
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    bucket = int(now.timestamp()) // (settings.ingestion_schedule_hours * 3600)
    source_key = hashlib.sha256(settings.fda_listing_url.encode()).hexdigest()[:16]
    key = f"scheduled-fda:v1:{source_key}:{settings.ingestion_schedule_hours}:{bucket}"
    async with database.session_factory() as session:
        if session.get_bind().dialect.name == "postgresql":
            await session.execute(select(func.pg_advisory_xact_lock(INGESTION_CLAIM_LOCK)))
        existing = await session.scalar(
            select(IngestionRun.id).where(
                IngestionRun.idempotency_key == key,
            )
        )
        active = await session.scalar(
            select(ProcessingJob.id)
            .where(
                ProcessingJob.job_type.in_(INGESTION_JOB_TYPES),
                ProcessingJob.status.in_([JobStatus.PENDING.value, JobStatus.RUNNING.value]),
            )
            .limit(1)
        )
        if existing or active:
            return None
        run = IngestionRun(
            run_type="discovery",
            source=settings.fda_listing_url,
            status=RunStatus.PENDING.value,
            requested_by="scheduled-fda-worker",
            idempotency_key=key,
            parser_version=settings.parser_version,
            scope_rule_version=settings.drug_scope_rule_version,
            metrics={},
        )
        try:
            session.add(run)
            await session.flush()
            session.add(
                ProcessingJob(
                    ingestion_run_id=run.id,
                    job_type="discovery",
                    status=JobStatus.PENDING.value,
                    idempotency_key=f"{key}:job",
                    payload={
                        "source": settings.fda_listing_url,
                        "refresh_before": (
                            now - timedelta(days=settings.ingestion_refresh_days)
                        ).isoformat(),
                    },
                )
            )
            await session.commit()
        except IntegrityError:
            await session.rollback()
            if await session.scalar(
                select(IngestionRun.id).where(
                    IngestionRun.idempotency_key == key,
                )
            ):
                return None
            raise
        log_event("fda_ingestion_scheduled", run_id=run.id)
        return run.id


async def ingestion_loop(database: Database, settings: Settings) -> None:
    while True:
        try:
            recovered = await recover_stale_worker_jobs(database, job_types=INGESTION_JOB_TYPES)
            if recovered:
                log_event("ingestion_jobs_recovered", count=recovered)
            await schedule_ingestion(database, settings)
            result = await process_next_job(
                database,
                settings,
                job_types=INGESTION_JOB_TYPES,
                single_active=True,
                continuation_on_cancel=True,
            )
            if result:
                log_event(
                    "ingestion_job_finished",
                    job_id=result.job_id,
                    status=result.status,
                    metrics=result.metrics,
                )
        except Exception as exc:
            log_event("ingestion_retry", error_type=type(exc).__name__)
        await asyncio.sleep(settings.background_poll_seconds)


async def research_loop(database: Database, settings: Settings) -> None:
    while True:
        try:
            result = await run_research_slice(database, settings)
            if result.get("processed"):
                log_event("research_worker_finished", **result)
        except Exception as exc:
            log_event("research_retry", error_type=type(exc).__name__)
        await asyncio.sleep(settings.background_poll_seconds)


async def run_background_worker(settings: Settings, *, stop: asyncio.Event | None = None) -> None:
    if not (settings.ingestion_worker_enabled or settings.research_agent_enabled):
        raise ValueError("Enable an ingestion or research lane before starting the worker")
    if settings.smtp_enabled:
        raise ValueError("This worker profile does not enable external notification delivery")
    if settings.research_agent_enabled and settings.llm_provider != "openai":
        raise ValueError("The research lane requires the configured OpenAI provider")
    if settings.app_env == "production" and not settings.worker_database_url:
        raise ValueError("The production worker requires its separate WORKER_DATABASE_URL")
    database = Database(
        settings.worker_database_url.get_secret_value()
        if settings.worker_database_url
        else settings.database_url
    )
    tasks: list[asyncio.Task] = []
    stop = stop or asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(name, stop.set)
        except NotImplementedError:  # Windows local qualification; Linux uses native signals.
            pass
    try:
        await asyncio.to_thread(build_object_store(settings).healthcheck)
        async with database.session_factory() as session:
            await session.execute(select(ProcessingJob.id).limit(1))
            if settings.research_agent_enabled:
                await session.execute(select(ResearchRun.id).limit(1))
        if settings.ingestion_worker_enabled:
            tasks.append(asyncio.create_task(ingestion_loop(database, settings)))
        if settings.research_agent_enabled:
            tasks.append(asyncio.create_task(research_loop(database, settings)))
        log_event(
            "background_worker_started",
            ingestion=settings.ingestion_worker_enabled,
            research=settings.research_agent_enabled,
        )
        await stop.wait()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await database.dispose()
        log_event("background_worker_stopped")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(run_background_worker(get_settings()))


if __name__ == "__main__":
    main()
