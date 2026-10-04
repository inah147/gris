"""Patch que leva os lembretes da contribuição aos novos padrões."""

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.patches import ajustar_lembretes_da_contribuicao as patch

DOCTYPE = "Configuracoes Contribuicao Mensal"


def _valores() -> tuple:
	return (
		frappe.db.get_single_value(DOCTYPE, "dias_lembrete_apos_vencimento", cache=False),
		frappe.db.get_single_value(DOCTYPE, "max_lembretes", cache=False),
	)


class TestPatchAjustarLembretes(FrappeTestCase):
	def test_padroes_antigos_viram_os_novos(self):
		frappe.db.set_single_value(DOCTYPE, {"dias_lembrete_apos_vencimento": 3, "max_lembretes": 2})
		patch.execute()
		self.assertEqual(_valores(), (7, 3))

	def test_ajuste_manual_nao_e_tocado(self):
		frappe.db.set_single_value(DOCTYPE, {"dias_lembrete_apos_vencimento": 3, "max_lembretes": 5})
		patch.execute()
		self.assertEqual(_valores(), (3, 5))

		frappe.db.set_single_value(DOCTYPE, {"dias_lembrete_apos_vencimento": 5, "max_lembretes": 2})
		patch.execute()
		self.assertEqual(_valores(), (5, 2))
