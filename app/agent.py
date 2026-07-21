"""Chat agent: OpenAI-compatible client → Llama Stack, with one RAG tool."""

from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

import kb
from config import STACK_API_KEY, STACK_BASE_URL, STACK_MODEL
from tracing import span

SYSTEM = (
    "You are a helpful OpenShift AI demo assistant. "
    "When the user asks about uploaded documents, call search_knowledge_base. "
    "Cite filenames. If nothing matches, say so clearly. Keep answers concise."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "Search uploaded documents for passages relevant to the query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language query"},
                },
                "required": ["query"],
            },
        },
    }
]


def _client() -> OpenAI:
    return OpenAI(base_url=STACK_BASE_URL, api_key=STACK_API_KEY)


def _run_tool(name: str, arguments: str) -> str:
    if name != "search_knowledge_base":
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        query = json.loads(arguments or "{}").get("query", "")
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid JSON arguments"})
    if not query:
        return json.dumps({"error": "query is required"})
    with span("search_knowledge_base", "RETRIEVER", {"query": query[:500]}):
        hits = kb.search(query)
    if not hits:
        return json.dumps({"results": [], "message": "No matching documents."})
    return json.dumps({"results": hits, "backend": "stack"})


def run_agent(
    user_text: str, history: list[dict[str, str]] | None = None
) -> dict[str, Any]:
    """One user turn. Returns {answer, tool_traces, model}."""
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM}]
    for item in history or []:
        if item.get("role") in ("user", "assistant") and item.get("content"):
            messages.append({"role": item["role"], "content": item["content"]})
    messages.append({"role": "user", "content": user_text})

    client = _client()
    traces: list[dict[str, str]] = []

    with span("run_agent", "AGENT", {"user_chars": len(user_text)}):
        for _ in range(4):
            with span(
                "llm.complete",
                "CHAT_MODEL",
                {"model": STACK_MODEL, "messages": len(messages)},
            ):
                response = client.chat.completions.create(
                    model=STACK_MODEL,
                    messages=messages,
                    tools=TOOLS,
                    temperature=0.2,
                    max_tokens=2048,
                )
            message = response.choices[0].message
            tool_calls = message.tool_calls or []

            if tool_calls:
                messages.append(message.model_dump(exclude_none=True))
                for call in tool_calls:
                    result = _run_tool(call.function.name, call.function.arguments or "{}")
                    traces.append(
                        {
                            "tool": call.function.name,
                            "arguments": call.function.arguments or "{}",
                            "result": result,
                        }
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": result,
                        }
                    )
                continue

            answer = (message.content or "").strip() or (
                "(Empty model response — try again.)"
            )
            return {
                "answer": answer,
                "tool_traces": traces,
                "model": STACK_MODEL,
            }

    return {
        "answer": "Stopped after maximum tool rounds without a final answer.",
        "tool_traces": traces,
        "model": STACK_MODEL,
    }
