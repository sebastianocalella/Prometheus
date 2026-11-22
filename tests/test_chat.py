"""Exercise the chat UI without a network connection or real credentials."""
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest


APP = Path(__file__).resolve().parents[1] / "app.py"


def workflow_reply(message, stage="brainstorming", decisions=None, draft=None):
    return json.dumps({
        "message": message, "stage": stage,
        "memory": {"idea": "A project idea", "confirmed_decisions": decisions or [],
                   "open_questions": [], "proposed_options": []},
        "draft": draft,
    })


def test_first_message_starts_chat_and_followup_keeps_context():
    provider = Mock()
    provider.reply.side_effect = [workflow_reply("Who will use it?"), workflow_reply("What should the first prototype do?")]
    with patch("prometheus.ai.configured_provider", return_value=provider):
        app = AppTest.from_file(str(APP)).run()
        assert not app.exception
        assert len(app.chat_input) == 1
        assert not app.text_input
        assert not app.text_area
        assert not app.checkbox
        assert not app.button
        assert st.get_option("client.toolbarMode") == "viewer"
        provider.reply.assert_not_called()

        app.chat_input[0].set_value("A tool for sharing project ideas").run()
        assert not app.exception
        assert [message.name for message in app.chat_message] == ["user", "assistant"]
        provider.reply.assert_called_once_with([
            {"role": "user", "content": "A tool for sharing project ideas"},
        ], provider.reply.call_args.args[1])
        assert "Current stage: brainstorming" in provider.reply.call_args.args[1]

        app.chat_input[0].set_value("My colleagues").run()
        assert not app.exception
        assert provider.reply.call_args.args[0] == [
            {"role": "user", "content": "A tool for sharing project ideas"},
            {"role": "assistant", "content": "Who will use it?"},
            {"role": "user", "content": "My colleagues"},
        ]
        app.run()
        assert provider.reply.call_count == 2


@pytest.mark.parametrize("missing, label", [
    ("PROMETHEUS_AI_ENDPOINT", "AI endpoint"),
    ("PROMETHEUS_AI_MODEL", "model"),
    ("PROMETHEUS_AI_API_KEY", "API key"),
])
def test_missing_configuration_is_reported_in_chat_and_message_is_kept(monkeypatch, missing, label):
    monkeypatch.setenv("PROMETHEUS_AI_ENDPOINT", "https://example.com/chat")
    monkeypatch.setenv("PROMETHEUS_AI_MODEL", "test-model")
    monkeypatch.setenv("PROMETHEUS_AI_API_KEY", "test-key")
    monkeypatch.delenv(missing)
    with patch("prometheus.ai.dotenv_values", return_value={}), patch("prometheus.ai.urlopen") as request:
        app = AppTest.from_file(str(APP)).run()
        assert label in app.chat_message[0].error[0].value
        app.chat_input[0].set_value("A community garden").run()
        assert not app.exception
        assert label in app.chat_message[-1].error[0].value
        request.assert_not_called()
        assert app.session_state["messages"][1:2] == [
            {"role": "user", "content": "A community garden"},
        ]
        assert len(app.error) == 2
        history = list(app.session_state["messages"])
        app.run()
        assert app.session_state["messages"] == history
        assert not app.chat_input[0].disabled
        app.chat_input[0].set_value("For my neighborhood").run()
        assert not app.chat_input[0].disabled
        assert app.session_state["messages"][-2] == {
            "role": "user", "content": "For my neighborhood",
        }
        assert app.session_state["messages"][:3] == history
        assert len(app.error) == 3

    provider = Mock()
    provider.reply.return_value = workflow_reply("Who would participate?")
    with patch("prometheus.ai.configured_provider", return_value=provider):
        app.run()
        assert not app.exception
        assert len(app.chat_message) == 6
        assert len(app.error) == 3
        assert not app.chat_input[0].disabled
        provider.reply.assert_called_once()
        assert provider.reply.call_args.args[0] == [
            {"role": "user", "content": "A community garden"},
            {"role": "user", "content": "For my neighborhood"},
        ]


def test_failed_response_can_be_retried_without_duplicate_messages():
    provider = Mock()
    provider.reply.side_effect = [RuntimeError("Unable to connect."), workflow_reply("Who is it for?")]
    with patch("prometheus.ai.configured_provider", return_value=provider):
        app = AppTest.from_file(str(APP)).run()
        app.chat_input[0].set_value("A learning app").run()
        assert not app.exception
        assert app.error[0].value == "Unable to connect."
        assert app.chat_message[-1].error[0].value == "Unable to connect."
        app.run()
        assert provider.reply.call_count == 1
        app.button[0].click().run()
        assert not app.exception
        assert app.chat_message[1].error[0].value == "Unable to connect."
        assert len(app.chat_message) == 3
        assert provider.reply.call_args_list[0] == provider.reply.call_args_list[1]


def test_different_failures_stay_in_order_across_new_messages_and_reruns():
    provider = Mock()
    provider.reply.side_effect = [RuntimeError("Connection timed out."), RuntimeError("Authentication failed.")]
    with patch("prometheus.ai.configured_provider", return_value=provider):
        app = AppTest.from_file(str(APP)).run()
        app.chat_input[0].set_value("First idea").run()
        app.chat_input[0].set_value("A clarification").run()
        app.run()
        assert not app.exception
        assert [message.name for message in app.chat_message] == ["user", "assistant", "user", "assistant"]
        assert app.chat_message[1].error[0].value == "Connection timed out."
        assert app.chat_message[3].error[0].value == "Authentication failed."
        assert provider.reply.call_count == 2
        assert provider.reply.call_args.args[0] == [
            {"role": "user", "content": "First idea"},
            {"role": "user", "content": "A clarification"},
        ]


def test_document_draft_requires_chat_confirmation_and_configured_directory(tmp_path):
    draft = {"name": "Garden", "overview": "A shared garden", "concept_map": "People -> plots",
             "next_steps": "Find a site", "context": "Confirmed: local pilot"}
    provider = Mock()
    provider.reply.return_value = workflow_reply("Save these decisions?", "documentation", ["Local pilot"], draft)
    with patch("prometheus.ai.configured_provider", return_value=provider), \
         patch("prometheus.ai.local_setting", return_value="") as setting:
        app = AppTest.from_file(str(APP)).run()
        app.chat_input[0].set_value("A shared community garden").run()
        assert app.session_state["workflow"].stage == "documentation"
        assert not list(tmp_path.iterdir())
        app.chat_input[0].set_value("Yes").run()
        assert "not saved" in app.chat_message[-1].error[0].value
        assert provider.reply.call_count == 1
        setting.assert_called_with("PROMETHEUS_PROJECTS_DIR")

    with patch("prometheus.ai.configured_provider", return_value=provider), \
         patch("prometheus.ai.local_setting", return_value=str(tmp_path)):
        app.chat_input[0].set_value("Yes, save it").run()
        assert not app.exception
        assert (tmp_path / "garden" / "project.md").exists()
        assert (tmp_path / "garden" / "context.md").read_text().endswith("Confirmed: local pilot\n")
        assert provider.reply.call_count == 1
        revised = dict(draft, overview="A revised garden")
        provider.reply.return_value = workflow_reply("Save this revision?", "documentation", ["Local pilot"], revised)
        app.chat_input[0].set_value("Change the overview").run()
        assert (tmp_path / "garden" / "project.md").read_text().endswith("A shared garden\n")
        app.chat_input[0].set_value("Yes, save it").run()
        assert (tmp_path / "garden" / "project.md").read_text().endswith("A revised garden\n")
