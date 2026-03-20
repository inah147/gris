---
name: frappe-client-scripting
description: Implementa scripts client-side no Frappe Desk com eventos de formulário, chamadas assíncronas e atualização de estado de UI. Use quando houver mudança em arquivos JavaScript de DocType, botões de ação, validações de UX e integrações via `frappe.call`.
---

# Client Scripting no Frappe Desk

## Quando usar
Use esta skill quando o pedido envolver:
- alteração de eventos de formulário em `frappe.ui.form.on(...)`;
- botões de ação e fluxos assíncronos com `frappe.call`;
- validações de UX no Desk com atualização de estado visual;
- integrações client-side com método backend já existente ou novo.

## Entregáveis esperados
- Script de formulário claro, com handlers pequenos por responsabilidade.
- Fluxo assíncrono com tratamento de sucesso, erro e feedback ao usuário.
- Sincronia entre estado do formulário e resposta do backend.
- Checklist final cobrindo UX, robustez e consistência com regras de backend.

## Fluxo recomendado (event → call → feedback → sync)
1. Mapear evento e objetivo
  - definir quais eventos do formulário serão usados (`refresh`, `validate`, campo específico etc.);
  - evitar lógica excessiva em um único handler.
2. Implementar interação com backend
  - usar `frappe.call` com `method`, `args` e mensagens de loading quando necessário;
  - validar retorno e cenários sem `r.message`.
3. Atualizar UI e estado
  - aplicar `frm.refresh_field(...)` para atualização pontual;
  - usar `frm.reload_doc()` quando o servidor alterar estado relevante.
4. Revisar UX e falhas
  - garantir feedback ao usuário em sucesso e erro;
  - manter experiência consistente sem travar o formulário sem necessidade.

## Princípios mandatórios desta skill
- Validação crítica deve existir também no backend.
- Evitar acoplamento entre handlers não relacionados.
- Tratar erro de API explicitamente na UI.
- Evitar lógica de negócio extensa no client.
- Preservar performance em formulários com child table e muitos eventos.

## Padrão base
```javascript
frappe.ui.form.on("DocType Name", {
  refresh(frm) {
    if (!frm.doc.__islocal) {
      frm.add_custom_button("Executar", async () => {
        // ação
      });
    }
  },

  field_name(frm) {
    if (frm.doc.field_name) {
      // lógica
    }
  }
});
```

## Child table
```javascript
frappe.ui.form.on("Child DocType Name", {
  child_table_field_name(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    // lógica com row
  }
});
```

## Chamadas assíncronas (`frappe.call`)
```javascript
frappe.call({
  method: "gris.api.modulo.metodo",
  args: { arg1: "valor" },
  freeze: true,
  freeze_message: "Processando...",
  callback(r) {
    if (r.message) {
      frappe.msgprint(r.message);
      frm.reload_doc();
    }
  }
});
```

## Anti-padrões (evitar)
- Colocar regra crítica apenas no JavaScript.
- Encadear múltiplas chamadas assíncronas sem controle de erro.
- Atualizar o formulário inteiro quando só um campo mudou.
- Criar handlers monolíticos com várias responsabilidades.
- Mostrar mensagem de sucesso sem validar retorno real da API.

## Checklist final
- [ ] Sem regra crítica apenas no JS.
- [ ] Erros de API tratados com feedback acionável.
- [ ] Atualização de estado visual consistente (`refresh_field`/`reload_doc`).
- [ ] Handlers curtos e com responsabilidade única.
- [ ] Fluxo validado para sucesso, falha e retorno vazio.
