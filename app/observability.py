"""TrustyAI safety + MLflow tracing helpers for v3."""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from typing import Any, Iterator
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from config import (
    LLAMA_STACK_BASE_URL,
    MLFLOW_EXPERIMENT,
    MLFLOW_TRACKING_URI,
    TRUSTYAI_SHIELD_ID,
)

log = logging.getLogger(__name__)


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


def list_shields() -> list[dict[str, Any]]:
    try:
        data = _stack_json("GET", "/shields")
        return list(data.get("data") or [])
    except Exception as exc:  # noqa: BLE001
        log.warning("list_shields failed: %s", exc)
        return []


def run_shield(user_text: str, shield_id: str | None = None) -> dict[str, Any]:
    """Run TrustyAI/Stack safety shield if configured. Returns {ok, detail}."""
    sid = shield_id or TRUSTYAI_SHIELD_ID
    shields = list_shields()
    if not sid and shields:
        sid = shields[0].get("identifier") or shields[0].get("id")
    if not sid:
        return {
            "ok": True,
            "skipped": True,
            "detail": "No TrustyAI/Stack shields registered yet",
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
        # Normalize: violation if violation present / not PASS
        violation = result.get("violation") or result.get("violations")
        blocked = bool(violation)
        return {"ok": not blocked, "skipped": False, "shield_id": sid, "detail": result}
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
