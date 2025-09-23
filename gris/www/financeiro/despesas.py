from datetime import date, timedelta

import frappe

from gris.api.portal_access import enrich_context, user_has_access
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	# Bloqueio para usuários não autenticados
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect_to=/financeiro/despesas"
		raise frappe.Redirect
	# Recupera logo e define para sidebar
	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		if uel_data.get("nome_da_uel"):
			context.sidebar_title = f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
		else:
			context.sidebar_title = "Portal"
	else:
		context.sidebar_title = "Portal"
	context.active_link = "/financeiro/despesas"
	enrich_context(context, "/financeiro/despesas")

	# Carrega contas fixas (todas) e separa por temporárias e contínuas
	fields = [
		"name",
		"descricao",
		"valor",
		"dia_vencimento",
		"despesa_temporaria",
		"ativa",
		"data_inicio",
		"data_termino",
	]
	contas = frappe.get_all(
		"Conta Fixa",
		fields=fields,
		order_by="despesa_temporaria ASC, dia_vencimento ASC",
	)
	# Determina intervalo do mês atual para localizar pagamento
	hoje = date.today()
	primeiro_dia = hoje.replace(day=1)
	if hoje.month == 12:
		proximo_mes = hoje.replace(year=hoje.year + 1, month=1, day=1)
	else:
		proximo_mes = hoje.replace(month=hoje.month + 1, day=1)
	ultimo_dia = proximo_mes - timedelta(days=1)

	continuas = []
	temporarias = []
	for c in contas:
		status_pagamento = None
		pagamento = frappe.db.get_value(
			"Pagamento Conta Fixa",
			{
				"conta": c.name,
				"mes_referencia": ["between", [primeiro_dia, ultimo_dia]],
			},
			"status",
		)
		if pagamento:
			status_pagamento = pagamento
		item = {
			"name": c.name,
			"descricao": c.descricao,
			"valor": c.valor,
			"dia_vencimento": c.dia_vencimento,
			"status": status_pagamento or "Em Aberto",
			"ativa": bool(getattr(c, "ativa", 0)),
			"despesa_temporaria": bool(getattr(c, "despesa_temporaria", 0)),
			"data_inicio": c.data_inicio,
			"data_termino": c.data_termino,
		}
		# Regra de filtro: mostrar se ativa OU status diferente de Pago
		if not item["ativa"] and item["status"] == "Pago":
			continue
		if c.despesa_temporaria:
			temporarias.append(item)
		else:
			continuas.append(item)

	context.contas_continuas = continuas
	context.contas_temporarias = temporarias
	# Permissão de edição
	roles = frappe.get_roles()
	context.can_edit_financeiro = "Gestor Financeiro" in roles
	return context
