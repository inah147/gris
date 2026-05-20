// Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
// For license information, please see license.txt

frappe.ui.form.on("Cobranca Infinitepay", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.status === "Pago") return;

		frm.add_custom_button(
			__("Marcar pagamento manualmente"),
			() => {
				frappe.prompt(
					[
						{
							label: __("Transaction NSU (InfinitePay)"),
							fieldname: "transaction_nsu",
							fieldtype: "Data",
							reqd: 1,
							description: __(
								"NSU exato da transação aprovada (visível no painel da InfinitePay).",
							),
						},
						{
							label: __("Justificativa"),
							fieldname: "justificativa",
							fieldtype: "Small Text",
							reqd: 1,
							description: __(
								"Por que estamos marcando manualmente? (ex.: webhook não chegou; pagamento confirmado no painel da InfinitePay)",
							),
						},
					],
					(values) => {
						frappe.confirm(
							__(
								"Tem certeza? Esta ação ignora a verificação automática da InfinitePay.",
							),
							() => {
								frappe.call({
									method:
										"gris.financeiro.doctype.cobranca_infinitepay.cobranca_infinitepay.marcar_pago_manualmente",
									args: {
										name: frm.doc.name,
										transaction_nsu: values.transaction_nsu,
										justificativa: values.justificativa,
									},
									freeze: true,
									freeze_message: __("Marcando como Pago..."),
									callback: (r) => {
										if (!r.message) return;
										frappe.show_alert({
											message: r.message.message,
											indicator: r.message.ok ? "green" : "orange",
										});
										if (r.message.ok) frm.reload_doc();
									},
								});
							},
						);
					},
					__("Marcar pagamento manualmente"),
					__("Confirmar"),
				);
			},
			__("InfinitePay"),
		);

		frm.add_custom_button(
			__("Sincronizar com InfinitePay"),
			() => {
				frappe.prompt(
					[
						{
							label: __("Transaction NSU (opcional)"),
							fieldname: "transaction_nsu",
							fieldtype: "Data",
							description: __(
								"NSU da transação aprovada (visível no painel da InfinitePay).",
							),
						},
						{
							label: __("Slug / Código da fatura (opcional)"),
							fieldname: "slug",
							fieldtype: "Data",
							description: __(
								"Slug da fatura na InfinitePay. Só chega via webhook ou pela URL de redirect após o pagamento. Se já estiver salvo no campo Invoice Slug, deixe em branco.",
							),
						},
					],
					(values) => {
						frappe.call({
							method:
								"gris.financeiro.doctype.cobranca_infinitepay.cobranca_infinitepay.sincronizar_pagamento",
							args: {
								name: frm.doc.name,
								transaction_nsu: values.transaction_nsu || null,
								slug: values.slug || null,
							},
							freeze: true,
							freeze_message: __("Consultando InfinitePay..."),
							callback: (r) => {
								if (!r.message) return;
								const indicator = r.message.ok ? "green" : "orange";
								frappe.show_alert({
									message: r.message.message,
									indicator,
								});
								if (r.message.ok) frm.reload_doc();
							},
						});
					},
					__("Sincronizar pagamento"),
					__("Confirmar"),
				);
			},
			__("InfinitePay"),
		);
	},
});
