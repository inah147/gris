# Frappe Development Standards

Estes padrões se aplicam a TODOS os custom agents neste workspace.

## Padrões de Código Obrigatórios

### Python
```python
# 1. Sempre validar no servidor
def validate(doc, method):
    if doc.field_value < 0:
        frappe.throw("Mensagem de erro clara")

# 2. Usar padrões Frappe
frappe.get_doc()      # Obter documento
frappe.get_list()     # Listar documentos
frappe.db.sql()       # Raw queries se necessário
frappe.cache()        # Cache operations

# 3. Logging
frappe.logger().info(f"Operação completada: {data}")

# 4. Permissões
if not frappe.db.has_permission("DocType", "read", name):
    frappe.throw("Sem permissão")
```

### JavaScript
```javascript
// 1. Form hooks corretos
frappe.ui.form.on("DocType", {
    refresh: function(frm) { },
    field_name: function(frm) { }
});

// 2. Async corretamente
frappe.call({
    method: "module.method_name",
    args: { arg: value },
    callback: function(r) {
        if (r.message) { }
    }
});

// 3. Validação antes de operações
if (!frm.doc.required_field) {
    frappe.throw("Campo obrigatório não preenchido");
}
```

### JSON (DocType Definition)
```json
{
    "doctype": "CamelCase",
    "module": "snake_case_app",
    "fields": [
        {
            "fieldname": "field_name",
            "fieldtype": "Data",
            "label": "Field Label",
            "reqd": 1
        }
    ]
}
```

## Namespaces e Convenções

### DocTypes
- **Padrão**: `PascalCase` (ex: `Customer`, `Sales Order`)
- **Prefix**: Use o nome da app para evitar conflitos

### Fields
- **Padrão**: `snake_case` (ex: `customer_name`, `is_active`)
- **ID Fields**: `{doctype_name}_id` ou apenas `name` (automático)

### Methods
- **Python**: `snake_case`
- **JavaScript**: `camelCase`

### Variables
- **Python**: `snake_case`
- **JavaScript**: `camelCase`

## Checklist Pré-Commit

Antes de qualquer commit, verificar:

- [ ] Código validado pelo linter
- [ ] Sem console.log() ou print() em produção
- [ ] Validações no servidor implementadas
- [ ] Permissões verificadas
- [ ] Testes básicos passam
- [ ] Nenhuma hardcoded credential
- [ ] Comments explicam WHY, não WHAT
- [ ] Performance considerada (sem N+1 queries)

## Estrutura de Projeto Esperada

```
seu_app/
├── seu_app/                  # App package
│   ├── __init__.py
│   ├── hooks.py              # Hooks de app
│   ├── config.py             # Menu config
│   └── modules.txt           # Modules declarados
│
├── seu_app/seu_modulo/       # Module
│   ├── __init__.py
│   ├── doctype/
│   │   └── seu_doctype/
│   │       ├── seu_doctype.py
│   │       ├── seu_doctype.js
│   │       └── seu_doctype.json
│   ├── report/
│   ├── page/
│   └── api.py                # Custom APIs
│
└── tests/                    # Unit tests
    └── test_seu_modulo.py
```

## Git Workflow

```bash
# Feature branch
git checkout -b feature/nome-da-feature

# Commit patterns
git commit -m "feat: descrição da feature"
git commit -m "fix: descrição do fix"
git commit -m "docs: atualização de documentação"

# Para merge
git push origin feature/nome-da-feature
```

## Comunicação Entre Agents

Quando um agent sugere handoff para outro:
1. Contexto é preservado na conversação
2. O novo agent herda todo o histórico
3. Prompt é pré-preenchido com tarefa

Exemplo de handoff eficiente:
```
Architect → Planejar estrutura
    ↓ handoff
DocType Builder → Implementar DocTypes
    ↓ handoff
Code Reviewer → Revisar qualidade
    ↓ handoff
Performance Optimizer → Otimizar (se necessário)
```

## Resources Obrigatórios

- Documentação Frappe: https://docs.frappe.io
- Framework Folder: `/frappe` em seu workspace
- Exemplos: Apps oficiais (frappe, erpnext)
- Reference: Código existente em seu projeto

## Quando Pedir Help

Se um agent não conseguir completar algo, SEMPRE handoff para:
- **Dúvida sobre padrão Frappe** → Architect
- **Issue de código Python** → Bug Fixer
- **Issue de formulário JS** → Bug Fixer
- **Problema de performance** → Performance Optimizer

## Security Best Practices

- Validar SEMPRE no servidor
- Nunca confiar em dados do cliente
- SQL parameterizado
- XSS protection
- CSRF tokens
- Rate limiting
- Input sanitization
- Secure headers

## Performance Best Practices

- Evitar N+1 queries
- Usar índices em campos de filtro
- Caching para dados estáticos
- Lazy loading para grandes datasets
- Minimizar requisições HTTP
- Minificar CSS/JS
- Compressão Gzip

## Acessibilidade (A11y) Best Practices

- Contraste de cores (4.5:1 para texto)
- Labels em inputs
- Semantic HTML
- ARIA labels
- Teclado navegável
- Focus indicators
- Alt text em imagens
