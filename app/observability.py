"""TrustyAI safety + MLflow tracing helpers for v3."""

from __future__ import annotations

import json
import logging
import ssl
from contextlib import contextmanager
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import (
    LLAMA_STACK_BASE_URL,
    MLFLOW_EXPERIMENT,
    MLFLOW_TRACKING_URI,
    TRUSTYAI_ORCHESTRATOR_URL,
    TRUSTYAI_SHIELD_ID,
)

log = logging.getLogger(__name__)

_DEFAULT_DETECTOR = "built-in-detector"
_PII_REGEX = {
    "email": {},
    "us-social-security-number": {},
    "credit-card": {},
}


def _stack_json(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    base = LLAMA_STACK_BASE_URL.rstrip("/")
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(
        base + path,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method=method,
    )
    with urlopen(req, timeout=60) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else {}


def _go_json(path: str, payload: dict[str, Any]) -> Any:
    """Call TrustyAI Guardrails Orchestrator (TLS, often self-signed)."""
    base = TRUSTYAI_ORCHESTRATOR_URL.rstrip("/")
    data = json.dumps(payload).encode()
    req = Request(
        base + path,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    ctx = ssl._create_unverified_context()
    with urlopen(req, timeout=60, context=ctx) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else {}


def list_shields() -> list[dict[str, Any]]:
    try:
        data = _stack_json("GET", "/shields")
        return list(data.get("data") or [])
    except Exception as exc:  # noqa: BLE001
        log.warning("list_shields failed: %s", exc)
        return []


def _shield_params(sid: str) -> dict[str, Any]:
    return {
        "type": "content",
        "message_types": ["user", "system"],
        "confidence_threshold": 0.5,
        "verify_ssl": False,
        "detectors": {sid: {"regex": dict(_PII_REGEX)}},
    }


def ensure_shield(shield_id: str | None = None) -> str | None:
    """Best-effort Stack shield registration (Stack may drop nested detector params)."""
    sid = (shield_id or TRUSTYAI_SHIELD_ID or _DEFAULT_DETECTOR).strip()
    if not sid:
        return None
    for s in list_shields():
        if (s.get("identifier") or s.get("id")) == sid:
            return sid
    try:
        _stack_json(
            "POST",
            "/shields",
            {
                "shield_id": sid,
                "provider_id": "trustyai_fms",
                "provider_shield_id": sid,
                "params": _shield_params(sid),
            },
        )
        return sid
    except Exception as exc:  # noqa: BLE001
        log.warning("ensure_shield(%s) failed: %s", sid, exc)
        return None


def _run_shield_via_orchestrator(user_text: str, detector_id: str) -> dict[str, Any] | None:
    if not TRUSTYAI_ORCHESTRATOR_URL:
        return None
    try:
        result = _go_json(
            "/api/v2/text/detection/content",
            {
                "content": user_text,
                "detectors": {detector_id: {"regex": dict(_PII_REGEX)}},
            },
        )
        detections = list(result.get("detections") or [])
        blocked = len(detections) > 0
        return {
            "ok": not blocked,
            "skipped": False,
            "blocked": blocked,
            "shield_id": detector_id,
            "via": "guardrails-orchestrator",
            "detail": result,
        }
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        log.warning("Guardrails Orchestrator call failed: %s", exc)
        return None


def run_shield(user_text: str, shield_id: str | None = None) -> dict[str, Any]:
    """Run TrustyAI safety check. Prefer direct GO (reliable PII regex); Stack as fallback."""
    sid = (shield_id or TRUSTYAI_SHIELD_ID or _DEFAULT_DETECTOR).strip()

    direct = _run_shield_via_orchestrator(user_text, sid)
    if direct is not None:
        return direct

    ensure_shield(sid)
    shields = list_shields()
    if not sid and shields:
        sid = shields[0].get("identifier") or shields[0].get("id") or ""
    if not sid:
        return {
            "ok": True,
            "skipped": True,
            "detail": "No TrustyAI orchestrator URL or Stack shields configured",
        }
    try:
        result = _stack_json(
            "POST",
            "/safety/run-shield",
            {
                "shield_id": sid,
                "messages": [{"role": "user", "content": user_text}],
            },
        )
        wrapper = result.get("violation") or {}
        meta = wrapper.get("metadata") or {}
        summary = meta.get("summary") or {}
        status = (meta.get("status") or "").lower()
        detections = int(summary.get("total_detections") or 0)
        blocked = status in {"violation", "failed", "fail"} or detections > 0
        return {
            "ok": not blocked,
            "skipped": False,
            "blocked": blocked,
            "shield_id": sid,
            "via": "llama-stack",
            "detail": result,
        }
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {"ok": True, "skipped": True, "detail": f"shield HTTP {exc.code}: {body}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": True, "skipped": True, "detail": str(exc)}


@contextmanager
def mlflow_chat_run(prompt: str, model: str) -> Iterator[dict[str, Any]]:
    """Context manager that logs a chat turn to MLflow when tracking URI is set."""
    meta: dict[str, Any] = {"enabled": False}
    if not MLFLOW_TRACKING_URI:
        yield meta
        return
    try:
        import mlflow

        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        mlflow.set_experiment(MLFLOW_EXPERIMENT)
        with mlflow.start_run(run_name="agent-chat") as run:
            meta["enabled"] = True
            meta["run_id"] = run.info.run_id
            mlflow.log_param("model", model)
            mlflow.log_param("prompt_chars", len(prompt))
            mlflow.log_text(prompt[:4000], "prompt.txt")
            yield meta
            if "answer" in meta:
                mlflow.log_text(str(meta["answer"])[:8000], "answer.txt")
                mlflow.log_metric("answer_chars", len(str(meta["answer"])))
            if "tool_calls" in meta:
                mlflow.log_metric("tool_calls", int(meta["tool_calls"]))
            if "shield_ok" in meta:
                mlflow.log_param("shield_ok", meta["shield_ok"])
    except Exception as exc:  # noqa: BLE001
        log.warning("MLflow logging failed: %s", exc)
        meta["error"] = str(exc)
        yield meta
