"""Contrato de engine (backend de LLM)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable

from atom.core.types import Message


class EngineError(RuntimeError):
    pass


class EngineTransientError(EngineError):
    """Falha provavelmente temporaria (rede, rate limit). Vale retentar."""


@dataclass
class Usage:
    """Contabilidade de tokens/custo. Zero quando o backend nao reporta."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0
    cost_usd: float = 0.0

    def add(self, other: "Usage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read += other.cache_read
        self.cache_write += other.cache_write
        self.cost_usd += other.cost_usd

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_read + self.cache_write


class Engine(ABC):
    name: str = "base"
    # True = o backend guarda o historico do lado dele; o agent manda so o delta.
    stateful: bool = False

    def __init__(self, model: str = "", temperature: float = 0.2,
                 timeout: int = 300, **kw) -> None:
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.options = kw
        self.usage = Usage()       # acumulado desde o boot
        self.last_usage = Usage()  # ultima chamada

    @abstractmethod
    def available(self) -> bool:
        """Backend utilizavel neste host."""

    @abstractmethod
    def complete(self, messages: list[Message]) -> str:
        """Uma rodada de completion. Retorna texto do assistant."""

    def stream(self, messages: list[Message]) -> Iterable[str]:
        yield self.complete(messages)

    def new_session(self) -> None:
        """Descarta estado do lado do backend. No-op se stateless."""

    def _account(self, u: Usage) -> None:
        self.last_usage = u
        self.usage.add(u)

    def describe(self) -> str:
        return f"{self.name}:{self.model or 'default'}"
