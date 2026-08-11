"""Carrega skills/agents markdown do vault Obsidian do Mestre.

Suporta dois formatos:
  - arquivo unico: Agents/Skills/backend_django_drf.md
  - pasta com SKILL.md: Agents/SEI/Skills/docker-specialist/SKILL.md
Frontmatter YAML opcional (name/description/triggers).
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

import yaml

from atom.core import paths
from atom.core.types import Skill

SKIP = {".git", ".obsidian", ".trash", "node_modules", "refs"}
SKIP_FILES = {"readme.md", "index.md", "tasks.md", "changelog.md"}
FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    m = FM_RE.match(text)
    if not m:
        return {}, text
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except Exception:
        data = {}
    return (data if isinstance(data, dict) else {}), text[m.end():]


def _derive_description(body: str) -> str:
    # 1a tentativa: secao "Quando usar"
    m = re.search(r"##+\s*Quando usar\s*\n(.+?)(?:\n##|\Z)", body, re.S | re.I)
    chunk = m.group(1) if m else body
    for line in chunk.splitlines():
        line = line.strip(" -*#\t")
        if line and not line.startswith(("!", "[", "|")):
            return line[:220]
    return "(sem descricao)"


def _domain_for(rel: Path) -> str:
    parts = [p.lower() for p in rel.parts]
    for key in ("sei", "java", "gsm"):
        if key in parts:
            return key
    return "geral"


def _kind_for(rel: Path) -> str:
    parts = [p.lower() for p in rel.parts]
    if "skills" in parts:
        return "skill"
    if "agents" in parts and rel.name.lower() != "atom.md":
        return "agent"
    return "doc"


def _iter_md(root: Path):
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d.lower() not in SKIP]
        for f in files:
            if f.lower().endswith(".md") and f.lower() not in SKIP_FILES:
                yield Path(dirpath, f)


@lru_cache(maxsize=1)
def load_all(vault: str = "") -> tuple[Skill, ...]:
    root = Path(vault) if vault else paths.default_vault()
    if not root.exists():
        return ()
    out: list[Skill] = []
    seen: set[str] = set()
    for md in _iter_md(root):
        rel = md.relative_to(root)
        kind = _kind_for(rel)
        if kind == "doc":
            continue
        try:
            text = md.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        fm, body = _parse_frontmatter(text)
        if md.name.upper() == "SKILL.md".upper():
            name = fm.get("name") or md.parent.name
        else:
            name = fm.get("name") or md.stem
        name = str(name).strip()
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        triggers = fm.get("triggers") or fm.get("keywords") or []
        if isinstance(triggers, str):
            triggers = [t.strip() for t in triggers.split(",")]
        out.append(Skill(
            name=name,
            path=str(md),
            domain=_domain_for(rel) if kind == "skill" else f"{_domain_for(rel)}/agent",
            description=str(fm.get("description") or _derive_description(body)),
            triggers=[str(t).lower() for t in triggers] + _auto_triggers(name),
            body=body.strip(),
        ))
    return tuple(sorted(out, key=lambda s: (s.domain, s.name)))


def _auto_triggers(name: str) -> list[str]:
    words = re.split(r"[\s_\-./]+", name.lower())
    return [w for w in words if len(w) > 2]


def find(name: str) -> Skill | None:
    target = name.lower().strip()
    skills = load_all()
    for s in skills:
        if s.name.lower() == target:
            return s
    for s in skills:
        if target in s.name.lower():
            return s
    return None


def route(query: str, limit: int = 2) -> list[Skill]:
    """Escolhe skills provaveis pela query do Mestre (scoring simples)."""
    q = query.lower()
    scored: list[tuple[int, Skill]] = []
    for s in load_all():
        score = 0
        for trig in set(s.triggers):
            if trig and trig in q:
                score += 3
        for word in re.split(r"\W+", s.description.lower()):
            if len(word) > 4 and word in q:
                score += 1
        if s.domain.split("/")[0] in q:
            score += 2
        if score:
            scored.append((score, s))
    scored.sort(key=lambda t: -t[0])
    return [s for _, s in scored[:limit]]


def reload() -> None:
    load_all.cache_clear()
