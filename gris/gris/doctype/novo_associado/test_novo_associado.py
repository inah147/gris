# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

from unittest import TestCase

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from gris.gris.doctype.novo_associado import novo_associado

# Mesmos valores dos defaults do Single "Vagas" (idades de transição de cada ramo).
FAIXAS = [
	("Filhotes", 6.5),
	("Lobinho", 10.5),
	("Escoteiro", 14.5),
	("Sênior", 17.5),
	("Pioneiro", 21.5),
]


def _registro(data_de_nascimento, ramo, name="abc"):
	return {
		"name": name,
		"nome_completo": "Jovem",
		"data_de_nascimento": data_de_nascimento,
		"ramo": ramo,
	}


class _FakeLogger:
	def info(self, *_args, **_kwargs):
		return None

	def warning(self, *_args, **_kwargs):
		return None


class TestNovoAssociado(FrappeTestCase):
	def _criar_novo_associado(self, **kwargs) -> "frappe.model.document.Document":
		doc = frappe.get_doc(
			{
				"doctype": "Novo Associado",
				"nome_completo": "Jovem de Teste",
				"cpf": kwargs.pop("cpf", "111.111.111-11"),
				"data_de_nascimento": "2015-04-14",
				"status": "Acompanhamento",
				"tipo_de_registro": "Provisório",
				**kwargs,
			}
		)
		doc.insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "Novo Associado", doc.name, force=True)
		return doc

	def test_data_de_ativacao_fica_vazia_enquanto_registro_provisorio_nao_efetivado(self):
		doc = self._criar_novo_associado(cpf="222.222.222-22")

		self.assertFalse(doc.registro_provisorio_efetivado)
		self.assertIsNone(doc.data_registro_provisorio_efetivado)

	def test_data_de_ativacao_e_gravada_ao_efetivar_registro_provisorio(self):
		doc = self._criar_novo_associado(cpf="333.333.333-33")

		doc.registro_provisorio_efetivado = 1
		doc.save(ignore_permissions=True)

		self.assertEqual(str(doc.data_registro_provisorio_efetivado), today())

	def test_data_de_ativacao_e_preservada_em_salvamentos_seguintes(self):
		doc = self._criar_novo_associado(
			cpf="444.444.444-44",
			registro_provisorio_efetivado=1,
		)
		doc.db_set("data_registro_provisorio_efetivado", "2026-01-10")
		doc.reload()

		doc.nome_completo = "Jovem de Teste Renomeado"
		doc.save(ignore_permissions=True)

		self.assertEqual(str(doc.data_registro_provisorio_efetivado), "2026-01-10")

	def test_desmarcar_registro_provisorio_limpa_data_e_controle_de_aviso(self):
		doc = self._criar_novo_associado(
			cpf="555.555.555-55",
			registro_provisorio_efetivado=1,
		)
		doc.db_set("data_aviso_seguimento_provisorio", today())
		doc.reload()
		self.assertIsNotNone(doc.data_registro_provisorio_efetivado)

		doc.registro_provisorio_efetivado = 0
		doc.save(ignore_permissions=True)

		self.assertIsNone(doc.data_registro_provisorio_efetivado)
		self.assertIsNone(doc.data_aviso_seguimento_provisorio)


class TestRamoPorDataDeNascimento(TestCase):
	"""A idade de transição é o limite superior do próprio ramo, não do seguinte."""

	def test_idade_igual_a_transicao_permanece_no_ramo(self):
		# 2016-03-01 tem exatamente 10 anos e 6 meses em 2026-09-01.
		ramo = novo_associado.ramo_por_data_de_nascimento("2016-03-01", FAIXAS, hoje="2026-09-01")
		self.assertEqual(ramo, "Lobinho")

	def test_idade_acima_da_transicao_promove_para_o_proximo_ramo(self):
		ramo = novo_associado.ramo_por_data_de_nascimento("2016-03-01", FAIXAS, hoje="2026-10-01")
		self.assertEqual(ramo, "Escoteiro")

	def test_cada_ramo_respeita_a_propria_faixa(self):
		esperado = {
			"2020-05-01": "Filhotes",  # 6 anos e 4 meses
			"2018-01-01": "Lobinho",  # 8 anos e 8 meses
			"2014-01-01": "Escoteiro",  # 12 anos e 8 meses
			"2010-01-01": "Sênior",  # 16 anos e 8 meses
			"2000-01-01": "Pioneiro",  # 26 anos e 8 meses
		}
		for nascimento, ramo in esperado.items():
			with self.subTest(nascimento=nascimento):
				self.assertEqual(
					novo_associado.ramo_por_data_de_nascimento(nascimento, FAIXAS, hoje="2026-09-01"),
					ramo,
				)

	def test_sem_data_de_nascimento_nao_define_ramo(self):
		self.assertIsNone(novo_associado.ramo_por_data_de_nascimento(None, FAIXAS))

	def test_idade_decimal_conta_anos_com_fracao_de_meses(self):
		self.assertAlmostEqual(novo_associado.idade_decimal("2016-03-01", hoje="2026-09-01"), 10.5, places=3)
		# Aniversário ainda não completado no mês corrente.
		self.assertAlmostEqual(
			novo_associado.idade_decimal("2016-09-15", hoje="2026-09-01"),
			9 + 11 / 12,
			places=3,
		)


