// Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
// For license information, please see license.txt

frappe.ui.form.on("Log de Execucao de Job", {
	refresh(frm) {
		frm.disable_save();
		frm.set_intro("");

		frappe.require("/assets/gris/js/job_log_timeline.js", () => {
			renderizar_detalhe(frm);
			aplicar_indicador(frm);
		});

		frm.add_custom_button(__("Monitor de Jobs"), () => {
			frappe.set_route("monitor-de-jobs");
		});
	},
});

function aplicar_indicador(frm) {
	frm.page.set_indicator(
		gris.job_logs.rotulo_status(frm.doc.status),
		gris.job_logs.cor_status(frm.doc.status)
	);
}

function renderizar_detalhe(frm) {
	const wrapper = frm.get_field("visualizacao").$wrapper;

	gris.job_logs.render_detalhe(wrapper, {
		eventos: parse_json(frm.doc.eventos, []),
		metricas: parse_json(frm.doc.metricas, {}),
		erro: frm.doc.erro,
	});
}

function parse_json(valor, padrao) {
	if (!valor) {
		return padrao;
	}

	try {
		return JSON.parse(valor);
	} catch (e) {
		return padrao;
	}
}
