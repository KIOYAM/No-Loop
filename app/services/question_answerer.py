"""Dynamic question answerer (user request: dynamic Q&A automation; S2/S4).

Answers application/screening questions STRICTLY from confirmed facts.
Classification is deterministic (Tier 0); when a BYOK provider is configured
it may *rephrase* an answer built from facts — it can never invent facts.
Unanswerable questions are flagged for the user with a reason, never guessed.
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass, field
from typing import Any

from app.domain.facts import ResumeFact
from app.domain.profile import CandidateProfile

__all__ = ["QuestionAnswer", "QuestionAnswerer", "build_fact_sheet"]

_YEARS_RE = re.compile(r"how many years|years of experience", re.I)
_RELOCATE_RE = re.compile(r"relocat", re.I)
_AUTHORIZATION_RE = re.compile(r"authorized|authorised|work permit|visa|right to work", re.I)
_SALARY_RE = re.compile(r"salary|compensation|pay expectations|expected pay|ctc", re.I)
_NOTICE_RE = re.compile(r"notice period|when can you start|availability|start date", re.I)
_REMOTE_RE = re.compile(r"remote|hybrid|onsite|work from office|wfo|wfh", re.I)
_SPONSOR_RE = re.compile(r"sponsor", re.I)
_YESNO_RE = re.compile(r"\?$", re.I)


@dataclass
class QuestionAnswer:
    question: str
    answer: str | None
    confidence: float
    source: str  # "profile" | "facts" | "needs_user"
    reason: str | None = None
    evidence_fact_ids: list[str] = field(default_factory=list)

    @property
    def needs_user(self) -> bool:
        return self.answer is None


def build_fact_sheet(facts: list[ResumeFact], profile: CandidateProfile) -> dict[str, Any]:
    """Aggregate confirmed facts into an answerable sheet (mirrors CLI payloads)."""
    skills: list[str] = []
    years: int | None = None
    for f in facts:
        if f.field_class == "skill" and f.skill:
            if f.skill.name.lower() not in [s.lower() for s in skills]:
                skills.append(f.skill.name)
        elif f.field_class == "experience_years" and years is None:
            with contextlib.suppress(TypeError, ValueError):
                years = int(f.value)
    sheet: dict[str, Any] = {
        "name": profile.contact_name or profile.name,
        "email": profile.contact_email,
        "phone": profile.contact_phone,
        "location": profile.location,
        "skills": skills,
        "experience_years": years,
        "salary_min": profile.targeting.min_salary if profile.targeting else None,
        "currency": profile.targeting.currency if profile.targeting else None,
        "notice_period_days": profile.targeting.notice_period_days if profile.targeting else None,
        "locations": list(profile.targeting.locations) if profile.targeting else [],
        "work_modes": sorted(m.value for m in profile.targeting.work_modes)
        if profile.targeting
        else [],
        "links": dict(profile.links),
    }
    return sheet


class QuestionAnswerer:
    """Deterministic Q&A over the fact sheet (Tier 0). Provider polish optional."""

    def __init__(self, fact_sheet: dict[str, Any]) -> None:
        self.sheet = fact_sheet

    def answer(self, question: str) -> QuestionAnswer:
        q = question.strip()
        low = q.lower()
        fact_ids: list[str] = []

        if _YEARS_RE.search(low):
            years = self.sheet.get("experience_years")
            if years:
                return QuestionAnswer(q, f"{years}+ years", 0.9, "facts", None, fact_ids)
            return QuestionAnswer(
                q, None, 0.0, "needs_user", "total experience not in confirmed facts"
            )

        if _RELOCATE_RE.search(low):
            locations = self.sheet.get("locations") or []
            if locations:
                return QuestionAnswer(
                    q, f"Open to: {', '.join(map(str, locations))}.", 0.8, "facts", None, fact_ids
                )
            return QuestionAnswer(
                q, None, 0.0, "needs_user", "relocation willingness not captured — ask user"
            )

        if _SPONSOR_RE.search(low):
            return QuestionAnswer(
                q,
                None,
                0.0,
                "needs_user",
                "visa sponsorship is a legal status — must be answered by user",
            )

        if _AUTHORIZATION_RE.search(low):
            return QuestionAnswer(
                q,
                None,
                0.0,
                "needs_user",
                "work authorization is a legal status — must be answered by user",
            )

        if _SALARY_RE.search(low):
            smin, cur = self.sheet.get("salary_min"), self.sheet.get("currency")
            if smin and cur:
                return QuestionAnswer(q, f"{cur} {smin}+", 0.85, "facts", None, fact_ids)
            return QuestionAnswer(
                q, None, 0.0, "needs_user", "salary expectation not set in targeting"
            )

        if _NOTICE_RE.search(low):
            days = self.sheet.get("notice_period_days")
            if days is not None:
                return QuestionAnswer(q, f"{days} days notice", 0.85, "facts", None, fact_ids)
            return QuestionAnswer(q, None, 0.0, "needs_user", "notice period not set in targeting")

        if _REMOTE_RE.search(low):
            modes = self.sheet.get("work_modes") or []
            if modes and "any" not in modes:
                return QuestionAnswer(
                    q, f"Preferred: {', '.join(modes)}.", 0.8, "facts", None, fact_ids
                )
            return QuestionAnswer(q, None, 0.0, "needs_user", "work-mode preference not set")

        # skills-ish questions
        if any(w in low for w in ("skill", "technolog", "stack", "language", "framework")):
            skills = self.sheet.get("skills") or []
            if skills:
                return QuestionAnswer(
                    q,
                    f"Core skills: {', '.join(map(str, skills[:8]))}.",
                    0.8,
                    "facts",
                    None,
                    fact_ids,
                )
            return QuestionAnswer(q, None, 0.0, "needs_user", "no confirmed skills yet")

        # anything else: honest fallback — no guessing (S2)
        return QuestionAnswer(
            q,
            None,
            0.0,
            "needs_user",
            "not answerable from confirmed facts without risk of"
            " fabrication — needs user input once",
        )