class TestAtualizarRamosPorIdade(TestCase):
	def _executar(self, registros, fila=None, hoje="2026-09-01"):
		"""Roda a rotina diária sem tocar o banco, devolvendo as escritas tentadas."""
		modulo = novo_associado
		fila = fila or []
		escritas = []

		orig_get_all = modulo.frappe.get_all
		orig_get_single = modulo.frappe.get_single
		orig_set_value = modulo.frappe.db.set_value
		orig_commit = modulo.frappe.db.commit
		orig_today = modulo.today
		orig_obter_logger = modulo.obter_logger

		por_doctype = {"Novo Associado": registros, "Fila de Espera": fila}
		transicoes = dict(FAIXAS)

		def _fake_get_all(doctype, *_args, **_kwargs):
			return [frappe._dict(linha) for linha in por_doctype.get(doctype, [])]

		def _fake_get_single(_doctype):
			return frappe._dict({campo: transicoes[ramo] for ramo, campo in modulo.CAMPOS_DE_TRANSICAO})

		def _fake_set_value(doctype, docname, fieldname, value, **_kwargs):
			escritas.append((doctype, docname, fieldname, value))

		modulo.frappe.get_all = _fake_get_all
		modulo.frappe.get_single = _fake_get_single
		modulo.frappe.db.set_value = _fake_set_value
		modulo.frappe.db.commit = lambda: None
		modulo.today = lambda: hoje
		modulo.obter_logger = lambda *_a, **_k: _FakeLogger()
		try:
			modulo.atualizar_ramos_por_idade()
		finally:
			modulo.frappe.get_all = orig_get_all
			modulo.frappe.get_single = orig_get_single
			modulo.frappe.db.set_value = orig_set_value
			modulo.frappe.db.commit = orig_commit
			modulo.today = orig_today
			modulo.obter_logger = orig_obter_logger

		return escritas

	def test_promove_quem_cruzou_a_idade_de_transicao(self):
		escritas = self._executar([_registro("2016-01-01", "Lobinho")])
		self.assertEqual(escritas, [("Novo Associado", "abc", "ramo", "Escoteiro")])

	def test_nao_escreve_quando_o_ramo_ja_esta_correto(self):
		escritas = self._executar([_registro("2018-01-01", "Lobinho")])
		self.assertEqual(escritas, [])

	def test_sincroniza_a_fila_de_espera_com_o_novo_ramo(self):
		escritas = self._executar(
			[_registro("2016-01-01", "Lobinho")],
			fila=[{"name": "FILA-1", "associado": "abc", "ramo": "Lobinho"}],
		)
		self.assertIn(("Novo Associado", "abc", "ramo", "Escoteiro"), escritas)
		self.assertIn(("Fila de Espera", "FILA-1", "ramo", "Escoteiro"), escritas)

	def test_corrige_a_fila_divergente_mesmo_sem_mudanca_no_novo_associado(self):
		escritas = self._executar(
			[_registro("2018-01-01", "Lobinho")],
			fila=[{"name": "FILA-1", "associado": "abc", "ramo": "Filhotes"}],
		)
		self.assertEqual(escritas, [("Fila de Espera", "FILA-1", "ramo", "Lobinho")])

	def test_registro_sem_data_de_nascimento_e_ignorado(self):
		escritas = self._executar(
			[
				_registro(None, None, name="sem-data"),
				_registro("2016-01-01", "Lobinho"),
			]
		)
		self.assertEqual(escritas, [("Novo Associado", "abc", "ramo", "Escoteiro")])
