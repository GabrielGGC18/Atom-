"""Isolamento dos testes em relacao a instalacao real do Mestre.

Sem isto `Config.load()` le' ~/.atom/config.yaml e o resultado do teste depende
da maquina: na VPS o `tools.enabled` nao lista `write_file` (foi enxugado no
deploy), entao test_dangerous_tool_needs_confirmation falhava la' e passava no
Windows. Teste tem que valer nas duas.

Efeito colateral bom: `atom.db` real nao e' mais tocado pelos testes.
"""

from __future__ import annotations

import pytest

ENV_OVERRIDES = ("ATOM_PROVIDER", "ATOM_MODEL", "ATOM_BASE_URL",
                 "ATOM_MAX_STEPS", "ATOM_TIMEOUT", "ATOM_ALLOW_DANGEROUS",
                 "ATOM_SHOW_HIDDEN")


@pytest.fixture(autouse=True)
def atom_home_isolado(tmp_path, monkeypatch):
    """Aponta ~/.atom para um diretorio descartavel e limpa overrides de env."""
    monkeypatch.setenv("ATOM_HOME", str(tmp_path / "atom-home"))
    for var in ENV_OVERRIDES:
        monkeypatch.delenv(var, raising=False)
    yield
