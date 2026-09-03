// Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
// For license information, please see license.txt

// Mesmo arranjo de Configuracoes de Recepcao: o Select de grupo não tem `options`
// no JSON porque a lista vem da instância WhatsApp conectada na Evolution API.
const CAMPO_DO_GRUPO = {
	fieldname: "grupo_desenvolvimento_whatsapp",
	description: "Selecione o grupo que recebe o aviso de cada nova solicitação do GRIS.",
};

frappe.ui.form.on("Configuracoes de Desenvolvimento", {
	refresh(frm) {
		carregar_opcoes_do_grupo(frm);
	},
});

async function carregar_opcoes_do_grupo(frm) {
	let grupos = null;

	try {
		const response = await frappe.call({
			method: "gris.utils.whatsapp.listar_grupos_whatsapp_para_select",
			args: { doctype: "Configuracoes de Desenvolvimento" },
		});
		grupos = Array.isArray(response.message) ? response.message : [];
	} catch (error) {
		console.warn("Não foi possível carregar os grupos do WhatsApp.", error);
	}

	aplicar_opcoes(frm, CAMPO_DO_GRUPO, grupos);
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

	// Sem isto, um grupo já configurado sumiria do Select quando a Evolution não
	// devolvesse a lista — e o próximo save gravaria vazio sem ninguém perceber.
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
