"""Resume text → fact ledger extraction service (LOOP-5; MASTER_SPEC §3).

Deterministic section/keyword/record heuristics with per-fact confidence and
**per-fact provenance spans**. Every fact is INFERRED — confirmation is the
user's job (skill 03). Inferred facts are never surfaced as truth by callers.

What changed in the 2026-09 upgrade (see No_Loop_docs/RESUME_PROCESSING_UPGRADE.md):

- sections are detected fuzzily (typos, "Summary of Qualifications", "MY STORY");
- skills come from the open-vocabulary taxonomy with canonical normalisation
  and boundary-safe matching (``C++``/``C#`` used to be unmatchable);
- employment / education / dates / certifications / projects / achievements are
  extracted as facts, each with ``provenance.span``;
- the outcome carries a coverage report (13 spec groups) and a parseability
  report (what an ATS would make of this document).
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field
from typing import Any

from app.adapters import skill_taxonomy
from app.adapters.parseability import coverage_report, parseability_report
from app.adapters.resume_records import (
    extract_certifications,
    extract_education,
    extract_employment,
    extract_location,
    extract_name,
    extract_projects,
    find_date_ranges,
    tenure_years,
)
from app.adapters.resume_sections import SectionMap, split_sections
from app.domain.facts import FactProvenance, ResumeFact, SkillClaim

__all__ = ["ResumeParseOutcome", "parse_resume_text", "KNOWN_SKILLS"]

#: Shared vocabulary for AI-merged skill facts (taxonomy discipline).
KNOWN_SKILLS: tuple[str, ...] = skill_taxonomy.known_surface_names()

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?:\+91[-\s]?)?[6-9]\d{4}[-\s]?\d{5}")
_PHONE_CANDIDATE_RES: tuple[re.Pattern[str], ...] = (
    # +country code … (e.g. +34 612 34 56 78, +44 7700 900123, +1 (617) 555-0143)
    # separators are spaces/tabs only: a phone number must never swallow a newline
    re.compile(r"\+\d[\d \t().\-]{6,22}"),
    # bracketed area code: (617) 555-0143
    re.compile(r"\(\d{2,4}\)[ \t]*[\d \t.\-]{6,18}"),
    # separator style: 617-555-0143 / 617.555.0143
    re.compile(r"\b\d{3}[-.]\d{3}[-.]\d{4}\b"),
)
_URL_RE = re.compile(r"https?://[^\s)>\]]+")
#: Bare profile URLs (resumes rarely write https:// before linkedin.com/…)
_BARE_URL_RE = re.compile(
    r"\b(?:linkedin\.com|github\.com|gitlab\.com|behance\.net|dribbble\.com|"
    r"twitter\.com|x\.com|medium\.com|stackoverflow\.com|stackblitz\.com|"
    r"youtube\.com|angellist\.com|wellfound\.com|producthunt\.com|hashnode\.dev|"
    r"dev\.to|notion\.site|vercel\.app|netlify\.app|pages\.dev|"
    r"[a-z0-9-]+\.(?:com|dev|io|in|me|tech|ai|app)/[A-Za-z0-9_/.-]+)"
    r"[^\s|,;)\]>]*"
)
_EXP_RE = re.compile(r"(\d{1,2})\+?\s*years?\b", re.IGNORECASE)
#: … under CERTIFICATIONS & AWARDS means the line is an honour, not a credential
_AWARD_RE = re.compile(
    r"\b(?:award|awards|winner|won\b|scholarship|fellowship|scholar\b|rank\b|"
    r"medal|prize|honou?rs?\b|recogni[sz]ed|trophy)\b",
    re.IGNORECASE,
)

#: Confidence bands (1.0 is reserved for user-entered facts).
_CONF = {
    "email": 0.95,
    "phone": 0.9,
    "link": 0.85,
    "skill_section": 0.9,
    "skill_text": 0.6,
    "name": 0.72,
    "location": 0.72,
    "summary": 0.7,
    "title": 0.78,
    "employer": 0.78,
    "date_range": 0.75,
    "tenure": 0.75,
    "years_claim": 0.7,
    "degree": 0.72,
    "education": 0.7,
    "education_year": 0.65,
    "certification": 0.7,
    "project": 0.6,
    "achievement": 0.6,
    "language": 0.6,
}


@dataclass
class ResumeParseOutcome:
    """Structured parse output: facts + contact + structure + reports."""

    facts: list[ResumeFact]
    contact_email: str | None
    contact_phone: str | None
    links: list[str]
    detected_sections: list[str]
    ambiguities: list[str]
    text_chars: int
    coverage: dict[str, object] = field(default_factory=dict)
    parseability: dict[str, object] = field(default_factory=dict)
    structure: dict[str, object] = field(default_factory=dict)
    tenure: float | None = None

    @property
    def needs_confirmation_count(self) -> int:
        return sum(1 for f in self.facts if not f.is_confirmed)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _page_for(page_offsets: list[int] | None, position: int) -> int | None:
    """1-based page number for a character offset (when the extractor knew)."""
    if not page_offsets:
        return None
    index = bisect.bisect_right(page_offsets, position) - 1
    return max(1, index + 1)


class _Factory:
    """Builds provenance-complete facts and de-duplicates them."""

    def __init__(self, profile_id: str, document_id: str, page_offsets: list[int] | None):
        self.profile_id = profile_id
        self.document_id = document_id
        self.page_offsets = page_offsets
        self.facts: list[ResumeFact] = []
        self._seen: set[str] = set()

    def add(
        self,
        field_class: str,
        value: object,
        confidence: float,
        *,
        rule: str,
        span: tuple[int, int] | None = None,
        skill: SkillClaim | None = None,
        key: str | None = None,
    ) -> ResumeFact | None:
        dedupe_key = key if key is not None else _dedupe_key(field_class, value, skill)
        if dedupe_key in self._seen:
            return None
        if confidence >= 1.0:  # invariant: only user entry may be certain
            confidence = 0.95
        self._seen.add(dedupe_key)
        provenance = FactProvenance(
            document_id=self.document_id,
            extraction_rule=rule,
            span=span,
            page=_page_for(self.page_offsets, span[0]) if span else None,
        )
        fact = ResumeFact(
            profile_id=self.profile_id,
            field_class=field_class,
            value=value,
            confidence=round(confidence, 2),
            skill=skill,
            provenance=provenance,
        )
        self.facts.append(fact)
        return fact


def _dedupe_key(field_class: str, value: object, skill: SkillClaim | None) -> str:
    if skill is not None:
        return f"skill:{(skill.normalized_name or skill.name).lower()}"
    if isinstance(value, dict):
        return f"{field_class}:{value.get('raw') or value}"
    return f"{field_class}:{str(value).strip().lower()}"


def _section_span(sections: SectionMap, text: str, name: str) -> tuple[int, int]:
    section = sections.get(name)
    if section is not None:
        return section.body_start, section.end
    return 0, len(text)  # nothing recognised: scan the whole document


def _summary_fallback(text: str) -> tuple[int, str]:
    """First prose line under the header when no summary heading exists."""
    from app.adapters.resume_sections import iter_lines

    for _idx, start, _line_end, raw in iter_lines(text):
        line = raw.strip()
        if len(line) < 40:
            continue
        if "@" in line or "|" in line or "http" in line:
            continue  # contact/header line
        if line.startswith(("-", "•", "*", "▪", "‣")):
            continue  # a bullet is experience, not a summary
        if line.rstrip().endswith(":"):
            continue  # a label ("Core tools:") is not prose
        offset = start + raw.index(line)
        return offset, line
    return 0, ""


# ---------------------------------------------------------------------------
# the parser
# ---------------------------------------------------------------------------


def parse_resume_text(
    profile_id: str,
    text: str,
    document_id: str | None = None,
    *,
    page_offsets: list[int] | None = None,
) -> ResumeParseOutcome:
    """Extract inferred facts from raw resume text. Pure function."""
    ambiguities: list[str] = []
    sections = split_sections(text)
    detected = sections.detected()
    doc_id = document_id if document_id else "pasted-text"
    factory = _Factory(profile_id, doc_id, page_offsets)

    header_start, header_end = _section_span(sections, text, "header")

    # -- identity -----------------------------------------------------------
    name = extract_name(text, start=header_start, end=header_end)
    if name:
        factory.add("full_name", name[0], _CONF["name"], rule="identity.name", span=name[1])
    location = extract_location(text, start=header_start, end=header_end)
    if not location:  # summary often carries "City, Country"
        s_start, s_end = _section_span(sections, text, "summary")
        location = extract_location(text, start=s_start, end=s_end)
    if location:
        factory.add(
            "location", location[0], _CONF["location"], rule="identity.location", span=location[1]
        )

    # -- contact ------------------------------------------------------------
    email_match = _EMAIL_RE.search(text)
    phone_match = _PHONE_RE.search(text)
    if phone_match is None:
        phone_match = _international_phone(text)
    links = list(dict.fromkeys(_URL_RE.findall(text) + _BARE_URL_RE.findall(text)))

    if email_match:
        factory.add(
            "contact_email",
            email_match.group(0),
            _CONF["email"],
            rule="contact.email",
            span=(email_match.start(), email_match.end()),
        )
    else:
        ambiguities.append("No email address found — add one to your profile")
    if phone_match:
        phone_value = re.sub(r"[\s|,;.\-–—]+$", "", phone_match.group(0)).strip()
        factory.add(
            "contact_phone",
            phone_value,
            _CONF["phone"],
            rule="contact.phone",
            span=(phone_match.start(), phone_match.start() + len(phone_value)),
        )
    else:
        ambiguities.append("No phone number found — add one to your profile")
    for link in links:
        span_match = re.search(re.escape(link), text)
        factory.add(
            "link",
            link,
            _CONF["link"],
            rule="contact.link",
            span=(span_match.start(), span_match.end()) if span_match else None,
            key=f"link:{link}",
        )

    # -- summary ------------------------------------------------------------
    summary_section = sections.get("summary")
    summary_body = ""
    summary_offset = 0
    if summary_section is not None and summary_section.body.strip():
        summary_offset = summary_section.body_start
        summary_body = summary_section.body.strip()
    else:
        # no heading: fall back to the first prose line under the header block
        # (never the whole document — that would swallow the name + contacts)
        summary_offset, summary_body = _summary_fallback(text)
        if summary_section is None:
            ambiguities.append("Section 'summary' not found — confirm manually")
    if summary_body:
        first_para = summary_body.split("\n\n")[0].strip()
        if len(first_para) >= 40:
            factory.add(
                "summary",
                first_para[:600],
                _CONF["summary"],
                rule="section.summary" if summary_section is not None else "summary.fallback",
                span=(summary_offset, summary_offset + len(first_para)),
            )
    elif summary_section is None:
        pass  # ambiguity already recorded above
    else:
        ambiguities.append("Section 'summary' found but empty — confirm manually")

    # -- skills (open vocabulary, canonicalised) ----------------------------
    # Three passes, highest confidence first so the best provenance wins:
    #   1. the dedicated skills section (everything, incl. prose-word skills)
    #   2. the whole document (prose-safe: skips "go", "rust", "spark" …)
    #   3. comma-separated skill lists anywhere (re-admits prose-word skills)
    skills_section = sections.get("skills")
    from app.adapters.resume_sections import iter_lines

    def _add_hit(hit: Any, conf: float, rule_name: str) -> None:
        surface = text[hit.span[0] : hit.span[1]] or hit.canonical  # keep the user's casing
        claim = SkillClaim(name=surface, normalized_name=hit.canonical)
        factory.add(
            "skill",
            None,
            conf,
            rule=rule_name,
            span=hit.span,
            skill=claim,
            key=f"skill:{hit.canonical.lower()}",
        )

    if skills_section is not None and skills_section.body.strip():
        for hit in skill_taxonomy.extract_skills(
            skills_section.body, offset=skills_section.body_start, allow_ambiguous=True
        ):
            _add_hit(hit, _CONF["skill_section"], "skills.section")
    else:
        ambiguities.append("Section 'skills' not found — confirm manually")

    for hit in skill_taxonomy.extract_skills(text, offset=0, allow_ambiguous=False):
        _add_hit(hit, _CONF["skill_text"], "skills.whole_text")

    for _idx, start, _end, raw in iter_lines(text):
        if raw.count(",") < 1:
            continue
        line = raw.strip()
        if not line:
            continue
        line_offset = start + raw.index(line)
        hits = skill_taxonomy.extract_skills(line, offset=line_offset, allow_ambiguous=True)
        if len(hits) >= 2:
            for hit in hits:
                _add_hit(hit, _CONF["skill_text"], "skills.list_line")

    # -- experience: records, dates, tenure ---------------------------------
    exp_start, exp_end = _section_span(sections, text, "experience")
    employment = extract_employment(
        text,
        start=exp_start,
        end=exp_end,
        require_title=sections.get("experience") is None,
    )
    date_ranges = [record.dates for record in employment if record.dates]
    if not date_ranges:
        # whole-document fallback: ignore ranges inside the education section,
        # otherwise a student's "2020 - 2024" degree becomes 4 years of work
        edu_section = sections.get("education")
        for candidate in find_date_ranges(text):
            if (
                edu_section is not None
                and edu_section.body_start <= candidate.span[0] < edu_section.end
            ):
                continue
            date_ranges.append(candidate)

    for record in employment:
        if record.title:
            factory.add(
                "title",
                record.title,
                _CONF["title"] if record.dates else 0.62,
                rule="experience.title",
                span=record.spans.get("title"),
            )
        if record.employer:
            factory.add(
                "employer",
                record.employer,
                _CONF["employer"] if record.dates else 0.65,
                rule="experience.employer",
                span=record.spans.get("employer"),
            )
        if record.dates:
            factory.add(
                "date_range",
                record.dates.as_dict(),
                _CONF["date_range"],
                rule="experience.dates",
                span=record.dates.span,
                key=f"date_range:{record.dates.raw.strip().lower()}",
            )
        if record.location and not location:
            factory.add(
                "location",
                record.location,
                0.6,
                rule="experience.location",
                span=record.spans.get("location"),
            )

    if not employment:
        ambiguities.append("No employment history detected — confirm manually")

    # experience years: explicit claim wins, timeline-derived fills the gap
    years = [int(m.group(1)) for m in _EXP_RE.finditer(text) if 0 < int(m.group(1)) <= 40]
    tenure = tenure_years(date_ranges)
    if years:
        factory.add("experience_years", max(years), _CONF["years_claim"], rule="experience.regex")
    elif tenure:
        factory.add("experience_years", tenure, _CONF["tenure"], rule="experience.timeline")
    else:
        ambiguities.append("Total experience not stated — onboarding question required")

    # -- education ----------------------------------------------------------
    edu_start, edu_end = _section_span(sections, text, "education")
    education = extract_education(
        text,
        start=edu_start,
        end=edu_end,
        strict=sections.get("education") is None,
    )
    for education_record in education:
        if education_record.degree:
            factory.add(
                "degree",
                education_record.degree,
                _CONF["degree"],
                rule="education.degree",
                span=education_record.spans.get("degree"),
            )
        if education_record.institution:
            factory.add(
                "education",
                education_record.institution,
                _CONF["education"],
                rule="education.institution",
                span=education_record.spans.get("education"),
            )
        if education_record.year:
            factory.add(
                "education_year",
                int(education_record.year),
                _CONF["education_year"],
                rule="education.year",
            )
    if not education:
        ambiguities.append("Section 'education' not found — confirm manually")

    # -- certifications / projects / achievements / languages ---------------
    if sections.get("certifications") is None:
        # no dedicated section: still catch lines that clearly state a credential
        for value, span in extract_certifications(text, start=0, end=len(text), require_hint=True):
            factory.add(
                "certification",
                value,
                _CONF["certification"],
                rule="certifications.hint",
                span=span,
            )
    for section_name, field_class, rule, confidence in (
        ("certifications", "certification", "certifications.section", _CONF["certification"]),
        ("achievements", "achievement", "achievements.section", _CONF["achievement"]),
        ("projects", "project", "projects.section", _CONF["project"]),
        ("languages", "language", "languages.section", _CONF["language"]),
    ):
        section = sections.get(section_name)
        if section is None or not section.body.strip():
            continue
        if field_class == "certification":
            items = extract_certifications(text, start=section.body_start, end=section.end)
        elif field_class == "project":
            items = extract_projects(text, start=section.body_start, end=section.end)
        else:
            items = extract_projects(text, start=section.body_start, end=section.end, limit=10)
        for value, span in items:
            field_class_out, rule_out = field_class, rule
            if field_class_out == "certification" and _AWARD_RE.search(value):
                # "… Award for …" under CERTIFICATIONS & AWARDS is an award
                field_class_out, rule_out = "achievement", "achievements.award_line"
            factory.add(field_class_out, value, confidence, rule=rule_out, span=span)

    # -- ambiguity / coverage / parseability --------------------------------
    if not detected:
        ambiguities.append("No standard section headings detected — layout may be unusual")
    if sections.unrecognized:
        ambiguities.append(
            "Non-standard section headings detected: " + ", ".join(sections.unrecognized[:4])
        )

    field_classes = {f.field_class for f in factory.facts}
    coverage = coverage_report(field_classes)
    parseability = parseability_report(
        text,
        sections,
        ranges=date_ranges,
        employment=employment,
        has_email=bool(email_match),
        has_phone=bool(phone_match),
    )

    structure = {
        "sections": [
            {
                "name": section.name,
                "start": section.start,
                "body_start": section.body_start,
                "end": section.end,
                "confidence": section.confidence,
            }
            for section in sections.sections.values()
        ],
        "detected": detected,
        "unrecognized_headings": sections.unrecognized,
        "employment_records": len(employment),
        "education_records": len(education),
        "date_ranges": len(date_ranges),
        "tenure_years": tenure,
    }

    return ResumeParseOutcome(
        facts=factory.facts,
        contact_email=email_match.group(0) if email_match else None,
        contact_phone=phone_match.group(0) if phone_match else None,
        links=links,
        detected_sections=detected,
        ambiguities=ambiguities,
        text_chars=len(text),
        coverage=coverage,
        parseability=parseability,
        structure=structure,
        tenure=tenure,
    )


def _international_phone(text: str) -> re.Match[str] | None:
    """Non-Indian numbers: country code, brackets, or separator groups.

    The candidate patterns are deliberately loose; the digit count (10..15) is
    what makes them safe, plus a hard reject on anything that looks like a date
    or an identifier rather than a number.
    """
    for pattern in _PHONE_CANDIDATE_RES:
        for match in pattern.finditer(text):
            raw = match.group(0)
            digits = re.sub(r"\D", "", raw)
            if not 10 <= len(digits) <= 15:
                continue
            if re.search(r"\b(?:19|20)\d{2}[-/]\d{1,2}", raw):
                continue  # date fragment, not a number
            if raw.count("+") > 1:
                continue
            return match
    return None
