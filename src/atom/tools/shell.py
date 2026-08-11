"""Execucao de comandos. Bloqueio de padroes destrutivos por default.

A blocklist antiga casava a string crua, entao `rm  -rf` (espaco duplo) ou
`rm -r -f` passavam batido. Aqui o comando e' normalizado antes -- e flags
soltas de `rm` sao remontadas -- o que fecha os desvios mais obvios.

Blocklist continua sendo defesa rasa: quem escreve o comando e' o modelo.
A trava seria dizer nao a `shell` e usar tools especificas. Isto reduz
acidente, nao resiste a intencao.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from atom.core.config import Config
from atom.core.registry import register

DANGEROUS_PATTERNS = [
    r"\brm\s+(?:-\w+\s+)*-\w*[rR]\w*f|\brm\s+(?:-\w+\s+)*-\w*f\w*[rR]",
    r"\bdel\s+/[sfq]",
    r"\bformat\b",
    r"\bmkfs\b",
    r"git\s+reset\s+--hard",
    r"git\s+push\b.*--force",
    r"git\s+clean\s+(?:-\w+\s*)*-\w*[fd]",
    r"\bdrop\s+(table|database)\b",
    r"\btruncate\s+table\b",
    r"\bshutdown\b|\breboot\b|\bhalt\b",
    r"\bdd\s+.*\bof=/dev/",
    r">\s*/dev/(sd|nvme|hd)",
    r"\bdiskpart\b",
    r"\bmkswap\b",
    r"chmod\s+(-\w+\s+)*777\s+/(\s|$)",
    r"chown\s+-R\b.*\s/(\s|$)",
    r":\(\)\s*\{.*\};\s*:",                      # fork bomb
    r"\bcurl\b[^|]*\|\s*(sudo\s+)?(ba)?sh",       # curl | sh
    r"\bwget\b[^|]*\|\s*(sudo\s+)?(ba)?sh",
    r"\bkill\s+-9\s+-1\b",
    r"docker\s+system\s+prune\b.*-a",
    r"\bhistory\s+-c\b",
]


def _normalize(cmd: str) -> str:
    """Colapsa espacos e junta flags curtas de rm para o regex enxergar."""
    s = re.sub(r"\s+", " ", cmd.strip())
    # `rm -r -f x` -> `rm -rf x`
    def _join(m: re.Match) -> str:
        flags = "".join(f.lstrip("-") for f in m.group(2).split())
        return f"{m.group(1)}-{flags} "
    s = re.sub(r"\b(rm\s+)((?:-\w+\s+){2,})", _join, s)
    return s


def is_dangerous(cmd: str) -> str | None:
    norm = _normalize(cmd)
    for pat in DANGEROUS_PATTERNS:
        if re.search(pat, norm, re.IGNORECASE) or re.search(pat, cmd, re.IGNORECASE):
            return pat
    return None


# Comandos que so' leem. Confirmar `ls` e `git log` treina o Mestre a aprovar
# no automatico -- e ai' a confirmacao que importa passa batido tambem.
READONLY = {
    "ls", "cat", "head", "tail", "wc", "file", "stat", "du", "df", "pwd",
    "echo", "which", "whoami", "date", "uname", "env", "printenv", "id",
    "grep", "rg", "find", "fd", "tree", "diff", "sort", "uniq", "cut", "awk",
    "sed", "jq", "ps", "top", "free", "uptime", "hostname", "curl", "wget",
}
# Subcomando de leitura de ferramentas que tambem escrevem.
READONLY_SUB = {
    "git": {"log", "status", "diff", "show", "branch", "remote", "config",
            "rev-parse", "rev-list", "describe", "blame", "ls-files", "tag",
            "shortlog", "whatchanged", "cat-file", "count-objects"},
    "docker": {"ps", "images", "logs", "inspect", "version", "info", "stats"},
    "kubectl": {"get", "describe", "logs", "version", "explain"},
    "npm": {"list", "ls", "view", "outdated", "audit"},
    "pip": {"list", "show", "freeze"},
    "poetry": {"show", "check"},
    "uv": {"pip"},
}


def is_readonly(cmd: str) -> bool:
    """Comando que so' le'? Conservador: na duvida, retorna False."""
    s = cmd.strip()
    if not s or is_dangerous(s):
        return False
    # Redirecionamento escreve; substituicao de comando esconde o alvo real.
    if re.search(r"(?<![0-9])>|>>|\$\(|`|\bsudo\b|\btee\b|\bxargs\b", s):
        return False
    for part in re.split(r"\|\||&&|\||;", s):
        toks = part.strip().split()
        if not toks:
            continue
        base = Path(toks[0]).name
        if base in READONLY:
            continue
        subs = READONLY_SUB.get(base)
        if subs:
            args = [a for a in toks[1:] if not a.startswith("-")]
            if args and args[0] in subs:
                continue
        return False
    return True


def _shell_needs_confirm(args: dict) -> bool:
    return not is_readonly(str(args.get("command", "")))


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
    risk=_shell_needs_confirm,
)
def shell(command: str, cwd: str = "", timeout: int = 120) -> str:
    allowed = (os.environ.get("ATOM_ALLOW_DANGEROUS") == "1"
               or bool(Config.load().get("tools.shell_allow_dangerous", False)))
    hit = is_dangerous(command)
    if hit and not allowed:
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
