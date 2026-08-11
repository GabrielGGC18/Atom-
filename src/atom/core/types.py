"""Tipos base compartilhados."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class Message:
    role: Role
    content: str
    name: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name:
            d["name"] = self.name
        return d


@dataclass
class ToolCall:
    tool: str
    args: dict[str, Any]
    raw: str = ""


@dataclass
class ToolResult:
    tool: str
    ok: bool
    output: str
    error: str | None = None

    def render(self, limit: int = 4000) -> str:
        body = self.output if self.ok else f"ERRO: {self.error}"
        if len(body) > limit:
            body = body[:limit] + f"\n... [truncado, {len(body)} chars]"
        return body


@dataclass
class Tool:
    name: str
    description: str
    schema: dict[str, str]
    handler: Callable[..., str]
    dangerous: bool = False

    def spec(self) -> str:
        args = ", ".join(f"{k}: {v}" for k, v in self.schema.items())
        flag = " [PEDE CONFIRMACAO]" if self.dangerous else ""
        return f"- {self.name}({args}) -> {self.description}{flag}"


@dataclass
class Skill:
    name: str
    path: str
    domain: str
    description: str
    triggers: list[str] = field(default_factory=list)
    body: str = ""
