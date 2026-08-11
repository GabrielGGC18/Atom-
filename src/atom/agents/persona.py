"""Persona e prompt de sistema do ATOM.

Separacao proposital em duas partes:

- `build_system_prompt`  -> ESTAVEL. Identidade, ferramentas, protocolo. Nao
  muda entre turnos, entao o backend consegue cachear (prompt cache) e a
  sessao do claude_cli sobrevive sem invalidar.
- `build_context_block`  -> VOLATIL. Data/hora, cwd, memoria e skills do turno.
  Vai colado no input do usuario, nao no system.

Antes tudo era system: qualquer mudanca (ate o relogio virar de minuto)
derrubava o cache e reenviava o prompt inteiro.
"""

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

CAVEMAN = """Modo caveman: corte artigos, filler e pleonasmo. Frases curtas, fragmentos OK.
Conteudo tecnico, nomes de arquivo, comandos e mensagens de erro ficam INTACTOS.
Sem narrar o que vai fazer antes de fazer. Sem recapitular o que ja foi dito.
Escreva normal (sem cortar) em: alerta de seguranca, confirmacao de acao destrutiva,
e passo a passo onde a ordem importa."""

TOOL_PROTOCOL = """## Protocolo de ferramentas

Para usar ferramentas responda APENAS blocos, nada mais:

```atom-tool
{"tool": "nome_da_tool", "args": {"chave": "valor"}}
```

Regras:
- Pode emitir VARIOS blocos numa mesma resposta quando as chamadas forem
  independentes (ex: ler 3 arquivos). Elas rodam em paralelo e voltam juntas.
- Se uma chamada depende do resultado da outra, mande so' a primeira e espere.
- Argumentos em JSON valido. Sem comentarios.
- Depois que tiver a resposta final, escreva texto normal SEM bloco de tool.
- Ferramentas marcadas [PEDE CONFIRMACAO] alteram o sistema: explique antes o que vai fazer.
- Nunca finja resultado de tool. Se falhou, diga que falhou.
- Para MOSTRAR um exemplo de bloco sem executar, use ~~~ no lugar das crases.
- NUNCA termine a resposta anunciando o que vai fazer ("vou abrir X", "deixa eu
  ver Y"). Texto sem bloco encerra o turno e a acao nunca acontece. Se falta um
  passo, emita o bloco de tool AGORA e anuncie depois, com o resultado na mao.
"""


def render_tools(tools: dict[str, Tool]) -> str:
    if not tools:
        return "(nenhuma ferramenta disponivel)"
    return "\n".join(t.spec() for t in tools.values())


def render_skills(skills: list[Skill], max_chars: int = 2500) -> str:
    """Injeta a skill cortada; o resto fica sob demanda via `skill_read`.

    Corpo inteiro de skill passa de 6KB. Multiplicado por turno, e' o maior
    gasto fixo do prompt -- e quase sempre so' o topo importa.
    """
    if not skills:
        return ""
    blocks = []
    for s in skills:
        body = s.body
        if len(body) > max_chars:
            body = body[:max_chars] + (
                f"\n\n[... cortado. {len(s.body)} chars no total. "
                f"Use skill_read(\"{s.name}\") se precisar do restante.]")
        blocks.append(f"### Skill: {s.name} ({s.domain})\nArquivo: {s.path}\n\n{body}")
    return "## Skills carregadas do vault\n\n" + "\n\n---\n\n".join(blocks)


def build_system_prompt(tools: dict[str, Tool], caveman: bool = False) -> str:
    """Parte estavel do prompt. Mantenha deterministica: nada de relogio aqui."""
    parts = [IDENTITY]
    if caveman:
        parts.append(CAVEMAN)
    parts.append("## Ferramentas\n" + render_tools(tools))
    parts.append(TOOL_PROTOCOL)
    return "\n\n".join(parts)


def project_index(roots: list[Path], limit: int = 40) -> str:
    """Caminho de cada projeto conhecido.

    Sem isto o modelo chuta o diretorio ao ouvir "o projeto FastAPI" e abre o
    errado. Custa ~1 linha por projeto e evita varias chamadas de list_dir.
    """
    rows: list[str] = []
    for root in roots:
        try:
            if not root.is_dir():
                continue
            for d in sorted(root.iterdir()):
                if d.is_dir() and not d.name.startswith("."):
                    rows.append(f"- {d}")
        except OSError:
            continue
    if not rows:
        return ""
    extra = f"\n- (+{len(rows) - limit} outros)" if len(rows) > limit else ""
    return ("Projetos do Mestre (use o caminho exato; nao adivinhe):\n"
            + "\n".join(rows[:limit]) + extra)


def build_context_block(skills: list[Skill], memories: list[str] | None = None,
                        skill_max_chars: int = 2500,
                        projects: str = "") -> str:
    """Parte volatil do turno. Vazio quando nao ha nada relevante."""
    parts = [f"[contexto: {datetime.now():%Y-%m-%d %H:%M}, cwd {Path.cwd()}]"]
    if projects:
        parts.append(projects)
    if memories:
        parts.append("Memoria do Mestre:\n" + "\n".join(f"- {m}" for m in memories))
    sk = render_skills(skills, skill_max_chars)
    if sk:
        parts.append(sk)
        parts.append("Siga a skill carregada quando o assunto casar com ela.")
    return "\n\n".join(parts)
