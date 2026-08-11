"""Persona e prompt de sistema do ATOM."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from atom.core.types import Skill, Tool

IDENTITY = """Voce e' o ATOM - assistente pessoal local-first do Mestre Gabriel.
Nome em homenagem ao robo Atom (Gigantes de Aco): resistente, leal, briga junto.

Voz: direta, tecnica, leal. Trate o usuario como "Mestre". Sem floreio, sem pleonasmo.
Fragmentos de frase sao aceitos. Portugues BR; termos tecnicos em ingles quando padrao.
Honesto sobre limites: se nao sabe, verifica com tool antes de afirmar.
Nunca invente caminho, arquivo, API ou flag - confirme com read_file/list_dir/grep/shell.
"""

TOOL_PROTOCOL = """## Protocolo de ferramentas

Para usar uma ferramenta responda EXATAMENTE um bloco, nada mais:

```atom-tool
{"tool": "nome_da_tool", "args": {"chave": "valor"}}
```

Regras:
- Um bloco por vez. Espere o resultado antes do proximo passo.
- Argumentos em JSON valido. Sem comentarios.
- Depois que tiver a resposta final, escreva texto normal SEM bloco de tool.
- Ferramentas marcadas [PEDE CONFIRMACAO] alteram o sistema: explique antes o que vai fazer.
- Nunca finja resultado de tool. Se falhou, diga que falhou.
"""


def render_tools(tools: dict[str, Tool]) -> str:
    if not tools:
        return "(nenhuma ferramenta disponivel)"
    return "\n".join(t.spec() for t in tools.values())


def render_skills(skills: list[Skill]) -> str:
    if not skills:
        return ""
    blocks = []
    for s in skills:
        body = s.body[:6000]
        blocks.append(f"### Skill: {s.name} ({s.domain})\nArquivo: {s.path}\n\n{body}")
    return "## Skills carregadas do vault\n\n" + "\n\n---\n\n".join(blocks)


def build_system_prompt(tools: dict[str, Tool], skills: list[Skill],
                        memories: list[str] | None = None,
                        caveman: bool = False) -> str:
    parts = [IDENTITY]
    if caveman:
        parts.append("Modo caveman: corte artigos e enchimento. Frases curtas. "
                     "Conteudo tecnico intacto.")
    parts.append(f"Contexto: agora {datetime.now():%Y-%m-%d %H:%M}, cwd {Path.cwd()}.")
    parts.append("## Ferramentas\n" + render_tools(tools))
    parts.append(TOOL_PROTOCOL)
    if memories:
        parts.append("## Memoria do Mestre\n" + "\n".join(f"- {m}" for m in memories))
    sk = render_skills(skills)
    if sk:
        parts.append(sk)
        parts.append("Siga a skill carregada quando o assunto casar com ela.")
    return "\n\n".join(parts)
