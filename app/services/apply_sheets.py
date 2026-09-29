"""ATS fill planning + platform answer sheets (REFERENCE_GAP_ANALYSIS P3/P4, Part B/C).

**P3 — Greenhouse/Lever (fill-only sweet spot):**
Greenhouse and Lever expose public job-board APIs that include the application
form schema (questions). Policy: public candidate forms — the candidate is
meant to fill them; v0.1 fills but the HUMAN clicks Submit (spec §11). Every
fill produces a field-reliability record — the telemetry that gates the v0.2
auto-submit decision.

**P4 — LinkedIn Easy-Apply / Naukri (PROHIBITED for bots — assisted only):**
An *answer sheet*: the standard question set pre-filled from the fact sheet
with copy-per-answer support. The user opens the site themselves and clicks
Submit. No browser automation against these platforms, ever (R-POLICY-3).
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from app.services.question_answerer import QuestionAnswerer, build_fact_sheet

__all__ = [
    "ATSFillPlanner",
    "build_answer_sheet",
    "EASY_APPLY_QUESTIONS",
    "NAUKRI_SHEET_FIELDS",
]

_FILLABLE_FIELD_KINDS = frozenset({"short_text", "long_text", "boolean", "select", "date"})


# ------------------------------------------------------------------- P3 ----
class ATSFillPlanner:
    """Plans fill-only runs on ATS portals from their public form schema.

    Usage flow:
      1. ``plan_from_questions`` — build the fill plan from a Greenhouse/Lever
         job's public questions list (fetched by the adapter).
      2. For each planned field, the UI/agent fills it from the fact sheet;
         every fill is recorded via ``record_fill``.
      3. ``reliability`` returns the aggregate the v0.2 decision consumes.
    """

    def __init__(self, facts: list[Any], profile: Any) -> None:
        self.sheet = build_fact_sheet(facts, profile)
        self.answerer = QuestionAnswerer(self.sheet)

    def plan_from_questions(
        self,
        *,
        platform: str,
        job_url: str,
        questions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        planned: list[dict[str, Any]] = []
        for q in questions:
            kind = str(q.get("type") or "short_text")
            if kind not in _FILLABLE_FIELD_KINDS:
                planned.append(
                    {
                        "field_id": q.get("id"),
                        "label": q.get("label") or q.get("question") or "",
                        "kind": kind,
                        "fillable": False,
                        "reason": "non-text field (file upload / custom) — human handles it",
                        "answer": None,
                    }
                )
                continue
            label = str(q.get("label") or q.get("question") or "")
            answer = self.answerer.answer(label)
            planned.append(
                {
                    "field_id": q.get("id"),
                    "label": label,
                    "kind": kind,
                    "required": bool(q.get("required")),
                    "fillable": not answer.needs_user,
                    "answer": answer.answer,
                    "needs_user": answer.needs_user,
                    "reason": answer.reason or "",
                    "source": answer.source,
                }
            )
        fillable = [p for p in planned if p["fillable"]]
        needs_user = [p for p in planned if not p["fillable"]]
        return {
            "id": uuid.uuid4().hex[:12],
            "platform": platform,
            "job_url": job_url,
            "fields": planned,
            "fillable_count": len(fillable),
            "needs_user_count": len(needs_user),
            "created_at": time.time(),
        }

    def record_fill(
        self,
        plan: dict[str, Any],
        *,
        field_id: Any,
        ok: bool,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Append a field-reliability record to the plan (persisted by the caller)."""
        plan.setdefault("fill_log", []).append(
            {
                "field_id": field_id,
                "ok": ok,
                "error": error,
                "at": time.time(),
            }
        )
        return plan

    @staticmethod
    def reliability(fill_log: list[dict[str, Any]]) -> dict[str, Any]:
        """Aggregate field reliability — the v0.2 auto-submit gate metric."""
        total = len(fill_log)
        ok = sum(1 for r in fill_log if r.get("ok"))
        rate = round(ok / total, 4) if total else None
        # Spec §11: auto-submit becomes discussable only with a proven fill
        # history; these thresholds are the documented gate.
        verdict = (
            "insufficient-data"
            if total < 50
            else ("candidate-for-v0.2" if rate and rate >= 0.98 else "not-reliable-enough")
        )
        return {"total_fills": total, "ok_fills": ok, "reliability": rate, "verdict": verdict}


# ------------------------------------------------------------------- P4 ----
#: The near-universal LinkedIn Easy-Apply question set.
EASY_APPLY_QUESTIONS: tuple[str, ...] = (
    "How many years of work experience do you have with the required skills?",
    "What is your expected salary?",
    "When can you start? / What is your notice period?",
    "Are you legally authorized to work in this location?",
    "How many years of experience do you have with Python?",  # placeholder skill slot
)

#: Naukri application-profile fields recruiters filter on.
NAUKRI_SHEET_FIELDS: tuple[str, ...] = (
    "Resume headline (one line, recruiter-search optimized)",
    "Key skills (top 10, comma separated)",
    "Total experience (years)",
    "Current salary (optional)",
    "Expected salary",
    "Notice period",
    "Preferred work location",
    "Highest qualification",
)


def build_answer_sheet(
    *,
    platform: str,
    facts: list[Any],
    profile: Any,
    job: Any = None,
) -> dict[str, Any]:
    """Assisted answer sheet for a PROHIBITED/ASSISTED platform (P4).

    Answers come ONLY from the confirmed fact sheet; anything not answerable
    is flagged needs_user with a reason (no guessing — R-POLICY-6).
    """
    sheet = build_fact_sheet(facts, profile)
    answerer = QuestionAnswerer(sheet)
    questions: tuple[str, ...] = (
        NAUKRI_SHEET_FIELDS if platform == "naukri" else EASY_APPLY_QUESTIONS
    )

    entries: list[dict[str, str]] = []
    for q in questions:
        # skill-slot question on Easy-Apply: substitute the JD's key skill when known
        effective = q
        job_desc = getattr(job, "description_text", None) if job is not None else None
        if job is not None and "Python?" in q and job_desc:
            from app.services.match_engine import _skills_from_job

            jd_skills = sorted(_skills_from_job(job))
            skill = jd_skills[0].title() if jd_skills else None
            effective = q.replace("Python", skill or "the required technology")
        answer = answerer.answer(effective)
        entries.append(
            {
                "question": effective,
                "answer": answer.answer or "— needs you —",
                "source": answer.source,
                "needs_user": "yes" if answer.needs_user else "no",
                "reason": answer.reason or "",
            }
        )
    filled = sum(1 for e in entries if e["needs_user"] == "no")
    return {
        "id": uuid.uuid4().hex[:12],
        "platform": platform,
        "job_id": getattr(job, "id", None) if job else None,
        "job_title": getattr(job, "title", None) if job else None,
        "company": getattr(job, "company", None) if job else None,
        "entries": entries,
        "filled": filled,
        "needs_user": len(entries) - filled,
        "created_at": time.time(),
    }
