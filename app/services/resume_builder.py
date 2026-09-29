"""Resume assembly + ATS score (REFERENCE_GAP_ANALYSIS A3/A4/A5).

Builds a renderable resume document from CONFIRMED facts + selected Knowledge
Base entries. Anti-fabrication (R-POLICY-6): only confirmed facts and
user-asserted KB entries reach the document; the assembler never invents
bullet text — KB entries are quoted verbatim (the user wrote them).

``ats_score`` is TF-IDF cosine between the assembled resume text and the JD
text (A4) — a *text similarity* signal, reported alongside (not replacing)
the structured match engine.
"""

from __future__ import annotations

from typing import Any

from app.domain.facts import ResumeFact
from app.domain.knowledge import KBEntry, cosine_similarity, tfidf_rank, tokenize

__all__ = [
    "ResumeAssembler",
    "ats_score",
    "select_kb_entries",
]


def ats_score(resume_text: str, jd_text: str) -> float:
    """0.0-1.0 TF-IDF-style cosine between resume and JD text (A4)."""
    return round(cosine_similarity(tokenize(resume_text), tokenize(jd_text)), 4)


def select_kb_entries(
    entries: list[KBEntry], jd_text: str, *, top_k: int = 5
) -> list[tuple[KBEntry, float]]:
    """Rank KB entries against a JD (A1). Thin wrapper for clarity at call sites."""
    return tfidf_rank(entries, jd_text, top_k=top_k)


class ResumeAssembler:
    """Facts + KB + profile -> resume doc dict ready for the renderer."""

    def __init__(self, facts: list[ResumeFact], profile: Any) -> None:
        self._facts = [f for f in facts if f.state.value == "confirmed"]
        self._profile = profile

    # -- public -------------------------------------------------------------
    def build(
        self,
        *,
        jd_text: str = "",
        kb_entries: list[KBEntry] | None = None,
        max_bullets_per_role: int = 4,
    ) -> dict[str, Any]:
        """Assemble the resume doc. KB entries (when given) are selected by
        relevance to the JD and quoted verbatim as experience/project bullets."""
        skills = self._skills()
        experience = self._experience(max_bullets_per_role)
        projects = self._projects()
        education = self._education()
        certifications = self._certifications()

        selected: list[tuple[KBEntry, float]] = []
        if kb_entries and jd_text.strip():
            selected = select_kb_entries(kb_entries, jd_text)
        # route selected entries into the doc by kind
        for entry, _score in selected:
            if entry.kind.value in ("achievement", "story") and experience:
                experience[0].setdefault("bullets", [])
                experience[0]["bullets"].insert(0, entry.body)
            elif entry.kind.value == "project":
                projects.append({"title": entry.title, "bullets": [entry.body]})
            elif entry.kind.value == "certification":
                certifications.append(entry.body)

        contact = {
            "name": self._profile.contact_name or self._profile.name,
            "email": self._profile.contact_email,
            "phone": self._profile.contact_phone,
            "location": self._profile.location,
        }
        summary = (self._profile.extra or {}).get("summary") or None
        doc: dict[str, Any] = {
            "contact": contact,
            "skills": skills,
            "experience": experience,
            "education": education,
        }
        if summary:
            doc["summary"] = summary
        if projects:
            doc["projects"] = projects
        if certifications:
            doc["certifications"] = certifications
        return doc

    def resume_text(self, doc: dict[str, Any] | None = None) -> str:
        """Flat text of the assembled resume (for the ATS score)."""
        doc = doc or self.build()
        parts: list[str] = [doc["contact"]["name"] or ""]
        parts.append(str(doc.get("summary") or ""))
        parts.append(" ".join(doc.get("skills", [])))
        for exp in doc.get("experience", []):
            parts.append(f"{exp.get('role', '')} {exp.get('company', '')}")
            parts.extend(exp.get("bullets", []))
        for proj in doc.get("projects", []):
            parts.append(str(proj.get("title", "")))
            parts.extend(proj.get("bullets", []))
        for ed in doc.get("education", []):
            parts.append(f"{ed.get('degree', '')} {ed.get('school', '')}")
        parts.extend(doc.get("certifications", []))
        return "\n".join(p for p in parts if p)

    def tailoring_suggestions(
        self, jd_text: str, kb_entries: list[KBEntry] | None = None
    ) -> dict[str, Any]:
        """What to emphasize / what's missing (A3) — honest, no fabrication."""
        jd_tokens = set(tokenize(jd_text))
        resume_tokens = set(tokenize(self.resume_text(self.build())))
        missing = sorted(jd_tokens - resume_tokens)[:15]
        suggestions: list[str] = []
        if kb_entries:
            ranked = select_kb_entries(kb_entries, jd_text, top_k=3)
            for entry, score in ranked:
                suggestions.append(
                    f"Lead with KB entry '{entry.title}' "
                    f"(relevance {score:.0%}, kind {entry.kind.value})"
                )
        if missing:
            suggestions.append(
                "JD mentions terms absent from your confirmed facts: "
                + ", ".join(missing[:8])
                + " — do NOT claim them; add real evidence or address them in the cover note."
            )
        return {"missing_terms": missing, "suggestions": suggestions}

    # -- fact extraction helpers ---------------------------------------------
    def _skills(self) -> list[str]:
        out: list[str] = []
        for f in self._facts:
            if f.field_class == "skill" and f.skill:
                name = f.skill.name
                if name.lower() not in [s.lower() for s in out]:
                    out.append(name)
        return out

    def _experience(self, max_bullets: int) -> list[dict[str, Any]]:
        """Group employer/title/date facts into role entries (no invented bullets).

        Bullets come only from KB entries passed to build(); plain fact groups
        render as a one-line role so the document is honest about what we know.
        """
        roles: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for f in self._facts:
            fc = f.field_class
            if fc == "employer":
                if current is not None:
                    roles.append(current)
                current = {"role": "", "company": str(f.value), "period": "", "bullets": []}
            elif fc == "title" and current is not None:
                current["role"] = str(f.value)
            elif fc == "date_range" and current is not None:
                current["period"] = str(f.value)
            elif fc == "experience_bullet" and current is not None:
                if len(current["bullets"]) < max_bullets:
                    current["bullets"].append(str(f.value))
        if current is not None:
            roles.append(current)
        # fallback: experience_years only -> a single honest line
        if not roles:
            years = next(
                (str(f.value) for f in self._facts if f.field_class == "experience_years"), None
            )
            if years:
                roles.append(
                    {
                        "role": "Professional experience",
                        "company": "",
                        "period": f"{years} years",
                        "bullets": [],
                    }
                )
        return roles

    def _projects(self) -> list[dict[str, Any]]:
        return [
            {"title": str(f.value), "bullets": []}
            for f in self._facts
            if f.field_class == "project" and f.value
        ]

    def _education(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        school: str | None = None
        degree: str | None = None
        period: str | None = None
        for f in self._facts:
            if f.field_class == "education":
                school = str(f.value)
            elif f.field_class == "degree":
                degree = str(f.value)
            elif f.field_class == "education_period":
                period = str(f.value)
        if degree or school:
            out.append({"degree": degree or "", "school": school or "", "period": period or ""})
        return out

    def _certifications(self) -> list[str]:
        return [str(f.value) for f in self._facts if f.field_class == "certification" and f.value]
