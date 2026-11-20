// Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
// For license information, please see license.txt

// O Select do grupo não tem `options` no JSON: a lista vem da instância WhatsApp
// conectada na Evolution API, como em Configurações de Recepção.
const CAMPO_GRUPO_CHEFES = "grupo_chefes_whatsapp";
const DESCRICAO_GRUPO_CHEFES =
	"Grupo que recebe, no início do mês, a lista dos beneficiários que vencem no mês, por seção.";

const MODELOS_DA_REGUA = [
	{ campo: "modelo_venc_30", rotulo: "Associado — 30 dias antes" },
	{ campo: "modelo_venc_7", rotulo: "Associado — 7 dias antes" },
	{ campo: "modelo_venc_1", rotulo: "Associado — 1 dia antes" },
	{ campo: "modelo_venc_0", rotulo: "Associado — no dia" },
	{ campo: "modelo_venc_recorrente", rotulo: "Associado — cobrança recorrente" },
	{ campo: "modelo_venc_grupo_mensal", rotulo: "Grupo de chefes — resumo do mês" },
	{ campo: "modelo_venc_chefe_30", rotulo: "Chefe — 30 dias antes" },
	{ campo: "modelo_venc_chefe_7", rotulo: "Chefe — 7 dias antes" },
	{ campo: "modelo_venc_chefe_pos", rotulo: "Chefe — vencidos" },
];

frappe.ui.form.on("Configuracoes de Associados", {
	async refresh(frm) {
		frm.add_custom_button(__("Pré-visualizar mensagem"), () => abrir_pre_visualizacao(frm));
		await carregar_opcoes_do_grupo(frm);
	},
});

async function carregar_opcoes_do_grupo(frm) {
	const field = frm.fields_dict[CAMPO_GRUPO_CHEFES];
	if (!field) {
		return;
	}

	let grupos = null;
	let erro = null;
	try {
		const response = await frappe.call({
			method: "gris.api.associados_vencimento_modelos.grupos_para_select",
		});
		grupos = response.message?.grupos ?? null;
		erro = response.message?.erro ?? null;
	} catch (error) {
		console.warn("Não foi possível carregar os grupos do WhatsApp.", error);
	}

	const options = [{ label: "", value: "" }];
	const valores = new Set();
	(grupos || []).forEach((grupo) => {
		const value = (grupo.value || "").trim();
		if (!value || valores.has(value)) {
			return;
		}
		valores.add(value);
		options.push({ label: (grupo.label || value).trim(), value });
	});

	const valorAtual = (frm.doc[CAMPO_GRUPO_CHEFES] || "").trim();
	if (valorAtual && !valores.has(valorAtual)) {
		options.push({ label: `${valorAtual} (selecionado anteriormente)`, value: valorAtual });
	}

	field.df.options = options;
	field.df.description =
		grupos === null
			? `Não foi possível carregar os grupos do WhatsApp${
					erro ? `: ${frappe.utils.escape_html(erro)}` : "."
			  }`
			: DESCRICAO_GRUPO_CHEFES;
	frm.refresh_field(CAMPO_GRUPO_CHEFES);
}

function abrir_pre_visualizacao(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Pré-visualizar mensagem"),
		size: "large",
		fields: [
			{
				fieldname: "campo",
				fieldtype: "Select",
				label: __("Mensagem"),
				options: MODELOS_DA_REGUA.map((m) => ({ label: m.rotulo, value: m.campo })),
				default: MODELOS_DA_REGUA[0].campo,
				change: () => atualizar_pre_visualizacao(frm, dialog),
			},
			{
				fieldname: "aviso",
				fieldtype: "HTML",
				options: `<p class="text-muted small">${__(
					"Dados fictícios. A mensagem mostra o texto ainda não salvo do formulário, com o rodapé que vai em toda mensagem."
				)}</p>`,
			},
			{ fieldname: "pre_visualizacao", fieldtype: "HTML" },
		],
		primary_action_label: __("Restaurar texto padrão"),
		primary_action: () => restaurar_padrao(frm, dialog),
		secondary_action_label: __("Fechar"),
		secondary_action: () => dialog.hide(),
	});
	dialog.show();
	atualizar_pre_visualizacao(frm, dialog);
}

async function atualizar_pre_visualizacao(frm, dialog) {
	const campo = dialog.get_value("campo");
	const area = dialog.fields_dict.pre_visualizacao.$wrapper;
	area.html(`<p class="text-muted">${__("Carregando…")}</p>`);

	try {
		const response = await frappe.call({
			method: "gris.api.associados_vencimento_modelos.pre_visualizar_modelo",
			args: { campo, texto: frm.doc[campo] || "" },
		});
		const bloco = $("<pre>")
			.css({
				"white-space": "pre-wrap",
				"font-family": "inherit",
				padding: "var(--padding-md)",
				background: "var(--subtle-fg)",
				"border-radius": "var(--border-radius-md)",
			})
			.text(response.message || "");
		area.empty().append(bloco);
	} catch (error) {
		area.html(
			`<p class="text-danger">${__(
				"Não foi possível montar a pré-visualização. Confira as variáveis do texto."
			)}</p>`
		);
	}
}

function restaurar_padrao(frm, dialog) {
	const campo = dialog.get_value("campo");
	const rotulo = MODELOS_DA_REGUA.find((m) => m.campo === campo)?.rotulo || campo;
	frappe.confirm(
		__("Trocar o texto de “{0}” pelo padrão? A mudança só vale depois de salvar.", [rotulo]),
		async () => {
			const response = await frappe.call({
				method: "gris.api.associados_vencimento_modelos.modelo_padrao",
				args: { campo },
			});
			await frm.set_value(campo, response.message || "");
			atualizar_pre_visualizacao(frm, dialog);
			frappe.show_alert({
				message: __("Texto padrão restaurado. Salve para aplicar."),
				indicator: "green",
			});
		}
	);
}
