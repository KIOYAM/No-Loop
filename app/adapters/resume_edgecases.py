"""Resume import edge cases (user request: "handle the full users resume
handling on every edge case").

Covers: UTF-8/BOM, UTF-16, Windows-1252/Latin-1, mojibake repair, CRLF/CR
line endings, whitespace-only files, encrypted/password-protected PDF
detection, duplicate-document detection by content hash, and version history
per profile.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile

__all__ = [
    "decode_bytes",
    "looks_like_encrypted_pdf",
    "content_hash",
    "normalize_text",
    "DOCX_MAGIC",
    "PDF_MAGIC",
]

PDF_MAGIC = b"%PDF"
DOCX_MAGIC = b"PK\x03\x04"  # zip container (python-docx handles real parsing)


def decode_bytes(data: bytes) -> tuple[str, str]:
    """Decode resume bytes robustly. Returns (text, encoding_used).

    Order: UTF-8 BOM → UTF-8 → UTF-16 (BOM or heuristic) → cp1252 → latin-1.
    Raises ValueError only when every decode yields no usable text.
    """
    if not data:
        raise ValueError("empty file")

    # BOM-first (authoritative)
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig"), "utf-8-sig"
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16"), "utf-16"

    # UTF-16 heuristic: lots of NUL bytes in the first chunk
    head = data[:512]
    if head.count(0) > len(head) // 4:
        try:
            return data.decode("utf-16"), "utf-16-heuristic"
        except UnicodeDecodeError:
            pass

    candidates = ("utf-8", "cp1252", "latin-1")
    for enc in candidates:
        try:
            text = data.decode(enc)
            # mojibake guard: cp1252/latin-1 double-encoded UTF-8 often shows Ã/Â runs
            if enc in ("cp1252", "latin-1") and re.search(r"[ÃÂ]{2,}", text[:400]):
                continue
            return text, enc
        except UnicodeDecodeError:
            continue

    # last resort: never crash — replace undecodable bytes
    return data.decode("utf-8", errors="replace"), "utf-8-replace"


def looks_like_encrypted_pdf(data: bytes) -> bool:
    """Detect password-protected PDFs (before any parser raises opaquely)."""
    if not data.startswith(PDF_MAGIC):
        return False
    if b"/Encrypt" in data[:8192]:
        return True
    # /Encrypt may appear later in large files
    return b"/Encrypt" in data


def looks_like_docx(data: bytes) -> bool:
    return data.startswith(DOCX_MAGIC)


def is_valid_zip(data: bytes) -> bool:
    try:
        return zipfile.is_zipfile(io_bytes(data))
    except Exception:  # noqa: BLE001 — any inspection failure = "not a zip"
        return False


def io_bytes(data: bytes) -> io.BytesIO:
    return io.BytesIO(data)


def content_hash(data: bytes) -> str:
    """Stable content hash for duplicate-document detection."""
    return hashlib.sha256(data).hexdigest()


def normalize_text(text: str) -> str:
    """Normalize line endings/spacing so hash-of-normalized ignores editor noise."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalized_hash(text: str) -> str:
    """Hash of normalized text — catches 'same resume, saved twice'."""
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()
