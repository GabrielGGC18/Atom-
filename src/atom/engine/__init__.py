"""Selecao de engine. Ordem local-first: ollama > openai_compat local > claude_cli."""

from __future__ import annotations

from atom.core.config import Config
from atom.engine.base import Engine, EngineError
from atom.engine.claude_cli import ClaudeCliEngine
from atom.engine.ollama import OllamaEngine
from atom.engine.openai_compat import OpenAICompatEngine

REGISTRY: dict[str, type[Engine]] = {
    "ollama": OllamaEngine,
    "openai_compat": OpenAICompatEngine,
    "claude_cli": ClaudeCliEngine,
}

AUTO_ORDER = ["ollama", "claude_cli", "openai_compat"]


def build(cfg: Config, provider: str | None = None) -> Engine:
    prov = provider or cfg.get("engine.provider", "auto")
    kw = dict(
        model=cfg.get("engine.model", "") or "",
        temperature=float(cfg.get("engine.temperature", 0.2)),
        timeout=int(cfg.get("engine.timeout", 300)),
        base_url=cfg.get("engine.base_url", "") or "",
        api_key_env=cfg.get("engine.api_key_env", "OPENAI_API_KEY"),
    )
    if prov != "auto":
        cls = REGISTRY.get(prov)
        if not cls:
            raise EngineError(f"provider desconhecido: {prov}")
        return cls(**kw)

    for name in AUTO_ORDER:
        eng = REGISTRY[name](**kw)
        if eng.available():
            return eng
    raise EngineError(
        "nenhum backend disponivel. Instale Ollama, defina OPENAI_API_KEY, "
        "ou garanta `claude` no PATH."
    )


def probe(cfg: Config) -> dict[str, bool]:
    kw = dict(
        model="", temperature=0.2, timeout=10,
        base_url=cfg.get("engine.base_url", "") or "",
        api_key_env=cfg.get("engine.api_key_env", "OPENAI_API_KEY"),
    )
    return {n: REGISTRY[n](**kw).available() for n in REGISTRY}


__all__ = ["Engine", "EngineError", "build", "probe", "REGISTRY"]
