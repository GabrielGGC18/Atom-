"""Engine Ollama local (http://localhost:11434). Stdlib apenas."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from atom.core.types import Message
from atom.engine.base import Engine, EngineError, EngineTransientError, Usage

DEFAULT_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:7b-instruct"


class OllamaEngine(Engine):
    name = "ollama"

    @property
    def base_url(self) -> str:
        return (self.options.get("base_url") or DEFAULT_URL).rstrip("/")

    def available(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=3) as r:
                return r.status == 200
        except Exception:
            return False

    def models(self) -> list[str]:
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=5) as r:
                data = json.loads(r.read().decode("utf-8"))
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    def complete(self, messages: list[Message]) -> str:
        model = self.model or (self.models() or [DEFAULT_MODEL])[0]
        payload = {
            "model": model,
            "messages": [m.to_dict() for m in messages],
            "stream": False,
            "options": {"temperature": self.temperature},
        }
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise EngineError(
                    f"ollama: modelo '{model}' nao existe. `ollama list` mostra os instalados."
                ) from exc
            raise EngineTransientError(f"ollama HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise EngineTransientError(f"ollama indisponivel: {exc}") from exc
        self._account(Usage(
            input_tokens=int(data.get("prompt_eval_count") or 0),
            output_tokens=int(data.get("eval_count") or 0),
        ))
        return (data.get("message") or {}).get("content", "").strip()
