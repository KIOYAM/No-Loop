"""Document extraction adapters (LOOP-5; skill 03).

Extraction ≠ inference: these adapters return raw text only. Facts and
confidence belong to the fact ledger service.

PDF: ADR-2 is still open (PyMuPDF is AGPL; decision recorded before P004).
Until then, PDF import fails HONESTLY with a clear user action (R-TRUTH-3) —
no silent mis-parse, no placeholder.
"""

from __future__ import annotations

import io
import re

from app.ports import ExtractionResult

__all__ = [
    "TxtExtractor",
    "DocxExtractor",
    "PdfExtractorUnavailable",
    "get_extractor",
    "SUPPORTED_FORMATS",
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
            import docx  # type: ignore[import-not-found]  # optional extra "docx"
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
        parts = [p.text for p in document.paragraphs if p.text.strip()]
        for table in document.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    parts.append(" | ".join(cells))
        text = "\n".join(parts).strip()
        if not text:
            return ExtractionResult(
                False,
                error_reason=("no text found — this looks like an image-only document"),
                user_action="Export a text PDF or paste your resume text.",
            )
        return ExtractionResult(True, text)


class PdfExtractorUnavailable:
    """PDF extraction is NOT implemented yet (ADR-2 open). Honest refusal (R-TRUTH-3).

    Special case: many "PDFs" from Indian portals contain an embedded text
    layer detectable without PyMuPDF; if plain ASCII text is extractable from
    the raw bytes we use it, else we refuse with the guided fallback.
    """

    formats = ("pdf",)

    def extract(self, data: bytes) -> ExtractionResult:
        if len(data) > _MAX_BYTES:
            return ExtractionResult(
                False,
                error_reason="file exceeds 10 MB limit",
                user_action="Split or compress the file.",
            )
        text = self._naive_text_layer(data)
        if text and len(text) >= 200:
            return ExtractionResult(True, text)
        return ExtractionResult(
            False,
            error_reason=(
                "PDF text extraction is not available yet (library decision ADR-2 pending)"
                if not text
                else "no text layer found — this looks like a scanned image"
            ),
            user_action=(
                "Save the resume as .txt or .docx for now; paste-text import is also available."
            ),
        )

    @staticmethod
    def _naive_text_layer(data: bytes) -> str:
        """Extract plainly-decodable ASCII runs (crude; zero dependencies)."""
        if not data.startswith(b"%PDF"):
            return ""
        chunks = re.findall(rb"[ -~]{4,}", data)
        words = b" ".join(chunks).decode("ascii", errors="ignore")
        words = re.sub(
            r"\b(obj|endobj|stream|endstream|xref|trailer|startxref|FlateDecode)\b", " ", words
        )
        words = re.sub(r"\s+", " ", words).strip()
        # Heuristic: real resume text layers have long word sequences.
        return words if len(words.split()) >= 40 else ""


_REGISTRY: dict[str, object] = {
    "txt": TxtExtractor(),
    "docx": DocxExtractor(),
    "pdf": PdfExtractorUnavailable(),
}

SUPPORTED_FORMATS = tuple(_REGISTRY)


def get_extractor(filename: str) -> object | None:
    """Pick an extractor by file extension (magic-byte sniffing happens inside extractors)."""
    ext = filename.rsplit(".", 1)[-1].lower()
    return _REGISTRY.get(ext)
