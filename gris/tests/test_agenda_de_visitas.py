"""Trava de no máximo uma visita agendada por jovem (SUG-00046)."""

from unittest import TestCase
from unittest.mock import patch

from gris.gris.doctype.agenda_de_visitas.agenda_de_visitas import AgendadeVisitas


class _VisitaFalsa(AgendadeVisitas):
	def __init__(self, name, jovem):
		self.name = name
		self.jovem = jovem


class TestValidateSemDuplicidade(TestCase):
	def test_recusa_quando_ja_existe_visita_para_o_jovem(self):
		visita = _VisitaFalsa(name="VIS-2", jovem="NA-1")

		with patch(
			"gris.gris.doctype.agenda_de_visitas.agenda_de_visitas.frappe.db.exists",
			return_value="VIS-1",
		):
			with self.assertRaises(Exception):
				visita.validate()

	def test_permite_quando_e_a_unica_visita(self):
		visita = _VisitaFalsa(name="VIS-1", jovem="NA-1")

		with patch(
			"gris.gris.doctype.agenda_de_visitas.agenda_de_visitas.frappe.db.exists",
			return_value=None,
		):
			visita.validate()

	def test_sem_jovem_nao_verifica(self):
		visita = _VisitaFalsa(name="VIS-1", jovem=None)

		with patch("gris.gris.doctype.agenda_de_visitas.agenda_de_visitas.frappe.db.exists") as existe:
			visita.validate()

		existe.assert_not_called()
