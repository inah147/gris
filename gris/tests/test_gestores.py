# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Testes da resolução de destinatários com papel de gestor de associados."""

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.utils import gestores


class TestBuscarDestinatariosGestores(FrappeTestCase):
	def test_papel_configurado_existe_no_sistema(self):
		"""Guarda contra o modo de falha silencioso: papel inexistente devolve lista vazia.

		O filtro já ficou no singular ("Gestor de Associado") enquanto a fixture criava o
		plural — ninguém recebia aviso nenhum e nada quebrava. Este teste falha na hora.
		"""
		self.assertTrue(
			frappe.db.exists("Role", gestores.ROLE_GESTOR_DE_ASSOCIADOS),
			f"O papel {gestores.ROLE_GESTOR_DE_ASSOCIADOS!r} não existe: "
			"buscar_destinatarios_gestores() devolveria sempre uma lista vazia.",
		)

	def _executar(self, *, atribuicoes, usuarios, associados=None):
		originais = {"get_all": gestores.frappe.get_all}

		def _fake_get_all(doctype, *_args, **kwargs):
			if doctype == "Has Role":
				self.filtros_has_role = kwargs.get("filters", {})
				return [frappe._dict(row) for row in atribuicoes]
			if doctype == "User":
				return [frappe._dict(row) for row in usuarios]
			if doctype == "Associado":
				return [frappe._dict(row) for row in (associados or [])]
			return []

		try:
			gestores.frappe.get_all = _fake_get_all
			return gestores.buscar_destinatarios_gestores()
		finally:
			gestores.frappe.get_all = originais["get_all"]

	def test_consulta_usa_o_papel_no_plural(self):
		self._executar(atribuicoes=[], usuarios=[])
		self.assertEqual(self.filtros_has_role["role"], "Gestor de Associados")
		self.assertEqual(self.filtros_has_role["parenttype"], "User")

	def test_usa_mobile_no_do_usuario(self):
		destinatarios = self._executar(
			atribuicoes=[{"parent": "gestor@escoteiros.org.br"}],
			usuarios=[
				{
					"name": "gestor@escoteiros.org.br",
					"full_name": "Ana Gestora",
					"mobile_no": "+5511999991111",
				}
			],
		)

		self.assertEqual(destinatarios, [{"nome": "Ana Gestora", "telefone": "+5511999991111"}])

	def test_fallback_para_o_telefone_do_associado_pelo_id_escoteiros(self):
		destinatarios = self._executar(
			atribuicoes=[{"parent": "gestor@escoteiros.org.br"}],
			usuarios=[{"name": "gestor@escoteiros.org.br", "full_name": "Ana Gestora", "mobile_no": ""}],
			associados=[{"id_escoteiros": "gestor@escoteiros.org.br", "telefone": "+5511988882222"}],
		)

		self.assertEqual(destinatarios, [{"nome": "Ana Gestora", "telefone": "+5511988882222"}])

	def test_usuario_sem_telefone_algum_fica_de_fora(self):
		destinatarios = self._executar(
			atribuicoes=[{"parent": "gestor@escoteiros.org.br"}],
			usuarios=[{"name": "gestor@escoteiros.org.br", "full_name": "Ana Gestora", "mobile_no": ""}],
			associados=[],
		)

		self.assertEqual(destinatarios, [])
