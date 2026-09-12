import frappe

DOCTYPE = "Sugestao ou Problema"
COLUNAS_ANTIGAS = ("Problemas reportados", "Solicitações de funcionalidades")
COLUNA_NOVA = "Refinamento"


def execute():
	"""Move para ``Refinamento`` o que estava nas duas colunas de triagem por tipo.

	O quadro de ``/sugestoes/acompanhamento`` passou a ter só colunas de andamento: as
	duas primeiras, que separavam a fila de entrada por tipo (problema ou nova
	funcionalidade), deram lugar a uma única coluna ``Refinamento``. O tipo continua no
	badge do card e no filtro da página. Sem este patch os registros já gravados ficariam
	com um status fora das opções do Select — sumiriam do quadro e qualquer novo save
	falharia na validação de status.
	"""
	if not frappe.db.table_exists(DOCTYPE) or not frappe.db.has_column(DOCTYPE, "status"):
		return

	tabela = frappe.qb.DocType(DOCTYPE)
	(
		frappe.qb.update(tabela)
		.set(tabela.status, COLUNA_NOVA)
		.where(tabela.status.isin(list(COLUNAS_ANTIGAS)))
	).run()

	frappe.db.commit()
