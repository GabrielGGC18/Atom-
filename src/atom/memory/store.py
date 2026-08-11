"""Memoria persistente do ATOM em SQLite: fatos, tarefas, sessoes."""

from __future__ import annotations

import json
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
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or paths.db_file()
        self._init()

    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        cx = sqlite3.connect(self.path)
        cx.row_factory = sqlite3.Row
        try:
            yield cx
            cx.commit()
        finally:
            cx.close()

    def _init(self) -> None:
        with self.conn() as cx:
            cx.executescript(SCHEMA)

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
        like = f"%{query}%"
        with self.conn() as cx:
            if query:
                rows = cx.execute(
                    "SELECT * FROM facts WHERE key LIKE ? OR value LIKE ? OR tags LIKE ?"
                    " ORDER BY updated_at DESC LIMIT ?", (like, like, like, limit)).fetchall()
            else:
                rows = cx.execute(
                    "SELECT * FROM facts ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
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
