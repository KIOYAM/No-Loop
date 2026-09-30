"""Record extraction — employment, education, dates, projects, certifications.

MASTER_SPEC §3 requires name/contact/summary/education/employment/dates/titles/
achievements/projects/technologies/certifications/links/locations. The rule
pass used to emit **only** skills and one experience-years number; everything
else either never existed or lived as an unprovenanced autofill suggestion.
This module extracts the missing field classes deterministically, each with a
character span so ``provenance.span`` can finally be populated (source
highlighting in the confirm UI, and grounding evidence for the AI tier).

Design rules:
- extraction ≠ inference: only strings literally present in the text become
  values (dates are *normalised*, never invented);
- every return carries offsets into the original text;
- heuristic confidence bands, always < 1.0 (1.0 is reserved for user entry);
- pure functions — no I/O, no globals mutated, easy to golden-test.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = [
    "DateRange",
    "EmploymentRecord",
    "EducationRecord",
    "find_date_ranges",
    "normalize_date",
    "tenure_years",
    "extract_employment",
    "extract_education",
    "extract_certifications",
    "extract_projects",
    "extract_name",
    "extract_location",
    "TITLE_KEYWORDS",
    "CITIES",
]

# ---------------------------------------------------------------------------
# dates
# ---------------------------------------------------------------------------

_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

_OPEN_END = ("present", "current", "now", "till date", "ongoing", "pursuing")


def _date_token(prefix: str) -> str:
    """Date alternation with prefix-scoped group names (a range needs two)."""
    return (
        rf"(?:(?P<m{prefix}>[A-Za-z]{{3,9}})\.?\s+(?P<y{prefix}>\d{{4}})"
        rf"|(?P<md{prefix}>\d{{1,2}})/(?P<my{prefix}>\d{{4}})"
        rf"|(?P<iso{prefix}>\d{{4}})-(?P<im{prefix}>\d{{2}})"
        rf"|(?P<y2{prefix}>\d{{4}}))"
    )


_RANGE_RE = re.compile(
    rf"(?P<start>{_date_token('a')})\s*(?:-|–|—|\.\.|to)\s*"
    rf"(?P<end>{_date_token('b')}|(?P<open>{'|'.join(_OPEN_END)}))",
    re.IGNORECASE,
)

_MONTHS_SET = frozenset(_MONTHS)
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")


def normalize_date(match: re.Match[str], prefix: str) -> str | None:
    """Normalise one side of a date match to ``YYYY-MM`` or ``YYYY``."""
    month = match.group(f"m{prefix}")
    year = match.group(f"y{prefix}")
    if month and year:
        key = month.lower().rstrip(".")
        if key not in _MONTHS_SET:
            return None
        return f"{year}-{_MONTHS[key]:02d}"
    md, my = match.group(f"md{prefix}"), match.group(f"my{prefix}")
    if md and my:
        if not 1 <= int(md) <= 12:
            return None
        return f"{my}-{int(md):02d}"
    iso, im = match.group(f"iso{prefix}"), match.group(f"im{prefix}")
    if iso and im:
        if not 1 <= int(im) <= 12:
            return None
        return f"{iso}-{int(im):02d}"
    bare = match.group(f"y2{prefix}")
    if bare:
        return bare
    return None


@dataclass(frozen=True)
class DateRange:
    """A normalised employment/education date range with its source span."""

    start: str | None
    end: str | None  # None => open-ended (Present/Current)
    raw: str
    span: tuple[int, int]

    @property
    def open_ended(self) -> bool:
        return self.end is None

    @property
    def label(self) -> str:
        return self.raw.strip()

    def as_dict(self) -> dict[str, object]:
        return {"start": self.start, "end": self.end, "raw": self.raw.strip()}


def find_date_ranges(text: str, *, offset: int = 0) -> list[DateRange]:
    """All ``<date> - <date|present>`` ranges in ``text`` (offset-adjusted)."""
    ranges: list[DateRange] = []
    for match in _RANGE_RE.finditer(text):
        start = normalize_date(match, "a")
        end = None if match.group("open") else normalize_date(match, "b")
        if start is None or (end is None and not match.group("open")):
            continue
        if start and end and end < start:  # "Present 2020" style reversal
            start, end = end, start
        ranges.append(
            DateRange(
                start=start,
                end=end,
                raw=match.group(0),
                span=(match.start() + offset, match.end() + offset),
            )
        )
    return ranges


def _to_months(value: str) -> int:
    year = int(value[:4])
    month = int(value[5:7]) if len(value) > 4 else 1
    return year * 12 + month


def tenure_years(ranges: list[DateRange], *, now_month: int | None = None) -> float | None:
    """Career-span tenure in years across ranges (open ranges run to 'now').

    Uses month arithmetic so a May→May span is a full year, and an open-ended
    range (``Mar 2021 - Present``) extends to the current month instead of
    being ignored.
    """
    if not ranges:
        return None
    starts = [r.start for r in ranges if r.start]
    if not starts:
        return None
    first = min(_to_months(s) for s in starts)
    if now_month is None:
        import datetime as _dt

        today = _dt.date.today()  # noqa: DTZ011 - month arithmetic only
        now_month = today.year * 12 + today.month
    closed = [r.end for r in ranges if r.end]
    last = max((_to_months(e) for e in closed), default=None)
    any_open = any(r.open_ended for r in ranges)
    end = now_month if any_open or last is None else last
    months = end - first
    if months < 0:
        return None
    years = round(months / 12.0, 1)
    return years if years > 0 else None


# ---------------------------------------------------------------------------
# employment
# ---------------------------------------------------------------------------

#: Title tokens scored against a line fragment. Ordered but matched as a set.
TITLE_KEYWORDS = frozenset(
    {
        "engineer",
        "developer",
        "architect",
        "consultant",
        "analyst",
        "designer",
        "manager",
        "head",
        "director",
        "lead",
        "principal",
        "staff",
        "senior",
        "junior",
        "intern",
        "trainee",
        "executive",
        "officer",
        "specialist",
        "administrator",
        "scientist",
        "researcher",
        "technician",
        "teacher",
        "professor",
        "coordinator",
        "associate",
        "strategist",
        "recruiter",
        "accountant",
        "auditor",
        "attorney",
        "lawyer",
        "nurse",
        "pharmacist",
        "devops",
        "sre",
        "product",
        "marketing",
        "sales",
        "data",
        "ml",
        "ai",
        "fullstack",
        "full-stack",
        "frontend",
        "backend",
        "test",
        "quality",
        "support",
        "operations",
        "operation",
        "business",
        "finance",
        "content",
        "writer",
        "editor",
        "photographer",
        "chef",
        "driver",
        "operator",
        "supervisor",
        "superintendent",
        "clerk",
        "assistant",
        "counselor",
        "advisor",
        "partner",
        "founder",
        "owner",
        "freelance",
        "freelancer",
        "tutor",
        "lecturer",
        "trainer",
        "mentor",
        # ES/PT title words (heading aliases already accept ES/PT section names;
        # full multilingual extraction stays P3 — these are just seeds)
        "analista",
        "ingeniero",
        "ingeniera",
        "desarrollador",
        "desarrolladora",
        "consultor",
        "consultora",
        "especialista",
        "arquitecto",
        "arquitecta",
        "tecnico",
        "técnico",
        "coordinador",
        "coordinadora",
        "responsable",
    }
)

#: Location-ish fragments inside a "Title, Employer, City" line.
_LOCATION_HINTS = frozenset(
    {
        "remote",
        "hybrid",
        "onsite",
        "on-site",
        "bengaluru",
        "bangalore",
        "chennai",
        "mumbai",
        "delhi",
        "hyderabad",
        "pune",
        "kolkata",
        "gurugram",
        "gurgaon",
        "noida",
        "cochin",
        "kochi",
        "trivandrum",
        "ahmedabad",
        "jaipur",
        "india",
        "remote (india)",
    }
)


@dataclass(frozen=True)
class EmploymentRecord:
    title: str | None
    employer: str | None
    dates: DateRange | None
    location: str | None
    spans: dict[str, tuple[int, int]] = field(default_factory=dict)
    confidence: float = 0.6

    @property
    def has_title(self) -> bool:
        return bool(self.title)


def _split_fragments(text: str, offset: int) -> list[tuple[str, tuple[int, int]]]:
    """Split a line fragment on ',' '|' and ' - ' keeping offsets."""
    out: list[tuple[str, tuple[int, int]]] = []
    cursor = 0
    pattern = re.compile(r"\s*(?:,|\||\s-\s|\s–\s|\s—\s)\s*")
    for match in pattern.finditer(text):
        piece = text[cursor : match.start()].strip()
        if piece:
            start = text.index(piece, cursor) + offset
            out.append((piece, (start, start + len(piece))))
        cursor = match.end()
    tail = text[cursor:].strip()
    if tail:
        start = text.index(tail, cursor) + offset
        out.append((tail, (start, start + len(tail))))
    return out


def _looks_like_title(value: str) -> bool:
    lowered = value.lower()
    return any(word in lowered.split() or word in lowered for word in TITLE_KEYWORDS) and (
        len(value.split()) <= 8
    )


def _looks_like_location(value: str) -> bool:
    lowered = value.lower().strip()
    if lowered in _LOCATION_HINTS:
        return True
    return (
        any(hint in lowered for hint in _LOCATION_HINTS if len(hint) > 4)
        and len(value.split()) <= 4
    )


def _classify(
    pieces: list[tuple[str, tuple[int, int]]],
) -> tuple[
    tuple[str, tuple[int, int]] | None,
    tuple[str, tuple[int, int]] | None,
    tuple[str, tuple[int, int]] | None,
]:
    """→ (title, employer, location) from the fragments before a date range."""
    title = employer = location = None
    for value, span in pieces:
        if location is None and _looks_like_location(value):
            location = (value, span)
            continue
        if title is None and _looks_like_title(value):
            title = (value, span)
            continue
        if employer is None:
            employer = (value, span)
    if title is None and employer is not None and len(pieces) == 1:
        # single fragment with dates: "Acme Corp" or "Senior Engineer"
        value, span = employer
        if _looks_like_title(value) and not _looks_like_location(value):
            title = (value, span)
            employer = None
    if title is not None and employer is None and len(pieces) >= 2:
        # title took the first piece; the next non-location piece is the employer
        for value, span in pieces:
            if value == title[0]:
                continue
            if _looks_like_location(value) and location is None:
                location = (value, span)
                continue
            employer = (value, span)
            break
    return title, employer, location


def extract_employment(
    text: str, *, start: int, end: int, require_title: bool = False
) -> list[EmploymentRecord]:
    """Employment records from the experience section (or the whole document).

    ``require_title`` is used when there is no experience section and the scan
    runs over the whole document: then a dated line must contain something that
    reads like a job title, otherwise education lines such as
    "B.Tech Computer Science, SASTRA University, 2020 - 2024" become jobs.
    """
    from app.adapters.resume_sections import iter_lines

    records: list[EmploymentRecord] = []
    lines = [
        (s, e, raw)
        for _idx, s, e, raw in iter_lines(text)
        if s >= start and e <= end and raw.strip()
    ]

    for position, (line_start, line_end, raw) in enumerate(lines):
        line = raw.strip()
        offset = line_start + (raw.index(line))
        range_match = _RANGE_RE.search(line)

        if range_match:
            dates = find_date_ranges(line, offset=offset)[0]
            before = line[: range_match.start()]
            pieces = _split_fragments(before, offset)
            title, employer, location = _classify(pieces)
            if title is None and employer is None:
                tail = before.strip(" ,-–—")
                if tail:
                    employer = (tail, (offset, offset + len(tail)))
            trailing = line[range_match.end() :].strip(" ,;|-–—")
            if title is None and trailing and _looks_like_title(trailing):
                title = (trailing, (offset + range_match.end(), line_end))
            if require_title and title is None:
                continue
            spans: dict[str, tuple[int, int]] = {}
            if title:
                spans["title"] = title[1]
            if employer:
                spans["employer"] = employer[1]
            spans["dates"] = dates.span
            if location:
                spans["location"] = location[1]
            records.append(
                EmploymentRecord(
                    title=title[0] if title else None,
                    employer=employer[0] if employer else None,
                    dates=dates,
                    location=location[0] if location else None,
                    spans=spans,
                    confidence=0.78 if (title and employer) else 0.7,
                )
            )
            continue

        # "Senior Software Engineer" alone, dates/employer on the next line
        if _looks_like_title(line) and len(line.split()) <= 8:
            nxt = lines[position + 1] if position + 1 < len(lines) else None
            if nxt and find_date_ranges(nxt[2].strip(), offset=nxt[0]):
                records.append(
                    EmploymentRecord(
                        title=line,
                        employer=None,
                        dates=None,
                        location=None,
                        spans={"title": (offset, offset + len(line))},
                        confidence=0.62,
                    )
                )

    # merge a title-only record with the record that carries the dates
    merged: list[EmploymentRecord] = []
    for record in records:
        prev = merged[-1] if merged else None
        if prev is not None and prev.title and not prev.dates and record.dates and not record.title:
            merged[-1] = EmploymentRecord(
                title=prev.title,
                employer=record.employer or prev.employer,
                dates=record.dates,
                location=record.location or prev.location,
                spans={**prev.spans, **record.spans},
                confidence=max(prev.confidence, record.confidence, 0.7),
            )
            continue
        merged.append(record)
    return merged


# ---------------------------------------------------------------------------
# education / certifications / projects
# ---------------------------------------------------------------------------

_DEGREE_RE = re.compile(
    r"\b(?P<degree>(?:b\.[a-z]\.|m\.[a-z]\.|b\.?e\.?|b\.?tech\.?|b\.?sc\.?|b\.?ca|b\.?com|b\.?a\b|bba|"
    r"m\.?e\.?|m\.?tech\.?|m\.?sc\.?|m\.?com|mba|m\.?a\b|m\.?phil|"
    r"ph\.?d\.?|d\.?phil|diploma|degree|bachelor(?:'s)?|master(?:'s)?|"
    r"associate(?:'s)?|higher secondary|secondary school|10th|12th))"
    r"(?:\s+(?:(?:in)\s+)?(?P<branch>[A-Z][A-Za-z&./ ]{2,40}))?",
    re.IGNORECASE,
)

_INSTITUTION_RE = re.compile(
    r"\b(?P<inst>(?:[A-Z][A-Za-z&.'-]*\s+){0,4}"
    r"(?:University|College|Institute|Institution|School|Academy|Polytechnic|IIT|NIT|IIM)"
    r"(?:\s+of\s+[A-Z][A-Za-z&.'-]+)*)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EducationRecord:
    degree: str | None
    institution: str | None
    year: str | None
    raw: str
    spans: dict[str, tuple[int, int]] = field(default_factory=dict)
    confidence: float = 0.7


def extract_education(
    text: str, *, start: int, end: int, strict: bool = False
) -> list[EducationRecord]:
    """Education records inside ``[start, end)``.

    ``strict`` is used when there is no education section and the scan runs
    over the whole document: then at least two of {degree, institution, year}
    must agree, so a header line like "Boston, MA | (617) 555-0143" can never
    be read as a degree from a phone number.
    """
    from app.adapters.resume_sections import iter_lines

    records: list[EducationRecord] = []
    for _idx, line_start, _line_end, raw in iter_lines(text):
        if line_start < start or not raw.strip():
            continue
        if line_start >= end:
            break
        line = raw.strip()
        offset = line_start + raw.index(line)
        degree_match = _DEGREE_RE.search(line)
        institution_match = _INSTITUTION_RE.search(line)
        years = _YEAR_RE.findall(line)
        if not degree_match and not institution_match:
            continue
        degree = None
        if degree_match:
            degree = degree_match.group("degree").strip()
            branch = (degree_match.group("branch") or "").strip(" -–—,.")
            if branch and len(branch) <= 48:
                degree = f"{degree} {branch}".strip()
        institution = institution_match.group("inst").strip() if institution_match else None
        institution_span: tuple[int, int] | None = None
        if institution is None:
            # fall back: the fragment that is not the degree and not a year
            pieces = _split_fragments(line, offset)
            for value, span in pieces:
                if degree_match and degree_match.group(0).strip().lower() in value.lower():
                    continue
                if _YEAR_RE.fullmatch(value.strip()):
                    continue
                if "@" in value or sum(ch.isdigit() for ch in value) >= 5:
                    continue  # never read a phone/email as a university
                if len(value.split()) >= 2:
                    institution, institution_span = value, span
                    break
        if strict:
            corroborated = (
                (bool(degree) or bool(years))
                if institution_match
                else bool(degree) and bool(years) and bool(institution)
            )
            if not corroborated:
                continue
        spans: dict[str, tuple[int, int]] = {}
        if degree_match:
            spans["degree"] = (degree_match.start() + offset, degree_match.end() + offset)
        if institution:
            if "institution" not in spans and institution_match:
                spans["education"] = (
                    institution_match.start() + offset,
                    institution_match.end() + offset,
                )
            elif "education" not in spans:
                spans["education"] = institution_span or (offset, offset + len(line))
        if not degree and not institution:
            continue
        records.append(
            EducationRecord(
                degree=degree,
                institution=institution,
                year=years[-1] if years else None,
                raw=line,
                spans=spans,
                confidence=0.72 if (degree and institution) else 0.65,
            )
        )
    return records


_CERT_HINT_RE = re.compile(
    r"\b(?:certified|certification|certificate|licensed|diploma in|badge)\b", re.IGNORECASE
)


def extract_certifications(
    text: str, *, start: int, end: int, limit: int = 12, require_hint: bool = False
) -> list[tuple[str, tuple[int, int]]]:
    from app.adapters.resume_sections import iter_lines

    out: list[tuple[str, tuple[int, int]]] = []
    for _idx, line_start, _line_end, raw in iter_lines(text):
        if line_start < start or line_start >= end:
            continue
        line = raw.strip().lstrip("-•*‣▪ ").strip()
        if not line or len(line) < 4:
            continue
        offset = line_start + raw.index(line)
        hinted = bool(_CERT_HINT_RE.search(line))
        if require_hint and not hinted:
            continue
        if not hinted and len(line.split()) > 7:
            continue
        value = line[:160]
        out.append((value, (offset, offset + len(line))))
        if len(out) >= limit:
            break
    return out


def extract_projects(
    text: str, *, start: int, end: int, limit: int = 12
) -> list[tuple[str, tuple[int, int]]]:
    from app.adapters.resume_sections import iter_lines

    out: list[tuple[str, tuple[int, int]]] = []
    for _idx, line_start, _line_end, raw in iter_lines(text):
        if line_start < start or line_start >= end:
            continue
        line = raw.strip().lstrip("-•*‣▪ ").strip()
        if not line or len(line) < 4:
            continue
        offset = line_start + raw.index(line)
        value = line[:160]
        out.append((value, (offset, offset + len(line))))
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# identity: name + location
# ---------------------------------------------------------------------------

#: City gazetteer (India-first + the common international destinations).
CITIES: tuple[str, ...] = (
    "bengaluru",
    "bangalore",
    "chennai",
    "mumbai",
    "delhi",
    "new delhi",
    "hyderabad",
    "pune",
    "kolkata",
    "gurugram",
    "gurgaon",
    "noida",
    "coimbatore",
    "kochi",
    "cochin",
    "trivandrum",
    "thiruvananthapuram",
    "ahmedabad",
    "jaipur",
    "lucknow",
    "surat",
    "indore",
    "nagpur",
    "vadodara",
    "mysuru",
    "mysore",
    "madurai",
    "tiruchirappalli",
    "thanjavur",
    "salem",
    "erode",
    "vellore",
    "pondicherry",
    "guwahati",
    "bhubaneswar",
    "chandigarh",
    "ludhiana",
    "patna",
    "ranchi",
    "dehradun",
    "vizag",
    "visakhapatnam",
    "warangal",
    "mangaluru",
    "mangalore",
    "thrissur",
    "kannur",
    "calicut",
    "kozhikode",
    "agra",
    "varanasi",
    "amritsar",
    "faridabad",
    "ghaziabad",
    "thane",
    "navi mumbai",
    "hanoi",
    "ho chi minh city",
    "bangkok",
    "singapore",
    "kuala lumpur",
    "jakarta",
    "manila",
    "dubai",
    "abu dhabi",
    "doha",
    "riyadh",
    "jeddah",
    "sharjah",
    "muscat",
    "london",
    "manchester",
    "birmingham",
    "dublin",
    "edinburgh",
    "amsterdam",
    "berlin",
    "munich",
    "frankfurt",
    "paris",
    "lyon",
    "zurich",
    "geneva",
    "madrid",
    "barcelona",
    "lisbon",
    "milan",
    "rome",
    "warsaw",
    "prague",
    "vienna",
    "stockholm",
    "copenhagen",
    "helsinki",
    "oslo",
    "brussels",
    "toronto",
    "vancouver",
    "montreal",
    "new york",
    "san francisco",
    "seattle",
    "austin",
    "boston",
    "chicago",
    "los angeles",
    "denver",
    "atlanta",
    "miami",
    "dallas",
    "houston",
    "phoenix",
    "portland",
    "sydney",
    "melbourne",
    "brisbane",
    "auckland",
    "wellington",
    "tokyo",
    "osaka",
    "seoul",
    "beijing",
    "shanghai",
    "shenzhen",
    "taipei",
    "hong kong",
)

_CITY_RE = re.compile(
    r"\b(" + "|".join(sorted((re.escape(c) for c in CITIES), key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

_NAME_STOPWORDS = frozenset(
    {"summary", "objective", "profile", "curriculum", "vitae", "resume", "cv"}
)


def extract_name(text: str, *, start: int, end: int) -> tuple[str, tuple[int, int]] | None:
    """The candidate's name: first plausible line of the header block."""
    from app.adapters.resume_sections import iter_lines

    for _idx, line_start, _line_end, raw in iter_lines(text):
        if line_start < start or line_start >= end:
            continue
        line = raw.strip()
        if not line:
            continue
        offset = line_start + raw.index(line)
        if len(line) > 60 or len(line.split()) > 6 or len(line.split()) < 2:
            return None
        if any(ch.isdigit() for ch in line) or "@" in line or "|" in line:
            return None
        if line.lower().rstrip(":") in _NAME_STOPWORDS:
            return None
        if not line[0].isupper():
            return None
        return line, (offset, offset + len(line))
    return None


def extract_location(text: str, *, start: int, end: int) -> tuple[str, tuple[int, int]] | None:
    """City from the header/summary block (first match wins)."""
    match = _CITY_RE.search(text, start, min(end, len(text)))
    if not match:
        return None
    value = match.group(0)
    tail = text[match.end() : match.end() + 24]
    country = re.match(r"\s*,\s*([A-Za-z .]{2,20})", tail)
    if country:
        value = f"{value}{country.group(0)}"
    return value.strip(), (match.start(), match.start() + len(value.strip()))


def split_span(span: tuple[int, int], text: str) -> str:
    return text[span[0] : span[1]]
