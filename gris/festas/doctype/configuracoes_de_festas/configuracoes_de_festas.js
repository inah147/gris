frappe.ui.form.on("Configuracoes de Festas", {
	refresh(frm) {
		atualizar_campos_obrigatorios(frm);
		carregar_opcoes_drive_compartilhado(frm);
	},
	validate(frm) {
		atualizar_campos_obrigatorios(frm);
		carregar_opcoes_drive_compartilhado(frm);
	},
	habilitar_pastas_festas_drive(frm) {
		atualizar_campos_obrigatorios(frm);
	},
});

function atualizar_campos_obrigatorios(frm) {
	const habilitado = Number(frm.doc.habilitar_pastas_festas_drive || 0) === 1;
	frm.toggle_reqd("drive_compartilhado_festas", habilitado);
	frm.toggle_reqd("pasta_festas_id", habilitado);
}

async function carregar_opcoes_drive_compartilhado(frm) {
	try {
		const response = await frappe.call({
			method: "gris.festas.doctype.configuracoes_de_festas.configuracoes_de_festas.get_opcoes_drives_compartilhados_festas",
		});
		const opcoes = Array.isArray(response.message) ? response.message : [];

		const values = [];
		opcoes.forEach((item) => {
			const driveId = String(item.value || "").trim();
			if (driveId) {
				values.push(driveId);
			}
		});

		frm.set_df_property("drive_compartilhado_festas", "options", values.join("\n"));
		frm.refresh_field("drive_compartilhado_festas");
	} catch (error) {
		console.warn("Nao foi possivel carregar drives compartilhados para festas.", error);
		frm.set_df_property("drive_compartilhado_festas", "options", "");
		frm.refresh_field("drive_compartilhado_festas");
	}
}
