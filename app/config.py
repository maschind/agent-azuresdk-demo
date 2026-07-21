"""v3 config — OpenShift AI / Llama Stack only."""

from __future__ import annotations

import os


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


# Llama Stack (chat + RAG)
STACK_BASE_URL = env("LLAMA_STACK_BASE_URL", "http://llamastack-demo-service:8321/v1")
STACK_MODEL = env("LLAMA_STACK_MODEL", "vllm-inference/llama-32-3b-instruct")
STACK_API_KEY = env("LLM_API_KEY", "EMPTY") or "EMPTY"
STACK_VECTOR_STORE = env("STACK_VECTOR_STORE_NAME", "agent-kb")
STACK_EMBEDDING_MODEL = env(
    "STACK_EMBEDDING_MODEL",
    "sentence-transformers/nomic-ai/nomic-embed-text-v1.5",
)
RAG_TOP_K = int(env("RAG_TOP_K", "4"))
MAX_UPLOAD_BYTES = int(env("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))

# TrustyAI Guardrails Orchestrator
TRUSTYAI_ORCHESTRATOR_URL = env(
    "TRUSTYAI_ORCHESTRATOR_URL",
    "https://guardrails-service.my-first-model.svc:8032",
)
TRUSTYAI_SHIELD_ID = env("TRUSTYAI_SHIELD_ID", "built-in-detector")

# MLflow (RHOAI)
MLFLOW_TRACKING_URI = env(
    "MLFLOW_TRACKING_URI",
    "https://mlflow.redhat-ods-applications.svc:8443",
)
MLFLOW_TRACKING_AUTH = env("MLFLOW_TRACKING_AUTH", "kubernetes-namespaced")
MLFLOW_WORKSPACE = env("MLFLOW_WORKSPACE", "agent-azuresdk-demo-ogx-native")
MLFLOW_EXPERIMENT = env("MLFLOW_EXPERIMENT", "agent-azuresdk-demo-ogx-native")
MLFLOW_UI_URL = env("MLFLOW_UI_URL", "")
MLFLOW_TRACING = env("MLFLOW_TRACING_ENABLED", "true").lower() in ("1", "true", "yes")
