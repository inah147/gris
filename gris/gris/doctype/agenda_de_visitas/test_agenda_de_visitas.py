# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

"""Regra de visita única por jovem.

Enquanto reagendar inseria uma linha nova, a antiga ficava parada na data velha e
reaparecia como visita fantasma na mensagem de sábado no grupo de chefes de seção.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase


class TestAgendadeVisitas(FrappeTestCase):
	def setUp(self):
		# O after_insert do controller manda WhatsApp; aqui só interessa a gravação.
		patcher = patch("gris.api.recepcao_notificacoes.notificar_visita_agendada")
		self.addCleanup(patcher.stop)
		patcher.start()

	def tearDown(self):
		# FrappeTestCase faz rollback por classe: sem isto o CPF do setUp vaza para o
		# próximo teste e vira DuplicateEntryError.
		frappe.db.rollback()

	def _criar_jovem(self, cpf="123.456.789-09"):
		doc = frappe.get_doc(
			{
				"doctype": "Novo Associado",
				"nome_completo": "Jovem de Teste",
				"cpf": cpf,
				"data_de_nascimento": "2016-04-14",
				"status": "Conversa Inicial",
				"ramo": "Lobinho",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def _criar_visita(self, jovem, data="2026-05-02"):
		visita = frappe.get_doc(
			{
				"doctype": "Agenda de Visitas",
				"jovem": jovem,
				"data_da_visita": data,
				"ramo": "Lobinho",
			}
		)
		visita.insert(ignore_permissions=True)
		return visita

	def test_primeira_visita_do_jovem_e_aceita(self):
		jovem = self._criar_jovem()

		visita = self._criar_visita(jovem.name)

		self.assertEqual(str(visita.data_da_visita), "2026-05-02")

	def test_segunda_visita_para_o_mesmo_jovem_e_recusada(self):
		jovem = self._criar_jovem(cpf="987.654.321-00")
		self._criar_visita(jovem.name)

		with self.assertRaises(frappe.ValidationError):
			self._criar_visita(jovem.name, data="2026-05-09")

	def test_alterar_a_data_da_propria_visita_continua_valendo(self):
		jovem = self._criar_jovem(cpf="529.982.247-25")
		visita = self._criar_visita(jovem.name)

		visita.data_da_visita = "2026-05-09"
		visita.save(ignore_permissions=True)

		self.assertEqual(str(visita.data_da_visita), "2026-05-09")

	def test_jovens_diferentes_podem_visitar_no_mesmo_dia(self):
		um = self._criar_jovem(cpf="111.444.777-35")
		outro = self._criar_jovem(cpf="123.456.789-09")

		self._criar_visita(um.name)
		visita = self._criar_visita(outro.name)

		self.assertEqual(visita.jovem, outro.name)
