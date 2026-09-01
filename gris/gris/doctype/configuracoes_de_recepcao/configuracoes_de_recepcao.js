// Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
// For license information, please see license.txt

// Os Selects de grupo não têm `options` no JSON: a lista vem da instância WhatsApp
// conectada na Evolution API e é montada aqui, em uma única chamada para os três campos.
const CAMPOS_DE_GRUPO = [
	{
		fieldname: "grupo_recepcao_whatsapp",
		description:
			"Selecione o grupo da recepção para envio de mensagens WhatsApp aos responsáveis.",
	},
	{
		fieldname: "grupo_chefes_secao_whatsapp",
		description: "Selecione o grupo dos chefes de seção para os avisos do fluxo de recepção.",
	},
	{
		fieldname: "grupo_recados_gerais_whatsapp",
		description:
			"Selecione o grupo geral da UEL onde os responsáveis são incluídos após a recepção.",
	},
];

frappe.ui.form.on("Configuracoes de Recepcao", {
	async refresh(frm) {
		await carregar_opcoes_dos_grupos(frm);
	},
});

async function carregar_opcoes_dos_grupos(frm) {
	let grupos = null;

	try {
		const response = await frappe.call({
			method: "gris.utils.whatsapp.listar_grupos_whatsapp_para_select",
		});
		grupos = Array.isArray(response.message) ? response.message : [];
	} catch (error) {
		console.warn("Não foi possível carregar os grupos do WhatsApp.", error);
	}

	CAMPOS_DE_GRUPO.forEach((campo) => aplicar_opcoes(frm, campo, grupos));
}

function aplicar_opcoes(frm, campo, grupos) {
	const field = frm.fields_dict[campo.fieldname];

	if (!field) {
		return;
	}

	if (grupos === null) {
		field.df.options = [{ label: "", value: "" }];
		field.df.description =
			"Não foi possível carregar os grupos da instância WhatsApp. Verifique as configurações.";
		frm.refresh_field(campo.fieldname);
		return;
	}

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

	const valorAtual = (frm.doc[campo.fieldname] || "").trim();
	if (valorAtual && !optionValues.has(valorAtual)) {
		options.push({
			label: `${valorAtual} (selecionado anteriormente)`,
			value: valorAtual,
		});
	}

	field.df.options = options;
	field.df.description = campo.description;
	frm.refresh_field(campo.fieldname);
}
