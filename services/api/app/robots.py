from __future__ import annotations

import asyncio
import time
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.config import Settings
from app.security.urls import (
    canonicalize_redirect,
    resolve_and_validate_host,
    validate_source_url,
)


class RobotsPolicyError(RuntimeError):
    """Raised when the acquisition policy cannot safely authorize a source URL."""


@dataclass(frozen=True)
class RobotsDecision:
    allowed: bool
    crawl_delay_seconds: float
    robots_url: str
    fetched_at_monotonic: float
    from_cache: bool


@dataclass
class _CachedPolicy:
    parser: urllib.robotparser.RobotFileParser
    fetched_at_monotonic: float
    crawl_delay_seconds: float


class RobotsPolicyCache:
    """Small, bounded, per-origin robots.txt cache used by the FDA client.

    A policy fetch failure is fail-closed by default. A missing robots.txt (404/410)
    is treated as an empty policy, matching the robots protocol convention.
    """

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self._transport = transport
        self._cache: dict[str, _CachedPolicy] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    @staticmethod
    def _origin(url: str) -> str:
        parsed = urlsplit(url)
        return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))

    @staticmethod
    def _user_agent_token(user_agent: str) -> str:
        return user_agent.split(None, 1)[0].split("/", 1)[0] or "*"

    async def _download(self, robots_url: str) -> tuple[str, float]:
        validated = validate_source_url(robots_url, self.settings.fda_allowed_hosts)
        if self._transport is None:
            await resolve_and_validate_host(validated.hostname)
        current = validated.canonical_url
        timeout = httpx.Timeout(self.settings.fda_timeout_seconds)
        headers = {
            "User-Agent": self.settings.fda_user_agent,
            "Accept": "text/plain;q=1.0,*/*;q=0.1",
        }
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            transport=self._transport,
            headers=headers,
        ) as client:
            for _ in range(self.settings.fda_max_redirects + 1):
                if self._transport is None:
                    hostname = urlsplit(current).hostname
                    if not hostname:
                        raise RobotsPolicyError("FDA robots.txt hostname is missing")
                    await resolve_and_validate_host(hostname)
                try:
                    response = await client.get(current)
                except httpx.HTTPError as exc:
                    raise RobotsPolicyError("FDA robots.txt request failed") from exc
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise RobotsPolicyError("FDA robots.txt redirect omitted Location")
                    current = canonicalize_redirect(
                        current, location, self.settings.fda_allowed_hosts
                    )
                    continue
                if response.status_code in {404, 410}:
                    return "User-agent: *\nAllow: /\n", time.monotonic()
                if response.status_code != 200:
                    raise RobotsPolicyError(
                        f"FDA robots.txt returned status {response.status_code}"
                    )
                if len(response.content) > self.settings.fda_robots_max_response_bytes:
                    raise RobotsPolicyError("FDA robots.txt exceeded configured size limit")
                return response.content.decode("utf-8", errors="replace"), time.monotonic()
        raise RobotsPolicyError("FDA robots.txt redirect limit exceeded")

    async def evaluate(self, url: str) -> RobotsDecision:
        validated = validate_source_url(url, self.settings.fda_allowed_hosts)
        origin = self._origin(validated.canonical_url)
        robots_url = f"{origin}/robots.txt"
        now = time.monotonic()
        cached = self._cache.get(origin)
        if cached and now - cached.fetched_at_monotonic < self.settings.fda_robots_cache_seconds:
            return self._decision(cached, validated.canonical_url, robots_url, from_cache=True)

        lock = self._locks.setdefault(origin, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            cached = self._cache.get(origin)
            if (
                cached
                and now - cached.fetched_at_monotonic < self.settings.fda_robots_cache_seconds
            ):
                return self._decision(cached, validated.canonical_url, robots_url, from_cache=True)
            try:
                body, fetched_at = await self._download(robots_url)
                parser = urllib.robotparser.RobotFileParser(robots_url)
                parser.parse(body.splitlines())
                token = self._user_agent_token(self.settings.fda_user_agent)
                crawl_delay = parser.crawl_delay(token)
                if crawl_delay is None:
                    crawl_delay = parser.crawl_delay("*")
                policy = _CachedPolicy(parser, fetched_at, float(crawl_delay or 0.0))
                self._cache[origin] = policy
            except RobotsPolicyError:
                if self.settings.fda_robots_fail_closed:
                    raise
                parser = urllib.robotparser.RobotFileParser(robots_url)
                parser.parse(["User-agent: *", "Allow: /"])
                policy = _CachedPolicy(parser, time.monotonic(), 0.0)
                self._cache[origin] = policy
            return self._decision(policy, validated.canonical_url, robots_url, from_cache=False)

    def _decision(
        self,
        policy: _CachedPolicy,
        url: str,
        robots_url: str,
        *,
        from_cache: bool,
    ) -> RobotsDecision:
        token = self._user_agent_token(self.settings.fda_user_agent)
        return RobotsDecision(
            allowed=policy.parser.can_fetch(token, url),
            crawl_delay_seconds=policy.crawl_delay_seconds,
            robots_url=robots_url,
            fetched_at_monotonic=policy.fetched_at_monotonic,
            from_cache=from_cache,
        )

    def clear(self) -> None:
        self._cache.clear()
