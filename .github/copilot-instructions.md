# Instruções de Desenvolvimento do Gris (Frappe)

Este arquivo define as orientações gerais para desenvolver no projeto **Gris** com o framework **Frappe**.

> **Diretriz principal:** usar as **skills** como referência técnica por tipo de tarefa.
> Não usar subagentes ou fluxo de handoff entre agentes neste projeto.

## 🎯 Objetivo

- Garantir consistência entre backend, frontend, portal e modelagem de dados.
- Reduzir retrabalho com padrões claros de implementação e revisão.
- Manter segurança, performance e manutenção como critérios de primeira classe.

## 🧩 Contexto do projeto

- Aplicação Frappe com foco em gestão do Gris.
- Módulos principais declarados em `gris/modules.txt`: `Gris` e `Financeiro`.
- Linguagem de documentação e comunicação do projeto: **Português (PT-BR)**.

## 🗺️ Mapa da estrutura real do app

Use estes caminhos como referência de implementação:

- `gris/hooks.py`: hooks, scheduler, overrides e integrações de ciclo de vida.
- `gris/api/`: endpoints e serviços de backend.
- `gris/www/`: páginas e fluxos de portal web.
- `gris/gris/doctype/`: DocTypes do módulo Gris (schema, controller e scripts).
- `gris/financeiro/doctype/`: DocTypes do módulo Financeiro.
- `gris/templates/` e `gris/public/`: templates, assets e scripts globais (ex.: PWA).

## 🧠 Skills oficiais (fonte de decisão técnica)

Consulte a skill adequada conforme o tipo de trabalho:

| Tipo de trabalho | Skill |
| :--- | :--- |
| Backend Python (controllers, hooks, DB) | `@frappe-server-logic` |
| Scripts de formulário Desk (Form API, eventos) | `@frappe-client-scripting` |
| Modelagem de DocType (JSON, campos, naming) | `@frappe-doctype-schema` |
| Portal Web (`www`, Jinja, contexto e frontend) | `@frappe-web-portal` |
| Guia de marca (cores, tipografia, tom, PWA, acessibilidade) | `@gris-brand-guide` |
| Design de API e whitelisting | `@frappe-api-design` |
| Segurança e performance | `@frappe-security-performance` |
| Importação do último backup do Google Drive | `@google-drive-backup-import` |

Skills disponíveis em: `.github/skills/<skill-name>/SKILL.md`.

## ⚙️ Convenções de backend (Frappe)

- Implementar regra de negócio no servidor (não depender apenas do client).
- Validar permissões antes de mutações de dados.
- Preferir operações com APIs do Frappe (`frappe.get_doc`, `insert`, `save`, `set_value`) com clareza de permissões.
- Em SQL, usar consultas parametrizadas e evitar interpolação de string.
- Evitar N+1: não executar consultas em loop quando houver alternativa agregada.
- Processos pesados devem ir para fila (`frappe.enqueue`) quando apropriado.

## 🖥️ Convenções de frontend (Desk + Portal)

> Prioridade de UI no projeto: **equilibrada** entre Desk e Portal.

- **Desk**: usar `frappe.ui.form.on(...)` com eventos claros e responsabilidades pequenas por handler.
- **Portal (`www`)**: usar `frappe.call`/fetch assíncrono com tratamento de erro e estado de carregamento.
- Evitar duplicar validações críticas no JS sem equivalente no backend.
- Separar lógica de apresentação da lógica de integração sempre que possível.

## 🔐 Segurança e autorização

- Revisar cuidadosamente endpoints com `allow_guest=True`.
- Nunca usar `ignore_permissions=True` sem justificativa explícita e contexto controlado.
- Garantir checagens de papel/perfil para operações sensíveis.
- Sanitizar entradas e validar dados antes de persistir.

## 🚀 Performance e robustez

- Priorizar queries agregadas em vez de múltiplas consultas por registro.
- Não usar `frappe.cache` neste projeto.
- Para performance de leitura, priorizar modelagem de consulta, índices e pré-processamento assíncrono quando necessário.
- Jobs longos e integrações externas devem rodar em background.
- Evitar regressões em rotinas agendadas (`scheduler_events`).

## ✅ Qualidade e validação

Ferramentas e automações do repositório:

- `.pre-commit-config.yaml`
- `pyproject.toml` (ruff e padrões Python)
- `.eslintrc` (JavaScript)
- `.github/workflows/linter.yml`

Diretrizes práticas:

- Código novo deve respeitar lint/format configurados no projeto.
- `console.log` e `print` são permitidos **apenas com critério** para debug temporário; remover quando não forem estritamente necessários.
- Mudanças críticas (permissões, regras de negócio, API e financeiro) exigem cobertura de teste proporcional ao risco.

## 📦 Checklist operacional para PR

Antes de concluir uma entrega:

- [ ] A skill correta foi seguida para o tipo de tarefa.
- [ ] Regras de negócio críticas estão no backend.
- [ ] Permissões/autorização foram revisadas.
- [ ] Não há SQL inseguro ou N+1 evitável.
- [ ] Fluxos Desk/Portal impactados foram validados manualmente.
- [ ] Lint/format/checks do projeto passaram.
- [ ] Em mudanças críticas, testes relevantes foram incluídos/atualizados.

## ⛔ Anti-padrões (evitar)

- Implementar lógica crítica só no client-side.
- Expor endpoint sem validação de acesso adequada.
- Usar SQL sem parâmetros.
- Implementar solução baseada em `frappe.cache`.
- Misturar regra de negócio extensa dentro de handlers de UI.
- Introduzir logs permanentes e ruidosos sem valor operacional.

## 🆘 Referências

- Documentação Frappe: [docs.frappe.io](https://docs.frappe.io)
- Código-base do framework no workspace: `apps/frappe/`
- Skills do projeto: `apps/gris/.github/skills/`
