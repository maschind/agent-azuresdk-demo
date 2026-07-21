"""Environment-driven configuration (LLM via Secret on OpenShift)."""

from __future__ import annotations

import os


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None or value == "":
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def optional_env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


# Populated from OpenShift Secret llm-credentials (scripts/create-llm-secret.sh)
LLM_API_KEY = optional_env("LLM_API_KEY", "")
LLM_BASE_URL = optional_env("LLM_BASE_URL", "")
LLM_MODEL = optional_env("LLM_MODEL", "")

DATABASE_URL = optional_env(
    "DATABASE_URL",
    "postgresql://rag:rag@localhost:5432/rag",
)

# Local embeddings (v1/v2); unused when RAG_BACKEND=stack
EMBEDDING_MODEL = optional_env("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
EMBEDDING_DIMS = int(optional_env("EMBEDDING_DIMS", "384"))

CHUNK_SIZE = int(optional_env("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(optional_env("CHUNK_OVERLAP", "120"))
RAG_TOP_K = int(optional_env("RAG_TOP_K", "4"))
MAX_UPLOAD_BYTES = int(optional_env("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))

AGENT_BACKEND = optional_env("AGENT_BACKEND", "direct")  # direct | llamastack | native
MODEL_PROVIDER = optional_env("MODEL_PROVIDER", "litemaas")  # litemaas | vllm | llamastack

# v3: stack | pgvector (default pgvector for v1/v2 images)
RAG_BACKEND = optional_env("RAG_BACKEND", "pgvector")
LLAMA_STACK_BASE_URL = optional_env(
    "LLAMA_STACK_BASE_URL",
    "http://llamastack-demo-service:8321/v1",
)
STACK_VECTOR_STORE_NAME = optional_env("STACK_VECTOR_STORE_NAME", "agent-kb")
STACK_EMBEDDING_MODEL = optional_env(
    "STACK_EMBEDDING_MODEL",
    "sentence-transformers/nomic-ai/nomic-embed-text-v1.5",
)
# When false (v3), hide LiteMaaS/vLLM agent bypasses
ENABLE_PROVIDER_BYPASS = optional_env("ENABLE_PROVIDER_BYPASS", "true").lower() in (
    "1",
    "true",
    "yes",
)

TRUSTYAI_SHIELD_ID = optional_env("TRUSTYAI_SHIELD_ID", "")
MLFLOW_TRACKING_URI = optional_env("MLFLOW_TRACKING_URI", "")
MLFLOW_EXPERIMENT = optional_env("MLFLOW_EXPERIMENT", "agent-azuresdk-demo-ogx-native")
