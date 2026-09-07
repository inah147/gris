"""Sinal de reagendamento de visita (SUG-00045).

Quando a visita cai, a recepção devolve o card para a coluna anterior com o
selo "Reagendar visita" — o jovem volta a aparecer entre os agendáveis e o
motivo, quando informado, vira observação no card.
"""

from unittest import TestCase
from unittest.mock import MagicMock, patch

from gris.api import recepcao, recepcao_funil
from gris.api.mcp import visitas
from gris.www.recepcao import agenda_visitas


class _DocFalso:
	"""Novo Associado suficiente para o que a função grava e lê."""

	def __init__(self, **campos):
		self.__dict__.update(campos)
		self.salvo = False

	def has_permission(self, _tipo):
		return True

	def save(self):
		self.salvo = True


class TestSinalizarReagendamento(TestCase):
	def _executar(self, doc, visitas_encontradas, motivo=None):
		with (
			patch.object(recepcao.frappe.db, "exists", return_value=True),
			patch.object(recepcao.frappe, "get_doc", return_value=doc),
			patch.object(recepcao.frappe, "get_all", return_value=visitas_encontradas),
			patch.object(recepcao.frappe, "delete_doc") as apagar,
			patch.object(recepcao, "today", return_value="2026-03-10"),
			patch.object(recepcao, "adicionar_comentario") as comentar,
		):
			resultado = recepcao.sinalizar_reagendamento_de_visita("NA-1", motivo)
		return resultado, apagar, comentar

	def test_devolve_o_card_para_a_coluna_anterior_com_o_sinal_ligado(self):
		doc = _DocFalso(
			status="Visita Agendada",
			visita_agendada=1,
			primeira_visita_realizada=0,
			reagendamento_pendente=0,
		)

		resultado, apagar, _ = self._executar(doc, [MagicMock(name="VIS-1")])

		self.assertEqual(doc.status, recepcao_funil.STATUS_ANTES_DA_VISITA)
		self.assertEqual(doc.visita_agendada, 0)
		self.assertEqual(doc.reagendamento_pendente, 1)
		self.assertEqual(doc.data_pedido_reagendamento, "2026-03-10")
		self.assertTrue(doc.salvo)
		self.assertEqual(resultado["novo_status"], "Conversa Inicial")
		apagar.assert_called_once()

	def test_visita_agendada_e_apagada_para_liberar_a_data(self):
		visita = MagicMock()
		visita.name = "VIS-7"
		doc = _DocFalso(
			status="Visita Agendada",
			visita_agendada=1,
			primeira_visita_realizada=0,
			reagendamento_pendente=0,
		)

		resultado, apagar, _ = self._executar(doc, [visita])

		apagar.assert_called_once_with("Agenda de Visitas", "VIS-7")
		self.assertEqual(resultado["visita_removida"], "VIS-7")

	def test_sem_visita_agendada_ainda_assim_sinaliza(self):
		doc = _DocFalso(
			status="Visita Agendada",
			visita_agendada=1,
			primeira_visita_realizada=0,
			reagendamento_pendente=0,
		)

		resultado, apagar, _ = self._executar(doc, [])

		apagar.assert_not_called()
		self.assertIsNone(resultado["visita_removida"])
		self.assertEqual(doc.reagendamento_pendente, 1)

	def test_motivo_informado_vira_observacao(self):
		doc = _DocFalso(
			status="Visita Agendada",
			visita_agendada=1,
			primeira_visita_realizada=0,
			reagendamento_pendente=0,
		)

		_, _, comentar = self._executar(doc, [], motivo="  família pediu para remarcar ")

		comentar.assert_called_once_with("NA-1", "Visita a reagendar: família pediu para remarcar")

	def test_motivo_em_branco_nao_cria_observacao(self):
		doc = _DocFalso(
			status="Visita Agendada",
			visita_agendada=1,
			primeira_visita_realizada=0,
			reagendamento_pendente=0,
		)

		_, _, comentar = self._executar(doc, [], motivo="   ")

		comentar.assert_not_called()

	def test_visita_ja_realizada_nao_volta_para_o_comeco(self):
		doc = _DocFalso(status="Aguardar Dados", visita_agendada=1, primeira_visita_realizada=1)

		with (
			patch.object(recepcao.frappe.db, "exists", return_value=True),
			patch.object(recepcao.frappe, "get_doc", return_value=doc),
		):
			with self.assertRaises(Exception):
				recepcao.sinalizar_reagendamento_de_visita("NA-1")

		self.assertFalse(doc.salvo)
		self.assertEqual(doc.status, "Aguardar Dados")

	def test_sem_permissao_de_escrita_recusa(self):
		doc = _DocFalso(status="Visita Agendada", primeira_visita_realizada=0)
		doc.has_permission = lambda _tipo: False

		with (
			patch.object(recepcao.frappe.db, "exists", return_value=True),
			patch.object(recepcao.frappe, "get_doc", return_value=doc),
		):
			with self.assertRaises(Exception):
				recepcao.sinalizar_reagendamento_de_visita("NA-1")

		self.assertFalse(doc.salvo)


class TestLimparSinalAoAgendar(TestCase):
	"""A visita nova encerra a pendência — senão o selo ficaria preso no card."""

	def test_agendar_visita_limpa_o_sinal(self):
		associado = _DocFalso(name="NA-1", ramo="Lobinho")
		visita = MagicMock()

		with (
			patch.object(agenda_visitas, "user_has_access", return_value=True),
			patch.object(agenda_visitas.frappe, "get_doc", side_effect=[associado, visita]),
			patch.object(agenda_visitas, "_is_date_available_for_ramo", return_value=True),
			patch.object(agenda_visitas, "limpar_sinal_de_reagendamento") as limpar,
		):
			agenda_visitas.schedule_visit("NA-1", "2026-03-14")

		limpar.assert_called_once_with("NA-1")
		self.assertEqual(associado.visita_agendada, 1)
		self.assertEqual(associado.status, recepcao_funil.STATUS_VISITA_AGENDADA)

	def test_limpar_apaga_marca_e_data(self):
		with patch.object(recepcao.frappe.db, "set_value") as set_value:
			recepcao.limpar_sinal_de_reagendamento("NA-1")

		set_value.assert_called_once_with(
			"Novo Associado",
			"NA-1",
			{"reagendamento_pendente": 0, "data_pedido_reagendamento": None},
		)


class TestAcaoMcpReagendarDepois(TestCase):
	def test_delega_para_a_mesma_regra_do_portal(self):
		dados = {
			"name": "VIS-1",
			"jovem": "NA-1",
			"data_da_visita": "2026-03-07",
			"ramo": "Lobinho",
			"visita_confirmada": 0,
		}
		with (
			patch.object(visitas.frappe.db, "get_value", return_value=dict(dados)),
			patch.object(recepcao, "sinalizar_reagendamento_de_visita") as sinalizar,
		):
			resultado = visitas.atualizar_visita("VIS-1", "reagendar_depois", motivo="chuva")

		sinalizar.assert_called_once_with("NA-1", "chuva")
		self.assertTrue(resultado["atualizada"])

	def test_simulacao_nao_sinaliza(self):
		dados = {"name": "VIS-1", "jovem": "NA-1", "ramo": "Lobinho", "visita_confirmada": 0}
		with (
			patch.object(visitas.frappe.db, "get_value", return_value=dict(dados)),
			patch.object(recepcao, "sinalizar_reagendamento_de_visita") as sinalizar,
		):
			resultado = visitas.atualizar_visita("VIS-1", "reagendar_depois", simular=True)

		sinalizar.assert_not_called()
		self.assertTrue(resultado["simulacao"])
