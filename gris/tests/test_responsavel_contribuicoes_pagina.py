"""Página de contribuições do responsável: usa a mesma apuração da tela do financeiro."""

import datetime
import hashlib
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_months

from gris.www.responsavel import contribuicoes as pagina

CPF = "99000000601"


class TestPaginaContribuicoesDoResponsavel(FrappeTestCase):
	def setUp(self):
		nome = hashlib.md5(CPF.encode("utf-8")).hexdigest()
		if not frappe.db.exists("Associado", nome):
			frappe.get_doc(
				{
					"doctype": "Associado",
					"cpf": CPF,
					"nome_completo": "Beneficiário do Responsável",
					"data_de_nascimento": "2015-01-01",
					"categoria": "Beneficiário",
					"status_no_grupo": "Ativo",
					"status_cobranca": "Ativo",
					"valor_contribuicao": 60.0,
				}
			).insert(ignore_permissions=True)
		self.associado = nome
		for pagamento in frappe.get_all(
			"Pagamento Contribuicao Mensal", filters={"associado": nome}, pluck="name"
		):
			frappe.delete_doc("Pagamento Contribuicao Mensal", pagamento, force=True, ignore_permissions=True)
		hoje = datetime.date.today().replace(day=1)
		frappe.get_doc(
			{
				"doctype": "Pagamento Contribuicao Mensal",
				"associado": nome,
				"mes_de_referencia": hoje,
				"status": "Atrasado",
				"valor": 70,
				"acrescimo_atraso": 10,
			}
		).insert(ignore_permissions=True)

	def _contexto(self) -> frappe._dict:
		contexto = frappe._dict()
		with (
			mock.patch.object(pagina, "enrich_context"),
			mock.patch.object(pagina, "user_has_access", return_value=True),
			mock.patch.object(pagina, "get_responsavel_do_usuario", return_value="R"),
			mock.patch.object(pagina, "get_beneficiarios_associados", return_value=[self.associado]),
			mock.patch.object(pagina.frappe, "session", frappe._dict(user="resp@exemplo.com")),
		):
			pagina.get_context(contexto)
		return contexto

	def test_botao_de_pagar_leva_a_pagina_publica(self):
		contexto = self._contexto()
		[beneficiario] = contexto.beneficiarios
		self.assertEqual(beneficiario["total_pendente"], 70)
		self.assertIn("/contribuicao/", beneficiario["link_pagamento"])
		self.assertNotIn("infinitepay", beneficiario["link_pagamento"].lower())
		self.assertFalse(contexto.em_dia)

	def test_meses_nao_gerados_ficam_fora_do_mes_a_mes(self):
		[beneficiario] = self._contexto().beneficiarios
		self.assertEqual(len(beneficiario["linhas_recentes"]), 1)
		self.assertEqual(beneficiario["linhas_recentes"][0]["acrescimo_atraso"], 10)

	def test_template_compila(self):
		self.assertTrue(frappe.get_template("gris/www/responsavel/contribuicoes.html"))


def _beneficiario(cpf: str, nome: str, secao: str, email: str | None = None) -> str:
	doc = frappe.get_doc(
		{
			"doctype": "Associado",
			"cpf": cpf,
			"nome_completo": nome,
			"data_de_nascimento": "2014-01-01",
			"categoria": "Beneficiário",
			"status_no_grupo": "Ativo",
			"status_cobranca": "Ativo",
			"valor_contribuicao": 60.0,
			"secao": secao,
		}
	).insert(ignore_permissions=True)
	if email:
		# Direto no banco: gravar `id_escoteiros` pelo documento dispararia a criação do usuário.
		frappe.db.set_value("Associado", doc.name, "id_escoteiros", email, update_modified=False)
	return doc.name


def _mensalidades(associado: str, situacoes: str) -> None:
	"""Uma mensalidade por letra, do mês mais antigo ao atual: P pago, A atrasado, E em aberto."""
	hoje = datetime.date.today().replace(day=1)
	for indice, letra in enumerate(situacoes):
		atrasado = letra == "A"
		frappe.get_doc(
			{
				"doctype": "Pagamento Contribuicao Mensal",
				"associado": associado,
				"mes_de_referencia": add_months(hoje, indice - len(situacoes) + 1),
				"status": {"P": "Pago", "A": "Atrasado", "E": "Em Aberto"}[letra],
				"valor": 70 if atrasado else 60,
				"acrescimo_atraso": 10 if atrasado else 0,
				"atrasou": int(atrasado),
			}
		).insert(ignore_permissions=True)


