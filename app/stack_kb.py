"""Llama Stack OpenAI-compatible vector store KB (files + search)."""

from __future__ import annotations

import json
import mimetypes
import time
import uuid
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from config import (
    LLAMA_STACK_BASE_URL,
    RAG_TOP_K,
    STACK_EMBEDDING_MODEL,
    STACK_VECTOR_STORE_NAME,
)


def _base() -> str:
    return LLAMA_STACK_BASE_URL.rstrip("/")


def _json(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(
        _base() + path,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method=method,
    )
    try:
        with urlopen(req, timeout=120) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Stack {method} {path} failed ({exc.code}): {body}") from exc


def ensure_vector_store() -> str:
    """Return vector store id (create once; id cached via list-by-name)."""
    listing = _json("GET", "/vector_stores")
    for item in listing.get("data") or []:
        if item.get("name") == STACK_VECTOR_STORE_NAME:
            return item["id"]
    created = _json(
        "POST",
        "/vector_stores",
        {
            "name": STACK_VECTOR_STORE_NAME,
            "metadata": {"embedding_model": STACK_EMBEDDING_MODEL},
        },
    )
    return created["id"]


def upload_file(filename: str, data: bytes, content_type: str | None = None) -> str:
    ctype = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    boundary = "----Bound" + uuid.uuid4().hex
    parts = [
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="purpose"\r\n\r\n'
            f"assistants\r\n"
        ).encode(),
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n"
        ).encode(),
        data,
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    body = b"".join(parts)
    req = Request(
        _base() + "/files",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urlopen(req, timeout=180) as resp:
        return json.load(resp)["id"]


def attach_file(vector_store_id: str, file_id: str) -> dict[str, Any]:
    return _json("POST", f"/vector_stores/{vector_store_id}/files", {"file_id": file_id})


def wait_file_ready(vector_store_id: str, file_id: str, timeout_s: float = 120) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        listing = _json("GET", f"/vector_stores/{vector_store_id}/files")
        for item in listing.get("data") or []:
            if item.get("id") == file_id:
                status = item.get("status")
                if status in ("completed", "ready"):
                    return
                if status in ("failed", "cancelled"):
                    raise RuntimeError(f"Vector store file {file_id} status={status}")
        time.sleep(1.5)
    raise TimeoutError(f"Timed out waiting for file {file_id} in vector store")


def ingest_document(filename: str, data: bytes, content_type: str | None = None) -> dict[str, str]:
    vs_id = ensure_vector_store()
    file_id = upload_file(filename, data, content_type)
    attach_file(vs_id, file_id)
    wait_file_ready(vs_id, file_id)
    return {"vector_store_id": vs_id, "file_id": file_id, "filename": filename}


def list_documents() -> list[dict[str, Any]]:
    vs_id = ensure_vector_store()
    listing = _json("GET", f"/vector_stores/{vs_id}/files")
    out: list[dict[str, Any]] = []
    for item in listing.get("data") or []:
        fid = item.get("id")
        # filename may only appear after content metadata fetch; use id fallback
        filename = item.get("filename") or (item.get("attributes") or {}).get("filename") or fid
        out.append(
            {
                "id": fid,
                "filename": filename,
                "chunk_count": 1,
                "byte_size": item.get("usage_bytes") or 0,
                "status": item.get("status"),
            }
        )
    # Enrich filenames from /v1/files when missing
    for doc in out:
        if doc["filename"] == doc["id"]:
            try:
                meta = _json("GET", f"/files/{doc['id']}")
                doc["filename"] = meta.get("filename") or doc["id"]
                doc["byte_size"] = meta.get("bytes") or doc["byte_size"]
            except Exception:  # noqa: BLE001
                pass
    return out


def delete_document(file_id: str) -> None:
    vs_id = ensure_vector_store()
    try:
        _json("DELETE", f"/vector_stores/{vs_id}/files/{file_id}")
    except Exception:  # noqa: BLE001
        pass
    try:
        _json("DELETE", f"/files/{file_id}")
    except Exception:  # noqa: BLE001
        pass


def search(query: str, top_k: int | None = None) -> list[dict[str, Any]]:
    vs_id = ensure_vector_store()
    k = top_k or RAG_TOP_K
    result = _json(
        "POST",
        f"/vector_stores/{vs_id}/search",
        {"query": query, "max_num_results": k},
    )
    hits: list[dict[str, Any]] = []
    for item in result.get("data") or []:
        content = item.get("content")
        if isinstance(content, list):
            text = " ".join(
                part.get("text", "") if isinstance(part, dict) else str(part) for part in content
            )
        else:
            text = str(content or item.get("text") or "")
        hits.append(
            {
                "filename": item.get("filename") or item.get("file_id"),
                "chunk_index": 0,
                "score": float(item.get("score") or 0),
                "content": text,
                "file_id": item.get("file_id"),
            }
        )
    return hits
