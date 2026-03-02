---
name: frappe-server-logic
description: Implementa lógica de servidor em Python no Frappe com controllers, validações de documento e operações de banco seguras. Use quando houver alterações em regras de negócio, hooks, serviços backend e consistência transacional.
---

# Lógica de Servidor (Python/Frappe)

## Quando usar
Use esta skill para controllers de DocType, serviços em `gris/api/`, hooks e regras de negócio sensíveis.

## Padrão de controller
```python
import frappe
from frappe.model.document import Document

class MyDocType(Document):
    def validate(self):
        self.validate_values()

    def on_submit(self):
        pass

    def validate_values(self):
        if self.field_value < 0:
            frappe.throw("Valor inválido")
```

## Operações comuns
```python
doc = frappe.get_doc("DocType", "name_id")

data = frappe.get_list(
    "Sales Order",
    filters={"status": "Open"},
    fields=["name", "customer", "grand_total"],
)

frappe.db.sql("SELECT name FROM `tabCustomer` WHERE name = %s", (customer_name,))
```

## Consistência
- Preferir `doc.save()` quando hooks/validações devem disparar.
- Usar `frappe.db.set_value` apenas quando o bypass for intencional e seguro.

## Observabilidade
```python
frappe.logger().info(f"Operação concluída: {data}")
```

## Checklist rápido
- [ ] Regra crítica no backend.
- [ ] Permissão/autorização revisada.
- [ ] Persistência escolhida com consciência (`save` vs `set_value`).
