from __future__ import annotations

import copy
from datetime import date

import pytest
from sqlalchemy import func, select

from app.cli import _requeue_partial_discovery
from app.config import Settings
from app.database import Database
from app.enums import JobStatus, RunStatus
from app.models import IngestionRun, ProcessingJob
from app.worker import _candidate_digest, _save_live_discovery_checkpoint


@pytest.mark.asyncio
async def test_cli_resume_copies_checkpoint_into_idempotent_new_audit_run(
    settings: Settings,
) -> None:
    source_url = "https://www.fda.gov/warning-letters/partial-cli-resume.csv"
    completed_hash = _candidate_digest(
        "https://www.fda.gov/warning-letters/already-completed"
    )
    failed_hash = _candidate_digest("https://www.fda.gov/warning-letters/retry-this-one")
    database = Database(settings.database_url)
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            source_run = IngestionRun(
                run_type="discovery",
                source=source_url,
                status=RunStatus.PARTIAL.value,
                requested_by="test",
                idempotency_key="cli-partial-source-run",
                parser_version="parser-v2-audit",
                scope_rule_version="drug-scope-v1-audit",
                metrics={"fetched": 1, "in_scope": 1, "failed": 1},
            )
            session.add(source_run)
            await session.flush()
            source_job = ProcessingJob(
                ingestion_run_id=source_run.id,
                job_type="discovery",
                status=JobStatus.SUCCEEDED.value,
                idempotency_key="cli-partial-source-job",
                payload={"source": source_url, "audit_marker": "preserve-me"},
                attempt_count=3,
                max_attempts=3,
            )
            _save_live_discovery_checkpoint(
                source_job,
                source_url=source_url,
                cutoff=date(2023, 8, 31),
                completed={completed_hash},
                failed={failed_hash},
                metrics={
                    "fetched": 1,
                    "in_scope": 1,
                    "out_of_scope": 0,
                    "ambiguous": 0,
                    "failed": 1,
                },
            )
            session.add(source_job)
            await session.commit()
            source_run_id = source_run.id
            source_job_id = source_job.id
            original_payload = copy.deepcopy(source_job.payload)

        first = await _requeue_partial_discovery(
            settings,
            run_id=source_run_id,
            retry_attempts=2,
        )
        assert first["state"] == "requeued"
        assert first["source_run_id"] == source_run_id
        assert first["source_job_id"] == source_job_id
        assert first["attempts_remaining"] == 2

        async with database.session_factory() as session:
            audited_run = await session.get(IngestionRun, source_run_id)
            audited_job = await session.get(ProcessingJob, source_job_id)
            resumed_run = await session.get(IngestionRun, str(first["run_id"]))
            resumed_job = await session.get(ProcessingJob, str(first["job_id"]))
            assert audited_run is not None
            assert audited_job is not None
            assert resumed_run is not None
            assert resumed_job is not None
            assert audited_run.status == RunStatus.PARTIAL.value
            assert audited_run.parser_version == "parser-v2-audit"
            assert audited_job.status == JobStatus.SUCCEEDED.value
            assert audited_job.payload == original_payload
            assert resumed_run.status == RunStatus.PENDING.value
            assert resumed_run.parser_version == settings.parser_version
            assert resumed_run.scope_rule_version == settings.drug_scope_rule_version
            assert resumed_job.status == JobStatus.PENDING.value
            assert resumed_job.attempt_count == 0
            assert resumed_job.max_attempts == 2
            assert resumed_job.payload["live_discovery_checkpoint"] == original_payload[
                "live_discovery_checkpoint"
            ]
            assert resumed_job.payload["resumed_from_run_id"] == source_run_id
            assert resumed_job.payload["resumed_from_job_id"] == source_job_id
            assert resumed_job.payload["resumed_from_parser_version"] == "parser-v2-audit"
            assert (
                resumed_job.payload["resumed_from_scope_rule_version"]
                == "drug-scope-v1-audit"
            )

        second = await _requeue_partial_discovery(
            settings,
            job_id=source_job_id,
            retry_attempts=9,
        )
        assert second["state"] == "already_created"
        assert second["run_id"] == first["run_id"]
        assert second["job_id"] == first["job_id"]
        assert second["attempts_remaining"] == 2

        async with database.session_factory() as session:
            assert await session.scalar(select(func.count(IngestionRun.id))) == 2
            assert await session.scalar(select(func.count(ProcessingJob.id))) == 2
    finally:
        await database.dispose()
