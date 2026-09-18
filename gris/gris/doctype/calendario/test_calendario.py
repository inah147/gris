# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

"""Coerência entre os três flags de disponibilidade da atividade.

``abertura_geral`` libera o dia para todos os ramos; ``permite_visita_novos_associados``
libera só o ramo da seção daquela atividade. Como a abertura geral já libera, ela zera o
flag específico no save — senão ficaria um ``1`` escondido pelo ``depends_on`` que voltaria
a valer ao desmarcar a abertura, deixando o dia liberado sem ninguém ver por quê.
"""

from itertools import count
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

_seq = count(1)


class TestCoerenciaDosFlags(FrappeTestCase):
	def setUp(self):
		# Qualquer save de Calendario avisa o grupo de métodos no WhatsApp; aqui só interessa
		# o que foi gravado.
		patcher = patch("gris.api.calendario_notificacoes.notificar_alteracao_calendario")
		self.addCleanup(patcher.stop)
		patcher.start()

	def tearDown(self):
		# FrappeTestCase faz rollback por classe: sem isto o `id` do teste anterior vaza e
		# vira DuplicateEntryError (o campo é unique e serve de autoname).
		frappe.db.rollback()

	def _criar(self, **campos):
		doc = frappe.get_doc(
			{
				"doctype": "Calendario",
				"id": f"TST-FLAG-{next(_seq):04d}",
				"atividade": "Atividade de teste",
				"secao": "Lobinho",
				"inicio": "2026-05-02 08:00:00",
				"termino": "2026-05-02 18:00:00",
				**campos,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def test_flag_de_visitacao_nasce_desmarcado(self):
		doc = self._criar()

		self.assertFalse(doc.permite_visita_novos_associados)

	def test_flag_de_visitacao_sozinho_e_preservado(self):
		doc = self._criar(permite_visita_novos_associados=1)

		self.assertEqual(doc.permite_visita_novos_associados, 1)

	def test_abertura_geral_zera_o_flag_de_visitacao(self):
		doc = self._criar(abertura_geral=1, permite_visita_novos_associados=1)

		self.assertEqual(doc.permite_visita_novos_associados, 0)

	def test_desmarcar_a_abertura_geral_nao_reacende_o_flag(self):
		doc = self._criar(abertura_geral=1, permite_visita_novos_associados=1)

		doc.abertura_geral = 0
		doc.save(ignore_permissions=True)

		self.assertEqual(doc.permite_visita_novos_associados, 0)

	def test_sem_atividade_com_flag_de_visitacao_e_rejeitado(self):
		with self.assertRaises(frappe.ValidationError):
			self._criar(sem_atividade=1, permite_visita_novos_associados=1)

	def test_abertura_geral_forca_o_nome_da_atividade(self):
		doc = self._criar(atividade="Reunião comum", abertura_geral=1)

		self.assertEqual(doc.atividade, "Abertura Geral")

	def test_sem_atividade_com_abertura_geral_e_rejeitado(self):
		with self.assertRaises(frappe.ValidationError):
			self._criar(sem_atividade=1, abertura_geral=1)
