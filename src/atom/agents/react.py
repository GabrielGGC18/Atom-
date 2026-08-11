"""Agent loop ReAct do ATOM: pensa -> chama tool -> observa -> responde."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Callable

from atom.agents.persona import build_system_prompt
from atom.core.config import Config
from atom.core.registry import enabled_tools
from atom.core.types import Message, ToolCall, ToolResult
from atom.engine import Engine, EngineError, build as build_engine
from atom.memory.store import get_store
from atom.skills import route as route_skills

TOOL_BLOCK = re.compile(r"```atom-tool\s*(.+?)```", re.S)
JSON_FALLBACK = re.compile(r'\{\s*"tool"\s*:\s*".+?"\s*,\s*"args"\s*:\s*\{.*?\}\s*\}', re.S)


def parse_tool_call(text: str) -> ToolCall | None:
    m = TOOL_BLOCK.search(text) or JSON_FALLBACK.search(text)
    if not m:
        return None
    raw = m.group(1) if m.re is TOOL_BLOCK else m.group(0)
    try:
        data = json.loads(raw.strip())
    except json.JSONDecodeError:
        return None
    name = data.get("tool")
    if not name:
        return None
    args = data.get("args") or {}
    if not isinstance(args, dict):
        return None
    return ToolCall(tool=str(name), args=args, raw=raw.strip())


@dataclass
class Turn:
    calls: list[ToolCall] = field(default_factory=list)
    results: list[ToolResult] = field(default_factory=list)
    answer: str = ""


class AtomAgent:
    def __init__(self, cfg: Config | None = None, engine: Engine | None = None,
                 session_id: str | None = None,
                 on_event: Callable[[str, str], None] | None = None) -> None:
        self.cfg = cfg or Config.load()
        self.engine = engine or build_engine(self.cfg)
        self.session_id = session_id or uuid.uuid4().hex[:12]
        self.on_event = on_event or (lambda kind, payload: None)
        self.tools = enabled_tools(self.cfg.get("tools.enabled"))
        self.max_steps = int(self.cfg.get("agent.max_steps", 12))
        self.history: list[Message] = []
        self.store = get_store()

    # --- contexto ---
    def _memories(self, query: str) -> list[str]:
        if not self.cfg.get("memory.enabled", True):
            return []
        rows = self.store.recall(query, int(self.cfg.get("memory.max_recall", 8)))
        if not rows:
            rows = self.store.recall("", 5)
        return [f"{r['key']}: {r['value']}" for r in rows]

    def _system(self, query: str) -> Message:
        skills = route_skills(query)
        self.on_event("skills", ", ".join(s.name for s in skills) or "nenhuma")
        prompt = build_system_prompt(
            self.tools, skills, self._memories(query),
            caveman=bool(self.cfg.get("agent.caveman", False)),
        )
        return Message(role="system", content=prompt)

    # --- execucao de tool ---
    def run_tool(self, call: ToolCall) -> ToolResult:
        tool = self.tools.get(call.tool)
        if not tool:
            return ToolResult(call.tool, False, "", f"tool '{call.tool}' nao existe ou desativada")
        try:
            out = tool.handler(**call.args)
        except TypeError as exc:
            return ToolResult(call.tool, False, "", f"args invalidos: {exc}")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(call.tool, False, "", f"{type(exc).__name__}: {exc}")
        return ToolResult(call.tool, True, str(out))

    # --- loop principal ---
    def run(self, user_input: str) -> Turn:
        turn = Turn()
        self.store.log_turn(self.session_id, "user", user_input)
        messages: list[Message] = [self._system(user_input), *self.history,
                                   Message("user", user_input)]

        for step in range(self.max_steps):
            try:
                reply = self.engine.complete(messages)
            except EngineError as exc:
                turn.answer = f"ERRO de engine: {exc}"
                return turn
            call = parse_tool_call(reply)
            if not call:
                turn.answer = reply.strip()
                break
            self.on_event("tool_call", f"{call.tool} {json.dumps(call.args, ensure_ascii=False)[:160]}")
            result = self.run_tool(call)
            self.on_event("tool_result", result.render(500))
            turn.calls.append(call)
            turn.results.append(result)
            messages.append(Message("assistant", reply))
            messages.append(Message("tool", result.render(), name=call.tool))
        else:
            turn.answer = f"(limite de {self.max_steps} passos atingido sem resposta final)"

        self.history.append(Message("user", user_input))
        self.history.append(Message("assistant", turn.answer))
        self.history = self.history[-20:]
        self.store.log_turn(self.session_id, "assistant", turn.answer)
        return turn

    def reset(self) -> None:
        self.history.clear()
        self.session_id = uuid.uuid4().hex[:12]
