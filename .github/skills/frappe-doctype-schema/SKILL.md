---
name: frappe-doctype-schema
description: Modela e revisa DocTypes no Frappe, incluindo schema JSON, campos, permissões e convenções de nomenclatura. Use quando criar ou alterar estruturas de dados, validações de campos e definições de módulos em DocTypes.
---

# Modelagem de DocType

## Quando usar
Use esta skill quando o pedido envolver:
- criação ou alteração de DocType (`*.json`);
- revisão de campos, tipos, defaults e obrigatoriedade;
- ajuste de permissões por papel;
- validação de naming, módulo e impacto em formulários/integrações.

## Entregáveis esperados
- Schema consistente com domínio e convenções do projeto.
- Permissões mínimas necessárias explicitadas.
- Campos com `fieldname`, `fieldtype` e comportamento previsíveis.
- Checklist final cobrindo segurança, consistência e impacto funcional.

## Fluxo recomendado (design → schema → permission → impact)
1. Definir estrutura de dados
  - identificar entidades e campos necessários;
  - escolher tipos de campo aderentes ao uso real.
2. Aplicar convenções
  - garantir naming legível de DocType e `fieldname` em `snake_case`;
  - alinhar `module` ao domínio correto (ex.: `Gris`, `Financeiro`).
3. Revisar permissões
  - definir permissões explícitas por papel;
  - evitar permissões amplas além do necessário.
4. Validar impacto
  - revisar reflexos em formulários, relatórios e integrações;
  - confirmar compatibilidade com dados existentes e migração esperada.

## Princípios mandatórios desta skill
- Modelagem deve refletir regra de negócio no backend.
- Permissões devem seguir princípio do menor privilégio.
- Evitar campos redundantes sem necessidade clara.
- Priorizar clareza semântica em labels e opções de `Select`.
- Considerar custo de manutenção antes de ampliar schema.

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

## Anti-padrões (evitar)
- Criar campo novo para resolver problema que cabe em regra de validação.
- Usar `fieldname` inconsistente com padrão `snake_case`.
- Deixar permissões implícitas ou excessivas.
- Misturar responsabilidades de módulos sem critério.
- Introduzir mudanças de schema sem avaliar impacto em relatórios/integrações.

## Checklist final
- [ ] `fieldname` em `snake_case`.
- [ ] `module` aderente ao domínio do app.
- [ ] Permissões explícitas e mínimas.
- [ ] Tipos de campo e defaults condizem com o uso real.
- [ ] Impacto em formulários, relatórios e integrações revisado.
