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


def _campos(etapas):
	return [etapa["field"] for etapa in etapas]


class TestCalcularEtapas(TestCase):
	def test_registro_definitivo_nao_tem_as_etapas_do_provisorio(self):
		provisorio = recepcao_funil.calcular_etapas({"tipo_de_registro": "Provisório"}, CONFIG)
		definitivo = recepcao_funil.calcular_etapas({"tipo_de_registro": "Definitivo"}, CONFIG)

		campos_definitivo = _campos(definitivo)
		self.assertEqual(len(provisorio), len(recepcao_funil.STEPS_DEF))
		self.assertEqual(len(definitivo), len(recepcao_funil.STEPS_DEF) - 2)
		self.assertNotIn("boleto_provisorio_gerado", campos_definitivo)
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


class TestEtapaBoletoDefinitivo(TestCase):
	"""A emissão do boleto do registro definitivo é etapa própria, antes da efetivação.

	É o que deixa visível a fila entre gerar o boleto e o registro sair: boleto marcado e
	efetivação pendente é boleto esperando pagamento.
	"""

	def test_boleto_vem_imediatamente_antes_da_efetivacao_definitiva(self):
		for tipo in ("Provisório", "Definitivo"):
			with self.subTest(tipo=tipo):
				campos = _campos(recepcao_funil.etapas_do_fluxo(tipo))

				self.assertEqual(
					campos.index("boleto_definitivo_gerado") + 1,
					campos.index("registro_definitivo_efetivado"),
				)

	def test_boleto_aparece_nos_dois_tipos_de_registro(self):
		for tipo in ("Provisório", "Definitivo"):
			with self.subTest(tipo=tipo):
				etapas = recepcao_funil.calcular_etapas({"tipo_de_registro": tipo}, CONFIG)
				campos = [etapa["field"] for etapa in etapas]

				self.assertIn("boleto_definitivo_gerado", campos)

	def test_intervalo_do_boleto_empurra_a_data_da_efetivacao(self):
		config = {**CONFIG, "boleto_definitivo_gerado": 4, "registro_definitivo_efetivado": 6}
		etapas = recepcao_funil.calcular_etapas(
			{"tipo_de_registro": "Definitivo"}, config, BASE, hoje=date(2026, 1, 1)
		)

		boleto = _etapa(etapas, "boleto_definitivo_gerado")["data_estimada"]
		efetivacao = _etapa(etapas, "registro_definitivo_efetivado")["data_estimada"]

		# No Definitivo o boleto vem logo depois do Paxtu (2026-01-18).
		self.assertEqual(boleto, "2026-01-22")
		self.assertEqual(efetivacao, "2026-01-28")

	def test_boleto_nao_e_etapa_de_efetivacao_nem_move_a_coluna(self):
		# Marcar o boleto não exige número de registro (isso é da efetivação) e não
		# empurra o card para outra lista do kanban.
		self.assertNotIn("boleto_definitivo_gerado", recepcao_funil.CAMPOS_DE_EFETIVACAO)
		self.assertNotIn("boleto_definitivo_gerado", dict(recepcao_funil.ETAPAS_QUE_MOVEM_O_FUNIL))

	def test_marcar_o_boleto_pela_timeline_nao_pede_numero_de_registro(self):
		doc = _DocFalso("Acompanhamento")
		with (
			patch.object(visao_geral, "numeros_de_registro_pendentes", return_value=["o jovem"]) as pendentes,
			patch.object(visao_geral.frappe, "get_doc", return_value=doc),
		):
			visao_geral.update_step_status("NA-1", "boleto_definitivo_gerado", 1)

		pendentes.assert_not_called()
		self.assertEqual(doc.campos["boleto_definitivo_gerado"], 1)
		self.assertEqual(doc.status, "Acompanhamento")
		self.assertTrue(doc.salvo)


