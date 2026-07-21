"""TrustyAI safety + MLflow run/trace helpers for v3."""

from __future__ import annotations

import json
import logging
import ssl
from contextlib import contextmanager, nullcontext
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import (
    LLAMA_STACK_BASE_URL,
    MLFLOW_EXPERIMENT,
    MLFLOW_TRACING_ENABLED,
    MLFLOW_TRACKING_URI,
    MLFLOW_WORKSPACE,
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
_mlflow_configured = False


def tracing_enabled() -> bool:
    return bool(MLFLOW_TRACING_ENABLED and MLFLOW_TRACKING_URI)


def configure_mlflow() -> bool:
    """Set tracking URI + experiment once. Returns True if ready."""
    global _mlflow_configured
    if not MLFLOW_TRACKING_URI:
        return False
    try:
        import mlflow

        if not _mlflow_configured:
            mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
            if MLFLOW_WORKSPACE and hasattr(mlflow, "set_workspace"):
                try:
                    mlflow.set_workspace(MLFLOW_WORKSPACE)
                except Exception as exc:  # noqa: BLE001
                    log.warning(
                        "mlflow.set_workspace(%s) failed: %s", MLFLOW_WORKSPACE, exc
                    )
            mlflow.set_experiment(MLFLOW_EXPERIMENT)
            _mlflow_configured = True
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("MLflow configure failed: %s", exc)
        return False


@contextmanager
def mlflow_span(
    name: str,
    span_type: str = "UNKNOWN",
    inputs: dict[str, Any] | None = None,
) -> Iterator[Any]:
    """Create an MLflow span when tracing is on; otherwise a no-op context."""
    if not (tracing_enabled() and configure_mlflow()):
        yield None
        return
    try:
        import mlflow

        with mlflow.start_span(name=name, span_type=span_type) as span:
            if inputs is not None and span is not None:
                span.set_inputs(inputs)
            yield span
    except Exception as exc:  # noqa: BLE001
        log.warning("MLflow span %s failed: %s", name, exc)
        yield None


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
    with mlflow_span(
        "trustyai-shield",
        span_type="TOOL",
        inputs={"shield_id": sid, "chars": len(user_text)},
    ) as span:
        out = _run_shield_impl(user_text, sid)
        if span is not None:
            span.set_outputs(
                {
                    "ok": out.get("ok"),
                    "blocked": out.get("blocked"),
                    "skipped": out.get("skipped"),
                    "via": out.get("via"),
                }
            )
        return out


def _run_shield_impl(user_text: str, sid: str) -> dict[str, Any]:
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
    """Log a chat turn as an MLflow run and (when enabled) a GenAI root span/trace."""
    meta: dict[str, Any] = {"enabled": False, "tracing": False}
    if not MLFLOW_TRACKING_URI or not configure_mlflow():
        yield meta
        return
    try:
        import mlflow
        from mlflow.entities import SpanType

        with mlflow.start_run(run_name="agent-chat") as run:
            meta["enabled"] = True
            meta["run_id"] = run.info.run_id
            mlflow.log_param("model", model)
            mlflow.log_param("prompt_chars", len(prompt))
            mlflow.log_param("tracing", tracing_enabled())
            mlflow.log_text(prompt[:4000], "prompt.txt")

            root_cm = (
                mlflow.start_span(
                    name="agent-chat",
                    span_type=SpanType.AGENT,
                )
                if tracing_enabled()
                else nullcontext(None)
            )
            with root_cm as root:
                meta["tracing"] = tracing_enabled() and root is not None
                if root is not None:
                    root.set_inputs({"prompt": prompt[:2000], "model": model})
                    # LiveSpan.request_id is available while the span is open
                    meta["trace_id"] = getattr(root, "request_id", None)
                yield meta
                if root is not None:
                    root.set_outputs(
                        {
                            "answer": str(meta.get("answer", ""))[:2000],
                            "tool_calls": meta.get("tool_calls"),
                            "shield_ok": meta.get("shield_ok"),
                        }
                    )

            if meta.get("trace_id"):
                mlflow.log_param("trace_id", meta["trace_id"])
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
