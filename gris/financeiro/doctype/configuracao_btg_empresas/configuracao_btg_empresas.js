// Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
// For license information, please see license.txt

frappe.ui.form.on("Configuracao BTG Empresas", {
	refresh(frm) {
		frm.add_custom_button(__("Autorizar / Reconsentir"), function () {
			frappe.call({
				method: "gris.api.financeiro.btg_auth.gerar_url_autorizacao",
				callback: function (r) {
					if (r.exc || !r.message) {
						frappe.msgprint(__("Erro ao gerar URL de autorização. Verifique Client ID e Redirect URI."));
						return;
					}
					window.open(r.message, "_blank");
					frappe.msgprint(
						__("Uma nova aba foi aberta com a página de login do BTG. Após autorizar, você será redirecionado de volta."),
					);
				},
			});
		}, __("BTG OAuth"));

		frm.add_custom_button(__("Buscar Account ID"), function () {
			frappe.call({
				method: "gris.api.financeiro.btg.get_account_info",
				callback: function (r) {
					if (r.exc) {
						frappe.msgprint(__("Erro ao buscar account ID. Verifique os tokens OAuth."));
						return;
					}
					frappe.msgprint(__("Account ID obtido com sucesso: ") + (r.message && r.message.account_id || ""));
					frm.reload_doc();
				},
			});
		}, __("BTG OAuth"));
	},
});
