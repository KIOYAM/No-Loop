"""Deterministic resume → profile autofill (user request: "profile auto filled").

Tier 0 only: pure regex/section heuristics, no network, sub-millisecond, and
every suggestion carries a confidence **below 1.0** plus the rule that produced
it, so the UI can label it "auto-filled — confirm". Nothing here ever overwrites
a value the user already entered (fill-only), and nothing is ever presented as
confirmed truth until the user accepts it (S2 anti-fabrication).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

__all__ = ["AutofillOutcome", "Suggestion", "suggest_profile_fields"]

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?:\+?\d{1,3}[-\s]?)?[6-9]\d{4}[-\s]?\d{5}")
_URL_RE = re.compile(r"https?://[^\s)>\]]+")
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_RANGE_RE = re.compile(
    r"((?:19|20)\d{2})\s*(?:-|–|—|to|till|through)\s*((?:19|20)\d{2}|present|current|now)",
    re.IGNORECASE,
)
_DEGREE_RE = re.compile(
    r"\b(b\.?tech|b\.?e\.?|bachelor(?:'s)?|m\.?tech|m\.?e\.?|master(?:'s)?|mba|"
    r"b\.?sc|m\.?sc|bca|mca|b\.?com|m\.?com|diploma|ph\.?d|bachelor of|master of)"
    r"[^|\n]{0,70}",
    re.IGNORECASE,
)
_TITLE_RE = re.compile(
    r"\b(senior|junior|lead|principal|staff|assistant|associate|intern|trainee)?\s*"
    r"(software|backend|frontend|full[\s-]?stack|machine[\s-]?learning|data|devops|"
    r"cloud|security|platform|site|quality|test|product|project|business|systems?)?\s*"
    r"(engineer|developer|analyst|architect|consultant|scientist|manager|designer|"
    r"specialist|administrator|technician)s?\b",
    re.IGNORECASE,
)

_CITIES = (
    "chennai",
    "bengaluru",
    "bangalore",
    "hyderabad",
    "pune",
    "mumbai",
    "delhi",
    "kolkata",
    "coimbatore",
    "madurai",
    "trichy",
    "tiruchirappalli",
    "salem",
    "erode",
    "ahmedabad",
    "jaipur",
    "lucknow",
    "kochi",
    "thiruvananthapuram",
    "bhubaneswar",
    "indore",
    "nagpur",
    "visakhapatnam",
    "mysuru",
    "mysore",
    "chandigarh",
    "gurugram",
    "gurgaon",
    "noida",
    "faridabad",
    "remote",
    "india",
    "singapore",
    "dubai",
    "london",
    "new york",
    "san francisco",
    "toronto",
    "sydney",
    "berlin",
    "dublin",
    "kuala lumpur",
)

_LINK_HINTS = (
    "github.com",
    "linkedin.com",
    "gitlab.com",
    "behance.net",
    "dribbble.com",
    "medium.com",
    "stackoverflow.com",
    "linktr.ee",
    "notion.site",
)

#: Profile fields that collect a list of suggestions instead of a single value.
_LIST_FIELDS = frozenset({"education", "job_titles", "employers", "certifications", "languages"})


@dataclass
class Suggestion:
    """One auto-filled profile field, with why it was inferred."""

    field: str
    value: Any
    confidence: float
    rule: str
    preview: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "value": self.value,
            "confidence": round(self.confidence, 2),
            "rule": self.rule,
            "preview": self.preview,
        }


@dataclass
class AutofillOutcome:
    suggestions: list[Suggestion] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.suggestions)

    def applied(self, existing: dict[str, Any]) -> dict[str, Any]:
        """Fill ONLY empty fields (fill-only rule; user data is never clobbered)."""
        applied: dict[str, Any] = {}
        for s in self.suggestions:
            if s.field.startswith("links."):
                key = s.field.split(".", 1)[1]
                if existing.get("links") or applied.get("links"):
                    continue
                applied.setdefault("links", {})[key] = s.value
            elif s.field in _LIST_FIELDS:
                if existing.get(s.field) or applied.get(s.field):
                    continue
                bucket = applied.setdefault(s.field, [])
                if s.value not in bucket:
                    bucket.append(s.value)
            elif s.field not in applied and existing.get(s.field) in (None, "", [], {}):
                applied[s.field] = s.value
        return {k: v for k, v in applied.items() if v not in (None, "", [], {})}

    def to_dict(self) -> dict[str, Any]:
        return {
            "suggestions": [s.to_dict() for s in self.suggestions],
            "warnings": list(self.warnings),
        }


def _first_meaningful_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or len(stripped) > 60:
            continue
        if _EMAIL_RE.search(stripped) or _URL_RE.search(stripped):
            continue
        if any(ch.isdigit() for ch in stripped):
            continue
        words = stripped.split()
        if (
            2 <= len(words) <= 5
            and all(w.strip(".,'-") for w in words)
            and re.fullmatch(r"[A-Za-z.'&\- ]+", stripped)
        ):
            return stripped
    return ""


def _suggest_name(text: str, email_line: str) -> Suggestion | None:
    candidate = ""
    if email_line:
        idx = text.find(email_line)
        if idx > 0:
            before = text[:idx].strip().splitlines()
            if before:
                tail = before[-1].strip()
                if 2 <= len(tail.split()) <= 5 and not any(c.isdigit() for c in tail):
                    candidate = tail
    if not candidate:
        candidate = _first_meaningful_line(text)
    if not candidate:
        return None
    return Suggestion("contact_name", candidate.title(), 0.78, "rule:header-line", candidate)


def _suggest_location(text: str) -> Suggestion | None:
    head = "\n".join(text.splitlines()[:30]).lower()
    for city in _CITIES:
        if re.search(rf"\b{re.escape(city)}\b", head):
            display = city.title() if city.islower() else city
            return Suggestion("location", display, 0.72, f"rule:city:{city}", display)
    m = re.search(r"\b([A-Z][a-zA-Z]+),\s*([A-Z]{2,3}|India)\b", text)
    if m:
        return Suggestion("location", m.group(0), 0.6, "rule:city-state", m.group(0))
    return None


def _suggest_links(text: str) -> list[Suggestion]:
    out: list[Suggestion] = []
    seen: set[str] = set()
    for url in _URL_RE.findall(text):
        clean = url.rstrip(".,);")
        low = clean.lower()
        if not any(h in low for h in _LINK_HINTS):
            continue
        if clean in seen:
            continue
        seen.add(clean)
        key = next(h.split(".")[0] for h in _LINK_HINTS if h in low)
        out.append(Suggestion(f"links.{key}", clean, 0.85, f"rule:url:{key}", clean))
    return out


def _suggest_summary(text: str) -> Suggestion | None:
    lowered = text.lower()
    for heading in ("summary", "objective", "profile", "about"):
        start = lowered.find(f"\n{heading}")
        if start < 0 and lowered.startswith(heading):
            start = 0
        if start < 0:
            continue
        chunk = text[start:].splitlines()[1:]
        body: list[str] = []
        for line in chunk:
            if not line.strip():
                if body:
                    break
                continue
            if len(line.strip()) < 60 and line.strip().rstrip(":").lower() in (
                "skills",
                "experience",
                "education",
                "projects",
                "certifications",
                "employment",
                "work history",
                "achievements",
                "languages",
            ):
                break
            body.append(line.strip())
            if sum(len(b) for b in body) > 420:
                break
        summary = " ".join(body)[:400].strip()
        if len(summary) > 60:
            return Suggestion("summary", summary, 0.7, f"rule:section:{heading}", summary[:120])
    return None


def _suggest_experience(text: str) -> Suggestion | None:
    claims = [int(m.group(1)) for m in re.finditer(r"(\d{1,2})\+?\s*years?\b", text, re.I)]
    claims = [c for c in claims if 0 < c <= 40]
    if claims:
        return Suggestion(
            "experience_years", max(claims), 0.7, "rule:experience.regex", f"{max(claims)} years"
        )
    ranges = _RANGE_RE.findall(text)
    if ranges:
        total = 0
        for start, end in ranges:
            try:
                end_year = 2026 if end.lower() in {"present", "current", "now"} else int(end)
                total += max(0, end_year - int(start))
            except ValueError:
                continue
        if total > 0:
            return Suggestion(
                "experience_years",
                min(total, 40),
                0.55,
                "rule:experience.date-range",
                f"~{total} years from date ranges",
            )
    return None


def _suggest_education(text: str) -> list[Suggestion]:
    out: list[Suggestion] = []
    for match in _DEGREE_RE.finditer(text):
        snippet = " ".join(match.group(0).split())[:90]
        if len(snippet) < 5:
            continue
        if any(snippet.lower() in s.value.lower() for s in out if isinstance(s.value, str)):
            continue
        out.append(Suggestion("education", snippet, 0.66, "rule:degree.regex", snippet))
        if len(out) >= 4:
            break
    return out


def _suggest_titles(text: str) -> list[Suggestion]:
    out: list[Suggestion] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or len(line) > 70:
            continue
        m = _TITLE_RE.search(line)
        if not m:
            continue
        title = " ".join(m.group(0).split()).strip()
        key = title.lower()
        if key in seen or len(title) < 6:
            continue
        seen.add(key)
        out.append(Suggestion("job_titles", title.title(), 0.6, "rule:title.regex", title))
        if len(out) >= 5:
            break
    return out


def _suggest_employers(text: str) -> list[Suggestion]:
    out: list[Suggestion] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or len(line) > 90:
            continue
        company = None
        if _RANGE_RE.search(line):
            parts = re.split(r"[|•·\u2022]", line)
            if len(parts) > 1:
                tail = parts[-1].strip()
                tail = _RANGE_RE.sub("", tail).strip(" |-,–—\t")
                company = tail
        else:
            m = re.search(
                r"\b(?:company|employer|organization)\s*[:\-|]\s*"
                r"([A-Za-z][\w&.\- ]{2,40})",
                line,
                re.I,
            )
            if m:
                company = m.group(1).strip()
        if not company:
            continue
        key = company.lower()
        if key in seen or len(company) < 3:
            continue
        seen.add(key)
        out.append(
            Suggestion("employers", company.strip(), 0.58, "rule:employer.timeline", company)
        )
        if len(out) >= 6:
            break
    return out


def suggest_profile_fields(text: str) -> AutofillOutcome:
    """Run every Tier-0 rule over resume text and return merge-ready suggestions."""
    outcome = AutofillOutcome()
    if not text.strip():
        outcome.warnings.append("no text — autofill skipped")
        return outcome

    email = _EMAIL_RE.search(text)
    email_line = ""
    if email:
        for line in text.splitlines():
            if email.group(0) in line:
                email_line = line
                break
        outcome.suggestions.append(
            Suggestion("contact_email", email.group(0), 0.95, "rule:email.regex", email.group(0))
        )
    else:
        outcome.warnings.append("no email found — add it manually")

    phone = _PHONE_RE.search(text)
    if phone:
        outcome.suggestions.append(
            Suggestion("contact_phone", phone.group(0), 0.9, "rule:phone.regex", phone.group(0))
        )

    name = _suggest_name(text, email_line)
    if name:
        outcome.suggestions.append(name)
    else:
        outcome.warnings.append("name not confidently detected — review the profile header")

    location = _suggest_location(text)
    if location:
        outcome.suggestions.append(location)

    outcome.suggestions.extend(_suggest_links(text))

    summary = _suggest_summary(text)
    if summary:
        outcome.suggestions.append(summary)

    experience = _suggest_experience(text)
    if experience:
        outcome.suggestions.append(experience)
    else:
        outcome.warnings.append("total experience not stated — onboarding question required")

    outcome.suggestions.extend(_suggest_education(text))
    outcome.suggestions.extend(_suggest_titles(text))
    outcome.suggestions.extend(_suggest_employers(text))
    return outcome
