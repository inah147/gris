# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Testes do módulo de Administração: áreas e funções pelo portal."""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.administracao.consultas import contar_pessoas_por_funcao, listar_funcoes, listar_unidades
from gris.api.administracao.endpoints import mover_unidade, salvar_funcao, salvar_unidade
from gris.api.administracao.permissoes import pode_gerenciar_estrutura
from gris.api.portal_access import user_has_access

PREFIXO = "ZZ Teste Admin"


class TestEstruturaDaUel(FrappeTestCase):
	def setUp(self):
		self.topo = self._criar_area("Topo")
		self.filha = self._criar_area("Filha", responde_para=self.topo)
		self.funcao = self._criar_funcao("Alfa")
		self.outra_funcao = self._criar_funcao("Beta")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _payload(self, **kwargs):
		return json.dumps(kwargs)

	# -- áreas ------------------------------------------------------------

	def test_criar_area_com_funcoes(self):
		salvar_unidade(
			self._payload(
				area=f"{PREFIXO} Nova",
				responde_para=self.topo,
				funcoes=[{"funcao": self.funcao}],
			)
		)

		doc = frappe.get_doc("Unidade Organizacional", f"{PREFIXO} Nova")
		self.assertEqual(doc.responde_para, self.topo)
		self.assertEqual([linha.funcao for linha in doc.funcoes], [self.funcao])

	def test_mesma_funcao_em_duas_areas(self):
		"""O caso que motivou o M:N: um título servindo várias áreas."""
		salvar_unidade(self._payload(name=self.topo, area=self.topo, funcoes=[{"funcao": self.funcao}]))
		salvar_unidade(self._payload(name=self.filha, area=self.filha, funcoes=[{"funcao": self.funcao}]))

		areas = {u["name"]: u for u in listar_unidades()}
		self.assertEqual([f["funcao"] for f in areas[self.topo]["funcoes"]], [self.funcao])
		self.assertEqual([f["funcao"] for f in areas[self.filha]["funcoes"]], [self.funcao])

	def test_funcao_repetida_na_mesma_area_e_barrada(self):
		with self.assertRaises(frappe.ValidationError):
			salvar_unidade(
				self._payload(
					name=self.topo,
					area=self.topo,
					funcoes=[{"funcao": self.funcao}, {"funcao": self.funcao}],
				)
			)

	def test_mover_area_troca_o_responde_para(self):
		outra = self._criar_area("Outro Topo")

		mover_unidade(self._payload(name=self.filha, responde_para=outra))

		self.assertEqual(frappe.db.get_value("Unidade Organizacional", self.filha, "responde_para"), outra)

	def test_mover_area_para_dentro_dela_mesma_e_barrado(self):
		with self.assertRaises(frappe.ValidationError):
			mover_unidade(self._payload(name=self.topo, responde_para=self.topo))

	def test_mover_criando_ciclo_e_barrado(self):
		"""A checagem de ciclo mora no controller e vale também para o arraste."""
		with self.assertRaises(frappe.ValidationError):
			mover_unidade(self._payload(name=self.topo, responde_para=self.filha))

	def test_area_automatica_nao_pode_ser_renomeada(self):
		automatica = self._criar_area("Automatica", origem_automatica=1)

		with self.assertRaises(frappe.ValidationError):
			salvar_unidade(self._payload(name=automatica, area=f"{PREFIXO} Renomeada"))

	def test_area_automatica_nao_pode_ser_desativada(self):
		automatica = self._criar_area("Automatica", origem_automatica=1)

		with self.assertRaises(frappe.ValidationError):
			salvar_unidade(self._payload(name=automatica, area=automatica, ativa=False))

	def test_renomear_area_feita_a_mao_leva_os_vinculos_junto(self):
		# O endpoint substitui o registro inteiro, então o payload manda o formulário
		# todo — é assim que o dialog da tela o chama.
		completo = {
			"name": self.filha,
			"responde_para": self.topo,
			"funcoes": [{"funcao": self.funcao}],
		}
		salvar_unidade(self._payload(area=self.filha, **completo))
		novo = f"{PREFIXO} Filha Renomeada"

		salvar_unidade(self._payload(area=novo, **completo))

		self.assertTrue(frappe.db.exists("Unidade Organizacional", novo))
		self.assertEqual(frappe.db.get_value("Unidade Organizacional", novo, "responde_para"), self.topo)
		self.assertTrue(frappe.db.exists("Funcao da Area", {"parent": novo, "funcao": self.funcao}))

	# -- funções ----------------------------------------------------------

	def test_criar_funcao_com_responsabilidades(self):
		salvar_funcao(
			self._payload(
				titulo=f"{PREFIXO} Funcao Nova",
				categoria="Dirigente",
				responsabilidades=[{"responsabilidade": "Cuidar do caixa", "detalhe": "mensal"}],
			)
		)

		doc = frappe.get_doc("Funcao Voluntario", f"{PREFIXO} Funcao Nova")
		self.assertEqual(doc.categoria, "Dirigente")
		self.assertEqual(doc.responsabilidades[0].responsabilidade, "Cuidar do caixa")

	def test_funcao_automatica_nao_pode_ser_renomeada(self):
		"""A sincronização de seções reconhece a função pelo título exato."""
		automatica = self._criar_funcao("Automatica", origem_automatica=1)

		with self.assertRaises(frappe.ValidationError):
			salvar_funcao(self._payload(name=automatica, titulo=f"{PREFIXO} Outro Titulo"))

	def test_desativar_funcao_mantem_o_registro(self):
		salvar_funcao(self._payload(name=self.funcao, titulo=self.funcao, ativa=False))

		self.assertTrue(frappe.db.exists("Funcao Voluntario", self.funcao))
		self.assertEqual(frappe.db.get_value("Funcao Voluntario", self.funcao, "ativa"), 0)

	def test_contagem_de_pessoas_ignora_funcao_encerrada(self):
		salvar_unidade(self._payload(name=self.topo, area=self.topo, funcoes=[{"funcao": self.funcao}]))
		self._pessoa_com_funcao(self.funcao, self.topo)
		self._pessoa_com_funcao(self.funcao, self.topo, data_fim="2024-06-01")

		contagem = contar_pessoas_por_funcao([self.funcao])

		self.assertEqual(contagem.get(self.funcao), 1)

	def test_listagem_traz_areas_e_contagem_da_funcao(self):
		salvar_unidade(self._payload(name=self.topo, area=self.topo, funcoes=[{"funcao": self.funcao}]))
		self._pessoa_com_funcao(self.funcao, self.topo)

		linha = next(f for f in listar_funcoes() if f["name"] == self.funcao)

		self.assertEqual(linha["areas"], [self.topo])
		self.assertEqual(linha["pessoas"], 1)

	# -- permissões -------------------------------------------------------

	def test_gestor_da_uel_edita_a_estrutura(self):
		usuario = self._criar_usuario("Gestor da UEL")
		frappe.set_user(usuario)

		self.assertTrue(pode_gerenciar_estrutura())
		salvar_unidade(self._payload(area=f"{PREFIXO} Da Uel"))

		self.assertTrue(frappe.db.exists("Unidade Organizacional", f"{PREFIXO} Da Uel"))

	def test_usuario_comum_ve_mas_nao_edita(self):
		usuario = self._criar_usuario()
		frappe.set_user(usuario)

		self.assertTrue(user_has_access("/administracao"))
		self.assertTrue(user_has_access("/administracao/unidades_organizacionais"))
		self.assertFalse(pode_gerenciar_estrutura())
		with self.assertRaises(frappe.PermissionError):
			salvar_unidade(self._payload(area=f"{PREFIXO} Proibida"))

	def test_usuario_comum_nao_cria_funcao(self):
		frappe.set_user(self._criar_usuario())

		with self.assertRaises(frappe.PermissionError):
			salvar_funcao(self._payload(titulo=f"{PREFIXO} Proibida"))

	# -- apoio ------------------------------------------------------------

	def _criar_area(self, sufixo, responde_para=None, origem_automatica=0):
		nome = f"{PREFIXO} {sufixo}"
		if not frappe.db.exists("Unidade Organizacional", nome):
			frappe.get_doc(
				{
					"doctype": "Unidade Organizacional",
					"area": nome,
					"responde_para": responde_para,
					"origem_automatica": origem_automatica,
				}
			).insert(ignore_permissions=True)
		return nome

	def _criar_funcao(self, sufixo, origem_automatica=0):
		titulo = f"{PREFIXO} Funcao {sufixo}"
		if not frappe.db.exists("Funcao Voluntario", titulo):
			frappe.get_doc(
				{
					"doctype": "Funcao Voluntario",
					"titulo": titulo,
					"categoria": "Dirigente",
					"origem_automatica": origem_automatica,
				}
			).insert(ignore_permissions=True)
		return titulo

	def _pessoa_com_funcao(self, funcao, area, data_fim=None):
		doc = frappe.get_doc(
			{
				"doctype": "Associado",
				"nome_completo": f"{PREFIXO} Pessoa",
				"cpf": frappe.generate_hash(length=32),
				"data_de_nascimento": "1990-01-01",
				"categoria": "Dirigente",
				"status_no_grupo": "Ativo",
				"historico_no_grupo": [{"data_de_ingresso": "2020-01-01"}],
				"funcoes_internas": [
					{"funcao": funcao, "area": area, "data_inicio": "2024-01-01", "data_fim": data_fim}
				],
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def _criar_usuario(self, *papeis):
		email = f"{frappe.generate_hash(length=10)}@example.com"
		doc = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Teste",
				"send_welcome_email": 0,
				"roles": [{"role": papel} for papel in papeis],
			}
		)
		doc.insert(ignore_permissions=True)
		return email
