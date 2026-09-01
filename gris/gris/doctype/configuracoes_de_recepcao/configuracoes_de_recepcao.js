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
		atualizar_campos_obrigatorios(frm);
		await Promise.all([
			carregar_opcoes_dos_grupos(frm),
			carregar_opcoes_drive_compartilhado(frm),
		]);
	},
	habilitar_documentos_drive(frm) {
		atualizar_campos_obrigatorios(frm);
	},
});

// Espelha o `validate()` do controller: os campos do Drive só são exigidos com o envio ligado.
function atualizar_campos_obrigatorios(frm) {
	const habilitado = Number(frm.doc.habilitar_documentos_drive || 0) === 1;
	[
		"drive_compartilhado_acesso_restrito",
		"pasta_documentos_identificacao_id",
		"pasta_declaracoes_nao_assinadas_id",
		"pasta_declaracoes_assinadas_id",
	].forEach((fieldname) => frm.toggle_reqd(fieldname, habilitado));
}

// O Select não tem `options` no JSON: a lista vem dos drives ativos de
// Configuracoes Google Workspace, mesma fonte usada por festas e projetos.
async function carregar_opcoes_drive_compartilhado(frm) {
	try {
		const response = await frappe.call({
			method: "gris.gris.doctype.configuracoes_de_recepcao.configuracoes_de_recepcao.get_opcoes_drives_compartilhados_recepcao",
		});
		const opcoes = Array.isArray(response.message) ? response.message : [];

		const values = [];
		opcoes.forEach((item) => {
			const driveId = String(item.value || "").trim();
			if (driveId) {
				values.push(driveId);
			}
		});

		frm.set_df_property("drive_compartilhado_acesso_restrito", "options", values.join("\n"));
		frm.refresh_field("drive_compartilhado_acesso_restrito");
	} catch (error) {
		console.warn("Não foi possível carregar os drives compartilhados.", error);
		frm.set_df_property("drive_compartilhado_acesso_restrito", "options", "");
		frm.refresh_field("drive_compartilhado_acesso_restrito");
	}
}

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
