"""Postgres + pgvector persistence for documents and chunks."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import psycopg
from pgvector.psycopg import register_vector

from config import DATABASE_URL, EMBEDDING_DIMS


def connect() -> psycopg.Connection:
    conn = psycopg.connect(DATABASE_URL, autocommit=False)
    register_vector(conn)
    return conn


def init_schema() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id UUID PRIMARY KEY,
                    filename TEXT NOT NULL,
                    content_type TEXT,
                    byte_size INTEGER NOT NULL,
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL
                )
                """
            )
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS chunks (
                    id UUID PRIMARY KEY,
                    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    embedding vector({EMBEDDING_DIMS}) NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS chunks_document_id_idx
                ON chunks(document_id)
                """
            )
        conn.commit()


def list_documents() -> list[dict[str, Any]]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, filename, content_type, byte_size, chunk_count, created_at
                FROM documents
                ORDER BY created_at DESC
                """
            )
            rows = cur.fetchall()
    return [
        {
            "id": str(r[0]),
            "filename": r[1],
            "content_type": r[2],
            "byte_size": r[3],
            "chunk_count": r[4],
            "created_at": r[5].isoformat() if r[5] else "",
        }
        for r in rows
    ]


def insert_document(
    filename: str,
    content_type: str,
    byte_size: int,
    chunks: list[str],
    embeddings: list[list[float]],
) -> str:
    doc_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO documents (id, filename, content_type, byte_size, chunk_count, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (doc_id, filename, content_type, byte_size, len(chunks), now),
            )
            for idx, (text, emb) in enumerate(zip(chunks, embeddings)):
                cur.execute(
                    """
                    INSERT INTO chunks (id, document_id, chunk_index, content, embedding)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (uuid.uuid4(), doc_id, idx, text, emb),
                )
        conn.commit()
    return str(doc_id)


def delete_document(document_id: str) -> bool:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM documents WHERE id = %s", (document_id,))
            deleted = cur.rowcount > 0
        conn.commit()
    return deleted


def similarity_search(query_embedding: list[float], top_k: int) -> list[dict[str, Any]]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.content, d.filename, c.chunk_index,
                       1 - (c.embedding <=> %s::vector) AS score
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                ORDER BY c.embedding <=> %s::vector
                LIMIT %s
                """,
                (query_embedding, query_embedding, top_k),
            )
            rows = cur.fetchall()
    return [
        {
            "content": r[0],
            "filename": r[1],
            "chunk_index": r[2],
            "score": float(r[3]) if r[3] is not None else 0.0,
        }
        for r in rows
    ]
