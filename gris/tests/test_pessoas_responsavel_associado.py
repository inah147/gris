# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Identidade entre `Responsavel` e `Associado` quando são a mesma pessoa.

O que está sob teste é a ponte: achar o cadastro de associado do responsável (inclusive
quando o hash do CPF é o legado, ou quando o CPF já foi apagado pela anonimização do
funil), migrar o perfil sem atropelar edição posterior, e ligar/desligar a função no
Conselho de Responsáveis conforme a pessoa tenha ou não beneficiário.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.gestao_adultos.responsaveis import AREA_CONSELHO, FUNCAO_RESPONSAVEL_LEGAL
from gris.api.pessoas import (
	associado_do_responsavel,
	responsavel_do_associado,
	vincular_responsavel_ao_associado,
)
from gris.utils.documento import formatar_cpf, id_por_cpf

PREFIXO = "ZZ Teste Pessoas"

#: CPFs fictícios. Só precisam ser únicos e ter 11 dígitos — nenhuma rotina aqui valida
#: dígito verificador.
CPF_CANONICO = "39000000001"
CPF_LEGADO = "39000000002"
CPF_ANONIMIZADO = "39000000003"
CPF_PERFIL = "39000000004"


class TestIdentidadeResponsavelAssociado(FrappeTestCase):
	def tearDown(self):
		# O rollback do FrappeTestCase é por classe: sem este, o cadastro de um teste
		# derruba o seguinte com DuplicateEntryError.
		frappe.db.rollback()

	# ------------------------------------------------------------------
	# Encontrar o associado
	# ------------------------------------------------------------------

	def test_casa_pelo_hash_canonico(self):
		associado = _criar_associado(CPF_CANONICO, "Canonico")
		responsavel = _criar_responsavel(CPF_CANONICO, "Canonico")
		_criar_vinculo(responsavel, associado)

		self.assertEqual(vincular_responsavel_ao_associado(responsavel), associado)
		self.assertEqual(frappe.db.get_value("Responsavel", responsavel, "associado"), associado)
		self.assertTrue(frappe.db.get_value("Responsavel", responsavel, "migrado_para_associado"))
		self.assertTrue(frappe.db.get_value("Associado", associado, "e_responsavel_legal"))

	def test_casa_pelo_hash_legado_do_cpf_pontuado(self):
		"""Cadastro antigo tem `name` = md5 do CPF *pontuado*, que não bate com o canônico."""
		associado = _criar_associado(CPF_LEGADO, "Legado")
		legado = _renomear_para_hash_legado(associado, CPF_LEGADO)
		self.assertNotEqual(legado, id_por_cpf(CPF_LEGADO))

		responsavel = _criar_responsavel(CPF_LEGADO, "Legado")
		_criar_vinculo(responsavel, legado)

		self.assertEqual(vincular_responsavel_ao_associado(responsavel), legado)
		# A ponte é o que cobre o caso: aqui o `name` dos dois **não** é o mesmo.
		self.assertNotEqual(responsavel, legado)
		self.assertEqual(associado_do_responsavel(responsavel), legado)
		self.assertEqual(responsavel_do_associado(legado), responsavel)

	def test_sem_cpf_ainda_casa_pelo_identificador(self):
		"""Depois da anonimização do funil só sobra a chave — e ela basta no caso canônico."""
		associado = _criar_associado(CPF_ANONIMIZADO, "Anonimizado")
		responsavel = _criar_responsavel(CPF_ANONIMIZADO, "Anonimizado")
		_criar_vinculo(responsavel, associado)
		frappe.db.set_value("Responsavel", responsavel, "cpf", None, update_modified=False)

		self.assertEqual(vincular_responsavel_ao_associado(responsavel), associado)

	def test_responsavel_sem_associado_nao_e_migrado(self):
		responsavel = _criar_responsavel("39000000009", "Sozinho")

		self.assertIsNone(vincular_responsavel_ao_associado(responsavel))
		self.assertIsNone(associado_do_responsavel(responsavel))
		self.assertFalse(frappe.db.get_value("Responsavel", responsavel, "migrado_para_associado"))

	# ------------------------------------------------------------------
	# Migração do perfil
	# ------------------------------------------------------------------

	def test_copia_hobbies_e_habilidades(self):
		associado = _criar_associado(CPF_PERFIL, "Perfil")
		responsavel = _criar_responsavel(
			CPF_PERFIL, "Perfil", hobbies="Marcenaria e trilha", habilidades=["Marcenaria"]
		)
		_criar_vinculo(responsavel, associado)

		vincular_responsavel_ao_associado(responsavel)

		doc = frappe.get_doc("Associado", associado)
		self.assertEqual(doc.o_que_gosta_de_fazer_no_dia_a_dia, "Marcenaria e trilha")
		self.assertEqual([linha.habilidade for linha in doc.habilidades], [f"{PREFIXO} Marcenaria"])

	def test_nao_sobrescreve_o_que_o_associado_ja_tinha(self):
		associado = _criar_associado(CPF_PERFIL, "Perfil")
		frappe.db.set_value("Associado", associado, "o_que_gosta_de_fazer_no_dia_a_dia", "Escrito depois")
		responsavel = _criar_responsavel(CPF_PERFIL, "Perfil", hobbies="Veio do responsável")
		_criar_vinculo(responsavel, associado)

		vincular_responsavel_ao_associado(responsavel)

		self.assertEqual(
			frappe.db.get_value("Associado", associado, "o_que_gosta_de_fazer_no_dia_a_dia"),
			"Escrito depois",
		)

	def test_rodar_duas_vezes_nao_duplica_nada(self):
		associado = _criar_associado(CPF_CANONICO, "Idempotente")
		responsavel = _criar_responsavel(
			CPF_CANONICO, "Idempotente", hobbies="Pescaria", habilidades=["Pescaria"]
		)
		_criar_vinculo(responsavel, associado)

		vincular_responsavel_ao_associado(responsavel)
		vincular_responsavel_ao_associado(responsavel)

		doc = frappe.get_doc("Associado", associado)
		self.assertEqual(len(doc.habilidades), 1)
		self.assertEqual(len(_linhas_do_conselho(doc)), 1)

	# ------------------------------------------------------------------
	# Função no Conselho de Responsáveis
	# ------------------------------------------------------------------

	def test_ganha_a_funcao_no_conselho_sem_virar_a_principal(self):
		associado = _criar_associado(CPF_CANONICO, "Conselho")
		responsavel = _criar_responsavel(CPF_CANONICO, "Conselho")
		_criar_vinculo(responsavel, associado)

		vincular_responsavel_ao_associado(responsavel)

		linhas = _linhas_do_conselho(frappe.get_doc("Associado", associado))
		self.assertEqual(len(linhas), 1)
		self.assertIsNone(linhas[0].data_fim)
		# A principal continua sendo a do quadro de voluntários — é ela que o card mostra.
		self.assertFalse(linhas[0].principal)

	def test_perder_o_ultimo_vinculo_encerra_a_funcao_sem_apagar(self):
		associado = _criar_associado(CPF_CANONICO, "Encerrada")
		responsavel = _criar_responsavel(CPF_CANONICO, "Encerrada")
		vinculo = _criar_vinculo(responsavel, associado)
		vincular_responsavel_ao_associado(responsavel)

		frappe.delete_doc("Responsavel Vinculo", vinculo, ignore_permissions=True)

		self.assertFalse(frappe.db.get_value("Associado", associado, "e_responsavel_legal"))
		linhas = _linhas_do_conselho(frappe.get_doc("Associado", associado))
		self.assertEqual(len(linhas), 1, "a linha é encerrada, não apagada: o histórico fica")
		self.assertIsNotNone(linhas[0].data_fim)

	def test_o_vinculo_novo_liga_tudo_sozinho(self):
		"""O hook é quem faz a regra valer sempre, e não só no dia do patch."""
		associado = _criar_associado(CPF_CANONICO, "Hook")
		responsavel = _criar_responsavel(CPF_CANONICO, "Hook")

		_criar_vinculo(responsavel, associado)

		self.assertTrue(frappe.db.get_value("Associado", associado, "e_responsavel_legal"))
		self.assertEqual(frappe.db.get_value("Responsavel", responsavel, "associado"), associado)

	def test_membro_migrado_sai_da_lista_derivada_do_conselho(self):
		from gris.api.gestao_adultos.responsaveis import listar_membros_do_conselho

		associado = _criar_associado(CPF_CANONICO, "Derivado")
		responsavel = _criar_responsavel(CPF_CANONICO, "Derivado")
		_criar_vinculo(responsavel, associado)
		vincular_responsavel_ao_associado(responsavel)

		nomes = {pessoa["name"] for pessoa in listar_membros_do_conselho()}

		self.assertNotIn(
			responsavel, nomes, "quem migrou já entra pela linha gravada; contar aqui duplicaria"
		)


