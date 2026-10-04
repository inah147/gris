"""Página de contribuições do responsável: usa a mesma apuração da tela do financeiro."""

import datetime
import hashlib
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

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
