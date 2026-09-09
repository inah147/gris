"""Testes do patch que remove duplicatas de Agenda de Visitas (SUG-00046)."""

from unittest import TestCase
from unittest.mock import patch

import frappe

from gris.patches import deduplicar_agenda_de_visitas as patch_module


class TestDeduplicarAgendaDeVisitas(TestCase):
	def test_nao_faz_nada_se_tabela_nao_existe(self):
		with (
			patch.object(patch_module.frappe.db, "table_exists", return_value=False),
			patch.object(patch_module.frappe.db, "sql") as sql,
		):
			patch_module.execute()

		sql.assert_not_called()

	def test_sem_duplicatas_nao_apaga_nada(self):
		with (
			patch.object(patch_module.frappe.db, "table_exists", return_value=True),
			patch.object(patch_module.frappe.db, "sql", return_value=[]),
			patch.object(patch_module.frappe, "get_all") as get_all,
			patch.object(patch_module.frappe, "delete_doc") as apagar,
			patch.object(patch_module.frappe.db, "commit"),
		):
			patch_module.execute()

		get_all.assert_not_called()
		apagar.assert_not_called()

	def test_mantem_o_registro_mais_recente_e_apaga_os_demais(self):
		duplicados = [frappe._dict(jovem="NA-1")]
		visitas_do_jovem = [
			frappe._dict(name="VIS-NOVA"),
			frappe._dict(name="VIS-ANTIGA"),
			frappe._dict(name="VIS-MAIS-ANTIGA"),
		]

		with (
			patch.object(patch_module.frappe.db, "table_exists", return_value=True),
			patch.object(patch_module.frappe.db, "sql", return_value=duplicados),
			patch.object(patch_module.frappe, "get_all", return_value=visitas_do_jovem) as get_all,
			patch.object(patch_module.frappe, "delete_doc") as apagar,
			patch.object(patch_module.frappe.db, "commit") as commit,
		):
			patch_module.execute()

		get_all.assert_called_once_with(
			"Agenda de Visitas",
			filters={"jovem": "NA-1"},
			fields=["name"],
			order_by="modified desc",
		)
		self.assertEqual(
			apagar.call_args_list,
			[
				(("Agenda de Visitas", "VIS-ANTIGA"), {"ignore_permissions": True, "force": True}),
				(("Agenda de Visitas", "VIS-MAIS-ANTIGA"), {"ignore_permissions": True, "force": True}),
			],
		)
		commit.assert_called_once()
