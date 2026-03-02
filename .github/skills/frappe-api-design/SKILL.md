---
name: frappe-api-design
description: Define e implementa APIs no Frappe com métodos whitelisted (RPC) e endpoints REST consistentes. Use quando houver criação, ajuste ou revisão de contratos de API, autenticação/autorização, paginação, filtros ou padronização de respostas.
---

# Design de API no Frappe

## Quando usar
Use esta skill ao expor funcionalidades para frontend, integrações externas ou automações via API.

## Fluxo recomendado
1. Definir contrato de entrada/saída e erros.
2. Validar autenticação/autorização antes de mutações.
3. Implementar método whitelisted ou endpoint REST.
4. Padronizar resposta e mensagens de erro.
5. Validar paginação/filtros e cenários de borda.

## RPC com `@frappe.whitelist`
```python
@frappe.whitelist()
def update_status(name, status):
    if not frappe.db.has_permission("My DocType", "write", name):
        frappe.throw("Permissão negada", frappe.PermissionError)

    doc = frappe.get_doc("My DocType", name)
    doc.status = status
    doc.save()
    return {"status": doc.status}
```

- `allow_guest=True` só em endpoints realmente públicos e com validações explícitas.
- Evite lógica crítica exclusivamente no client.

## Padrões REST
- Preferir comportamento stateless.
- Suportar filtros estruturados quando necessário.
- Respeitar `limit_start` e `limit_page_length`.
- Retornar erros de forma previsível e acionável.

## Checklist rápido
- [ ] Permissão revisada para leitura/escrita.
- [ ] Sem SQL inseguro.
- [ ] Contrato de resposta estável.
- [ ] Casos de erro importantes cobertos.
