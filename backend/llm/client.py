"""Calls a chat model through the OpenAI-compatible API.

Ollama, vLLM, LM Studio and most hosted providers accept this API, so changing the
model is a matter of LLM_BASE_URL and LLM_MODEL in .env, not of code.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Protocol

from backend.llm.constants import LLM_TEMPERATURE

# Some models (e.g. Qwen in thinking mode) put their reasoning between these tags.
_THINKING = re.compile(r"<think>.*?</think>", re.DOTALL)


class LLMError(RuntimeError):
    """Raised when the model server cannot be reached or returns an unexpected reply."""


class ChatModel(Protocol):
    """Anything that turns a system prompt and a user prompt into a reply."""

    def complete(self, system: str, user: str) -> str: ...


class OpenAICompatibleModel:
    """A model served at ``{base_url}/chat/completions``."""

    def __init__(self, base_url: str, model: str, api_key: str = "", timeout: float = 300):
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._api_key = api_key
        self._timeout = timeout

    def complete(self, system: str, user: str) -> str:
        """Send one request and return the reply text without any thinking section."""
        body = {
            "model": self._model,
            "temperature": LLM_TEMPERATURE,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        request = urllib.request.Request(
            self._url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                reply = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as error:
            raise LLMError(f"Cannot reach the model at {self._url}: {error}") from error
        try:
            text = reply["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as error:
            raise LLMError(f"Unexpected reply from the model: {reply}") from error
        return _THINKING.sub("", text).strip()
