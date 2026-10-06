import frappe

DOCTYPE = "Drives Compartilhados Workspace"


def execute():
	"""Troca o acesso padrão dos adultos voluntários de Colaborador para Administrador de conteúdo.

	O novo ``default`` do campo só vale para drive cadastrado daqui em diante; os já
	existentes guardam ``writer`` e continuariam concedendo Colaborador. Quem estava em
	``reader`` escolheu restringir de propósito e fica como está.

	A sincronização diária promove as permissões já concedidas no Google.
	"""
	if not frappe.db.exists("DocType", DOCTYPE):
		return

	tabela = frappe.qb.DocType(DOCTYPE)
	(
		frappe.qb.update(tabela)
		.set(tabela.permissao_padrao_adulto_voluntario, "fileOrganizer")
		.where(tabela.permissao_padrao_adulto_voluntario == "writer")
	).run()
