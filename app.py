"""Chat-first interface for developing project ideas."""
from pathlib import Path

import streamlit as st

from prometheus.ai import configured_provider

st.set_page_config(
    page_title="Prometheus",
    page_icon=str(Path(__file__).resolve().parent / "assets" / "prometheus-icon.png"),
)
st.set_option("client.toolbarMode", "viewer")
st.markdown(
    "<style>.stAppDeployButton, [data-testid='stAppDeployButton'] "
    "{display: none !important;}</style>",
    unsafe_allow_html=True,
)
st.title("Prometheus")
st.caption("Describe your idea. We’ll shape it together, one question at a time.")

configuration_error = None
try:
    provider = configured_provider()
except RuntimeError as exc:
    provider = None
    configuration_error = str(exc)
if "messages" not in st.session_state:
    st.session_state.messages = []
if "reply_error" not in st.session_state:
    st.session_state.reply_error = None

if not st.session_state.messages and configuration_error:
    st.session_state.messages.append({
        "role": "assistant", "content": configuration_error, "kind": "error",
    })

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message.get("kind") == "error":
            st.error(message["content"])
        else:
            st.markdown(message["content"])

conversation = [
    {"role": message["role"], "content": message["content"]}
    for message in st.session_state.messages if message.get("kind") != "error"
]
pending = bool(conversation and conversation[-1]["role"] == "user")
if prompt := st.chat_input("Describe your idea or continue the conversation", key="chat_input"):
    prompt = prompt.strip()
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        conversation.append({"role": "user", "content": prompt})
        st.session_state.reply_error = None
        pending = True
        with st.chat_message("user"):
            st.markdown(prompt)

if configuration_error and pending and st.session_state.messages[-1].get("kind") != "error":
    st.session_state.messages.append({
        "role": "assistant", "content": configuration_error, "kind": "error",
    })
    st.rerun()

if pending and st.session_state.reply_error and provider is not None:
    if st.button("Retry response"):
        st.session_state.reply_error = None

if pending and provider is not None and not st.session_state.reply_error:
    try:
        with st.spinner("Thinking..."):
            answer = provider.reply(conversation)
        st.session_state.messages.append({"role": "assistant", "content": answer})
    except RuntimeError as exc:
        st.session_state.reply_error = str(exc)
        st.session_state.messages.append({
            "role": "assistant", "content": str(exc), "kind": "error",
        })
    st.rerun()
