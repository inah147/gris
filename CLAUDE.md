# Índice de Instruções — Projeto Gris

Este arquivo é o ponto de entrada do Claude Code neste repositório. Ele **não** repete conteúdo — aponta para o arquivo certo conforme a tarefa. Leia primeiro a seção "Instruções gerais" e depois o arquivo específico da tarefa antes de editar código.

## Instruções gerais

| Preciso de... | Arquivo |
|---|---|
| Visão geral do projeto, stack, estrutura de pastas, convenções de código, segurança, anti-padrões e checklist de qualidade | [AGENTS.md](AGENTS.md) |

## Skills por tipo de tarefa

| Vou trabalhar em... | Arquivo |
|---|---|
| Criar ou alterar um DocType (schema, campos, naming) | [.github/skills/frappe-doctype-schema/SKILL.md](.github/skills/frappe-doctype-schema/SKILL.md) |
| Lógica de backend (controllers, hooks, banco de dados) | [.github/skills/frappe-server-logic/SKILL.md](.github/skills/frappe-server-logic/SKILL.md) |
| Scripts de formulário no Desk (client scripting) | [.github/skills/frappe-client-scripting/SKILL.md](.github/skills/frappe-client-scripting/SKILL.md) |
| Páginas do portal web (`www`, Jinja) | [.github/skills/frappe-web-portal/SKILL.md](.github/skills/frappe-web-portal/SKILL.md) |
| Design de API e whitelisting | [.github/skills/frappe-api-design/SKILL.md](.github/skills/frappe-api-design/SKILL.md) |
| Segurança e performance | [.github/skills/frappe-security-performance/SKILL.md](.github/skills/frappe-security-performance/SKILL.md) |
| Gráficos ECharts | [.github/skills/gris-echarts-charts/SKILL.md](.github/skills/gris-echarts-charts/SKILL.md) |
| Guia de marca (cores, tipografia, tom, PWA) | [.github/skills/gris-brand-guide/SKILL.md](.github/skills/gris-brand-guide/SKILL.md) |
| Backup/importação do Google Drive | [.github/skills/google-drive-backup-import/SKILL.md](.github/skills/google-drive-backup-import/SKILL.md) |
| Criar ou avaliar uma nova skill | [.github/skills/gris-skill-creator/SKILL.md](.github/skills/gris-skill-creator/SKILL.md) |

## Operação e dados

| Preciso de... | Arquivo |
|---|---|
| Deploy em Docker/produção | [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) |
| Dados de fixtures (roles, categorias, UOs) | [FIXTURES.md](FIXTURES.md) |

## Regra de manutenção deste índice

Ao criar um novo arquivo de instrução (skill, guia de módulo, etc.), adicione uma linha na tabela correspondente acima. Não duplique aqui o conteúdo dos arquivos linkados.
