# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Testes dos Acordos de Trabalho Voluntário (ATV).

A regra de validade (`classificar_validade`) é função pura e é testada direto, sem
banco. Os endpoints ganham testes de persistência e de escopo — acordo não pode
atravessar de uma pessoa para outra.
"""

import json
from typing import ClassVar

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, nowdate

from gris.api.gestao_adultos.atribuicoes import atribuir_funcao, listar_funcoes_do_associado
from gris.api.gestao_adultos.atvs import (
	SITUACAO_SEM_ATV,
	SITUACAO_VENCIDO,
	SITUACAO_VIGENTE,
	apagar_atv,
	classificar_validade,
	listar_atvs,
	listar_atvs_da_funcao,
	salvar_atv,
)

PREFIXO = "ZZ Teste ATV"
HOJE = getdate("2026-06-15")


def _atv(fim, inicio="2026-01-01", assinado=1, nome="a", creation="2026-01-01 10:00:00"):
	return {
		"name": nome,
		"data_inicio": inicio,
		"data_fim": fim,
		"assinado": assinado,
		"creation": creation,
	}


class TestClassificarValidade(FrappeTestCase):
	"""Função pura: sem banco, sem fixture."""

	def test_sem_acordo_nenhum(self):
		resultado = classificar_validade([], HOJE)

		self.assertEqual(resultado["situacao"], SITUACAO_SEM_ATV)
		self.assertIsNone(resultado["data_fim"])
		self.assertIsNone(resultado["dias_para_vencer"])
		self.assertFalse(resultado["assinado"])

	def test_acordo_dentro_do_prazo(self):
		resultado = classificar_validade([_atv("2026-12-31")], HOJE)

		self.assertEqual(resultado["situacao"], SITUACAO_VIGENTE)
		self.assertEqual(resultado["dias_para_vencer"], 199)
		self.assertTrue(resultado["assinado"])

	def test_acordo_vencido_conta_dias_negativos(self):
		resultado = classificar_validade([_atv("2026-06-01")], HOJE)

		self.assertEqual(resultado["situacao"], SITUACAO_VENCIDO)
		self.assertEqual(resultado["dias_para_vencer"], -14)

	def test_vence_hoje_ainda_esta_vigente(self):
		"""O mesmo corte do organograma: só está encerrado o que já passou."""
		resultado = classificar_validade([_atv("2026-06-15")], HOJE)

		self.assertEqual(resultado["situacao"], SITUACAO_VIGENTE)
		self.assertEqual(resultado["dias_para_vencer"], 0)

	def test_vale_o_de_validade_mais_recente(self):
		"""A renovação manda, mesmo tendo sido cadastrada antes da anterior."""
		resultado = classificar_validade(
			[
				_atv("2026-06-01", nome="antigo", creation="2026-05-01 10:00:00"),
				_atv("2027-06-01", nome="novo", creation="2026-01-01 10:00:00"),
			],
			HOJE,
		)

		self.assertEqual(resultado["acordo"], "novo")
		self.assertEqual(resultado["situacao"], SITUACAO_VIGENTE)

	def test_empate_de_validade_desempata_pela_criacao(self):
		resultado = classificar_validade(
			[
				_atv("2027-01-01", nome="primeiro", creation="2026-01-01 10:00:00"),
				_atv("2027-01-01", nome="segundo", creation="2026-02-01 10:00:00", assinado=0),
			],
			HOJE,
		)

		self.assertEqual(resultado["acordo"], "segundo")
		self.assertFalse(resultado["assinado"])

	def test_nao_assinado_e_independente_da_situacao(self):
		"""Dentro do prazo e sem assinatura continua sendo pendência."""
		resultado = classificar_validade([_atv("2026-12-31", assinado=0)], HOJE)

		self.assertEqual(resultado["situacao"], SITUACAO_VIGENTE)
		self.assertFalse(resultado["assinado"])


class TestPermissaoDaPagina(FrappeTestCase):
	#: `user_has_access` trata lista vazia como "não informado" e cai nos papéis da
	#: sessão — que no test runner é Administrator. Um papel inexistente é a forma de
	#: dizer "alguém logado, sem papel nenhum que importe".
	SEM_PAPEL: ClassVar[list[str]] = ["ZZ Papel Inexistente"]

	def test_a_pagina_nao_e_aberta_a_qualquer_autenticado(self):
		"""Diferente do organograma: a lista mostra pendência de documento por pessoa."""
		from gris.api.portal_access import user_has_access

		self.assertFalse(user_has_access("/gestao_adultos/atvs", roles=self.SEM_PAPEL))

	def test_gestao_de_adultos_abre_a_pagina(self):
		from gris.api.portal_access import user_has_access

		self.assertTrue(user_has_access("/gestao_adultos/atvs", roles=["Gestor de Adultos"]))


class TestEndpointsDeAtv(FrappeTestCase):
	def setUp(self):
		self.area = self._criar_area("Area")
		self.funcao = self._criar_funcao("Funcao")
		self._vincular(self.area, self.funcao)
		self.associado = self._criar_associado("Pessoa")
		atribuir_funcao(json.dumps({"associado": self.associado, "area": self.area, "funcao": self.funcao}))
		self.linha = listar_funcoes_do_associado(self.associado)[0]["linha"]

	def tearDown(self):
		# O rollback do FrappeTestCase é por classe: sem isto os documentos do `setUp`
		# vazam para o teste seguinte e derrubam a inserção com DuplicateEntryError.
		frappe.db.rollback()

	def _payload(self, **kwargs):
		kwargs.setdefault("associado", self.associado)
		kwargs.setdefault("linha", self.linha)
		return json.dumps(kwargs)

	def test_salvar_cria_o_acordo_e_espelha_a_funcao(self):
		resposta = salvar_atv(self._payload(data_inicio="2026-01-01", data_fim="2027-01-01", assinado=1))

		doc = frappe.get_doc("Acordo de Trabalho Voluntario", resposta["name"])
		self.assertEqual(doc.funcao, self.funcao)
		self.assertEqual(doc.area, self.area)
		self.assertEqual(resposta["validade"]["situacao"], SITUACAO_VIGENTE)

	def test_salvar_sem_datas_e_barrado(self):
		with self.assertRaises(frappe.ValidationError):
			salvar_atv(self._payload(data_inicio="2026-01-01"))

	def test_termino_antes_do_inicio_e_barrado(self):
		with self.assertRaises(frappe.ValidationError):
			salvar_atv(self._payload(data_inicio="2027-01-01", data_fim="2026-01-01"))

	def test_acordo_na_linha_de_outra_pessoa_e_barrado(self):
		outro = self._criar_associado("Outro")

		with self.assertRaises(frappe.DoesNotExistError):
			salvar_atv(
				json.dumps(
					{
						"associado": outro,
						"linha": self.linha,
						"data_inicio": "2026-01-01",
						"data_fim": "2027-01-01",
					}
				)
			)

	def test_editar_um_acordo_de_outra_funcao_e_barrado(self):
		"""`name` e `linha` precisam falar da mesma alocação."""
		outra_funcao = self._criar_funcao("Outra")
		self._vincular(self.area, outra_funcao)
		atribuir_funcao(json.dumps({"associado": self.associado, "area": self.area, "funcao": outra_funcao}))
		outra_linha = next(
			linha["linha"]
			for linha in listar_funcoes_do_associado(self.associado)
			if linha["funcao"] == outra_funcao
		)
		criado = salvar_atv(self._payload(data_inicio="2026-01-01", data_fim="2027-01-01"))

		with self.assertRaises(frappe.ValidationError):
			salvar_atv(
				self._payload(
					name=criado["name"],
					linha=outra_linha,
					data_inicio="2026-01-01",
					data_fim="2027-01-01",
				)
			)

	def test_historico_vem_do_mais_recente_para_o_mais_antigo(self):
		salvar_atv(self._payload(data_inicio="2024-01-01", data_fim="2025-01-01"))
		salvar_atv(self._payload(data_inicio="2025-01-02", data_fim="2026-01-01"))

		historico = listar_atvs_da_funcao(self.associado, self.linha)

		self.assertEqual([atv["data_fim"] for atv in historico], ["2026-01-01", "2025-01-01"])

	def test_apagar_devolve_a_linha_para_sem_atv(self):
		criado = salvar_atv(self._payload(data_inicio="2026-01-01", data_fim="2027-01-01"))

		resposta = apagar_atv(json.dumps({"name": criado["name"]}))

		self.assertEqual(resposta["validade"]["situacao"], SITUACAO_SEM_ATV)
		self.assertEqual(resposta["atvs"], [])

	def test_listagem_traz_uma_linha_por_funcao_em_vigor(self):
		linhas = [item for item in listar_atvs() if item["associado"] == self.associado]

		self.assertEqual(len(linhas), 1)
		self.assertEqual(linhas[0]["funcao"], self.funcao)
		self.assertEqual(linhas[0]["situacao"], SITUACAO_SEM_ATV)

	def test_listagem_ignora_funcao_encerrada(self):
		frappe.db.set_value("Funcao do Associado", self.linha, "data_fim", add_days(nowdate(), -1))

		linhas = [item for item in listar_atvs() if item["associado"] == self.associado]

		self.assertEqual(linhas, [])

	def _criar_area(self, sufixo):
		nome = f"{PREFIXO} {sufixo}"
		if not frappe.db.exists("Unidade Organizacional", nome):
			frappe.get_doc({"doctype": "Unidade Organizacional", "area": nome}).insert(
				ignore_permissions=True
			)
		return nome

	def _criar_funcao(self, sufixo):
		titulo = f"{PREFIXO} Funcao {sufixo}"
		if not frappe.db.exists("Funcao Voluntario", titulo):
			frappe.get_doc(
				{
					"doctype": "Funcao Voluntario",
					"titulo": titulo,
					"categoria": "Dirigente",
					"ativa": 1,
				}
			).insert(ignore_permissions=True)
		return titulo

	def _vincular(self, area, funcao):
		doc = frappe.get_doc("Unidade Organizacional", area)
		doc.append("funcoes", {"funcao": funcao})
		doc.save(ignore_permissions=True)

	def _criar_associado(self, sufixo):
		doc = frappe.get_doc(
			{
				"doctype": "Associado",
				"nome_completo": f"{PREFIXO} {sufixo}",
				"cpf": frappe.generate_hash(length=32),
				"data_de_nascimento": "1990-01-01",
				"categoria": "Dirigente",
				"status_no_grupo": "Ativo",
				"historico_no_grupo": [{"data_de_ingresso": "2020-01-01"}],
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name
