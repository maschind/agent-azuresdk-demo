"""Document text extraction and chunking."""

from __future__ import annotations

import io
import re

from pypdf import PdfReader

from config import CHUNK_OVERLAP, CHUNK_SIZE, MAX_UPLOAD_BYTES


ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf"}


def extension_ok(filename: str) -> bool:
    lower = filename.lower()
    return any(lower.endswith(ext) for ext in ALLOWED_EXTENSIONS)


def extract_text(filename: str, data: bytes) -> str:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"File exceeds max size of {MAX_UPLOAD_BYTES} bytes")
    lower = filename.lower()
    if lower.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        parts = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        text = "\n".join(parts)
    else:
        text = data.decode("utf-8", errors="replace")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        raise ValueError("No extractable text in document")
    return text


def chunk_text(text: str) -> list[str]:
    if len(text) <= CHUNK_SIZE:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(0, end - CHUNK_OVERLAP)
    return chunks
