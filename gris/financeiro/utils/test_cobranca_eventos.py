# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

from types import SimpleNamespace
from unittest import TestCase

from gris.financeiro.utils.cobranca_eventos import status_mudou_para


class _FakeDoc:
	def __init__(self, status: str, old_status: str | None = None):
		self.status = status
		self._old = SimpleNamespace(status=old_status) if old_status is not None else None

	def get_doc_before_save(self):
		return self._old


class TestStatusMudouPara(TestCase):
	def test_transicao_valida(self):
		self.assertTrue(status_mudou_para(_FakeDoc("Pago", "Pendente"), "Pago"))

	def test_sem_doc_antes_e_status_atual_target_retorna_true(self):
		self.assertTrue(status_mudou_para(_FakeDoc("Pago"), "Pago"))

	def test_status_atual_diferente_retorna_false(self):
		self.assertFalse(status_mudou_para(_FakeDoc("Pendente", "Pendente"), "Pago"))

	def test_status_ja_era_target_retorna_false(self):
		self.assertFalse(status_mudou_para(_FakeDoc("Pago", "Pago"), "Pago"))
