"""Agendamento de visita pelo portal do responsável (SUG-00046).

Reagendar (cancelar + agendar) não pode deixar um registro de Agenda de
Visitas órfão com a data antiga — schedule_visit precisa reaproveitar um
registro já existente para o jovem em vez de sempre inserir um novo.
"""

from contextlib import ExitStack
from unittest import TestCase
from unittest.mock import patch

import frappe

from gris.www.responsavel import beneficiarios


class TestScheduleVisit(TestCase):
	def _agendar(self, existing_visit):
		with ExitStack() as pilha:
			pilha.enter_context(patch.object(beneficiarios.frappe, "session"))
			pilha.enter_context(patch.object(beneficiarios, "_get_responsavel_name", return_value="RESP-1"))
			pilha.enter_context(
				patch.object(
					beneficiarios.frappe,
					"get_all",
					side_effect=[
						[frappe._dict(beneficiario_novo_associado="NA-1")],
						[frappe._dict(name="NA-1", ramo="Lobinho")],
					],
				)
			)
			pilha.enter_context(patch.object(beneficiarios, "_is_date_available_for_ramo", return_value=True))
			pilha.enter_context(patch.object(beneficiarios.frappe.db, "exists", return_value=existing_visit))
			set_value = pilha.enter_context(patch.object(beneficiarios.frappe.db, "set_value"))
			pilha.enter_context(patch.object(beneficiarios, "limpar_sinal_de_reagendamento"))
			get_doc = pilha.enter_context(patch.object(beneficiarios.frappe, "get_doc"))

			resultado = beneficiarios.schedule_visit("2026-03-14")

		return resultado, get_doc, set_value

	def test_sem_visita_existente_cria_um_novo_registro(self):
		resultado, get_doc, set_value = self._agendar(existing_visit=None)

		get_doc.assert_called_once_with(
			{
				"doctype": "Agenda de Visitas",
				"jovem": "NA-1",
				"data_da_visita": "2026-03-14",
				"ramo": "Lobinho",
				"visita_confirmada": 0,
			}
		)
		get_doc.return_value.insert.assert_called_once_with(ignore_permissions=True)
		set_value.assert_called_once_with(
			"Novo Associado", "NA-1", {"visita_agendada": 1, "status": "Visita Agendada"}
		)
		self.assertEqual(resultado, "Visita agendada com sucesso.")

	def test_com_visita_orfa_existente_atualiza_em_vez_de_duplicar(self):
		"""Reproduz o cenário do bug: cancel_visit não apagou o registro antigo."""
		_, get_doc, set_value = self._agendar(existing_visit="VIS-ANTIGA")

		get_doc.assert_not_called()
		set_value.assert_any_call(
			"Agenda de Visitas",
			"VIS-ANTIGA",
			{"data_da_visita": "2026-03-14", "ramo": "Lobinho", "visita_confirmada": 0},
		)
