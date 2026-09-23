# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Testes dos endpoints que atribuem funções internas pela ficha do portal."""

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, nowdate

from gris.api.gestao_adultos.atribuicoes import (
	atribuir_funcao,
	definir_principal,
	encerrar_funcao,
	listar_areas_com_funcoes,
	listar_funcoes_do_associado,
)

PREFIXO = "ZZ Teste Atribuicao"


class TestAtribuicoesDeFuncao(FrappeTestCase):
	def setUp(self):
		self.area = self._criar_area("Area")
		self.area_vazia = self._criar_area("Area Vazia")
		self.funcao = self._criar_funcao("Principal")
		self.funcao_extra = self._criar_funcao("Extra")
		self.funcao_inativa = self._criar_funcao("Inativa", ativa=0)
		self._vincular(self.area, self.funcao)
		self._vincular(self.area, self.funcao_extra)
		self._vincular(self.area, self.funcao_inativa)
		self.associado = self._criar_associado()

	def tearDown(self):
		frappe.db.rollback()

	def _payload(self, **kwargs):
		kwargs.setdefault("associado", self.associado)
		return json.dumps(kwargs)

	def test_atribuir_abre_a_funcao_hoje(self):
		atribuir_funcao(self._payload(area=self.area, funcao=self.funcao))

		linhas = listar_funcoes_do_associado(self.associado)
		self.assertEqual(len(linhas), 1)
		self.assertEqual(linhas[0]["area"], self.area)
		self.assertEqual(linhas[0]["data_inicio"], getdate(nowdate()).isoformat())
		self.assertTrue(linhas[0]["atual"])

	def test_atribuir_o_mesmo_par_duas_vezes_e_barrado(self):
		"""Duas linhas abertas iguais disputariam a mesma vaga no organograma."""
		atribuir_funcao(self._payload(area=self.area, funcao=self.funcao))

		with self.assertRaises(frappe.ValidationError):
			atribuir_funcao(self._payload(area=self.area, funcao=self.funcao))

	def test_atribuir_par_sem_vinculo_e_barrado(self):
		with self.assertRaises(frappe.ValidationError):
			atribuir_funcao(self._payload(area=self.area_vazia, funcao=self.funcao))

	def test_atribuir_sem_area_e_barrado(self):
		with self.assertRaises(frappe.ValidationError):
			atribuir_funcao(self._payload(funcao=self.funcao))

	def test_encerrar_mantem_a_linha_e_grava_data_fim(self):
		"""Encerrar preserva o histórico — apagar tiraria a pessoa do painel também."""
		atribuir_funcao(self._payload(area=self.area, funcao=self.funcao))
		linha = listar_funcoes_do_associado(self.associado)[0]["linha"]

		encerrar_funcao(self._payload(linha=linha))

		linhas = listar_funcoes_do_associado(self.associado)
		self.assertEqual(len(linhas), 1)
		self.assertEqual(linhas[0]["data_fim"], getdate(nowdate()).isoformat())

	def test_encerrar_duas_vezes_e_barrado(self):
		atribuir_funcao(self._payload(area=self.area, funcao=self.funcao))
		linha = listar_funcoes_do_associado(self.associado)[0]["linha"]
		encerrar_funcao(self._payload(linha=linha))
		# A primeira encerra em hoje; adiantar a data deixa a linha no passado.
		frappe.db.set_value("Funcao do Associado", linha, "data_fim", add_days(nowdate(), -1))

		with self.assertRaises(frappe.ValidationError):
			encerrar_funcao(self._payload(linha=linha))

	def test_encerrar_funcao_futura_nao_inverte_o_periodo(self):
		"""Data de início no futuro: encerrar em 'hoje' criaria fim antes do início."""
		atribuir_funcao(
			self._payload(area=self.area, funcao=self.funcao, data_inicio=add_days(nowdate(), 10))
		)
		linha = listar_funcoes_do_associado(self.associado)[0]["linha"]

		encerrar_funcao(self._payload(linha=linha))

		atualizada = listar_funcoes_do_associado(self.associado)[0]
		self.assertEqual(atualizada["data_fim"], atualizada["data_inicio"])

	def test_definir_principal_desmarca_as_outras(self):
		atribuir_funcao(self._payload(area=self.area, funcao=self.funcao, principal=True))
		atribuir_funcao(self._payload(area=self.area, funcao=self.funcao_extra))
		alvo = next(
			linha["linha"]
			for linha in listar_funcoes_do_associado(self.associado)
			if linha["funcao"] == self.funcao_extra
		)

		definir_principal(self._payload(linha=alvo))

		principais = [
			linha["funcao"] for linha in listar_funcoes_do_associado(self.associado) if linha["principal"]
		]
		self.assertEqual(principais, [self.funcao_extra])

	def test_funcao_encerrada_nao_pode_ser_principal(self):
		atribuir_funcao(self._payload(area=self.area, funcao=self.funcao))
		linha = listar_funcoes_do_associado(self.associado)[0]["linha"]
		frappe.db.set_value("Funcao do Associado", linha, "data_fim", add_days(nowdate(), -1))

		with self.assertRaises(frappe.ValidationError):
			definir_principal(self._payload(linha=linha))

	def test_linha_de_outra_pessoa_nao_e_encontrada(self):
		atribuir_funcao(self._payload(area=self.area, funcao=self.funcao))
		linha = listar_funcoes_do_associado(self.associado)[0]["linha"]
		outro = self._criar_associado("Outro")

		with self.assertRaises(frappe.DoesNotExistError):
			encerrar_funcao(json.dumps({"associado": outro, "linha": linha}))

	def test_cascata_traz_so_funcoes_ativas_da_area(self):
		areas = {item["value"]: item for item in listar_areas_com_funcoes()}

		disponiveis = [f["value"] for f in areas[self.area]["funcoes"]]
		self.assertIn(self.funcao, disponiveis)
		self.assertIn(self.funcao_extra, disponiveis)
		# Função desativada continua no histórico, mas não deve ser atribuível.
		self.assertNotIn(self.funcao_inativa, disponiveis)
		self.assertEqual(areas[self.area_vazia]["funcoes"], [])

	def test_payload_invalido_e_recusado(self):
		with self.assertRaises(frappe.ValidationError):
			atribuir_funcao("isto não é json")

	def _criar_area(self, sufixo):
		nome = f"{PREFIXO} {sufixo}"
		if not frappe.db.exists("Unidade Organizacional", nome):
			frappe.get_doc({"doctype": "Unidade Organizacional", "area": nome}).insert(
				ignore_permissions=True
			)
		return nome

	def _criar_funcao(self, sufixo, ativa=1):
		titulo = f"{PREFIXO} Funcao {sufixo}"
		if not frappe.db.exists("Funcao Voluntario", titulo):
			frappe.get_doc(
				{
					"doctype": "Funcao Voluntario",
					"titulo": titulo,
					"categoria": "Dirigente",
					"ativa": ativa,
				}
			).insert(ignore_permissions=True)
		return titulo

	def _vincular(self, area, funcao):
		doc = frappe.get_doc("Unidade Organizacional", area)
		doc.append("funcoes", {"funcao": funcao})
		doc.save(ignore_permissions=True)

	def _criar_associado(self, sufixo="Pessoa"):
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
