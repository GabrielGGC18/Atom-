"""Engine OpenAI-compat (OpenAI, Groq, OpenRouter, LM Studio, vLLM...)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from atom.core.types import Message
from atom.engine.base import Engine, EngineError, EngineTransientError, Usage

DEFAULT_URL = "https://api.openai.com/v1"


class OpenAICompatEngine(Engine):
    name = "openai_compat"

    @property
    def base_url(self) -> str:
        return (self.options.get("base_url") or DEFAULT_URL).rstrip("/")

    @property
    def api_key(self) -> str:
        env_name = self.options.get("api_key_env") or "OPENAI_API_KEY"
        return os.environ.get(env_name, "")

    def available(self) -> bool:
        # LM Studio/vLLM locais nao exigem key
        return bool(self.api_key) or "localhost" in self.base_url or "127.0.0.1" in self.base_url

    def complete(self, messages: list[Message]) -> str:
        payload = {
            "model": self.model or "gpt-4o-mini",
            "messages": [m.to_dict() for m in messages],
            "temperature": self.temperature,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read()[:300]
            if exc.code in (408, 409, 429, 500, 502, 503, 504):
                raise EngineTransientError(f"HTTP {exc.code}: {body!r}") from exc
            raise EngineError(f"HTTP {exc.code}: {body!r}") from exc
        except urllib.error.URLError as exc:
            raise EngineTransientError(f"conexao falhou: {exc}") from exc
        u = data.get("usage") or {}
        self._account(Usage(
            input_tokens=int(u.get("prompt_tokens") or 0),
            output_tokens=int(u.get("completion_tokens") or 0),
        ))
        return data["choices"][0]["message"]["content"].strip()
