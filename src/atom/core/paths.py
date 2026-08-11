"""Caminhos canonicos do ATOM."""

from __future__ import annotations

import os
from pathlib import Path


def _home() -> Path:
    return Path(os.path.expanduser("~"))


def atom_home() -> Path:
    """Raiz de dados do ATOM (~/.atom, override por ATOM_HOME)."""
    override = os.environ.get("ATOM_HOME")
    root = Path(override) if override else _home() / ".atom"
    root.mkdir(parents=True, exist_ok=True)
    return root


def config_file() -> Path:
    return atom_home() / "config.yaml"


def db_file() -> Path:
    return atom_home() / "atom.db"


def sessions_dir() -> Path:
    d = atom_home() / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def logs_dir() -> Path:
    d = atom_home() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def default_vault() -> Path:
    """Vault Obsidian com agents/skills do Mestre."""
    override = os.environ.get("ATOM_VAULT")
    if override:
        return Path(override)
    return _home() / "ATom-agent"


def workspace() -> Path:
    """Diretorio de trabalho corrente."""
    return Path.cwd()
