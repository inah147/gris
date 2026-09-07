# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe

from gris.api.sugestoes.constantes import PRIORIDADE_PADRAO, PRIORIDADES, peso_prioridade


def execute():
	"""Dá prioridade às solicitações abertas antes de o campo existir.

	O quadro passou a ordenar por ``prioridade_peso`` (ver ``CARD_ORDER_BY`` em
	``gris.api.sugestoes.portal``). Um registro antigo com o campo em branco
	ficaria com peso 0 — o mesmo de "Urgente" — e todo o passivo apareceria no
	topo da coluna, que é exatamente o contrário do que o campo serve.

	Também reescreve o peso de quem já tem prioridade: ele é derivado da posição
	do rótulo em ``PRIORIDADES``, então inserir uma urgência nova no meio da lista
	desatualiza os pesos gravados.
	"""
	if not frappe.db.table_exists("Sugestao ou Problema"):
		return

	if not frappe.db.has_column("Sugestao ou Problema", "prioridade"):
		return

	tabela = frappe.qb.DocType("Sugestao ou Problema")

	# Sem prioridade definida: entra no meio da fila, como toda submissão nova.
	frappe.qb.update(tabela).set(tabela.prioridade, PRIORIDADE_PADRAO).where(
		tabela.prioridade.isnull() | (tabela.prioridade == "")
	).run()

	for prioridade in PRIORIDADES:
		frappe.qb.update(tabela).set(tabela.prioridade_peso, peso_prioridade(prioridade)).where(
			tabela.prioridade == prioridade
		).run()

	frappe.db.commit()
