"""Engine que usa o binario local do Claude Code (`claude -p`).

Vantagem: funciona sem API key propria, reaproveitando o login existente.

Sessao persistente: a 1a chamada cria a sessao (`--session-id`), as seguintes
usam `--resume`. Assim o historico fica do lado do CLI e o ATOM manda so o
delta -- em vez de reserializar a conversa inteira a cada passo do ReAct.
Isso corta custo (prompt cache do lado do servidor) e latencia.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid

from atom.core.types import Message
from atom.engine.base import Engine, EngineError, EngineTransientError, Usage

# Erros que costumam passar numa segunda tentativa.
TRANSIENT_MARKS = (
    "overloaded", "rate limit", "429", "500", "502", "503", "504",
    "timeout", "timed out", "connection", "econnreset", "temporarily",
)


def _find_claude() -> str | None:
    for cand in ("claude", "claude.cmd", "claude.exe"):
        p = shutil.which(cand)
        if p:
            return p
    exec_path = os.environ.get("CLAUDE_CODE_EXECPATH")
    if exec_path and os.path.exists(exec_path):
        return exec_path
    return None


def _sig(m: Message) -> tuple:
    return (m.role, m.name or "", hash(m.content))


def _render(m: Message) -> str:
    if m.role == "tool":
        return f"<tool name=\"{m.name or ''}\">\n{m.content}\n</tool>"
    if m.role == "assistant":
        return f"<assistant>\n{m.content}\n</assistant>"
    return m.content


def _flatten(messages: list[Message]) -> str:
    if len(messages) == 1 and messages[0].role == "user":
        return messages[0].content
    return "\n\n".join(_render(m) for m in messages)


class ClaudeCliEngine(Engine):
    name = "claude_cli"
    stateful = True

    def __init__(self, *a, **kw) -> None:
        super().__init__(*a, **kw)
        self._sid: str | None = None
        self._system: str | None = None
        self._sent: list[tuple] = []

    def available(self) -> bool:
        return _find_claude() is not None

    def new_session(self) -> None:
        self._sid = None
        self._system = None
        self._sent = []

    # --- delta ---
    def _delta(self, rest: list[Message]) -> list[Message]:
        """Mensagens ainda nao enviadas, na ordem.

        A sessao do CLI e' um superconjunto do historico do agent (guarda ate
        os passos intermediarios de tool que o agent descarta). Por isso o
        casamento e' por avanco de ponteiro, nao por prefixo exato.
        """
        out: list[Message] = []
        i = 0
        for m in rest:
            s = _sig(m)
            found = -1
            for j in range(i, len(self._sent)):
                if self._sent[j] == s:
                    found = j
                    break
            if found >= 0:
                i = found + 1
            else:
                out.append(m)
        return out

    def _usage_from(self, data: dict) -> Usage:
        u = data.get("usage") or {}
        return Usage(
            input_tokens=int(u.get("input_tokens") or 0),
            output_tokens=int(u.get("output_tokens") or 0),
            cache_read=int(u.get("cache_read_input_tokens") or 0),
            cache_write=int(u.get("cache_creation_input_tokens") or 0),
            cost_usd=float(data.get("total_cost_usd") or 0.0),
        )

    def complete(self, messages: list[Message]) -> str:
        exe = _find_claude()
        if not exe:
            raise EngineError("binario `claude` nao encontrado no PATH")

        system = "\n\n".join(m.content for m in messages if m.role == "system")
        rest = [m for m in messages if m.role != "system"]

        # System prompt mudou => cache invalido, sessao nova.
        if self._system is not None and system != self._system:
            self.new_session()

        payload = self._delta(rest) if self._sid else rest
        if not payload:
            payload = rest[-1:] if rest else [Message("user", "continue")]

        # tools ""            => CLI vira LLM puro; quem executa tool e' o ATOM.
        # strict-mcp-config   => nao sobe servidor MCP nenhum. Sem isto o modelo
        #                        enxerga as tools MCP do usuario e acha que sao
        #                        as unicas que tem, ignorando as do ATOM.
        # setting-sources ""  => nao carrega CLAUDE.md/settings do usuario.
        #                        Medido: 16k tokens de cache por chamada, ~76x
        #                        no custo, tudo irrelevante para o ATOM.
        cmd = [exe, "-p", "--output-format", "json", "--tools", "",
               "--strict-mcp-config", "--setting-sources", ""]
        if self._sid:
            cmd += ["--resume", self._sid]
        else:
            cmd += ["--session-id", str(uuid.uuid4())]
            if system:
                cmd += ["--system-prompt", system]
        if self.model:
            cmd += ["--model", self.model]

        env = dict(os.environ)
        env.pop("CLAUDE_CODE_ENTRYPOINT", None)
        try:
            proc = subprocess.run(
                cmd,
                input=_flatten(payload),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise EngineTransientError(f"timeout apos {self.timeout}s") from exc

        if proc.returncode != 0:
            err = (proc.stderr or "falha no claude cli").strip()[:500]
            low = err.lower()
            if any(t in low for t in TRANSIENT_MARKS):
                raise EngineTransientError(err)
            raise EngineError(err)

        raw = (proc.stdout or "").strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Sem JSON valido nao da' pra confiar no session_id; trata como texto.
            self._system = system
            return raw

        if data.get("is_error"):
            raise EngineTransientError(str(data.get("result") or "erro no claude cli")[:500])

        text = str(data.get("result") or "").strip()
        sid = data.get("session_id")
        if sid:
            self._sid = str(sid)
        self._system = system
        self._sent.extend(_sig(m) for m in payload)
        self._sent.append(_sig(Message("assistant", text)))
        self._account(self._usage_from(data))
        return text
