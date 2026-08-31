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
	ParametrosContribuicao,
	_acao_de_cadastro,
	calcular_vencimento,
	chave_mes,
	construir_meses,
	montar_grade,
	normalizar_meses,
	resolver_inicio_do_pagamento,
)

HOJE = datetime.date(2026, 8, 22)
VALOR = 60.0
VALOR_ATRASO = 70.0


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

	def test_apenas_beneficiario_contribui(self):
		self.assertNotIn("Dirigente", CATEGORIAS_CONTRIBUINTES)
		self.assertNotIn("Escotista", CATEGORIAS_CONTRIBUINTES)
		self.assertEqual(set(CATEGORIAS_CONTRIBUINTES), {"Beneficiário"})

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


def _pagamento(valor: float, data: str | None = None, infinitepay: bool = False) -> dict:
	"""Uma transação de contribuição como a apuração a enxerga."""
	return {
		"valor": float(valor),
		"data": datetime.date.fromisoformat(data) if data else None,
		"retroativa": infinitepay,
	}


def _mes(*pagamentos: dict) -> dict:
	"""Entrada de um mês do dicionário de recebimentos."""
	return {
		"valor": round(sum(p["valor"] for p in pagamentos), 2),
		"qtd": len(pagamentos),
		"transacoes": list(pagamentos),
	}


PARAMETROS = ParametrosContribuicao(
	valor_base=VALOR,
	valor_atraso=VALOR_ATRASO,
	dia_vencimento=10,
	carencia_provisorio=2,
	carencia_definitivo=1,
)


class TestValorEmAtraso(FrappeTestCase):
	"""O mês que vence sem quitação passa a valer o valor de atraso."""

	def setUp(self):
		self.meses = construir_meses(6, HOJE)
		self.vencimentos = {chave_mes(mes): calcular_vencimento(mes, 10) for mes in self.meses}

	def _grade(self, recebido, contribuinte=None, hoje=HOJE):
		contribuinte = contribuinte or {
			"valor_contribuicao": VALOR,
			"inicio_do_pagamento": "2026-01-01",
		}
		return montar_grade(contribuinte, self.meses, recebido, hoje, self.vencimentos, VALOR, PARAMETROS)

	def _linha(self, grade, ym):
		return next(linha for linha in grade["linhas"] if linha["ym"] == ym)

	def test_mes_vencido_sem_pagamento_custa_o_valor_de_atraso(self):
		grade = self._grade({})
		self.assertEqual(self._linha(grade, "2026-03")["esperado"], VALOR_ATRASO)
		self.assertEqual(self._linha(grade, "2026-03")["status"], STATUS_ATRASADO)
		self.assertTrue(self._linha(grade, "2026-03")["em_atraso"])
		# Seis meses vencidos, todos pelo valor de atraso.
		self.assertEqual(grade["total_esperado"], 6 * VALOR_ATRASO)

	def test_mes_pago_no_prazo_continua_valendo_o_valor_base(self):
		grade = self._grade({"2026-03": _mes(_pagamento(VALOR, "2026-03-08"))})
		linha = self._linha(grade, "2026-03")
		self.assertEqual(linha["esperado"], VALOR)
		self.assertEqual(linha["status"], STATUS_PAGO)
		self.assertFalse(linha["em_atraso"])

	def test_pagamento_do_valor_base_depois_do_vencimento_quita_o_mes(self):
		"""Pagar 60 depois do vencimento fecha o mês: o acréscimo é o que se cobra."""
		grade = self._grade({"2026-03": _mes(_pagamento(VALOR, "2026-04-02"))})
		linha = self._linha(grade, "2026-03")
		self.assertEqual(linha["esperado"], VALOR_ATRASO)
		self.assertEqual(linha["status"], STATUS_PAGO)
		self.assertEqual(linha["falta"], 0.0)
		self.assertTrue(linha["quitado_sem_acrescimo"])

	def test_pagamento_menor_que_o_valor_em_dia_nao_quita(self):
		grade = self._grade({"2026-03": _mes(_pagamento(30.0, "2026-04-02"))})
		linha = self._linha(grade, "2026-03")
		self.assertEqual(linha["status"], STATUS_PARCIAL)
		# A cobrança do que falta continua saindo pelo valor cheio do mês vencido.
		self.assertEqual(linha["falta"], round(VALOR_ATRASO - 30.0, 2))

	def test_pagamento_do_valor_de_atraso_quita_o_mes(self):
		grade = self._grade({"2026-03": _mes(_pagamento(VALOR_ATRASO, "2026-04-02"))})
		linha = self._linha(grade, "2026-03")
		self.assertEqual(linha["esperado"], VALOR_ATRASO)
		self.assertEqual(linha["status"], STATUS_PAGO)
		self.assertFalse(linha["quitado_sem_acrescimo"])

	def test_mes_corrente_antes_do_vencimento_nao_encarece(self):
		grade = self._grade({}, hoje=datetime.date(2026, 8, 5))
		linha = self._linha(grade, "2026-08")
		self.assertEqual(linha["esperado"], VALOR)
		self.assertEqual(linha["status"], STATUS_EM_ABERTO)

	def test_valor_proprio_do_associado_recebe_o_mesmo_acrescimo(self):
		grade = self._grade(
			{},
			contribuinte={"valor_contribuicao": 100.0, "inicio_do_pagamento": "2026-01-01"},
		)
		self.assertEqual(grade["esperado_mensal"], 100.0)
		self.assertEqual(self._linha(grade, "2026-03")["esperado"], 110.0)

	def test_sem_valor_de_atraso_configurado_o_mes_nao_encarece(self):
		parametros = ParametrosContribuicao(valor_base=VALOR, valor_atraso=VALOR, dia_vencimento=10)
		grade = montar_grade(
			{"valor_contribuicao": VALOR, "inicio_do_pagamento": "2026-01-01"},
			self.meses,
			{},
			HOJE,
			self.vencimentos,
			VALOR,
			parametros,
		)
		self.assertEqual(grade["total_esperado"], 6 * VALOR)


