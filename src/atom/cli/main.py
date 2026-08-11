"""CLI do ATOM."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

import atom.tools  # noqa: F401  (popula registry)
from atom import __version__
from atom.agents import AtomAgent
from atom.cli import banner
from atom.core import paths
from atom.core.config import Config
from atom.core.registry import all_tools
from atom.engine import build as build_engine, probe
from atom.memory.store import get_store
from atom.skills import find as find_skill, load_all as load_skills

# Windows: console legado em cp1252 quebra com acento -> forca UTF-8
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

console = Console(soft_wrap=False)
app = typer.Typer(name="atom", help="ATOM - assistente pessoal local-first do Mestre Gabriel",
                  no_args_is_help=False, add_completion=False)
skill_app = typer.Typer(help="Skills do vault")
mem_app = typer.Typer(help="Memoria do ATOM")
task_app = typer.Typer(help="Tarefas")
cfg_app = typer.Typer(help="Configuracao")
app.add_typer(skill_app, name="skill")
app.add_typer(mem_app, name="mem")
app.add_typer(task_app, name="task")
app.add_typer(cfg_app, name="config")


def _agent(verbose: bool = True) -> AtomAgent:
    cfg = Config.load()

    def on_event(kind: str, payload: str) -> None:
        if not verbose:
            return
        if kind == "tool_call":
            console.print(f"[yellow]-> {payload}[/]")
        elif kind == "tool_result":
            console.print(f"[dim]{payload.splitlines()[0][:160] if payload else ''}[/]")
        elif kind == "skills" and payload != "nenhuma":
            console.print(f"[magenta]skills: {payload}[/]")
        elif kind in ("retry", "trim"):
            console.print(f"[dim yellow]{payload}[/]")

    return AtomAgent(cfg=cfg, on_event=on_event)


def _run(agent: AtomAgent, text: str):
    """Roda o turno com spinner.

    Sem isto o terminal fica identico a travado enquanto o modelo pensa:
    `engine.complete` bloqueia e nada e' impresso ate a resposta inteira chegar.
    """
    with console.status("[dim]ATOM pensando...[/]", spinner="dots"):
        return agent.run(text)


def _fmt_usage(u) -> str:
    if not u.total_tokens and not u.cost_usd:
        return "[dim](backend nao reporta uso)[/]"
    cost = f"  ~US$ {u.cost_usd:.4f}" if u.cost_usd else ""
    return (f"[dim]in {u.input_tokens}  out {u.output_tokens}  "
            f"cache r/w {u.cache_read}/{u.cache_write}{cost}[/]")


HELP = """[bold]comandos do chat[/]
  /clear /reset   limpa o contexto (e a sessao do backend)
  /cost           tokens e custo do turno e da sessao
  /model <nome>   troca de modelo (ex: /model opus, /model sonnet)
  /tools          lista ferramentas
  /skills         lista skills do vault
  /mem            lista memoria
  /help           esta ajuda
  /sair           encerra"""


# ---------------- comandos ----------------

@app.command()
def ask(pergunta: list[str] = typer.Argument(..., help="Pergunta ou ordem"),
        quiet: bool = typer.Option(False, "--quiet", "-q", help="Sem log de tools"),
        cost: bool = typer.Option(False, "--cost", help="Mostra tokens/custo no fim"),
        model: str = typer.Option("", "--model", "-m", help="Modelo (ex: opus, sonnet)")) -> None:
    """Uma pergunta, uma resposta (com uso de ferramentas)."""
    agent = _agent(verbose=not quiet)
    if model:
        agent.engine.model = model
    turn = agent.run(" ".join(pergunta)) if quiet else _run(agent, " ".join(pergunta))
    console.print(Markdown(turn.answer or "(vazio)"))
    if cost:
        console.print(_fmt_usage(turn.usage))


@app.command()
def chat() -> None:
    """Sessao interativa com o ATOM."""
    agent = _agent()
    banner.show(console, agent.engine.describe(), len(agent.tools), len(load_skills()))
    console.print("[dim]comandos: /clear /cost /model /tools /skills /mem /help /sair[/]\n")
    while True:
        try:
            user = console.input("[bold green]Mestre>[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[cyan]ATOM off.[/]")
            return
        if not user:
            continue
        low = user.lower()
        if low in ("/sair", "/exit", "/quit", "sair"):
            console.print("[cyan]ATOM off, Mestre.[/]")
            return
        if low in ("/reset", "/clear", "/limpar"):
            agent.reset()
            console.print("[dim]contexto limpo (sessao nova no backend)[/]")
            continue
        if low in ("/help", "/ajuda", "/?"):
            console.print(HELP)
            continue
        if low == "/cost":
            console.print("sessao: " + _fmt_usage(agent.engine.usage))
            continue
        if low.startswith("/model"):
            parts = user.split(maxsplit=1)
            if len(parts) == 1:
                console.print(f"modelo atual: [cyan]{agent.engine.describe()}[/]")
            else:
                agent.engine.model = parts[1].strip()
                agent.engine.new_session()
                console.print(f"[green]modelo -> {agent.engine.describe()}[/] "
                              "[dim](contexto reiniciado)[/]")
            continue
        if low == "/tools":
            tools()
            continue
        if low == "/skills":
            skill_list()
            continue
        if low == "/mem":
            mem_list("")
            continue
        try:
            turn = _run(agent, user)
        except KeyboardInterrupt:
            console.print("[yellow]turno cancelado[/]")
            continue
        console.print(f"\n[bold cyan]ATOM>[/]")
        console.print(Markdown(turn.answer or "(vazio)"))
        console.print(_fmt_usage(turn.usage))
        console.print()


@app.command()
def doctor() -> None:
    """Diagnostico: engines, tools, skills, paths."""
    cfg = Config.load()
    console.print(f"[bold]ATOM v{__version__}[/]")
    t = Table("item", "valor", show_header=False, box=None)
    t.add_row("python", sys.version.split()[0])
    t.add_row("atom home", str(paths.atom_home()))
    t.add_row("config", str(paths.config_file()) + ("" if paths.config_file().exists() else " [dim](default)[/]"))
    t.add_row("db", str(paths.db_file()))
    vault = paths.default_vault()
    t.add_row("vault", f"{vault} {'[green]ok[/]' if vault.exists() else '[red]ausente[/]'}")
    t.add_row("cwd", str(Path.cwd()))
    console.print(t)

    console.print("\n[bold]engines[/]")
    for name, ok in probe(cfg).items():
        console.print(f"  {'[green]OK  [/]' if ok else '[red]--  [/]'} {name}")
    try:
        eng = build_engine(cfg)
        console.print(f"  [cyan]ativo: {eng.describe()}[/]")
    except Exception as exc:
        console.print(f"  [red]nenhum engine ativo: {exc}[/]")

    skills = load_skills()
    console.print(f"\n[bold]tools[/] {len(all_tools())}   [bold]skills[/] {len(skills)}")
    st = get_store().stats()
    console.print(f"[bold]memoria[/] fatos={st['facts']} tarefas_pendentes={st['pending_tasks']}"
                  f" sessoes={st['sessions']}")


@app.command("tools")
def tools() -> None:
    """Lista ferramentas registradas."""
    t = Table("tool", "args", "descricao")
    for name, tool in sorted(all_tools().items()):
        t.add_row(f"[bold]{name}[/]" + (" [red]!*[/]" if tool.dangerous else ""),
                  ", ".join(tool.schema.keys()) or "-", tool.description)
    console.print(t)


@skill_app.command("list")
def skill_list() -> None:
    """Lista skills e agents do vault."""
    t = Table("nome", "dominio", "descricao")
    for s in load_skills():
        t.add_row(s.name, s.domain, s.description[:80])
    console.print(t)


@skill_app.command("show")
def skill_show(nome: str) -> None:
    """Mostra conteudo de uma skill."""
    s = find_skill(nome)
    if not s:
        console.print(f"[red]skill '{nome}' nao encontrada[/]")
        raise typer.Exit(1)
    console.print(f"[dim]{s.path}[/]\n")
    console.print(Markdown(s.body[:12000]))


@skill_app.command("route")
def skill_route(query: list[str]) -> None:
    """Mostra qual skill o ATOM escolheria."""
    from atom.skills import route
    hits = route(" ".join(query), limit=5)
    if not hits:
        console.print("[dim]nenhuma skill casou; ATOM responde direto[/]")
        return
    for s in hits:
        console.print(f"- [bold]{s.name}[/] ({s.domain})")


@mem_app.command("list")
def mem_list(query: str = typer.Argument("", help="filtro")) -> None:
    """Lista fatos memorizados."""
    rows = get_store().recall(query, 50)
    if not rows:
        console.print("[dim](memoria vazia)[/]")
        return
    t = Table("chave", "valor", "tags")
    for r in rows:
        t.add_row(r["key"], r["value"][:80], r["tags"])
    console.print(t)


@mem_app.command("add")
def mem_add(key: str, value: list[str], tags: str = typer.Option("", "--tags")) -> None:
    """Grava fato na memoria."""
    fid = get_store().remember(key, " ".join(value), tags)
    console.print(f"[green]memorizado #{fid}[/]")


@mem_app.command("forget")
def mem_forget(key: str) -> None:
    """Apaga fato."""
    n = get_store().forget(key)
    console.print(f"[green]{n} removido(s)[/]" if n else "[dim]nada removido[/]")


@task_app.command("add")
def task_add(titulo: list[str], project: str = typer.Option("", "--project", "-p")) -> None:
    """Cria tarefa."""
    tid = get_store().task_add(" ".join(titulo), project)
    console.print(f"[green]task #{tid}[/]")


@task_app.command("list")
def task_list(status: str = typer.Option("pending", "--status", "-s")) -> None:
    """Lista tarefas."""
    rows = get_store().task_list(status)
    if not rows:
        console.print("[dim](sem tarefas)[/]")
        return
    t = Table("id", "status", "titulo", "projeto")
    for r in rows:
        t.add_row(str(r["id"]), r["status"], r["title"], r["project"])
    console.print(t)


@task_app.command("done")
def task_done(task_id: int) -> None:
    """Conclui tarefa."""
    ok = get_store().task_done(task_id)
    console.print(f"[green]task #{task_id} concluida[/]" if ok else "[red]nao encontrada[/]")


@app.command()
def digest(llm: bool = typer.Option(False, "--llm", help="Resumo em linguagem natural (gasta token)"),
           all_repos: bool = typer.Option(False, "--all", help="Inclui repos limpos"),
           save: bool = typer.Option(False, "--save", help="Grava no journal do vault")) -> None:
    """Briefing do dia: repos, tarefas, memoria."""
    from atom.routines.digest import LLM_PROMPT, collect, to_text
    cfg = Config.load()
    with console.status("[dim]varrendo repos...[/]", spinner="dots"):
        d = collect(cfg)
    text = to_text(d, only_interesting=not all_repos)
    console.print(Markdown(text))

    if llm:
        agent = _agent(verbose=False)
        turn = _run(agent, LLM_PROMPT + text)
        console.print("\n[bold cyan]Leitura do ATOM>[/]")
        console.print(Markdown(turn.answer or "(vazio)"))
        console.print(_fmt_usage(turn.usage))
        text += "\n\n## Leitura do ATOM\n\n" + turn.answer

    if save:
        from atom.tools.vault import journal
        console.print(f"[green]{journal(text)}[/]")


@app.command()
def daemon(once: bool = typer.Option(False, "--once", help="Roda o que estiver vencido e sai"),
           force: bool = typer.Option(False, "--force", help="Roda tudo, vencido ou nao"),
           tick: int = typer.Option(20, "--tick", help="Segundos entre verificacoes")) -> None:
    """Agendador de rotinas (ver `routines.items` no config)."""
    from atom.routines.daemon import load_routines, run_due, serve

    def on_event(kind: str, payload: str) -> None:
        color = {"start": "dim", "done": "green", "fail": "red", "boot": "cyan"}.get(kind, "dim")
        console.print(f"[{color}]{datetime.now():%H:%M:%S} {kind}: {payload}[/]")

    cfg = Config.load()
    routines = load_routines(cfg)
    if not routines:
        console.print("[yellow]nenhuma rotina em routines.items do config[/]")
        raise typer.Exit(1)

    if once or force:
        ran = run_due(cfg, force=force, on_event=on_event)
        console.print(f"[green]{len(ran)} rotina(s) executada(s)[/]" if ran
                      else "[dim]nada vencido[/]")
        return
    console.print("[dim]Ctrl+C para parar[/]")
    try:
        serve(cfg, tick=tick, on_event=on_event)
    except KeyboardInterrupt:
        console.print("\n[cyan]daemon parado[/]")


@app.command("routines")
def routines_cmd() -> None:
    """Lista rotinas e ultima execucao."""
    from atom.routines.daemon import load_routines
    rows = load_routines(Config.load())
    if not rows:
        console.print("[dim](nenhuma rotina configurada)[/]")
        return
    store = get_store()
    t = Table("rotina", "schedule", "acao", "ativa", "ultima", "status")
    for r in rows:
        last = store.routine_last(r.name)
        t.add_row(r.name, r.schedule, r.action[:40],
                  "sim" if r.enabled else "nao",
                  (last or {}).get("started_at", "-"),
                  (last or {}).get("status", "-"))
    console.print(t)


@cfg_app.command("show")
def config_show() -> None:
    """Mostra config efetiva."""
    import yaml
    console.print(yaml.safe_dump(Config.load().as_dict(), allow_unicode=True, sort_keys=False))


@cfg_app.command("set")
def config_set(chave: str, valor: str) -> None:
    """Define valor (ex: atom config set engine.provider ollama)."""
    cfg = Config.load()
    val: object = valor
    if valor.lower() in ("true", "false"):
        val = valor.lower() == "true"
    elif valor.isdigit():
        val = int(valor)
    cfg.set(chave, val)
    cfg.save()
    console.print(f"[green]{chave} = {val}[/]  -> {paths.config_file()}")


@cfg_app.command("init")
def config_init() -> None:
    """Escreve config default em ~/.atom/config.yaml."""
    cfg = Config.load()
    cfg.save()
    console.print(f"[green]config criada:[/] {paths.config_file()}")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context,
         version: bool = typer.Option(False, "--version", "-v")) -> None:
    if version:
        console.print(f"ATOM v{__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        chat()


if __name__ == "__main__":
    app()
