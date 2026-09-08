from __future__ import annotations

import json
import time

from fastapi import FastAPI
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import Settings


class VercelRequestLogMiddleware:
    """Emit bounded request metadata to managed runtime logs, including streamed failures."""

    def __init__(self, app: ASGIApp, *, service_name: str) -> None:
        self.app = app
        self.service_name = service_name

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") in {"/health/live", "/health/ready"}:
            await self.app(scope, receive, send)
            return
        start = time.monotonic()
        status = 500
        completed = False

        async def observe(message: Message) -> None:
            nonlocal status, completed
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                completed = True

        try:
            await self.app(scope, receive, observe)
        finally:
            # Use the registered route template, never URL/path parameters, query strings,
            # request headers, bodies, exception text, or generated model content.
            route = getattr(scope.get("route"), "path", "unmatched")
            print(
                json.dumps(
                    {
                        "event": "api_request",
                        "service": self.service_name,
                        "route": route,
                        "status": status,
                        "completed": completed,
                        "duration_ms": round((time.monotonic() - start) * 1000, 2),
                    },
                    separators=(",", ":"),
                ),
                flush=True,
            )


def configure_telemetry(app: FastAPI, settings: Settings) -> None:
    """Configure metadata-only OTLP tracing; regulated payloads stay in governed stores."""

    if settings.telemetry_backend == "vercel_logs":
        app.add_middleware(VercelRequestLogMiddleware, service_name=settings.otel_service_name)
        return
    if not settings.otel_exporter_otlp_endpoint:
        return
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": settings.otel_service_name,
                "service.version": settings.app_version,
                "deployment.environment.name": settings.app_env,
            }
        )
    )
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint))
    )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=provider,
        excluded_urls="health/live,health/ready",
    )
