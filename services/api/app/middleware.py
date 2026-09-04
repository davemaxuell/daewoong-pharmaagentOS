from __future__ import annotations

import re
import time
import uuid
from collections import defaultdict, deque

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,80}$")


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, max_request_bytes: int) -> None:
        super().__init__(app)
        self.max_request_bytes = max_request_bytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        supplied = request.headers.get("x-request-id", "")
        request_id = supplied if SAFE_REQUEST_ID.fullmatch(supplied) else str(uuid.uuid4())
        request.state.request_id = request_id
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                too_large = int(content_length) > self.max_request_bytes
            except ValueError:
                too_large = True
            if too_large:
                return JSONResponse(
                    {
                        "type": "about:blank",
                        "title": "Request body too large",
                        "status": 413,
                        "request_id": request_id,
                    },
                    status_code=413,
                    media_type="application/problem+json",
                    headers={"X-Request-ID": request_id},
                )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cache-Control"] = "no-store"
        return response


class InMemoryRateLimiter:
    """Per-process development limiter; production should use the shared gateway limit."""

    def __init__(self) -> None:
        self._entries: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, per_minute: int) -> None:
        now = time.monotonic()
        bucket = self._entries[key]
        while bucket and now - bucket[0] >= 60:
            bucket.popleft()
        if len(bucket) >= per_minute:
            retry_after = max(1, int(60 - (now - bucket[0])))
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)
