# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.utils.documento import formatar_cpf


def _gerar_cpf(base9: str) -> str:
	"""CPF fictício com dígitos verificadores corretos, a partir de 9 dígitos."""
	digitos = [int(d) for d in base9]
	for posicao in (9, 10):
		soma = sum(d * (posicao + 1 - i) for i, d in enumerate(digitos))
		resto = 11 - (soma % 11)
		digitos.append(0 if resto >= 10 else resto)
	return "".join(str(d) for d in digitos)


# CPF exclusivo deste módulo, para não colidir com os dos outros testes.
CPF_JOVEM = _gerar_cpf("614253879")
REGISTRO_JOVEM = "9914253"


class TestAssociado(FrappeTestCase):
	pass


class TestCriacaoNaoEfetivaRegistroDefinitivo(FrappeTestCase):
	"""Criar o Associado do jovem não efetiva o registro definitivo no funil.

	A importação do relatório do Paxtu cria o Associado de quem ainda está na recepção, sem
	informar o tipo do registro — e o Select grava "Definitivo", a primeira opção. A criação
	marcava a etapa "Registro definitivo efetivado" de todo jovem importado, mesmo sem o
	registro ter saído. Essa etapa é só da recepção, marcada à mão.
	"""

	def setUp(self):
		frappe.set_user("Administrator")
		# Os hooks do Associado enfileiram criação de usuário e o aviso do número de
		# registro; o que está em teste é o que a criação grava no funil, não os jobs.
		mock.patch.object(frappe, "enqueue").start()
		self.addCleanup(mock.patch.stopall)

		jovem = frappe.get_doc(
			{
				"doctype": "Novo Associado",
				"cpf": formatar_cpf(CPF_JOVEM),
				"nome_completo": "Jovem da Importação",
				"data_de_nascimento": "2015-05-10",
				"status": "Fazer Registro",
				"ramo": "Lobinho",
				"tipo_de_registro": "Definitivo",
			}
		)
		jovem.insert(ignore_permissions=True)
		self.jovem = jovem.name

	def tearDown(self):
		frappe.db.rollback()

	def _importar_associado(self, **campos):
		"""Associado com os campos que o importador do relatório do Paxtu preenche."""
		dados = {
			"doctype": "Associado",
			"cpf": CPF_JOVEM,
			"nome_completo": "Jovem Da Importação",
			"registro": REGISTRO_JOVEM,
			"data_de_nascimento": "2015-05-10",
			"categoria": "Beneficiário",
			"ramo": "Lobinho",
		}
		dados.update(campos)
		return frappe.get_doc(dados).insert(ignore_permissions=True)

	def test_importacao_nao_marca_o_registro_definitivo_efetivado(self):
		associado = self._importar_associado()

		# O tipo chega "Definitivo" sem ninguém ter escolhido: é o que disparava a marcação.
		self.assertEqual(associado.tipo_registro, "Definitivo")
		jovem = frappe.get_doc("Novo Associado", self.jovem)
		self.assertEqual(jovem.registro_definitivo_efetivado, 0)
		self.assertEqual(jovem.boleto_definitivo_gerado, 0)
		self.assertNotIn(
			"registro_definitivo_efetivado", [linha.etapa for linha in jovem.historico_de_etapas]
		)

	def test_tipo_definitivo_informado_tambem_nao_efetiva(self):
		self._importar_associado(tipo_registro="Definitivo")

		self.assertEqual(
			frappe.db.get_value("Novo Associado", self.jovem, "registro_definitivo_efetivado"), 0
		)

	def test_criacao_ainda_leva_o_numero_e_o_status_ao_funil(self):
		self._importar_associado()

		jovem = frappe.db.get_value(
			"Novo Associado", self.jovem, ["numero_de_registro", "status"], as_dict=True
		)
		self.assertEqual(jovem.numero_de_registro, REGISTRO_JOVEM)
		self.assertEqual(jovem.status, "Acompanhamento")
