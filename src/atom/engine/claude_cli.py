"""Engine que usa o binario local do Claude Code (`claude -p`).

Vantagem: funciona sem API key propria, reaproveitando o login existente.
Modo headless, uma pergunta por chamada; historico e' serializado no prompt.
"""

from __future__ import annotations

import os
import shutil
import subprocess

from atom.core.types import Message
from atom.engine.base import Engine, EngineError


def _find_claude() -> str | None:
    for cand in ("claude", "claude.cmd", "claude.exe"):
        p = shutil.which(cand)
        if p:
            return p
    exec_path = os.environ.get("CLAUDE_CODE_EXECPATH")
    if exec_path and os.path.exists(exec_path):
        return exec_path
    return None


def _split_system(messages: list[Message]) -> tuple[str, list[Message]]:
    sys_parts = [m.content for m in messages if m.role == "system"]
    rest = [m for m in messages if m.role != "system"]
    return "\n\n".join(sys_parts), rest


def _flatten(messages: list[Message]) -> str:
    parts: list[str] = []
    for m in messages:
        if m.role == "system":
            parts.append(f"<system>\n{m.content}\n</system>")
        elif m.role == "user":
            parts.append(f"<user>\n{m.content}\n</user>")
        elif m.role == "assistant":
            parts.append(f"<assistant>\n{m.content}\n</assistant>")
        else:
            parts.append(f"<tool name=\"{m.name or ''}\">\n{m.content}\n</tool>")
    parts.append("<assistant>")
    return "\n\n".join(parts)


class ClaudeCliEngine(Engine):
    name = "claude_cli"

    def available(self) -> bool:
        return _find_claude() is not None

    def complete(self, messages: list[Message]) -> str:
        exe = _find_claude()
        if not exe:
            raise EngineError("binario `claude` nao encontrado no PATH")
        # tools "" => CLI vira LLM puro; quem executa ferramenta e' o ATOM.
        # System prompt vai no stdin: Windows limita linha de comando a ~8KB.
        cmd = [exe, "-p", "--output-format", "text", "--tools", ""]
        if self.model:
            cmd += ["--model", self.model]
        env = dict(os.environ)
        env.pop("CLAUDE_CODE_ENTRYPOINT", None)
        try:
            proc = subprocess.run(
                cmd,
                input=_flatten(messages),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise EngineError(f"timeout apos {self.timeout}s") from exc
        if proc.returncode != 0:
            raise EngineError((proc.stderr or "falha no claude cli").strip()[:500])
        return (proc.stdout or "").strip()
