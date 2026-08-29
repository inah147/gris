"""Testes da edição em lote feita direto na célula do grid do extrato.

Cobrem o registro de campos editáveis, a validação do valor recebido do
cliente e o contrato do endpoint que grava e devolve as linhas atualizadas.
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.financeiro.transactions import (
	EXTRATO_CAMPOS_EDITAVEIS,
	EXTRATO_MAX_EDICAO_LOTE,
	get_extrato_colunas,
	get_extrato_opcoes_editaveis,
	render_extrato_rows,
	update_extrato_celulas,
)

DOCTYPE = "Transacao Extrato Geral"


class TestExtratoCamposEditaveis(FrappeTestCase):
	def test_registro_cobre_os_campos_de_categorizacao(self):
		self.assertEqual(
			set(EXTRATO_CAMPOS_EDITAVEIS),
			{
				"descricao_reduzida",
				"categoria",
				"centro_de_custo",
				"ordinaria_extraordinaria",
				"transacao_revisada",
			},
		)

	def test_cada_campo_editavel_declara_um_tipo_conhecido(self):
		for campo, meta in EXTRATO_CAMPOS_EDITAVEIS.items():
			self.assertIn(meta["tipo"], ("texto", "opcoes", "booleano"), campo)
			if meta["tipo"] == "opcoes":
				# Ou vem de um doctype (Link) ou traz a lista fixa (Select).
				self.assertTrue(meta.get("doctype") or meta.get("opcoes"), campo)

	def test_campos_editaveis_existem_no_doctype(self):
		campos_do_doctype = {f.fieldname for f in frappe.get_meta(DOCTYPE).fields}
		self.assertEqual(set(EXTRATO_CAMPOS_EDITAVEIS) - campos_do_doctype, set())

	def test_opcoes_cobrem_todos_os_campos_de_selecao(self):
		opcoes = get_extrato_opcoes_editaveis()
		esperados = {c for c, m in EXTRATO_CAMPOS_EDITAVEIS.items() if m["tipo"] == "opcoes"}
		self.assertEqual(set(opcoes), esperados)
		self.assertEqual(
			opcoes["ordinaria_extraordinaria"], ["Ordinária", "Extraordinária"]
		)

	def test_grid_marca_as_celulas_editaveis(self):
		colunas = get_extrato_colunas()
		html = render_extrato_rows([{"name": "TX-0001", "descricao_reduzida": "Compra"}], colunas)
		for campo, meta in EXTRATO_CAMPOS_EDITAVEIS.items():
			self.assertIn(f'data-editavel="{meta["tipo"]}"', html, campo)
		# Coluna não editável não ganha o atributo.
		self.assertNotIn('data-col="valor" data-editavel', html)

	def test_valor_editavel_vai_escapado_para_o_atributo(self):
		html = render_extrato_rows(
			[{"name": "TX-0002", "descricao_reduzida": '"><script>alert(1)</script>'}],
			get_extrato_colunas(),
		)
		self.assertNotIn("<script>alert(1)</script>", html)
		self.assertIn("&lt;script&gt;", html)


class TestUpdateExtratoCelulas(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_guest_nao_edita(self):
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				update_extrato_celulas(json.dumps(["TX-0001"]), "categoria", "Qualquer")
		finally:
			frappe.set_user("Administrator")

	def test_campo_fora_do_registro_e_recusado(self):
		with self.assertRaises(frappe.ValidationError):
			update_extrato_celulas(json.dumps(["TX-0001"]), "valor", "10")

	def test_selecao_vazia_e_recusada(self):
		with self.assertRaises(frappe.ValidationError):
			update_extrato_celulas("[]", "categoria", "Qualquer")

	def test_json_invalido_e_tratado_como_selecao_vazia(self):
		with self.assertRaises(frappe.ValidationError):
			update_extrato_celulas("isto não é json", "categoria", "Qualquer")

	def test_lote_acima_do_teto_e_recusado(self):
		ids = [f"TX-{i:04d}" for i in range(EXTRATO_MAX_EDICAO_LOTE + 1)]
		with self.assertRaises(frappe.ValidationError):
			update_extrato_celulas(json.dumps(ids), "categoria", "Qualquer")

	def test_valor_invalido_para_campo_de_selecao_e_recusado(self):
		with self.assertRaises(frappe.ValidationError):
			update_extrato_celulas(
				json.dumps(["TX-0001"]), "ordinaria_extraordinaria", "Inexistente"
			)

	def test_link_inexistente_e_recusado(self):
		with self.assertRaises(frappe.ValidationError):
			update_extrato_celulas(
				json.dumps(["TX-0001"]), "categoria", "Categoria que não existe"
			)

	def test_transacao_inexistente_conta_como_falha_sem_quebrar(self):
		resposta = update_extrato_celulas(
			json.dumps(["TX-INEXISTENTE"]), "descricao_reduzida", "Aluguel"
		)
		self.assertEqual(resposta["updated_count"], 0)
		self.assertEqual(resposta["falhas"], 1)
		self.assertEqual(resposta["html"].strip(), "")

	def test_edicao_em_lote_grava_e_devolve_as_linhas(self):
		nomes = [
			doc.name
			for doc in frappe.get_all(DOCTYPE, fields=["name"], limit=2, order_by="creation desc")
		]
		if len(nomes) < 2:
			self.skipTest("site sem transações suficientes para o teste em lote")

		resposta = update_extrato_celulas(json.dumps(nomes), "descricao_reduzida", "Aluguel da sede")

		self.assertEqual(resposta["updated_count"], 2)
		self.assertEqual(resposta["falhas"], 0)
		for nome in nomes:
			self.assertEqual(frappe.db.get_value(DOCTYPE, nome, "descricao_reduzida"), "Aluguel da sede")
			self.assertIn(f'data-transaction-id="{nome}"', resposta["html"])
		self.assertIn("Aluguel da sede", resposta["html"])

	def test_booleano_aceita_zero_e_um(self):
		nome = frappe.db.get_value(DOCTYPE, {}, "name")
		if not nome:
			self.skipTest("site sem transações para o teste")

		update_extrato_celulas(json.dumps([nome]), "transacao_revisada", "1")
		self.assertEqual(frappe.db.get_value(DOCTYPE, nome, "transacao_revisada"), 1)

		update_extrato_celulas(json.dumps([nome]), "transacao_revisada", "0")
		self.assertEqual(frappe.db.get_value(DOCTYPE, nome, "transacao_revisada"), 0)

	def test_valor_vazio_limpa_o_campo(self):
		nome = frappe.db.get_value(DOCTYPE, {}, "name")
		if not nome:
			self.skipTest("site sem transações para o teste")

		update_extrato_celulas(json.dumps([nome]), "descricao_reduzida", "Preenchido")
		update_extrato_celulas(json.dumps([nome]), "descricao_reduzida", "")
		self.assertIn(frappe.db.get_value(DOCTYPE, nome, "descricao_reduzida"), (None, ""))
