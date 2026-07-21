"""Local embeddings via fastembed (no remote embedding API)."""

from __future__ import annotations

from functools import lru_cache

from fastembed import TextEmbedding

from config import EMBEDDING_MODEL


@lru_cache(maxsize=1)
def _model() -> TextEmbedding:
    return TextEmbedding(model_name=EMBEDDING_MODEL)


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    vectors = list(_model().embed(texts))
    return [v.tolist() if hasattr(v, "tolist") else list(v) for v in vectors]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
