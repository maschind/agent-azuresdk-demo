"""Azure AI Inference chat + tool-calling agent loop (LiteMaaS / OpenAI-compatible)."""

from __future__ import annotations

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
from observability import mlflow_span
from tools.rag import TOOL_DEFINITION, run_tool

SYSTEM_PROMPT = (
    "You are a helpful demo assistant for Red Hat OpenShift AI. "
    "When the user asks about uploaded documents or facts that may be in the knowledge base, "
    "call the search_knowledge_base tool. Cite filenames when you use retrieved passages. "
    "If the knowledge base is empty or has no match, say so clearly. "
    "Keep answers concise."
)


def _endpoint() -> str:
    return config.LLM_BASE_URL.rstrip("/")


def _client() -> ChatCompletionsClient:
    """Build Azure AI Inference client.

    AzureKeyCredential sends ``Authorization: Bearer <key>`` (and ``api-key``)
    without requiring HTTPS — needed for in-cluster Llama Stack / vLLM (http://).
    TokenCredential path enforces TLS and breaks those endpoints.
    """
    if not config.LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY is not set")
    # In-cluster services often use a dummy key; EMPTY is accepted by many OpenAI-compat servers.
    key = config.LLM_API_KEY or "EMPTY"
    return ChatCompletionsClient(
        endpoint=_endpoint(),
        credential=AzureKeyCredential(key),
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
    """Extract assistant text; Qwen/LiteMaaS thinking models may leave content empty."""
    content = getattr(msg, "content", None)
    if isinstance(content, str) and content.strip():
        return content.strip()

    for attr in ("reasoning_content", "reasoning"):
        val = getattr(msg, attr, None)
        if isinstance(val, str) and val.strip():
            return val.strip()

    if hasattr(msg, "as_dict"):
        data = msg.as_dict()
        for key in ("content", "reasoning_content", "reasoning"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        # nested provider fields
        nested = data.get("provider_specific_fields") or {}
        for key in ("reasoning_content", "reasoning"):
            val = nested.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()

    return ""


def _complete(client: ChatCompletionsClient, messages: list[Any], *, with_tools: bool = True):
    kwargs: dict[str, Any] = {
        "messages": messages,
        "model": config.LLM_MODEL,
        "temperature": 0.2,
        "max_tokens": 2048,
        # Disable Qwen3 "thinking" so content is returned in message.content
        "model_extras": {
            "chat_template_kwargs": {"enable_thinking": False},
            "enable_thinking": False,
        },
    }
    if with_tools:
        kwargs["tools"] = _tools()
    with mlflow_span(
        "llm.complete",
        span_type="CHAT_MODEL",
        inputs={
            "model": config.LLM_MODEL,
            "with_tools": with_tools,
            "message_count": len(messages),
        },
    ) as span:
        response = client.complete(**kwargs)
        if span is not None:
            choice = response.choices[0]
            message = choice.message
            tool_calls = getattr(message, "tool_calls", None) or []
            span.set_outputs(
                {
                    "content_chars": len(_message_content(message)),
                    "tool_call_count": len(tool_calls),
                }
            )
        return response


def run_agent(user_text: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """
    Run one user turn. Returns {answer, tool_traces, messages}.
    history items: {role: user|assistant, content: str}
    """
    if not config.LLM_BASE_URL or not config.LLM_MODEL:
        raise RuntimeError("LLM_BASE_URL and LLM_MODEL must be set (Secret llm-credentials)")

    with mlflow_span(
        "run_agent",
        span_type="AGENT",
        inputs={"user_chars": len(user_text), "history_len": len(history or [])},
    ) as agent_span:
        result = _run_agent_impl(user_text, history)
        if agent_span is not None:
            agent_span.set_outputs(
                {
                    "answer_chars": len(result.get("answer") or ""),
                    "tool_calls": len(result.get("tool_traces") or []),
                }
            )
        return result


def _run_agent_impl(
    user_text: str, history: list[dict[str, str]] | None = None
) -> dict[str, Any]:
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
        response = _complete(client, messages, with_tools=True)
        choice = response.choices[0]
        message = choice.message
        tool_calls = getattr(message, "tool_calls", None) or []

        if tool_calls:
            messages.append(message)
            for call in tool_calls:
                fn = call.function
                name = fn.name
                args = fn.arguments or "{}"
                span_type = "RETRIEVER" if name == "search_knowledge_base" else "TOOL"
                with mlflow_span(
                    name,
                    span_type=span_type,
                    inputs={"arguments": args[:1000]},
                ) as tool_span:
                    result = run_tool(name, args)
                    if tool_span is not None:
                        tool_span.set_outputs({"result_chars": len(result or "")})
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
        if not answer:
            answer = (
                "(Model returned an empty message. Try again, or check LiteMaaS model settings.)"
            )
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
    response = _complete(
        client,
        [UserMessage(content="Reply with the single word OK")],
        with_tools=False,
    )
    return _message_content(response.choices[0].message)
