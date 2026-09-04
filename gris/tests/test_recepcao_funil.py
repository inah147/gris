"""Testes do cálculo do funil de recepção (etapas, cadência e atraso).

Mesma regra usada pelo kanban de /recepcao/visao_geral e pelas ferramentas MCP.
"""

from datetime import date
from unittest import TestCase
from unittest.mock import patch

import frappe

from gris.api import recepcao, recepcao_funil
from gris.www.recepcao import visao_geral

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
		self.assertEqual(len(definitivo), len(recepcao_funil.STEPS_DEF) - 1)
		self.assertNotIn("registro_provisorio_efetivado", campos_definitivo)

	def test_etapas_de_pagamento_foram_removidas_do_fluxo(self):
		campos = [etapa["field"] for etapa in recepcao_funil.STEPS_DEF]
		self.assertNotIn("registro_provisorio_pago", campos)
		self.assertNotIn("registro_definitivo_pago", campos)
		self.assertNotIn("registro_provisorio_pago", recepcao_funil.FIELD_INTERVAL_MAP)
		self.assertNotIn("registro_definitivo_pago", recepcao_funil.FIELD_INTERVAL_MAP)

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

		self.assertEqual(resumo["total"], len(recepcao_funil.STEPS_DEF) - 1)
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


class TestColunaDeAcompanhamento(TestCase):
	"""A lista provisória e a definitiva saem dos dados, não do campo ``status``."""

	def test_provisorio_pendente_fica_na_lista_provisoria(self):
		self.assertEqual(
			recepcao_funil.coluna_de_acompanhamento(
				{"tipo_de_registro": "Provisório", "registro_provisorio_efetivado": 0}
			),
			recepcao_funil.COLUNA_ACOMPANHAMENTO_PROVISORIO,
		)

	def test_provisorio_efetivado_migra_para_a_lista_definitiva(self):
		self.assertEqual(
			recepcao_funil.coluna_de_acompanhamento(
				{"tipo_de_registro": "Provisório", "registro_provisorio_efetivado": 1}
			),
			recepcao_funil.COLUNA_ACOMPANHAMENTO_DEFINITIVO,
		)

	def test_quem_entra_como_definitivo_nunca_passa_pela_provisoria(self):
		self.assertEqual(
			recepcao_funil.coluna_de_acompanhamento(
				{"tipo_de_registro": "Definitivo", "registro_provisorio_efetivado": 0}
			),
			recepcao_funil.COLUNA_ACOMPANHAMENTO_DEFINITIVO,
		)


class TestAnexarHistorico(TestCase):
	def test_so_etapas_concluidas_recebem_data_e_autor(self):
		etapas = [
			{"field": "visita_agendada", "completed": True},
			{"field": "ficha_medica_preenchida", "completed": False},
		]
		historico = {
			"visita_agendada": {"concluida_em": "2026-01-05 10:00:00", "concluido_por": "ana@x.com"},
			"ficha_medica_preenchida": {"concluida_em": "2026-01-06 10:00:00", "concluido_por": "bo@x.com"},
		}

		recepcao_funil.anexar_historico(etapas, historico)

		self.assertEqual(etapas[0]["concluida_em"], "2026-01-05 10:00:00")
		self.assertEqual(etapas[0]["concluido_por"], "ana@x.com")
		self.assertNotIn("concluida_em", etapas[1])

	def test_etapa_concluida_sem_historico_nao_inventa_data(self):
		etapas = [{"field": "visita_agendada", "completed": True}]

		recepcao_funil.anexar_historico(etapas, {})

		self.assertNotIn("concluida_em", etapas[0])
		self.assertNotIn("concluido_por", etapas[0])


class TestNumerosDeRegistro(TestCase):
	"""Quem precisa de número de registro, e o que a ficha pode editar."""

	def _pendentes(self, numero_do_jovem, responsaveis):
		with (
			patch.object(recepcao.frappe.db, "get_value", return_value=numero_do_jovem),
			patch.object(recepcao, "_vinculos_do_novo_associado", return_value=responsaveis),
		):
			return recepcao.numeros_de_registro_pendentes("NA-1")

	def test_jovem_sem_numero_e_sempre_pendencia(self):
		self.assertEqual(self._pendentes("", []), ["o jovem"])
		self.assertEqual(self._pendentes("   ", []), ["o jovem"])

	def test_responsavel_so_pendencia_quando_sera_registrado(self):
		responsaveis = [
			{"nome": "Vai registrar", "numero_de_registro": "", "sera_registrado": True},
			{"nome": "Não registra", "numero_de_registro": "", "sera_registrado": False},
		]
		self.assertEqual(self._pendentes("A-1", responsaveis), ["Vai registrar"])

	def test_tudo_preenchido_nao_tem_pendencia(self):
		responsaveis = [{"nome": "Vai registrar", "numero_de_registro": "B-2", "sera_registrado": True}]
		self.assertEqual(self._pendentes("A-1", responsaveis), [])


