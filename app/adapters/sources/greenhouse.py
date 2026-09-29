"""Greenhouse public job-board adapter (REFERENCE_GAP_ANALYSIS C1; DATA_SOURCES policy).

POLICY_STATUS: ALLOWED_PUBLIC_API (discovery) / FILL-ONLY (application).
Greenhouse hosts public job boards (`boards-api.greenhouse.io`) and public
application forms — the candidate is the intended user of both. v0.1 contract:
we may PRE-FILL; the human clicks Submit (spec §11). Every fill is logged for
the field-reliability telemetry that gates v0.2 auto-submit.

Public endpoints (documented by Greenhouse, no key):
  boards-api.greenhouse.io/v1/boards/{token}/jobs
  boards-api.greenhouse.io/v1/boards/{token}/jobs/{id}?questions=true
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from app.adapters.fetcher import safe_get
from app.domain.errors import SourceFetchError
from app.domain.jobs import Job, PolicyStatus, SourceRef
from app.ports import PolicyDeclaration

__all__ = ["GreenhouseAdapter", "GREENHOUSE_FILL_POLICY_NOTE"]

GREENHOUSE_FILL_POLICY_NOTE = (
    "Public candidate application form: No_Loop may pre-FILL from confirmed facts; "
    "the human clicks Submit (v0.1 contract). Fill runs record field reliability."
)

_MAX_ITEMS = 100


class GreenhouseAdapter:
    """One board per company token. Discovery + question schema fetch."""

    def __init__(self, *, board_token: str) -> None:
        if not board_token or not board_token.strip():
            raise SourceFetchError(
                stage="discovery.configure",
                reason="greenhouse needs the company's board token "
                "(the slug in their careers URL, e.g. 'acme' in boards.greenhouse.io/acme)",
                user_action="Add the company's Greenhouse board token in Settings → Sources.",
            )
        self.adapter_id = "greenhouse"
        self.board_token = board_token.strip().lower()
        self.policy = PolicyDeclaration(
            discovery=True,
            parsing=True,
            application=False,  # fill-only later; submit stays human in v0.1
            email=False,
            policy_status=PolicyStatus.ALLOWED_PUBLIC_API,
            policy_source_url="https://developers.greenhouse.io/job-board.html",
            policy_reviewed_at="2026-09-30",
        )

    # -- discovery -----------------------------------------------------------
    def _normalize(self, item: dict[str, Any]) -> Job | None:
        try:
            title = str(item.get("title", "")).strip()
            url = str(item.get("absolute_url", "")).strip()
            if not title or not url.startswith("http"):
                return None
            company = str(item.get("company", {}).get("name") or self.board_token).strip()
            loc = item.get("location") or {}
            posted = None
            ts = item.get("updated_at") or item.get("first_published")
            if ts:
                try:
                    posted = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                    if posted.tzinfo is None:
                        posted = posted.replace(tzinfo=UTC)
                except ValueError:
                    posted = None
            return Job(
                title=title[:200],
                company=company[:200] or self.board_token,
                location=str(loc.get("name") or "").strip() or None,
                work_mode="remote" if "remote" in str(loc.get("name", "")).lower() else "unknown",
                description_text=str(item.get("content") or "")[:20000],
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
        url = f"https://boards-api.greenhouse.io/v1/boards/{self.board_token}/jobs"
        outcome = await safe_get(url)
        try:
            payload = json.loads(outcome.body.decode("utf-8"))
            items: list[dict[str, Any]] = payload.get("jobs", [])
        except (ValueError, AttributeError) as exc:
            raise SourceFetchError(
                stage="discovery.normalize",
                reason=f"malformed payload: {exc.__class__.__name__}",
            ) from exc
        yielded = 0
        for item in items[:_MAX_ITEMS]:
            job = self._normalize(item)
            if job is None:
                continue
            if query and query.lower() not in (job.title + " " + job.company).lower():
                continue
            yield job
            yielded += 1
            if yielded >= limit:
                return

    # -- application question schema (the fill-only input) --------------------
    async def fetch_questions(self, job_native_id: str) -> list[dict[str, Any]]:
        """Public questions for one job — the input to ATSFillPlanner."""
        url = (
            f"https://boards-api.greenhouse.io/v1/boards/{self.board_token}"
            f"/jobs/{job_native_id}?questions=true"
        )
        outcome = await safe_get(url)
        try:
            payload = json.loads(outcome.body.decode("utf-8"))
        except (ValueError, AttributeError) as exc:
            raise SourceFetchError(
                stage="ats.schema",
                reason=f"malformed payload: {exc.__class__.__name__}",
            ) from exc
        questions: list[dict[str, Any]] = []
        for q in payload.get("questions", []):
            questions.append(
                {
                    "id": q.get("id"),
                    "label": str(q.get("label") or "").strip(),
                    "type": str(q.get("type") or "short_text"),
                    "required": bool(q.get("required")),
                    "values": q.get("values") or [],
                }
            )
        return questions
