"""Testes do patch que normaliza a grafia antiga do tipo 'Insígnia Especial'."""

from unittest import TestCase
from unittest.mock import MagicMock, patch

from gris.patches import renomear_insignia_especial as patch_module


class TestRenomearInsigniaEspecial(TestCase):
	def test_nao_faz_nada_se_tabela_nao_existe(self):
		qb = MagicMock()
		with (
			patch.object(patch_module.frappe.db, "table_exists", return_value=False),
			patch.object(patch_module.frappe, "qb", new=qb),
		):
			patch_module.execute()

		qb.DocType.assert_not_called()

	def test_nao_faz_nada_se_coluna_nao_existe(self):
		qb = MagicMock()
		with (
			patch.object(patch_module.frappe.db, "table_exists", return_value=True),
			patch.object(patch_module.frappe.db, "has_column", return_value=False),
			patch.object(patch_module.frappe, "qb", new=qb),
		):
			patch_module.execute()

		qb.DocType.assert_not_called()

	def test_atualiza_registros_com_a_grafia_antiga(self):
		query = MagicMock()
		query.set.return_value = query
		query.where.return_value = query
		qb = MagicMock()
		qb.update.return_value = query

		with (
			patch.object(patch_module.frappe.db, "table_exists", return_value=True),
			patch.object(patch_module.frappe.db, "has_column", return_value=True),
			patch.object(patch_module.frappe.db, "commit") as commit,
			patch.object(patch_module.frappe, "qb", new=qb),
		):
			patch_module.execute()

		qb.update.assert_called_once()
		query.set.assert_called_once()
		_, set_valor = query.set.call_args[0]
		self.assertEqual(set_valor, "Insígnia de Interesse Especial")

		query.where.assert_called_once()
		query.run.assert_called_once()
		commit.assert_called_once()
