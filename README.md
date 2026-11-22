# Prometheus

Prometheus helps turn an idea into a concise project plan through a single chat input. Your first message starts the AI conversation immediately when a provider is configured. It can move between brainstorming, consulting, and documentation as the discussion develops; a sufficiently clear first description can skip brainstorming. It asks short questions, suggests approaches, and distinguishes proposals from confirmed decisions.

## Getting started

Install Python 3.11 or newer and [uv](https://docs.astral.sh/uv/), then run:

```bash
uv sync
uv run streamlit run app.py
```

There are no project forms. Missing endpoint, model or API key configuration is reported directly in the chat. Your first message is retained in the current session but cannot receive an AI reply until configuration is complete. After connecting a provider, rerun the app to send the pending message. Connection failures, authentication errors and provider errors also appear in the chat; failed requests can be retried without duplicating your message. Chat and compact project memory are kept only in the current Streamlit session; reloading the browser or restarting the server can discard them. Streamlit's developer toolbar controls, including Deploy, are hidden.

## AI configuration

The local `.env` is configured for OpenAI's `gpt-6-luna` as a low-cost test model. Add your OpenAI Platform API key to `PROMETHEUS_AI_API_KEY` in `.env`, then start or restart Streamlit with `uv run streamlit run app.py`. A Codex login through ChatGPT is not itself an API key. If you signed into Codex with a Platform API key, that same key can be used here, subject to your API account's access and billing.

You can also override any `.env` setting with an exported environment variable:

```bash
export PROMETHEUS_AI_ENDPOINT="https://your-provider.example/v1/chat/completions"
export PROMETHEUS_AI_MODEL="your-model"
export PROMETHEUS_AI_API_KEY="your-platform-key"
uv run streamlit run app.py
```

Use the full chat completions URL supplied by your provider. Endpoint, model and API key are all required by this integration. `.env` is loaded automatically and excluded from Git; do not commit credentials. Conversation content is sent to the configured endpoint. Microsoft Foundry may require a different endpoint, authentication, or API version; it has not been configured or verified here.

The adapter in `prometheus/ai.py` implements a small provider interface and can be replaced for a different API. `prometheus/workflow.py` holds the current stage and compact memory. Each model reply proposes the next stage and memory as structured JSON; the application validates it before updating the session. Invalid responses appear as retryable chat errors. Stage selection is model-guided, so correct mistaken conclusions in chat.

To enable document saving, set `PROMETHEUS_PROJECTS_DIR` in `.env` to an absolute directory you authorize for project files. When the conversation reaches documentation, Prometheus shows a concise draft and asks you to confirm it. Reply with an unambiguous confirmation such as `Yes, save it` to create four Markdown files in a new project subfolder. Later revisions to that same project also require confirmation before the four files are updated. An unrelated existing subfolder is never overwritten. Reopening past projects in a new session is not yet implemented.

## Verification

```bash
uv run pytest
```
