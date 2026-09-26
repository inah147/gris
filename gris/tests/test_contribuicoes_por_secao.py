"""Recorte da contribuição mensal por seção: cada chefe vê só os próprios beneficiários.

O chefe de seção recebe a role "Visualizador Contribuição Mensal da Seção" (pelo
Role Profile "Chefe de Seção") e o recorte vem do cadastro: a `secao` (ou, na
falta, o `ramo`) do beneficiário casada com a do Associado do chefe, pela mesma
regra de `gris.utils.chefes`.
"""

import datetime
import hashlib

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.financeiro import pagamentos_contribuicao as servico
from gris.api.financeiro.cobranca_contribuicao_automatica import resumo_cobrancas_do_mes

SECAO = "Alcateia Recorte Teste"
OUTRA_SECAO = "Tropa Recorte Teste"
EMAIL_CHEFE = "chefe.recorte.secao@example.com"
EMAIL_ESCOTISTA = "escotista.recorte.secao@example.com"


def _nome_por_cpf(cpf: str) -> str:
	return hashlib.md5(cpf.encode("utf-8")).hexdigest()


def _criar_associado(cpf: str, **campos) -> str:
	nome = _nome_por_cpf(cpf)
	if frappe.db.exists("Associado", nome):
		return nome
	doc = frappe.get_doc(
		{
			"doctype": "Associado",
			"cpf": cpf,
			"nome_completo": f"Associado Recorte {cpf}",
			"data_de_nascimento": "2015-01-01",
			"categoria": "Beneficiário",
			"status_no_grupo": "Ativo",
			"status_cobranca": "Ativo",
			"valor_contribuicao": 60.0,
			**campos,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _criar_usuario(email: str, roles: list[str]) -> None:
	for role in roles:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role}).insert(ignore_permissions=True)
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "Recorte", "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	usuario = frappe.get_doc("User", email)
	usuario.add_roles(*roles)


class TestRecorteDaContribuicaoPorSecao(FrappeTestCase):
	def setUp(self):
		self.usuario_original = frappe.session.user
		self.jovem_da_secao = _criar_associado("99000000401", secao=SECAO, ramo="Lobinho")
		self.jovem_de_outra = _criar_associado("99000000402", secao=OUTRA_SECAO, ramo="Escoteiro")
		self.chefe = _criar_associado(
			"99000000403",
			categoria="Escotista",
			funcao="Chefe de Seção",
			secao=SECAO,
			ramo="Lobinho",
			data_de_nascimento="1990-01-01",
			id_escoteiros=EMAIL_CHEFE,
		)
		_criar_associado(
			"99000000404",
			categoria="Escotista",
			funcao="Assistente",
			secao=SECAO,
			ramo="Lobinho",
			data_de_nascimento="1990-01-01",
			id_escoteiros=EMAIL_ESCOTISTA,
		)
		_criar_usuario(EMAIL_CHEFE, [servico.ROLE_VISUALIZADOR_SECAO])
		_criar_usuario(EMAIL_ESCOTISTA, [servico.ROLE_VISUALIZADOR_SECAO])

	def tearDown(self):
		frappe.set_user(self.usuario_original)

	def test_chefe_ve_so_os_beneficiarios_da_propria_secao(self):
		frappe.set_user(EMAIL_CHEFE)
		visiveis = servico.associados_visiveis()
		self.assertIn(self.jovem_da_secao, visiveis)
		self.assertNotIn(self.jovem_de_outra, visiveis)

		dados = servico.get_apuracao(3)["dados"]
		ids = {a["id"] for a in dados["associados"]}
		self.assertIn(self.jovem_da_secao, ids)
		self.assertNotIn(self.jovem_de_outra, ids)
		self.assertEqual(dados["nao_vinculadas"], [])
		self.assertEqual(dados["totais"]["contribuintes"], len(ids))

	def test_chefe_nao_consulta_extrato_de_outra_secao(self):
		frappe.set_user(EMAIL_CHEFE)
		self.assertTrue(servico.get_extrato_do_associado(self.jovem_da_secao, 3)["success"])
		with self.assertRaises(frappe.PermissionError):
			servico.get_extrato_do_associado(self.jovem_de_outra, 3)

	def test_role_sem_funcao_de_chefe_nao_ve_ninguem(self):
		frappe.set_user(EMAIL_ESCOTISTA)
		self.assertEqual(servico.associados_visiveis(), set())
		self.assertEqual(servico.get_apuracao(3)["dados"]["associados"], [])

	def test_visao_completa_nao_tem_recorte(self):
		_criar_usuario(EMAIL_CHEFE, [servico.ROLE_VISUALIZADOR])
		frappe.set_user(EMAIL_CHEFE)
		try:
			self.assertIsNone(servico.associados_visiveis())
		finally:
			frappe.set_user(self.usuario_original)
			frappe.get_doc("User", EMAIL_CHEFE).remove_roles(servico.ROLE_VISUALIZADOR)

	def test_apuracao_antiga_recusa_quem_so_tem_a_role_da_secao(self):
		from gris.api.financeiro import contribuicoes as apuracao_antiga

		frappe.set_user(EMAIL_CHEFE)
		with self.assertRaises(frappe.PermissionError):
			apuracao_antiga.get_apuracao(3)

	def test_cobrancas_do_mes_respeitam_o_recorte(self):
		vazio = resumo_cobrancas_do_mes(datetime.date(2026, 3, 22), associados=set())
		self.assertEqual(vazio["cobrancas"], [])
		self.assertEqual(vazio["totais"]["emitidas"], 0)
