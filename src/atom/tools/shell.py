"""Execucao de comandos. Bloqueio de padroes destrutivos por default."""

from __future__ import annotations

import os
import re
import shutil
import subprocess

from atom.core.registry import register

DANGEROUS_PATTERNS = [
    r"\brm\s+-rf\b",
    r"\bdel\s+/[sfq]",
    r"\bformat\b",
    r"\bmkfs\b",
    r"git\s+reset\s+--hard",
    r"git\s+push\s+.*--force",
    r"\bdrop\s+(table|database)\b",
    r"\bshutdown\b",
    r">\s*/dev/sd",
    r"\bdiskpart\b",
]


def is_dangerous(cmd: str) -> str | None:
    for pat in DANGEROUS_PATTERNS:
        if re.search(pat, cmd, re.IGNORECASE):
            return pat
    return None


def _shell_exe() -> list[str]:
    if os.name == "nt":
        bash = shutil.which("bash")
        if bash:
            return [bash, "-lc"]
        return ["cmd", "/c"]
    return ["/bin/sh", "-c"]


@register(
    "shell",
    "Roda comando no shell e devolve stdout+stderr. Use para git, ls, npm, python, etc.",
    {"command": "str", "cwd": "str (opcional)", "timeout": "int seg (opcional, default 120)"},
    dangerous=True,
)
def shell(command: str, cwd: str = "", timeout: int = 120) -> str:
    hit = is_dangerous(command)
    if hit and os.environ.get("ATOM_ALLOW_DANGEROUS") != "1":
        return (f"BLOQUEADO: comando casa com padrao destrutivo `{hit}`. "
                "Confirme com o Mestre e reexecute com ATOM_ALLOW_DANGEROUS=1.")
    argv = _shell_exe() + [command]
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=int(timeout), cwd=cwd or None,
        )
    except subprocess.TimeoutExpired:
        return f"TIMEOUT apos {timeout}s"
    except FileNotFoundError as exc:
        return f"ERRO: {exc}"
    out = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr else "")
    return f"[exit {proc.returncode}]\n{out.strip()}" or f"[exit {proc.returncode}] (sem saida)"
