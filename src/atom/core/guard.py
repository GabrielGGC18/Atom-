"""Contencao de escrita e protecao de dados sensiveis.

`tools.workspace_guard` existia no config mas nunca era lido por ninguem --
dava falsa sensacao de contencao. Aqui ele passa a valer de fato.

Politica:
- LEITURA livre (o Mestre precisa ler qualquer projeto), menos chave privada.
- ARQUIVO DE SEGREDO (.env, .pem, credentials) e' lido com os valores
  mascarados: o agent ve quais variaveis existem, nao o conteudo delas.
- SAIDA DE TOOL passa por `redact` antes de virar contexto. Sem isso um
  `shell: cat .env` contorna a protecao do read_file.
- ESCRITA so' dentro das raizes permitidas.

Nada disto impede um comando deliberadamente ofuscado. E' rede de protecao
contra acidente -- que e' o caso comum -- nao contra adversario.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from atom.core.config import Config

# Chave privada / credencial pura: nao ha' o que mascarar, nao se le'.
BLOCK_NAMES = {"id_rsa", "id_ed25519", "id_ecdsa", "id_dsa", ".htpasswd",
               ".netrc", ".pgpass"}
BLOCK_DIRS = {".ssh", ".gnupg"}

# Arquivo util cujo conteudo e' sensivel: le' mascarado.
MASK_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".keystore", ".jks"}
MASK_NAMES = {"credentials", "credentials.json", "service-account.json",
              ".npmrc", ".pypirc", ".dockercfg", "secrets.yaml", "secrets.yml"}


def is_secret_file(path: str | Path) -> bool:
    p = Path(path)
    name = p.name.lower()
    if name == ".env" or name.startswith(".env."):
        return True
    if name in MASK_NAMES or p.suffix.lower() in MASK_SUFFIXES:
        return True
    return "secret" in name and p.suffix.lower() in {".json", ".yaml", ".yml", ".txt"}


# Nome de variavel que indica segredo no valor.
_SECRET_KEY = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|PASSWD|PWD|API_?KEY|ACCESS_?KEY|"
    r"PRIVATE_?KEY|CREDENTIAL|AUTH|AWS_[A-Z_]*KEY|AWS_SESSION|DSN|"
    r"DATABASE_URL|CONN(?:ECTION)?_?STRING)[A-Z0-9_]*)\s*([:=])\s*(\S+)")

# Segredos reconheciveis pelo proprio formato, com ou sem nome de variavel.
_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{16,}"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    re.compile(r"(?i)\b[a-z][a-z0-9+.\-]*://[^\s:/@]+:([^\s@/]{3,})@"),  # senha em URL
]

MASK = "***REDIGIDO***"


# Valor que e' codigo, nao segredo: `SECRET_KEY = os.getenv("SECRET_KEY")`.
# Mascarar isso cegaria o agent no proprio fonte, que e' o caso mais comum.
_CODE_VALUE = re.compile(
    r"""^(?:[\w.]+\s*[\(\[]|os\.environ|process\.env|import\b|from\b|["']?\{\{|\$\{|<)""")
# Identificador puro sem digito (`str`, `request`, `Field`, `token`) e'
# anotacao de tipo ou nome de variavel. Chave de verdade quase sempre mistura
# digito -- `k9dJ2mQp7xVn` nao passa por aqui.
_BARE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z_]{0,20}$")
_PLACEHOLDER = {"", '""', "''", "none", "null", "changeme", "xxx", "your_key_here",
                "todo", "...", "-"}


def _mask_kv(m: re.Match) -> str:
    val = m.group(3)
    if val.lower().strip("\"'") in _PLACEHOLDER or val.startswith("$"):
        return m.group(0)  # placeholder: mostrar ajuda e nao vaza nada
    if _CODE_VALUE.match(val):
        return m.group(0)  # chamada de funcao / indexacao, nao literal
    if _BARE_IDENT.match(val.strip("\"'")):
        return m.group(0)  # anotacao de tipo ou nome de variavel
    return f"{m.group(1)}{m.group(2)}{MASK}"


def redact(text: str) -> str:
    """Troca segredos por marcador. Idempotente e seguro em texto qualquer."""
    if not text:
        return text
    out = _SECRET_KEY.sub(_mask_kv, text)
    for rx in _PATTERNS:
        if rx.groups:
            out = rx.sub(lambda m: m.group(0).replace(m.group(1), MASK), out)
        else:
            out = rx.sub(MASK, out)
    return out


def masking_enabled(cfg: Config | None = None) -> bool:
    cfg = cfg or Config.load()
    return bool(cfg.get("tools.mask_secrets", True))


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
    """Motivo do bloqueio, ou None se liberado (pode exigir mascara)."""
    cfg = cfg or Config.load()
    if not cfg.get("tools.workspace_guard", True):
        return None
    p = Path(path).expanduser()
    if p.name in BLOCK_NAMES or (set(p.parts) & BLOCK_DIRS):
        return (f"BLOQUEADO: {p} e' chave privada/credencial. "
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
