"""Config do ATOM: YAML em ~/.atom/config.yaml + overrides por env."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any

import yaml

from atom.core import paths

DEFAULTS: dict[str, Any] = {
    "engine": {
        "provider": "auto",          # auto | claude_cli | ollama | openai_compat
        "model": "",                  # vazio = default do provider
        "base_url": "",              # openai_compat / ollama
        "api_key_env": "OPENAI_API_KEY",
        "temperature": 0.2,
        "timeout": 300,
    },
    "agent": {
        "max_steps": 12,
        "persona": "atom",
        "language": "pt-BR",
        "caveman": False,
    },
    "tools": {
        "enabled": ["shell", "read_file", "write_file", "list_dir", "grep",
                     "http_get", "note_search", "note_read", "note_write",
                     "task_add", "task_list", "task_done", "sysinfo",
                     "remember", "recall"],
        "shell_allow_dangerous": False,
        "workspace_guard": True,
    },
    "vault": {
        "path": "",                  # vazio = ~/ATom-agent
        "skills_globs": ["Agents/Skills/**/*.md", "SEI/Skills/**/*.md",
                          "Java/Skills/**/*.md", "*/Skills/**/*.md"],
        "agents_globs": ["Agents/*.md", "*/Agents/*.md"],
    },
    "memory": {
        "enabled": True,
        "max_recall": 8,
    },
}


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


@dataclass
class Config:
    data: dict[str, Any] = field(default_factory=lambda: dict(DEFAULTS))

    # --- acesso ---
    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        node = self.data
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = value

    # --- io ---
    @classmethod
    def load(cls) -> "Config":
        cfg = cls(data=_deep_merge(DEFAULTS, {}))
        f = paths.config_file()
        if f.exists():
            try:
                loaded = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
                cfg.data = _deep_merge(DEFAULTS, loaded)
            except Exception:
                pass
        cfg._apply_env()
        return cfg

    def save(self) -> None:
        paths.config_file().write_text(
            yaml.safe_dump(self.data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    def _apply_env(self) -> None:
        env_map = {
            "ATOM_PROVIDER": "engine.provider",
            "ATOM_MODEL": "engine.model",
            "ATOM_BASE_URL": "engine.base_url",
            "ATOM_MAX_STEPS": "agent.max_steps",
        }
        for env, dotted in env_map.items():
            val = os.environ.get(env)
            if val:
                self.set(dotted, int(val) if val.isdigit() else val)

    def as_dict(self) -> dict[str, Any]:
        return dict(self.data)


def load_config() -> Config:
    return Config.load()
