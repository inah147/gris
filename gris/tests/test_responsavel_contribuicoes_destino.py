"""Troca de quem recebe a cobrança na área do responsável.

O responsável via na tela do beneficiário que havia dois telefones cadastrados,
mas não tinha como dizer qual deles a contribuição mensal devia cobrar. A escolha
passa a ser dele também, e não só do gestor — a troca vale para as próximas
cobranças.
"""

import hashlib

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.website.serve import get_response_content

from gris.www.responsavel import contribuicoes

CPF_MAE = "99000000301"
CPF_PAI = "99000000302"
CPF_FILHO = "99000000303"
TELEFONE_MAE = "+5511900000301"
TELEFONE_PAI = "+5511900000302"
LOGIN_MAE = "mae.contribuicoes@exemplo.org"


def _nome_por_cpf(cpf: str) -> str:
	"""Associado e Responsavel são nomeados pelo md5 do CPF."""
	return hashlib.md5(cpf.encode("utf-8")).hexdigest()


class TestDestinoNaAreaDoResponsavel(FrappeTestCase):
	def setUp(self):
		self.mae = self._criar_responsavel(CPF_MAE, "Mãe da Área", TELEFONE_MAE, LOGIN_MAE)
		self.pai = self._criar_responsavel(CPF_PAI, "Pai da Área", TELEFONE_PAI, "")
		self.filho = self._criar_beneficiario()
		self._criar_vinculo(self.mae, primeiro=True)
		self._criar_vinculo(self.pai, primeiro=False)
		frappe.db.set_value("Associado", self.filho, "telefone_cobranca", TELEFONE_MAE)

	def tearDown(self):
		frappe.set_user("Administrator")

	def _criar_responsavel(self, cpf: str, nome: str, celular: str, email: str) -> str:
		registro = _nome_por_cpf(cpf)
		if frappe.db.exists("Responsavel", registro):
			return registro
		frappe.get_doc(
			{
				"doctype": "Responsavel",
				"cpf": cpf,
				"nome_completo": nome,
				"celular": celular,
				"email": email,
			}
		).insert(ignore_permissions=True)
		return registro

	def _criar_beneficiario(self) -> str:
		registro = _nome_por_cpf(CPF_FILHO)
		if frappe.db.exists("Associado", registro):
			return registro
		frappe.get_doc(
			{
				"doctype": "Associado",
				"cpf": CPF_FILHO,
				"nome_completo": "Filho da Área",
				"data_de_nascimento": "2015-01-01",
				"categoria": "Beneficiário",
				"status_no_grupo": "Ativo",
				"status_cobranca": "Ativo",
				"valor_contribuicao": 60.0,
				"inicio_do_pagamento": "2026-01-01",
			}
		).insert(ignore_permissions=True)
		return registro

	def _criar_vinculo(self, responsavel: str, primeiro: bool) -> None:
		if frappe.db.exists(
			"Responsavel Vinculo",
			{"responsavel": responsavel, "beneficiario_associado": self.filho},
		):
			return
		frappe.get_doc(
			{
				"doctype": "Responsavel Vinculo",
				"responsavel": responsavel,
				"beneficiario_associado": self.filho,
				"primeiro_responsavel": 1 if primeiro else 0,
			}
		).insert(ignore_permissions=True)

	def _como_mae(self):
		usuario = self._garantir_usuario()
		frappe.set_user(usuario)

	def _garantir_usuario(self) -> str:
		if not frappe.db.exists("User", LOGIN_MAE):
			doc = frappe.get_doc(
				{
					"doctype": "User",
					"email": LOGIN_MAE,
					"first_name": "Mãe",
					"send_welcome_email": 0,
				}
			)
			doc.insert(ignore_permissions=True)
		usuario = frappe.get_doc("User", LOGIN_MAE)
		if not frappe.db.exists("Role", "Responsavel"):
			frappe.get_doc({"doctype": "Role", "role_name": "Responsavel"}).insert(ignore_permissions=True)
		if "Responsavel" not in {linha.role for linha in usuario.roles}:
			usuario.add_roles("Responsavel")
		return LOGIN_MAE

	def test_contexto_diz_quem_recebe_a_cobranca_de_cada_beneficiario(self):
		self._como_mae()
		contexto = frappe._dict()
		frappe.local.form_dict = frappe._dict()
		contribuicoes.get_context(contexto)

		destino = contexto.beneficiarios[0]["destino_cobranca"]
		self.assertEqual(destino["destinatario"]["telefone"], TELEFONE_MAE)
		self.assertEqual({r["id"] for r in destino["responsaveis"]}, {self.mae, self.pai})

	def test_pagina_oferece_o_outro_responsavel_para_receber(self):
		self._como_mae()
		frappe.local.form_dict = frappe._dict()
		conteudo = get_response_content("/responsavel/contribuicoes")

		self.assertIn("A cobrança deste beneficiário vai para", conteudo)
		self.assertIn(f'data-destinatario="{self.pai}"', conteudo)
		# Quem já recebe não aparece como opção de troca.
		self.assertNotIn(f'data-destinatario="{self.mae}"', conteudo)
