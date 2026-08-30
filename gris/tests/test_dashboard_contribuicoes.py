"""Testes das séries de contribuição do painel financeiro.

Depois da migração, os três endpoints do painel leem a apuração de
`gris.api.financeiro.contribuicoes` em vez de contar registros de
`Pagamento Contribuicao Mensal`. O que estes testes protegem é justamente isso:
o contrato de resposta que o `dashboard.js` e a ferramenta MCP consomem, e o
fato de os números virem da mesma regra da página /financeiro/contribuicoes.
"""

import datetime
from unittest import mock

from frappe.tests.utils import FrappeTestCase

from gris.api.financeiro import dashboard
from gris.api.financeiro.contribuicoes import (
	SITUACOES_DO_MES_DEVIDO,
	STATUS_ATRASADO,
	STATUS_EM_ABERTO,
	STATUS_PAGO,
	STATUS_PARCIAL,
	apurar,
	calcular_vencimento,
	chave_mes,
	construir_meses,
	montar_grade,
)

HOJE = datetime.date(2026, 8, 22)
VALOR = 60.0


class TestVencimentoNaGrade(FrappeTestCase):
	"""A marca de vencido é o que separa o parcial inadimplente do parcial no prazo."""

	def setUp(self):
		self.meses = construir_meses(6, HOJE)
		self.vencimentos = {chave_mes(mes): calcular_vencimento(mes, 10) for mes in self.meses}

	def _grade(self, recebido, hoje=HOJE):
		contribuinte = {"valor_contribuicao": VALOR, "inicio_do_pagamento": "2026-01-01"}
		return montar_grade(contribuinte, self.meses, recebido, hoje, self.vencimentos, VALOR)

	def _linha(self, grade, ym):
		return next(linha for linha in grade["linhas"] if linha["ym"] == ym)

	def test_mes_passado_esta_sempre_vencido(self):
		grade = self._grade({})
		self.assertTrue(self._linha(grade, "2026-07")["vencido"])

	def test_mes_corrente_antes_do_vencimento_nao_esta_vencido(self):
		# Vencimento de 08/2026 é dia 10; apurando no dia 5 o mês ainda está no prazo.
		grade = self._grade({}, hoje=datetime.date(2026, 8, 5))
		linha = self._linha(grade, "2026-08")
		self.assertFalse(linha["vencido"])
		self.assertEqual(linha["status"], STATUS_EM_ABERTO)

	def test_parcial_no_prazo_e_parcial_vencido_se_distinguem(self):
		parcial = {"2026-08": {"valor": 20.0, "qtd": 1}}

		no_prazo = self._linha(self._grade(parcial, hoje=datetime.date(2026, 8, 5)), "2026-08")
		self.assertEqual(no_prazo["status"], STATUS_PARCIAL)
		self.assertFalse(no_prazo["vencido"])

		vencido = self._linha(self._grade(parcial, hoje=datetime.date(2026, 8, 22)), "2026-08")
		self.assertEqual(vencido["status"], STATUS_PARCIAL)
		self.assertTrue(vencido["vencido"])


class TestSeriesDaApuracao(FrappeTestCase):
	"""As séries agregadas que o painel passou a consumir."""

	def test_por_situacao_cobre_as_quatro_situacoes_do_mes_devido(self):
		self.assertEqual(
			SITUACOES_DO_MES_DEVIDO,
			(STATUS_PAGO, STATUS_PARCIAL, STATUS_EM_ABERTO, STATUS_ATRASADO),
		)

	def test_apurar_expoe_series_e_totais_da_inadimplencia(self):
		dados = apurar(6, hoje=HOJE)
		series = dados["series"]
		totais = dados["totais"]

		quantidade = len(series["labels"])
		self.assertEqual(len(series["inadimplencia"]), quantidade)
		self.assertEqual(len(series["meses_devidos"]), quantidade)
		for situacao in SITUACOES_DO_MES_DEVIDO:
			self.assertEqual(len(series["por_situacao"][situacao]), quantidade)

		# Cada mês devido cai em exatamente uma das quatro situações.
		for indice, devidos in enumerate(series["meses_devidos"]):
			soma = sum(series["por_situacao"][s][indice] for s in SITUACOES_DO_MES_DEVIDO)
			self.assertEqual(soma, devidos)

		self.assertIn("inadimplentes", totais)
		self.assertIn("inadimplencia_associados", totais)
		self.assertLessEqual(totais["inadimplentes"], totais["contribuintes"])


