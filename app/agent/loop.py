"""Azure AI Inference chat + tool-calling agent loop (LiteMaaS / OpenAI-compatible)."""

from __future__ import annotations

import json
from typing import Any

from azure.ai.inference import ChatCompletionsClient
from azure.ai.inference.models import (
    AssistantMessage,
    ChatCompletionsToolDefinition,
    FunctionDefinition,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from azure.core.credentials import AzureKeyCredential

import config
from tools.rag import TOOL_DEFINITION, run_tool

SYSTEM_PROMPT = (
    "You are a helpful demo assistant for Red Hat OpenShift AI. "
    "When the user asks about uploaded documents or facts that may be in the knowledge base, "
    "call the search_knowledge_base tool. Cite filenames when you use retrieved passages. "
    "If the knowledge base is empty or has no match, say so clearly."
)


def _endpoint() -> str:
    return config.LLM_BASE_URL.rstrip("/")


def _client() -> ChatCompletionsClient:
    if not config.LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY is not set")
    return ChatCompletionsClient(
        endpoint=_endpoint(),
        credential=AzureKeyCredential(config.LLM_API_KEY),
    )


def _tools() -> list[ChatCompletionsToolDefinition]:
    fn = TOOL_DEFINITION["function"]
    return [
        ChatCompletionsToolDefinition(
            function=FunctionDefinition(
                name=fn["name"],
                description=fn["description"],
                parameters=fn["parameters"],
            )
        )
    ]


def _message_content(msg: Any) -> str:
    content = getattr(msg, "content", None)
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return str(content)


def run_agent(user_text: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """
    Run one user turn. Returns {answer, tool_traces, messages}.
    history items: {role: user|assistant, content: str}
    """
    client = _client()
    messages: list[Any] = [SystemMessage(content=SYSTEM_PROMPT)]
    for item in history or []:
        role = item.get("role")
        content = item.get("content", "")
        if role == "user":
            messages.append(UserMessage(content=content))
        elif role == "assistant":
            messages.append(AssistantMessage(content=content))
    messages.append(UserMessage(content=user_text))

    tool_traces: list[dict[str, Any]] = []
    max_rounds = 4

    for _ in range(max_rounds):
        response = client.complete(
            messages=messages,
            model=config.LLM_MODEL,
            tools=_tools(),
            temperature=0.2,
        )
        choice = response.choices[0]
        message = choice.message
        tool_calls = getattr(message, "tool_calls", None) or []

        if tool_calls:
            # Append assistant message with tool calls
            messages.append(message)
            for call in tool_calls:
                fn = call.function
                name = fn.name
                args = fn.arguments or "{}"
                result = run_tool(name, args)
                tool_traces.append(
                    {
                        "tool": name,
                        "arguments": args,
                        "result": result,
                    }
                )
                messages.append(
                    ToolMessage(
                        tool_call_id=call.id,
                        content=result,
                    )
                )
            continue

        answer = _message_content(message)
        return {
            "answer": answer,
            "tool_traces": tool_traces,
            "model": config.LLM_MODEL,
            "base_url": config.LLM_BASE_URL,
        }

    return {
        "answer": "Stopped after maximum tool rounds without a final answer.",
        "tool_traces": tool_traces,
        "model": config.LLM_MODEL,
        "base_url": config.LLM_BASE_URL,
    }


def ping_llm() -> str:
    client = _client()
    response = client.complete(
        messages=[UserMessage(content="Reply with OK")],
        model=config.LLM_MODEL,
        temperature=0,
        max_tokens=8,
    )
    return _message_content(response.choices[0].message)
