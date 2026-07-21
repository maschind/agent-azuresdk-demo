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


LLM_API_KEY = optional_env("LLM_API_KEY")
LLM_BASE_URL = optional_env(
    "LLM_BASE_URL",
    "https://litellm-litemaas.apps.prod.rhoai.rh-aiservices-bu.com/v1",
)
LLM_MODEL = optional_env("LLM_MODEL", "Qwen3.6-35B-A3B")

DATABASE_URL = optional_env(
    "DATABASE_URL",
    "postgresql://rag:rag@localhost:5432/rag",
)

# Local embeddings (baked / downloaded in container)
EMBEDDING_MODEL = optional_env("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
EMBEDDING_DIMS = int(optional_env("EMBEDDING_DIMS", "384"))

CHUNK_SIZE = int(optional_env("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(optional_env("CHUNK_OVERLAP", "120"))
RAG_TOP_K = int(optional_env("RAG_TOP_K", "4"))
MAX_UPLOAD_BYTES = int(optional_env("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))

AGENT_BACKEND = optional_env("AGENT_BACKEND", "direct")  # direct | llamastack
MODEL_PROVIDER = optional_env("MODEL_PROVIDER", "litemaas")  # litemaas | vllm
