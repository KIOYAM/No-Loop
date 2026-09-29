"""Resume text → fact ledger extraction service (LOOP-5; MASTER_SPEC §3).

Deterministic section/keyword heuristics with per-fact confidence. Every fact
is INFERRED — confirmation is the user's job (skill 03). Inferred facts are
never surfaced as truth by callers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.facts import FactProvenance, ResumeFact, SkillClaim

__all__ = ["ResumeParseOutcome", "parse_resume_text", "KNOWN_SKILLS"]

_SECTION_HEADINGS = {
    "summary": ("summary", "objective", "profile"),
    "skills": ("skills", "technical skills", "technologies"),
    "experience": ("experience", "employment", "work history", "professional experience"),
    "education": ("education", "academics"),
    "projects": ("projects",),
    "certifications": ("certifications", "certificates"),
}

_KNOWN_SKILLS = (
    "python",
    "java",
    "javascript",
    "typescript",
    "sql",
    "c++",
    "c#",
    "go",
    "rust",
    "fastapi",
    "django",
    "flask",
    "react",
    "angular",
    "vue",
    "node.js",
    "next.js",
    "docker",
    "kubernetes",
    "terraform",
    "aws",
    "azure",
    "gcp",
    "postgresql",
    "mysql",
    "mongodb",
    "redis",
    "kafka",
    "spark",
    "hadoop",
    "pandas",
    "numpy",
    "scikit-learn",
    "pytorch",
    "tensorflow",
    "keras",
    "huggingface",
    "langchain",
    "llm",
    "nlp",
    "machine learning",
    "deep learning",
    "generative ai",
    "mlops",
    "git",
    "linux",
    "rest api",
    "graphql",
    "microservices",
    "ci/cd",
    "jenkins",
    "selenium",
)

#: Public alias — shared vocabulary for AI-merged skill facts (taxonomy discipline).
KNOWN_SKILLS = _KNOWN_SKILLS

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?:\+91[-\s]?)?[6-9]\d{4}[-\s]?\d{5}")
_URL_RE = re.compile(r"https?://[^\s)>\]]+")
_EXP_RE = re.compile(r"(\d{1,2})\+?\s*years?\b", re.IGNORECASE)


@dataclass
class ResumeParseOutcome:
    """Structured parse output: facts + contact + detected sections + ambiguity report."""

    facts: list[ResumeFact]
    contact_email: str | None
    contact_phone: str | None
    links: list[str]
    detected_sections: list[str]
    ambiguities: list[str]
    text_chars: int

    @property
    def needs_confirmation_count(self) -> int:
        return sum(1 for f in self.facts if not f.is_confirmed)


def _split_sections(text: str) -> tuple[dict[str, str], list[str]]:
    """Split resume into sections by heading lines; returns sections + detected names."""
    sections: dict[str, str] = {}
    detected: list[str] = []
    current = "header"
    buffer: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        heading = None
        if line and len(line) < 60:
            normalized = line.lower().rstrip(":")
            for name, aliases in _SECTION_HEADINGS.items():
                if normalized in aliases:
                    heading = name
                    break
        if heading:
            sections[current] = "\n".join(buffer).strip()
            detected.append(heading)
            current = heading
            buffer = []
        else:
            buffer.append(raw)
    sections[current] = "\n".join(buffer).strip()
    return sections, detected


def _fact(
    profile_id: str, field_class: str, value: object, confidence: float, **prov: object
) -> ResumeFact:
    return ResumeFact(
        profile_id=profile_id,
        field_class=field_class,
        value=value,
        confidence=confidence,
        provenance=(
            FactProvenance.model_validate(prov) if prov else FactProvenance(user_entry=True)
        ),
    )


def parse_resume_text(
    profile_id: str, text: str, document_id: str | None = None
) -> ResumeParseOutcome:
    """Extract inferred facts from raw resume text. Pure function."""
    ambiguities: list[str] = []
    sections, detected = _split_sections(text)

    facts: list[ResumeFact] = []
    doc_id = document_id if document_id else "pasted-text"

    email = _EMAIL_RE.search(text)
    phone = _PHONE_RE.search(text)
    links = _URL_RE.findall(text)

    # Skills (section-first, fallback whole-text)
    skills_text = sections.get("skills", "")
    search_space = skills_text if skills_text else text
    found_skills: list[str] = []
    for skill in _KNOWN_SKILLS:
        pattern = r"\b" + re.escape(skill) + r"\b"
        if re.search(pattern, search_space, re.IGNORECASE):
            found_skills.append(skill)
    for skill in found_skills:
        level = None
        m = re.search(
            re.escape(skill) + r"\D{0,20}?(\d{1,2}\+?\s*years?)", search_space, re.IGNORECASE
        )
        if m:
            level = m.group(1)
        facts.append(
            ResumeFact(
                profile_id=profile_id,
                field_class="skill",
                skill=SkillClaim(name=skill, claimed_level=level),
                confidence=0.9 if skills_text else 0.6,
                provenance=FactProvenance(document_id=doc_id, extraction_rule="skills.keyword"),
            )
        )

    # Experience years (max claim found)
    years = [int(m.group(1)) for m in _EXP_RE.finditer(text) if 0 < int(m.group(1)) <= 40]
    if years:
        facts.append(
            ResumeFact(
                profile_id=profile_id,
                field_class="experience_years",
                value=max(years),
                confidence=0.7,
                provenance=FactProvenance(document_id=doc_id, extraction_rule="experience.regex"),
            )
        )
    else:
        ambiguities.append("Total experience not stated — onboarding question required")

    if not detected:
        ambiguities.append("No standard section headings detected — layout may be unusual")
    for required in ("skills", "experience", "education"):
        if required not in detected:
            ambiguities.append(f"Section '{required}' not found — confirm manually")

    return ResumeParseOutcome(
        facts=facts,
        contact_email=email.group(0) if email else None,
        contact_phone=phone.group(0) if phone else None,
        links=links,
        detected_sections=detected,
        ambiguities=ambiguities,
        text_chars=len(text),
    )
