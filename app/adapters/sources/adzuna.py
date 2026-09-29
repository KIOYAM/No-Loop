"""adzuna source adapter — India-first jobs API (DATA_SOURCES.md §1.5).

POLICY_STATUS: USER_ACCOUNT_REQUIRED — free-tier API requires the user's own
``app_id``/``app_key`` (stored locally via SettingsStore, never hardcoded).
Policy evidence: https://www.adzuna.com/ (accessed 2026-09-28); quota is
verified per LOOP-12. Credentials come from the user's account; discovery
only, application via the assisted flow.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from app.adapters.fetcher import safe_get
from app.domain.errors import SourceFetchError
from app.domain.jobs import Job, PolicyStatus, SourceRef
from app.ports import PolicyDeclaration

__all__ = ["AdzunaAdapter"]

_BASE = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}.json"
_MAX_PAGE = 5  # API serves pages 1..N; keep bounded
_PAGE_DELAY_S = 2.0


class AdzunaAdapter:
    """Free-tier adzuna search. Requires the user's app_id/app_key (BYO-account)."""

    def __init__(
        self,
        *,
        app_id: str,
        app_key: str,
        country: str = "in",
        page_delay_s: float = _PAGE_DELAY_S,
    ) -> None:
        if not app_id or not app_key:
            raise SourceFetchError(
                stage="discovery.configure",
                reason="adzuna needs your free app_id/app_key (Settings → Sources)",
                user_action=(
                    "Create a free account at developer.adzuna.com and paste the "
                    "credentials in Settings → Sources. Until then use remotive/arbeitnow."
                ),
            )
        self.adapter_id = "adzuna"
        self.policy = PolicyDeclaration(
            discovery=True,
            parsing=True,
            application=False,
            email=False,
            policy_status=PolicyStatus.USER_ACCOUNT_REQUIRED,
            policy_source_url="https://www.adzuna.com/",
            policy_reviewed_at="2026-09-28",
        )
        self._app_id = app_id
        self._app_key = app_key
        self._country = country.lower()
        self._delay = page_delay_s

    def _normalize(self, item: dict[str, Any]) -> Job | None:
        try:
            title = str(item.get("title", "")).strip()
            company = str((item.get("company") or {}).get("display_name", "")).strip()
            url = str(item.get("redirect_url", "")).strip()
            if not title or not company or not url.startswith("http"):
                return None
            posted = None
            ts = item.get("created")
            if ts:
                try:
                    posted = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                    if posted.tzinfo is None:
                        posted = posted.replace(tzinfo=UTC)
                except ValueError:
                    posted = None
            loc = str((item.get("location") or {}).get("display_name", "")).strip() or None
            salary_min = item.get("salary_min")
            salary_max = item.get("salary_max")
            return Job(
                title=title[:200],
                company=company[:200],
                location=loc,
                work_mode="unknown",
                description_text=str(item.get("description", ""))[:20000],
                salary_min=int(salary_min) if isinstance(salary_min, (int, float)) else None,
                salary_max=int(salary_max) if isinstance(salary_max, (int, float)) else None,
                salary_currency="INR" if self._country == "in" else None,
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
        """Yield jobs page by page (results per page = max(10, limit//2), bounded)."""
        per_page = min(50, max(10, limit // 2 if limit >= 20 else limit))
        yielded = 0
        for page in range(1, _MAX_PAGE + 1):
            if yielded >= limit:
                return
            params = f"?app_id={self._app_id}&app_key={self._app_key}&results_per_page={per_page}"
            if query:
                params += f"&what={query}"
            url = _BASE.format(country=self._country, page=page) + params
            outcome = await safe_get(url)
            try:
                payload = json.loads(outcome.body.decode("utf-8"))
                items: list[dict[str, Any]] = payload.get("results", [])
            except (ValueError, AttributeError) as exc:
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
                yield job
                yielded += 1
                if yielded >= limit:
                    return
            if page < _MAX_PAGE:
                await asyncio.sleep(self._delay)  # rate-limit respect (R-POLICY-4)
