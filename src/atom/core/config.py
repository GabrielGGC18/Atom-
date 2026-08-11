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
        "caveman": True,           # respostas curtas = menos token de saida
        "retries": 2,              # retry com backoff em falha temporaria
        "parallel_tools": 4,       # tools independentes em paralelo
        "tool_result_chars": 4000, # corte do resultado de tool no contexto
        "max_context_chars": 60000,# orcamento total antes de podar historico
        "skill_max_chars": 2500,   # resto da skill via tool skill_read
        "project_index": True,     # lista os projetos do Mestre no contexto
    },
    "tools": {
        "enabled": ["shell", "read_file", "write_file", "list_dir", "grep",
                     "http_get", "note_search", "note_read", "note_write",
                     "task_add", "task_list", "task_done", "sysinfo",
                     "remember", "recall", "skill_list", "skill_read"],
        "shell_allow_dangerous": False,
        "workspace_guard": True,
        # Mascara segredo em arquivo .env/.pem e em qualquer saida de tool.
        "mask_secrets": True,
        # Pede confirmacao no chat antes de tool que altera o sistema.
        "confirm_dangerous": True,
        # Raizes onde write_file pode escrever. Vazio = cwd + ~/projects +
        # ~/gabriel-projects + ~/.atom. Leitura nao e' restrita por aqui.
        "write_roots": [],
    },
    "vault": {
        "path": "",                  # vazio = ~/ATom-agent
        "skills_globs": ["Agents/Skills/**/*.md", "*/Skills/**/*.md"],
        "agents_globs": ["Agents/*.md", "*/Agents/*.md"],
        # Pastas do vault que viram "dominio" da skill (ex: java, infra).
        "domains": [],
        # Skills/agents a esconder de `skill list` e do roteamento.
        # Fica no config local; nao versione nome de projeto privado.
        "hidden_skills": [],
    },
    "memory": {
        "enabled": True,
        "max_recall": 8,
    },
    "digest": {
        # Vazio = ~/projects + ~/gabriel-projects
        "repo_roots": [],
    },
    "routines": {
        # schedule: 10m | 2h | daily@07:30 | hourly@:15
        # action:   digest | ask:<prompt> | shell:<comando>
        "items": [
            {"name": "briefing", "schedule": "daily@08:00",
             "action": "digest", "enabled": False},
        ],
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
            "ATOM_TIMEOUT": "engine.timeout",
        }
        for env, dotted in env_map.items():
            val = os.environ.get(env)
            if val:
                self.set(dotted, int(val) if val.isdigit() else val)

    def as_dict(self) -> dict[str, Any]:
        return dict(self.data)


def load_config() -> Config:
    return Config.load()
