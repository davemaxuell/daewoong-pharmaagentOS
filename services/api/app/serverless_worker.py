"""Authenticated bounded queue consumers for Vercel Functions + Supabase Cron."""

from __future__ import annotations

import asyncio
import hmac
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import Settings, get_settings
from app.database import Database
from app.observability import configure_telemetry
from app.worker import process_next_job, recover_stale_worker_jobs

LANES = {
    "cases": ("orchestrate_case_run",),
    "ingestion": (
        "discovery",
        "reconcile",
        "lifecycle_sweep",
        "backfill",
        "lifecycle",
        "reprocess",
        "embed",
        "integrity_sample",
    ),
}


async def run_slice(database: Database, settings: Settings, lane: str) -> dict:
    recovered = 0
    completed = 0
    failed = 0
    yielded = False
    try:
        async with asyncio.timeout(settings.worker_slice_seconds):
            recovered = await recover_stale_worker_jobs(database)
            for _ in range(8):
                result = await process_next_job(
                    database, settings, job_types=LANES[lane], continuation_on_cancel=True
                )
                if result is None:
                    break
                completed += 1
                failed += result.status != "succeeded"
    except TimeoutError:
        yielded = True
    return {"processed": completed, "failed": failed, "recovered": recovered, "yielded": yielded}


def create_worker_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        base = get_settings()
        if not base.worker_database_url:
            raise ValueError("Worker service requires its separate WORKER_DATABASE_URL")
        settings = Settings(
            _env_file=None,
            **(
                base.model_dump()
                | {
                    "database_url": base.worker_database_url.get_secret_value(),
                    "otel_service_name": "pharma-vercel-worker",
                }
            ),
        )
    database = Database(settings.database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            await database.dispose()

    worker_app = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    worker_app.state.database = database
    worker_app.state.settings = settings
    worker_app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    configure_telemetry(worker_app, settings)

    @worker_app.post("/internal/worker/{lane}")
    async def tick(lane: str, request: Request):
        if not settings.serverless_worker_enabled:
            raise HTTPException(status_code=503, detail="Worker activation is disabled")
        secret = settings.worker_trigger_secret
        expected = f"Bearer {secret.get_secret_value()}" if secret else ""
        supplied = request.headers.get("authorization", "")
        if not expected or not hmac.compare_digest(supplied.encode(), expected.encode()):
            raise HTTPException(status_code=401, detail="Worker authentication required")
        if lane not in LANES:
            raise HTTPException(status_code=404, detail="Unknown worker lane")
        body = await request.body()
        try:
            empty_body = not body or json.loads(body) == {}
        except (ValueError, UnicodeDecodeError):
            empty_body = False
        if request.query_params or not empty_body:
            raise HTTPException(status_code=400, detail="Worker triggers take no caller payload")
        result = await run_slice(database, settings, lane)
        return JSONResponse(result, headers={"Cache-Control": "no-store"})

    return worker_app
