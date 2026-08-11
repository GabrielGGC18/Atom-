# ATOM

Assistente pessoal **local-first** do Mestre Gabriel.
Nome em homenagem ao robô **Atom** (*Gigantes de Aço*) e aos agents do vault.

Arquitetura inspirada no [OpenJarvis](https://github.com/open-jarvis/OpenJarvis) (Stanford),
reescrita enxuta: sem cloud obrigatória, sem 2000 arquivos, sem Rust/Electron.

```
Mestre -> CLI -> AtomAgent (ReAct loop) -> Engine (Ollama | OpenAI-compat | Claude CLI)
                        |
                        +-- Tools    (shell, arquivos, http, vault, tarefas, sistema)
                        +-- Skills   (markdown do vault ~/ATom-agent)
                        +-- Memória  (SQLite ~/.atom/atom.db)
```

## Instalação

```bash
cd ~/atom
uv venv
uv pip install -e .
```

Rodar sem ativar venv: `uv run atom ...`

## Uso

```bash
atom                      # chat interativo (default)
atom ask "o que mudou no repo hoje?"
atom doctor               # diagnóstico: engines, tools, skills, paths
atom tools                # lista ferramentas
atom skill list           # skills carregadas do vault
atom skill show backend_django_drf
atom skill route "erro no docker do SEI"   # mostra roteamento
atom mem add stack "Django + React + Render"
atom mem list
atom task add "revisar PR do portal" -p sei
atom task list
atom config set engine.provider ollama
```

No chat: `/sair` `/reset` `/tools` `/skills` `/mem`.

## Engines

Seleção `auto`, ordem local-first:

| Provider | Quando usa | Requisito |
|---|---|---|
| `ollama` | preferido, 100% local | Ollama rodando em :11434 |
| `claude_cli` | fallback sem API key | binário `claude` no PATH |
| `openai_compat` | OpenAI, Groq, OpenRouter, LM Studio, vLLM | `OPENAI_API_KEY` ou base_url local |

Forçar: `atom config set engine.provider ollama` + `atom config set engine.model qwen2.5:7b-instruct`.

## Tools

| Grupo | Tools |
|---|---|
| shell | `shell` (padrões destrutivos bloqueados) |
| arquivos | `read_file`, `write_file`, `list_dir`, `grep` |
| web | `http_get`, `http_post` |
| vault | `note_search`, `note_read`, `note_write`, `journal` |
| memória | `remember`, `recall`, `forget` |
| tarefas | `task_add`, `task_list`, `task_done` |
| sistema | `sysinfo`, `git_status`, `open_path` |

Comandos destrutivos (`rm -rf`, `git reset --hard`, `git push --force`, `drop table`, …)
são **bloqueados** salvo `ATOM_ALLOW_DANGEROUS=1`.

## Skills

Lidas direto do vault Obsidian (`~/ATom-agent`, override por `ATOM_VAULT`):

- `Agents/Skills/*.md` — GSM, Django/DRF, React, deploy Render, API
- `Agents/SEI/Skills/*/SKILL.md` — portal-sei, docker, PHP legado, CSS
- `Agents/Java/Skills/*.md` — POO, mentor

Roteamento por score de triggers/descrição. Skill escolhida entra no system prompt.

## Config

`~/.atom/config.yaml` (crie com `atom config init`). Env overrides:
`ATOM_HOME`, `ATOM_VAULT`, `ATOM_PROVIDER`, `ATOM_MODEL`, `ATOM_BASE_URL`, `ATOM_MAX_STEPS`.

## Layout

```
src/atom/
  core/      config, paths, registry, types
  engine/    base, ollama, openai_compat, claude_cli
  agents/    persona, react (loop)
  tools/     shell, files, web, vault, brain, system
  skills/    loader do vault
  memory/    store SQLite
  cli/       main (typer), banner
```

## Roadmap

- [ ] `atom digest` — briefing diário (agenda, git, tarefas)
- [ ] `atom daemon` — agendador de rotinas
- [ ] voz (STT/TTS local)
- [ ] MCP client
