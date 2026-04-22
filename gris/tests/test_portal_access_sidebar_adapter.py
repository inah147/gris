"""Tests for sidebar adapter used by the design system template."""

from frappe.tests.utils import FrappeTestCase

from gris.api.portal_access import _is_current_path, _normalize_path, _to_design_system_sidebar_items


class TestPortalAccessSidebarAdapter(FrappeTestCase):
	def test_normalize_path(self):
		self.assertEqual(_normalize_path("inicio"), "/inicio")
		self.assertEqual(_normalize_path("/inicio/"), "/inicio")
		self.assertEqual(_normalize_path(None), "/")

	def test_inicio_is_current_for_root(self):
		menu = _to_design_system_sidebar_items(
			[{"label": "Inicio", "path": "/inicio"}],
			"/",
		)
		self.assertEqual(len(menu), 1)
		self.assertTrue(menu[0]["current"])

	def test_submenu_marks_open_and_child_current(self):
		items = [
			{
				"label": "Associados",
				"path": "/associados",
				"children": [
					{"label": "Visao Geral", "path": "/associados/dashboard"},
					{"label": "Lista", "path": "/associados/lista"},
				],
			},
		]

		menu = _to_design_system_sidebar_items(items, "/associados/lista")
		self.assertEqual(len(menu), 1)

		submenu = menu[0]
		self.assertEqual(submenu["type"], "submenu")
		self.assertTrue(submenu["open"])
		self.assertEqual(submenu.get("attrs"), {"aria-current": "page"})

		children = submenu["items"]
		self.assertEqual(len(children), 2)
		self.assertFalse(children[0]["current"])
		self.assertTrue(children[1]["current"])

	def test_adapter_skips_invalid_items(self):
		items = [
			{"label": "", "path": "/nao-valido"},
			{"label": "Sem Path"},
			{
				"label": "Grupo sem filhos validos",
				"path": "/grupo",
				"children": [{"label": "Filho sem path"}],
			},
		]

		menu = _to_design_system_sidebar_items(items, "/grupo")
		self.assertEqual(menu, [])

	def test_is_current_path_for_nested_route(self):
		self.assertTrue(_is_current_path("/financeiro", "/financeiro/relatorios"))
		self.assertTrue(_is_current_path("/financeiro", "/financeiro"))
		self.assertFalse(_is_current_path("/financeiro", "/associados"))
