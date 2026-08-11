"""Skills sob demanda.

O prompt so' carrega o topo da skill roteada. Quando o modelo precisa do
resto -- ou de uma skill que o roteador nao escolheu -- ele puxa por aqui,
em vez de pagarmos 6KB por turno em toda conversa.
"""

from __future__ import annotations

from atom.core.registry import register
from atom.skills import find, load_all

MAX_SKILL = 20_000


@register("skill_list", "Lista skills/agents disponiveis no vault (nome, dominio, descricao).",
          {"filtro": "str (opcional)"})
def skill_list(filtro: str = "") -> str:
    f = filtro.lower().strip()
    rows = []
    for s in load_all():
        if f and f not in s.name.lower() and f not in s.description.lower():
            continue
        rows.append(f"- {s.name} ({s.domain}): {s.description[:110]}")
    return "\n".join(rows) or "(nenhuma skill)"


@register("skill_read", "Le o conteudo completo de uma skill do vault pelo nome.",
          {"nome": "str", "start": "int (opcional)", "end": "int (opcional)"})
def skill_read(nome: str, start: int = 0, end: int = 0) -> str:
    s = find(nome)
    if not s:
        return f"ERRO: skill '{nome}' nao encontrada. Use skill_list para ver as disponiveis."
    body = s.body
    if start or end:
        lines = body.splitlines()
        body = "\n".join(lines[max(0, start - 1): end or len(lines)])
    if len(body) > MAX_SKILL:
        body = body[:MAX_SKILL] + f"\n... [truncado, {len(s.body)} chars no total]"
    return f"# {s.name} ({s.domain})\nArquivo: {s.path}\n\n{body}"
