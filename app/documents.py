"""Upload helpers (type / size checks). Stack stores the raw file."""

from __future__ import annotations

from config import MAX_UPLOAD_BYTES

ALLOWED = {".txt", ".md", ".pdf"}


def extension_ok(filename: str) -> bool:
    lower = filename.lower()
    return any(lower.endswith(ext) for ext in ALLOWED)


def validate_upload(filename: str, data: bytes) -> None:
    if not extension_ok(filename):
        raise ValueError("Unsupported type (use .txt, .md, or .pdf)")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"File exceeds {MAX_UPLOAD_BYTES} bytes")
    if not data:
        raise ValueError("Empty file")
