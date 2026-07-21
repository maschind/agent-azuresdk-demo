"""Streamlit UI: chat + knowledge base upload/list/delete."""

from __future__ import annotations

import os
import traceback

import streamlit as st

import config
from agent.loop import run_agent
from config import AGENT_BACKEND, MAX_UPLOAD_BYTES
from db import delete_document, init_schema, insert_document, list_documents
from documents import chunk_text, extension_ok, extract_text
from embeddings import embed_texts

# Optional in-cluster vLLM (OpenShift AI sample)
VLLM_BASE_URL = os.environ.get(
    "VLLM_BASE_URL",
    # Headless KServe predictor resolves to pod IP; listen port is 8080.
    "http://llama-32-3b-instruct-predictor.my-first-model.svc.cluster.local:8080/v1",
)
VLLM_MODEL = os.environ.get("VLLM_MODEL", "llama-32-3b-instruct")
LITEMASS_BASE_URL = os.environ.get("LITEMASS_BASE_URL", os.environ.get("LLM_BASE_URL", ""))
LITEMASS_MODEL = os.environ.get("LITEMASS_MODEL", os.environ.get("LLM_MODEL", ""))
LLAMA_STACK_BASE_URL = os.environ.get("LLAMA_STACK_BASE_URL", "http://llamastack-demo:8321/v1")

st.set_page_config(page_title="Azure SDK Agent Demo", page_icon="🟥", layout="wide")


def apply_provider(provider: str) -> None:
    """Config-only switch for Azure SDK endpoint/model (and optional Llama Stack)."""
    if provider == "vllm":
        os.environ["LLM_BASE_URL"] = VLLM_BASE_URL
        os.environ["LLM_MODEL"] = VLLM_MODEL
        if not os.environ.get("LLM_API_KEY"):
            os.environ["LLM_API_KEY"] = "EMPTY"
    elif provider == "llamastack":
        os.environ["LLM_BASE_URL"] = LLAMA_STACK_BASE_URL
        os.environ["LLM_MODEL"] = os.environ.get("LLAMA_STACK_MODEL", LITEMASS_MODEL)
    else:
        os.environ["LLM_BASE_URL"] = LITEMASS_BASE_URL
        os.environ["LLM_MODEL"] = LITEMASS_MODEL
    config.LLM_BASE_URL = os.environ["LLM_BASE_URL"]
    config.LLM_MODEL = os.environ["LLM_MODEL"]
    config.LLM_API_KEY = os.environ.get("LLM_API_KEY", config.LLM_API_KEY)
    config.MODEL_PROVIDER = provider


@st.cache_resource
def ensure_db() -> bool:
    init_schema()
    # Warm local embedding model once
    embed_texts(["warmup"])
    return True


def sidebar_kb() -> None:
    st.sidebar.header("Model provider")
    default_provider = os.environ.get("MODEL_PROVIDER", "litemaas")
    choices = ["litemaas", "vllm"]
    if AGENT_BACKEND == "llamastack" or os.environ.get("ENABLE_LLAMA_STACK_PROVIDER") == "true":
        choices.append("llamastack")
    provider = st.sidebar.selectbox(
        "LLM endpoint",
        choices,
        index=choices.index(default_provider) if default_provider in choices else 0,
    )
    apply_provider(provider)
    st.sidebar.caption(f"`{config.LLM_MODEL}` @ `{config.LLM_BASE_URL}`")

    st.sidebar.header("Knowledge base")
    st.sidebar.caption(f"Max upload {MAX_UPLOAD_BYTES // (1024 * 1024)} MB · .txt .md .pdf")

    uploaded = st.sidebar.file_uploader("Upload document", type=["txt", "md", "pdf"])
    if uploaded is not None and st.sidebar.button("Ingest", type="primary"):
        try:
            data = uploaded.getvalue()
            if not extension_ok(uploaded.name):
                st.sidebar.error("Unsupported file type")
            else:
                text = extract_text(uploaded.name, data)
                chunks = chunk_text(text)
                with st.sidebar.status("Embedding and storing…"):
                    vectors = embed_texts(chunks)
                    doc_id = insert_document(
                        filename=uploaded.name,
                        content_type=uploaded.type or "application/octet-stream",
                        byte_size=len(data),
                        chunks=chunks,
                        embeddings=vectors,
                    )
                st.sidebar.success(f"Stored {len(chunks)} chunks ({doc_id[:8]}…)")
                st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.sidebar.error(str(exc))

    docs = list_documents()
    if not docs:
        st.sidebar.info("Knowledge base is empty. Upload a document to begin.")
        return

    st.sidebar.subheader("Documents")
    for doc in docs:
        cols = st.sidebar.columns([4, 1])
        cols[0].markdown(
            f"**{doc['filename']}**<br/><small>{doc['chunk_count']} chunks · {doc['byte_size']} B</small>",
            unsafe_allow_html=True,
        )
        if cols[1].button("🗑", key=f"del-{doc['id']}", help="Delete"):
            delete_document(doc["id"])
            st.rerun()


def main() -> None:
    try:
        ensure_db()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Database not ready: {exc}")
        st.stop()

    st.title("OpenShift AI · Azure SDK Agent")
    st.caption(
        f"Backend `{AGENT_BACKEND}` · provider `{config.MODEL_PROVIDER}` · "
        f"model `{config.LLM_MODEL}` · `{config.LLM_BASE_URL}`"
    )

    sidebar_kb()

    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "tool_traces" not in st.session_state:
        st.session_state.tool_traces = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    prompt = st.chat_input("Ask about your uploaded documents…")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                try:
                    history = [
                        {"role": m["role"], "content": m["content"]}
                        for m in st.session_state.messages[:-1]
                    ]
                    result = run_agent(prompt, history=history)
                    answer = result["answer"]
                    traces = result.get("tool_traces") or []
                    st.session_state.tool_traces = traces
                    st.markdown(answer)
                    if traces:
                        with st.expander("Tool calls", expanded=True):
                            for t in traces:
                                st.code(
                                    f"{t['tool']}({t['arguments']})\n→ {t['result'][:2000]}",
                                    language="json",
                                )
                except Exception as exc:  # noqa: BLE001
                    answer = f"Error: {exc}"
                    st.error(answer)
                    st.code(traceback.format_exc())
        st.session_state.messages.append({"role": "assistant", "content": answer})

    if st.session_state.tool_traces and not prompt:
        with st.expander("Last tool calls"):
            for t in st.session_state.tool_traces:
                st.code(
                    f"{t['tool']}({t['arguments']})\n→ {t['result'][:2000]}",
                    language="json",
                )


if __name__ == "__main__":
    main()
