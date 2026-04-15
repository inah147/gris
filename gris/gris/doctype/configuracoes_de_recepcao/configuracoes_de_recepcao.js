// Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
// For license information, please see license.txt

frappe.ui.form.on("Configuracoes de Recepcao", {
	async refresh(frm) {
		await carregar_opcoes_grupo_recepcao(frm);
	},
});

async function carregar_opcoes_grupo_recepcao(frm) {
	const fieldname = "grupo_recepcao_whatsapp";
	const field = frm.fields_dict[fieldname];

	if (!field) {
		return;
	}

	try {
		const response = await frappe.call({
			method: "gris.utils.whatsapp.listar_grupos_whatsapp_para_select",
		});

		const grupos = Array.isArray(response.message) ? response.message : [];
		const options = [{ label: "", value: "" }];
		const optionValues = new Set();

		grupos.forEach((grupo) => {
			const value = (grupo.value || "").trim();
			if (!value || optionValues.has(value)) {
				return;
			}

			optionValues.add(value);
			options.push({
				label: (grupo.label || value).trim(),
				value,
			});
		});

		const valorAtual = (frm.doc[fieldname] || "").trim();
		if (valorAtual && !optionValues.has(valorAtual)) {
			options.push({
				label: `${valorAtual} (selecionado anteriormente)`,
				value: valorAtual,
			});
		}

		field.df.options = options;
		field.df.description =
			"Selecione o grupo da recepção para envio de mensagens WhatsApp aos responsáveis.";
		frm.refresh_field(fieldname);
	} catch (error) {
		console.warn("Não foi possível carregar os grupos do WhatsApp.", error);
		field.df.options = [{ label: "", value: "" }];
		field.df.description =
			"Não foi possível carregar os grupos da instância WhatsApp. Verifique as configurações.";
		frm.refresh_field(fieldname);
	}
}