# Apuração de dois meses com um de cada situação relevante, para checar o
# contrato dos endpoints sem depender do que existe no banco.
APURACAO_FALSA = {
	"meses": [{"ym": "2026-07", "rotulo": "07/2026"}, {"ym": "2026-08", "rotulo": "08/2026"}],
	"series": {
		"labels": ["07/2026", "08/2026"],
		"inadimplencia": [50.0, 25.0],
		"meses_devidos": [4, 4],
		"por_situacao": {
			STATUS_PAGO: [2, 3],
			STATUS_PARCIAL: [1, 0],
			STATUS_EM_ABERTO: [0, 0],
			STATUS_ATRASADO: [1, 1],
		},
	},
	"totais": {
		"contribuintes": 4,
		"inadimplentes": 1,
		"inadimplencia_associados": 25.0,
	},
}


class TestEndpointsDoPainel(FrappeTestCase):
	"""Contrato de resposta dos três endpoints, com a apuração controlada."""

	def _com_apuracao(self):
		return mock.patch.object(dashboard, "apurar", return_value=APURACAO_FALSA)

	def test_status_por_mes_devolve_uma_serie_por_situacao_presente(self):
		with self._com_apuracao():
			payload = dashboard.get_contribuicoes_mensais_por_status()

		# O painel rotula em MM/AA, como os demais gráficos que ficam ao lado.
		self.assertEqual(payload["labels"], ["07/26", "08/26"])
		nomes = [dataset["name"] for dataset in payload["datasets"]]
		# "Em Aberto" está zerado nos dois meses e não vira barra.
		self.assertEqual(nomes, [STATUS_PAGO, STATUS_PARCIAL, STATUS_ATRASADO])
		self.assertTrue(all(d["chartType"] == "bar" for d in payload["datasets"]))
		self.assertEqual(payload["datasets"][0]["values"], [2, 3])

	def test_inadimplencia_mensal_mantem_o_formato_de_linha(self):
		with self._com_apuracao():
			payload = dashboard.get_contribuicoes_mensais_inadimplencia()

		# O painel rotula em MM/AA, como os demais gráficos que ficam ao lado.
		self.assertEqual(payload["labels"], ["07/26", "08/26"])
		self.assertEqual(len(payload["datasets"]), 1)
		dataset = payload["datasets"][0]
		self.assertEqual(dataset["name"], "Inadimplência (%)")
		self.assertEqual(dataset["chartType"], "line")
		self.assertEqual(dataset["values"], [50.0, 25.0])

	def test_card_historico_conta_associados_nao_meses(self):
		with self._com_apuracao():
			payload = dashboard.get_inadimplencia_historica_12m()

		self.assertEqual(payload, {"percent": 25.0, "atrasado": 1, "total": 4})

	def test_alias_de_6m_continua_apontando_para_o_de_12m(self):
		self.assertIs(dashboard.get_inadimplencia_historica_6m, dashboard.get_inadimplencia_historica_12m)

	def test_painel_sem_contribuintes_nao_quebra(self):
		vazio = {
			"meses": [],
			"series": {
				"labels": [],
				"inadimplencia": [],
				"meses_devidos": [],
				"por_situacao": {situacao: [] for situacao in SITUACOES_DO_MES_DEVIDO},
			},
			"totais": {"contribuintes": 0, "inadimplentes": 0, "inadimplencia_associados": 0.0},
		}
		with mock.patch.object(dashboard, "apurar", return_value=vazio):
			self.assertEqual(dashboard.get_contribuicoes_mensais_por_status()["datasets"], [])
			self.assertEqual(
				dashboard.get_inadimplencia_historica_12m(),
				{"percent": 0.0, "atrasado": 0, "total": 0},
			)
