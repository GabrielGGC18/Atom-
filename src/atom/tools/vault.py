"""Tools do vault Obsidian (notas, skills, agents do Mestre)."""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

from atom.core import paths
from atom.core.registry import register

SKIP = {".git", ".obsidian", ".trash", "node_modules"}


def vault_root() -> Path:
    return paths.default_vault()


def _iter_notes(root: Path):
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for f in files:
            if f.lower().endswith((".md", ".canvas")):
                yield Path(dirpath, f)


@register("note_search", "Busca texto nas notas do vault Obsidian.",
          {"query": "str", "limit": "int (opcional)"})
def note_search(query: str, limit: int = 20) -> str:
    root = vault_root()
    if not root.exists():
        return f"ERRO: vault nao encontrado em {root}"
    rx = re.compile(re.escape(query), re.IGNORECASE)
    hits: list[str] = []
    for note in _iter_notes(root):
        try:
            text = note.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if rx.search(note.name) or rx.search(text):
            snippet = ""
            m = rx.search(text)
            if m:
                s = max(0, m.start() - 80)
                snippet = text[s:m.end() + 120].replace("\n", " ")
            hits.append(f"{note.relative_to(root)} :: {snippet[:220]}")
            if len(hits) >= limit:
                break
    return "\n".join(hits) or "(nada encontrado)"


@register("note_read", "Le nota do vault por caminho relativo.", {"path": "str"})
def note_read(path: str) -> str:
    p = vault_root() / path
    if not p.exists():
        return f"ERRO: nota nao existe: {p}"
    return p.read_text(encoding="utf-8", errors="replace")[:100_000]


@register("note_write", "Cria/atualiza nota no vault (caminho relativo).",
          {"path": "str", "content": "str", "append": "bool (opcional)"}, dangerous=True)
def note_write(path: str, content: str, append: bool = False) -> str:
    p = vault_root() / path
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a" if append else "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content if content.endswith("\n") else content + "\n")
    return f"OK: nota salva em {p}"


@register("journal", "Anexa entrada no diario do dia (vault/Journal/AAAA-MM-DD.md).",
          {"text": "str"})
def journal(text: str) -> str:
    day = datetime.now().strftime("%Y-%m-%d")
    stamp = datetime.now().strftime("%H:%M")
    p = vault_root() / "Journal" / f"{day}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    header = "" if p.exists() else f"# Journal {day}\n\n"
    with open(p, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(f"{header}- **{stamp}** {text}\n")
    return f"OK: registrado em {p}"
