"""Agent loop ReAct do ATOM: pensa -> chama tool -> observa -> responde."""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

from atom.agents.persona import build_context_block, build_system_prompt, project_index
from atom.core.config import Config
from atom.core.guard import masking_enabled, redact
from atom.core.registry import enabled_tools
from atom.core.types import Message, ToolCall, ToolResult
from atom.engine import Engine, EngineError, build as build_engine
from atom.engine.base import EngineTransientError, Usage
from atom.memory.store import get_store
from atom.skills import route as route_skills

TOOL_BLOCK = re.compile(r"```atom-tool\s*(.+?)```", re.S)
# So' vale como fallback se a resposta INTEIRA for o JSON -- senao um exemplo
# citado no meio da explicacao viraria execucao real.
JSON_ONLY = re.compile(r'^\s*(\{\s*"tool"\s*:.*\})\s*$', re.S)

# ~3.6 chars por token em pt-BR. Serve para orcamento, nao para cobranca.
CHARS_PER_TOKEN = 3.6


def parse_tool_calls(text: str) -> list[ToolCall]:
    """Todos os blocos de tool da resposta. Vazio = resposta final."""
    out: list[ToolCall] = []
    for raw in TOOL_BLOCK.findall(text):
        call = _one(raw)
        if call:
            out.append(call)
    if out:
        return out
    m = JSON_ONLY.match(text)
    if m:
        call = _one(m.group(1))
        if call:
            return [call]
    return []