class TestEtapaBoletoProvisorio(TestCase):
	"""O registro provisório também é pago: o boleto dele é etapa própria, antes da efetivação."""

	def test_boleto_provisorio_vem_entre_o_paxtu_e_a_efetivacao_provisoria(self):
		campos = _campos(recepcao_funil.etapas_do_fluxo("Provisório"))

		self.assertEqual(
			campos.index("registro_criado_no_paxtu") + 1,
			campos.index("boleto_provisorio_gerado"),
		)
		self.assertEqual(
			campos.index("boleto_provisorio_gerado") + 1,
			campos.index("registro_provisorio_efetivado"),
		)

	def test_intervalo_do_boleto_provisorio_vem_da_configuracao(self):
		config = {**CONFIG, "boleto_provisorio_gerado": 2}
		etapas = recepcao_funil.calcular_etapas(
			{"tipo_de_registro": "Provisório"}, config, BASE, hoje=date(2026, 1, 1)
		)

		# Paxtu em 2026-01-18, mais os 2 dias do boleto.
		self.assertEqual(_etapa(etapas, "boleto_provisorio_gerado")["data_estimada"], "2026-01-20")

	def test_boleto_provisorio_nao_e_etapa_de_efetivacao_nem_move_a_coluna(self):
		self.assertNotIn("boleto_provisorio_gerado", recepcao_funil.CAMPOS_DE_EFETIVACAO)
		self.assertNotIn("boleto_provisorio_gerado", dict(recepcao_funil.ETAPAS_QUE_MOVEM_O_FUNIL))

	def test_marcar_o_boleto_provisorio_pela_timeline_nao_pede_numero_de_registro(self):
		doc = _DocFalso("Acompanhamento")
		with (
			patch.object(visao_geral, "numeros_de_registro_pendentes", return_value=["o jovem"]) as pendentes,
			patch.object(visao_geral.frappe, "get_doc", return_value=doc),
		):
			visao_geral.update_step_status("NA-1", "boleto_provisorio_gerado", 1)

		pendentes.assert_not_called()
		self.assertEqual(doc.campos["boleto_provisorio_gerado"], 1)
		self.assertEqual(doc.status, "Acompanhamento")
		self.assertTrue(doc.salvo)


class TestOrdemDasEtapasPorTipo(TestCase):
	"""Quem entra direto no definitivo efetiva o registro logo depois do Paxtu.

	É o número de registro que abre a ficha médica no Paxtu; pesquisa, ficha, id@escoteiros
	e acolhida ficam para depois, e são o que o "Acompanhamento Final" acompanha.
	"""

	def test_ordem_do_provisorio(self):
		self.assertEqual(
			_campos(recepcao_funil.etapas_do_fluxo("Provisório")),
			[
				"visita_agendada",
				"primeira_visita_realizada",
				"dados_para_registro_enviados",
				"registro_criado_no_paxtu",
				"boleto_provisorio_gerado",
				"registro_provisorio_efetivado",
				"pesquisa_de_novos_associados_respondida",
				"ficha_medica_preenchida",
				"id_escoteiros_criado",
				"boleto_definitivo_gerado",
				"registro_definitivo_efetivado",
				"reuniao_de_acolhida_realizada",
			],
		)

	def test_ordem_do_definitivo(self):
		self.assertEqual(
			_campos(recepcao_funil.etapas_do_fluxo("Definitivo")),
			[
				"visita_agendada",
				"primeira_visita_realizada",
				"dados_para_registro_enviados",
				"registro_criado_no_paxtu",
				"boleto_definitivo_gerado",
				"registro_definitivo_efetivado",
				"pesquisa_de_novos_associados_respondida",
				"ficha_medica_preenchida",
				"id_escoteiros_criado",
				"reuniao_de_acolhida_realizada",
			],
		)

	def test_tipo_ainda_nao_escolhido_segue_o_provisorio(self):
		for tipo in (None, ""):
			with self.subTest(tipo=tipo):
				self.assertEqual(
					recepcao_funil.etapas_do_fluxo(tipo),
					recepcao_funil.etapas_do_fluxo("Provisório"),
				)

	def test_ordem_do_definitivo_tem_todas_as_etapas_menos_as_do_provisorio(self):
		# Etapa nova em STEPS_DEF esquecida em ORDEM_DEFINITIVO sumiria do funil de quem
		# entra direto no definitivo, sem erro nenhum.
		esperadas = [
			campo
			for campo in recepcao_funil.CAMPOS_DE_ETAPA
			if campo not in recepcao_funil.ETAPAS_DO_PROVISORIO
		]

		self.assertCountEqual(recepcao_funil.ORDEM_DEFINITIVO, esperadas)
		self.assertEqual(len(recepcao_funil.ORDEM_DEFINITIVO), len(set(recepcao_funil.ORDEM_DEFINITIVO)))

	def test_datas_estimadas_do_definitivo_seguem_a_ordem_dele(self):
		config = {**CONFIG, "boleto_definitivo_gerado": 2, "registro_definitivo_efetivado": 3}
		etapas = recepcao_funil.calcular_etapas(
			{"tipo_de_registro": "Definitivo"}, config, BASE, hoje=date(2026, 1, 1)
		)

		# Paxtu em 2026-01-18 → boleto +2 → efetivação +3 → pesquisa +3.
		self.assertEqual(_etapa(etapas, "boleto_definitivo_gerado")["data_estimada"], "2026-01-20")
		self.assertEqual(_etapa(etapas, "registro_definitivo_efetivado")["data_estimada"], "2026-01-23")
		self.assertEqual(
			_etapa(etapas, "pesquisa_de_novos_associados_respondida")["data_estimada"], "2026-01-26"
		)


