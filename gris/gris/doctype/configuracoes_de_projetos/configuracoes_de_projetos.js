frappe.ui.form.on("Configuracoes de Projetos", {
	refresh(frm) {
		atualizar_campos_obrigatorios(frm);
		carregar_opcoes_drive_compartilhado(frm);
	},
	validate(frm) {
		atualizar_campos_obrigatorios(frm);
		carregar_opcoes_drive_compartilhado(frm);
	},
	habilitar_pastas_projetos_drive(frm) {
		atualizar_campos_obrigatorios(frm);
	},
});

function atualizar_campos_obrigatorios(frm) {
	const habilitado = Number(frm.doc.habilitar_pastas_projetos_drive || 0) === 1;
	frm.toggle_reqd("drive_compartilhado_projetos", habilitado);
	frm.toggle_reqd("pasta_projetos_id", habilitado);
}

async function carregar_opcoes_drive_compartilhado(frm) {
	try {
		const response = await frappe.call({
			method: "gris.gris.doctype.configuracoes_de_projetos.configuracoes_de_projetos.get_opcoes_drives_compartilhados_projetos",
		});
		const opcoes = Array.isArray(response.message) ? response.message : [];

		const values = [];
		opcoes.forEach((item) => {
			const driveId = String(item.value || "").trim();
			if (driveId) {
				values.push(driveId);
			}
		});

		frm.set_df_property("drive_compartilhado_projetos", "options", values.join("\n"));
		frm.refresh_field("drive_compartilhado_projetos");
	} catch (error) {
		console.warn("Nao foi possivel carregar drives compartilhados para projetos.", error);
		frm.set_df_property("drive_compartilhado_projetos", "options", "");
		frm.refresh_field("drive_compartilhado_projetos");
	}
}
