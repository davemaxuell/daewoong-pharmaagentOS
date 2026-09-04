from __future__ import annotations

import httpx
import pytest

from app.config import Settings
from app.fda_client import FdaAcquisitionError, FdaClient, FdaSystemicAcquisitionError


@pytest.mark.asyncio
async def test_robots_policy_is_enforced_and_cached(tmp_path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                text="User-agent: *\nDisallow: /private\nCrawl-delay: 0\n",
                headers={"content-type": "text/plain"},
            )
        return httpx.Response(
            200,
            content=b"<html><main><p>FDA source</p></main></html>",
            headers={"content-type": "text/html"},
        )

    settings = Settings(
        app_env="test",
        object_store_path=tmp_path,
        fda_request_delay_seconds=0,
        fda_user_agent="TestFDAClient/1.0",
    )
    client = FdaClient(settings, httpx.MockTransport(handler))
    await client.fetch("https://www.fda.gov/warning-letters/allowed-one")
    await client.fetch("https://www.fda.gov/warning-letters/allowed-two")
    assert calls.count("/robots.txt") == 1
    with pytest.raises(FdaAcquisitionError, match="disallows"):
        await client.fetch("https://www.fda.gov/private/document")
    assert "/private/document" not in calls


@pytest.mark.asyncio
async def test_robots_failure_is_fail_closed(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, headers={"content-type": "text/plain"})

    settings = Settings(
        app_env="test",
        object_store_path=tmp_path,
        fda_request_delay_seconds=0,
    )
    client = FdaClient(settings, httpx.MockTransport(handler))
    with pytest.raises(FdaSystemicAcquisitionError, match="could not be evaluated") as caught:
        await client.fetch("https://www.fda.gov/warning-letters/example")
    assert caught.value.reason_code == "robots_policy_unavailable"


@pytest.mark.asyncio
async def test_dns_preflight_failure_is_classified_as_systemic(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fail_resolution(_hostname: str) -> list[str]:
        raise OSError("temporary resolver outage")

    monkeypatch.setattr("app.fda_client.resolve_and_validate_host", fail_resolution)
    settings = Settings(
        app_env="test",
        object_store_path=tmp_path,
        fda_request_delay_seconds=0,
    )
    client = FdaClient(settings)
    with pytest.raises(FdaSystemicAcquisitionError) as caught:
        await client.fetch("https://www.fda.gov/warning-letters/example")
    assert caught.value.reason_code == "dns_preflight_unavailable"
