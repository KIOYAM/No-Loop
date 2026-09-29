"""remotive source adapter (DATA_SOURCES.md §1.2).

POLICY_STATUS: ALLOWED_PUBLIC_API — public JSON feed of remote jobs, no key,
documented as free to use. Policy evidence:
https://remotive.com/remote-jobs/api (accessed 2026-09-28).
Discovery only; application happens via the assisted flow.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from selectolax.parser import HTMLParser

from app.adapters.fetcher import safe_get
from app.domain.jobs import Job, PolicyStatus, SourceRef
from app.ports import PolicyDeclaration

__all__ = ["RemotiveAdapter"]

_ENDPOINT = "https://remotive.com/api/remote-jobs"
_MAX_PAGES = 3  # bounded pagination (limit param does most of the work)
_PAGE_DELAY_S = 2.0
_SANITIZE_TAGS = {"script", "style", "iframe", "object", "embed", "link", "meta"}


def _sanitize_html_to_text(html: str) -> str:
    tree = HTMLParser(html)
    for tag in _SANITIZE_TAGS:
        for node in tree.css(tag):
            node.decompose()
    text = tree.body.text(separator="\n") if tree.body else ""
    lines = (line.strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


class RemotiveAdapter:
    """Public remote-jobs feed. One GET covers up to ~50 postings; bounded."""

    def __init__(self, *, page_delay_s: float = _PAGE_DELAY_S, max_pages: int = _MAX_PAGES) -> None:
        self.adapter_id = "remotive"
        self.policy = PolicyDeclaration(
            discovery=True,
            parsing=True,
            application=False,
            email=False,
            policy_status=PolicyStatus.ALLOWED_PUBLIC_API,
            policy_source_url="https://remotive.com/remote-jobs/api",
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
            posted = None
            ts = item.get("publication_date")
            if ts:
                try:
                    posted = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                    if posted.tzinfo is None:
                        posted = posted.replace(tzinfo=UTC)
                except ValueError:
                    posted = None
            # candidate_required_location: keep as-is; work_mode is remote by
            # definition on this board, location narrows who may apply.
            location = str(item.get("candidate_required_location") or "").strip() or None
            return Job(
                title=title[:200],
                company=company[:200],
                location=location,
                work_mode="remote",
                description_text=_sanitize_html_to_text(str(item.get("description", "")))[:20000],
                posted_at=posted,
                source=SourceRef(
                    kind="public_api",
                    adapter_id=self.adapter_id,
                    native_id=str(item.get("id")) or None,
                    url=url,
                ),
            )
        except Exception:  # noqa: BLE001 — single bad item must not kill the run
            return None

    async def discover(self, *, query: str | None = None, limit: int = 50) -> AsyncIterator[Job]:
        """Yield jobs from the feed. Client-side filter when a query is given."""
        yielded = 0
        for page in range(1, self._max_pages + 1):
            if yielded >= limit:
                return
            url = f"{_ENDPOINT}?limit={min(50, limit)}"
            if page > 1:
                url = f"{_ENDPOINT}?limit={min(50, limit)}&page={page}"
            outcome = await safe_get(url)
            try:
                payload = json.loads(outcome.body.decode("utf-8"))
                items: list[dict[str, Any]] = payload.get("jobs", [])
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
            if page < self._max_pages:
                await asyncio.sleep(self._delay)  # rate-limit respect (R-POLICY-4)
