"""Geração mensal da contribuição respeita a carência de registro."""

import datetime
import hashlib
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.financeiro import monthly_payments

MES = datetime.date(2026, 10, 1)


def _criar_associado(cpf: str, ingresso: str | None, **campos) -> str:
	doc = frappe.get_doc(
		{
			"doctype": "Associado",
			"cpf": cpf,
			"nome_completo": "Beneficiário Carência",
			"data_de_nascimento": "2015-01-01",
			"categoria": "Beneficiário",
			"status_no_grupo": "Ativo",
			"valor_contribuicao": 60.0,
			**campos,
		}
	)
	if ingresso:
		doc.append("historico_no_grupo", {"data_de_ingresso": ingresso})
	doc.insert(ignore_permissions=True)
	return doc.name


def _gerado(associado: str) -> bool:
	return bool(
		frappe.db.exists(
			"Pagamento Contribuicao Mensal", {"associado": associado, "mes_de_referencia": MES}
		)
	)


class TestGeracaoMensalCarencia(FrappeTestCase):
	def setUp(self):
		frappe.db.set_single_value(
			"Configuracoes Contribuicao Mensal",
			{"meses_carencia_provisorio": 2, "meses_carencia_definitivo": 1},
		)
		patcher = mock.patch.object(monthly_payments, "_first_day_of_month", return_value=MES)
		patcher.start()
		self.addCleanup(patcher.stop)

	def _gerar(self) -> None:
		monthly_payments.generate_monthly_payments()

	def test_provisorio_dentro_da_carencia_nao_gera(self):
		# Ingresso em agosto + 2 meses = início em outubro; setembro ainda é carência.
		dentro = _criar_associado("99000000401", "2026-09-15", tipo_registro="Provisório")
		fora = _criar_associado("99000000402", "2026-08-15", tipo_registro="Provisório")
		self._gerar()
		self.assertFalse(_gerado(dentro))
		self.assertTrue(_gerado(fora))

	def test_definitivo_dentro_e_fora_da_carencia(self):
		dentro = _criar_associado("99000000403", "2026-10-05", tipo_registro="Definitivo")
		fora = _criar_associado("99000000404", "2026-09-05", tipo_registro="Definitivo")
		self._gerar()
		self.assertFalse(_gerado(dentro))
		self.assertTrue(_gerado(fora))

	def test_inicio_manual_prevalece(self):
		manual_antes = _criar_associado(
			"99000000405", "2026-10-05", tipo_registro="Definitivo", inicio_do_pagamento="2026-10-01"
		)
		manual_depois = _criar_associado(
			"99000000406", "2025-01-05", tipo_registro="Definitivo", inicio_do_pagamento="2026-11-01"
		)
		self._gerar()
		self.assertTrue(_gerado(manual_antes))
		self.assertFalse(_gerado(manual_depois))

	def test_sem_ingresso_continua_gerando(self):
		associado = _criar_associado("99000000407", None, tipo_registro="Definitivo")
		self._gerar()
		self.assertTrue(_gerado(associado))
