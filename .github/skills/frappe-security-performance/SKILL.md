---
name: frappe-security-performance
description: Aplica práticas de segurança e performance em código Frappe, incluindo autorização, sanitização, SQL seguro e otimização de consultas. Use quando auditar ou implementar trechos sensíveis, operações pesadas e fluxos com risco de regressão.
---

# Segurança e Performance

## Quando usar
Use esta skill para revisão preventiva e implementação segura de backend, APIs e rotinas de alto custo.

## Segurança
### Permissões
```python
if not frappe.db.has_permission("DocType", "read", doc_name):
    frappe.throw("Não permitido")
```

### SQL Injection
```python
# ✅ Parametrizado
frappe.db.sql("select name from tabCustomer where name = %s", (name,))
```

### XSS
```python
safe_html = frappe.utils.html_escape(user_input)
```

## Performance
### Evitar N+1
```python
orders = frappe.get_list(
    "Sales Order",
    fields=["name", "customer_name", "grand_total"]
)
```

### Operações pesadas em background
```python
frappe.enqueue(
    method="gris.api.tasks.processar_lote",
    queue="long",
    timeout=300,
    param1=value,
)
```

## Regras deste projeto
- Não usar `frappe.cache`.
- Priorizar modelagem de consulta, índices e processamento assíncrono.
- Revisar riscos em endpoints e tarefas agendadas.

## Loop de validação
1. Implementar mudança.
2. Revisar segurança (permissão, sanitização, SQL).
3. Revisar custo de consulta e concorrência.
4. Ajustar e revalidar até passar.

## Checklist rápido
- [ ] Permissões conferidas antes de mutação.
- [ ] Sem SQL por interpolação.
- [ ] Sem `frappe.cache`.
- [ ] Operação pesada fora do request síncrono quando aplicável.
