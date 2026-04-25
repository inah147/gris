// Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
// For license information, please see license.txt

frappe.ui.form.on("Agenda de Visitas", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		if (frm.doc.visita_confirmada) {
			return;
		}

		frm.add_custom_button("Mandar Lembrete de Visita", () => {
			frappe.call({
				method: "gris.api.recepcao_notificacoes.enviar_lembrete_visita_manual",
				args: {
					visita_name: frm.doc.name,
				},
				freeze: true,
				freeze_message: "Enviando lembrete para o responsável...",
				callback(r) {
					if (r.message && r.message.success) {
						frappe.show_alert({
							message: r.message.message || "Lembrete enviado com sucesso.",
							indicator: "green",
						});
					}
				},
			});
		});
	},
});
