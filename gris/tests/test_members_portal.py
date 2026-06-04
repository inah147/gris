from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from gris.api import members_portal


class TestMembersPortal(TestCase):
	def test_update_member_allows_linked_responsavel_on_allowed_fields(self):
		doc = SimpleNamespace(name="ASSOC-1", save=MagicMock(), set=MagicMock())
		meta = MagicMock()
		meta.get_field.side_effect = lambda fieldname: SimpleNamespace(
			fieldtype="Check" if fieldname == "pais_divorciados" else "Data"
		)

		with (
			patch.object(members_portal, "_can_manage_member", return_value=False),
			patch.object(members_portal, "_is_linked_responsavel", return_value=True),
			patch.object(members_portal.frappe, "get_doc", return_value=doc),
			patch.object(members_portal.frappe, "get_meta", return_value=meta),
			patch.object(
				members_portal.frappe,
				"parse_json",
				return_value={"pais_divorciados": 1, "telefone": "+5511999999999", "area": "X"},
			),
			patch.object(members_portal.frappe.db, "commit"),
			patch.object(members_portal.frappe, "session", SimpleNamespace(user="resp@example.com"), create=True),
		):
			result = members_portal.update_member(
				"ASSOC-1",
				'{"pais_divorciados": 1, "telefone": "+5511999999999", "area": "X"}',
			)

		self.assertTrue(result["success"])
		doc.set.assert_any_call("pais_divorciados", 1)
		doc.set.assert_any_call("telefone", "+5511999999999")
		self.assertEqual(doc.set.call_count, 2)
		doc.save.assert_called_once_with(ignore_permissions=True)

	def test_update_member_blocks_unlinked_responsavel(self):
		doc = SimpleNamespace(name="ASSOC-1", save=MagicMock(), set=MagicMock())

		with (
			patch.object(members_portal, "_can_manage_member", return_value=False),
			patch.object(members_portal, "_is_linked_responsavel", return_value=False),
			patch.object(members_portal.frappe, "get_doc", return_value=doc),
			patch.object(members_portal.frappe, "parse_json", return_value={"pais_divorciados": 1}),
			patch.object(members_portal.frappe, "session", SimpleNamespace(user="resp@example.com"), create=True),
		):
			result = members_portal.update_member("ASSOC-1", '{"pais_divorciados": 1}')

		self.assertTrue(result["success"])
		self.assertEqual(result["applied"], {})
		doc.save.assert_not_called()
