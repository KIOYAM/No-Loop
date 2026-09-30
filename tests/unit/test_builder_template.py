"""Resume canvas contract: bound skeleton -> editor -> override diff -> exports.

The builder's whole safety story is here: content only round-trips through
``data-nl-path`` leaves, an edit is an override only when the text actually
differs from the fact, and every export is built from one merged doc.
"""

from __future__ import annotations

from app.services.builder_template import (
    DEFAULT_RESUME_CSS,
    bound_values,
    diff_overrides,
    get_path,
    html_export,
    merge_doc,
    render_skeleton,
    section_order,
    set_path,
    text_export,
)

DOC = {
    "contact": {
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "phone": "123",
        "location": "London",
    },
    "summary": "Backend engineer.",
    "skills": ["Python", "Go"],
    "experience": [
        {
            "role": "Engineer",
            "company": "Acme",
            "period": "2021 - Present",
            "bullets": ["Built the payments API in Go"],
        }
    ],
    "projects": [{"title": "Ledger", "bullets": ["Open source double-entry core"]}],
    "education": [{"degree": "BSc", "school": "UCL", "period": "2016"}],
    "certifications": ["AWS Solutions Architect"],
}


def test_skeleton_binds_every_editable_value() -> None:
    html = render_skeleton(DOC)
    paths = bound_values(html)
    assert paths["contact.name"] == "Ada Lovelace"
    assert paths["summary"] == "Backend engineer."
    assert paths["skills[1]"] == "Go"
    assert paths["experience[0].role"] == "Engineer"
    assert paths["experience[0].bullets[0]"] == "Built the payments API in Go"
    assert paths["projects[0].bullets[0]"] == "Open source double-entry core"
    assert paths["education[0].degree"] == "BSc"
    assert paths["certifications[0]"] == "AWS Solutions Architect"
    # containers must not be collected, or the diff would double-count
    assert "experience[0]" not in paths
    assert "skills" not in paths


def test_empty_sections_are_omitted_not_rendered_hollow() -> None:
    html = render_skeleton({"contact": {"name": "Ada", "email": "a@b.c"}})
    assert 'data-nl-section="header"' in html
    assert 'data-nl-section="experience"' not in html
    assert 'data-nl-section="education"' not in html
    # a summary with no text is not a heading with nothing under it either
    assert 'data-nl-section="summary"' not in html


def test_section_order_follows_the_canvas_layout() -> None:
    html = render_skeleton(DOC, ["header", "education", "experience", "skills"])
    assert section_order(html) == ["header", "education", "experience", "skills"]
    # the canvas really renders them in that order
    positions = [html.index(f'data-nl-section="{name}"') for name in ("education", "experience")]
    assert positions == sorted(positions)


def test_diff_keeps_only_paths_the_human_changed() -> None:
    html = render_skeleton(DOC)
    edited = html.replace("Built the payments API in Go", "Built the payments API in Go and Kafka")
    overrides = diff_overrides(edited, DOC)
    assert overrides == {"experience[0].bullets[0]": "Built the payments API in Go and Kafka"}


def test_diff_captures_a_cleared_field_and_ignores_unchanged_text() -> None:
    html = render_skeleton(DOC)
    cleared = html.replace("Backend engineer.", "")
    overrides = diff_overrides(cleared, DOC)
    assert overrides == {"summary": ""}


def test_diff_normalises_whitespace_and_entities() -> None:
    html = render_skeleton(DOC)
    reflowed = html.replace("Built the payments API in Go", "Built  the payments\nAPI in Go")
    assert diff_overrides(reflowed, DOC) == {}


def test_merge_applies_overrides_without_touching_the_original() -> None:
    merged = merge_doc(DOC, {"experience[0].bullets[0]": "Shipped it", "summary": "New line"})
    assert merged["experience"][0]["bullets"][0] == "Shipped it"
    assert merged["summary"] == "New line"
    assert DOC["experience"][0]["bullets"][0] == "Built the payments API in Go"
    # a path that cannot exist is reported, not silently created in a list
    assert set_path(merged, "experience[9].role", "Ghost") is False


def test_get_path_reads_nested_and_indexed_values() -> None:
    assert get_path(DOC, "contact.email") == "ada@example.com"
    assert get_path(DOC, "skills[0]") == "Python"
    assert get_path(DOC, "experience[0].company") == "Acme"
    assert get_path(DOC, "experience[3].role") is None
    assert get_path(DOC, "skills[7]") is None


def test_html_export_is_self_contained() -> None:
    page = html_export(render_skeleton(DOC), DEFAULT_RESUME_CSS, title="Ada Lovelace")
    assert page.startswith("<!doctype html>")
    assert "<title>Ada Lovelace</title>" in page
    assert DEFAULT_RESUME_CSS.splitlines()[0] in page
    assert 'data-nl-path="contact.name"' in page
    # no network references at all: local-first means the export opens offline
    assert "http://" not in page and "https://" not in page


def test_text_export_keeps_what_an_ats_parser_looks_for() -> None:
    text = text_export(DOC)
    # contact: a resume without an email is a resume nobody can answer
    assert "Ada Lovelace" in text
    assert "ada@example.com" in text
    assert "123" in text and "London" in text
    # headings, employers and dates — the flat scoring text drops all of these
    assert "EXPERIENCE" in text
    assert "Engineer — Acme (2021 - Present)" in text
    assert "\u2022 Built the payments API in Go" in text
    assert "EDUCATION" in text and "BSc — UCL (2016)" in text
    assert "AWS Solutions Architect" in text
    assert text.endswith("\n")


def test_text_export_follows_the_section_order_and_skips_empty_sections() -> None:
    text = text_export(DOC, ["experience", "summary", "header", "made-up"])
    assert text.index("EXPERIENCE") < text.index("SUMMARY") < text.index("Ada")
    # a section the doc knows nothing about is skipped, never crashed on
    assert "Made-up" not in text
    empty = text_export({"contact": {"name": "Ada", "email": "a@b.c"}})
    assert "EXPERIENCE" not in empty
    assert "a@b.c" in empty
