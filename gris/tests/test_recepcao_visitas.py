"""Serviço da visita do jovem: agendar, remarcar e cancelar.

A regra que estes testes fixam é a de visita única. Antes, "Reagendar Visita" na visão
geral chamava o mesmo serviço de agendar, que inseria um registro novo e deixava o antigo
na data velha — e ``notificar_visitas_do_dia``, que seleciona só por ``data_da_visita``,
listava a visita fantasma no grupo de chefes de seção.
"""

from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from gris.api import recepcao_visitas


class _VisitaFalsa:
	"""Agenda de Visitas suficiente para observar o que o serviço grava."""

	def __init__(self, name="VIS-1", data_da_visita="2026-05-02", ramo="Lobinho", confirmada=1):
		self.name = name
		self.data_da_visita = data_da_visita
		self.ramo = ramo
		self.visita_confirmada = confirmada
		self.salvo = False

	def save(self, ignore_permissions=False):
		self.salvo = True


def _linha(name="VIS-1", data="2026-05-02"):
	return frappe._dict({"name": name, "jovem": "NA-1", "data_da_visita": data, "ramo": "Lobinho"})


class TestVisitaDoJovem(TestCase):
	def test_sem_visita_devolve_none(self):
		with patch.object(recepcao_visitas.frappe, "get_all", return_value=[]):
			self.assertIsNone(recepcao_visitas.visita_do_jovem("NA-1"))

	def test_devolve_a_de_data_mais_alta(self):
		# A ordenação vem do SQL; o serviço fica com a primeira.
		linhas = [_linha("VIS-NOVA", "2026-05-09"), _linha("VIS-VELHA", "2026-05-02")]
		with patch.object(recepcao_visitas.frappe, "get_all", return_value=linhas):
			self.assertEqual(recepcao_visitas.visita_do_jovem("NA-1").name, "VIS-NOVA")

	def test_leitura_nao_apaga_duplicata(self):
		linhas = [_linha("VIS-NOVA", "2026-05-09"), _linha("VIS-VELHA", "2026-05-02")]
		with (
			patch.object(recepcao_visitas.frappe, "get_all", return_value=linhas),
			patch.object(recepcao_visitas.frappe, "delete_doc") as apagar,
		):
			recepcao_visitas.visita_do_jovem("NA-1")

		apagar.assert_not_called()

	def test_sem_jovem_devolve_none(self):
		self.assertIsNone(recepcao_visitas.visita_do_jovem(""))


class TestAgendarOuRemarcar(TestCase):
	def test_sem_visita_insere_uma_nova(self):
		novo = MagicMock()
		novo.name = "VIS-9"
		with (
			patch.object(recepcao_visitas.frappe, "get_all", return_value=[]),
			patch.object(recepcao_visitas.frappe, "get_doc", return_value=novo) as get_doc,
		):
			resultado = recepcao_visitas.agendar_ou_remarcar_visita("NA-1", "2026-05-02", ramo="Lobinho")

		self.assertEqual(resultado, "VIS-9")
		novo.insert.assert_called_once()
		self.assertEqual(get_doc.call_args[0][0]["jovem"], "NA-1")

	def test_com_visita_altera_a_data_em_vez_de_criar_outra(self):
		visita = _VisitaFalsa(data_da_visita="2026-05-02")
		with (
			patch.object(recepcao_visitas.frappe, "get_all", return_value=[_linha()]),
			patch.object(recepcao_visitas.frappe, "get_doc", return_value=visita),
			patch.object(recepcao_visitas, "_avisar_remarcacao"),
		):
			resultado = recepcao_visitas.agendar_ou_remarcar_visita("NA-1", "2026-05-09")

		self.assertEqual(resultado, "VIS-1")
		self.assertEqual(str(visita.data_da_visita), "2026-05-09")
		self.assertTrue(visita.salvo)

	def test_remarcar_zera_a_confirmacao_da_data_antiga(self):
		visita = _VisitaFalsa(confirmada=1)
		with (
			patch.object(recepcao_visitas.frappe, "get_all", return_value=[_linha()]),
			patch.object(recepcao_visitas.frappe, "get_doc", return_value=visita),
			patch.object(recepcao_visitas, "_avisar_remarcacao"),
		):
			recepcao_visitas.agendar_ou_remarcar_visita("NA-1", "2026-05-09")

		self.assertEqual(visita.visita_confirmada, 0)

	def test_remarcar_avisa_o_responsavel(self):
		visita = _VisitaFalsa()
		with (
			patch.object(recepcao_visitas.frappe, "get_all", return_value=[_linha()]),
			patch.object(recepcao_visitas.frappe, "get_doc", return_value=visita),
			patch.object(recepcao_visitas, "_avisar_remarcacao") as avisar,
		):
			recepcao_visitas.agendar_ou_remarcar_visita("NA-1", "2026-05-09")

		avisar.assert_called_once()

	def test_mesma_data_nao_mexe_na_confirmacao_nem_avisa(self):
		"""Reagendar para o mesmo dia é um clique repetido, não uma remarcação."""
		visita = _VisitaFalsa(data_da_visita="2026-05-02", confirmada=1)
		with (
			patch.object(recepcao_visitas.frappe, "get_all", return_value=[_linha()]),
			patch.object(recepcao_visitas.frappe, "get_doc", return_value=visita),
			patch.object(recepcao_visitas, "_avisar_remarcacao") as avisar,
		):
			recepcao_visitas.agendar_ou_remarcar_visita("NA-1", "2026-05-02")

		self.assertEqual(visita.visita_confirmada, 1)
		avisar.assert_not_called()

	def test_duplicatas_de_legado_sao_consolidadas(self):
		visita = _VisitaFalsa(name="VIS-NOVA", data_da_visita="2026-05-09")
		linhas = [_linha("VIS-NOVA", "2026-05-09"), _linha("VIS-VELHA", "2026-05-02")]
		with (
			patch.object(recepcao_visitas.frappe, "get_all", return_value=linhas),
			patch.object(recepcao_visitas.frappe, "get_doc", return_value=visita),
			patch.object(recepcao_visitas.frappe, "delete_doc") as apagar,
			patch.object(recepcao_visitas, "_avisar_remarcacao"),
		):
			recepcao_visitas.agendar_ou_remarcar_visita("NA-1", "2026-05-16")

		apagar.assert_called_once_with("Agenda de Visitas", "VIS-VELHA", ignore_permissions=True)

	def test_sem_jovem_e_recusado(self):
		with self.assertRaises(frappe.ValidationError):
			recepcao_visitas.agendar_ou_remarcar_visita("", "2026-05-02")


class TestRemoverVisitaDoJovem(TestCase):
	def test_apaga_todas_as_visitas_e_devolve_a_contagem(self):
		linhas = [_linha("VIS-1"), _linha("VIS-2", "2026-04-25")]
		with (
			patch.object(recepcao_visitas.frappe, "get_all", return_value=linhas),
			patch.object(recepcao_visitas.frappe, "delete_doc") as apagar,
		):
			removidas = recepcao_visitas.remover_visita_do_jovem("NA-1")

		self.assertEqual(removidas, 2)
		self.assertEqual(apagar.call_count, 2)

	def test_sem_visita_nao_apaga_nada(self):
		with (
			patch.object(recepcao_visitas.frappe, "get_all", return_value=[]),
			patch.object(recepcao_visitas.frappe, "delete_doc") as apagar,
		):
			self.assertEqual(recepcao_visitas.remover_visita_do_jovem("NA-1"), 0)

		apagar.assert_not_called()
