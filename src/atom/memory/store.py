"""Memoria persistente do ATOM em SQLite: fatos, tarefas, sessoes."""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from atom.core import paths

SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    tags TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facts_key ON facts(key);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    project TEXT DEFAULT '',
    due TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    done_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_sid ON sessions(session_id);

CREATE TABLE IF NOT EXISTS routine_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    output TEXT DEFAULT '',
    started_at TEXT NOT NULL,
    duration_ms INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_routine_name ON routine_runs(name, started_at);
"""

# Busca por relevancia. O LIKE %x% anterior nao rankeava e nao casava termo
# no meio de palavra composta; FTS5 com bm25 resolve os dois.
FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
    key, value, tags, content='facts', content_rowid='id', tokenize='unicode61'
);
CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
    INSERT INTO facts_fts(rowid, key, value, tags) VALUES (new.id, new.key, new.value, new.tags);
END;
CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, key, value, tags)
    VALUES('delete', old.id, old.key, old.value, old.tags);
END;
CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, key, value, tags)
    VALUES('delete', old.id, old.key, old.value, old.tags);
    INSERT INTO facts_fts(rowid, key, value, tags) VALUES (new.id, new.key, new.value, new.tags);
END;
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _fts_query(query: str) -> str:
    """Frase do usuario -> OR de prefixos. Aspas fora para nao virar sintaxe FTS."""
    words = [w for w in re.split(r"\W+", query.lower()) if len(w) > 2]
    return " OR ".join(f'"{w}"*' for w in words[:12])


class Store:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or paths.db_file()
        self._cx: sqlite3.Connection | None = None
        self.fts = False
        self._init()

    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        # Conexao unica reaproveitada: no loop de tools o open/close por
        # operacao aparecia no perfil. WAL evita lock em leitura concorrente.
        if self._cx is None:
            self._cx = sqlite3.connect(self.path, check_same_thread=False)
            self._cx.row_factory = sqlite3.Row
            try:
                self._cx.execute("PRAGMA journal_mode=WAL")
                self._cx.execute("PRAGMA synchronous=NORMAL")
            except sqlite3.DatabaseError:
                pass
        try:
            yield self._cx
            self._cx.commit()
        except Exception:
            self._cx.rollback()
            raise

    def close(self) -> None:
        """Fecha a conexao. Idempotente.

        Sem isto o arquivo fica aberto ate' o GC: no Windows o SO nao deixa
        apagar/mover .db (nem os -wal/-shm), e teste com diretorio temporario
        quebra com WinError 32.
        """
        if self._cx is None:
            return
        try:
            self._cx.execute("PRAGMA optimize")
            self._cx.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.DatabaseError:
            pass
        try:
            self._cx.close()
        finally:
            self._cx = None

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def _init(self) -> None:
        with self.conn() as cx:
            cx.executescript(SCHEMA)
        try:
            with self.conn() as cx:
                cx.executescript(FTS)
                # Banco que ja existia antes do FTS entra vazio; popula uma vez.
                n = cx.execute("SELECT COUNT(*) c FROM facts_fts").fetchone()["c"]
                total = cx.execute("SELECT COUNT(*) c FROM facts").fetchone()["c"]
                if n == 0 and total > 0:
                    cx.execute("INSERT INTO facts_fts(rowid, key, value, tags)"
                               " SELECT id, key, value, tags FROM facts")
            self.fts = True
        except sqlite3.DatabaseError:
            self.fts = False  # SQLite sem FTS5: cai no LIKE

    # --- fatos ---
    def remember(self, key: str, value: str, tags: str = "") -> int:
        with self.conn() as cx:
            row = cx.execute("SELECT id FROM facts WHERE key = ?", (key,)).fetchone()
            if row:
                cx.execute("UPDATE facts SET value=?, tags=?, updated_at=? WHERE id=?",
                           (value, tags, _now(), row["id"]))
                return int(row["id"])
            cur = cx.execute(
                "INSERT INTO facts(key, value, tags, created_at, updated_at) VALUES (?,?,?,?,?)",
                (key, value, tags, _now(), _now()))
            return int(cur.lastrowid)

    def recall(self, query: str = "", limit: int = 20) -> list[dict[str, Any]]:
        if not query:
            with self.conn() as cx:
                rows = cx.execute(
                    "SELECT * FROM facts ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]
        if self.fts:
            match = _fts_query(query)
            if match:
                try:
                    with self.conn() as cx:
                        rows = cx.execute(
                            "SELECT f.* FROM facts_fts s JOIN facts f ON f.id = s.rowid"
                            " WHERE facts_fts MATCH ? ORDER BY bm25(facts_fts) LIMIT ?",
                            (match, limit)).fetchall()
                    if rows:
                        return [dict(r) for r in rows]
                except sqlite3.DatabaseError:
                    pass
        like = f"%{query}%"
        with self.conn() as cx:
            rows = cx.execute(
                "SELECT * FROM facts WHERE key LIKE ? OR value LIKE ? OR tags LIKE ?"
                " ORDER BY updated_at DESC LIMIT ?", (like, like, like, limit)).fetchall()
        return [dict(r) for r in rows]

    def forget(self, key: str) -> int:
        with self.conn() as cx:
            cur = cx.execute("DELETE FROM facts WHERE key = ?", (key,))
            return cur.rowcount

    # --- tarefas ---
    def task_add(self, title: str, project: str = "", due: str = "") -> int:
        with self.conn() as cx:
            cur = cx.execute(
                "INSERT INTO tasks(title, project, due, created_at) VALUES (?,?,?,?)",
                (title, project, due, _now()))
            return int(cur.lastrowid)

    def task_list(self, status: str = "pending") -> list[dict[str, Any]]:
        with self.conn() as cx:
            if status == "all":
                rows = cx.execute("SELECT * FROM tasks ORDER BY id DESC LIMIT 100").fetchall()
            else:
                rows = cx.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY id DESC LIMIT 100",
                    (status,)).fetchall()
        return [dict(r) for r in rows]

    def task_done(self, task_id: int) -> bool:
        with self.conn() as cx:
            cur = cx.execute("UPDATE tasks SET status='done', done_at=? WHERE id=?",
                             (_now(), task_id))
            return cur.rowcount > 0

    # --- sessoes ---
    def log_turn(self, session_id: str, role: str, content: str) -> None:
        with self.conn() as cx:
            cx.execute(
                "INSERT INTO sessions(session_id, role, content, created_at) VALUES (?,?,?,?)",
                (session_id, role, content, _now()))

    def history(self, session_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self.conn() as cx:
            rows = cx.execute(
                "SELECT role, content, created_at FROM sessions WHERE session_id=?"
                " ORDER BY id DESC LIMIT ?", (session_id, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]

    def sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.conn() as cx:
            rows = cx.execute(
                "SELECT session_id, COUNT(*) n, MAX(created_at) last FROM sessions"
                " GROUP BY session_id ORDER BY last DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # --- rotinas ---
    def routine_log(self, name: str, status: str, output: str = "",
                    duration_ms: int = 0) -> None:
        with self.conn() as cx:
            cx.execute(
                "INSERT INTO routine_runs(name, status, output, started_at, duration_ms)"
                " VALUES (?,?,?,?,?)", (name, status, output[:4000], _now(), duration_ms))

    def routine_last(self, name: str) -> dict[str, Any] | None:
        with self.conn() as cx:
            row = cx.execute(
                "SELECT * FROM routine_runs WHERE name=? ORDER BY id DESC LIMIT 1",
                (name,)).fetchone()
        return dict(row) if row else None

    def routine_history(self, limit: int = 30) -> list[dict[str, Any]]:
        with self.conn() as cx:
            rows = cx.execute(
                "SELECT * FROM routine_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict[str, int]:
        with self.conn() as cx:
            f = cx.execute("SELECT COUNT(*) c FROM facts").fetchone()["c"]
            t = cx.execute("SELECT COUNT(*) c FROM tasks WHERE status='pending'").fetchone()["c"]
            s = cx.execute("SELECT COUNT(DISTINCT session_id) c FROM sessions").fetchone()["c"]
        return {"facts": f, "pending_tasks": t, "sessions": s}

    def export(self) -> str:
        return json.dumps({"facts": self.recall(limit=1000),
                           "tasks": self.task_list("all")}, ensure_ascii=False, indent=2)


_store: Store | None = None


def get_store() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store
