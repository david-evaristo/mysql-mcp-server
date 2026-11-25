# Plano de ação — Conexão MySQL controlada por variável

## Objetivo
Permitir que o servidor conecte ao MySQL de duas formas, escolhidas pela variável `MYSQL_CONNECTION_MODE`:

| Modo | Descrição |
|---|---|
| `teleport` (padrão) | Comportamento atual: túnel Teleport em loopback, sem senha (mTLS no proxy). |
| `direct` | Conexão direta ao host MySQL com usuário e senha, com SSL opcional. |

O padrão `teleport` mantém compatibilidade total com quem já usa o servidor.

## Variáveis de ambiente

| Variável | Modo | Obrigatória | Descrição |
|---|---|---|---|
| `MYSQL_CONNECTION_MODE` | ambos | não | `teleport` (padrão) ou `direct`. Outro valor gera erro. |
| `MYSQL_HOST` | ambos | sim | Em `teleport` deve ser loopback (aviso se não for). Em `direct` aceita qualquer host. |
| `MYSQL_PORT` | ambos | não | Padrão `54855` em `teleport`; sugerido `3306` em `direct`. |
| `MYSQL_USER` | ambos | sim | Usuário de conexão. |
| `MYSQL_PASSWORD` | direct | sim | Ignorada em `teleport`. Nunca registrada em log, auditoria ou `repr`. |
| `MYSQL_SSL_CA` | direct | não | Caminho do CA para TLS (recomendado). |

## Fases

### Fase 1 — Configuração (`src/config.py`)
- [ ] Adicionar ao `DatabaseConfig` os campos `mode`, `password` e `ssl_ca`.
- [ ] Manter o `__repr__` sem expor a senha.
- [ ] Em `from_env()`, ler e validar `MYSQL_CONNECTION_MODE`, com erro claro para valor inválido.
- [ ] `teleport`: comportamento atual, incluindo o aviso de host não loopback.
- [ ] `direct`: exigir `MYSQL_PASSWORD`, sem aviso de loopback, validar que `MYSQL_SSL_CA` existe quando informado.
- [ ] Alinhar o padrão de `MCP_POOL_MIN` (código usa 2, `.env.example` usa 1).

### Fase 2 — Pool de conexões (`src/db/lifespan.py`)
- [ ] Montar os `kwargs` do `aiomysql.create_pool` conforme o modo.
- [ ] Em `direct`: passar `password` e, se houver `ssl_ca`, `ssl=ssl.create_default_context(cafile=...)`.
- [ ] Manter `init_command="SET SESSION TRANSACTION READ ONLY"` nos dois modos.
- [ ] Trocar o log fixo "teleport-proxy" por `mode=<modo>`.

### Fase 3 — Textos e demais módulos
- [ ] `src/initialization.py`: escolher as `instructions` do MCP conforme o modo. O aviso sobre `tsh` só em `teleport`.
- [ ] `src/db/repository.py`: revisar os comentários sobre Teleport. Decidir se a conexão única em `describe_table` vale para os dois modos.
- [ ] `src/audit.py`: usar o config em vez de `os.getenv("MYSQL_USER")`.

### Fase 4 — Testes
`tests/test_config.py`:
- [ ] Modo padrão é `teleport`.
- [ ] Modo inválido levanta `ValueError`.
- [ ] `direct` sem senha levanta `ValueError`.
- [ ] `direct` com host remoto não emite warning.
- [ ] `teleport` com host remoto continua emitindo warning.
- [ ] A senha não aparece no `repr`.

`tests/test_lifespan.py`:
- [ ] `create_pool` recebe `password` e `ssl` apenas em `direct`.
- [ ] `init_command` read-only presente nos dois modos.

Rodar a suíte unitária (`pytest --ignore=tests/integration`), `ruff`, `mypy` e `bandit`.

### Fase 5 — Documentação
- [ ] `.env.example`: novas variáveis, com exemplos dos dois modos.
- [ ] `README.md`: seção "Modos de conexão" e exemplos de configuração.
- [ ] `CLAUDE.md`: tabela de variáveis.
- [ ] `claude_desktop_config.example.json`: exemplo para `direct`.
- [ ] Nota de segurança no README: usuário MySQL com apenas `SELECT`.

### Fase 6 — Publicação e repositório
- [ ] Corrigir `<owner>/<repo>` e `<tag>` nos exemplos (se ainda pendente).
- [ ] Adicionar `LICENSE` (sugestão: MIT) e o campo `license` no `pyproject.toml`.
- [ ] CI no GitHub Actions: `ruff`, `mypy`, `pytest` (sem integração) e `bandit`.
- [ ] Ativar Dependabot e secret scanning.
- [ ] Subir a versão para `1.1.0` e criar a tag `v1.1.0`.

## Riscos e decisões

| Item | Decisão / mitigação |
|---|---|
| Vazamento de senha | Só via variável de ambiente ou secret manager. Nunca em log, auditoria ou `repr`. |
| Segurança em `direct` | O usuário MySQL deve ter só `SELECT`. `READ ONLY` e `query_guard` são defesa adicional. |
| Compatibilidade | Padrão `teleport` preserva o comportamento atual. |
| Testes de integração | Exigem banco real. Ficam fora da CI. |
| Banco padrão | Opcional: aceitar `MYSQL_DATABASE` no modo `direct`. Decidir antes da Fase 2. |

## Critérios de aceite
- Sem `MYSQL_CONNECTION_MODE`, tudo funciona como hoje.
- Com `direct`, conecta usando usuário, senha e SSL, e continua somente leitura.
- Testes unitários, lint e tipos passam.
- A documentação descreve os dois modos.
