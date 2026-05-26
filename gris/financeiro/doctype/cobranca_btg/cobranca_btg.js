frappe.ui.form.on("Cobranca BTG", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Atualizar Status"), () => {
				frappe.call({
					method: "gris.api.financeiro.btg_cobrancas.consultar_cobranca",
					args: { name: frm.doc.name },
					callback(r) {
						if (!r.exc) {
							frm.reload_doc();
							frappe.msgprint(__("Status atualizado."));
						}
					},
				});
			}, __("BTG"));

			if (frm.doc.link_pagamento) {
				frm.add_custom_button(__("Abrir Link de Pagamento"), () => {
					window.open(frm.doc.link_pagamento, "_blank");
				}, __("BTG"));
			}

			if (frm.doc.status === "Pendente") {
				frm.add_custom_button(__("Recriar no BTG"), () => {
					frappe.confirm(
						__("Isso tentará criar novamente a cobrança na API BTG. Continuar?"),
						() => {
							frappe.call({
								method: "gris.api.financeiro.btg_cobrancas.criar_cobranca",
								args: { name: frm.doc.name },
								callback(r) {
									if (!r.exc) {
										frm.reload_doc();
										frappe.msgprint(__("Cobrança enviada ao BTG."));
									}
								},
							});
						}
					);
				}, __("BTG"));
			}
		}
	},
});
