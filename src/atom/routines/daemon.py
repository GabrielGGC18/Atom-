"""Agendador de rotinas do ATOM.

Stdlib pura -- nao vale puxar APScheduler/celery para meia duzia de jobs
locais. Persistencia da ultima execucao fica no SQLite, entao reiniciar a
maquina nao faz a rotina rodar duas vezes nem perder a janela.

Formatos de schedule:
    30s 10m 2h 1d       intervalo desde a ultima execucao
    daily@07:30         uma vez por dia, a partir do horario
    hourly@:15          uma vez por hora, a partir do minuto 15

Acoes:
    digest              gera o briefing
    ask:<prompt>        manda o prompt para o agent (usa engine)
    shell:<comando>     roda comando no shell
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from atom.core.config import Config
from atom.memory.store import get_store

TICK = 20  # segundos entre verificacoes
UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
INTERVAL_RE = re.compile(r"^(\d+)\s*([smhd])$", re.I)
DAILY_RE = re.compile(r"^daily@(\d{1,2}):(\d{2})$", re.I)
HOURLY_RE = re.compile(r"^hourly@:(\d{1,2})$", re.I)


class ScheduleError(ValueError):
    pass


@dataclass
class Routine:
    name: str
    schedule: str
    action: str
    enabled: bool = True

    @classmethod
    def from_dict(cls, d: dict) -> "Routine":
        if not d.get("name") or not d.get("schedule") or not d.get("action"):
            raise ScheduleError(f"rotina incompleta: {d}")
        return cls(name=str(d["name"]), schedule=str(d["schedule"]),
                   action=str(d["action"]), enabled=bool(d.get("enabled", True)))


def parse_last(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def due(routine: Routine, last: datetime | None, now: datetime | None = None) -> bool:
    """Rotina deve rodar agora?"""
    now = now or datetime.now()
    sched = routine.schedule.strip()

    m = INTERVAL_RE.match(sched)
    if m:
        secs = int(m.group(1)) * UNITS[m.group(2).lower()]
        return last is None or (now - last).total_seconds() >= secs

    m = DAILY_RE.match(sched)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if now < target:
            return False
        # Ja passou do horario hoje: roda se ainda nao rodou depois dele.
        return last is None or last < target

    m = HOURLY_RE.match(sched)
    if m:
        mm = int(m.group(1))
        target = now.replace(minute=mm, second=0, microsecond=0)
        if now < target:
            target -= timedelta(hours=1)
        return last is None or last < target

    raise ScheduleError(f"schedule invalido: '{sched}' (use 10m, 2h, daily@07:30, hourly@:15)")


def load_routines(cfg: Config | None = None) -> list[Routine]:
    cfg = cfg or Config.load()
    return [Routine.from_dict(d) for d in (cfg.get("routines.items") or [])]


# --- execucao ---

def run_action(action: str, cfg: Config) -> str:
    if action.strip() == "digest":
        from atom.routines.digest import collect, to_text
        return to_text(collect(cfg))

    if action.startswith("shell:"):
        from atom.tools.shell import shell
        return shell(action[len("shell:"):].strip())

    if action.startswith("ask:"):
        from atom.agents import AtomAgent
        agent = AtomAgent(cfg=cfg)
        return agent.run(action[len("ask:"):].strip()).answer

    raise ScheduleError(f"acao desconhecida: '{action}' (use digest, ask:..., shell:...)")


def run_one(routine: Routine, cfg: Config,
            on_event: Callable[[str, str], None] | None = None) -> tuple[bool, str]:
    emit = on_event or (lambda k, p: None)
    store = get_store()
    t0 = time.time()
    emit("start", routine.name)
    try:
        out = run_action(routine.action, cfg)
        ok = True
    except Exception as exc:  # noqa: BLE001  rotina quebrada nao derruba o daemon
        out = f"{type(exc).__name__}: {exc}"
        ok = False
    ms = int((time.time() - t0) * 1000)
    store.routine_log(routine.name, "ok" if ok else "erro", out, ms)
    emit("done" if ok else "fail", f"{routine.name} ({ms}ms)")
    return ok, out


def run_due(cfg: Config | None = None, force: bool = False,
            on_event: Callable[[str, str], None] | None = None) -> list[str]:
    """Roda o que estiver vencido. Devolve os nomes executados."""
    cfg = cfg or Config.load()
    store = get_store()
    ran: list[str] = []
    for r in load_routines(cfg):
        if not r.enabled:
            continue
        last_row = store.routine_last(r.name)
        last = parse_last(last_row.get("started_at") if last_row else None)
        try:
            should = force or due(r, last)
        except ScheduleError as exc:
            (on_event or (lambda k, p: None))("fail", f"{r.name}: {exc}")
            continue
        if should:
            run_one(r, cfg, on_event)
            ran.append(r.name)
    return ran


def serve(cfg: Config | None = None, tick: int = TICK,
          on_event: Callable[[str, str], None] | None = None,
          max_ticks: int = 0) -> None:
    """Laco do daemon. `max_ticks` > 0 limita as voltas (usado em teste)."""
    # cfg explicito manda; sem ele, recarrega do disco a cada volta para que
    # editar rotina nao exija restart do daemon.
    reload_each_cycle = cfg is None
    cfg = cfg or Config.load()
    emit = on_event or (lambda k, p: None)
    routines = load_routines(cfg)
    emit("boot", f"{len(routines)} rotina(s), tick {tick}s")
    n = 0
    while True:
        try:
            run_due(Config.load() if reload_each_cycle else cfg, on_event=on_event)
        except Exception as exc:  # noqa: BLE001
            emit("fail", f"ciclo falhou: {exc}")
        n += 1
        if max_ticks and n >= max_ticks:
            return
        time.sleep(tick)
