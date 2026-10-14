import frappe

_CAMPOS_VALOR = ("cotacao_escolhida_valor", "valor_total_compra")
# Cenários de item constante (sem produtos vinculados): passaram a ser a própria
# quantidade final em vez de ⌈final ÷ pacote⌉.
_CAMPOS_CENARIOS = (
	"quantidade_compra",
	*(
		f"{campo}_{chave}"
		for chave in ("min", "intermediario", "max")
		for campo in ("qtd_sugerida", "valor_total", "qtd_sobra_individual", "valor_sobra")
	),
)


def execute():
	"""Recalcula as compras gravadas com a regra "quantidade final = nº de cotações".

	Entre 15/08 e 14/10/2026 o valor total de compra era ⌈final ÷ pacote⌉ x valor
	(lia a quantidade final na unidade de medida), e os cenários de itens sem
	produtos vinculados seguiam a mesma leitura. Só os campos cuja fórmula mudou
	são regravados, sem mexer em `modified`: os cenários de itens usados em
	produtos ficam como estão. Depois cada festa afetada tem orçamento por área e
	lista de compras refeitos.

	Itens "varia com o público" sem produtos guardavam na quantidade final o
	consumo por pessoa; ela vira a quantidade sugerida (nº de cotações do cenário
	ativo) que já estava gravada.
	"""
	if not frappe.db.table_exists("Compra Festa"):
		return

	festas = set()
	for nome in frappe.get_all("Compra Festa", filters={"previsto": 1}, pluck="name"):
		try:
			doc = frappe.get_doc("Compra Festa", nome)
			campos = list(_CAMPOS_VALOR)
			if not doc.usado_em_produtos:
				if doc.varia_com_publico and doc.quantidade_compra:
					doc.quantidade_compra_final = doc.quantidade_compra
					campos.append("quantidade_compra_final")
				doc._calcular_cenarios()
				doc._calcular_quantidade_compra()
				campos.extend(_CAMPOS_CENARIOS)
			doc._calcular_valor_total()
		except Exception:
			frappe.log_error(
				title=f"Patch: falha ao recalcular Compra Festa {nome}",
				message=frappe.get_traceback(),
			)
			continue
		valores = {campo: doc.get(campo) for campo in campos}
		frappe.db.set_value("Compra Festa", nome, valores, update_modified=False)
		if doc.festa:
			festas.add(doc.festa)

	for festa in sorted(festas):
		try:
			_reagregar_festa(festa)
		except Exception:
			frappe.log_error(
				title=f"Patch: falha ao reagregar Festa {festa}",
				message=frappe.get_traceback(),
			)


def _reagregar_festa(nome: str) -> None:
	"""Refaz orçamento por área, totais e lista de compras sem `save()`.

	Festas antigas podem reprovar validações sem relação com o orçamento (ex.:
	data limite de vendas depois da festa), então só os cálculos são rodados.
	"""
	festa = frappe.get_doc("Festa", nome)
	festa._sincronizar_receitas_e_despesas()
	festa._calcular_totais_financeiros()
	festa._gerar_lista_de_compras()
	festa.db_update()
	for campo in ("receitas_por_area", "despesas_por_area", "lista_compras"):
		festa.update_child_table(campo)
