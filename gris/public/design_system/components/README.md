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
- `file-upload.html.jinja`
- `lucide.html.jinja`

Esse arquivo expande os componentes CSS-only/composed que nao sao gerados pelo
CLI.

## Exemplo de import

```jinja
{% from "public/design_system/components/generated/select.html.jinja" import select %}
{% from "public/design_system/components/composed/basecoat-composed.html.jinja" import empty, field %}
{% from "public/design_system/components/composed/file-upload.html.jinja" import file_upload %}
{% from "public/design_system/components/composed/lucide.html.jinja" import lucide_icon %}
```

## Upload de arquivos

Use `file_upload` para uploads no Portal com UI Basecoat. O componente envia para
`/api/method/upload_file` e emite `gris:file-upload:success` com `files`,
`source` e `is_private`.

Opções principais:

- `sources`: origens exibidas. Aceita `local`, `camera`, `web_link` e `library`.
- `allow_take_photo`: adiciona a origem `camera` mesmo quando ela não estiver em `sources`.
- `private_by_default`: define se o arquivo será salvo como privado quando o usuário não puder escolher.
- `allow_private_choice`: mostra a opção para o usuário escolher público/privado. `allow_toggle_private` e `allow_private_toggle` funcionam como aliases.
- `allowed_extensions`, `accept`, `allow_multiple`, `max_files`, `folder`, `doctype`, `docname`, `fieldname` e `method`: espelham as opções de upload do Frappe.
