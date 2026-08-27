"""Testes do cálculo do funil de recepção (etapas, cadência e atraso).

Mesma regra usada pelo kanban de /recepcao/visao_geral e pelas ferramentas MCP.
"""

from datetime import date
from unittest import TestCase

from gris.api import recepcao_funil

CONFIG = {
	"dados_para_registro_enviados": 5,
	"registro_criado_no_paxtu": 10,
	"pesquisa_de_novos_associados_respondida": 3,
}

BASE = date(2026, 1, 3)


def _etapa(etapas, campo):
	return next(etapa for etapa in etapas if etapa["field"] == campo)


class TestCalcularEtapas(TestCase):
	def test_registro_definitivo_pula_etapas_condicionais(self):
		provisorio = recepcao_funil.calcular_etapas({"tipo_de_registro": "Provisório"}, CONFIG)
		definitivo = recepcao_funil.calcular_etapas({"tipo_de_registro": "Definitivo"}, CONFIG)

		campos_definitivo = [etapa["field"] for etapa in definitivo]
		self.assertEqual(len(provisorio), len(recepcao_funil.STEPS_DEF))
		self.assertEqual(len(definitivo), len(recepcao_funil.STEPS_DEF) - 2)
		self.assertNotIn("registro_provisorio_pago", campos_definitivo)
		self.assertNotIn("registro_provisorio_efetivado", campos_definitivo)

	def test_sem_data_base_nao_estima_datas(self):
		etapas = recepcao_funil.calcular_etapas({"tipo_de_registro": "Definitivo"}, CONFIG)
		self.assertTrue(all("data_estimada" not in etapa for etapa in etapas))
		self.assertTrue(all("is_overdue" not in etapa for etapa in etapas))

	def test_intervalos_sao_cumulativos_a_partir_da_visita(self):
		etapas = recepcao_funil.calcular_etapas(
			{"tipo_de_registro": "Definitivo"}, CONFIG, BASE, hoje=date(2026, 1, 1)
		)
		self.assertEqual(_etapa(etapas, "dados_para_registro_enviados")["data_estimada"], "2026-01-08")
		self.assertEqual(_etapa(etapas, "registro_criado_no_paxtu")["data_estimada"], "2026-01-18")
		self.assertEqual(
			_etapa(etapas, "pesquisa_de_novos_associados_respondida")["data_estimada"], "2026-01-21"
		)

	def test_etapa_concluida_nao_estima_mas_empurra_a_proxima(self):
		dados = {"tipo_de_registro": "Definitivo", "dados_para_registro_enviados": 1}
		etapas = recepcao_funil.calcular_etapas(dados, CONFIG, BASE, hoje=date(2026, 1, 1))

		concluida = _etapa(etapas, "dados_para_registro_enviados")
		self.assertTrue(concluida["completed"])
		self.assertNotIn("data_estimada", concluida)
		self.assertEqual(_etapa(etapas, "registro_criado_no_paxtu")["data_estimada"], "2026-01-18")

	def test_marca_atraso_quando_a_data_estimada_ja_passou(self):
		etapas = recepcao_funil.calcular_etapas(
			{"tipo_de_registro": "Definitivo"}, CONFIG, BASE, hoje=date(2026, 2, 1)
		)
		self.assertTrue(_etapa(etapas, "dados_para_registro_enviados")["is_overdue"])
		self.assertNotIn("is_overdue", _etapa(etapas, "visita_agendada"))

	def test_intervalo_invalido_na_configuracao_nao_quebra(self):
		etapas = recepcao_funil.calcular_etapas(
			{"tipo_de_registro": "Definitivo"},
			{"dados_para_registro_enviados": "cinco dias"},
			BASE,
			hoje=date(2026, 1, 1),
		)
		self.assertNotIn("data_estimada", _etapa(etapas, "dados_para_registro_enviados"))

	def test_etapa_sem_intervalo_configurado_nao_estima(self):
		etapas = recepcao_funil.calcular_etapas(
			{"tipo_de_registro": "Definitivo"}, CONFIG, BASE, hoje=date(2026, 1, 1)
		)
		# 'visita_agendada' não tem intervalo em FIELD_INTERVAL_MAP
		self.assertNotIn("data_estimada", _etapa(etapas, "visita_agendada"))


class TestResumoEtapas(TestCase):
	def test_consolida_progresso_e_proxima_etapa(self):
		dados = {
			"tipo_de_registro": "Definitivo",
			"visita_agendada": 1,
			"primeira_visita_realizada": 1,
		}
		etapas = recepcao_funil.calcular_etapas(dados, CONFIG, BASE, hoje=date(2026, 2, 1))
		resumo = recepcao_funil.resumo_etapas(etapas)

		self.assertEqual(resumo["total"], len(recepcao_funil.STEPS_DEF) - 2)
		self.assertEqual(resumo["concluidas"], 2)
		self.assertEqual(resumo["proxima_etapa"], "dados_para_registro_enviados")
		self.assertEqual(resumo["proxima_etapa_rotulo"], "Dados Enviados")
		self.assertIn("dados_para_registro_enviados", resumo["etapas_atrasadas"])

	def test_tudo_concluido_nao_tem_proxima_etapa(self):
		dados = {"tipo_de_registro": "Definitivo"}
		dados.update({campo: 1 for campo in recepcao_funil.CAMPOS_DE_ETAPA})
		resumo = recepcao_funil.resumo_etapas(recepcao_funil.calcular_etapas(dados, CONFIG, BASE))

		self.assertEqual(resumo["pendentes"], 0)
		self.assertIsNone(resumo["proxima_etapa"])
		self.assertEqual(resumo["atrasadas"], 0)
