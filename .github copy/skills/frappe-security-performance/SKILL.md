---
name: frappe-security-performance
description: Aplica práticas de segurança e performance em código Frappe, incluindo autorização, sanitização, SQL seguro e otimização de consultas. Use quando auditar ou implementar trechos sensíveis, operações pesadas e fluxos com risco de regressão.
---

# Segurança e Performance

## Quando usar
Use esta skill quando o pedido envolver:
- auditoria de autorização, sanitização e SQL em backend/API;
- revisão de endpoints com risco de exposição de dados;
- otimização de consultas e redução de N+1;
- rotinas pesadas, jobs e fluxos com risco de regressão.

## Entregáveis esperados
- Diagnóstico claro de risco de segurança e custo de execução.
- Ajustes objetivos para autorização, entrada de dados e SQL seguro.
- Estratégia de performance sem uso de `frappe.cache` (regra do projeto).
- Checklist final para validação antes de concluir.

## Fluxo recomendado (audit → harden → optimize → validate)
1. Auditar riscos
    - mapear mutações sem checagem de permissão;
    - mapear SQL potencialmente inseguro e entradas não sanitizadas.
2. Endurecer segurança
    - aplicar autorização antes de mutação;
    - parametrizar SQL e sanitizar dados de entrada/saída quando aplicável.
3. Otimizar performance
    - reduzir N+1 e consultas redundantes;
    - mover processamento pesado para `frappe.enqueue` quando necessário.
4. Validar resultado
    - verificar regressão funcional;
    - confirmar que segurança e performance melhoraram sem overengineering.

## Princípios mandatórios desta skill
- Permissão e autorização vêm antes da persistência.
- Sem SQL por interpolação de string.
- Não usar `frappe.cache` neste projeto.
- Evitar N+1 sempre que houver alternativa agregada.
- Evitar vazamento de detalhe sensível em mensagens de erro.

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

## Anti-padrões (evitar)
- Validar acesso apenas no frontend.
- Usar `ignore_permissions=True` sem justificativa explícita.
- Manter consulta em loop quando existe forma agregada.
- Executar processo pesado de forma síncrona no request principal.
- Introduzir otimização sem medir efeito em custo e legibilidade.

## Checklist final
- [ ] Permissões conferidas antes de mutação.
- [ ] Sem SQL por interpolação.
- [ ] Sem `frappe.cache`.
- [ ] Operação pesada fora do request síncrono quando aplicável.
- [ ] Risco de N+1 revisado e mitigado.
- [ ] Mensagens de erro não expõem detalhes sensíveis.
