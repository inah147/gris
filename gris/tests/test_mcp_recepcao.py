"""Testes das ferramentas MCP do funil de recepção."""

from datetime import date
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from gris.api.mcp import recepcao
from gris.api.mcp.registry import ErroDeFerramenta

CONFIG = {"dados_para_registro_enviados": 5, "registro_criado_no_paxtu": 10}


def _pessoa(name, **campos):
	base = {
		"name": name,
		"nome_completo": f"Pessoa {name}",
		"status": "Aguardar Dados",
		"ramo": "Lobinho",
		"tipo_de_registro": "Definitivo",
		"responsavel_recepcao": "ana@example.com",
	}
	base.update(campos)
	return base


def _visita(jovem, data=date(2026, 1, 3), confirmada=1):
	return SimpleNamespace(
		name=f"VIS-{jovem}",
		jovem=jovem,
		data_da_visita=data,
		visita_confirmada=confirmada,
	)


class TestListarNovosAssociados(TestCase):
	def test_filtros_viram_where_e_etapa_pendente_e_validada(self):
		with (
			patch.object(recepcao.frappe, "get_all", return_value=[]) as get_all,
			patch.object(recepcao, "carregar_configuracao", return_value=CONFIG),
			patch.object(recepcao, "data_da_ultima_visita", return_value={}),
		):
			recepcao.listar_novos_associados(
				status="Aguardar Dados", ramo="Lobinho", etapa_pendente="ficha_medica_preenchida"
			)

		filtros = get_all.call_args.kwargs["filters"]
		self.assertEqual(filtros["status"], "Aguardar Dados")
		self.assertEqual(filtros["ficha_medica_preenchida"], 0)
		# Quem desistiu está desativado e fica fora do funil
		self.assertEqual(filtros["desistiu"], 0)

	def test_etapa_inexistente(self):
		with self.assertRaises(ErroDeFerramenta) as ctx:
			recepcao.listar_novos_associados(etapa_pendente="etapa_fantasma")
		self.assertEqual(ctx.exception.codigo, "ARGUMENTO_INVALIDO")

	def test_sem_responsavel_filtra_vazios(self):
		with (
			patch.object(recepcao.frappe, "get_all", return_value=[]) as get_all,
			patch.object(recepcao, "carregar_configuracao", return_value=CONFIG),
			patch.object(recepcao, "data_da_ultima_visita", return_value={}),
		):
			recepcao.listar_novos_associados(sem_responsavel=True)

		self.assertEqual(get_all.call_args.kwargs["filters"]["responsavel_recepcao"], ["in", [None, ""]])

	def test_somente_atrasados_filtra_pelo_progresso_calculado(self):
		registros = [_pessoa("NA-1"), _pessoa("NA-2")]
		visitas = {"NA-1": _visita("NA-1")}
		with (
			patch.object(recepcao.frappe, "get_all", return_value=registros),
			patch.object(recepcao, "carregar_configuracao", return_value=CONFIG),
			patch.object(recepcao, "data_da_ultima_visita", return_value=visitas),
			patch.object(recepcao, "getdate", return_value=date(2026, 6, 1)),
		):
			resultado = recepcao.listar_novos_associados(somente_atrasados=True)

		# NA-2 não tem visita, então não há data estimada nem atraso.
		self.assertEqual([p["name"] for p in resultado["novos_associados"]], ["NA-1"])
		self.assertEqual(resultado["paginacao"]["total_com_filtros"], 1)

	def test_lista_traz_progresso_e_esconde_campos_de_etapa(self):
		registros = [_pessoa("NA-1", visita_agendada=1)]
		with (
			patch.object(recepcao.frappe, "get_all", return_value=registros),
			patch.object(recepcao, "carregar_configuracao", return_value=CONFIG),
			patch.object(recepcao, "data_da_ultima_visita", return_value={"NA-1": _visita("NA-1")}),
			patch.object(recepcao, "getdate", return_value=date(2026, 1, 5)),
		):
			resultado = recepcao.listar_novos_associados()

		pessoa = resultado["novos_associados"][0]
		self.assertNotIn("visita_agendada", pessoa)
		self.assertEqual(pessoa["progresso"]["concluidas"], 1)
		self.assertEqual(pessoa["progresso"]["proxima_etapa"], "primeira_visita_realizada")
		self.assertTrue(pessoa["visita"]["confirmada"])
		self.assertEqual(pessoa["etapas"][0]["etapa"], "visita_agendada")


