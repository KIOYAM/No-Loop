"""Structured resume records: dates, tenure, employment, education, credentials.

These are the layer above raw regexes — they decide *what a line means*. The
regressions that hurt most live here (a degree read as a job, a phone number
read as a university), so each of those failures has an explicit test.
"""

from __future__ import annotations

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

# ---------------------------------------------------------------------------
# dates
# ---------------------------------------------------------------------------


def test_date_ranges_normalise_month_names_and_open_ends() -> None:
    (current,) = find_date_ranges("Senior Engineer, Acme, Mar 2021 - Present")
    assert current.start == "2021-03"
    assert current.end is None
    assert current.open_ended is True
    assert current.raw == "Mar 2021 - Present"

    (closed,) = find_date_ranges("Data Engineer, 09/2017 - 02/2021")
    assert (closed.start, closed.end) == ("2017-09", "2021-02")
    assert closed.open_ended is False


def test_tenure_uses_month_arithmetic() -> None:
    assert tenure_years([]) is None
    open_range = find_date_ranges("Mar 2021 - Present")
    assert tenure_years(open_range, now_month=2024 * 12 + 3) == 3.0
    closed = find_date_ranges("Jun 2018 - Feb 2021")
    assert tenure_years(closed, now_month=2030 * 12 + 1) == 2.7  # 32 months


# ---------------------------------------------------------------------------
# employment
# ---------------------------------------------------------------------------


def test_dated_role_line_splits_title_and_employer() -> None:
    text = "Senior Software Engineer, Razorpay, Mar 2021 - Present"
    (record,) = extract_employment(text, start=0, end=len(text))
    assert record.title == "Senior Software Engineer"
    assert record.employer == "Razorpay"
    assert record.dates is not None and record.dates.raw == "Mar 2021 - Present"


def test_role_line_splits_on_dash_and_comma() -> None:
    text = "Software Engineer - Zoho, Jun 2018 - Feb 2021"
    (record,) = extract_employment(text, start=0, end=len(text))
    assert (record.title, record.employer) == ("Software Engineer", "Zoho")


def test_title_line_merges_with_the_dated_line_below_it() -> None:
    text = "Senior Software Engineer\nAcme Corp, Mar 2021 - Present"
    (record,) = extract_employment(text, start=0, end=len(text))
    assert record.title == "Senior Software Engineer"
    assert record.employer == "Acme Corp"
    assert record.dates is not None


def test_education_line_is_not_a_job_when_scanning_the_whole_document() -> None:
    """The fallback path has no section to trust, so it demands a title."""
    text = "B.Tech Computer Science, SASTRA University, 2020 - 2024"
    assert extract_employment(text, start=0, end=len(text), require_title=True) == []
    # …but the same line inside a real experience section is still a record
    assert extract_employment(text, start=0, end=len(text))


# ---------------------------------------------------------------------------
# education
# ---------------------------------------------------------------------------


def test_strict_mode_never_reads_a_header_line_as_a_degree() -> None:
    header = "Boston, MA | john.smith@example.com | (617) 555-0143"
    assert extract_education(header, start=0, end=len(header), strict=True) == []


def test_strict_mode_keeps_a_real_degree_line() -> None:
    text = "B.S. Computer Science, University of Michigan, 2015"
    (record,) = extract_education(text, start=0, end=len(text), strict=True)
    assert record.degree == "B.S. Computer Science"
    assert record.institution == "University of Michigan"
    assert record.year == "2015"


def test_institution_regex_does_not_swallow_the_next_word() -> None:
    assert extract_education("SCHOOLING", start=0, end=len("SCHOOLING")) == []


def test_relaxed_mode_still_accepts_a_degree_only_line() -> None:
    text = "Master of Engineering"
    (record,) = extract_education(text, start=0, end=len(text))
    assert record.degree is not None
    assert record.institution is None


# ---------------------------------------------------------------------------
# certifications / projects / identity
# ---------------------------------------------------------------------------


def test_certification_hint_mode_ignores_ordinary_lines() -> None:
    text = "Built payment APIs with Redis caching\nAWS Certified Developer - Associate"
    assert extract_certifications(text, start=0, end=len(text), require_hint=True) == [
        ("AWS Certified Developer - Associate", (0 + text.index("AWS"), len(text)))
    ]
    # without the hint the short second line is still eligible in a section
    assert len(extract_certifications(text, start=0, end=len(text))) == 2


def test_projects_are_the_lines_of_the_section() -> None:
    text = "- UPI Settlement Engine: ledger reconciler in Go\n- resume-lens: ATS scores"
    values = [value for value, _span in extract_projects(text, start=0, end=len(text))]
    assert values == [
        "UPI Settlement Engine: ledger reconciler in Go",
        "resume-lens: ATS scores",
    ]


def test_name_requires_a_clean_first_line() -> None:
    header = "Priya Raghavan\npriya.raghavan@gmail.com | +91 90000 11111"
    found = extract_name(header, **{"start": 0, "end": len(header)})
    assert found is not None and found[0] == "Priya Raghavan"
    assert extract_name(header, start=15, end=len(header)) is None  # contact line


def test_location_keeps_the_country() -> None:
    header = "Priya Raghavan\npriya.raghavan@gmail.com | Chennai, India\n"
    found = extract_location(header, start=0, end=len(header))
    assert found is not None
    assert found[0] == "Chennai, India"
    assert header[found[1][0] : found[1][1]] == "Chennai, India"
