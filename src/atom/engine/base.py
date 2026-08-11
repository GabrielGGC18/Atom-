"""Contrato de engine (backend de LLM)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from atom.core.types import Message


class EngineError(RuntimeError):
    pass


class Engine(ABC):
    name: str = "base"

    def __init__(self, model: str = "", temperature: float = 0.2,
                 timeout: int = 300, **kw) -> None:
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.options = kw

    @abstractmethod
    def available(self) -> bool:
        """Backend utilizavel neste host."""

    @abstractmethod
    def complete(self, messages: list[Message]) -> str:
        """Uma rodada de completion. Retorna texto do assistant."""

    def stream(self, messages: list[Message]) -> Iterable[str]:
        yield self.complete(messages)

    def describe(self) -> str:
        return f"{self.name}:{self.model or 'default'}"