class TestFunilRecepcao(TestCase):
	def test_consolida_status_ramo_e_gargalos(self):
		registros = [
			_pessoa("NA-1", ramo="Lobinho"),
			_pessoa("NA-2", ramo="Escoteiro", status="Fazer Registro", responsavel_recepcao=None),
		]
		visitas = {"NA-1": _visita("NA-1")}
		with (
			patch.object(recepcao.frappe, "get_all", return_value=registros),
			patch.object(recepcao, "carregar_configuracao", return_value=CONFIG),
			patch.object(recepcao, "data_da_ultima_visita", return_value=visitas),
			patch.object(recepcao, "getdate", return_value=date(2026, 6, 1)),
		):
			resultado = recepcao.funil_recepcao()

		self.assertEqual(resultado["total_no_funil"], 2)
		self.assertEqual(resultado["com_etapa_atrasada"], 1)
		self.assertEqual(resultado["sem_visita_agendada"], 1)
		self.assertEqual(resultado["por_ramo"], {"Lobinho": 1, "Escoteiro": 1})
		self.assertEqual(resultado["por_responsavel"]["(sem responsável)"], 1)
		self.assertEqual(resultado["gargalos"][0]["etapa"], "dados_para_registro_enviados")
		self.assertEqual(resultado["gargalos"][0]["rotulo"], "Dados Enviados")


class TestAtualizarEtapa(TestCase):
	def test_etapa_invalida(self):
		with patch.object(recepcao.frappe.db, "exists", return_value=True):
			with self.assertRaises(ErroDeFerramenta):
				recepcao.atualizar_etapa_recepcao("NA-1", "etapa_fantasma")

	def test_estado_igual_nao_grava(self):
		with (
			patch.object(recepcao.frappe.db, "exists", return_value=True),
			patch.object(recepcao.frappe.db, "get_value", return_value=1),
		):
			resultado = recepcao.atualizar_etapa_recepcao("NA-1", "ficha_medica_preenchida", True)

		self.assertFalse(resultado["atualizado"])

	def test_simulacao_anuncia_efeito_colateral(self):
		with (
			patch.object(recepcao.frappe.db, "exists", return_value=True),
			patch.object(recepcao.frappe.db, "get_value", return_value=0),
		):
			resultado = recepcao.atualizar_etapa_recepcao(
				"NA-1", "registro_criado_no_paxtu", True, simular=True
			)

		self.assertTrue(resultado["simulacao"])
		self.assertIn("Acompanhamento", resultado["efeito_colateral"])

	def test_paxtu_usa_o_servico_que_move_o_status(self):
		from gris.www.recepcao import visao_geral

		with (
			patch.object(recepcao.frappe.db, "exists", return_value=True),
			patch.object(recepcao.frappe.db, "get_value", return_value=0),
			patch.object(visao_geral, "confirmar_registro_paxtu") as paxtu,
			patch.object(visao_geral, "update_step_status") as generico,
		):
			recepcao.atualizar_etapa_recepcao("NA-1", "registro_criado_no_paxtu", True)

		paxtu.assert_called_once_with("NA-1")
		generico.assert_not_called()

	def test_primeira_visita_usa_registrar_recepcao_realizada(self):
		with (
			patch.object(recepcao.frappe.db, "exists", return_value=True),
			patch.object(recepcao.frappe.db, "get_value", return_value=0),
			patch.object(recepcao.servico, "registrar_recepcao_realizada") as servico,
		):
			recepcao.atualizar_etapa_recepcao("NA-1", "primeira_visita_realizada", True)

		servico.assert_called_once_with("NA-1")

	def test_demais_etapas_usam_update_step_status(self):
		from gris.www.recepcao import visao_geral

		with (
			patch.object(recepcao.frappe.db, "exists", return_value=True),
			patch.object(recepcao.frappe.db, "get_value", return_value=0),
			patch.object(visao_geral, "update_step_status") as generico,
		):
			recepcao.atualizar_etapa_recepcao("NA-1", "ficha_medica_preenchida", True)

		generico.assert_called_once_with("NA-1", "ficha_medica_preenchida", 1)