class TestResumoEtapas(TestCase):
	def test_consolida_progresso_e_proxima_etapa(self):
		dados = {
			"tipo_de_registro": "Definitivo",
			"visita_agendada": 1,
			"primeira_visita_realizada": 1,
		}
		etapas = recepcao_funil.calcular_etapas(dados, CONFIG, BASE, hoje=date(2026, 2, 1))
		resumo = recepcao_funil.resumo_etapas(etapas)

		self.assertEqual(resumo["total"], len(recepcao_funil.ORDEM_DEFINITIVO))
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

	def test_registro_definitivo_efetivado_vai_para_a_lista_final(self):
		# Nos dois tipos, e com as pendências finais (pesquisa, ficha, id, acolhida) abertas.
		for dados in (
			{"tipo_de_registro": "Definitivo", "registro_definitivo_efetivado": 1},
			{
				"tipo_de_registro": "Provisório",
				"registro_provisorio_efetivado": 1,
				"registro_definitivo_efetivado": 1,
			},
		):
			with self.subTest(tipo=dados["tipo_de_registro"]):
				self.assertEqual(
					recepcao_funil.coluna_de_acompanhamento(dados),
					recepcao_funil.COLUNA_ACOMPANHAMENTO_FINAL,
				)

	def test_boleto_definitivo_sem_efetivacao_continua_na_lista_definitiva(self):
		self.assertEqual(
			recepcao_funil.coluna_de_acompanhamento(
				{"tipo_de_registro": "Definitivo", "boleto_definitivo_gerado": 1}
			),
			recepcao_funil.COLUNA_ACOMPANHAMENTO_DEFINITIVO,
		)

	def test_quem_concluiu_tudo_fica_na_final_para_finalizar_a_recepcao(self):
		dados = {"tipo_de_registro": "Definitivo"}
		dados.update(dict.fromkeys(recepcao_funil.CAMPOS_DE_ETAPA, 1))

		self.assertEqual(
			recepcao_funil.coluna_de_acompanhamento(dados),
			recepcao_funil.COLUNA_ACOMPANHAMENTO_FINAL,
		)


class TestColunasDoKanban(TestCase):
	"""A visão geral monta as três listas de acompanhamento, com a final por último."""

	def _contexto(self, jovens):
		def _get_all(doctype, *args, **kwargs):
			if doctype == "Novo Associado":
				return [frappe._dict(j) for j in jovens]
			return []

		context = frappe._dict()
		with (
			patch.object(visao_geral, "enrich_context"),
			patch.object(visao_geral, "carregar_configuracao", return_value={}),
			patch.object(visao_geral.frappe, "get_all", side_effect=_get_all),
		):
			visao_geral.get_context(context)
		return context

	def test_as_tres_listas_de_acompanhamento_fecham_o_kanban(self):
		context = self._contexto([])

		self.assertEqual(
			context.kanban_columns[-3:],
			["Acompanhamento Provisório", "Acompanhamento Definitivo", "Acompanhamento Final"],
		)
		self.assertEqual(context.colunas_de_acompanhamento, context.kanban_columns[-3:])

	def test_cada_card_de_acompanhamento_cai_na_sua_lista(self):
		base = {"status": "Acompanhamento", "nome_completo": "Jovem"}
		context = self._contexto(
			[
				{**base, "name": "NA-PROV", "tipo_de_registro": "Provisório"},
				{
					**base,
					"name": "NA-DEF",
					"tipo_de_registro": "Provisório",
					"registro_provisorio_efetivado": 1,
				},
				{
					**base,
					"name": "NA-FINAL",
					"tipo_de_registro": "Definitivo",
					"registro_definitivo_efetivado": 1,
				},
			]
		)

		nomes = {coluna: [card.name for card in cards] for coluna, cards in context.kanban_data.items()}
		self.assertEqual(nomes["Acompanhamento Provisório"], ["NA-PROV"])
		self.assertEqual(nomes["Acompanhamento Definitivo"], ["NA-DEF"])
		self.assertEqual(nomes["Acompanhamento Final"], ["NA-FINAL"])

	def test_o_boleto_provisorio_e_buscado_do_banco(self):
		"""Sem o campo na consulta a etapa apareceria sempre pendente — e o erro seria mudo."""
		capturados = {}

		def _get_all(doctype, *args, **kwargs):
			if doctype == "Novo Associado":
				capturados["fields"] = kwargs.get("fields") or []
			return []

		with (
			patch.object(visao_geral, "enrich_context"),
			patch.object(visao_geral, "carregar_configuracao", return_value={}),
			patch.object(visao_geral.frappe, "get_all", side_effect=_get_all),
		):
			visao_geral.get_context(frappe._dict())

		self.assertIn("boleto_provisorio_gerado", capturados["fields"])
		self.assertIn("registro_definitivo_efetivado", capturados["fields"])


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

	def __init__(self, status="Aguardar Dados", **etapas):
		self.status = status
		self.campos = dict(etapas)
		self.salvo = False

	def set(self, campo, valor):
		self.campos[campo] = valor

	def get(self, campo, padrao=None):
		return self.campos.get(campo, padrao)

	def save(self):
		self.salvo = True


