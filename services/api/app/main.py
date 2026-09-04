from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.agent_platform.control_router import router as platform_control_router
from app.agent_platform.registry.router import router as workflow_registry_router
from app.agent_platform.runtime.router import router as runs_router
from app.ai import build_ai_generator
from app.approvals.router import router as approvals_router
from app.cases.router import router as cases_router
from app.config import Settings, get_settings
from app.database import Database
from app.embeddings import build_embedding_generator
from app.evaluation.router import router as evaluation_router
from app.integrations.a2a import router as a2a_router
from app.integrations.router import router as integrations_router
from app.internal_knowledge.router import router as internal_knowledge_router
from app.middleware import InMemoryRateLimiter, RequestContextMiddleware
from app.models import WarningLetter, utcnow
from app.notifications import ensure_default_email_subscription
from app.observability import configure_telemetry
from app.retention import retire_expired_letters
from app.routes.admin import router as admin_router
from app.routes.chat import router as chat_router
from app.routes.core import router as core_router
from app.routes.intelligence import router as intelligence_router
from app.security.secrets import build_secret_provider
from app.storage import build_object_store
from app.verification.router import router as verification_router
from app.worker import recover_interrupted_local_jobs, run_worker


def _problem(
    request: Request,
    *,
    status_code: int,
    title: str,
    detail: str | None = None,
    errors: list[dict[str, str]] | None = None,
) -> JSONResponse:
    body: dict[str, object] = {
        "type": "about:blank",
        "title": title,
        "status": status_code,
        "instance": request.url.path,
        "request_id": getattr(request.state, "request_id", "unavailable"),
    }
    if detail:
        body["detail"] = detail[:2_000]
    if errors:
        body["errors"] = errors
    return JSONResponse(body, status_code=status_code, media_type="application/problem+json")


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    database = Database(resolved.database_url)
    object_store = build_object_store(resolved)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        worker_task: asyncio.Task[int] | None = None
        await asyncio.to_thread(object_store.healthcheck)
        if resolved.database_url.startswith("sqlite"):
            from pathlib import Path

            database_path = resolved.database_url.partition("///")[2]
            if database_path and database_path != ":memory:":
                Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        if resolved.auto_create_schema:
            await database.create_schema()
        # Production API startup is intentionally read-safe. Subscription bootstrap,
        # retention and recovery belong to the durable worker/admin migration workflow, not
        # every horizontally scaled API replica.
        if resolved.app_env != "production":
            async with database.session_factory() as session:
                if resolved.embedded_worker_enabled:
                    await recover_interrupted_local_jobs(session)
                await ensure_default_email_subscription(session, resolved)
                await retire_expired_letters(
                    session,
                    resolved,
                    reference_date=utcnow().date(),
                )
                await session.commit()
        if resolved.embedded_worker_enabled and resolved.app_env != "production":
            worker_task = asyncio.create_task(
                run_worker(database, resolved, poll_seconds=2.0),
                name="local-durable-worker",
            )
            app.state.worker_task = worker_task
        try:
            yield
        finally:
            if worker_task:
                worker_task.cancel()
                with suppress(asyncio.CancelledError):
                    await worker_task
            await database.dispose()

    documentation_enabled = resolved.app_env != "production"
    app = FastAPI(
        title=resolved.app_name,
        version=resolved.app_version,
        docs_url="/docs" if documentation_enabled else None,
        redoc_url="/redoc" if documentation_enabled else None,
        openapi_url="/openapi.json" if documentation_enabled else None,
        lifespan=lifespan,
    )
    app.state.settings = resolved
    app.state.database = database
    app.state.object_store = object_store
    app.state.rate_limiter = InMemoryRateLimiter()
    app.state.ai_generator = build_ai_generator(resolved)
    app.state.embedding_generator = build_embedding_generator(resolved)
    app.state.secret_provider = build_secret_provider(resolved)
    configure_telemetry(app, resolved)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "X-Request-ID",
            "X-Dev-User",
            "X-Dev-Roles",
        ],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=resolved.allowed_hosts)
    app.add_middleware(RequestContextMiddleware, max_request_bytes=resolved.max_request_bytes)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        response = _problem(
            request,
            status_code=exc.status_code,
            title={
                400: "Bad request",
                401: "Unauthorized",
                403: "Forbidden",
                404: "Not found",
                409: "Conflict",
                413: "Payload too large",
                429: "Too many requests",
            }.get(exc.status_code, "Request failed"),
            detail=str(exc.detail),
        )
        response.headers.update(exc.headers or {})
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = [
            {
                "field": ".".join(str(part) for part in item["loc"]),
                "code": str(item["type"]),
                "message": str(item["msg"]),
            }
            for item in exc.errors()
        ]
        return _problem(
            request,
            status_code=422,
            title="Validation failed",
            detail="The request did not match the API contract",
            errors=errors,
        )

    app.include_router(core_router, prefix="/api/v1")
    app.include_router(intelligence_router, prefix="/api/v1")
    app.include_router(chat_router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")
    app.include_router(cases_router, prefix="/api/v1")
    app.include_router(approvals_router, prefix="/api/v1")
    app.include_router(runs_router, prefix="/api/v1")
    app.include_router(workflow_registry_router, prefix="/api/v1")
    app.include_router(internal_knowledge_router, prefix="/api/v1")
    app.include_router(verification_router, prefix="/api/v1")
    app.include_router(evaluation_router, prefix="/api/v1")
    app.include_router(platform_control_router, prefix="/api/v1")
    app.include_router(integrations_router, prefix="/api/v1")
    app.include_router(a2a_router)

    @app.get("/health/live", tags=["Health"], include_in_schema=True)
    async def root_live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["Health"], include_in_schema=True)
    async def root_ready() -> JSONResponse:
        checks = {"database": "ok", "object_store": "ok"}
        status_code = 200
        try:
            async with database.session_factory() as session:
                await session.execute(select(WarningLetter.id).limit(1))
        except Exception:
            checks["database"] = "schema_unavailable"
            status_code = 503
        try:
            await asyncio.to_thread(object_store.healthcheck)
        except Exception:
            checks["object_store"] = "unavailable"
            status_code = 503
        return JSONResponse(
            {"status": "ready" if status_code == 200 else "degraded", "checks": checks},
            status_code=status_code,
        )

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "service": resolved.app_name,
            "version": resolved.app_version,
            "health": "/api/v1/health/live",
        }

    return app


app = create_app()
