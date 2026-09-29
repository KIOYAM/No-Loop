"""Employer intel from your own ledger (REFERENCE_GAP_ANALYSIS A6).

No external dataset, no scraping: the user's own application history IS the
dataset. Per company: how many applications, outcomes breakdown, average days
to first response, and user-authored notes. This is the No_Loop answer to
JobMatchAI's H1B lookup — built only on data the user already owns.
"""

from __future__ import annotations

import time
from collections import Counter
from typing import Any

__all__ = ["EmployerIntel"]


class EmployerIntel:
    def __init__(self, store: Any, ledger: Any) -> None:
        self._store = store
        self._ledger = ledger

    def company_report(self, company: str) -> dict[str, Any]:
        """Aggregate the user's history with one company."""
        wanted = company.strip().lower()
        if not wanted:
            return {"ok": False, "error": "company name is required"}
        apps = [a for a in self._ledger.all() if (a.company or "").strip().lower() == wanted]
        outcomes = Counter(a.status.value for a in apps)
        submitted = [a for a in apps if a.submission_evidence is not None]
        response_days: list[float] = []
        for a in apps:
            if (
                a.status.value in ("rejected", "interview", "offer")
                and a.updated_at
                and a.created_at
            ):
                delta = (a.updated_at - a.created_at).total_seconds() / 86400
                if 0 <= delta < 365:
                    response_days.append(round(delta, 1))
        interviews = outcomes.get("interview", 0) + outcomes.get("offer", 0)
        notes = [
            n
            for n in self._store.all("company_notes").values()
            if str(n.get("company", "")).strip().lower() == wanted
        ]
        notes.sort(key=lambda n: -(n.get("at") or 0))
        return {
            "ok": True,
            "company": company.strip(),
            "applications": len(apps),
            "outcomes": dict(outcomes),
            "submitted": len(submitted),
            "interviews": interviews,
            "interview_rate": round(interviews / len(apps), 4) if apps else None,
            "avg_days_to_response": (
                round(sum(response_days) / len(response_days), 1) if response_days else None
            ),
            "notes": notes[:20],
            "verdict": self._verdict(len(apps), interviews, outcomes),
        }

    @staticmethod
    def _verdict(apps: int, interviews: int, outcomes: Counter[str]) -> str:
        if apps == 0:
            return "no-history"
        if interviews == 0 and apps >= 5:
            return "cold — consider reworking resume/tailoring for this company"
        if interviews / apps >= 0.3:
            return "strong history — prioritize this company's postings"
        return "some traction"

    def top_companies(self, *, limit: int = 10) -> list[dict[str, Any]]:
        """Companies with the most activity — quick portfolio view."""
        counts = Counter((a.company or "").strip().title() for a in self._ledger.all() if a.company)
        return [{"company": c, "applications": n} for c, n in counts.most_common(limit)]

    def add_note(self, company: str, note: str) -> dict[str, Any]:
        """User-authored intel: 'recruiter ghosted after round 2', 'great WLB', etc."""
        company = company.strip()
        note = note.strip()
        if not company or not note:
            return {"ok": False, "error": "company and note are required"}
        note_id = f"{company.lower()}-{int(time.time())}"
        record = {
            "id": note_id,
            "company": company,
            "note": note[:2000],
            "at": time.time(),
        }
        self._store.upsert("company_notes", note_id, record)
        return {"ok": True, "id": note_id}
