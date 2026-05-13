// Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
// For license information, please see license.txt

frappe.ui.form.on("Produto de Venda Festa", {
	refresh(frm) {
		frm.set_query("area", () => ({
			filters: { festa: frm.doc.festa || "" },
		}));
	},
	festa(frm) {
		// Limpa area se festa mudou para evitar cruzamento
		frm.set_value("area", "");
	},
});
