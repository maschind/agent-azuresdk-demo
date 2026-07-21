"""Streamlit UI: chat + knowledge base upload/list/delete."""

from __future__ import annotations

import os
import traceback

import streamlit as st

import config
from agent.loop import run_agent
from config import (
    AGENT_BACKEND,
    ENABLE_PROVIDER_BYPASS,
    MAX_UPLOAD_BYTES,
    RAG_BACKEND,
)
from documents import extension_ok, extract_text
from observability import mlflow_chat_run, run_shield

# Provider endpoints/models — dedicated env keys so Streamlit reruns cannot
# overwrite LiteMaaS defaults when apply_provider mutates LLM_*.
VLLM_BASE_URL = os.environ.get(
    "VLLM_BASE_URL",
    "http://llama-32-3b-instruct-predictor.my-first-model.svc.cluster.local:8080/v1",
)
VLLM_MODEL = os.environ.get("VLLM_MODEL", "llama-32-3b-instruct")
LLAMA_STACK_BASE_URL = os.environ.get(
    "LLAMA_STACK_BASE_URL",
    "http://llamastack-demo-service:8321/v1",
)
LLAMA_STACK_MODEL = os.environ.get("LLAMA_STACK_MODEL", "vllm-inference/Qwen3.6-35B-A3B")

st.set_page_config(page_title="Azure SDK Agent Demo", page_icon="🟥", layout="wide")


def _litemaas_endpoint() -> tuple[str, str]:
    if "litemaas_base_url" not in st.session_state:
        st.session_state.litemaas_base_url = os.environ.get("LITEMASS_BASE_URL") or os.environ.get(
            "LLM_BASE_URL", ""
        )
        st.session_state.litemaas_model = os.environ.get("LITEMASS_MODEL") or os.environ.get(
            "LLM_MODEL", ""
        )
    return st.session_state.litemaas_base_url, st.session_state.litemaas_model


def apply_provider(provider: str) -> None:
    litemaas_url, litemaas_model = _litemaas_endpoint()
    if provider == "vllm":
        os.environ["LLM_BASE_URL"] = VLLM_BASE_URL
        os.environ["LLM_MODEL"] = VLLM_MODEL
        if not os.environ.get("LLM_API_KEY"):
            os.environ["LLM_API_KEY"] = "EMPTY"
    elif provider == "llamastack":
        os.environ["LLM_BASE_URL"] = LLAMA_STACK_BASE_URL
        os.environ["LLM_MODEL"] = LLAMA_STACK_MODEL
        if not os.environ.get("LLM_API_KEY"):
            os.environ["LLM_API_KEY"] = "EMPTY"
    else:
        os.environ["LLM_BASE_URL"] = litemaas_url
        os.environ["LLM_MODEL"] = litemaas_model
    config.LLM_BASE_URL = os.environ["LLM_BASE_URL"]
    config.LLM_MODEL = os.environ["LLM_MODEL"]
    config.LLM_API_KEY = os.environ.get("LLM_API_KEY", config.LLM_API_KEY)
    config.MODEL_PROVIDER = provider


@st.cache_resource
def ensure_backend() -> bool:
    if RAG_BACKEND == "stack":
        from stack_kb import ensure_vector_store

        ensure_vector_store()
        return True
    from db import init_schema
    from embeddings import embed_texts

    init_schema()
    embed_texts(["warmup"])
    return True


def _list_docs():
    if RAG_BACKEND == "stack":
        from stack_kb import list_documents

        return list_documents()
    from db import list_documents

    return list_documents()


def _delete_doc(doc_id: str) -> None:
    if RAG_BACKEND == "stack":
        from stack_kb import delete_document

        delete_document(doc_id)
        return
    from db import delete_document

    delete_document(doc_id)


