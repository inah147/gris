// Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
// For license information, please see license.txt

// Os Selects do drive e do grupo não têm `options` no JSON: as listas vêm do Google
// Workspace e da instância WhatsApp, como em Configurações de Festas e de Associados.
const MODULO = "gris.gris.doctype.configuracoes_de_assembleias.configuracoes_de_assembleias";

frappe.ui.form.on("Configuracoes de Assembleias", {
	async refresh(frm) {
		atualizar_obrigatorios(frm);
		await Promise.all([carregar_drives(frm), carregar_grupos(frm)]);
	},
	habilitar_pastas_drive(frm) {
		atualizar_obrigatorios(frm);
	},
});

function atualizar_obrigatorios(frm) {
	const ligado = Number(frm.doc.habilitar_pastas_drive || 0) === 1;
	frm.toggle_reqd("drive_compartilhado_assembleias", ligado);
	frm.toggle_reqd("pasta_assembleias_id", ligado);
}

function aplicar_opcoes(frm, campo, itens, descricao) {
	const field = frm.fields_dict[campo];
	if (!field) {
		return;
	}
	const options = [{ label: "", value: "" }];
	const valores = new Set();
	(itens || []).forEach((item) => {
		const value = String(item.value || "").trim();
		if (value && !valores.has(value)) {
			valores.add(value);
			options.push({ label: String(item.label || value).trim(), value });
		}
	});
	const atual = String(frm.doc[campo] || "").trim();
	if (atual && !valores.has(atual)) {
		options.push({ label: `${atual} (selecionado anteriormente)`, value: atual });
	}
	field.df.options = options;
	if (descricao) {
		field.df.description = descricao;
	}
	frm.refresh_field(campo);
}

async function carregar_drives(frm) {
	try {
		const { message } = await frappe.call({ method: `${MODULO}.opcoes_de_drive` });
		aplicar_opcoes(frm, "drive_compartilhado_assembleias", message);
	} catch (error) {
		console.warn("Não foi possível carregar os drives compartilhados.", error);
	}
}

async function carregar_grupos(frm) {
	let grupos = null;
	let erro = null;
	try {
		const { message } = await frappe.call({ method: `${MODULO}.grupos_para_select` });
		grupos = message?.grupos ?? null;
		erro = message?.erro ?? null;
	} catch (error) {
		console.warn("Não foi possível carregar os grupos do WhatsApp.", error);
	}
	aplicar_opcoes(
		frm,
		"grupo_diretoria_whatsapp",
		grupos,
		grupos === null
			? `Não foi possível carregar os grupos do WhatsApp${
					erro ? `: ${frappe.utils.escape_html(erro)}` : "."
			  }`
			: __("Recebe os lembretes do prazo do edital.")
	);
}
