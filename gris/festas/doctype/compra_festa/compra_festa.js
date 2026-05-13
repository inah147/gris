// Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
// For license information, please see license.txt

frappe.ui.form.on("Compra Festa", {
	refresh(frm) {
		frm.set_query("area", () => ({
			filters: { festa: frm.doc.festa || "" },
		}));
	},
	festa(frm) {
		frm.set_value("area", "");
		(frm.doc.usos_em_produto || []).forEach((uso) => {
			frappe.model.set_value(uso.doctype, uso.name, "produto", "");
		});
	},
});

frappe.ui.form.on("Cotacao Compra Festa", {
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

frappe.ui.form.on("Uso em Produto Festa", {
	produto(frm, cdt, cdn) {
		// Filtragem por festa eh feita na grid; nada mais a fazer por enquanto.
	},
});
