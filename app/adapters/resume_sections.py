"""Section segmentation — heading detection that survives real-world resumes.

The old splitter required an *exact* alias match on a line shorter than 60
characters, so "WORK EXPERENCE" (typo), "Work Experience", "Summary of
Qualifications" or "My Professional Journey" all fell through to "no standard
section headings detected — layout may be unusual" and the whole document was
scanned as one blob.

This module keeps the same contract (a ``name → body`` mapping plus the
detected order) but decides headings with:

1. decoration stripping (``== Skills ==``, ``# Education``, ``3. Projects``),
2. exact alias match (confidence 1.0),
3. fuzzy match (RapidFuzz, already a dependency) **with a remainder rule**: the
   text left over after removing the alias may only contain linking words
   ("of", "the", "&", "qualifications" …) — so "Summary of Qualifications"
   matches while "Experience working with children" does not,
4. structural guards: a heading stands alone in its paragraph, is never a
   bullet line (unless exact) and never ends a sentence.

Every section carries ``start``/``body_start``/``end`` character spans so facts
can record ``provenance.span`` (the schema always had it; nothing set it).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from rapidfuzz import fuzz

__all__ = ["Section", "SectionMap", "split_sections", "iter_lines", "normalize_heading"]

#: canonical section → accepted surface headings.
SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "summary": (
        "summary",
        "objective",
        "profile",
        "professional summary",
        "personal summary",
        "career summary",
        "career objective",
        "about me",
        "about",
        "summary of qualifications",
        "qualifications summary",
        "professional profile",
        "personal profile",
        "overview",
        # ES/PT surfaces (full multilingual is P3; headings are cheap)
        "resumen",
        "resumen profesional",
        "perfil profesional",
    ),
    "skills": (
        "skills",
        "technical skills",
        "technologies",
        "tech stack",
        "skills & tools",
        "skills and tools",
        "core competencies",
        "competencies",
        "technical competencies",
        "areas of expertise",
        "expertise",
        "technicals",
        "technology skills",
        "programming skills",
        "key skills",
        "habilidades",
        "habilidades tecnicas",
        "habilidades técnicas",
        "competencias técnicas",
    ),
    "experience": (
        "experience",
        "employment",
        "work history",
        "professional experience",
        "work experience",
        "employment history",
        "career history",
        "professional history",
        "work background",
        "professional background",
        "employment record",
        "relevant experience",
        "my experience",
        "professional journey",
        "career trajectory",
        "experiencia",
        "experiencia laboral",
        "experiencia profesional",
        "histórico laboral",
    ),
    "education": (
        "education",
        "academics",
        "academic background",
        "educational qualification",
        "educational qualifications",
        "education & training",
        "education and training",
        "academic qualifications",
        "qualifications",
        "formación",
        "formacion",
        "formación académica",
        "educación",
        "educacion",
        "estudios",
    ),
    "projects": (
        "projects",
        "personal projects",
        "key projects",
        "academic projects",
        "selected projects",
        "project experience",
        "portfolio",
        "proyectos",
    ),
    "certifications": (
        "certifications",
        "certificates",
        "certifications & awards",
        "licenses",
        "licenses & certifications",
        "professional certifications",
        "courses",
        "certificaciones",
        "certificados",
    ),
    "achievements": (
        "achievements",
        "awards",
        "honors",
        "honours",
        "awards & achievements",
        "accomplishments",
        "recognition",
    ),
    "languages": ("languages", "spoken languages", "language skills"),
    "links": ("links", "online presence", "social profiles", "find me online"),
    "volunteering": (
        "volunteering",
        "volunteer experience",
        "volunteer work",
        "community involvement",
    ),
}

#: Reverse index: alias (lower) → canonical name.
_ALIAS_TO_NAME: dict[str, str] = {
    alias.lower(): name for name, aliases in SECTION_ALIASES.items() for alias in aliases
}

#: Tokens allowed to remain around a matched alias ("Summary of Qualifications").
_REMAINDER_OK = frozenset(
    {
        "of",
        "the",
        "and",
        "a",
        "an",
        "in",
        "for",
        "my",
        "our",
        "&",
        "+",
        "plus",
        "section",
        "details",
        "background",
        "history",
        "qualifications",
        "qualification",
        "competency",
        "competencies",
        "summary",
        "profile",
        "overview",
        "record",
        "records",
        "list",
        "key",
        "relevant",
        "professional",
        "personal",
        "technical",
        "technologies",
        "skills",
        "experience",
        "education",
        "achievements",
        "awards",
        "training",
        "tools",
        "toolbox",
        "work",
        "works",
        "job",
        "jobs",
        "role",
        "roles",
        "position",
        "positions",
        "employment",
        "career",
        "careers",
        "past",
        "prior",
        "previous",
        "current",
        "timeline",
        "selected",
        "notable",
        "related",
        "other",
        "extra",
        "additional",
        "volunteer",
        "academic",
        "industry",
    }
)

#: Fuzzy acceptance thresholds: approximate containment + remainder rule.
_CONTAIN_MIN = 85

_HEADING_MAX_RAW = 72
_HEADING_MAX_NORM = 60
_BULLET_PREFIX = ("-", "•", "*", "▪", "‣", ">", "›", "»", "●")
_SENTENCE_END = (".", "?", "!")


@dataclass(frozen=True)
class Section:
    """One resume section with character spans into the source text."""

    name: str
    heading: str
    start: int  # offset of the heading line
    body_start: int  # offset where the body begins
    end: int  # offset where the body ends (exclusive)
    body: str
    confidence: float
    duplicate: bool = False

    @property
    def span(self) -> tuple[int, int]:
        return (self.start, self.end)


@dataclass
class SectionMap:
    """Result of :func:`split_sections`."""

    sections: dict[str, Section] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    unrecognized: list[str] = field(default_factory=list)
    raw_headings: list[tuple[str, int]] = field(default_factory=list)  # (heading, offset)

    def body(self, name: str) -> str:
        section = self.sections.get(name)
        return section.body if section else ""

    def detected(self) -> list[str]:
        """Heading-derived sections in document order (the ``header`` prefix excluded)."""
        return [name for name in self.order if name != "header"]

    def get(self, name: str) -> Section | None:
        return self.sections.get(name)


def iter_lines(text: str) -> Iterator[tuple[int, int, int, str]]:
    """Yield ``(index, start, end, line)`` with exact character offsets."""
    index = 0
    i = 0
    n = len(text)
    while i < n:
        j = i
        while j < n and text[j] not in "\r\n":
            j += 1
        yield index, i, j, text[i:j]
        index += 1
        if j >= n:
            break
        i = j + 2 if text[j] == "\r" and j + 1 < n and text[j + 1] == "\n" else j + 1


def normalize_heading(line: str) -> str:
    """Strip decoration from a candidate heading line."""
    s = line.strip()
    s = re.sub(r"^[#*=\-–—•‣▪●○»›>]+\s*", "", s)  # leading markers
    s = re.sub(r"^\d{1,2}[.)]\s*", "", s)  # numbered headings ("3. Projects")
    s = re.sub(r"^[=*~_\-–—•#]+$", "", s)  # a line that is pure decoration
    s = s.strip()
    s = re.sub(r"[=*~_\-–—•#]+$", "", s).strip()  # trailing rules/decoration
    s = s.rstrip(":：").strip()
    s = re.sub(r"\s{2,}", " ", s)
    s = s.strip(" \t-–—=*~_#")
    return s


def _is_candidate(raw: str) -> bool:
    stripped = raw.strip()
    if not stripped or len(stripped) > _HEADING_MAX_RAW:
        return False
    norm = normalize_heading(stripped)
    if not norm or len(norm) > _HEADING_MAX_NORM:
        return False
    if "@" in norm or "http" in norm.lower():
        return False
    if norm.endswith(_SENTENCE_END):
        return False
    if len(norm.split()) > 7:
        return False
    return sum(ch.isdigit() for ch in norm) <= 2


def _exact(norm: str) -> str | None:
    return _ALIAS_TO_NAME.get(norm.lower())


def _fuzzy(norm: str) -> str | None:
    """Accept a fuzzy heading only when the leftover words are linking words.

    Uses approximate *containment* (partial alignment) rather than whole-line
    similarity so "WORK EXPERENCE" (typo) still matches "experience", while the
    remainder rule keeps prose sentences ("Experience working with children")
    out of the heading set.
    """
    text = norm.lower()
    best: tuple[float, str] | None = None
    for alias, name in _ALIAS_TO_NAME.items():
        if text == alias:
            return name
        alignment = fuzz.partial_ratio_alignment(text, alias)
        if alignment is None or alignment.score < _CONTAIN_MIN:
            continue
        leftover = text[: alignment.src_start] + " " + text[alignment.src_end :]
        tokens = re.findall(r"[a-z0-9]+|&", leftover)
        if any(token not in _REMAINDER_OK for token in tokens):
            continue  # "Experience working with children" is not a heading
        if best is None or alignment.score > best[0]:
            best = (float(alignment.score), name)
    return best[1] if best else None


def _standalone(lines: list[str], index: int) -> bool:
    prev_blank = index == 0 or not lines[index - 1].strip()
    next_blank = index == len(lines) - 1 or not lines[index + 1].strip()
    return prev_blank or next_blank


def _unknown_heading(stripped: str, index: int, lines: list[str]) -> str:
    """Return the section name for a non-standard heading, or ``''``.

    Deliberately strict: short, standalone, capitalised, punctuation-free and
    followed by content — so a name line, a contact line or a bullet item can
    never split a section in two.
    """
    if index <= 0 or not stripped or stripped.startswith(_BULLET_PREFIX):
        return ""
    if not _standalone(lines, index):
        return ""
    if index + 1 >= len(lines) or not lines[index + 1].strip():
        return ""
    if len(stripped) > 40 or len(stripped.split()) > 5:
        return ""
    if not stripped[0].isupper() or stripped.endswith(_SENTENCE_END):
        return ""
    if any(ch in stripped for ch in ",:;@|()[]{}") or any(ch.isdigit() for ch in stripped):
        return ""
    norm = normalize_heading(stripped)
    if not norm or _exact(norm) or _fuzzy(norm):
        return ""
    return stripped


def split_sections(text: str) -> SectionMap:
    """Split ``text`` into sections; never raises, always returns a header."""
    spans = list(iter_lines(text))
    raw_lines = [raw for _idx, _start, _end, raw in spans]
    lines = [raw.strip() for raw in raw_lines]

    result = SectionMap()
    current = "header"
    current_start = 0
    current_body_start = 0
    current_confidence = 1.0
    buffer_start = 0
    # (name, heading, heading_start, body_start, body_end, body, confidence, duplicate)
    pieces: list[tuple[str, str, int, int, int, str, float, bool]] = []

    for index, start, end, raw in spans:
        stripped = lines[index]
        heading_name: str | None = None
        confidence = 1.0
        bullet = stripped.startswith(_BULLET_PREFIX)
        if stripped and _is_candidate(raw):
            norm = normalize_heading(stripped)
            heading_name = _exact(norm)
            if heading_name is None and not bullet and _standalone(lines, index):
                heading_name = _fuzzy(norm)
                confidence = 0.9
            if heading_name and stripped.startswith(_BULLET_PREFIX) and confidence > 0.95:
                confidence = 0.95

        if heading_name:
            body = text[current_body_start:start].strip()
            pieces.append(
                (
                    current,
                    "",
                    current_start,
                    current_body_start,
                    start,
                    body,
                    current_confidence,
                    False,
                )
            )
            result.raw_headings.append((stripped, start))
            current = heading_name
            current_start = start
            current_body_start = end + 1 if end < len(text) else end
            current_confidence = confidence
            buffer_start = current_body_start
        else:
            # An unrecognized heading ("MY STORY", "Languages I speak") still
            # opens a section so its body is not swallowed by the previous one;
            # it also feeds the parseability report (non-standard headings).
            unknown = _unknown_heading(stripped, index, lines) if result.raw_headings else ""
            if unknown:
                body = text[current_body_start:start].strip()
                pieces.append(
                    (
                        current,
                        "",
                        current_start,
                        current_body_start,
                        start,
                        body,
                        current_confidence,
                        False,
                    )
                )
                result.unrecognized.append(stripped)
                result.raw_headings.append((stripped, start))
                current = unknown
                current_start = start
                current_body_start = end + 1 if end < len(text) else end
                current_confidence = confidence
                buffer_start = current_body_start

    # close the final section
    body = text[buffer_start:].strip()
    pieces.append(
        (
            current,
            "",
            current_start,
            current_body_start,
            len(text),
            body,
            current_confidence,
            False,
        )
    )

    # merge repeated canonical sections (resumes often repeat "Skills")
    merged: dict[str, Section] = {}
    for name, heading, h_start, body_start, end, body, confidence, _dup in pieces:
        if not name and not body:
            continue
        existing = merged.get(name)
        if existing is None:
            merged[name] = Section(
                name=name,
                heading=heading,
                start=h_start,
                body_start=body_start,
                end=end,
                body=body,
                confidence=confidence,
            )
            result.order.append(name)
        else:
            combined = f"{existing.body}\n{body}".strip()
            merged[name] = Section(
                name=name,
                heading=existing.heading,
                start=existing.start,
                body_start=existing.body_start,
                end=end,
                body=combined,
                confidence=existing.confidence,
                duplicate=True,
            )
    result.sections = merged
    return result
