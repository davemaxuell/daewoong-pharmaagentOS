from __future__ import annotations

import ipaddress
import posixpath
import socket
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit


class UnsafeUrlError(ValueError):
    """Raised when a source URL violates the FDA acquisition policy."""


TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"fbclid", "gclid"}


def _normalized_host(hostname: str | None) -> str:
    if not hostname:
        raise UnsafeUrlError("URL hostname is missing")
    try:
        return hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise UnsafeUrlError("URL hostname is invalid") from exc


def canonicalize_fda_url(url: str, allowed_hosts: list[str]) -> str:
    if not isinstance(url, str) or len(url) > 4096:
        raise UnsafeUrlError("URL is missing or too long")
    parsed = urlsplit(url.strip())
    if parsed.scheme.lower() != "https":
        raise UnsafeUrlError("Only HTTPS FDA URLs are allowed")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("Credentials in source URLs are forbidden")
    host = _normalized_host(parsed.hostname)
    allowed = {_normalized_host(item) for item in allowed_hosts}
    if host not in allowed:
        raise UnsafeUrlError("Source hostname is not allowlisted")
    if parsed.port not in (None, 443):
        raise UnsafeUrlError("Non-standard source ports are forbidden")

    decoded_path = parsed.path or "/"
    if "\\" in decoded_path or "\x00" in decoded_path:
        raise UnsafeUrlError("URL path contains forbidden characters")
    normalized_path = posixpath.normpath(decoded_path)
    if not normalized_path.startswith("/"):
        normalized_path = "/" + normalized_path
    if decoded_path.endswith("/") and normalized_path != "/":
        normalized_path += "/"
    if normalized_path != "/":
        normalized_path = normalized_path.rstrip("/")

    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS
        and not key.lower().startswith(TRACKING_QUERY_PREFIXES)
    ]
    query = urlencode(sorted(query_items), doseq=True)
    return urlunsplit(("https", host, normalized_path, query, ""))


def canonicalize_redirect(current_url: str, location: str, allowed_hosts: list[str]) -> str:
    return canonicalize_fda_url(urljoin(current_url, location), allowed_hosts)


def validate_resolved_addresses(addresses: list[str]) -> None:
    if not addresses:
        raise UnsafeUrlError("Source hostname did not resolve")
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise UnsafeUrlError("DNS returned an invalid address") from exc
        if not ip.is_global:
            raise UnsafeUrlError("FDA source resolved to a non-public address")


async def resolve_and_validate_host(hostname: str, port: int = 443) -> list[str]:
    import asyncio

    def resolve() -> list[str]:
        records = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        return sorted({record[4][0] for record in records})

    addresses = await asyncio.to_thread(resolve)
    validate_resolved_addresses(addresses)
    return addresses


@dataclass(frozen=True)
class ValidatedSourceUrl:
    canonical_url: str
    hostname: str


def validate_source_url(url: str, allowed_hosts: list[str]) -> ValidatedSourceUrl:
    canonical = canonicalize_fda_url(url, allowed_hosts)
    return ValidatedSourceUrl(canonical, _normalized_host(urlsplit(canonical).hostname))
