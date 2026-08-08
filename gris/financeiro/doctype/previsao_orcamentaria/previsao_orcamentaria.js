// Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
// For license information, please see license.txt

frappe.ui.form.on("Previsao Orcamentaria", {
	refresh(frm) {
		if (frm.doc.name && !frm.is_new()) {
			frm.add_custom_button(__("Abrir no Portal"), () => {
				window.open(`/financeiro/previsao_orcamentaria?previsao=${encodeURIComponent(frm.doc.name)}`);
			});
		}
	},
});