class TestCarenciaDeRegistro(FrappeTestCase):
	"""Os primeiros meses depois do ingresso pagam registro, não contribuição."""

	def setUp(self):
		self.meses = construir_meses(6, HOJE)
		self.vencimentos = {chave_mes(mes): calcular_vencimento(mes, 10) for mes in self.meses}

	def _grade(self, contribuinte, recebido=None):
		return montar_grade(
			contribuinte, self.meses, recebido or {}, HOJE, self.vencimentos, VALOR, PARAMETROS
		)

	def _motivos(self, grade):
		return {linha["ym"]: linha["motivo"] for linha in grade["linhas"] if linha["motivo"]}

	def test_provisorio_so_contribui_no_terceiro_mes(self):
		grade = self._grade(
			{
				"valor_contribuicao": VALOR,
				"tipo_registro": "Provisório",
				"data_de_ingresso": "2026-03-15",
			}
		)
		status = {linha["ym"]: linha["status"] for linha in grade["linhas"]}
		self.assertEqual(status["2026-03"], STATUS_NAO_APLICAVEL)
		self.assertEqual(status["2026-04"], STATUS_NAO_APLICAVEL)
		self.assertEqual(status["2026-05"], STATUS_ATRASADO)
		self.assertEqual(grade["meses_devidos"], 4)
		self.assertEqual(grade["inicio_do_pagamento"], "2026-05-01")
		self.assertTrue(grade["inicio_calculado"])

	def test_provisorio_explica_o_que_se_paga_na_carencia(self):
		grade = self._grade(
			{
				"valor_contribuicao": VALOR,
				"tipo_registro": "Provisório",
				"data_de_ingresso": "2026-03-15",
			}
		)
		self.assertEqual(
			self._motivos(grade),
			{"2026-03": "Registro provisório", "2026-04": "Registro definitivo + uniforme"},
		)

	def test_definitivo_contribui_a_partir_do_segundo_mes(self):
		grade = self._grade(
			{
				"valor_contribuicao": VALOR,
				"tipo_registro": "Definitivo",
				"data_de_ingresso": "2026-03-15",
			}
		)
		status = {linha["ym"]: linha["status"] for linha in grade["linhas"]}
		self.assertEqual(status["2026-03"], STATUS_NAO_APLICAVEL)
		self.assertEqual(status["2026-04"], STATUS_ATRASADO)
		self.assertEqual(grade["meses_devidos"], 5)
		self.assertEqual(self._motivos(grade), {"2026-03": "Registro definitivo"})

	def test_inicio_do_cadastro_prevalece_sobre_a_carencia(self):
		grade = self._grade(
			{
				"valor_contribuicao": VALOR,
				"tipo_registro": "Provisório",
				"data_de_ingresso": "2026-03-15",
				"inicio_do_pagamento": "2026-04-01",
			}
		)
		self.assertEqual(grade["inicio_do_pagamento"], "2026-04-01")
		self.assertFalse(grade["inicio_calculado"])
		self.assertEqual(grade["meses_devidos"], 5)
		# O mês já cobrado não recebe rótulo de carência.
		self.assertEqual(self._motivos(grade), {"2026-03": "Registro provisório"})

	def test_sem_ingresso_e_sem_inicio_todos_os_meses_sao_devidos(self):
		grade = self._grade({"valor_contribuicao": VALOR, "tipo_registro": "Definitivo"})
		self.assertEqual(grade["meses_devidos"], 6)
		self.assertIsNone(grade["inicio_do_pagamento"])

	def test_resolver_inicio_conta_a_carencia_a_partir_do_mes_do_ingresso(self):
		provisorio = resolver_inicio_do_pagamento(
			{"tipo_registro": "Provisório", "data_de_ingresso": "2026-03-31"}, PARAMETROS
		)
		definitivo = resolver_inicio_do_pagamento(
			{"tipo_registro": "Definitivo", "data_de_ingresso": "2026-03-01"}, PARAMETROS
		)
		self.assertEqual(provisorio, datetime.date(2026, 5, 1))
		self.assertEqual(definitivo, datetime.date(2026, 4, 1))


