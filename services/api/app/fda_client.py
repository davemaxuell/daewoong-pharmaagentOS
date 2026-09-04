from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass
from datetime import UTC
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import httpx

from app.config import Settings
from app.robots import RobotsDecision, RobotsPolicyCache
from app.security.urls import (
    canonicalize_redirect,
    resolve_and_validate_host,
    validate_source_url,
)


class FdaAcquisitionError(RuntimeError):
    pass


_SYSTEMIC_REASON_CODES = frozenset(
    {
        "dns_preflight_unavailable",
        "network_request_failed",
        "robots_policy_unavailable",
        "upstream_transient_status",
    }
)


class FdaSystemicAcquisitionError(FdaAcquisitionError):
    """A retryable FDA-origin or network outage that can affect every candidate."""

    def __init__(
        self,
        reason_code: str,
        message: str = "FDA acquisition is temporarily unavailable",
    ) -> None:
        self.reason_code = (
            reason_code
            if reason_code in _SYSTEMIC_REASON_CODES
            else "acquisition_unavailable"
        )
        super().__init__(message)


@dataclass(frozen=True)
class FetchedSource:
    requested_url: str
    final_url: str
    redirect_chain: list[str]
    content: bytes
    content_type: str
    status_code: int
    headers: dict[str, str]
    retrieved_monotonic: float


class FdaClient:
    """Bounded, allowlisted FDA acquisition client with manual redirect validation."""

    def __init__(
        self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.settings = settings
        self._transport = transport
        self.robots = RobotsPolicyCache(settings, transport)
        self._last_request_at = 0.0
        self._lock = asyncio.Lock()

    async def _resolve_host(self, hostname: str) -> None:
        try:
            await resolve_and_validate_host(hostname)
        except Exception as exc:
            raise FdaSystemicAcquisitionError("dns_preflight_unavailable") from exc

    async def _evaluate_robots(self, url: str) -> RobotsDecision:
        try:
            return await self.robots.evaluate(url)
        except Exception as exc:
            raise FdaSystemicAcquisitionError(
                "robots_policy_unavailable",
                "FDA robots policy could not be evaluated",
            ) from exc

    async def _respect_domain_delay(self, minimum_delay: float = 0.0) -> None:
        async with self._lock:
            elapsed = time.monotonic() - self._last_request_at
            configured = max(self.settings.fda_request_delay_seconds, minimum_delay)
            remaining = configured - elapsed
            if remaining > 0:
                await asyncio.sleep(remaining)
            self._last_request_at = time.monotonic()

    @staticmethod
    def _retry_after_seconds(value: str | None) -> float | None:
        if not value:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(value)
                from datetime import datetime

                return max(0.0, (parsed - datetime.now(UTC)).total_seconds())
            except (TypeError, ValueError, OverflowError):
                return None

    async def fetch(self, url: str) -> FetchedSource:
        validated = validate_source_url(url, self.settings.fda_allowed_hosts)
        if self._transport is None:
            await self._resolve_host(validated.hostname)
        policy = await self._evaluate_robots(validated.canonical_url)
        if not policy.allowed:
            raise FdaAcquisitionError("FDA robots policy disallows this source URL")
        current = validated.canonical_url
        redirects: list[str] = []
        headers = {
            "User-Agent": self.settings.fda_user_agent,
            "Accept": (
                "text/html,application/xhtml+xml,application/json,application/pdf;q=0.9,*/*;q=0.1"
            ),
        }
        timeout = httpx.Timeout(self.settings.fda_timeout_seconds)

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            transport=self._transport,
            headers=headers,
        ) as client:
            transient_attempt = 0
            while True:
                if self._transport is None:
                    hostname = urlsplit(current).hostname
                    if not hostname:
                        raise FdaAcquisitionError("FDA source hostname is missing")
                    await self._resolve_host(hostname)
                await self._respect_domain_delay(policy.crawl_delay_seconds)
                try:
                    async with client.stream("GET", current) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("location")
                            if not location:
                                raise FdaAcquisitionError("FDA redirect omitted Location")
                            if len(redirects) >= self.settings.fda_max_redirects:
                                raise FdaAcquisitionError("FDA redirect limit exceeded")
                            current = canonicalize_redirect(
                                current, location, self.settings.fda_allowed_hosts
                            )
                            if current in redirects:
                                raise FdaAcquisitionError("FDA redirect loop detected")
                            redirect_policy = await self._evaluate_robots(current)
                            if not redirect_policy.allowed:
                                raise FdaAcquisitionError(
                                    "FDA robots policy disallows redirected source URL"
                                )
                            policy = redirect_policy
                            redirects.append(current)
                            continue
                        if response.status_code in {408, 425, 429} or (
                            500 <= response.status_code <= 599
                        ):
                            if transient_attempt >= 3:
                                raise FdaSystemicAcquisitionError(
                                    "upstream_transient_status"
                                )
                            retry = self._retry_after_seconds(response.headers.get("retry-after"))
                            delay = (
                                retry
                                if retry is not None
                                else min(8.0, 2**transient_attempt + random.random())
                            )
                            transient_attempt += 1
                            await response.aread()
                            await asyncio.sleep(delay)
                            continue
                        if response.status_code >= 400:
                            raise FdaAcquisitionError(f"FDA returned status {response.status_code}")

                        content_type = response.headers.get("content-type", "").split(";", 1)[0]
                        allowed_types = {
                            "text/html",
                            "application/xhtml+xml",
                            "application/pdf",
                            "application/json",
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            "application/octet-stream",
                            "text/csv",
                        }
                        if content_type not in allowed_types:
                            raise FdaAcquisitionError("FDA returned an unsupported content type")
                        chunks: list[bytes] = []
                        size = 0
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > self.settings.fda_max_response_bytes:
                                raise FdaAcquisitionError(
                                    "FDA response exceeded configured size limit"
                                )
                            chunks.append(chunk)
                        content = b"".join(chunks)
                        if content_type == "application/pdf" and not content.startswith(b"%PDF-"):
                            raise FdaAcquisitionError("FDA PDF failed magic-byte validation")
                        return FetchedSource(
                            requested_url=validated.canonical_url,
                            final_url=current,
                            redirect_chain=redirects,
                            content=content,
                            content_type=content_type,
                            status_code=response.status_code,
                            headers={
                                key.lower(): value
                                for key, value in response.headers.items()
                                if key.lower() in {"etag", "last-modified", "content-type"}
                            },
                            retrieved_monotonic=time.monotonic(),
                        )
                except httpx.HTTPError as exc:
                    if transient_attempt >= 3:
                        raise FdaSystemicAcquisitionError("network_request_failed") from exc
                    await asyncio.sleep(min(8.0, 2**transient_attempt + random.random()))
                    transient_attempt += 1
        raise FdaAcquisitionError("FDA acquisition did not complete")
