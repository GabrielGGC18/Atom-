"""Briefing do dia: repos, tarefas, memoria.

Determinístico por padrao -- roda em ~1s, custo zero, funciona sem engine.
O resumo em linguagem natural e' opcional (`--llm`), porque briefing e' a
coisa que mais se roda por dia e nao vale queimar token em toda execucao.
"""

from __future__ import annotations

import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from atom.core.config import Config
from atom.memory.store import get_store

MAX_DEPTH = 3


@dataclass
class RepoState:
    path: Path
    branch: str = ""
    dirty: int = 0
    ahead: int = 0
    behind: int = 0
    last_commit: str = ""
    last_when: str = ""
    error: str = ""

    @property
    def interesting(self) -> bool:
        return bool(self.dirty or self.ahead or self.behind or self.error)


@dataclass
class Digest:
    when: datetime = field(default_factory=datetime.now)
    repos: list[RepoState] = field(default_factory=list)
    tasks: list[dict] = field(default_factory=list)
    facts: list[dict] = field(default_factory=list)
    sessions: int = 0


def _git(repo: Path, *args: str) -> str:
    try:
        p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                           text=True, timeout=15, encoding="utf-8", errors="replace")
        return p.stdout.strip() if p.returncode == 0 else ""
    except Exception:
        return ""


def _scan_repo(repo: Path) -> RepoState:
    st = RepoState(path=repo)
    st.branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD") or "(sem branch)"
    status = _git(repo, "status", "--porcelain")
    st.dirty = len([l for l in status.splitlines() if l.strip()])
    counts = _git(repo, "rev-list", "--left-right", "--count", "@{upstream}...HEAD")
    if counts:
        parts = counts.split()
        if len(parts) == 2:
            st.behind, st.ahead = int(parts[0]), int(parts[1])
    log = _git(repo, "log", "-1", "--format=%s\x1f%cr")
    if log and "\x1f" in log:
        st.last_commit, st.last_when = log.split("\x1f", 1)
    return st


def find_repos(roots: list[Path]) -> list[Path]:
    """Repos ate MAX_DEPTH abaixo das raizes. Nao desce dentro de repo."""
    found: list[Path] = []
    seen: set[Path] = set()

    def walk(d: Path, depth: int) -> None:
        if depth > MAX_DEPTH or d in seen:
            return
        seen.add(d)
        if (d / ".git").exists():
            found.append(d)
            return
        try:
            for child in sorted(d.iterdir()):
                if child.is_dir() and not child.name.startswith("."):
                    walk(child, depth + 1)
        except OSError:
            return

    for r in roots:
        if r.is_dir():
            walk(r.resolve(), 0)
    return found


def repo_roots(cfg: Config) -> list[Path]:
    raw = cfg.get("digest.repo_roots") or []
    if raw:
        return [Path(r).expanduser() for r in raw]
    home = Path.home()
    return [home / "projects", home / "gabriel-projects"]


def collect(cfg: Config | None = None) -> Digest:
    cfg = cfg or Config.load()
    d = Digest()
    store = get_store()
    repos = find_repos(repo_roots(cfg))
    if repos:
        with ThreadPoolExecutor(max_workers=8) as pool:
            d.repos = list(pool.map(_scan_repo, repos))
    d.repos.sort(key=lambda r: (not r.interesting, str(r.path)))
    d.tasks = store.task_list("pending")
    cutoff = (datetime.now() - timedelta(days=7)).isoformat(timespec="seconds")
    d.facts = [f for f in store.recall("", 50) if f.get("updated_at", "") >= cutoff]
    d.sessions = store.stats().get("sessions", 0)
    return d


def to_text(d: Digest, only_interesting: bool = True) -> str:
    """Versao markdown, usada na tela, no --save e como input do --llm."""
    out = [f"# Briefing ATOM - {d.when:%d/%m/%Y %H:%M}", ""]

    repos = [r for r in d.repos if r.interesting] if only_interesting else d.repos
    out.append(f"## Repositorios ({len(repos)} com pendencia / {len(d.repos)} varridos)")
    if not repos:
        out.append("- tudo limpo e sincronizado")
    for r in repos:
        bits = [f"branch {r.branch}"]
        if r.dirty:
            bits.append(f"{r.dirty} alterado(s)")
        if r.ahead:
            bits.append(f"{r.ahead} a enviar")
        if r.behind:
            bits.append(f"{r.behind} a puxar")
        tail = f" | ultimo: {r.last_commit[:60]} ({r.last_when})" if r.last_commit else ""
        out.append(f"- **{r.path.name}** - {', '.join(bits)}{tail}")

    out += ["", f"## Tarefas pendentes ({len(d.tasks)})"]
    if not d.tasks:
        out.append("- nenhuma")
    for t in d.tasks[:20]:
        proj = f" [{t['project']}]" if t.get("project") else ""
        out.append(f"- #{t['id']}{proj} {t['title']}")

    if d.facts:
        out += ["", f"## Memoria recente ({len(d.facts)} nos ultimos 7 dias)"]
        for f in d.facts[:10]:
            out.append(f"- {f['key']}: {str(f['value'])[:100]}")

    return "\n".join(out)


LLM_PROMPT = """Abaixo o briefing bruto do dia. Resuma em no maximo 6 linhas para o Mestre:
o que exige acao hoje, o que esta parado, e o risco mais provavel.
Nao repita a lista inteira - destaque. Se nao houver nada relevante, diga isso em uma linha.

"""
