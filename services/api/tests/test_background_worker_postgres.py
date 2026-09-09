"""Qualify scheduling/claims against real PostgreSQL, including rollout overlap."""

import asyncio
import os
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.background_worker import schedule_ingestion
from app.database import Database
from app.enums import JobStatus
from app.models import IngestionRun, ProcessingJob, utcnow
from app.worker import INGESTION_JOB_TYPES, _claim_next_job, recover_stale_worker_jobs

pytestmark = pytest.mark.skipif(
    os.getenv("AGENT_OS_POSTGRES_TEST") != "1",
    reason="requires isolated PostgreSQL migration CI service",
)


async def test_concurrent_schedulers_and_workers_share_one_ingestion_lane(settings):
    database = Database(os.environ["DATABASE_URL"])
    prefix = "railway-pg-" + uuid4().hex
    source = f"https://www.fda.gov/warning-letters/{prefix}"
    settings = settings.model_copy(
        update={
            "ingestion_schedule_enabled": True,
            "ingestion_worker_enabled": True,
            "fda_listing_url": source,
        }
    )
    try:
        admitted = await asyncio.gather(*(schedule_ingestion(database, settings) for _ in range(8)))
        assert len([run for run in admitted if run]) == 1
        async with database.session_factory() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(IngestionRun)
                    .where(
                        IngestionRun.source == source,
                    )
                )
                == 1
            )
            session.add_all(
                [
                    ProcessingJob(job_type=kind, idempotency_key=f"{prefix}:{kind}", payload={})
                    for kind in ["reconcile", "orchestrate_case_run"]
                ]
            )
            await session.commit()
        claims = await asyncio.gather(
            *(
                _claim_next_job(database, job_types=INGESTION_JOB_TYPES, single_active=True)
                for _ in range(6)
            )
        )
        claimed = [claim for claim in claims if claim]
        assert len(claimed) == 1
        async with database.session_factory() as session:
            job = await session.get(ProcessingJob, claimed[0].job_id)
            assert job.job_type == "discovery"
            job.available_at = utcnow() - timedelta(minutes=1)
            await session.commit()
        assert await recover_stale_worker_jobs(database, job_types=INGESTION_JOB_TYPES) == 1
        recovered = await _claim_next_job(
            database,
            job_types=INGESTION_JOB_TYPES,
            single_active=True,
        )
        assert recovered.job_id == claimed[0].job_id
        assert recovered.attempt_count == 2
        async with database.session_factory() as session:
            case = await session.scalar(
                select(ProcessingJob).where(
                    ProcessingJob.idempotency_key == f"{prefix}:orchestrate_case_run",
                )
            )
            assert case.status == JobStatus.PENDING.value
    finally:
        async with database.session_factory() as session:
            run_ids = select(IngestionRun.id).where(IngestionRun.source == source)
            await session.execute(
                delete(ProcessingJob).where(
                    ProcessingJob.ingestion_run_id.in_(run_ids)
                    | ProcessingJob.idempotency_key.startswith(prefix),
                )
            )
            await session.execute(delete(IngestionRun).where(IngestionRun.source == source))
            await session.commit()
        await database.dispose()
