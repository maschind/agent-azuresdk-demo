"""Knowledge base on Llama Stack vector stores (files + search)."""

from __future__ import annotations

import json
import mimetypes
import time
import uuid
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from config import (
    RAG_TOP_K,
    STACK_BASE_URL,
    STACK_EMBEDDING_MODEL,
    STACK_VECTOR_STORE,
)


def _url(path: str) -> str:
    return STACK_BASE_URL.rstrip("/") + path


def _json(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(
        _url(path),
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
        raise RuntimeError(f"Stack {method} {path} → {exc.code}: {body}") from exc


def ensure_store(*, recreate: bool = False) -> str:
    for item in (_json("GET", "/vector_stores").get("data") or []):
        if item.get("name") == STACK_VECTOR_STORE:
            if not recreate:
                return item["id"]
            try:
                _json("DELETE", f"/vector_stores/{item['id']}")
            except Exception:  # noqa: BLE001
                pass
            break
    created = _json(
        "POST",
        "/vector_stores",
        {
            "name": STACK_VECTOR_STORE,
            "metadata": {"embedding_model": STACK_EMBEDDING_MODEL},
        },
    )
    return created["id"]


def _upload(filename: str, data: bytes, content_type: str | None) -> str:
    ctype = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    boundary = "----Bound" + uuid.uuid4().hex
    body = b"".join(
        [
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
    )
    req = Request(
        _url("/files"),
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urlopen(req, timeout=180) as resp:
        return json.load(resp)["id"]


def _wait_ready(store_id: str, file_id: str, timeout_s: float = 120) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        for item in (_json("GET", f"/vector_stores/{store_id}/files").get("data") or []):
            if item.get("id") != file_id:
                continue
            status = item.get("status")
            if status in ("completed", "ready"):
                return
            if status in ("failed", "cancelled"):
                raise RuntimeError(f"Ingest failed for {file_id}: {status}")
        time.sleep(1.5)
    raise TimeoutError(f"Timed out waiting for {file_id}")


def ingest(filename: str, data: bytes, content_type: str | None = None) -> dict[str, str]:
    store_id = ensure_store()
    file_id = _upload(filename, data, content_type)
    try:
        _json("POST", f"/vector_stores/{store_id}/files", {"file_id": file_id})
        _wait_ready(store_id, file_id)
    except Exception:  # noqa: BLE001
        # Stale store after Stack/Milvus restart
        store_id = ensure_store(recreate=True)
        _json("POST", f"/vector_stores/{store_id}/files", {"file_id": file_id})
        _wait_ready(store_id, file_id)
    return {"store_id": store_id, "file_id": file_id, "filename": filename}


def list_docs() -> list[dict[str, Any]]:
    store_id = ensure_store()
    docs: list[dict[str, Any]] = []
    for item in (_json("GET", f"/vector_stores/{store_id}/files").get("data") or []):
        fid = item["id"]
        filename = item.get("filename") or fid
        if filename == fid:
            try:
                meta = _json("GET", f"/files/{fid}")
                filename = meta.get("filename") or fid
            except Exception:  # noqa: BLE001
                pass
        docs.append(
            {
                "id": fid,
                "filename": filename,
                "byte_size": item.get("usage_bytes") or 0,
                "status": item.get("status"),
            }
        )
    return docs


def delete(file_id: str) -> None:
    store_id = ensure_store()
    for path in (f"/vector_stores/{store_id}/files/{file_id}", f"/files/{file_id}"):
        try:
            _json("DELETE", path)
        except Exception:  # noqa: BLE001
            pass


def search(query: str, top_k: int | None = None) -> list[dict[str, Any]]:
    store_id = ensure_store()
    result = _json(
        "POST",
        f"/vector_stores/{store_id}/search",
        {"query": query, "max_num_results": top_k or RAG_TOP_K},
    )
    hits: list[dict[str, Any]] = []
    for item in result.get("data") or []:
        content = item.get("content")
        if isinstance(content, list):
            text = " ".join(
                p.get("text", "") if isinstance(p, dict) else str(p) for p in content
            )
        else:
            text = str(content or "")
        hits.append(
            {
                "filename": item.get("filename") or item.get("file_id"),
                "score": round(float(item.get("score") or 0), 4),
                "content": text,
            }
        )
    return hits
