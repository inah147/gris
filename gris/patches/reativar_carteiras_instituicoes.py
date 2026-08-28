import frappe


def execute():
	"""Reativa Carteiras e Instituições Financeiras desativadas por deploys anteriores.

	Os arquivos `fixtures/carteira.json` e `fixtures/instituicao_financeira.json`
	eram reimportados a cada `bench migrate` (o import de fixtures varre todos os
	`.json` da pasta, independente do hook `fixtures`). Como os snapshots não tinham
	o campo `ativa`, cada deploy zerava o campo e desativava os registros.

	Os arquivos foram removidos (correção da causa raiz). Este patch é a recuperação
	única para os registros que já ficaram com `ativa` NULL/0 por causa do bug.
	"""
	for doctype in ("Carteira", "Instituicao Financeira"):
		if not frappe.db.table_exists(doctype):
			continue
		if not frappe.db.has_column(doctype, "ativa"):
			continue
		# Interpolação segura: `doctype` vem da tupla literal acima.
		frappe.db.sql(
			f"UPDATE `tab{doctype}` SET `ativa` = 1 WHERE `ativa` IS NULL OR `ativa` = 0"
		)  # nosemgrep

	frappe.db.commit()
