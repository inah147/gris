---
name: frappe-api-design
description: Define e implementa APIs no Frappe com métodos whitelisted (RPC) e endpoints REST consistentes. Use quando houver criação, ajuste ou revisão de contratos de API, autenticação/autorização, paginação, filtros, padronização de respostas e tratamento de erros.
---

# Design de API no Frappe

## Quando usar
Use esta skill quando o pedido envolver:
- criação de método `@frappe.whitelist` para frontend Desk/Portal;
- criação ou revisão de endpoint REST no Frappe;
- definição de contrato de entrada/saída, paginação e filtros;
- revisão de autenticação/autorização em APIs com mutação de dados;
- padronização de resposta e erros para integrações externas.

## Entregáveis esperados
- Contrato explícito de entrada, saída e erros.
- Endpoint RPC/REST com autorização coerente ao risco.
- Resposta previsível para sucesso e falha.
- Checklist final cobrindo segurança, performance e consistência.

## Fluxo recomendado (contract → auth → implement → validate)
1. Capturar intenção e contrato
    - definir payload de entrada, campos obrigatórios/opcionais e formato de retorno;
    - mapear cenários de erro (permissão, validação, não encontrado, conflito).
2. Definir autenticação e autorização
    - decidir se a API é autenticada ou pública;
    - para mutações, validar papel/perfil e permissão no backend antes de persistir.
3. Implementar RPC ou REST
    - usar `@frappe.whitelist()` para chamadas RPC de app/portal;
    - manter contrato estável e nomes claros para parâmetros.
4. Padronizar resposta e erros
    - retornar payload consistente, acionável e sem vazamento de detalhe sensível;
    - diferenciar erros de validação, permissão e falha interna.
5. Validar bordas e custo
    - revisar paginação, filtros, ordenação e limites;
    - evitar N+1 e SQL por interpolação.

## Princípios mandatórios desta skill
- Regras críticas no backend (nunca somente no client).
- Autorização antes de qualquer mutação de dados.
- SQL sempre parametrizado quando necessário.
- `allow_guest=True` apenas com requisito explícito e validações adicionais.
- `ignore_permissions=True` somente com justificativa clara e contexto controlado.
- Operações pesadas devem considerar processamento assíncrono (`frappe.enqueue`).

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

- Para mutação, validar também regras de negócio no servidor além da permissão.
- Se usar `allow_guest=True`, documentar explicitamente por que o endpoint pode ser público.

## Padrões REST
- Preferir comportamento stateless e contrato explícito de filtros.
- Respeitar `limit_start` e `limit_page_length` para listas.
- Validar e normalizar parâmetros de paginação e ordenação.
- Não expor stack trace ou detalhes internos em erros de produção.

## Padrão de resposta e erros
### Sucesso
```json
{
    "ok": true,
    "data": {
        "name": "DOC-0001",
        "status": "Ativo"
    },
    "meta": {
        "request_id": "optional"
    }
}
```

### Erro
```json
{
    "ok": false,
    "error": {
        "code": "PERMISSION_DENIED",
        "message": "Você não tem permissão para esta operação."
    }
}
```

Diretrizes:
- manter `code` estável para consumo por integração;
- usar mensagens claras em PT-BR sem detalhes internos;
- garantir que erros de validação sejam distinguíveis de erros de permissão.

## Anti-padrões (evitar)
- Expor endpoint com mutação sem checar permissão no backend.
- Implementar validação crítica apenas no JavaScript do cliente.
- Usar SQL com interpolação de string.
- Publicar endpoint com `allow_guest=True` por conveniência.
- Usar `ignore_permissions=True` sem justificativa operacional.
- Ignorar paginação em consultas de alto volume.
- Retornar erros inconsistentes para cenários equivalentes.

## Checklist final
- [ ] Contrato de entrada/saída e erros está explícito.
- [ ] Autenticação/autorização revisadas para o risco da operação.
- [ ] Sem SQL inseguro e sem N+1 evitável.
- [ ] Paginação/filtros/ordenação validados para listas.
- [ ] Resposta e erro seguem padrão consistente e acionável.
- [ ] `allow_guest=True` e `ignore_permissions=True` revisados com justificativa.
- [ ] Cenários de borda e falha principal foram cobertos.
