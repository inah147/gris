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
		frappe.db.exists("Pagamento Contribuicao Mensal", {"associado": associado, "mes_de_referencia": MES})
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


class TestAcrescimoAutomatico(FrappeTestCase):
	def setUp(self):
		frappe.db.set_single_value(
			"Configuracoes Contribuicao Mensal",
			{
				"valor_base": 60,
				"valor_atraso": 70,
				"dia_vencimento": 10,
				"acrescimo_automatico_desde": "2026-09-01",
			},
		)
		cpf = "99000000411"
		existente = hashlib.md5(cpf.encode("utf-8")).hexdigest()
		if frappe.db.exists("Associado", existente):
			self.associado = existente
		else:
			self.associado = _criar_associado(cpf, None, tipo_registro="Definitivo")
		for nome in frappe.get_all(
			"Pagamento Contribuicao Mensal", filters={"associado": self.associado}, pluck="name"
		):
			frappe.delete_doc("Pagamento Contribuicao Mensal", nome, force=True, ignore_permissions=True)

	def _pagamento(self, mes: str, valor: float = 60.0, status: str = "Em Aberto") -> str:
		doc = frappe.get_doc(
			{
				"doctype": "Pagamento Contribuicao Mensal",
				"associado": self.associado,
				"mes_de_referencia": f"{mes}-01",
				"status": status,
				"valor": valor,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def _rodar(self, hoje: str = "2026-10-14") -> None:
		monthly_payments.atualizar_status_pagamentos(frappe.utils.getdate(hoje))

	def test_transicao_aplica_o_acrescimo_uma_vez(self):
		nome = self._pagamento("2026-10")
		self._rodar()
		self._rodar()
		doc = frappe.get_doc("Pagamento Contribuicao Mensal", nome)
		self.assertEqual(doc.status, "Atrasado")
		self.assertEqual(doc.atrasou, 1)
		self.assertEqual(doc.valor, 70)
		self.assertEqual(doc.acrescimo_atraso, 10)

	def test_dentro_do_prazo_nao_muda(self):
		nome = self._pagamento("2026-10")
		self._rodar("2026-10-09")
		self.assertEqual(frappe.db.get_value("Pagamento Contribuicao Mensal", nome, "status"), "Em Aberto")

	def test_mes_anterior_a_data_configurada_nao_recebe(self):
		nome = self._pagamento("2026-08")
		self._rodar()
		doc = frappe.get_doc("Pagamento Contribuicao Mensal", nome)
		self.assertEqual(doc.status, "Atrasado")
		self.assertEqual(doc.valor, 60)
		self.assertEqual(doc.acrescimo_atraso, 0)

	def test_sem_data_configurada_nao_ha_acrescimo(self):
		frappe.db.set_single_value("Configuracoes Contribuicao Mensal", "acrescimo_automatico_desde", "")
		nome = self._pagamento("2026-10")
		self._rodar()
		self.assertEqual(frappe.db.get_value("Pagamento Contribuicao Mensal", nome, "valor"), 60)

	def test_valor_proprio_recebe_o_mesmo_acrescimo(self):
		nome = self._pagamento("2026-10", valor=45)
		self._rodar()
		self.assertEqual(frappe.db.get_value("Pagamento Contribuicao Mensal", nome, "valor"), 55)

	def test_mes_antigo_em_aberto_e_alcancado(self):
		nome = self._pagamento("2026-09")
		self._rodar()
		doc = frappe.get_doc("Pagamento Contribuicao Mensal", nome)
		self.assertEqual((doc.status, doc.valor), ("Atrasado", 70))
