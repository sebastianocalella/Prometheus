"""Replaceable chat interface and optional OpenAI-compatible adapter."""
import json
import os
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from dotenv import dotenv_values


class ChatProvider(Protocol):
    def reply(self, messages: list[dict[str, str]], system_prompt: str) -> str: ...


class OpenAICompatibleProvider:
    def __init__(self, endpoint: str, model: str, api_key: str = ""):
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key

    def reply(self, messages: list[dict[str, str]], system_prompt: str) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = json.dumps({"model": self.model, "messages": [
            {"role": "system", "content": system_prompt}, *messages
        ]}).encode("utf-8")
        try:
            request = Request(self.endpoint, data=body, headers=headers, method="POST")
            with urlopen(request, timeout=60) as response:
                data = json.load(response)
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Empty response")
            return content.strip()
        except HTTPError as exc:
            if exc.code in (401, 403):
                message = "AI authentication failed. Check your API key and model access."
            elif exc.code == 404:
                message = "The AI endpoint or model was not found. Check the endpoint and model configuration."
            elif exc.code == 429:
                message = "The AI provider's rate or usage limit was reached. Check your quota or retry later."
            else:
                message = f"The AI provider rejected the request (HTTP {exc.code}). Check the configuration or retry later."
            raise RuntimeError(message) from exc
        except TimeoutError as exc:
            raise RuntimeError("The AI connection timed out. Check your connection or retry later.") from exc
        except (URLError, OSError) as exc:
            raise RuntimeError("Cannot reach the AI provider. Check your internet connection and endpoint, then retry.") from exc
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("The AI provider returned an invalid or empty reply. Check that the endpoint supports chat completions.") from exc


def local_setting(name: str) -> str:
    settings = dotenv_values(os.path.join(os.path.dirname(__file__), "..", ".env"))
    return (os.getenv(name, settings.get(name) or "")).strip()


def configured_provider() -> ChatProvider:
    endpoint = local_setting("PROMETHEUS_AI_ENDPOINT")
    model = local_setting("PROMETHEUS_AI_MODEL")
    api_key = local_setting("PROMETHEUS_AI_API_KEY")
    missing = [label for label, value in (
        ("AI endpoint", endpoint), ("model", model), ("API key", api_key)
    ) if not value]
    if missing:
        raise RuntimeError(f"AI is not connected. Missing configuration: {', '.join(missing)}.")
    try:
        url = urlsplit(endpoint)
        if url.scheme not in ("https", "http") or not url.hostname:
            raise ValueError("Invalid endpoint")
    except ValueError as exc:
        raise RuntimeError("The AI endpoint is invalid. Configure a full HTTP or HTTPS chat completions URL.") from exc
    return OpenAICompatibleProvider(endpoint, model, api_key)
