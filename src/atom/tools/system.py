"""Info de maquina e contexto de trabalho."""

from __future__ import annotations

import os
import platform
import shutil
import socket
from datetime import datetime
from pathlib import Path

from atom.core import paths
from atom.core.registry import register


@register("sysinfo", "Info do host: SO, disco, cwd, hora, ferramentas presentes.", {})
def sysinfo() -> str:
    total, used, free = shutil.disk_usage(Path.home().anchor or "/")
    tools = {t: bool(shutil.which(t)) for t in
             ("git", "node", "npm", "docker", "python", "uv", "claude", "ollama")}
    lines = [
        f"host      : {socket.gethostname()}",
        f"so        : {platform.system()} {platform.release()} ({platform.machine()})",
        f"python    : {platform.python_version()}",
        f"agora     : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"cwd       : {Path.cwd()}",
        f"atom home : {paths.atom_home()}",
        f"vault     : {paths.default_vault()}",
        f"disco     : {free // 2**30}GB livre de {total // 2**30}GB",
        "tools     : " + ", ".join(f"{k}{'+' if v else '-'}" for k, v in tools.items()),
    ]
    return "\n".join(lines)


@register("git_status", "Status resumido do repo git no caminho dado.",
          {"path": "str (opcional)"})
def git_status(path: str = ".") -> str:
    import subprocess
    try:
        out = subprocess.run(["git", "-C", path or ".", "status", "--short", "--branch"],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=30)
    except Exception as exc:
        return f"ERRO: {exc}"
    if out.returncode != 0:
        return (out.stderr or "nao e' repo git").strip()
    return out.stdout.strip() or "(working tree limpo)"


@register("open_path", "Abre arquivo/pasta/URL no app padrao do sistema.", {"target": "str"})
def open_path(target: str) -> str:
    try:
        if os.name == "nt":
            os.startfile(target)  # type: ignore[attr-defined]
        else:
            import subprocess
            subprocess.Popen(["xdg-open", target])
    except Exception as exc:
        return f"ERRO: {exc}"
    return f"OK: abrindo {target}"
