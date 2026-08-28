# Diretrizes do Projeto Gris

## Visão Geral

App Frappe (v15) para gestão complementar de Grupos Escoteiros.
Módulos: **Gris**, **Financeiro**, **Gestão de Adultos**.
Linguagem de comunicação e documentação: **Português (PT-BR)**.

## Estrutura do Projeto

```
gris/
├── hooks.py                    # Hooks, scheduler, overrides
├── api/                        # Endpoints REST (@frappe.whitelist)
│   ├── mcp/                    # Ferramentas expostas ao Claude (MCP)
│   └── recepcao_funil.py       # Etapas e cadência do funil (portal + MCP)
├── www/                        # Páginas de portal web (Jinja + Python)
├── gris/doctype/               # DocTypes do módulo Gris
├── financeiro/doctype/         # DocTypes do módulo Financeiro
├── gestão_de_adultos/doctype/  # DocTypes do módulo Gestão de Adultos
├── templates/                  # Templates Jinja (base PWA, portal)
├── public/                     # Assets estáticos (JS, CSS, manifest PWA)
├── fixtures/                   # Dados iniciais (roles, categorias, UOs)
├── utils/                      # Utilitários compartilhados
└── scripts/                    # Scripts auxiliares
mcp_server/                     # Ponte MCP stdio (Claude -> API do GRIS)
apps/                           # Apps Django complementares (em construção)
```

## Stack Técnica

| Componente | Tecnologia |
|---|---|
| Framework | Frappe v15 |
| Python | ≥ 3.10 (deploy: 3.11) |
| Node.js | 18.20 |
| Banco de dados | MariaDB 10.6 (utf8mb4) |
| Cache/Fila | Redis 6.2 |
| Container | Docker Compose (Gunicorn + Nginx + Caddy) |
| Lint Python | Ruff (linha 110 chars) |
| Lint JS | ESLint + Prettier |
| PWA | Service Worker + manifest.json customizado |

## Skills Disponíveis

Ao trabalhar em tarefas específicas, consulte a skill correspondente em `.claude/skills/<nome>/SKILL.md`:

| Tarefa | Skill |
|---|---|
| Backend Python (controllers, hooks, DB) | `frappe-server-logic` |
| Scripts de formulário Desk | `frappe-client-scripting` |
| Modelagem de DocType (JSON, campos, naming) | `frappe-doctype-schema` |
| Portal Web (www, Jinja, contexto) | `frappe-web-portal` |
| Design de API e whitelisting | `frappe-api-design` |
| Segurança e performance | `frappe-security-performance` |
| Gráficos ECharts | `gris-echarts-charts` |
| Guia de marca (cores, tipografia, PWA) | `gris-brand-guide` |
| Backup do Google Drive | `google-drive-backup-import` |
| Criação/avaliação de skills | `gris-skill-creator` |

## Convenções de Código

### Nomes e Linguagem

- Nomes de campos e DocTypes em **português** (ex: `nome_completo`, `historico_no_grupo`)
- Nomes de funções Python em **snake_case** (inglês ou português conforme contexto)
- Classes em **CamelCase**
- Comentários e docstrings em português quando descrevem regras de negócio

### Backend (Python/Frappe)

- Regras de negócio **sempre no servidor**, nunca apenas no client
- APIs expostas com `@frappe.whitelist()`, restringir métodos quando possível (`methods=["POST"]`)
- Endpoints guest (`allow_guest=True`) devem ser revisados com rigor
- Nunca usar `ignore_permissions=True` sem justificativa explícita
- SQL **sempre parametrizado** — nunca interpolação de string
- Evitar N+1: preferir queries agregadas
- Processos pesados devem usar `frappe.enqueue`
- **Jobs** (agendados ou enfileirados) devem narrar o que fizeram com
  `gris.utils.job_logger`: use `obter_logger(...)` no lugar de `frappe.logger(...)`,
  `metrica(...)` para contadores e `definir_resumo(...)` para a frase final. Cada
  execução vira um "Log de Execucao de Job", visível em `/app/monitor-de-jobs`
- **Não usar `frappe.cache`** neste projeto
- Respostas de API retornam dicts com chave `"success"`
- Validar permissões com `frappe.get_roles()` antes de mutações

### Frontend (Desk + Portal)

- **Desk**: eventos via `frappe.ui.form.on(...)` com handlers curtos e focados
- **Portal (www)**: `frappe.call` / fetch assíncrono com tratamento de erro
- Manipulação de campos: `frm.set_df_property()`, `frm.set_value()`
- Não duplicar validações críticas no JS sem equivalente no backend

### Segurança

- Checar `frappe.session.user == "Guest"` antes de operações autenticadas
- Sanitizar entradas e validar dados antes de persistir
- Controle de acesso por roles via `PAGE_ROLES` para portais

## Qualidade

- **Antes de commitar, rode `gris-lint`.** Ele reproduz o job "Frappe Linter" do
  CI: `pre-commit run --all-files` (Ruff, Prettier e ESLint nas versões fixadas
  em `.pre-commit-config.yaml`) e o semgrep com as regras do Frappe. Rodar o
  `prettier` ou o `ruff` do `node_modules`/`PATH` não serve: as versões diferem
  das fixadas e o CI reprova formatação feita com outra versão
- Nunca monte SQL com f-string dentro de `frappe.db.sql` — o semgrep barra
  (`frappe-sql-format-injection`) mesmo quando a interpolação é uma constante.
  Use `frappe.qb`
- Código novo deve passar nos linters configurados (Ruff, ESLint, Prettier)
- `console.log` / `print` apenas para debug temporário — remover antes de merge
- Mudanças críticas (permissões, regras de negócio, API, financeiro) exigem cobertura de teste

## Anti-padrões (evitar)

- Lógica crítica apenas no client-side
- Endpoint sem validação de acesso
- SQL sem parâmetros
- Usar `frappe.cache`
- Gravar `User.role_profile_name` (ou chamar `User.save()` / `add_roles()`) em rotinas
  automáticas: o Frappe repopula `roles` a partir do perfil e remove papéis concedidos
  manualmente. Use os utilitários de `gris/api/users/roles.py`
- Regra de negócio extensa dentro de handlers de UI
- Logs permanentes ruidosos sem valor operacional
- Job novo que termina em silêncio: sem resumo nem contadores, o Monitor de Jobs
  não consegue dizer o que aquela execução fez

## Referências

- Documentação Frappe: [docs.frappe.io](https://docs.frappe.io)
- Skills do projeto: `.claude/skills/`
- Detalhes de deploy: `DOCKER_DEPLOYMENT.md`
- Integração com o Claude (MCP): `MCP_CLAUDE.md`
