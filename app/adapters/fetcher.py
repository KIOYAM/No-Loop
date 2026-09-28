"""SSRF-guarded HTTP fetcher (SECURITY.md; CODING_STANDARDS §7.2).

Every external fetch in No_Loop goes through :func:`safe_get` — no raw
``httpx.get`` on user input, ever. Scheme allowlist, size cap, timeout cap,
redirect re-validation.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from app.domain.errors import SourceFetchError

__all__ = ["safe_get", "FetchOutcome", "MAX_RESPONSE_BYTES"]

MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB
_CONNECT_TIMEOUT = 10.0
_READ_TIMEOUT = 20.0
_MAX_REDIRECTS = 3
_UA = "No_Loop/0.1 (+local-first job assistant)"


@dataclass
class FetchOutcome:
    status_code: int
    body: bytes
    final_url: str


def _assert_public_host(host: str) -> None:
    """Reject private/loopback/link-local/metadata hosts (SSRF guard)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise SourceFetchError(
            stage="fetch.resolve", reason=f"DNS resolution failed: {host}"
        ) from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
            or str(ip) in {"169.254.169.254"}
        ):
            raise SourceFetchError(
                stage="fetch.resolve",
                reason="refusing to fetch private/reserved address",
                retryable=False,
            )


def _validate_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise SourceFetchError(
            stage="fetch.validate", reason=f"scheme not allowed: {parts.scheme}", retryable=False
        )
    if not parts.hostname:
        raise SourceFetchError(stage="fetch.validate", reason="URL has no host", retryable=False)
    _assert_public_host(parts.hostname)


async def safe_get(url: str, *, headers: dict[str, str] | None = None) -> FetchOutcome:
    """SSRF-guarded GET: allowlisted scheme, public host, bounded size/time.

    Redirects re-validated per hop.
    """
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        _validate_url(current)
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=_CONNECT_TIMEOUT,
                read=_READ_TIMEOUT,
                write=_READ_TIMEOUT,
                pool=_READ_TIMEOUT,
            ),
            follow_redirects=False,
            headers={"User-Agent": _UA, **(headers or {})},
        ) as client:
            try:
                response = await client.get(current)
            except httpx.HTTPError as exc:
                raise SourceFetchError(
                    stage="fetch.http", reason=f"network error: {exc.__class__.__name__}"
                ) from exc
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("location")
            if not location:
                raise SourceFetchError(
                    stage="fetch.http", reason="redirect without Location header", retryable=False
                )
            current = str(httpx.URL(response.url).join(location))
            continue
        if response.status_code >= 400:
            raise SourceFetchError(
                stage="fetch.http",
                reason=f"source returned HTTP {response.status_code}",
                retryable=response.status_code in (429, 500, 502, 503, 504),
            )
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise SourceFetchError(
                stage="fetch.size", reason="response exceeds 5 MB cap", retryable=False
            )
        return FetchOutcome(
            status_code=response.status_code, body=response.content, final_url=str(response.url)
        )
    raise SourceFetchError(
        stage="fetch.http", reason=f"too many redirects (> {_MAX_REDIRECTS})", retryable=False
    )
