"""Página pública /festas/venda_convite.

Não exige login: o usuário escolhe a festa (entre as que estão com vendas
abertas) e percorre as abas Convites → Carrinho → Revisão → Convidados →
Pagamento. A lógica de preço, doação e criação de pedido é executada pelos
endpoints em `gris.api.festas.venda_convite`.
"""

from __future__ import annotations

import frappe
from frappe.utils import today

from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	context.title = "Comprar convites"
	context.show_sidebar = False
	context.no_header = True
	context.no_footer = True

	festas_raw = frappe.get_all(
		"Festa",
		filters=[
			["data_limite_vendas", "is", "set"],
			["data_limite_vendas", ">=", today()],
			["status", "=", "Em andamento"],
		],
		fields=["name", "nome_festa", "data", "aceitar_doacoes", "data_limite_vendas"],
		order_by="data asc",
	)

	festas = []
	for row in festas_raw:
		festas.append(
			{
				"name": row.name,
				"nome_festa": row.nome_festa or row.name,
				"data": row.data.isoformat() if row.data else "",
				"aceitar_doacoes": bool(row.aceitar_doacoes),
				"data_limite_vendas": row.data_limite_vendas.isoformat() if row.data_limite_vendas else "",
			}
		)

	uel_data = get_uel_cached() or {}
	context.festas = festas
	context.portal_logo = uel_data.get("logo")
	context.sem_festas = len(festas) == 0
	context.festas_select_items = [
		{"label": f["nome_festa"], "value": f["name"], "type": "item"} for f in festas
	]

	# Pré-seleção via query param ?festa=<name> (usada pelo QR "Vender na porta").
	# Só aceita se a festa estiver realmente na lista (não vaza outras festas).
	festa_param = (frappe.form_dict.get("festa") or "").strip()
	festa_pre_selecionada = ""
	if festa_param:
		nomes_validos = {f["name"] for f in festas}
		if festa_param in nomes_validos:
			festa_pre_selecionada = festa_param
	context.festa_pre_selecionada = festa_pre_selecionada
