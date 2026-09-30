"""Extraction layer: reading order, DOCX body order, page offsets, honest failures.

Two-column resumes are the classic ATS failure (31%+ parse errors, see
``app/adapters/parseability.py``), so the column split is exercised both with
synthetic segments (fast, precise) and with a real reportlab-built PDF (proves
the pypdf visitor really gives us coordinates).
"""

from __future__ import annotations

import io

from app.adapters.extractors import (
    DocxExtractor,
    PdfExtractor,
    TxtExtractor,
    get_extractor,
    order_reading_pass,
)

PAGE_WIDTH = 595.27  # A4, points


# ---------------------------------------------------------------------------
# order_reading_pass (pure function)
# ---------------------------------------------------------------------------


def test_two_columns_are_read_left_column_first() -> None:
    left = [(50.0, 720.0 - 40 * i, f"L{i + 1} alpha", 10.0) for i in range(4)]
    right = [(300.0, 720.0 - 40 * i, f"R{i + 1} beta", 10.0) for i in range(3)]
    # interleaved on purpose: both columns share the same y values
    segments = [segment for pair in zip(left, right, strict=False) for segment in pair]
    segments.extend(left[3:])

    ordered = order_reading_pass(segments, PAGE_WIDTH).splitlines()
    assert ordered[:4] == ["L1 alpha", "L2 alpha", "L3 alpha", "L4 alpha"]
    assert ordered[4:] == ["R1 beta", "R2 beta", "R3 beta"]


def test_single_column_keeps_plain_top_to_bottom_order() -> None:
    segments = [(50.0, 720.0 - 40 * i, f"LINE {i}", 10.0) for i in range(6)]
    assert order_reading_pass(segments, PAGE_WIDTH).splitlines() == [f"LINE {i}" for i in range(6)]


def test_empty_input_is_not_an_error() -> None:
    assert order_reading_pass([], PAGE_WIDTH) == ""


# ---------------------------------------------------------------------------
# PDF end to end
# ---------------------------------------------------------------------------


def _pdf(pages: list[list[tuple[float, ...]]]) -> bytes:
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, pagesize=(595.27, 841.89))
    for page in pages:
        document.setFont("Helvetica", 10)
        for segment in page:
            x, y, text = segment[0], segment[1], segment[2]
            document.drawString(x, y, text)
        document.showPage()
    document.save()
    return buffer.getvalue()


def _two_column_page() -> list[tuple[float, float, str]]:
    left = [
        "LEFT column line one alpha",
        "LEFT column line two beta",
        "LEFT column line three gamma",
        "LEFT column line four delta",
        "LEFT column line five epsilon",
    ]
    right = [
        "RIGHT column line one alpha",
        "RIGHT column line two beta",
        "RIGHT column line three gamma",
        "RIGHT column line four delta",
        "RIGHT column line five epsilon",
    ]
    page: list[tuple[float, float, str]] = []
    for index, (left_text, right_text) in enumerate(zip(left, right, strict=True)):
        y = 720.0 - 40 * index
        # drawn column-by-column on purpose: a y-only reading order interleaves
        page.append((320.0, y, right_text))
        page.append((50.0, y, left_text))
    return page


def test_pdf_two_column_resume_reads_left_column_first() -> None:
    result = PdfExtractor().extract(_pdf([_two_column_page()]))
    assert result.ok, result.error_reason
    lines = [line for line in result.text.splitlines() if line.strip()]
    left = [line for line in lines if line.startswith("LEFT")]
    right = [line for line in lines if line.startswith("RIGHT")]

    assert len(left) == 5 and len(right) == 5
    assert lines.index(left[-1]) < lines.index(right[0]), "right column interleaved"
    assert [line.rsplit(" ", 1)[-1] for line in left] == [
        "alpha",
        "beta",
        "gamma",
        "delta",
        "epsilon",
    ]
    assert right[0].endswith("alpha")


def test_pdf_page_offsets_point_at_each_page() -> None:
    page_one = [(50.0, 720.0 - 30 * i, f"PAGE ONE line {i} alpha beta", 10.0) for i in range(6)]
    page_two = [(50.0, 720.0 - 30 * i, f"PAGE TWO line {i} gamma delta", 10.0) for i in range(6)]
    result = PdfExtractor().extract(_pdf([page_one, page_two]))

    assert result.ok, result.error_reason
    assert result.page_offsets is not None and len(result.page_offsets) == 2
    assert result.page_offsets[0] == 0
    assert result.text[result.page_offsets[1] :].startswith("PAGE TWO line 0")
    assert result.text[: result.page_offsets[1]].startswith("PAGE ONE line 0")


def test_pdf_without_a_text_layer_fails_honestly() -> None:
    result = PdfExtractor().extract(b"this is not a pdf")
    assert result.ok is False
    assert result.error_reason and result.user_action
    assert result.text == ""


# ---------------------------------------------------------------------------
# DOCX body order
# ---------------------------------------------------------------------------


def _docx_with_table() -> bytes:
    import docx

    buffer = io.BytesIO()
    document = docx.Document()
    document.add_paragraph("Header paragraph")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Left cell"
    table.rows[0].cells[1].text = "Right cell"
    document.add_paragraph("Trailing paragraph")
    document.save(buffer)
    return buffer.getvalue()


def test_docx_keeps_body_order_paragraph_table_paragraph() -> None:
    result = DocxExtractor().extract(_docx_with_table())
    assert result.ok, result.error_reason
    parts = [line for line in result.text.splitlines() if line.strip()]
    assert parts == [
        "Header paragraph",
        "Left cell | Right cell",
        "Trailing paragraph",
    ]


# ---------------------------------------------------------------------------
# registry / text
# ---------------------------------------------------------------------------


def test_extractor_registry_is_case_insensitive() -> None:
    assert get_extractor("resume.pdf") is not None
    assert get_extractor("RESUME.PDF") is not None
    assert get_extractor("resume.docx") is not None
    assert get_extractor("resume.txt") is not None
    assert get_extractor("resume.exe") is None


def test_txt_extractor_strips_and_decodes() -> None:
    result = TxtExtractor().extract(b"  Priya Raghavan\nChennai  ")
    assert result.ok
    assert result.text == "Priya Raghavan\nChennai"
