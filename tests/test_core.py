from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

import atom.tools  # noqa: F401  popula registry
from atom.agents.react import parse_tool_call
from atom.core.config import Config
from atom.core.registry import all_tools
from atom.memory.store import Store
from atom.tools.shell import is_dangerous


def test_tools_registered():
    tools = all_tools()
    for expected in ("shell", "read_file", "write_file", "sysinfo", "remember"):
        assert expected in tools


def test_parse_tool_call_block():
    txt = 'blabla\n```atom-tool\n{"tool": "sysinfo", "args": {}}\n```'
    call = parse_tool_call(txt)
    assert call and call.tool == "sysinfo" and call.args == {}


def test_parse_tool_call_inline_json():
    call = parse_tool_call('{"tool": "read_file", "args": {"path": "x.txt"}}')
    assert call and call.args["path"] == "x.txt"


def test_parse_tool_call_none():
    assert parse_tool_call("resposta final sem tool") is None


@pytest.mark.parametrize("cmd", ["rm -rf /", "git reset --hard HEAD~3",
                                  "git push origin main --force", "DROP TABLE users"])
def test_dangerous_detected(cmd):
    assert is_dangerous(cmd)


def test_safe_commands():
    assert is_dangerous("git status") is None
    assert is_dangerous("ls -la") is None


def test_config_get_set():
    cfg = Config()
    assert cfg.get("agent.max_steps") == 12
    cfg.set("engine.provider", "ollama")
    assert cfg.get("engine.provider") == "ollama"
    assert cfg.get("nao.existe", "fallback") == "fallback"


def test_store_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        st = Store(Path(d) / "t.db")
        st.remember("stack", "django")
        st.remember("stack", "django+react")   # upsert
        rows = st.recall("stack")
        assert len(rows) == 1 and rows[0]["value"] == "django+react"

        tid = st.task_add("fazer x", project="p")
        assert st.task_list()[0]["id"] == tid
        assert st.task_done(tid)
        assert st.task_list() == []
        assert st.stats()["facts"] == 1


def test_store_sessions():
    with tempfile.TemporaryDirectory() as d:
        st = Store(Path(d) / "t.db")
        st.log_turn("s1", "user", "oi")
        st.log_turn("s1", "assistant", "ATOM ativo")
        hist = st.history("s1")
        assert [h["role"] for h in hist] == ["user", "assistant"]


def test_file_tools_roundtrip():
    from atom.tools.files import list_dir, read_file, write_file
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "sub" / "a.txt"
        assert "OK" in write_file(str(f), "linha1\nlinha2\n")
        assert "linha2" in read_file(str(f))
        assert "a.txt" in list_dir(str(f.parent))


def test_skills_loader_on_vault():
    from atom.skills import load_all
    vault = Path(os.path.expanduser("~")) / "ATom-agent"
    if not vault.exists():
        pytest.skip("vault ausente")
    skills = load_all(str(vault))
    assert len(skills) > 5
    assert all(s.name and s.body for s in skills)
