"""Testes do patch que alinha os valores gravados às listas de opções do Paxtu."""

from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.patches import normalizar_opcoes_cadastro as patch_module
from gris.utils.documento import id_por_cpf


def _gerar_cpf(base9: str) -> str:
	digitos = [int(d) for d in base9]
	for posicao in (9, 10):
		soma = sum(d * (posicao + 1 - i) for i, d in enumerate(digitos))
		resto = 11 - (soma % 11)
		digitos.append(0 if resto >= 10 else resto)
	return "".join(str(d) for d in digitos)


CPF_ANTIGO = _gerar_cpf("246813579")


class TestPatchNormalizarOpcoesCadastro(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.novo_associado = self._criar_com_grafia_antiga()

	def tearDown(self):
		frappe.db.rollback()

	def _criar_com_grafia_antiga(self) -> str:
		name = id_por_cpf(CPF_ANTIGO)
		if not frappe.db.exists("Novo Associado", name):
			doc = frappe.get_doc(
				{"doctype": "Novo Associado", "cpf": CPF_ANTIGO, "nome_completo": "Cadastro Antigo"}
			)
			doc.insert(ignore_permissions=True)

		# Direto na tabela: as opções novas já não aceitam a grafia antiga, que é justamente
		# a situação que o patch existe para resolver.
		frappe.db.set_value(
			"Novo Associado",
			name,
			{
				"etnia": "Nâo desejo informar",
				"religiao": "Evangélico/Petencostal",
				"escolaridade": "Ensino tecnico completo",
			},
			update_modified=False,
		)
		return name

	def _executar(self):
		# ``execute`` comita; num teste isso escaparia do rollback e sujaria a base.
		with mock.patch.object(frappe.db, "commit"):
			patch_module.execute()

	def test_corrige_as_grafias_antigas(self):
		self._executar()

		doc = frappe.db.get_value(
			"Novo Associado", self.novo_associado, ["etnia", "religiao"], as_dict=True
		)
		self.assertEqual(doc.etnia, "Não desejo informar")
		self.assertEqual(doc.religiao, "Evangélico/Pentecostal")

	def test_valor_fora_da_lista_e_registrado_e_nao_apagado(self):
		"""Apagar o que não casa perderia informação que a recepção ainda usa para transcrever."""
		logger = mock.MagicMock()
		with mock.patch.object(frappe, "logger", return_value=logger):
			self._executar()

		self.assertEqual(
			frappe.db.get_value("Novo Associado", self.novo_associado, "escolaridade"),
			"Ensino tecnico completo",
		)
		registrado = " ".join(str(chamada) for chamada in logger.info.call_args_list)
		self.assertIn("Ensino tecnico completo", registrado)

	def test_rodar_duas_vezes_nao_muda_nada(self):
		self._executar()
		self._executar()

		self.assertEqual(
			frappe.db.get_value("Novo Associado", self.novo_associado, "etnia"),
			"Não desejo informar",
		)

	def test_nao_faz_nada_quando_a_tabela_nao_existe(self):
		qb = mock.MagicMock()
		with (
			mock.patch.object(frappe.db, "table_exists", return_value=False),
			mock.patch.object(frappe, "qb", new=qb),
			mock.patch.object(frappe.db, "commit"),
		):
			patch_module.execute()

		qb.update.assert_not_called()
