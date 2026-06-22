---
name: frappe-server-logic
description: Implementa lógica de servidor em Python no Frappe com controllers, validações de documento e operações de banco seguras. Use quando houver alterações em regras de negócio, hooks, serviços backend e consistência transacional.
---

# Lógica de Servidor (Python/Frappe)

## Quando usar
Use esta skill quando o pedido envolver:
- controllers de DocType e validações de documento;
- serviços em `gris/api/` com regra de negócio;
- hooks e automações de ciclo de vida;
- operações de banco com necessidade de consistência transacional.

## Entregáveis esperados
- Regra de negócio implementada no backend com validação explícita.
- Persistência escolhida de forma consciente (`save` vs `set_value`).
- Tratamento de autorização e integridade de dados antes da mutação.
- Checklist final cobrindo segurança, consistência e manutenção.

## Fluxo recomendado (rule → validate → persist → verify)
1. Definir regra de negócio
    - mapear pré-condições e invariantes;
    - manter responsabilidades claras entre controller, serviço e hook.
2. Validar autorização e dados
    - aplicar checagens de permissão quando necessário;
    - validar entradas antes de persistir.
3. Persistir com estratégia adequada
    - usar `doc.save()` quando hooks/validações devem disparar;
    - usar `frappe.db.set_value` apenas quando bypass for intencional e seguro.
4. Verificar consistência
    - revisar efeitos colaterais, idempotência e possíveis regressões;
    - garantir rastreabilidade mínima com logs úteis e não ruidosos.

## Princípios mandatórios desta skill
- Regra crítica deve viver no backend.
- Mutação sem validação de autorização é proibida.
- SQL deve ser parametrizado quando necessário.
- Evitar N+1 e consultas redundantes.
- Observabilidade deve ser útil e proporcional.

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

## Anti-padrões (evitar)
- Implementar regra crítica só no client-side.
- Usar `ignore_permissions=True` por conveniência.
- Misturar lógica extensa de negócio em handlers de UI.
- Usar logs permanentes sem valor operacional.
- Persistir com bypass sem justificar impacto.

## Checklist final
- [ ] Regra crítica no backend.
- [ ] Permissão/autorização revisada.
- [ ] Persistência escolhida com consciência (`save` vs `set_value`).
- [ ] SQL seguro e sem N+1 evitável.
- [ ] Efeitos colaterais e regressões principais revisados.
