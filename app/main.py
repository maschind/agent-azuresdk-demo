"""Streamlit UI — OpenShift AI agent (Llama Stack + TrustyAI + MLflow)."""

from __future__ import annotations

import traceback

import streamlit as st

import kb
from agent import run_agent
from config import (
    MAX_UPLOAD_BYTES,
    MLFLOW_UI_URL,
    STACK_BASE_URL,
    STACK_MODEL,
)
from documents import validate_upload
from safety import check_prompt
from tracing import chat_run

st.set_page_config(page_title="OpenShift AI Agent", layout="wide")


@st.cache_resource
def ready() -> bool:
    kb.ensure_store()
    return True


def sidebar() -> None:
    st.sidebar.header("OpenShift AI")
    st.sidebar.caption(f"Stack `{STACK_MODEL}`")
    st.sidebar.code(STACK_BASE_URL, language=None)

    st.sidebar.header("Knowledge base")
    st.sidebar.caption(f"Max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB · .txt .md .pdf")
    uploaded = st.sidebar.file_uploader("Upload", type=["txt", "md", "pdf"])
    if uploaded is not None and st.sidebar.button("Ingest", type="primary"):
        try:
            data = uploaded.getvalue()
            validate_upload(uploaded.name, data)
            with st.sidebar.status("Uploading to Llama Stack…"):
                meta = kb.ingest(
                    uploaded.name, data, uploaded.type or "application/octet-stream"
                )
            st.sidebar.success(f"Stored `{meta['file_id'][:12]}…`")
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.sidebar.error(str(exc))

    docs = kb.list_docs()
    if not docs:
        st.sidebar.info("Empty — upload a document to start.")
        return
    st.sidebar.subheader("Documents")
    for doc in docs:
        c1, c2 = st.sidebar.columns([4, 1])
        c1.markdown(f"**{doc['filename']}**")
        if c2.button("🗑", key=f"del-{doc['id']}", help="Delete"):
            kb.delete(doc["id"])
            st.rerun()


def main() -> None:
    try:
        ready()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Stack not ready: {exc}")
        st.stop()

    st.title("OpenShift AI Agent")
    st.caption("Chat → Llama Stack / KServe · RAG → Stack vector IO · TrustyAI · MLflow")
    sidebar()

    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "last_tools" not in st.session_state:
        st.session_state.last_tools = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    prompt = st.chat_input("Ask about your uploaded documents…")
    if not prompt:
        if st.session_state.last_tools:
            with st.expander("Last tool calls"):
                for t in st.session_state.last_tools:
                    st.code(
                        f"{t['tool']}({t['arguments']})\n→ {t['result'][:2000]}",
                        language="json",
                    )
        return

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        try:
            history = [
                {"role": m["role"], "content": m["content"]}
                for m in st.session_state.messages[:-1]
            ]
            with chat_run(prompt, STACK_MODEL) as mf:
                shield = check_prompt(prompt)
                mf["shield_ok"] = shield.get("ok", True)
                if shield.get("blocked"):
                    answer = (
                        "**Blocked by TrustyAI (PII detected).**\n\n"
                        f"```json\n{shield.get('detail')}\n```"
                    )
                    mf["answer"] = answer
                    mf["tool_calls"] = 0
                    st.warning(answer)
                else:
                    result = run_agent(prompt, history=history)
                    answer = result["answer"]
                    tools = result.get("tool_traces") or []
                    mf["answer"] = answer
                    mf["tool_calls"] = len(tools)
                    st.session_state.last_tools = tools
                    st.markdown(answer)
                    if tools:
                        with st.expander("Tool calls", expanded=True):
                            for t in tools:
                                st.code(
                                    f"{t['tool']}({t['arguments']})\n→ {t['result'][:2000]}",
                                    language="json",
                                )
                with st.expander("Observability"):
                    st.json({"shield": shield, "mlflow": mf, "mlflow_ui": MLFLOW_UI_URL})
        except Exception as exc:  # noqa: BLE001
            answer = f"Error: {exc}"
            st.error(answer)
            st.code(traceback.format_exc())

    st.session_state.messages.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    main()
