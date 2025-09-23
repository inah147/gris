from datetime import date, timedelta

import frappe

from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	# Param name (docname da Conta Fixa)
	conta_name = frappe.form_dict.get("name") or frappe.form_dict.get("id")
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect_to=/financeiro/despesas"
		raise frappe.Redirect
	enrich_context(context, "/financeiro/despesas")
	context.active_link = "/financeiro/despesas"

	if not conta_name:
		frappe.throw("Conta não informada")

	doc = frappe.get_doc("Conta Fixa", conta_name)

	# Pagamento mês atual (status)
	hoje = date.today()
	primeiro_dia = hoje.replace(day=1)
	if hoje.month == 12:
		proximo_mes = hoje.replace(year=hoje.year + 1, month=1, day=1)
	else:
		proximo_mes = hoje.replace(month=hoje.month + 1, day=1)
	ultimo_dia = proximo_mes - timedelta(days=1)

	status_pagamento = (
		frappe.db.get_value(
			"Pagamento Conta Fixa",
			{
				"conta": doc.name,
				"mes_referencia": ["between", [primeiro_dia, ultimo_dia]],
			},
			"status",
		)
		or "Em Aberto"
	)

	context.conta = {
		"name": doc.name,
		"descricao": doc.descricao,
		"valor": doc.valor,
		"dia_vencimento": doc.dia_vencimento,
		"ativa": bool(doc.ativa),
		"despesa_temporaria": bool(doc.despesa_temporaria),
		"data_inicio": doc.data_inicio,
		"data_termino": doc.data_termino,
		"status": status_pagamento,
	}

	# Sidebar branding
	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		if uel_data.get("nome_da_uel"):
			context.sidebar_title = f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
		else:
			context.sidebar_title = "Portal"
	else:
		context.sidebar_title = "Portal"

	return context