class TestAtualizarNovoAssociado(TestCase):
	def test_exige_algum_campo(self):
		with patch.object(recepcao.frappe.db, "exists", return_value=True):
			with self.assertRaises(ErroDeFerramenta):
				recepcao.atualizar_novo_associado("NA-1")

	def test_responsavel_precisa_ter_o_papel_recepcao(self):
		with (
			patch.object(recepcao.frappe.db, "exists", return_value=True),
			patch.object(recepcao.frappe, "get_roles", return_value=["Gestor de Associados"]),
		):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				recepcao.atualizar_novo_associado("NA-1", responsavel_recepcao="bruno@example.com")

		self.assertEqual(ctx.exception.codigo, "VALIDACAO")

	def test_simulacao_nao_delega(self):
		with (
			patch.object(recepcao.frappe.db, "exists", return_value=True),
			patch.object(recepcao.frappe.db, "get_value", return_value={"status": "Novo Contato"}),
			patch.object(recepcao.servico, "update_novo_associado") as servico,
		):
			resultado = recepcao.atualizar_novo_associado("NA-1", status="Conversa Inicial", simular=True)

		servico.assert_not_called()
		self.assertEqual(
			resultado["alteracoes"]["status"], {"de": "Novo Contato", "para": "Conversa Inicial"}
		)

	def test_execucao_delega(self):
		with (
			patch.object(recepcao.frappe.db, "exists", return_value=True),
			patch.object(recepcao.frappe.db, "get_value", return_value={"status": "Novo Contato"}),
			patch.object(recepcao.servico, "update_novo_associado") as servico,
		):
			recepcao.atualizar_novo_associado("NA-1", status="Conversa Inicial")

		servico.assert_called_once_with("NA-1", status="Conversa Inicial")


