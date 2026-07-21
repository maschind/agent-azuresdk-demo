"""MLflow runs + GenAI spans (RHOAI tracking server)."""

from __future__ import annotations

import logging
from contextlib import contextmanager, nullcontext
from typing import Any, Iterator

from config import (
    MLFLOW_EXPERIMENT,
    MLFLOW_TRACING,
    MLFLOW_TRACKING_URI,
    MLFLOW_WORKSPACE,
)

log = logging.getLogger(__name__)
_ready = False


def _configure() -> bool:
    global _ready
    if not MLFLOW_TRACKING_URI:
        return False
    try:
        import mlflow

        if not _ready:
            mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
            if MLFLOW_WORKSPACE and hasattr(mlflow, "set_workspace"):
                try:
                    mlflow.set_workspace(MLFLOW_WORKSPACE)
                except Exception as exc:  # noqa: BLE001
                    log.warning("set_workspace failed: %s", exc)
            mlflow.set_experiment(MLFLOW_EXPERIMENT)
            _ready = True
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("MLflow configure failed: %s", exc)
        return False


@contextmanager
def span(
    name: str,
    span_type: str = "UNKNOWN",
    inputs: dict[str, Any] | None = None,
) -> Iterator[Any]:
    if not (MLFLOW_TRACING and _configure()):
        yield None
        return
    try:
        import mlflow

        with mlflow.start_span(name=name, span_type=span_type) as sp:
            if inputs is not None and sp is not None:
                sp.set_inputs(inputs)
            yield sp
    except Exception as exc:  # noqa: BLE001
        log.warning("span %s failed: %s", name, exc)
        yield None


@contextmanager
def chat_run(prompt: str, model: str) -> Iterator[dict[str, Any]]:
    """One chat turn → MLflow run + root AGENT span."""
    meta: dict[str, Any] = {"enabled": False, "tracing": False}
    if not MLFLOW_TRACKING_URI or not _configure():
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
            mlflow.log_text(prompt[:4000], "prompt.txt")

            root_cm = (
                mlflow.start_span(name="agent-chat", span_type=SpanType.AGENT)
                if MLFLOW_TRACING
                else nullcontext(None)
            )
            with root_cm as root:
                meta["tracing"] = root is not None
                if root is not None:
                    root.set_inputs({"prompt": prompt[:2000], "model": model})
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
            flush = getattr(mlflow, "flush_trace_async_logging", None)
            if callable(flush):
                try:
                    flush()
                except Exception as exc:  # noqa: BLE001
                    log.warning("trace flush failed: %s", exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("MLflow run failed: %s", exc)
        meta["error"] = str(exc)
        yield meta
