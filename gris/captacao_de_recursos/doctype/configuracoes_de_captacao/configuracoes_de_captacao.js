frappe.ui.form.on("Configuracoes de Captacao", {
	refresh(frm) {
		atualizar_obrigatorios(frm);
		carregar_drives(frm);
	},
	habilitar_pastas_drive(frm) {
		atualizar_obrigatorios(frm);
	},
});

function atualizar_obrigatorios(frm) {
	const habilitado = Number(frm.doc.habilitar_pastas_drive || 0) === 1;
	frm.toggle_reqd("drive_compartilhado", habilitado);
	frm.toggle_reqd("pasta_captacao", habilitado);
}

async function carregar_drives(frm) {
	try {
		const resposta = await frappe.call({
			method: "gris.captacao_de_recursos.doctype.configuracoes_de_captacao.configuracoes_de_captacao.opcoes_de_drive",
		});
		const opcoes = Array.isArray(resposta.message) ? resposta.message : [];
		const valores = opcoes.map((item) => String(item.value || "").trim()).filter(Boolean);
		frm.set_df_property("drive_compartilhado", "options", ["", ...valores].join("\n"));
	} catch (erro) {
		frm.set_df_property("drive_compartilhado", "options", "");
	}
	frm.refresh_field("drive_compartilhado");
}
