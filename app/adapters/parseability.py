"""Coverage + parseability — "how much did we get, and what would an ATS see?".

Two reports, both deterministic and both surfaced to the user after import:

* **coverage** — MASTER_SPEC §3 mandates 13 field groups (name, contact,
  summary, education, employment, dates, titles, achievements, projects,
  technologies, certifications, links, locations). This says how many were
  found, which are missing, and what the user still has to supply.
* **parseability** — the same failure modes that make real ATS parsers drop
  content (non-standard headings, table-flattened rows, mixed date formats,
  missing contact details) scored with an actionable fix for each. This is the
  "what an ATS sees" panel; it also validates our own renderer's output.

Evidence for the weightings: EDLIGO 2025 (tables/multi-column 31%+ parse
failure vs ~4% plain DOCX), ATSChecker 2026 (two-column 31.2% failure,
header/footer 22.1%), ATSHiring's "seven most common reasons ATS rejects".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.adapters.resume_records import DateRange, EmploymentRecord
from app.adapters.resume_sections import SectionMap

__all__ = ["REQUIRED_GROUPS", "coverage_report", "parseability_report"]

#: MASTER_SPEC §3 field groups, in spec order.
REQUIRED_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("name", ("full_name",)),
    ("contact", ("contact_email", "contact_phone")),
    ("summary", ("summary",)),
    ("education", ("education", "degree", "education_year")),
    ("employment", ("employer",)),
    ("dates", ("date_range",)),
    ("titles", ("title",)),
    ("achievements", ("achievement",)),
    ("projects", ("project",)),
    ("technologies", ("skill",)),
    ("certifications", ("certification",)),
    ("links", ("link",)),
    ("locations", ("location",)),
)


def coverage_report(field_classes: set[str]) -> dict[str, object]:
    """Which of the 13 spec field groups were found (and which were not)."""
    groups: dict[str, bool] = {}
    for name, members in REQUIRED_GROUPS:
        groups[name] = any(member in field_classes for member in members)
    found = [name for name, ok in groups.items() if ok]
    missing = [name for name, ok in groups.items() if not ok]
    expected = len(REQUIRED_GROUPS)
    return {
        "found": len(found),
        "expected": expected,
        "percent": round(100 * len(found) / expected),
        "groups": groups,
        "missing": missing,
    }


@dataclass
class _Flag:
    code: str
    severity: str  # "info" | "warn" | "error"
    message: str
    fix: str
    penalty: int = 0


def _date_format_kinds(ranges: list[DateRange]) -> set[str]:
    kinds: set[str] = set()
    for date_range in ranges:
        raw = date_range.raw
        if any(ch.isalpha() for ch in raw):
            kinds.add("month-name")
        elif "/" in raw:
            kinds.add("mm/yyyy")
        elif raw.count("-") >= 1 and len(raw.strip().split("-")[0].strip()) == 4:
            kinds.add("yyyy-mm")
        if date_range.start and len(date_range.start) == 4:
            kinds.add("year-only")
    return kinds


def parseability_report(
    text: str,
    sections: SectionMap,
    *,
    ranges: list[DateRange] | None = None,
    employment: list[EmploymentRecord] | None = None,
    has_email: bool = False,
    has_phone: bool = False,
) -> dict[str, object]:
    """Score + explain how legible this document is to an ATS-style parser."""
    flags: list[_Flag] = []
    detected = sections.detected()
    table_rows = sum(1 for line in text.splitlines() if line.count("|") >= 2)
    unrecognised = list(sections.unrecognized)
    ranges = ranges or []
    employment = employment or []

    if len(detected) < 3:
        flags.append(
            _Flag(
                "headings",
                "error",
                "Fewer than 3 standard section headings were detected.",
                "Use conventional headings: Summary, Experience, Skills, Education.",
                20,
            )
        )
    if unrecognised:
        flags.append(
            _Flag(
                "nonstandard_headings",
                "warn",
                f"Non-standard section headings: {', '.join(unrecognised[:4])}."
                + (" …" if len(unrecognised) > 4 else ""),
                "Rename them to what recruiters and parsers expect "
                "(Awards, Languages, Volunteer Work).",
                min(5 * len(unrecognised), 15),
            )
        )
    if table_rows >= 3:
        flags.append(
            _Flag(
                "table_layout",
                "warn",
                f"{table_rows} table-like rows detected — layout tables often parse out of order.",
                "Prefer single-column text with plain bullet lists.",
                10,
            )
        )
    kinds = _date_format_kinds(ranges)
    if len(kinds) >= 2:
        flags.append(
            _Flag(
                "mixed_dates",
                "warn",
                f"Mixed date formats in use: {', '.join(sorted(kinds))}.",
                "Pick one format and use it everywhere (e.g. 'Mar 2021 - Present').",
                10,
            )
        )
    if not has_email:
        flags.append(
            _Flag(
                "missing_email",
                "error",
                "No email address found in the text.",
                "Put a plain-text email in the header (never only in a header/footer box).",
                20,
            )
        )
    if not has_phone:
        flags.append(
            _Flag(
                "missing_phone",
                "warn",
                "No phone number found in the text.",
                "Add a phone number in plain text next to your email.",
                10,
            )
        )
    undated = [r for r in employment if not r.dates]
    if employment and undated:
        flags.append(
            _Flag(
                "missing_dates",
                "warn",
                f"{len(undated)} role(s) have no dates.",
                "Add 'Mon YYYY - Mon YYYY' to every role so tenure can be computed.",
                10,
            )
        )

    score = max(0, min(100, 100 - sum(f.penalty for f in flags)))
    return {
        "score": score,
        "grade": (
            "excellent"
            if score >= 90
            else "good"
            if score >= 75
            else "fair"
            if score >= 55
            else "poor"
        ),
        "standard_headings": detected,
        "nonstandard_headings": unrecognised,
        "table_rows": table_rows,
        "date_formats": sorted(kinds),
        "flags": [
            {
                "code": f.code,
                "severity": f.severity,
                "message": f.message,
                "fix": f.fix,
            }
            for f in flags
        ],
    }


@dataclass
class ImportReport:
    """Bundled coverage + parseability result (serialisable for the UI)."""

    coverage: dict[str, object] = field(default_factory=dict)
    parseability: dict[str, object] = field(default_factory=dict)
