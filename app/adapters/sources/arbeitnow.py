"""arbeitnow source adapter (LOOP-3; DATA_SOURCES.md §1.1).

POLICY_STATUS: ALLOWED_PUBLIC_API — public JSON job-board feed, no key.
Policy evidence: https://www.arbeitnow.com/blog/job-board-api (accessed 2026-09-28).
Discovery only; application on this adapter is the assisted flow.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC
from typing import Any

from selectolax.parser import HTMLParser

from app.adapters.fetcher import safe_get
from app.domain.jobs import Job, PolicyStatus, SourceRef
from app.ports import PolicyDeclaration

__all__ = ["ArbeitnowAdapter"]

_ENDPOINT = "https://www.arbeitnow.com/api/job-board-api"
_MAX_PAGES = 5  # bounded pagination per run (rate-limit respect)
_PAGE_DELAY_S = 2.0
_SANITIZE_TAGS = {"script", "style", "iframe", "object", "embed", "link", "meta"}


def _sanitize_html_to_text(html: str) -> str:
    """Strip dangerous tags, decode to text (SECURITY.md: fetched HTML is untrusted)."""
    tree = HTMLParser(html)
    for tag in _SANITIZE_TAGS:
        for node in tree.css(tag):
            node.decompose()
    text = tree.body.text(separator="\n") if tree.body else ""
    lines = (line.strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


class ArbeitnowAdapter:
    """Public job-board adapter. Async iterator, bounded pages, sanitized payloads."""

    def __init__(self, *, page_delay_s: float = _PAGE_DELAY_S, max_pages: int = _MAX_PAGES) -> None:
        self.adapter_id = "arbeitnow"
        self.policy = PolicyDeclaration(
            discovery=True,
            parsing=True,
            application=False,  # fill-only later, different surface; here discovery only
            email=False,
            policy_status=PolicyStatus.ALLOWED_PUBLIC_API,
            policy_source_url="https://www.arbeitnow.com/blog/job-board-api",
            policy_reviewed_at="2026-09-28",
        )
        self._delay = page_delay_s
        self._max_pages = max_pages

    def _normalize(self, item: dict[str, Any]) -> Job | None:
        try:
            title = str(item.get("title", "")).strip()
            company = str(item.get("company_name", "")).strip()
            url = str(item.get("url", "")).strip()
            if not title or not company or not url.startswith("http"):
                return None
            from datetime import datetime

            posted = None
            ts = item.get("created_at")
            if ts:
                try:
                    posted = datetime.fromtimestamp(int(ts), tz=UTC)
                except (TypeError, ValueError, OSError):
                    posted = None
            return Job(
                title=title[:200],
                company=company[:200],
                location=(str(item.get("location")).strip() or None)
                if item.get("location")
                else None,
                work_mode="remote" if item.get("remote") else "unknown",
                description_text=_sanitize_html_to_text(str(item.get("description", "")))[:20000],
                salary_min=item.get("salary_min"),
                salary_max=item.get("salary_max"),
                posted_at=posted,
                source=SourceRef(
                    kind="public_api",
                    adapter_id=self.adapter_id,
                    native_id=str(item.get("slug")) or None,
                    url=url,
                ),
            )
        except Exception:  # noqa: BLE001 — single bad item must not kill the run (source isolation)
            return None

    async def discover(self, *, query: str | None = None, limit: int = 50) -> AsyncIterator[Job]:
        """Yield jobs page by page. Stops at limit / max_pages / empty page."""
        yielded = 0
        page = 1
        url: str | None = _ENDPOINT
        while url and page <= self._max_pages and yielded < limit:
            outcome = await safe_get(url)
            try:
                payload = json.loads(outcome.body.decode("utf-8"))
                items: list[dict[str, Any]] = payload.get("data", [])
            except (ValueError, AttributeError) as exc:
                from app.domain.errors import SourceFetchError

                raise SourceFetchError(
                    stage="discovery.normalize",
                    reason=f"malformed payload: {exc.__class__.__name__}",
                ) from exc
            if not items:
                return
            for item in items:
                job = self._normalize(item)
                if job is None:
                    continue
                if query and query.lower() not in (job.title + " " + job.company).lower():
                    continue
                yield job
                yielded += 1
                if yielded >= limit:
                    return
            url = payload.get("links", {}).get("next")
            page += 1
            if url:
                await asyncio.sleep(self._delay)  # rate-limit respect (R-POLICY-4)
