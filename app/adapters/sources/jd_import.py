"""URL / JD import source (MASTER_SPEC §6: user-provided jobs).

Two modes:
- ``jd_text``: paste a job description → normalized Job (fully offline).
- fetch-from-URL: goes through the SSRF-guarded fetcher; parses <title> and
  visible text heuristically. Application surface = ASSISTED ONLY.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from selectolax.parser import HTMLParser

from app.domain.errors import ValidationError
from app.domain.jobs import Job, PolicyStatus, SourceRef
from app.ports import PolicyDeclaration

__all__ = ["JDImportAdapter"]

_SANITIZE_TAGS = {"script", "style", "iframe", "object", "embed", "nav", "header", "footer"}


def _html_to_text(html: str) -> str:
    tree = HTMLParser(html)
    for tag in _SANITIZE_TAGS:
        for node in tree.css(tag):
            node.decompose()
    body = tree.body
    text = body.text(separator="\n") if body else ""
    lines = (ln.strip() for ln in text.splitlines())
    return "\n".join(ln for ln in lines if ln)


class JDImportAdapter:
    adapter_id = "jd_import"

    def __init__(self) -> None:
        self.policy = PolicyDeclaration(
            discovery=True,
            parsing=True,
            application=False,
            email=False,
            policy_status=PolicyStatus.ASSISTED_ONLY,
            policy_source_url="user-provided content; no third-party automation",
            policy_reviewed_at="2026-09-28",
        )

    def from_text(self, *, title: str, company: str, jd_text: str, url: str | None = None) -> Job:
        """Paste-mode: user supplies the essentials; we normalize + sanitize."""
        title = title.strip()
        company = company.strip()
        if not title or not company:
            raise ValidationError(stage="jd_import.parse", reason="title and company are required")
        return Job(
            title=title[:200],
            company=company[:200],
            description_text=re.sub(r"\n{3,}", "\n\n", jd_text.strip())[:20000],
            work_mode="remote" if re.search(r"\bremote\b", jd_text, re.IGNORECASE) else "unknown",
            posted_at=datetime.now(UTC),
            source=SourceRef(kind="jd_import", adapter_id=self.adapter_id, url=url),
        )

    async def from_url(self, url: str) -> Job:
        """Fetch a job page (SSF-guarded) and extract title/text heuristically."""
        from app.adapters.fetcher import safe_get
        from app.domain.errors import SourceFetchError

        outcome = await safe_get(url)
        html = outcome.body.decode("utf-8", errors="replace")
        tree = HTMLParser(html)
        title_el = tree.css_first("title")
        title = (title_el.text(strip=True) if title_el else "").strip()
        h1 = tree.css_first("h1")
        if h1:
            title = h1.text(strip=True) or title
        if not title:
            raise SourceFetchError(
                stage="jd_import.parse",
                reason="page has no title/h1 to derive a job title",
                retryable=False,
            )
        text = _html_to_text(html)
        company = ""
        m = re.search(r"(?:at|@|Company[:\s]+)\s*([A-Z][\w&.\- ]{2,40})", text)
        if m:
            company = m.group(1).strip()
        if not company:
            # derive from hostname as last resort: careers.acme.com -> acme
            host = re.sub(r"^www\.", "", url.split("/")[2] if "://" in url else url)
            company = host.split(".")[-2] if "." in host else host
        return self.from_text(title=title, company=company, jd_text=text, url=url)
