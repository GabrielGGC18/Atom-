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
atom skill route "erro no build do docker"  # mostra roteamento
atom mem add stack "Django + React + Render"
atom mem list
atom task add "revisar PR do portal" -p web
atom task list
atom config set engine.provider ollama

atom digest               # briefing: repos git, tarefas, memoria (custo zero)
atom digest --llm         # + leitura em linguagem natural (gasta token)
atom digest --save        # grava no Journal do vault
atom daemon               # agendador de rotinas (Ctrl+C para parar)
atom daemon --once        # roda o que estiver vencido e sai
atom routines             # lista rotinas e ultima execucao
```

No chat: `/clear` `/cost` `/model <nome>` `/tools` `/skills` `/mem` `/help` `/sair`.

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
| skills | `skill_list`, `skill_read` (conteudo completo sob demanda) |
| memória | `remember`, `recall`, `forget` |
| tarefas | `task_add`, `task_list`, `task_done` |
| sistema | `sysinfo`, `git_status`, `open_path` |

Comandos destrutivos (`rm -rf`, `git reset --hard`, `git push --force`, `drop table`, …)
são **bloqueados** salvo `ATOM_ALLOW_DANGEROUS=1`.

## Skills

Lidas direto do vault Obsidian (`~/ATom-agent`, override por `ATOM_VAULT`):

- `Agents/Skills/*.md` — GSM, Django/DRF, React, deploy Render, API
- `Agents/<Dominio>/Skills/*/SKILL.md` — skills agrupadas por dominio
- `Agents/Java/Skills/*.md` — POO, mentor

Roteamento por score de triggers/descrição. Skill escolhida entra no system prompt.
Só o topo dela (2500 chars) vai no prompt; o resto sai por `skill_read`.

Para esconder skills do `skill list` e do roteamento, use o config local
(nomes de projeto privado não vão para o repo):

```yaml
vault:
  hidden_skills: [nome-da-skill, outra-skill]
  domains: [java, infra]     # pastas do vault que viram dominio
```

Alternativa por arquivo: `hidden: true` no frontmatter da skill.
`ATOM_SHOW_HIDDEN=1` mostra tudo de novo.

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

## Rotinas

`routines.items` no config. Schedule: `10m`, `2h`, `daily@07:30`, `hourly@:15`.
Acao: `digest`, `ask:<prompt>`, `shell:<comando>`.

```yaml
routines:
  items:
    - {name: briefing, schedule: "daily@08:00", action: digest, enabled: true}
    - {name: disco, schedule: "6h", action: "shell:df -h /", enabled: true}
```

Ultima execucao fica no SQLite: reiniciar a maquina nao duplica nem perde a
janela. Rotina que quebra e' registrada como `erro` e nao derruba o daemon.

## Custo

O `claude_cli` mantem UMA sessao por conversa (`--session-id` + `--resume`):
so' o delta e' enviado a cada passo do ReAct, o resto fica no cache do
servidor. Roda tambem com `--strict-mcp-config --setting-sources ""`, senao o
CLI carrega o `CLAUDE.md` e as tools MCP do usuario em toda chamada (medido:
~16k tokens de cache e ~76x no custo, tudo irrelevante para o ATOM).

`atom ask --cost` e `/cost` no chat mostram tokens e custo.

## Roadmap

- [x] `atom digest` — briefing diário (git, tarefas, memória)
- [x] `atom daemon` — agendador de rotinas
- [ ] voz (STT/TTS local)
- [ ] MCP client
