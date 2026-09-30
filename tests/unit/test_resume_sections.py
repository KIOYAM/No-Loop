"""Section detection: exact aliases, typo-tolerant fuzzy headings, unknown headings.

The parser's field extractors trust section spans, so a wrong heading decision
propagates into wrong facts. These tests cover the three branches of
``split_sections``: recognised, fuzzy-recognised, and deliberately unknown.
"""

from __future__ import annotations

from app.adapters.resume_sections import iter_lines, normalize_heading, split_sections


def test_recognised_headings_split_the_document() -> None:
    text = (
        "ARUN KUMAR\narun@x.io\n\n"
        "PROFESSIONAL SUMMARY\nBackend engineer.\n\n"
        "EXPERIENCE\nSenior Engineer, Acme, Mar 2021 - Present\n\n"
        "TECHNICAL SKILLS\nPython, Go\n"
    )
    sections = split_sections(text)
    assert sections.detected() == ["summary", "experience", "skills"]
    assert sections.body("skills").strip() == "Python, Go"
    assert sections.unrecognized == []
    # the header block keeps everything before the first heading
    assert "ARUN KUMAR" in sections.body("header")


def test_fuzzy_heading_tolerates_a_typo_but_not_prose() -> None:
    typo = split_sections(
        "John Doe\n\nWORK EXPERENCE\nAcme Corp, 2020 - 2021\n\nEDUCATION\nB.E. X, Y, 2018"
    )
    assert "experience" in typo.sections
    assert typo.sections["experience"].confidence <= 0.9
    assert typo.unrecognized == []

    prose = split_sections(
        "John Doe\n\nExperience working with children is my passion.\n\nSKILLS\nPython"
    )
    assert "experience" not in prose.sections
    assert prose.unrecognized == []


def test_unknown_heading_opens_its_own_section_after_a_known_one() -> None:
    text = "John Smith\njohn@x.io\n\nSUMMARY\nFine.\n\nWHAT I KNOW\nPython, Go\n"
    sections = split_sections(text)
    assert "WHAT I KNOW" in sections.sections
    assert sections.unrecognized == ["WHAT I KNOW"]
    assert sections.body("WHAT I KNOW").strip() == "Python, Go"
    assert "summary" in sections.sections


def test_a_leading_unknown_heading_needs_a_recognised_heading_first() -> None:
    """A name/contact block must never be mistaken for a section."""
    text = "John Smith\n\nWHAT I KNOW\nPython, Go\n\nSUMMARY\nFine.\n"
    sections = split_sections(text)
    assert "WHAT I KNOW" not in sections.sections
    assert sections.unrecognized == []


def test_contact_and_bullet_lines_are_never_headings() -> None:
    text = (
        "John Smith\n"
        "john@x.io | +91 98765 43210\n\n"
        "SKILLS\n"
        "- Python, Go, Rust\n"
        "- Built APIs in C++\n"
    )
    sections = split_sections(text)
    assert sections.body("skills").strip().startswith("- Python")
    assert sections.unrecognized == []


def test_duplicate_headings_merge_bodies() -> None:
    text = "SKILLS\nPython\n\nEXPERIENCE\nAcme\n\nSKILLS\nGo\n"
    sections = split_sections(text)
    merged = sections.sections["skills"]
    assert merged.duplicate is True
    assert "Python" in merged.body and "Go" in merged.body
    assert merged.end >= sections.sections["experience"].end


def test_normalize_heading_strips_decoration() -> None:
    assert normalize_heading("## Skills:") == "Skills"
    assert normalize_heading("3. Projects") == "Projects"
    assert normalize_heading("----") == ""
    assert normalize_heading("  EDUCATION  ") == "EDUCATION"


def test_iter_lines_reports_exact_offsets() -> None:
    text = "alpha\r\nbeta\n\n gamma"
    lines = list(iter_lines(text))
    assert [raw for _i, _s, _e, raw in lines] == ["alpha", "beta", "", " gamma"]
    for _index, start, end, raw in lines:
        assert text[start:end] == raw


def test_body_spans_point_back_into_the_source_text() -> None:
    text = "SUMMARY\nHello there.\n\nEXPERIENCE\nAcme, 2020 - 2021"
    sections = split_sections(text)
    experience = sections.sections["experience"]
    assert text[experience.body_start : experience.end].strip() == ("Acme, 2020 - 2021")
