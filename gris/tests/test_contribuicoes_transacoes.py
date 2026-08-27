"""Testes da apuração de contribuições mensais a partir das transações.

Cobrem a lógica de cálculo (grade mês a mês, crédito acumulado, vencimento e
pendência de cadastro), que é pura e não depende de banco.
"""

import datetime

from frappe.tests.utils import FrappeTestCase

from gris.api.financeiro.contribuicoes import (
	CATEGORIAS_CONTRIBUINTES,
	MESES_MAXIMO,
	MESES_PADRAO,
	STATUS_AGUARDANDO,
	STATUS_ATRASADO,
	STATUS_EM_ABERTO,
	STATUS_NAO_APLICAVEL,
	STATUS_PAGO,
	STATUS_PARCIAL,
	_acao_de_cadastro,
	calcular_vencimento,
	chave_mes,
	construir_meses,
	montar_grade,
	normalizar_meses,
)

HOJE = datetime.date(2026, 8, 22)
VALOR = 60.0


class TestApuracaoContribuicoes(FrappeTestCase):
	def setUp(self):
		self.meses = construir_meses(6, HOJE)
		self.vencimentos = {chave_mes(mes): calcular_vencimento(mes, 10) for mes in self.meses}

	def _grade(self, recebido, contribuinte=None, hoje=HOJE):
		contribuinte = contribuinte or {
			"valor_contribuicao": VALOR,
			"inicio_do_pagamento": "2026-01-01",
		}
		return montar_grade(contribuinte, self.meses, recebido, hoje, self.vencimentos, VALOR)

	def _todos_os_meses(self, valor=VALOR):
		return {chave: {"valor": valor, "qtd": 1} for chave in self.vencimentos}

	def _status(self, grade):
		return [linha["status"] for linha in grade["linhas"]]

	# ── janela de meses ──────────────────────────────────────────────

	def test_construir_meses_termina_no_mes_corrente(self):
		self.assertEqual(
			[chave_mes(mes) for mes in self.meses],
			["2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"],
		)

	def test_normalizar_meses_limita_a_faixa_util(self):
		self.assertEqual(normalizar_meses("abc"), MESES_PADRAO)
		self.assertEqual(normalizar_meses(None), MESES_PADRAO)
		self.assertEqual(normalizar_meses(0), 1)
		self.assertEqual(normalizar_meses(999), MESES_MAXIMO)
		self.assertEqual(normalizar_meses("24"), 24)

	def test_vencimento_pula_fim_de_semana(self):
		# 10/05/2026 cai num domingo: o vencimento anda para a segunda-feira.
		self.assertEqual(calcular_vencimento(datetime.date(2026, 5, 1), 10), datetime.date(2026, 5, 11))
		self.assertEqual(calcular_vencimento(datetime.date(2026, 6, 1), 10), datetime.date(2026, 6, 10))

	# ── apuração mês a mês ───────────────────────────────────────────

	def test_dirigente_fora_das_categorias_contribuintes(self):
		self.assertNotIn("Dirigente", CATEGORIAS_CONTRIBUINTES)
		self.assertEqual(set(CATEGORIAS_CONTRIBUINTES), {"Beneficiário", "Escotista"})

	def test_pagamento_em_dia_quita_todos_os_meses(self):
		grade = self._grade(self._todos_os_meses())
		self.assertEqual(grade["situacao"], STATUS_PAGO)
		self.assertEqual(grade["meses_quitados"], 6)
		self.assertEqual(grade["meses_devidos"], 6)
		self.assertEqual(grade["credito"], 0.0)
		self.assertEqual(grade["total_recebido"], 360.0)

	def test_meses_sem_transacao_ficam_atrasados(self):
		grade = self._grade(
			{
				"2026-03": {"valor": VALOR, "qtd": 1},
				"2026-04": {"valor": VALOR, "qtd": 1},
				"2026-05": {"valor": VALOR, "qtd": 1},
			}
		)
		self.assertEqual(grade["situacao"], STATUS_ATRASADO)
		self.assertEqual(self._status(grade)[3:], [STATUS_ATRASADO] * 3)
		self.assertEqual(grade["meses_quitados"], 3)

	def test_pagamento_a_maior_gera_credito_que_quita_o_mes_seguinte(self):
		grade = self._grade(
			{
				"2026-03": {"valor": 120.0, "qtd": 1},
				"2026-05": {"valor": VALOR, "qtd": 1},
				"2026-06": {"valor": VALOR, "qtd": 1},
				"2026-07": {"valor": VALOR, "qtd": 1},
				"2026-08": {"valor": VALOR, "qtd": 1},
			}
		)
		self.assertEqual(grade["situacao"], STATUS_PAGO)
		self.assertEqual(grade["linhas"][1]["status"], STATUS_PAGO)
		self.assertTrue(grade["linhas"][1]["usou_credito"])
		self.assertFalse(grade["linhas"][0]["usou_credito"])

	def test_credito_sobrando_fica_registrado(self):
		grade = self._grade(self._todos_os_meses() | {"2026-08": {"valor": 150.0, "qtd": 1}})
		self.assertEqual(grade["credito"], 90.0)
		self.assertEqual(grade["saldo"], 90.0)

	def test_pagamento_parcial_nao_quita_o_mes(self):
		grade = self._grade(self._todos_os_meses() | {"2026-07": {"valor": 30.0, "qtd": 1}})
		self.assertEqual(grade["linhas"][4]["status"], STATUS_PARCIAL)
		self.assertEqual(grade["meses_quitados"], 5)

	def test_meses_anteriores_ao_inicio_nao_sao_cobrados(self):
		grade = self._grade(
			{
				"2026-05": {"valor": VALOR, "qtd": 1},
				"2026-06": {"valor": VALOR, "qtd": 1},
				"2026-07": {"valor": VALOR, "qtd": 1},
				"2026-08": {"valor": VALOR, "qtd": 1},
			},
			contribuinte={"valor_contribuicao": VALOR, "inicio_do_pagamento": "2026-05-01"},
		)
		self.assertEqual(self._status(grade)[:2], [STATUS_NAO_APLICAVEL] * 2)
		self.assertEqual(grade["meses_devidos"], 4)
		self.assertEqual(grade["situacao"], STATUS_PAGO)

	def test_inicio_futuro_fica_aguardando(self):
		grade = self._grade(
			{},
			contribuinte={"valor_contribuicao": VALOR, "inicio_do_pagamento": "2026-08-30"},
		)
		self.assertEqual(grade["linhas"][-1]["status"], STATUS_AGUARDANDO)
		self.assertEqual(grade["meses_devidos"], 0)
		self.assertEqual(grade["situacao"], STATUS_AGUARDANDO)

	def test_mes_corrente_antes_do_vencimento_fica_em_aberto(self):
		grade = self._grade(
			{chave: {"valor": VALOR, "qtd": 1} for chave in self.vencimentos if chave != "2026-08"},
			hoje=datetime.date(2026, 8, 5),
		)
		self.assertEqual(grade["linhas"][-1]["status"], STATUS_EM_ABERTO)
		self.assertEqual(grade["situacao"], STATUS_EM_ABERTO)

	def test_mes_corrente_apos_o_vencimento_fica_atrasado(self):
		grade = self._grade(
			{chave: {"valor": VALOR, "qtd": 1} for chave in self.vencimentos if chave != "2026-08"}
		)
		self.assertEqual(grade["linhas"][-1]["status"], STATUS_ATRASADO)

	def test_sem_valor_no_cadastro_usa_o_valor_base(self):
		grade = self._grade({}, contribuinte={"valor_contribuicao": 0, "inicio_do_pagamento": "2026-01-01"})
		self.assertEqual(grade["esperado_mensal"], VALOR)
		self.assertEqual(grade["total_esperado"], 360.0)

	# ── pendências de cadastro da cobrança ───────────────────────────

	def test_inativo_com_cobranca_ativa_precisa_cancelar(self):
		acao = _acao_de_cadastro({"status_no_grupo": "Inativo", "status_cobranca": "Ativo"}, HOJE)
		self.assertEqual(acao, "Cancelar")

	def test_ativo_prestes_a_comecar_precisa_cadastrar(self):
		acao = _acao_de_cadastro(
			{
				"status_no_grupo": "Ativo",
				"status_cobranca": "Inativo",
				"inicio_do_pagamento": "2026-09-10",
			},
			HOJE,
		)
		self.assertEqual(acao, "Cadastrar")

	def test_inicio_distante_ainda_nao_pede_cadastro(self):
		acao = _acao_de_cadastro(
			{
				"status_no_grupo": "Ativo",
				"status_cobranca": "Inativo",
				"inicio_do_pagamento": "2026-12-01",
			},
			HOJE,
		)
		self.assertIsNone(acao)

	def test_cobranca_ja_ativa_nao_gera_pendencia(self):
		acao = _acao_de_cadastro({"status_no_grupo": "Ativo", "status_cobranca": "Ativo"}, HOJE)
		self.assertIsNone(acao)
