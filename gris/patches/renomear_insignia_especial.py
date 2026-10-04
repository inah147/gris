import frappe

VALOR_ANTIGO = "Insígnia Especial"
VALOR_NOVO = "Insígnia de Interesse Especial"
# O DocType foi renomeado de "Insignia ou Distintivo" em renomear_insignias_para_compras,
# que roda antes (pre_model_sync).
DOCTYPE = "Item de Catalogo de Compras"


def execute():
	"""Normaliza o tipo dos itens do catálogo já cadastrados com a grafia antiga.

	O Select do campo ``tipo`` passou a usar "Insígnia de Interesse Especial" no lugar
	de "Insígnia Especial", que não descrevia bem a categoria. Registros já gravados com
	o valor antigo ficariam fora das opções do Select — sumiriam dos filtros do portal e
	qualquer novo save do documento falharia na validação.
	"""
	if not frappe.db.table_exists(DOCTYPE) or not frappe.db.has_column(DOCTYPE, "tipo"):
		return

	tabela = frappe.qb.DocType(DOCTYPE)
	(frappe.qb.update(tabela).set(tabela.tipo, VALOR_NOVO).where(tabela.tipo == VALOR_ANTIGO)).run()

	frappe.db.commit()
