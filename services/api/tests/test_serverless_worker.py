import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import select

from app.config import Settings
from app.database import Database
from app.enums import JobStatus
from app.models import ProcessingJob
from app.serverless_worker import create_worker_app, run_slice
from app.worker import _claim_next_job

SECRET = "isolated-trigger-fixture-32-characters"


@pytest.mark.parametrize(
    ("path", "body", "authorization", "expected"),
    [
        ("cases", b"", None, 401),
        ("cases", b"", "Bearer incorrect", 401),
        ("cases", b"", f"Bearer {SECRET}", 200),
        ("ingestion", b"{}", f"Bearer {SECRET}", 200),
        ("other", b"{}", f"Bearer {SECRET}", 404),
        ("cases?job_id=arbitrary", b"{}", f"Bearer {SECRET}", 400),
        ("cases", b'{"job_id":"arbitrary"}', f"Bearer {SECRET}", 400),
        ("cases", b"[]", f"Bearer {SECRET}", 400),
        ("cases", b"false", f"Bearer {SECRET}", 400),
        ("cases", b"null", f"Bearer {SECRET}", 400),
        ("cases", b"invalid", f"Bearer {SECRET}", 400),
    ],
)
def test_trigger_auth_and_fixed_scope(settings, monkeypatch, path, body, authorization, expected):
    settings.serverless_worker_enabled = True
    settings.worker_trigger_secret = SecretStr(SECRET)
    execute = AsyncMock(return_value={"processed": 1})
    monkeypatch.setattr("app.serverless_worker.run_slice", execute)
    with TestClient(create_worker_app(settings)) as client:
        headers = {"Authorization": authorization} if authorization else {}
        response = client.post(f"/internal/worker/{path}", content=body, headers=headers)
    assert response.status_code == expected
    assert execute.await_count == int(expected == 200)
    if expected == 200:
        assert response.headers["cache-control"] == "no-store"


def test_worker_disabled_by_default(settings, monkeypatch):
    execute = AsyncMock()
    monkeypatch.setattr("app.serverless_worker.run_slice", execute)
    with TestClient(create_worker_app(settings)) as client:
        assert client.post("/internal/worker/cases").status_code == 503
        assert client.get("/docs").status_code == 404
    execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_claim_lane_cannot_take_another_lanes_job(settings):
    database = Database(settings.database_url)
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            session.add_all(
                [
                    ProcessingJob(job_type="discovery", idempotency_key="discovery"),
                    ProcessingJob(job_type="orchestrate_case_run", idempotency_key="case"),
                ]
            )
            await session.commit()
        claim = await _claim_next_job(database, job_types=("orchestrate_case_run",))
        assert claim is not None
        assert await _claim_next_job(database, job_types=("orchestrate_case_run",)) is None
        async with database.session_factory() as session:
            claimed = await session.get(ProcessingJob, claim.job_id)
            assert claimed.job_type == "orchestrate_case_run"
            ingestion = await session.scalar(
                select(ProcessingJob).where(ProcessingJob.job_type == "discovery")
            )
            assert ingestion.status == JobStatus.PENDING.value
    finally:
        await database.dispose()


@pytest.mark.parametrize(
    "overrides",
    [
        {"worker_trigger_secret": "too-short"},
        {"embedded_worker_enabled": True},
        {"temporal_enabled": True},
        {"worker_slice_seconds": 300},
    ],
)
def test_worker_configuration_fails_closed(overrides):
    values = {
        "serverless_worker_enabled": True,
        "worker_trigger_secret": SECRET,
        "embedded_worker_enabled": False,
    } | overrides
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


@pytest.mark.asyncio
async def test_slice_timeout_cancels_work_and_reports_yield(settings, monkeypatch):
    settings.worker_slice_seconds = 0.01
    cancelled = asyncio.Event()

    async def blocked_job(*args, **kwargs):
        assert kwargs["continuation_on_cancel"] is True
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr("app.serverless_worker.process_next_job", blocked_job)
    monkeypatch.setattr(
        "app.serverless_worker.recover_stale_worker_jobs", AsyncMock(return_value=2)
    )
    result = await run_slice(None, settings, "cases")
    assert result == {"processed": 0, "failed": 0, "recovered": 2, "yielded": True}
    assert cancelled.is_set()
