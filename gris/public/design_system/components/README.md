# Macros Jinja do Design System

## Macros geradas pelo Basecoat CLI

Arquivos em `generated/`:

- `command.html.jinja`
- `dialog.html.jinja`
- `dropdown-menu.html.jinja`
- `popover.html.jinja`
- `select.html.jinja`
- `sidebar.html.jinja`
- `tabs.html.jinja`
- `toast.html.jinja`

## Macros de composicao

Arquivo em `composed/`:

- `basecoat-composed.html.jinja`
- `lucide.html.jinja`

Esse arquivo expande os componentes CSS-only/composed que nao sao gerados pelo
CLI.

## Exemplo de import

```jinja
{% from "public/design_system/components/generated/select.html.jinja" import select %}
{% from "public/design_system/components/composed/basecoat-composed.html.jinja" import empty, field %}
{% from "public/design_system/components/composed/lucide.html.jinja" import lucide_icon %}
```
