"""Registro de tools."""

from __future__ import annotations

from typing import Callable

from atom.core.types import Tool

_TOOLS: dict[str, Tool] = {}


def register(name: str, description: str, schema: dict[str, str],
             dangerous: bool = False,
             risk: Callable[[dict], bool] | None = None) -> Callable:
    def deco(fn: Callable[..., str]) -> Callable[..., str]:
        _TOOLS[name] = Tool(name=name, description=description, schema=schema,
                            handler=fn, dangerous=dangerous, risk=risk)
        return fn
    return deco


def all_tools() -> dict[str, Tool]:
    return dict(_TOOLS)


def get(name: str) -> Tool | None:
    return _TOOLS.get(name)


def enabled_tools(names: list[str] | None) -> dict[str, Tool]:
    if not names:
        return all_tools()
    return {n: t for n, t in _TOOLS.items() if n in names}
