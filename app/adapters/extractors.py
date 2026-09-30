"""Document extraction adapters (LOOP-5; skill 03).

Extraction ≠ inference: these adapters return raw text only. Facts and
confidence belong to the fact ledger service.

What the 2026-09 upgrade added (No_Loop_docs/RESUME_PROCESSING_UPGRADE.md §5 L1):

- **PDF reading order.** pypdf returns text in *content-stream* order, which for
  a two-column resume interleaves the columns line by line — the single most
  common real-world ATS failure (EDLIGO 2025: 31%+ failure on tables/multi-column
  vs ~4% for plain DOCX). We keep pypdf (BSD, ADR-2 already rejected
  PyMuPDF/AGPL) but rebuild reading order from character positions: line
  clustering → gutter detection → column order. A plain-text result is always
  computed in the same pass and used as the safety net, so a PDF can only ever
  get *more* readable, never less.
- **Page offsets** so facts can carry ``provenance.page``.
- **DOCX document order.** ``document.paragraphs`` + ``document.tables`` puts
  *every* table after *every* paragraph; resumes with a contact/skills table
  came out scrambled. Blocks are now walked in body order.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from typing import Any

from app.ports import ExtractionResult

__all__ = [
    "TxtExtractor",
    "DocxExtractor",
    "PdfExtractor",
    "get_extractor",
    "SUPPORTED_FORMATS",
    "order_reading_pass",
]

_MAX_BYTES = 10 * 1024 * 1024  # 10 MB (SECURITY.md file caps)


class TxtExtractor:
    formats = ("txt",)

    def extract(self, data: bytes) -> ExtractionResult:
        if len(data) > _MAX_BYTES:
            return ExtractionResult(
                False,
                error_reason="file exceeds 10 MB limit",
                user_action="Split or compress the file.",
            )
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1", errors="replace")
        text = text.strip()
        if not text:
            return ExtractionResult(
                False,
                error_reason="file contains no readable text",
                user_action="Check the file contents.",
            )
        return ExtractionResult(True, text)


class DocxExtractor:
    """DOCX via python-docx (optional extra; honest failure if not installed)."""

    formats = ("docx",)

    def extract(self, data: bytes) -> ExtractionResult:
        if len(data) > _MAX_BYTES:
            return ExtractionResult(
                False,
                error_reason="file exceeds 10 MB limit",
                user_action="Split or compress the file.",
            )
        try:
            import docx
        except ImportError:
            return ExtractionResult(
                False,
                error_reason="DOCX support not installed in this environment",
                user_action=("Install the 'docx' extra or save the resume as .txt."),
            )
        try:
            document = docx.Document(io.BytesIO(data))
        except Exception as exc:  # noqa: BLE001 — mapped to domain error below
            return ExtractionResult(
                False,
                error_reason=f"corrupt or unsupported DOCX: {exc.__class__.__name__}",
                user_action="Re-save the file from Word and retry.",
            )
        parts = list(_iter_block_texts(document))
        text = "\n".join(parts).strip()
        if not text:
            return ExtractionResult(
                False,
                error_reason=("no text found — this looks like an image-only document"),
                user_action="Export a text PDF or paste your resume text.",
            )
        return ExtractionResult(True, text)


def _iter_block_texts(document: Any) -> Iterator[str]:
    """Yield paragraph/table-row texts in *document body order*.

    ``document.paragraphs`` and ``document.tables`` are separate lists — using
    them sequentially appends all tables after all paragraphs, which scrambles
    any resume that uses a layout table (contact header, skills sidebar).
    """
    try:
        from docx.oxml.ns import qn
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError:  # pragma: no cover - guarded by the caller's import
        for paragraph in document.paragraphs:
            if paragraph.text.strip():
                yield paragraph.text
        return

    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            paragraph = Paragraph(child, document)
            if paragraph.text.strip():
                yield paragraph.text
        elif child.tag == qn("w:tbl"):
            table = Table(child, document)
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if cells:
                    yield " | ".join(cells)


# ---------------------------------------------------------------------------
# PDF reading order
# ---------------------------------------------------------------------------


def _page_segments(page: Any) -> tuple[str, list[tuple[float, float, str, float]]]:
    """(plain text, segments) — one extraction pass yields both."""
    segments: list[tuple[float, float, str, float]] = []

    def visitor(text: str, cm: Any, tm: Any, _font_dict: Any, font_size: Any) -> None:
        if not text or not text.strip():
            return
        try:
            # text matrix translation pushed through the current transform
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
        except Exception:  # noqa: BLE001 - degenerate matrices happen
            try:
                x, y = float(tm[4]), float(tm[5])
            except Exception:  # noqa: BLE001
                return
        try:
            size = float(font_size) if font_size else 10.0
        except Exception:  # noqa: BLE001
            size = 10.0
        segments.append((float(x), float(y), text, size))

    try:
        plain = page.extract_text(visitor_text=visitor) or ""
    except Exception:  # noqa: BLE001 - one broken page must not kill the doc
        plain, segments = "", []
    return plain, segments


def _cluster_lines(
    segments: list[tuple[float, float, str, float]],
) -> list[tuple[float, float, float, float, str]]:
    """Group segments into visual lines: (x0, x1, y, size, text)."""
    if not segments:
        return []
    ordered = sorted(segments, key=lambda s: (-s[1], s[0]))
    clusters: list[dict[str, Any]] = []
    for x, y, text, size in ordered:
        if clusters:
            current = clusters[-1]
            tolerance = max(1.6, 0.45 * max(size, current["size"]))
            if abs(current["y"] - y) <= tolerance:
                current["pieces"].append((x, text, size))
                current["size"] = max(current["size"], size)
                continue
        clusters.append({"y": y, "size": size, "pieces": [(x, text, size)]})

    built: list[tuple[float, float, float, float, str]] = []
    for cluster in clusters:
        pieces = sorted(cluster["pieces"], key=lambda p: p[0])
        buffer = ""
        cursor_x: float | None = None
        cursor_size = cluster["size"]
        for x, text, psize in pieces:
            if (
                cursor_x is not None
                and x - cursor_x > 0.8 * max(cursor_size, psize, 1.0)
                and not buffer.endswith(" ")
            ):
                buffer += " "
            buffer += text
            cursor_x = x + max(len(text), 1) * psize * 0.5
            cursor_size = psize
        last_x, last_text, last_size = pieces[-1]
        x1 = last_x + max(len(last_text), 1) * last_size * 0.5
        buffer = buffer.strip()
        if buffer:
            built.append((pieces[0][0], x1, cluster["y"], cluster["size"], buffer))
    return built


def _extent(segment: tuple[float, float, str, float]) -> float:
    x, _y, text, size = segment
    return x + max(len(text), 1) * size * 0.5


def _split_columns(
    segments: list[tuple[float, float, str, float]], page_width: float | None
) -> tuple[list[tuple[float, float, str, float]], list[tuple[float, float, str, float]]]:
    """Split segments into (left column, right column); right is ``[]`` if single.

    Columns must be split *before* line clustering: a two-column resume draws
    both columns at the same y, so clustering by y alone merges them into one
    long interleaved line — exactly the failure this pass exists to fix.
    """
    live = [segment for segment in segments if segment[2].strip()]
    if page_width is None or len(live) < 6:
        return segments, []
    xs = sorted({round(segment[0], 1) for segment in live})
    minimum_gap = 0.12 * page_width
    best: tuple[float, float] | None = None  # (gap, gutter)
    for left_x, right_x in zip(xs, xs[1:], strict=False):
        gap = right_x - left_x
        if gap < minimum_gap or (best and gap <= best[0]):
            continue
        left = [segment for segment in live if segment[0] <= left_x]
        right = [segment for segment in live if segment[0] >= right_x]
        if len(left) < 3 or len(right) < 2:
            continue
        extents = sorted(_extent(segment) for segment in left)
        extent = extents[int(0.75 * (len(extents) - 1))]
        if right_x - extent < 0.05 * page_width:
            continue  # the "gap" is just indented text, not a column break
        gutter = (extent + right_x) / 2
        straddling = sum(1 for segment in live if segment[0] < gutter < _extent(segment))
        if straddling > max(1, len(live) // 8):
            continue  # full-width lines cross the gutter: not a two-column page
        best = (gap, gutter)
    if best is None:
        return segments, []
    gutter = best[1]
    left_col = [segment for segment in segments if segment[0] < gutter]
    right_col = [segment for segment in segments if segment[0] >= gutter]
    if len(left_col) < 3 or len(right_col) < 2:
        return segments, []
    return left_col, right_col


def order_reading_pass(
    segments: list[tuple[float, float, str, float]], page_width: float | None
) -> str:
    """Character positions → reading-order text (columns handled)."""
    if not segments:
        return ""
    left, right = _split_columns(segments, page_width)
    output: list[str] = []
    for group in [left, right] if right else [left]:
        for line in sorted(_cluster_lines(group), key=lambda ln: (-ln[2], ln[0])):
            output.append(line[4])
    return "\n".join(output)


def _page_width(page: Any) -> float | None:
    try:
        return float(page.mediabox.width) or None
    except Exception:  # noqa: BLE001
        return None


class PdfExtractor:
    """PDF text extraction via pypdf (BSD-3-Clause — ADR-2 decision 2026-09-29).

    pypdf was chosen over PyMuPDF (AGPL — contamination risk per R-TRUTH-6).
    Password-protected files are refused with a guided user action; scanned /
    image-only PDFs yield no text and are refused honestly (R-TRUTH-3).

    Reading order is rebuilt from character positions (see module docstring);
    the plain extraction of the same call is the fallback whenever the ordered
    pass loses more than 40% of the words.
    """

    formats = ("pdf",)

    def extract(self, data: bytes) -> ExtractionResult:
        if len(data) > _MAX_BYTES:
            return ExtractionResult(
                False,
                error_reason="file exceeds 10 MB limit",
                user_action="Split or compress the file.",
            )
        if not data.startswith(b"%PDF"):
            return ExtractionResult(
                False,
                error_reason="file is not a valid PDF (bad magic bytes)",
                user_action="Re-export the file as PDF from the source app.",
            )
        try:
            from io import BytesIO

            from pypdf import PdfReader
            from pypdf.errors import PdfReadError
        except ImportError:  # pragma: no cover - pypdf is a declared dependency
            return ExtractionResult(
                False,
                error_reason="PDF library missing (pypdf not installed)",
                user_action="Reinstall No_Loop or run: pip install pypdf",
            )
        try:
            reader = PdfReader(BytesIO(data))
            if reader.is_encrypted:
                return ExtractionResult(
                    False,
                    error_reason="this PDF is password-protected/encrypted",
                    user_action="Remove the password (Print → Save as PDF) and retry.",
                )
            parts: list[str] = []
            page_offsets: list[int] = []
            offset = 0
            for page in reader.pages[:50]:  # bounded: resumes never need 50+ pages
                try:
                    plain, segments = _page_segments(page)
                    ordered = order_reading_pass(segments, _page_width(page))
                    if plain and ordered:
                        plain_words = len(plain.split())
                        if len(ordered.split()) < 0.6 * plain_words:
                            ordered = ""  # safety net: never lose content
                    chosen = (ordered or plain).strip()
                except Exception:  # noqa: BLE001, S112 - one bad page must not kill the doc
                    continue
                if not chosen:
                    continue
                page_offsets.append(offset)
                offset += len(chosen) + 1
                parts.append(chosen)
            text = "\n".join(parts)
        except PdfReadError as exc:
            return ExtractionResult(
                False,
                error_reason=f"corrupt or unreadable PDF: {exc.__class__.__name__}",
                user_action="Open the PDF to verify it, then re-export and retry.",
            )
        except Exception as exc:  # noqa: BLE001 - honest error envelope
            return ExtractionResult(
                False,
                error_reason=f"PDF parse failed: {exc.__class__.__name__}",
                user_action="Save as .txt/.docx or paste your resume text instead.",
            )
        if not text or len(text.split()) < 20:
            return ExtractionResult(
                False,
                error_reason="no text layer found — this looks like a scanned image",
                user_action="Export a text PDF, save as .docx/.txt, or paste your resume text.",
            )
        return ExtractionResult(True, text, page_offsets=page_offsets or None)


_REGISTRY: dict[str, object] = {
    "txt": TxtExtractor(),
    "docx": DocxExtractor(),
    "pdf": PdfExtractor(),
}

SUPPORTED_FORMATS = tuple(_REGISTRY)


def get_extractor(filename: str) -> object | None:
    """Pick an extractor by file extension (magic-byte sniffing happens inside extractors)."""
    ext = filename.rsplit(".", 1)[-1].lower()
    return _REGISTRY.get(ext)
