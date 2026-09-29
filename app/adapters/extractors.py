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
    "PdfExtractor",
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


class PdfExtractor:
    """PDF text extraction via pypdf (BSD-3-Clause — ADR-2 decision 2026-09-29).

    pypdf was chosen over PyMuPDF (AGPL — contamination risk per R-TRUTH-6) and
    pdfminer.six (MIT but slower). Password-protected files are detected by
    pypdf and refused with a guided user action. Scanned/image-only PDFs yield
    no text and are refused honestly (no OCR in v0.1, spec §3).
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
            for page in reader.pages[:50]:  # bounded: resumes never need 50+ pages
                try:
                    parts.append(page.extract_text() or "")
                except Exception:  # noqa: BLE001, S112 - one bad page must not kill the doc
                    continue
            text = "\n".join(parts).strip()
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
        return ExtractionResult(True, text)

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
    "pdf": PdfExtractor(),
}

SUPPORTED_FORMATS = tuple(_REGISTRY)


def get_extractor(filename: str) -> object | None:
    """Pick an extractor by file extension (magic-byte sniffing happens inside extractors)."""
    ext = filename.rsplit(".", 1)[-1].lower()
    return _REGISTRY.get(ext)