def sidebar_kb() -> None:
    st.sidebar.header("Model provider")
    stack_enabled = AGENT_BACKEND in ("llamastack", "native") or os.environ.get(
        "ENABLE_LLAMA_STACK_PROVIDER"
    ) == "true"
    default_provider = os.environ.get(
        "MODEL_PROVIDER", "llamastack" if stack_enabled else "litemaas"
    )
    if stack_enabled and not ENABLE_PROVIDER_BYPASS:
        choices = ["llamastack"]
    elif stack_enabled:
        choices = ["llamastack", "litemaas", "vllm"]
    else:
        choices = ["litemaas", "vllm"]
    provider = st.sidebar.selectbox(
        "LLM endpoint",
        choices,
        index=choices.index(default_provider) if default_provider in choices else 0,
        help="v3: Stack only. v2: Stack default with optional bypasses.",
    )
    apply_provider(provider)
    st.sidebar.caption(f"`{config.LLM_MODEL}` @ `{config.LLM_BASE_URL}`")
    st.sidebar.caption(f"RAG backend: `{RAG_BACKEND}`")

    st.sidebar.header("Knowledge base")
    st.sidebar.caption(f"Max upload {MAX_UPLOAD_BYTES // (1024 * 1024)} MB · .txt .md .pdf")

    uploaded = st.sidebar.file_uploader("Upload document", type=["txt", "md", "pdf"])
    if uploaded is not None and st.sidebar.button("Ingest", type="primary"):
        try:
            data = uploaded.getvalue()
            if not extension_ok(uploaded.name):
                st.sidebar.error("Unsupported file type")
            elif RAG_BACKEND == "stack":
                from stack_kb import ingest_document

                with st.sidebar.status("Uploading to Llama Stack vector store…"):
                    meta = ingest_document(
                        uploaded.name,
                        data,
                        uploaded.type or "application/octet-stream",
                    )
                st.sidebar.success(f"Stored via Stack ({meta['file_id'][:12]}…)")
                st.rerun()
            else:
                from db import insert_document
                from documents import chunk_text
                from embeddings import embed_texts

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

    docs = _list_docs()
    if not docs:
        st.sidebar.info("Knowledge base is empty. Upload a document to begin.")
        return

    st.sidebar.subheader("Documents")
    for doc in docs:
        cols = st.sidebar.columns([4, 1])
        cols[0].markdown(
            f"**{doc['filename']}**<br/><small>{doc.get('chunk_count', '?')} · "
            f"{doc.get('byte_size', 0)} B</small>",
            unsafe_allow_html=True,
        )
        if cols[1].button("🗑", key=f"del-{doc['id']}", help="Delete"):
            _delete_doc(doc["id"])
            st.rerun()


def main() -> None:
    try:
        ensure_backend()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Backend not ready: {exc}")
        st.stop()

    st.title("OpenShift AI · Azure SDK Agent")
    st.caption(
        f"Backend `{AGENT_BACKEND}` · provider `{config.MODEL_PROVIDER}` · "
        f"RAG `{RAG_BACKEND}` · model `{config.LLM_MODEL}` · `{config.LLM_BASE_URL}`"
    )

    sidebar_kb()

    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "tool_traces" not in st.session_state:
        st.session_state.tool_traces = []
    if "obs_notes" not in st.session_state:
        st.session_state.obs_notes = []

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
                    shield = run_shield(prompt)
                    if not shield.get("ok", True) and not shield.get("skipped"):
                        answer = (
                            "**Blocked by TrustyAI / Stack safety shield.**\n\n"
                            f"```json\n{shield.get('detail')}\n```"
                        )
                        st.warning(answer)
                        st.session_state.obs_notes = [shield]
                        st.session_state.messages.append(
                            {"role": "assistant", "content": answer}
                        )
                        st.stop()

                    history = [
                        {"role": m["role"], "content": m["content"]}
                        for m in st.session_state.messages[:-1]
                    ]
                    with mlflow_chat_run(prompt, config.LLM_MODEL) as mf:
                        result = run_agent(prompt, history=history)
                        answer = result["answer"]
                        traces = result.get("tool_traces") or []
                        mf["answer"] = answer
                        mf["tool_calls"] = len(traces)
                        mf["shield_ok"] = shield.get("ok", True)
                    st.session_state.tool_traces = traces
                    st.session_state.obs_notes = [shield, {"mlflow": mf}]
                    st.markdown(answer)
                    if traces:
                        with st.expander("Tool calls", expanded=True):
                            for t in traces:
                                st.code(
                                    f"{t['tool']}({t['arguments']})\n→ {t['result'][:2000]}",
                                    language="json",
                                )
                    with st.expander("Observability (TrustyAI / MLflow)"):
                        st.json(
                            {
                                "shield": shield,
                                "mlflow": mf,
                                "mlflow_ui": os.environ.get("MLFLOW_UI_URL", ""),
                                "trustyai_orchestrator": os.environ.get(
                                    "TRUSTYAI_ORCHESTRATOR_URL", ""
                                ),
                            }
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
