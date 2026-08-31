import frappe

VALOR_ANTIGO = "Feminínio"
VALOR_NOVO = "Feminino"
DOCTYPES = ("Novo Associado", "Responsavel")


def execute():
	"""Corrige a grafia da opção de sexo em ``Novo Associado`` e ``Responsavel``.

	Os dois DocTypes tinham ``Feminínio`` como opção do campo ``sexo``, enquanto ``Associado``
	sempre usou ``Feminino``. Com o schema corrigido, os registros já gravados com a grafia
	antiga ficariam fora da lista de opções — o valor sumiria dos selects do portal e qualquer
	novo save do documento falharia na validação de Select. Este patch normaliza os dados
	existentes para a grafia correta.
	"""
	for doctype in DOCTYPES:
		if not frappe.db.table_exists(doctype) or not frappe.db.has_column(doctype, "sexo"):
			continue

		frappe.db.sql(
			f"UPDATE `tab{doctype}` SET `sexo` = %(novo)s WHERE `sexo` = %(antigo)s",
			{"novo": VALOR_NOVO, "antigo": VALOR_ANTIGO},
		)

	frappe.db.commit()
