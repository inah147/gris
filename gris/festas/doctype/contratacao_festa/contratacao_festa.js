// Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
// For license information, please see license.txt

frappe.ui.form.on("Contratacao Festa", {
	refresh(frm) {
		frm.set_query("area", () => ({
			filters: { festa: frm.doc.festa || "" },
		}));
	},
	festa(frm) {
		frm.set_value("area", "");
	},
});

frappe.ui.form.on("Cotacao Contratacao Festa", {
	escolhida(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.escolhida) return;
		(frm.doc.cotacoes || []).forEach((c) => {
			if (c.name !== cdn && c.escolhida) {
				frappe.model.set_value(c.doctype, c.name, "escolhida", 0);
			}
		});
	},
});
