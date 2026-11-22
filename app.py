"""Chat-first interface for developing project ideas."""
from pathlib import Path

import streamlit as st

from prometheus.ai import configured_provider, local_setting
from prometheus.storage import save_project, update_project
from prometheus.workflow import WorkflowState, apply_response, is_save_confirmation, system_prompt

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
if "workflow" not in st.session_state:
    st.session_state.workflow = WorkflowState()
if "save_handled" not in st.session_state:
    st.session_state.save_handled = False

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
pending = bool(conversation and conversation[-1]["role"] == "user" and not st.session_state.save_handled)
if prompt := st.chat_input("Describe your idea or continue the conversation", key="chat_input"):
    prompt = prompt.strip()
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        conversation.append({"role": "user", "content": prompt})
        st.session_state.reply_error = None
        st.session_state.save_handled = False
        pending = True
        with st.chat_message("user"):
            st.markdown(prompt)
        draft = st.session_state.workflow.draft
        if draft and not is_save_confirmation(prompt):
            st.session_state.workflow.draft = None
        if draft and is_save_confirmation(prompt):
            root = local_setting("PROMETHEUS_PROJECTS_DIR")
            if not root:
                answer = "Project documents were not saved: configure PROMETHEUS_PROJECTS_DIR, then confirm again."
                kind = "error"
            elif not Path(root).expanduser().is_absolute():
                answer = "Project documents were not saved: PROMETHEUS_PROJECTS_DIR must be an absolute path."
                kind = "error"
            else:
                try:
                    project_root = Path(root).expanduser().resolve()
                    saved_directory = st.session_state.workflow.saved_directory
                    if saved_directory:
                        directory = Path(saved_directory)
                        if directory.parent != project_root:
                            raise ValueError("The configured project directory has changed.")
                        update_project(
                            directory, draft.name, draft.overview,
                            draft.concept_map, draft.next_steps, draft.context,
                        )
                        answer = f"Updated the four project documents in {directory}."
                    else:
                        directory = save_project(
                            project_root, draft.name, draft.overview,
                            draft.concept_map, draft.next_steps, draft.context,
                        )
                        st.session_state.workflow.saved_directory = str(directory)
                        answer = f"Saved the four project documents in {directory}."
                    kind = None
                    st.session_state.workflow.draft = None
                except (OSError, ValueError) as exc:
                    answer = f"Project documents were not saved: {exc}"
                    kind = "error"
            st.session_state.messages.append({"role": "assistant", "content": answer, **({"kind": kind} if kind else {})})
            st.session_state.save_handled = True
            st.rerun()

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
            raw = provider.reply(conversation, system_prompt(st.session_state.workflow))
            answer = apply_response(st.session_state.workflow, raw)
            draft = st.session_state.workflow.draft
            if draft:
                answer += (
                    f"\n\nProject overview\n\n{draft.overview}"
                    f"\n\nConcept map\n\n{draft.concept_map}"
                    f"\n\nNext steps\n\n{draft.next_steps}"
                    f"\n\nResumption context\n\n{draft.context}"
                )
        st.session_state.messages.append({"role": "assistant", "content": answer})
    except RuntimeError as exc:
        st.session_state.reply_error = str(exc)
        st.session_state.messages.append({
            "role": "assistant", "content": str(exc), "kind": "error",
        })
    st.rerun()
