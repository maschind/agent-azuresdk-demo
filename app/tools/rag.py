"""RAG tool: search_knowledge_base (pgvector or Llama Stack vector store)."""

from __future__ import annotations

import json
from typing import Any

from config import RAG_BACKEND, RAG_TOP_K

TOOL_NAME = "search_knowledge_base"

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": (
            "Search the uploaded knowledge base for passages relevant to the query. "
            "Use this when the user asks about content that may be in uploaded documents."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query",
                }
            },
            "required": ["query"],
        },
    },
}


def search_knowledge_base(query: str, top_k: int | None = None) -> str:
    k = top_k or RAG_TOP_K
    if RAG_BACKEND == "stack":
        from stack_kb import search

        hits = search(query, k)
    else:
        from db import similarity_search
        from embeddings import embed_query

        embedding = embed_query(query)
        hits = similarity_search(embedding, k)

    if not hits:
        return json.dumps({"results": [], "message": "No documents in the knowledge base."})
    payload: list[dict[str, Any]] = [
        {
            "filename": h["filename"],
            "chunk_index": h.get("chunk_index", 0),
            "score": round(float(h["score"]), 4),
            "content": h["content"],
        }
        for h in hits
    ]
    return json.dumps({"results": payload, "backend": RAG_BACKEND})


def run_tool(name: str, arguments_json: str) -> str:
    if name != TOOL_NAME:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        args = json.loads(arguments_json or "{}")
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid tool arguments JSON"})
    query = args.get("query", "")
    if not query:
        return json.dumps({"error": "query is required"})
    return search_knowledge_base(query)