class TestQuitacaoRetroativa(FrappeTestCase):
	"""Pagamento da InfinitePay em múltiplo de mensalidade quita o passado."""

	def setUp(self):
		self.meses = construir_meses(6, HOJE)
		self.vencimentos = {chave_mes(mes): calcular_vencimento(mes, 10) for mes in self.meses}

	def _grade(self, recebido):
		return montar_grade(
			{"valor_contribuicao": VALOR, "inicio_do_pagamento": "2026-01-01"},
			self.meses,
			recebido,
			HOJE,
			self.vencimentos,
			VALOR,
			PARAMETROS,
		)

	def _status(self, grade):
		return {linha["ym"]: linha["status"] for linha in grade["linhas"]}

	def test_multiplo_do_valor_de_atraso_quita_os_meses_mais_antigos(self):
		grade = self._grade({"2026-08": _mes(_pagamento(3 * VALOR_ATRASO, "2026-08-05", infinitepay=True))})
		status = self._status(grade)
		self.assertEqual(status["2026-03"], STATUS_PAGO)
		self.assertEqual(status["2026-04"], STATUS_PAGO)
		self.assertEqual(status["2026-05"], STATUS_PAGO)
		self.assertEqual(status["2026-06"], STATUS_ATRASADO)
		self.assertEqual(status["2026-08"], STATUS_ATRASADO)
		self.assertEqual(grade["credito"], 0.0)

	def test_multiplo_do_valor_base_fecha_tres_meses(self):
		"""180 = três mensalidades: quitar mais um mês vale mais que o acréscimo."""
		grade = self._grade({"2026-08": _mes(_pagamento(3 * VALOR, "2026-08-05", infinitepay=True))})
		linhas = {linha["ym"]: linha for linha in grade["linhas"]}
		self.assertEqual(linhas["2026-03"]["status"], STATUS_PAGO)
		self.assertEqual(linhas["2026-04"]["status"], STATUS_PAGO)
		self.assertEqual(linhas["2026-05"]["status"], STATUS_PAGO)
		self.assertEqual(linhas["2026-05"]["coberto"], VALOR)
		self.assertEqual(linhas["2026-05"]["falta"], 0.0)
		self.assertEqual(linhas["2026-06"]["status"], STATUS_ATRASADO)
		self.assertTrue(linhas["2026-03"]["quitacao_retroativa"])

	def test_multiplo_do_valor_de_atraso_paga_o_acrescimo_dos_mesmos_meses(self):
		"""210 fecha os mesmos três meses pelo valor cheio, sem tocar num quarto."""
		grade = self._grade({"2026-08": _mes(_pagamento(3 * VALOR_ATRASO, "2026-08-05", infinitepay=True))})
		linhas = {linha["ym"]: linha for linha in grade["linhas"]}
		self.assertEqual(linhas["2026-05"]["coberto"], VALOR_ATRASO)
		self.assertFalse(linhas["2026-05"]["quitado_sem_acrescimo"])
		self.assertEqual(linhas["2026-06"]["coberto"], 0.0)
		self.assertEqual(linhas["2026-06"]["status"], STATUS_ATRASADO)

	def test_pagamento_fora_da_infinitepay_continua_virando_credito(self):
		grade = self._grade({"2026-08": _mes(_pagamento(3 * VALOR_ATRASO, "2026-08-05"))})
		status = self._status(grade)
		self.assertEqual(status["2026-03"], STATUS_ATRASADO)
		self.assertEqual(status["2026-08"], STATUS_PAGO)
		# Pagou 210 no mês corrente, que custa 60: sobram 150 de crédito.
		self.assertEqual(grade["credito"], 150.0)

	def test_valor_que_nao_fecha_mensalidade_nao_quita_o_passado(self):
		grade = self._grade({"2026-08": _mes(_pagamento(45.0, "2026-08-05", infinitepay=True))})
		linhas = {linha["ym"]: linha for linha in grade["linhas"]}
		self.assertEqual(linhas["2026-03"]["status"], STATUS_ATRASADO)
		self.assertEqual(linhas["2026-08"]["status"], STATUS_PARCIAL)
		self.assertEqual(linhas["2026-08"]["coberto"], 45.0)

	def test_sem_divida_no_passado_o_excedente_vira_credito(self):
		recebido = {
			chave: _mes(_pagamento(VALOR, f"{chave}-05", infinitepay=True)) for chave in self.vencimentos
		}
		recebido["2026-08"] = _mes(
			_pagamento(VALOR, "2026-08-05", infinitepay=True),
			_pagamento(2 * VALOR, "2026-08-05", infinitepay=True),
		)
		grade = self._grade(recebido)
		self.assertEqual(grade["situacao"], STATUS_PAGO)
		self.assertEqual(grade["credito"], 2 * VALOR)

	def test_pagamento_retroativo_de_um_mes_so_prioriza_a_divida_mais_antiga(self):
		grade = self._grade({"2026-08": _mes(_pagamento(VALOR_ATRASO, "2026-08-05", infinitepay=True))})
		status = self._status(grade)
		self.assertEqual(status["2026-03"], STATUS_PAGO)
		self.assertEqual(status["2026-08"], STATUS_ATRASADO)
