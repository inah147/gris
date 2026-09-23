"""Responsáveis na ficha do associado (`/associados/detalhe`) e no MCP.

Os campos do segundo responsável sempre existiram no cadastro; o que faltava era
a tela mostrá-los do mesmo jeito que a tela de registro de novo associado — um
card por pessoa — e o telefone ser preenchido com máscara, em vez de um campo de
texto solto. Estes testes cobrem os dois lados: o contexto que monta os cards e a
lista de responsáveis que o Claude lê para comparar cadastros.
"""

import hashlib

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.mcp.associados import obter_associado
from gris.www.associados import detalhe

CPF_BENEFICIARIO = "99000000201"


def _nome_por_cpf(cpf: str) -> str:
	"""Associado é nomeado pelo md5 do CPF, que também é gravado hasheado."""
	return hashlib.md5(cpf.encode("utf-8")).hexdigest()


def _criar_beneficiario() -> str:
	nome = _nome_por_cpf(CPF_BENEFICIARIO)
	campos = {
		"nome_responsavel_1": "Mãe do Beneficiário",
		# Guardado sem DDI de propósito: é assim que cadastros antigos ficaram, e
		# o controle com máscara precisa reconhecê-los mesmo assim.
		"telefone_responsavel_1": "11999990201",
		"email_responsavel_1": "mae@exemplo.com",
		"nome_responsavel_2": "Pai do Beneficiário",
		"telefone_responsavel_2": "11999990202",
		"email_responsavel_2": "pai@exemplo.com",
	}
	# Sempre pelo documento, nunca por `db.set_value`: o controller normaliza nome
	# e telefone, e é o valor normalizado que a tela e o MCP devolvem.
	if frappe.db.exists("Associado", nome):
		doc = frappe.get_doc("Associado", nome)
		doc.update({**campos, "categoria": "Beneficiário"})
		doc.save(ignore_permissions=True)
		return nome
	frappe.get_doc(
		{
			"doctype": "Associado",
			"cpf": CPF_BENEFICIARIO,
			"nome_completo": "Beneficiário com Dois Responsáveis",
			"data_de_nascimento": "2015-01-01",
			"categoria": "Beneficiário",
			"status_no_grupo": "Ativo",
			**campos,
		}
	).insert(ignore_permissions=True)
	return nome


class TestResponsaveisNaFichaDoAssociado(FrappeTestCase):
	"""Um card por responsável, com a guarda separada e telefone com máscara."""

	def setUp(self):
		self.associado = _criar_beneficiario()

	def _contexto(self):
		frappe.local.form_dict = frappe._dict(name=self.associado)
		contexto = frappe._dict()
		detalhe.get_context(contexto)
		return contexto

	def test_ficha_monta_um_card_por_responsavel(self):
		grupos = self._contexto().grupos_responsaveis

		self.assertEqual([g["indice"] for g in grupos], [1, 2])
		self.assertEqual([g["titulo"] for g in grupos], ["1º Responsável", "2º Responsável"])
		self.assertEqual(grupos[1]["nome"], "Pai Do Beneficiário")

	def test_segundo_card_existe_mesmo_sem_segundo_responsavel(self):
		"""É por ele que se cadastra o segundo responsável de quem só tem um."""
		frappe.db.set_value(
			"Associado",
			self.associado,
			{"nome_responsavel_2": "", "telefone_responsavel_2": "", "email_responsavel_2": ""},
		)
		grupos = self._contexto().grupos_responsaveis

		self.assertEqual(len(grupos), 2)
		self.assertEqual(grupos[1]["nome"], "")
		self.assertIn("nome_responsavel_2", [c["fieldname"] for c in grupos[1]["campos"]])

	def test_cada_card_so_traz_os_campos_do_seu_responsavel(self):
		grupos = self._contexto().grupos_responsaveis

		for indice, grupo in zip((1, 2), grupos, strict=True):
			nomes = [campo["fieldname"] for campo in grupo["campos"]]
			self.assertTrue(all(nome.endswith(f"_{indice}") for nome in nomes), nomes)

	def test_guarda_fica_fora_dos_cards_por_ser_da_familia(self):
		contexto = self._contexto()

		self.assertEqual(
			[campo["fieldname"] for campo in contexto.group_guarda],
			["pais_divorciados", "tipo_guarda"],
		)
		nos_cards = [c["fieldname"] for g in contexto.grupos_responsaveis for c in g["campos"]]
		self.assertNotIn("pais_divorciados", nos_cards)
		self.assertNotIn("tipo_guarda", nos_cards)

	def test_telefone_sai_normalizado_e_marcado_para_o_campo_com_mascara(self):
		"""O componente de máscara só reconhece o país com o número em +55DDNÚMERO."""
		campos = {c["fieldname"]: c for c in self._contexto().grupos_responsaveis[0]["campos"]}

		telefone = campos["telefone_responsavel_1"]
		self.assertTrue(telefone["is_phone"])
		self.assertEqual(telefone["value"], "+5511999990201")
		self.assertFalse(campos["email_responsavel_1"]["is_phone"])

	def test_associado_que_nao_e_beneficiario_nao_ganha_cards(self):
		frappe.db.set_value("Associado", self.associado, "categoria", "Escotista")
		try:
			contexto = self._contexto()
			self.assertEqual(contexto.grupos_responsaveis, [])
			self.assertEqual(contexto.group_guarda, [])
		finally:
			frappe.db.set_value("Associado", self.associado, "categoria", "Beneficiário")


class TestResponsaveisNoMcp(FrappeTestCase):
	"""`obter_associado` devolve os responsáveis no formato de `obter_novo_associado`."""

	def setUp(self):
		self.associado = _criar_beneficiario()

	def test_lista_traz_os_dois_responsaveis_com_contato(self):
		responsaveis = obter_associado(self.associado)["responsaveis"]

		self.assertEqual([r["ordem"] for r in responsaveis], [1, 2])
		self.assertEqual(responsaveis[0]["nome_completo"], "Mãe Do Beneficiário")
		self.assertEqual(responsaveis[0]["email"], "mae@exemplo.com")
		self.assertEqual(responsaveis[1]["celular"], "+5511999990202")

	def test_responsavel_em_branco_fica_de_fora(self):
		frappe.db.set_value("Associado", self.associado, "nome_responsavel_2", "")
		responsaveis = obter_associado(self.associado)["responsaveis"]

		self.assertEqual([r["ordem"] for r in responsaveis], [1])