class TestUpdateStepStatus(TestCase):
	"""Marcar a etapa pela bolinha da timeline tem que mover a coluna do funil.

	Antes a virada de status só acontecia nos atalhos (botão do Paxtu, botão de recepção
	realizada, formulário do responsável), e quem usava a timeline ficava com o card parado.
	"""

	def _executar(self, campo, valor=1, status_inicial="Aguardar Dados", **etapas):
		doc = _DocFalso(status_inicial, **etapas)
		with (
			patch.object(visao_geral.frappe, "get_doc", return_value=doc),
			patch.object(visao_geral, "remover_visita_do_jovem") as remover,
		):
			visao_geral.update_step_status("NA-1", campo, valor)
		doc.visita_removida = remover.called
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

	def test_desmarcar_devolve_o_card_para_a_etapa_anterior_concluida(self):
		doc = self._executar(
			"registro_criado_no_paxtu",
			valor=0,
			status_inicial="Acompanhamento",
			visita_agendada=1,
			primeira_visita_realizada=1,
			dados_para_registro_enviados=1,
		)

		self.assertEqual(doc.campos["registro_criado_no_paxtu"], 0)
		self.assertEqual(doc.status, "Fazer Registro")

	def test_desmarcar_pula_as_etapas_que_nunca_foram_concluidas(self):
		# Ninguém enviou os dados nem fez a visita: a volta é para "Visita Agendada",
		# não para a coluna imediatamente anterior no mapa.
		doc = self._executar(
			"registro_criado_no_paxtu",
			valor=0,
			status_inicial="Acompanhamento",
			visita_agendada=1,
		)

		self.assertEqual(doc.status, "Visita Agendada")

	def test_desmarcar_a_primeira_etapa_volta_para_conversa_inicial(self):
		doc = self._executar("visita_agendada", valor=0, status_inicial="Visita Agendada")

		self.assertEqual(doc.status, "Conversa Inicial")

	def test_desmarcar_visita_agendada_cancela_a_visita(self):
		doc = self._executar("visita_agendada", valor=0, status_inicial="Visita Agendada")

		self.assertTrue(doc.visita_removida)

	def test_desmarcar_outra_etapa_nao_mexe_na_visita(self):
		doc = self._executar(
			"ficha_medica_preenchida", valor=0, status_inicial="Acompanhamento", visita_agendada=1
		)

		self.assertFalse(doc.visita_removida)

	def test_card_fora_do_funil_nao_e_arrastado_de_volta(self):
		for status in recepcao_funil.STATUS_FORA_DO_FUNIL:
			with self.subTest(status=status):
				doc = self._executar("registro_criado_no_paxtu", valor=0, status_inicial=status)

				self.assertEqual(doc.status, status)

	def test_desmarcar_etapa_sem_coluna_propria_recalcula_pelo_que_sobrou(self):
		doc = self._executar(
			"ficha_medica_preenchida",
			valor=0,
			status_inicial="Acompanhamento",
			visita_agendada=1,
			primeira_visita_realizada=1,
			dados_para_registro_enviados=1,
			registro_criado_no_paxtu=1,
		)

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
