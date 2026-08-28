// Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
// For license information, please see license.txt

frappe.listview_settings["Log de Execucao de Job"] = {
	add_fields: ["status", "duracao", "total_erros"],
	hide_name_column: true,

	get_indicator(doc) {
		const cores = {
			"Em Execucao": "blue",
			Sucesso: "green",
			"Sucesso com Avisos": "orange",
			"Concluido com Erros": "orange",
			Erro: "red",
		};

		return [__(doc.status), cores[doc.status] || "gray", `status,=,${doc.status}`];
	},

	onload(listview) {
		listview.page.add_inner_button(__("Monitor de Jobs"), () => {
			frappe.set_route("monitor-de-jobs");
		});
	},
};