def _one(raw: str) -> ToolCall | None:
    try:
        data = json.loads(raw.strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    name = data.get("tool")
    if not name:
        return None
    args = data.get("args") or {}
    if not isinstance(args, dict):
        return None
    return ToolCall(tool=str(name), args=args, raw=raw.strip())


def parse_tool_call(text: str) -> ToolCall | None:
    """Compat: primeira chamada apenas."""
    calls = parse_tool_calls(text)
    return calls[0] if calls else None


@dataclass
class Turn:
    calls: list[ToolCall] = field(default_factory=list)
    results: list[ToolResult] = field(default_factory=list)
    answer: str = ""
    steps: int = 0
    usage: Usage = field(default_factory=Usage)


class AtomAgent:
    def __init__(self, cfg: Config | None = None, engine: Engine | None = None,
                 session_id: str | None = None,
                 on_event: Callable[[str, str], None] | None = None,
                 on_confirm: Callable[[ToolCall], bool] | None = None) -> None:
        self.cfg = cfg or Config.load()
        self.engine = engine or build_engine(self.cfg)
        self.session_id = session_id or uuid.uuid4().hex[:12]
        self.on_event = on_event or (lambda kind, payload: None)
        # Sem confirmador registrado a tool roda direto: `atom ask` e o daemon
        # nao tem ninguem no teclado para responder.
        self.on_confirm = on_confirm
        self.confirm_dangerous = bool(self.cfg.get("tools.confirm_dangerous", True))
        self.mask = masking_enabled(self.cfg)
        self.tools = enabled_tools(self.cfg.get("tools.enabled"))
        self.max_steps = int(self.cfg.get("agent.max_steps", 12))
        self.retries = int(self.cfg.get("agent.retries", 2))
        self.parallel = int(self.cfg.get("agent.parallel_tools", 4))
        self.tool_limit = int(self.cfg.get("agent.tool_result_chars", 4000))
        self.max_ctx = int(self.cfg.get("agent.max_context_chars", 60000))
        self.skill_chars = int(self.cfg.get("agent.skill_max_chars", 2500))
        self._projects = self._project_index()
        self.history: list[Message] = []
        self.store = get_store()
        self._system = build_system_prompt(
            self.tools, caveman=bool(self.cfg.get("agent.caveman", False)))

    def _project_index(self) -> str:
        if not self.cfg.get("agent.project_index", True):
            return ""
        raw = self.cfg.get("digest.repo_roots") or []
        roots = ([Path(r).expanduser() for r in raw] if raw
                 else [Path.home() / "projects", Path.home() / "gabriel-projects"])
        return project_index(roots)

    # --- contexto ---
    def _memories(self, query: str) -> list[str]:
        if not self.cfg.get("memory.enabled", True):
            return []
        rows = self.store.recall(query, int(self.cfg.get("memory.max_recall", 8)))
        # Sem casamento => nao injeta nada. Fato aleatorio no prompt e' ruido
        # que o modelo tenta usar.
        return [f"{r['key']}: {r['value']}" for r in rows]

    def _trim(self, messages: list[Message]) -> list[Message]:
        """Corta do meio pra caber no orcamento, preservando system e o fim."""
        budget = self.max_ctx
        total = sum(len(m.content) for m in messages)
        if total <= budget:
            return messages
        head = [m for m in messages if m.role == "system"]
        tail = [m for m in messages if m.role != "system"]
        size = sum(len(m.content) for m in head)
        keep: list[Message] = []
        for m in reversed(tail):
            if size + len(m.content) > budget and keep:
                break
            size += len(m.content)
            keep.append(m)
        keep.reverse()
        dropped = len(tail) - len(keep)
        if dropped > 0:
            self.on_event("trim", f"{dropped} mensagens antigas cortadas do contexto")
        return head + keep

    # --- execucao de tool ---
    def run_tool(self, call: ToolCall) -> ToolResult:
        tool = self.tools.get(call.tool)
        if not tool:
            known = ", ".join(sorted(self.tools)[:20])
            return ToolResult(call.tool, False, "",
                              f"tool '{call.tool}' nao existe ou esta desativada. Disponiveis: {known}")
        if self.confirm_dangerous and self.on_confirm and tool.risky(call.args):
            if not self.on_confirm(call):
                return ToolResult(call.tool, False, "",
                                  "recusado pelo Mestre. Nao repita esta chamada; "
                                  "proponha outro caminho ou pergunte.")
        try:
            out = tool.handler(**call.args)
        except TypeError as exc:
            return ToolResult(call.tool, False, "", f"args invalidos: {exc}")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(call.tool, False, "", f"{type(exc).__name__}: {exc}")
        text = str(out)
        # Ultima barreira: pega segredo que veio por shell (`cat .env`, `env`),
        # http_get ou qualquer tool que nao conheca a politica.
        return ToolResult(call.tool, True, redact(text) if self.mask else text)

    def run_tools(self, calls: list[ToolCall]) -> list[ToolResult]:
        if len(calls) == 1:
            return [self.run_tool(calls[0])]
        workers = max(1, min(self.parallel, len(calls)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(self.run_tool, calls))

    # --- engine com retry ---
    def _complete(self, messages: list[Message]) -> str:
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                return self.engine.complete(self._trim(messages))
            except EngineTransientError as exc:
                last = exc
                if attempt < self.retries:
                    wait = 2 ** attempt
                    self.on_event("retry", f"falha temporaria ({exc}); retry em {wait}s")
                    time.sleep(wait)
            except EngineError:
                raise
        raise EngineError(f"falhou apos {self.retries + 1} tentativas: {last}")

    # --- loop principal ---
    def run(self, user_input: str) -> Turn:
        turn = Turn()
        before = Usage(**vars(self.engine.usage))
        self.store.log_turn(self.session_id, "user", user_input)

        skills = route_skills(user_input)
        self.on_event("skills", ", ".join(s.name for s in skills) or "nenhuma")
        ctx = build_context_block(skills, self._memories(user_input), self.skill_chars,
                                  self._projects)
        first = f"{ctx}\n\n---\n\n{user_input}" if ctx else user_input

        messages: list[Message] = [Message("system", self._system), *self.history,
                                   Message("user", first)]

        for step in range(self.max_steps):
            turn.steps = step + 1
            try:
                reply = self._complete(messages)
            except EngineError as exc:
                turn.answer = f"ERRO de engine: {exc}"
                self._finish(user_input, turn, before, first)
                return turn

            calls = parse_tool_calls(reply)
            if not calls:
                turn.answer = reply.strip()
                break

            for c in calls:
                self.on_event("tool_call", f"{c.tool} {json.dumps(c.args, ensure_ascii=False)[:160]}")
            results = self.run_tools(calls)
            messages.append(Message("assistant", reply))
            for c, r in zip(calls, results):
                self.on_event("tool_result", r.render(300))
                turn.calls.append(c)
                turn.results.append(r)
                messages.append(Message("tool", r.render(self.tool_limit), name=c.tool))
        else:
            # Limite estourado: em vez de jogar fora o trabalho, pede o fechamento.
            self.on_event("retry", f"limite de {self.max_steps} passos; pedindo resposta final")
            messages.append(Message(
                "user",
                "Limite de passos atingido. Sem mais tools. Responda agora, em texto "
                "normal, com o que ja' foi apurado e diga explicitamente o que ficou em aberto."))
            try:
                turn.answer = self._complete(messages).strip()
            except EngineError as exc:
                turn.answer = f"(limite de {self.max_steps} passos atingido; engine falhou: {exc})"

        self._finish(user_input, turn, before, first)
        return turn

    def _finish(self, user_input: str, turn: Turn, before: Usage,
                sent: str | None = None) -> None:
        now = self.engine.usage
        turn.usage = Usage(
            input_tokens=now.input_tokens - before.input_tokens,
            output_tokens=now.output_tokens - before.output_tokens,
            cache_read=now.cache_read - before.cache_read,
            cache_write=now.cache_write - before.cache_write,
            cost_usd=round(now.cost_usd - before.cost_usd, 6),
        )
        # Engine com sessao propria compara o historico com o que ja' enviou.
        # Guardar o input cru aqui (e nao o texto com o bloco de contexto que
        # foi realmente enviado) fazia a pergunta antiga nao casar e ser
        # reenviada em todo turno seguinte.
        self.history.append(Message("user", sent if (sent and self.engine.stateful)
                                    else user_input))
        self.history.append(Message("assistant", turn.answer))
        self.history = self.history[-20:]
        self.store.log_turn(self.session_id, "assistant", turn.answer)

    def reset(self) -> None:
        self.history.clear()
        self.session_id = uuid.uuid4().hex[:12]
        self.engine.new_session()
