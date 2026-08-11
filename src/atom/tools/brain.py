"""Tools de memoria e tarefas (backed por SQLite)."""

from __future__ import annotations

from atom.core.registry import register
from atom.memory.store import get_store


@register("remember", "Grava fato duravel na memoria do ATOM.",
          {"key": "str", "value": "str", "tags": "str (opcional)"})
def remember(key: str, value: str, tags: str = "") -> str:
    fid = get_store().remember(key, value, tags)
    return f"OK: memorizado #{fid} [{key}]"


@register("recall", "Consulta memoria por termo (vazio = mais recentes).",
          {"query": "str (opcional)", "limit": "int (opcional)"})
def recall(query: str = "", limit: int = 10) -> str:
    rows = get_store().recall(query, limit)
    if not rows:
        return "(memoria vazia para esse termo)"
    return "\n".join(f"[{r['key']}] {r['value']}" + (f"  #{r['tags']}" if r["tags"] else "")
                     for r in rows)


@register("forget", "Apaga fato da memoria pela chave.", {"key": "str"}, dangerous=True)
def forget(key: str) -> str:
    n = get_store().forget(key)
    return f"OK: {n} registro(s) removido(s)" if n else "nada removido"


@register("task_add", "Cria tarefa pessoal.",
          {"title": "str", "project": "str (opcional)", "due": "str (opcional)"})
def task_add(title: str, project: str = "", due: str = "") -> str:
    tid = get_store().task_add(title, project, due)
    return f"OK: task #{tid} criada"


@register("task_list", "Lista tarefas (pending|done|all).", {"status": "str (opcional)"})
def task_list(status: str = "pending") -> str:
    rows = get_store().task_list(status)
    if not rows:
        return "(sem tarefas)"
    return "\n".join(
        f"#{r['id']} [{r['status']}] {r['title']}"
        + (f" ({r['project']})" if r["project"] else "")
        + (f" vence {r['due']}" if r["due"] else "")
        for r in rows)


@register("task_done", "Marca tarefa como concluida.", {"task_id": "int"})
def task_done(task_id: int) -> str:
    ok = get_store().task_done(int(task_id))
    return f"OK: task #{task_id} concluida" if ok else f"task #{task_id} nao encontrada"