class TestSalvarNumerosDeRegistro(TestCase):
	"""A ficha precisa poder corrigir — inclusive apagar — um número errado.

	A exigência do número vive na trava da etapa de efetivação, não na gravação:
	se ``salvar_numeros_de_registro`` recusasse valor vazio, não haveria como
	desfazer um número digitado errado pela ficha de registro.
	"""

	def test_numero_vazio_do_jovem_e_aceito_e_grava_none(self):
		gravados = []

		def _set_value(doctype, name, campo, valor):
			gravados.append((doctype, name, campo, valor))

		with (
			patch.object(recepcao.frappe, "has_permission", return_value=True),
			patch.object(recepcao.frappe.db, "set_value", side_effect=_set_value),
			patch.object(recepcao, "_vinculos_do_novo_associado", return_value=[]),
			patch.object(recepcao, "numeros_de_registro_pendentes", return_value=["o jovem"]),
		):
			resultado = recepcao.salvar_numeros_de_registro("NA-1", "   ")

		self.assertEqual(gravados, [("Novo Associado", "NA-1", "numero_de_registro", None)])
		self.assertEqual(resultado["pendentes"], ["o jovem"])

	def test_responsavel_fora_do_vinculo_e_recusado(self):
		with (
			patch.object(recepcao.frappe, "has_permission", return_value=True),
			patch.object(recepcao.frappe.db, "set_value"),
			patch.object(recepcao, "_vinculos_do_novo_associado", return_value=[]),
		):
			with self.assertRaises(frappe.PermissionError):
				recepcao.salvar_numeros_de_registro("NA-1", "A-1", {"outro-responsavel": "9"})

	def test_sem_permissao_de_escrita_nao_grava(self):
		with (
			patch.object(recepcao.frappe, "has_permission", return_value=False),
			patch.object(recepcao.frappe.db, "set_value") as set_value,
		):
			with self.assertRaises(frappe.PermissionError):
				recepcao.salvar_numeros_de_registro("NA-1", "A-1")

		set_value.assert_not_called()


class _DocFalso:
	"""Novo Associado suficiente para observar o que ``update_step_status`` grava."""

	def __init__(self, status="Aguardar Dados"):
		self.status = status
		self.campos = {}
		self.salvo = False

	def set(self, campo, valor):
		self.campos[campo] = valor

	def save(self):
		self.salvo = True


class TestUpdateStepStatus(TestCase):
	"""Marcar a etapa pela bolinha da timeline tem que mover a coluna do funil.

	Antes a virada de status só acontecia nos atalhos (botão do Paxtu, botão de recepção
	realizada, formulário do responsável), e quem usava a timeline ficava com o card parado.
	"""

	def _executar(self, campo, valor=1, status_inicial="Aguardar Dados"):
		doc = _DocFalso(status_inicial)
		with patch.object(visao_geral.frappe, "get_doc", return_value=doc):
			visao_geral.update_step_status("NA-1", campo, valor)
		return doc

	def test_cada_etapa_de_virada_move_o_status(self):
		for campo, status in visao_geral.STATUS_POR_ETAPA.items():
			with self.subTest(etapa=campo):
				doc = self._executar(campo, status_inicial="Novo Contato")

				self.assertEqual(doc.campos[campo], 1)
				self.assertEqual(doc.status, status)
				self.assertTrue(doc.salvo)

	def test_etapa_fora_do_mapa_nao_mexe_no_status(self):
		doc = self._executar("ficha_medica_preenchida", status_inicial="Acompanhamento")

		self.assertEqual(doc.campos["ficha_medica_preenchida"], 1)
		self.assertEqual(doc.status, "Acompanhamento")

	def test_desmarcar_nao_reverte_o_status(self):
		doc = self._executar("registro_criado_no_paxtu", valor=0, status_inicial="Acompanhamento")

		self.assertEqual(doc.campos["registro_criado_no_paxtu"], 0)
		self.assertEqual(doc.status, "Acompanhamento")

	def test_botao_do_paxtu_faz_o_mesmo_que_a_bolinha(self):
		doc = _DocFalso("Fazer Registro")
		with patch.object(visao_geral.frappe, "get_doc", return_value=doc):
			visao_geral.confirmar_registro_paxtu("NA-1")

		self.assertEqual(doc.campos["registro_criado_no_paxtu"], 1)
		self.assertEqual(doc.status, "Acompanhamento")

	def test_campo_invalido_e_recusado(self):
		with self.assertRaises(frappe.ValidationError):
			visao_geral.update_step_status("NA-1", "status", 1)

	def test_sem_registro_informado_e_recusado(self):
		with self.assertRaises(frappe.ValidationError):
			visao_geral.update_step_status("", "registro_criado_no_paxtu", 1)


class TestTravaDeEfetivacao(TestCase):
	"""Marcar registro efetivado exige o número de registro em mãos."""

	def test_etapa_de_efetivacao_e_recusada_sem_numero_de_registro(self):
		for campo in recepcao_funil.CAMPOS_DE_EFETIVACAO:
			with self.subTest(etapa=campo):
				with patch.object(visao_geral, "numeros_de_registro_pendentes", return_value=["o jovem"]):
					with self.assertRaises(frappe.ValidationError):
						visao_geral.update_step_status("NA-1", campo, 1)

	def test_etapa_de_efetivacao_passa_com_os_numeros_preenchidos(self):
		doc = _DocFalso("Acompanhamento")
		with (
			patch.object(visao_geral, "numeros_de_registro_pendentes", return_value=[]),
			patch.object(visao_geral.frappe, "get_doc", return_value=doc),
		):
			visao_geral.update_step_status("NA-1", "registro_definitivo_efetivado", 1)

		self.assertEqual(doc.campos["registro_definitivo_efetivado"], 1)
		self.assertTrue(doc.salvo)

	def test_desmarcar_efetivacao_nao_exige_numero(self):
		doc = _DocFalso("Acompanhamento")
		with (
			patch.object(visao_geral, "numeros_de_registro_pendentes", return_value=["o jovem"]) as pendentes,
			patch.object(visao_geral.frappe, "get_doc", return_value=doc),
		):
			visao_geral.update_step_status("NA-1", "registro_definitivo_efetivado", 0)

		pendentes.assert_not_called()
		self.assertEqual(doc.campos["registro_definitivo_efetivado"], 0)
