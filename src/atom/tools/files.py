"""Leitura/escrita/busca em arquivos."""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path

from atom.core.guard import (check_read, check_write, is_secret_file,
                             masking_enabled, redact)
from atom.core.registry import register

MAX_READ = 200_000
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist",
             "build", ".next", ".mypy_cache", ".pytest_cache"}


@register("read_file", "Le arquivo de texto (opcional faixa de linhas).",
          {"path": "str", "start": "int (opcional)", "end": "int (opcional)"})
def read_file(path: str, start: int = 0, end: int = 0) -> str:
    blocked = check_read(path)
    if blocked:
        return blocked
    p = Path(path).expanduser()
    if not p.exists():
        return f"ERRO: nao existe {p}"
    if p.is_dir():
        return f"ERRO: {p} e' diretorio; use list_dir"
    try:
        text = p.read_text(encoding="utf-8", errors="replace")[:MAX_READ]
    except Exception as exc:
        return f"ERRO: {exc}"
    if start or end:
        lines = text.splitlines()
        text = "\n".join(lines[max(0, start - 1): end or len(lines)])
    if masking_enabled():
        if is_secret_file(p):
            # Mostra as chaves, esconde os valores: da' pra saber o que o
            # projeto espera sem despejar credencial no prompt.
            return (f"[arquivo de segredo: valores mascarados]\n{redact(text)}")
        return redact(text)
    return text


@register("write_file", "Escreve/sobrescreve arquivo de texto. Cria diretorios.",
          {"path": "str", "content": "str", "append": "bool (opcional)"}, dangerous=True)
def write_file(path: str, content: str, append: bool = False) -> str:
    blocked = check_write(path)
    if blocked:
        return blocked
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    try:
        with open(p, mode, encoding="utf-8", newline="\n") as fh:
            fh.write(content)
    except Exception as exc:
        return f"ERRO: {exc}"
    return f"OK: {'append' if append else 'escrito'} {len(content)} chars em {p}"


@register("list_dir", "Lista arquivos/pastas de um diretorio.",
          {"path": "str", "pattern": "str glob (opcional)", "recursive": "bool (opcional)"})
def list_dir(path: str = ".", pattern: str = "*", recursive: bool = False) -> str:
    p = Path(path).expanduser()
    if not p.exists():
        return f"ERRO: nao existe {p}"
    rows: list[str] = []
    if recursive:
        for root, dirs, files in os.walk(p):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                if fnmatch.fnmatch(f, pattern):
                    rows.append(str(Path(root, f)))
            if len(rows) > 500:
                break
    else:
        for item in sorted(p.iterdir()):
            if fnmatch.fnmatch(item.name, pattern):
                rows.append(("[dir] " if item.is_dir() else "      ") + item.name)
    return "\n".join(rows[:500]) or "(vazio)"


@register("grep", "Busca regex em arquivos de um diretorio.",
          {"pattern": "str regex", "path": "str", "glob": "str (opcional, ex *.py)"})
def grep(pattern: str, path: str = ".", glob: str = "*") -> str:
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        return f"ERRO regex: {exc}"
    root = Path(path).expanduser()
    mask = masking_enabled()
    hits: list[str] = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            if not fnmatch.fnmatch(fname, glob):
                continue
            fp = Path(dirpath, fname)
            if mask and is_secret_file(fp):
                continue  # grep em .env vazaria o valor na linha do match
            try:
                for i, line in enumerate(fp.read_text(encoding="utf-8",
                                                       errors="ignore").splitlines(), 1):
                    if rx.search(line):
                        snip = line.strip()[:200]
                        hits.append(f"{fp}:{i}: {redact(snip) if mask else snip}")
                        if len(hits) >= 200:
                            return "\n".join(hits) + "\n... [limite 200]"
            except Exception:
                continue
    return "\n".join(hits) or "(sem resultados)"
