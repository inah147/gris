"""Testes da apuração de contribuição mensal baseada no Pagamento Contribuicao Mensal.

A fonte de verdade voltou a ser o DocType: sem carência, valor de atraso
escalonado ou crédito retroativo — o status e o valor de cada mês são só o que
está gravado no registro. Estes testes cobrem a leitura (grade mês a mês,
apuração do período e por associado) e a escrita compartilhada por tela e MCP
(`gris.api.financeiro.monthly_payments.definir_pagamento`).
"""

import datetime
import hashlib

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.financeiro import monthly_payments, pagamentos_contribuicao as servico

CPF_BENEFICIARIO = "99000000301"


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
			"nome_completo": "Beneficiário Pagamentos",
			"data_de_nascimento": "2015-01-01",
			"categoria": "Beneficiário",
			"status_no_grupo": "Ativo",
			"status_cobranca": "Ativo",
			"valor_contribuicao": 60.0,
			"inicio_do_pagamento": "2026-01-01",
			**campos,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _criar_pagamento(associado: str, mes: str, status: str, valor: float = 60.0, **campos) -> str:
	doc = frappe.get_doc(
		{
			"doctype": "Pagamento Contribuicao Mensal",
			"associado": associado,
			"mes_de_referencia": f"{mes}-01",
			"status": status,
			"valor": valor,
			**campos,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


class TestMontarGradePagamentos(FrappeTestCase):
	def setUp(self):
		self.meses = [datetime.date(2026, 1, 1), datetime.date(2026, 2, 1), datetime.date(2026, 3, 1)]

	def test_mes_sem_registro_e_nao_gerado(self):
		grade = servico.montar_grade_pagamentos(self.meses, {})
		self.assertEqual([linha["status"] for linha in grade["linhas"]], [servico.STATUS_NAO_GERADO] * 3)
		self.assertEqual(grade["situacao"], servico.STATUS_NAO_GERADO)
		self.assertEqual(grade["total_esperado"], 0.0)

	def test_situacao_e_o_pior_status_presente(self):
		pagamentos = {
			"2026-01": frappe._dict(name="P1", status="Pago", valor=60.0, atrasou=0, transacao_extrato=None),
			"2026-02": frappe._dict(name="P2", status="Atrasado", valor=70.0, atrasou=1, transacao_extrato=None),
		}
		grade = servico.montar_grade_pagamentos(self.meses, pagamentos)
		self.assertEqual(grade["situacao"], servico.STATUS_ATRASADO)
		self.assertEqual(grade["total_esperado"], 130.0)
		self.assertEqual(grade["total_recebido"], 60.0)
		self.assertEqual(grade["meses_gerados"], 2)
		self.assertEqual(grade["meses_quitados"], 1)

	def test_linha_paga_carrega_a_transacao_vinculada(self):
		pagamentos = {
			"2026-01": frappe._dict(
				name="P1", status="Pago", valor=70.0, atrasou=1, transacao_extrato="TX-1"
			)
		}
		grade = servico.montar_grade_pagamentos(self.meses, pagamentos)
		self.assertEqual(grade["linhas"][0]["transacao_extrato"], "TX-1")
		self.assertTrue(grade["linhas"][0]["atrasou"])


class TestApurarComRegistrosReais(FrappeTestCase):
	def setUp(self):
		self.associado = _criar_associado(CPF_BENEFICIARIO)
		_criar_pagamento(self.associado, "2026-01", "Pago", valor=60.0)
		_criar_pagamento(self.associado, "2026-02", "Atrasado", valor=70.0, atrasou=1)

	def test_apurar_associados_reflete_os_registros(self):
		apurado = servico.apurar_associados([self.associado], 3, datetime.date(2026, 3, 22))[0]
		self.assertEqual(apurado["situacao"], servico.STATUS_ATRASADO)
		self.assertEqual(apurado["total_recebido"], 60.0)
		self.assertEqual(apurado["total_esperado"], 130.0)

		por_mes = {linha["ym"]: linha for linha in apurado["linhas"]}
		self.assertEqual(por_mes["2026-01"]["status"], "Pago")
		self.assertEqual(por_mes["2026-02"]["status"], "Atrasado")
		self.assertEqual(por_mes["2026-03"]["status"], servico.STATUS_NAO_GERADO)

	def test_apurar_do_periodo_soma_por_mes(self):
		dados = servico.apurar(3, datetime.date(2026, 3, 22))
		serie = dict(zip(dados["series"]["labels"], dados["series"]["recebido"], strict=True))
		self.assertEqual(serie["01/2026"], 60.0)
		self.assertEqual(serie["02/2026"], 0.0)


class TestDefinirPagamento(FrappeTestCase):
	def setUp(self):
		self.associado = _criar_associado(CPF_BENEFICIARIO)
		_garantir_role_gestor()

	def test_cria_registro_quando_nao_existe(self):
		resultado = monthly_payments.definir_pagamento(
			self.associado, "2026-05-01", status="Pago", valor=60.0
		)
		self.assertTrue(resultado["ok"])
		self.assertEqual(
			frappe.db.get_value("Pagamento Contribuicao Mensal", resultado["name"], "status"), "Pago"
		)

	def test_atualiza_registro_existente_e_mantem_o_mesmo_name(self):
		nome = _criar_pagamento(self.associado, "2026-06", "Em Aberto", valor=60.0)
		resultado = monthly_payments.definir_pagamento(self.associado, "2026-06-01", status="Pago")
		self.assertEqual(resultado["name"], nome)
		self.assertEqual(resultado["status"], "Pago")

	def test_vincula_transacao_valida(self):
		transacao = frappe.get_doc(
			{
				"doctype": "Transacao Extrato Geral",
				"id": f"test-def-pag-{frappe.generate_hash(length=8)}",
				"valor": 60,
				"debito_credito": "Crédito",
			}
		).insert(ignore_permissions=True)

		resultado = monthly_payments.definir_pagamento(
			self.associado, "2026-07-01", status="Pago", transacao_extrato=transacao.name
		)
		self.assertEqual(resultado["transacao_extrato"], transacao.name)

	def test_recusa_transacao_inexistente(self):
		with self.assertRaises(frappe.ValidationError):
			monthly_payments.definir_pagamento(
				self.associado, "2026-08-01", transacao_extrato="TX-NAO-EXISTE"
			)

	def test_recusa_status_invalido(self):
		with self.assertRaises(frappe.ValidationError):
			monthly_payments.definir_pagamento(self.associado, "2026-08-01", status="Cancelado")

	def test_recusa_valor_negativo(self):
		with self.assertRaises(frappe.ValidationError):
			monthly_payments.definir_pagamento(self.associado, "2026-08-01", valor=-10)

	def test_exige_role_de_gestor(self):
		usuario_original = frappe.session.user
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				monthly_payments.definir_pagamento(self.associado, "2026-09-01", status="Pago")
		finally:
			frappe.set_user(usuario_original)


def _garantir_role_gestor() -> None:
	role = monthly_payments.REQUIRED_MANAGER_ROLE
	if not frappe.db.exists("Role", role):
		frappe.get_doc({"doctype": "Role", "role_name": role}).insert(ignore_permissions=True)
	usuario = frappe.get_doc("User", frappe.session.user)
	if role not in {linha.role for linha in usuario.roles}:
		usuario.add_roles(role)
