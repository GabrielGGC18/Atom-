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


VAULT_CANDIDATES = ("Atom-Agent", "ATom-agent", "atom-agent", "ATOM-Agent", "vault")


def default_vault() -> Path:
    """Vault Obsidian com agents/skills do Mestre.

    Ordem: $ATOM_VAULT -> ~/.atom/vault -> nomes conhecidos em ~ ->
    varredura case-insensitive em ~. Linux e' case-sensitive; nao da'
    pra confiar num literal so'.
    """
    override = os.environ.get("ATOM_VAULT")
    if override:
        return Path(override).expanduser()

    local = atom_home() / "vault"
    if local.is_dir():
        return local

    home = _home()
    for name in VAULT_CANDIDATES:
        cand = home / name
        if cand.is_dir():
            return cand

    wanted = {n.lower() for n in VAULT_CANDIDATES}
    try:
        for entry in home.iterdir():
            if entry.is_dir() and entry.name.lower() in wanted:
                return entry
    except OSError:
        pass

    return home / VAULT_CANDIDATES[0]


def workspace() -> Path:
    """Diretorio de trabalho corrente."""
    return Path.cwd()
