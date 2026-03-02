---
name: frappe-client-scripting
description: Implementa scripts client-side no Frappe Desk com eventos de formulário, chamadas assíncronas e atualização de estado de UI. Use quando houver mudança em arquivos JavaScript de DocType, botões de ação, validações de UX e integrações via `frappe.call`.
---

# Client Scripting no Frappe Desk

## Quando usar
Use esta skill para alterar comportamento de formulário no Desk (`frappe.ui.form.on`) e interações com métodos backend.

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

## Boas práticas
- Validação crítica deve existir também no backend.
- Use `frm.refresh_field("campo")` para atualização pontual.
- Use `frm.reload_doc()` quando o servidor alterar estado relevante.
- Handlers pequenos e com responsabilidade única.

## Checklist rápido
- [ ] Sem regra crítica apenas no JS.
- [ ] Erros de API tratados na UI.
- [ ] Atualização de estado visual consistente.
