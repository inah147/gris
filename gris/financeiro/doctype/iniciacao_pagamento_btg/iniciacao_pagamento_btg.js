frappe.ui.form.on("Iniciacao Pagamento BTG", {
	refresh(frm) {
		if (!frm.is_new() && frm.doc.docstatus === 1 && frm.doc.external_id) {
			frm.add_custom_button(__("Cancelar Pagamento"), () => {
				frappe.confirm(
					__("Deseja cancelar este pagamento no BTG?"),
					() => {
						frappe.call({
							method: "gris.api.financeiro.btg_payments.cancelar_pagamento",
							args: { name: frm.doc.name },
							callback(r) {
								if (!r.exc) {
									frm.reload_doc();
									frappe.msgprint(__("Pedido de cancelamento enviado."));
								}
							},
						});
					}
				);
			}, __("BTG"));
		}
	},
});
