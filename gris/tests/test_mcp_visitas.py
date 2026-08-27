"""Testes das ferramentas MCP da agenda de visitas."""

from unittest import TestCase
from unittest.mock import patch

from gris.api.mcp import visitas
from gris.api.mcp.registry import ErroDeFerramenta
from gris.www.recepcao import agenda_visitas

DATAS_LIVRES = [
	{"value": "2026-03-07", "label": "07/03/2026"},
	{"value": "2026-03-14", "label": "14/03/2026"},
]

VISITA = {
	"name": "VIS-1",
	"jovem": "NA-1",
	"data_da_visita": "2026-03-07",
	"ramo": "Lobinho",
	"visita_confirmada": 0,
}


class TestListarVisitas(TestCase):
	def test_periodo_e_confirmacao_viram_filtros(self):
		with (
			patch.object(visitas.frappe, "get_all", return_value=[]) as get_all,
			patch.object(visitas.frappe.db, "count", return_value=0),
			patch.object(visitas, "nomes_desistentes", return_value=set()),
		):
			visitas.listar_visitas(data_inicio="2026-03-01", data_fim="2026-03-31", confirmada=False)

		filtros = get_all.call_args.kwargs["filters"]
		self.assertEqual(filtros["data_da_visita"], ["between", ["2026-03-01", "2026-03-31"]])
		self.assertEqual(filtros["visita_confirmada"], 0)

	def test_anexa_nome_de_quem_visita(self):
		agendadas = [dict(VISITA)]
		pessoas = [{"name": "NA-1", "nome_completo": "Ana"}]
		with (
			patch.object(visitas.frappe, "get_all", side_effect=[agendadas, pessoas]),
			patch.object(visitas.frappe.db, "count", return_value=1),
			patch.object(visitas, "nomes_desistentes", return_value=set()),
		):
			resultado = visitas.listar_visitas()

		self.assertEqual(resultado["visitas"][0]["nome_completo"], "Ana")

	def test_visitas_de_quem_desistiu_ficam_fora_da_listagem(self):
		with (
			patch.object(visitas.frappe, "get_all", return_value=[]) as get_all,
			patch.object(visitas.frappe.db, "count", return_value=0),
			patch.object(visitas, "nomes_desistentes", return_value={"NA-9"}),
		):
			visitas.listar_visitas()

		self.assertEqual(get_all.call_args.kwargs["filters"]["jovem"], ["not in", ["NA-9"]])


class TestDatasDisponiveis(TestCase):
	def test_exige_ramo_ou_visita(self):
		with self.assertRaises(ErroDeFerramenta):
			visitas.datas_disponiveis_visita()

	def test_por_ramo(self):
		with patch.object(agenda_visitas, "get_available_dates_for_ramo", return_value=DATAS_LIVRES):
			resultado = visitas.datas_disponiveis_visita(ramo="Lobinho")

		self.assertEqual(resultado["total"], 2)

	def test_por_visita_usa_o_endpoint_de_remarcacao(self):
		with (
			patch.object(visitas.frappe.db, "get_value", return_value=dict(VISITA)),
			patch.object(
				agenda_visitas, "get_available_visit_dates_for_reschedule", return_value=DATAS_LIVRES
			) as servico,
		):
			visitas.datas_disponiveis_visita(visita="VIS-1")

		servico.assert_called_once_with("VIS-1")


