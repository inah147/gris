---
name: frappe-doctype-schema
description: Modela e revisa DocTypes no Frappe, incluindo schema JSON, campos, permissões e convenções de nomenclatura. Use quando criar ou alterar estruturas de dados, validações de campos e definições de módulos em DocTypes.
---

# Modelagem de DocType

## Quando usar
Use esta skill ao criar/editar arquivos de DocType (`*.json`) e ao revisar consistência de naming, permissões e tipos de campo.

## Convenções
- Nome de DocType: legível e consistente com domínio.
- `fieldname`: `snake_case`.
- Permissões explícitas por papel.
- Módulo deve refletir o app real (ex.: `Gris`, `Financeiro`).

## Estrutura de referência
```json
{
  "doctype": "DocType",
  "module": "Gris",
  "fields": [
    {
      "fieldname": "title",
      "fieldtype": "Data",
      "label": "Título",
      "reqd": 1,
      "in_list_view": 1
    },
    {
      "fieldname": "status",
      "fieldtype": "Select",
      "label": "Status",
      "options": "Aberto\nFechado",
      "default": "Aberto"
    }
  ],
  "permissions": [
    {
      "role": "System Manager",
      "read": 1,
      "write": 1,
      "create": 1,
      "delete": 1
    }
  ]
}
```

## Fluxo recomendado
1. Definir campos e tipos.
2. Revisar naming e módulo.
3. Revisar permissões mínimas necessárias.
4. Validar impacto em formulários, relatórios e integrações.

## Checklist rápido
- [ ] `fieldname` em `snake_case`.
- [ ] `module` aderente ao domínio do app.
- [ ] Permissões explícitas e mínimas.