def _usuario_responsavel(email: str) -> str:
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	frappe.get_doc("User", email).add_roles("Responsavel")
	return email


class TestResponsavelComDoisFilhos(FrappeTestCase):
	"""Sem mocks na resolução: o responsável, os vínculos e a apuração vêm do banco."""

	EMAIL_MAE = "mae.dois.filhos@exemplo.com"
	EMAIL_FILHA = "filha.dois.filhos@escoteiros.org.br"

	def setUp(self):
		self.usuario_original = frappe.session.user
		self.filho = _beneficiario("99000000611", "Filho Em Dia", "Alcateia Dois Filhos")
		self.filha = _beneficiario(
			"99000000612", "Filha Em Atraso", "Tropa Dois Filhos", email=self.EMAIL_FILHA
		)
		self.outra_familia = _beneficiario("99000000613", "Jovem De Outra Familia", "Alcateia Dois Filhos")
		_mensalidades(self.filho, "PPPPPE")
		_mensalidades(self.filha, "PPPAAE")
		_mensalidades(self.outra_familia, "AAAAAA")

		mae = frappe.get_doc(
			{
				"doctype": "Responsavel",
				"nome_completo": "Mãe De Dois Filhos",
				"cpf": "99000000614",
				"email": self.EMAIL_MAE,
			}
		).insert(ignore_permissions=True)
		pai_de_outra = frappe.get_doc(
			{"doctype": "Responsavel", "nome_completo": "Pai De Outra Familia", "cpf": "99000000615"}
		).insert(ignore_permissions=True)
		for responsavel, beneficiario in (
			(mae.name, self.filho),
			(mae.name, self.filha),
			(pai_de_outra.name, self.outra_familia),
		):
			frappe.get_doc(
				{
					"doctype": "Responsavel Vinculo",
					"responsavel": responsavel,
					"beneficiario_associado": beneficiario,
				}
			).insert(ignore_permissions=True)

		_usuario_responsavel(self.EMAIL_MAE)
		_usuario_responsavel(self.EMAIL_FILHA)

	def tearDown(self):
		frappe.set_user(self.usuario_original)
		frappe.db.rollback()

	def _contexto(self, user: str) -> frappe._dict:
		contexto = frappe._dict()
		frappe.set_user(user)
		with mock.patch.object(pagina, "enrich_context"):
			pagina.get_context(contexto)
		return contexto

	def test_mae_ve_os_dois_filhos_e_mais_ninguem(self):
		contexto = self._contexto(self.EMAIL_MAE)
		por_id = {b["id"]: b for b in contexto.beneficiarios}

		self.assertEqual(set(por_id), {self.filho, self.filha})
		self.assertNotIn(self.outra_familia, por_id)
		self.assertTrue(contexto.tem_vinculo)

	def test_cada_filho_tem_a_propria_situacao_e_o_proprio_link(self):
		contexto = self._contexto(self.EMAIL_MAE)
		por_id = {b["id"]: b for b in contexto.beneficiarios}
		filho, filha = por_id[self.filho], por_id[self.filha]

		self.assertEqual(filho["meses_em_atraso"], 0)
		self.assertEqual(filho["total_pendente"], 60)
		self.assertEqual(filha["meses_em_atraso"], 2)
		self.assertEqual(filha["total_pendente"], 70 + 70 + 60)
		self.assertNotEqual(filho["link_pagamento"], filha["link_pagamento"])

		# O aviso do topo soma as duas pendências, e a família não está em dia.
		self.assertEqual(contexto.total_pendente, filho["total_pendente"] + filha["total_pendente"])
		self.assertFalse(contexto.em_dia)

	def test_filha_logada_nao_ve_o_irmao(self):
		# A conta id@escoteiros da filha tem vínculo como beneficiária, não como responsável.
		contexto = self._contexto(self.EMAIL_FILHA)
		self.assertFalse(contexto.tem_vinculo)
		self.assertEqual(contexto.beneficiarios, [])
