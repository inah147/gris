// Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
// For license information, please see license.txt

frappe.ui.form.on("Convite Festa", {
	setup(frm) {
		frm.set_query("festa", () => ({
			filters: { status: "Em andamento" },
		}));
		frm.set_query("opcao_convite", "itens", (doc) => ({
			filters: { festa: doc.festa, ativo: 1 },
		}));
	},
	refresh(frm) {
		if (!frm.is_new() && frm.doc.cobranca_infinitepay) {
			frm.add_custom_button(__("Reenviar QR codes"), () => {
				frappe.call({
					method:
						"gris.festas.doctype.convite_festa.convite_festa.reenviar_qr_codes",
					args: { convite_name: frm.doc.name },
					freeze: true,
					freeze_message: __("Enfileirando reenvio..."),
					callback: (r) => {
						if (r.message && r.message.ok) {
							frappe.show_alert({
								message: __("Reenvio enfileirado com sucesso."),
								indicator: "green",
							});
						}
					},
				});
			});
		}
	},
});

frappe.ui.form.on("Item Convite Festa", {
	opcao_convite(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.eh_convite || !row.opcao_convite) return;
		frappe.db
			.get_value("Opcao Convite Festa", row.opcao_convite, [
				"nome_convite",
				"valor",
			])
			.then((r) => {
				if (!r || !r.message) return;
				frappe.model.set_value(cdt, cdn, "descricao", r.message.nome_convite);
				frappe.model.set_value(cdt, cdn, "valor", r.message.valor);
			});
	},
	eh_convite(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.eh_convite) {
			frappe.model.set_value(cdt, cdn, "opcao_convite", null);
		}
	},
});