class TestAgendarVisita(TestCase):
	def test_pessoa_inexistente(self):
		with patch.object(visitas.frappe.db, "get_value", return_value=None):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				visitas.agendar_visita("NA-9", "2026-03-07")
		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")

	def test_pessoa_sem_ramo(self):
		with patch.object(visitas.frappe.db, "get_value", return_value={"name": "NA-1", "ramo": None}):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				visitas.agendar_visita("NA-1", "2026-03-07")
		self.assertIn("ramo", ctx.exception.mensagem)

	def test_data_indisponivel_lista_as_livres(self):
		with (
			patch.object(visitas.frappe.db, "get_value", return_value={"name": "NA-1", "ramo": "Lobinho"}),
			patch.object(agenda_visitas, "get_available_dates_for_ramo", return_value=DATAS_LIVRES),
		):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				visitas.agendar_visita("NA-1", "2026-03-10")

		self.assertEqual(ctx.exception.codigo, "VALIDACAO")
		self.assertIn("2026-03-07", ctx.exception.detalhes["datas_disponiveis"])

	def test_simulacao_valida_mas_nao_agenda(self):
		with (
			patch.object(visitas.frappe.db, "get_value", return_value={"name": "NA-1", "ramo": "Lobinho"}),
			patch.object(agenda_visitas, "get_available_dates_for_ramo", return_value=DATAS_LIVRES),
			patch.object(agenda_visitas, "schedule_visit") as servico,
		):
			resultado = visitas.agendar_visita("NA-1", "2026-03-07", simular=True)

		servico.assert_not_called()
		self.assertTrue(resultado["simulacao"])

	def test_execucao_delega(self):
		with (
			patch.object(
				visitas.frappe.db,
				"get_value",
				return_value={"name": "NA-1", "ramo": "Lobinho", "nome_completo": "Ana"},
			),
			patch.object(agenda_visitas, "get_available_dates_for_ramo", return_value=DATAS_LIVRES),
			patch.object(agenda_visitas, "schedule_visit") as servico,
		):
			resultado = visitas.agendar_visita("NA-1", "2026-03-07")

		servico.assert_called_once_with("NA-1", "2026-03-07")
		self.assertTrue(resultado["agendado"])
		self.assertEqual(resultado["data"], "2026-03-07")


class TestAtualizarVisita(TestCase):
	def test_visita_inexistente(self):
		with patch.object(visitas.frappe.db, "get_value", return_value=None):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				visitas.atualizar_visita("VIS-9", "confirmar")
		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")

	def test_remarcar_exige_nova_data(self):
		with patch.object(visitas.frappe.db, "get_value", return_value=dict(VISITA)):
			with self.assertRaises(ErroDeFerramenta):
				visitas.atualizar_visita("VIS-1", "remarcar")

	def test_remarcar_valida_disponibilidade(self):
		with (
			patch.object(visitas.frappe.db, "get_value", return_value=dict(VISITA)),
			patch.object(agenda_visitas, "get_available_dates_for_ramo", return_value=DATAS_LIVRES),
		):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				visitas.atualizar_visita("VIS-1", "remarcar", nova_data="2026-03-10")
		self.assertEqual(ctx.exception.codigo, "VALIDACAO")

	def test_confirmar_visita_ja_confirmada(self):
		confirmada = dict(VISITA, visita_confirmada=1)
		with patch.object(visitas.frappe.db, "get_value", return_value=confirmada):
			resultado = visitas.atualizar_visita("VIS-1", "confirmar")
		self.assertFalse(resultado["atualizada"])

	def test_cada_acao_chama_o_servico_correspondente(self):
		with (
			patch.object(visitas.frappe.db, "get_value", return_value=dict(VISITA)),
			patch.object(agenda_visitas, "get_available_dates_for_ramo", return_value=DATAS_LIVRES),
			patch.object(agenda_visitas, "confirm_visit") as confirmar,
			patch.object(agenda_visitas, "reschedule_visit") as remarcar,
			patch.object(agenda_visitas, "cancel_visit") as cancelar,
		):
			visitas.atualizar_visita("VIS-1", "confirmar")
			visitas.atualizar_visita("VIS-1", "remarcar", nova_data="2026-03-14")
			visitas.atualizar_visita("VIS-1", "cancelar")

		confirmar.assert_called_once_with("VIS-1")
		remarcar.assert_called_once_with("VIS-1", "2026-03-14")
		cancelar.assert_called_once_with("VIS-1")

	def test_simulacao_nao_altera(self):
		with (
			patch.object(visitas.frappe.db, "get_value", return_value=dict(VISITA)),
			patch.object(agenda_visitas, "cancel_visit") as cancelar,
		):
			resultado = visitas.atualizar_visita("VIS-1", "cancelar", simular=True)

		cancelar.assert_not_called()
		self.assertTrue(resultado["simulacao"])
