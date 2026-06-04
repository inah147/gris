"""Tests for sidebar adapter used by the design system template."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.portal_access import (
	SIDEBAR_STRUCTURE,
	_is_current_path,
	_normalize_path,
	_to_design_system_sidebar_items,
	_to_portal_breadcrumb_items,
	user_has_access,
)


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

	def test_breadcrumb_inicio_root_generates_single_item(self):
		breadcrumbs = _to_portal_breadcrumb_items(SIDEBAR_STRUCTURE, "/")

		self.assertEqual(
			breadcrumbs,
			[
				{
					"label": str(SIDEBAR_STRUCTURE[0]["label"]),
					"url": None,
				}
			],
		)

	def test_breadcrumb_child_route_keeps_parent_link_and_last_item_without_url(self):
		items = [
			{
				"label": "Financeiro",
				"path": "/financeiro",
				"children": [
					{"label": "Extrato", "path": "/financeiro/extrato"},
				],
			},
		]

		breadcrumbs = _to_portal_breadcrumb_items(items, "/financeiro/extrato")

		self.assertEqual(
			breadcrumbs,
			[
				{"label": "Financeiro", "url": "/financeiro"},
				{"label": "Extrato", "url": None},
			],
		)

	def test_breadcrumb_prefix_match_uses_most_specific_route(self):
		items = [
			{
				"label": "Financeiro",
				"path": "/financeiro",
				"children": [
					{"label": "Extrato", "path": "/financeiro/extrato"},
					{"label": "Relatorios", "path": "/financeiro/relatorios"},
				],
			},
		]

		breadcrumbs = _to_portal_breadcrumb_items(items, "/financeiro/extrato/detalhe/123")

		self.assertEqual(
			breadcrumbs,
			[
				{"label": "Financeiro", "url": "/financeiro"},
				{"label": "Extrato", "url": None},
			],
		)

	def test_breadcrumb_skips_invalid_items_without_label_or_path(self):
		items = [
			{"label": "", "path": "/nao-valido"},
			{"label": "Sem Path"},
			{
				"path": "/financeiro",
				"children": [
					{"label": "Extrato", "path": "/financeiro/extrato"},
				],
			},
		]

		breadcrumbs = _to_portal_breadcrumb_items(items, "/financeiro/extrato")

		self.assertEqual(
			breadcrumbs,
			[
				{"label": "Extrato", "url": None},
			],
		)

	def test_associado_detalhe_allows_linked_responsavel(self):
		with (
			patch("gris.api.portal_access._get_user_roles", return_value=["Responsavel"]),
			patch("gris.api.portal_access._responsavel_has_associado_access", return_value=True),
		):
			frappe.local.form_dict = {"name": "ASSOC-1"}
			self.assertTrue(user_has_access("/associados/detalhe", user="resp@example.com"))

	def test_associado_detalhe_blocks_unlinked_responsavel(self):
		with (
			patch("gris.api.portal_access._get_user_roles", return_value=["Responsavel"]),
			patch("gris.api.portal_access._responsavel_has_associado_access", return_value=False),
		):
			frappe.local.form_dict = {"name": "ASSOC-1"}
			self.assertFalse(user_has_access("/associados/detalhe", user="resp@example.com"))
