import json
from io import BytesIO
from urllib.error import HTTPError, URLError
from unittest.mock import patch

import pytest

from prometheus.ai import OpenAICompatibleProvider, configured_provider
from prometheus.storage import save_project, update_project
from prometheus.workflow import WorkflowState, apply_response, is_save_confirmation, system_prompt


def test_save_confirmed_project_without_overwriting(tmp_path):
    directory = save_project(tmp_path, "My idea", "Overview", "Concept", "Steps", "Context")
    assert (directory / "project.md").read_text() == "# My idea\n\n## Confirmed idea\n\nOverview\n"
    assert (directory / "concept-map.md").read_text() == "# Concept map\n\nConcept\n"
    assert (directory / "next-steps.md").read_text() == "# Next steps\n\nSteps\n"
    assert (directory / "context.md").read_text() == "# Context\n\nContext\n"
    with pytest.raises(FileExistsError):
        save_project(tmp_path, "My idea", "Another idea")
    update_project(directory, "My idea", "Revised overview", "New map", "New step", "New context")
    assert (directory / "project.md").read_text().endswith("Revised overview\n")
    assert (directory / "context.md").read_text().endswith("New context\n")


def test_update_rejects_unrecognized_directory(tmp_path):
    with pytest.raises(ValueError, match="missing"):
        update_project(tmp_path, "Idea", "Overview")


def test_missing_settings_are_reported(monkeypatch):
    monkeypatch.delenv("PROMETHEUS_AI_ENDPOINT", raising=False)
    monkeypatch.delenv("PROMETHEUS_AI_MODEL", raising=False)
    monkeypatch.delenv("PROMETHEUS_AI_API_KEY", raising=False)
    with patch("prometheus.ai.dotenv_values", return_value={}):
        with pytest.raises(RuntimeError, match="Missing configuration: AI endpoint, model, API key"):
            configured_provider()


def test_local_env_is_loaded_without_overriding_exported_values(monkeypatch, tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "PROMETHEUS_AI_ENDPOINT=https://example.com/v1/chat/completions\n"
        "PROMETHEUS_AI_MODEL=local-model\n"
        "PROMETHEUS_AI_API_KEY=local-key\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("PROMETHEUS_AI_ENDPOINT", raising=False)
    monkeypatch.delenv("PROMETHEUS_AI_MODEL", raising=False)
    monkeypatch.delenv("PROMETHEUS_AI_API_KEY", raising=False)
    from prometheus.ai import dotenv_values

    with patch("prometheus.ai.dotenv_values", side_effect=lambda _: dotenv_values(dotenv)):
        provider = configured_provider()
        assert provider.endpoint == "https://example.com/v1/chat/completions"
        assert provider.model == "local-model"
        assert provider.api_key == "local-key"
        monkeypatch.setenv("PROMETHEUS_AI_MODEL", "exported-model")
        assert configured_provider().model == "exported-model"


def test_invalid_endpoint_is_reported(monkeypatch):
    monkeypatch.setenv("PROMETHEUS_AI_ENDPOINT", "not-a-url")
    monkeypatch.setenv("PROMETHEUS_AI_MODEL", "test-model")
    monkeypatch.setenv("PROMETHEUS_AI_API_KEY", "test-key")
    with pytest.raises(RuntimeError, match="endpoint is invalid"):
        configured_provider()


@pytest.mark.parametrize("error, message", [
    (URLError("private endpoint details"), "Check your internet connection"),
    (TimeoutError("private timeout details"), "timed out"),
    (HTTPError("private-url", 401, "private-body", {}, None), "authentication failed"),
    (HTTPError("private-url", 404, "private-body", {}, None), "model was not found"),
    (HTTPError("private-url", 429, "private-body", {}, None), "usage limit"),
    (HTTPError("private-url", 503, "private-body", {}, None), "HTTP 503"),
])
def test_provider_failures_explain_the_issue_without_leaking_details(error, message):
    with patch("prometheus.ai.urlopen", side_effect=error):
        with pytest.raises(RuntimeError, match=message) as caught:
            OpenAICompatibleProvider("https://example.com/chat", "model", "secret").reply([], "Instructions")
    assert "private" not in str(caught.value)
    assert "secret" not in str(caught.value)


@pytest.mark.parametrize("body", [b"not-json", b"{}", b'{"choices": []}',
    b'{"choices": [{"message": {"content": ""}}]}'])
def test_invalid_model_response_is_reported(body):
    with patch("prometheus.ai.urlopen", return_value=BytesIO(body)):
        with pytest.raises(RuntimeError, match="invalid or empty reply"):
            OpenAICompatibleProvider("https://example.com/chat", "model", "secret").reply([], "Instructions")


def test_provider_sends_conversation_and_reads_response():
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"choices": [{"message": {"content": "Who is it for?"}}]}'

    with patch("prometheus.ai.urlopen", return_value=Response()) as open_url:
        result = OpenAICompatibleProvider("https://example.com/chat", "model", "secret").reply(
            [{"role": "user", "content": "An idea"}], "Instructions"
        )
    request = open_url.call_args.args[0]
    assert json.loads(request.data)["messages"][0]["content"] == "Instructions"
    assert json.loads(request.data)["messages"][-1]["content"] == "An idea"
    assert request.get_header("Authorization") == "Bearer secret"
    assert result == "Who is it for?"


def response(message, stage, decisions=(), draft=None):
    return json.dumps({"message": message, "stage": stage, "memory": {
        "idea": "A small project", "confirmed_decisions": list(decisions),
        "open_questions": [], "proposed_options": []}, "draft": draft})


def test_stage_can_skip_brainstorming_and_step_back():
    state = WorkflowState()
    assert apply_response(state, response("Try a prototype.", "consulting")) == "Try a prototype."
    assert state.stage == "consulting"
    assert "Current stage: consulting" in system_prompt(state)
    apply_response(state, response("Who is the user?", "brainstorming"))
    assert state.stage == "brainstorming"
    apply_response(state, response("Ready to document?", "documentation", ["Use a local prototype"]))
    assert state.stage == "documentation"


def test_invalid_stage_or_unconfirmed_documentation_does_not_change_memory():
    state = WorkflowState()
    for raw in ("not json", response("Ready?", "documentation"), response("Hi", "unknown")):
        with pytest.raises(RuntimeError, match="invalid workflow response"):
            apply_response(state, raw)
        assert state.stage == "brainstorming"
        assert not state.memory.idea


def test_save_confirmation_is_unambiguous():
    assert is_save_confirmation("Yes, save it!")
    assert not is_save_confirmation("Yes, but change the scope")
