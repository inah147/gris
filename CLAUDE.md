# Índice de Instruções — Projeto Gris

Este arquivo é o ponto de entrada do Claude Code neste repositório. Ele **não** repete conteúdo — aponta para o arquivo certo conforme a tarefa. Leia primeiro a seção "Instruções gerais" e depois o arquivo específico da tarefa antes de editar código.

## Instruções gerais

| Preciso de... | Arquivo |
|---|---|
| Visão geral do projeto, stack, estrutura de pastas, convenções de código, segurança, anti-padrões e checklist de qualidade | [AGENTS.md](AGENTS.md) |
| Instruções detalhadas de convenções de backend/frontend e checklist de PR (formato alternativo, mesmo conteúdo do AGENTS.md em mais detalhe) | [.claude/instructions.md](.claude/instructions.md) |

## Skills por tipo de tarefa

| Vou trabalhar em... | Arquivo |
|---|---|
| Criar ou alterar um DocType (schema, campos, naming) | [.claude/skills/frappe-doctype-schema/SKILL.md](.claude/skills/frappe-doctype-schema/SKILL.md) |
| Lógica de backend (controllers, hooks, banco de dados) | [.claude/skills/frappe-server-logic/SKILL.md](.claude/skills/frappe-server-logic/SKILL.md) |
| Scripts de formulário no Desk (client scripting) | [.claude/skills/frappe-client-scripting/SKILL.md](.claude/skills/frappe-client-scripting/SKILL.md) |
| Páginas do portal web (`www`, Jinja) | [.claude/skills/frappe-web-portal/SKILL.md](.claude/skills/frappe-web-portal/SKILL.md) |
| Design de API e whitelisting | [.claude/skills/frappe-api-design/SKILL.md](.claude/skills/frappe-api-design/SKILL.md) |
| Segurança e performance | [.claude/skills/frappe-security-performance/SKILL.md](.claude/skills/frappe-security-performance/SKILL.md) |
| Gráficos ECharts | [.claude/skills/gris-echarts-charts/SKILL.md](.claude/skills/gris-echarts-charts/SKILL.md) |
| Guia de marca (cores, tipografia, tom, PWA) | [.claude/skills/gris-brand-guide/SKILL.md](.claude/skills/gris-brand-guide/SKILL.md) |
| Backup/importação do Google Drive | [.claude/skills/google-drive-backup-import/SKILL.md](.claude/skills/google-drive-backup-import/SKILL.md) |
| Rodar, atualizar ou depurar a aplicação local (WSL2 + Frappe Manager) | [.claude/skills/gris-ambiente-local/SKILL.md](.claude/skills/gris-ambiente-local/SKILL.md) |
| Criar ou avaliar uma nova skill | [.claude/skills/gris-skill-creator/SKILL.md](.claude/skills/gris-skill-creator/SKILL.md) |

## Operação e dados

| Preciso de... | Arquivo |
|---|---|
| Deploy em Docker/produção | [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) |
| Setup inicial do ambiente no Windows (WSL2, Docker, `fm`) | [WINDOWS_SETUP.md](WINDOWS_SETUP.md) |
| Dados de fixtures (roles, categorias, UOs) | [FIXTURES.md](FIXTURES.md) |
| Permissões e ambiente do auto mode do Claude Code | [.claude/settings.json](.claude/settings.json) |
| Bench para rodar testes nas sessões do Claude Code na web | [.claude/hooks/session-start.sh](.claude/hooks/session-start.sh) |

## Regra de manutenção deste índice

Ao criar um novo arquivo de instrução (skill, guia de módulo, etc.), adicione uma linha na tabela correspondente acima. Não duplique aqui o conteúdo dos arquivos linkados.
