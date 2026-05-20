// Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
// For license information, please see license.txt

frappe.ui.form.on("Opcao Convite Festa", {
	setup(frm) {
		frm.set_query("festa", () => ({
			filters: { status: "Em andamento" },
		}));
	},
});