class TestFilaDeEspera(TestCase):
	def test_envio_para_fila_ja_na_fila(self):
		with (
			patch.object(recepcao.frappe.db, "exists", return_value=True),
			patch.object(
				recepcao.frappe.db, "get_value", return_value={"status": "Fila de espera", "ramo": "Lobinho"}
			),
		):
			resultado = recepcao.enviar_para_fila_espera("NA-1")

		self.assertFalse(resultado["enviado"])

	def test_envio_para_fila_delega(self):
		with (
			patch.object(recepcao.frappe.db, "exists", return_value=True),
			patch.object(
				recepcao.frappe.db, "get_value", return_value={"status": "Novo Contato", "ramo": "Lobinho"}
			),
			patch.object(recepcao.servico, "enviar_para_fila_espera") as servico,
		):
			resultado = recepcao.enviar_para_fila_espera("NA-1")

		servico.assert_called_once_with("NA-1")
		self.assertTrue(resultado["enviado"])

	def test_lista_numera_a_posicao_por_ramo(self):
		fila = [
			{"name": "F1", "associado": "NA-1", "ramo": "Lobinho", "dt_inclusao_fila": "2026-01-01"},
			{"name": "F2", "associado": "NA-2", "ramo": "Lobinho", "dt_inclusao_fila": "2026-02-01"},
			{"name": "F3", "associado": "NA-3", "ramo": "Escoteiro", "dt_inclusao_fila": "2026-01-15"},
		]
		pessoas = [
			{"name": "NA-1", "nome_completo": "Ana"},
			{"name": "NA-2", "nome_completo": "Bruno"},
			{"name": "NA-3", "nome_completo": "Carla"},
		]
		with (
			patch.object(recepcao.frappe, "get_all", side_effect=[fila, pessoas]),
			patch.object(recepcao.servico, "nomes_desistentes", return_value=set()),
		):
			resultado = recepcao.listar_fila_espera()

		self.assertEqual(resultado["fila"][1]["posicao_no_ramo"], 2)
		self.assertEqual(resultado["fila"][2]["posicao_no_ramo"], 1)
		self.assertEqual(resultado["fila"][0]["nome_completo"], "Ana")

	def test_quem_desistiu_sai_da_fila_listada(self):
		fila = [
			{"name": "F1", "associado": "NA-1", "ramo": "Lobinho", "dt_inclusao_fila": "2026-01-01"},
			{"name": "F2", "associado": "NA-2", "ramo": "Lobinho", "dt_inclusao_fila": "2026-02-01"},
		]
		pessoas = [{"name": "NA-2", "nome_completo": "Bruno"}]
		with (
			patch.object(recepcao.frappe, "get_all", side_effect=[fila, pessoas]),
			patch.object(recepcao.servico, "nomes_desistentes", return_value={"NA-1"}),
		):
			resultado = recepcao.listar_fila_espera()

		self.assertEqual(resultado["total"], 1)
		self.assertEqual(resultado["fila"][0]["associado"], "NA-2")

	def test_chamar_da_fila_inexistente(self):
		with patch.object(recepcao.frappe.db, "get_value", return_value=None):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				recepcao.chamar_da_fila_espera("F9")
		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")

	def test_chamar_da_fila_simulado_e_real(self):
		from gris.www.recepcao import fila_espera

		dados = {"name": "F1", "associado": "NA-1", "ramo": "Lobinho"}
		with (
			patch.object(recepcao.frappe.db, "get_value", return_value=dados),
			patch.object(fila_espera, "chamar_associado") as servico,
		):
			simulado = recepcao.chamar_da_fila_espera("F1", simular=True)
			real = recepcao.chamar_da_fila_espera("F1")

		servico.assert_called_once_with("F1")
		self.assertTrue(simulado["simulacao"])
		self.assertEqual(real["novo_associado"], "NA-1")


class TestComentario(TestCase):
	def test_texto_vazio(self):
		with patch.object(recepcao.frappe.db, "exists", return_value=True):
			with self.assertRaises(ErroDeFerramenta):
				recepcao.comentar_novo_associado("NA-1", "   ")

	def test_delega_para_o_servico(self):
		with (
			patch.object(recepcao.frappe.db, "exists", return_value=True),
			patch.object(recepcao.servico, "adicionar_comentario", return_value={"name": "C1"}) as servico,
		):
			resultado = recepcao.comentar_novo_associado("NA-1", "Família pediu retorno em maio")

		servico.assert_called_once_with("NA-1", "Família pediu retorno em maio")
		self.assertTrue(resultado["comentado"])


class TestNps(TestCase):
	def test_consolida_promotores_e_detratores(self):
		respostas = [
			{"nps_recepcao": "10"},
			{"nps_recepcao": "9"},
			{"nps_recepcao": "8"},
			{"nps_recepcao": "5"},
			{"nps_recepcao": None},
		]
		from gris.www.recepcao import pesquisa_novos_respostas

		with (
			patch.object(pesquisa_novos_respostas, "get_nps_chart_data", return_value={"labels": []}),
			patch.object(recepcao.frappe, "get_all", return_value=respostas),
		):
			resultado = recepcao.nps_recepcao()

		consolidado = resultado["consolidado_geral"]
		self.assertEqual(consolidado["respostas_com_nota"], 4)
		self.assertEqual(consolidado["promotores"], 2)
		self.assertEqual(consolidado["neutros"], 1)
		self.assertEqual(consolidado["detratores"], 1)
		self.assertEqual(consolidado["nps"], 25.0)

	def test_sem_respostas_nao_divide_por_zero(self):
		from gris.www.recepcao import pesquisa_novos_respostas

		with (
			patch.object(pesquisa_novos_respostas, "get_nps_chart_data", return_value={}),
			patch.object(recepcao.frappe, "get_all", return_value=[]),
		):
			resultado = recepcao.nps_recepcao()

		self.assertIsNone(resultado["consolidado_geral"]["nps"])
