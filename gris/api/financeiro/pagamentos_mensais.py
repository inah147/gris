import datetime

import frappe


def _first_day_of_month(date: datetime.date | None = None) -> datetime.date:
	date = date or datetime.date.today()
	return datetime.date(date.year, date.month, 1)


@frappe.whitelist()
def gerar_pagamentos_mensais():
	"""Cria registros 'Em Aberto' de Pagamento Contribuicao Mensal para todos os Associados ativos
	que ainda não possuem linha para o mês atual. Valor = valor_contribuicao do Associado.
	Idempotente por mês.
	"""
	mes_ref = _first_day_of_month()
	mes_ref_str = mes_ref.strftime("%Y-%m-%d")

	associados = frappe.get_all(
		"Associado",
		filters={"status_no_grupo": "Ativo", "categoria": "Beneficiário"},
		fields=["name", "valor_contribuicao"],
	)
	if not associados:
		return 0

	existentes = frappe.get_all(
		"Pagamento Contribuicao Mensal",
		filters={"mes_de_referencia": mes_ref_str},
		pluck="associado",
	)
	existentes_set = set(existentes)

	created = 0
	for a in associados:
		if a.name in existentes_set:
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Pagamento Contribuicao Mensal",
				"associado": a.name,
				"status": "Em Aberto",
				"mes_de_referencia": mes_ref_str,
				"valor": a.valor_contribuicao or 0,
			}
		)
		doc.insert()
		created += 1

	frappe.logger("pagamento_contribuicao_mensal").info(
		{
			"evento": "gerar_pagamentos_mensais",
			"mes_referencia": mes_ref_str,
			"criadas": created,
		}
	)
	return created
