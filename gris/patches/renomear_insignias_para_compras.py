import frappe
from frappe.model.rename_doc import rename_doc
from frappe.model.utils.rename_field import rename_field

# O módulo de insígnias virou o módulo de Compras, com as áreas Manutenção,
# Programa Educativo e Administrativo. A ordem importa: o filho é renomeado antes
# do pai para que o `parenttype` das linhas acompanhe a troca de nome do pai.
RENOMEACOES = (
	("Insignia ou Distintivo", "Item de Catalogo de Compras", "item_de_catalogo_de_compras"),
	("Item de Solicitacao de Insignias", "Item de Solicitacao de Compra", "item_de_solicitacao_de_compra"),
	("Solicitacao de Insignias", "Solicitacao de Compra", "solicitacao_de_compra"),
)

AREA_PROGRAMA_EDUCATIVO = "Programa Educativo"
SERIE_ANTIGA = "SOL-INS-.YYYY.-"


def execute():
	"""Renomeia os DocTypes de insígnias e marca o que já existe como Programa Educativo.

	Roda antes do sync de modelos: com os nomes antigos ainda no banco, o sync criaria
	tabelas novas e vazias ao lado das antigas, e o histórico de pedidos sumiria do
	portal. Cada passo checa o estado atual, então o patch é idempotente.
	"""
	for antigo, novo, _modulo in RENOMEACOES:
		if frappe.db.exists("DocType", antigo) and not frappe.db.exists("DocType", novo):
			rename_doc("DocType", antigo, novo, force=True)

	# Carrega o schema novo já aqui: o campo `area` e o `item_catalogo` precisam
	# existir para copiar os dados antes de o sync terminar.
	for _antigo, novo, modulo in RENOMEACOES:
		if frappe.db.exists("DocType", novo):
			frappe.reload_doc("gris", "doctype", modulo)

	# A série de nomes (default/options do naming_series) fica em Property Setter, que
	# acompanha a renomeação. Sem removê-lo, pedidos novos continuariam saindo como
	# SOL-INS-… em vez da série do JSON (SOL-COMP-…). Pedidos antigos mantêm o nome.
	frappe.db.delete(
		"Property Setter",
		{
			"doc_type": "Solicitacao de Compra",
			"field_name": "naming_series",
			"property": ["in", ["default", "options"]],
			"value": SERIE_ANTIGA,
		},
	)

	filho = "Item de Solicitacao de Compra"
	if frappe.db.table_exists(filho) and frappe.db.has_column(filho, "insignia"):
		rename_field(filho, "insignia", "item_catalogo")

	for doctype in ("Item de Catalogo de Compras", "Solicitacao de Compra"):
		if not frappe.db.table_exists(doctype) or not frappe.db.has_column(doctype, "area"):
			continue
		tabela = frappe.qb.DocType(doctype)
		(
			frappe.qb.update(tabela)
			.set(tabela.area, AREA_PROGRAMA_EDUCATIVO)
			.where(tabela.area.isnull() | (tabela.area == ""))
		).run()

	# O módulo também aparece como opção nas Sugestões e Problemas.
	if frappe.db.table_exists("Sugestao ou Problema") and frappe.db.has_column(
		"Sugestao ou Problema", "modulo"
	):
		sugestao = frappe.qb.DocType("Sugestao ou Problema")
		(
			frappe.qb.update(sugestao)
			.set(sugestao.modulo, "Compras")
			.where(sugestao.modulo == "Insígnias e Distintivos")
		).run()

	frappe.db.commit()
