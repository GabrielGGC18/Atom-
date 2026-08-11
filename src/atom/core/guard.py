"""Contencao de escrita e leitura de segredos.

`tools.workspace_guard` existia no config mas nunca era lido por ninguem --
dava falsa sensacao de contencao. Aqui ele passa a valer de fato.

Politica:
- LEITURA livre (o Mestre precisa ler qualquer projeto), menos segredos obvios.
- ESCRITA so' dentro das raizes permitidas.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from atom.core.config import Config

# Arquivos que nao interessam ao agent e vazam credencial se forem parar no prompt.
SECRET_NAMES = {"id_rsa", "id_ed25519", "id_ecdsa", "id_dsa", ".htpasswd",
                "credentials", ".netrc", ".pgpass"}
SECRET_DIRS = {".ssh", ".gnupg"}


def _roots(cfg: Config) -> list[Path]:
    raw = cfg.get("tools.write_roots") or []
    out = [Path(r).expanduser().resolve() for r in raw]
    if not out:
        home = Path.home()
        out = [Path.cwd().resolve(), home / "projects", home / "gabriel-projects",
               home / ".atom", Path(tempfile.gettempdir()).resolve()]
    return out


def _inside(p: Path, root: Path) -> bool:
    try:
        p.relative_to(root)
        return True
    except ValueError:
        return False


def check_read(path: str, cfg: Config | None = None) -> str | None:
    """Devolve motivo do bloqueio, ou None se liberado."""
    cfg = cfg or Config.load()
    if not cfg.get("tools.workspace_guard", True):
        return None
    p = Path(path).expanduser()
    parts = set(p.parts)
    if p.name in SECRET_NAMES or (parts & SECRET_DIRS):
        return (f"BLOQUEADO: {p} parece conter credencial. "
                "Desligue com `atom config set tools.workspace_guard false` se for intencional.")
    return None


def check_write(path: str, cfg: Config | None = None) -> str | None:
    cfg = cfg or Config.load()
    if not cfg.get("tools.workspace_guard", True):
        return None
    p = Path(path).expanduser().resolve()
    roots = _roots(cfg)
    if any(_inside(p, r) for r in roots):
        return None
    listed = ", ".join(str(r) for r in roots)
    return (f"BLOQUEADO: escrita fora das raizes permitidas ({listed}). "
            f"Alvo: {p}. Ajuste com `atom config set tools.write_roots '<lista>'` "
            "ou desligue com `atom config set tools.workspace_guard false`.")