class TestAnonimizacaoPreservaAPonte(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_finalizar_a_recepcao_nao_apaga_o_vinculo_com_o_associado(self):
		"""`_anonimizar_responsaveis` limpa tudo que não estiver na lista de preservados."""
		from gris.www.recepcao.visao_geral import _anonimizar_responsaveis

		associado = _criar_associado(CPF_CANONICO, "Anonimiza")
		responsavel = _criar_responsavel(CPF_CANONICO, "Anonimiza")
		_criar_vinculo(responsavel, associado)
		vincular_responsavel_ao_associado(responsavel)

		_anonimizar_responsaveis([responsavel])

		depois = frappe.db.get_value(
			"Responsavel", responsavel, ["cpf", "associado", "migrado_para_associado"], as_dict=True
		)
		self.assertIsNone(depois.cpf, "o CPF sai — é o que a anonimização existe para fazer")
		self.assertEqual(depois.associado, associado)
		self.assertTrue(depois.migrado_para_associado)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _linhas_do_conselho(doc) -> list:
	return [
		linha
		for linha in doc.funcoes_internas
		if linha.funcao == FUNCAO_RESPONSAVEL_LEGAL and linha.area == AREA_CONSELHO
	]


def _criar_associado(cpf: str, sufixo: str) -> str:
	doc = frappe.get_doc(
		{
			"doctype": "Associado",
			"nome_completo": f"{PREFIXO} {sufixo}",
			"cpf": cpf,
			"data_de_nascimento": "1985-01-01",
			"categoria": "Dirigente",
			"status_no_grupo": "Ativo",
			"historico_no_grupo": [{"data_de_ingresso": "2020-01-01"}],
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _renomear_para_hash_legado(associado: str, cpf: str) -> str:
	"""Recria a convenção antiga: md5 do CPF como o operador digitou, com pontuação."""
	import hashlib

	legado = hashlib.md5(formatar_cpf(cpf).encode("utf-8")).hexdigest()  # nosec B324
	frappe.rename_doc("Associado", associado, legado, force=True, show_alert=False)
	return legado


def _criar_responsavel(
	cpf: str, sufixo: str, hobbies: str | None = None, habilidades: list[str] | None = None
) -> str:
	for habilidade in habilidades or []:
		nome = f"{PREFIXO} {habilidade}"
		if not frappe.db.exists("Habilidade", nome):
			frappe.get_doc({"doctype": "Habilidade", "habilidade": nome}).insert(ignore_permissions=True)

	doc = frappe.get_doc(
		{
			"doctype": "Responsavel",
			"nome_completo": f"{PREFIXO} {sufixo}",
			"cpf": cpf,
			"celular": "11999990000",
			"o_que_gosta_de_fazer_no_dia_a_dia": hobbies,
			"habilidades": [{"habilidade": f"{PREFIXO} {habilidade}"} for habilidade in (habilidades or [])],
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _criar_vinculo(responsavel: str, associado: str) -> str:
	doc = frappe.get_doc(
		{
			"doctype": "Responsavel Vinculo",
			"responsavel": responsavel,
			"beneficiario_associado": associado,
			"é_guardiao_legal": 1,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name
