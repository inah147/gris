# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Modo sessão: quem entra, o que cada um grava e a leitura ao vivo (RF-16)."""

from __future__ import annotations

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate

from gris.api.assembleias import constantes as c
from gris.api.assembleias import sessao
from gris.tests.test_assembleias_criacao import _criar
from gris.tests.test_assembleias_formularios import _associado

SECRETARIO = "zz-asm-sessao-sec@example.com"
PRESIDENTE = "zz-asm-sessao-pres@example.com"
ESTRANHO = "zz-asm-sessao-x@example.com"


class _Base(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.name = _criar(add_days(getdate(), 30))["name"]
		self.secretario = _associado("SSEC", usuario=SECRETARIO)
		self.presidente = _associado("SPRES", usuario=PRESIDENTE)
		_associado("SX", usuario=ESTRANHO)
		frappe.db.set_value(
			c.DOCTYPE_ASSEMBLEIA,
			self.name,
			{
				"secretario_tipo": "Associado",
				"secretario": self.secretario,
				"presidente_tipo": "Associado",
				"presidente": self.presidente,
			},
		)
		self._aviso = patch("gris.api.assembleias.sessao.frappe.publish_realtime")
		self.aviso = self._aviso.start()

	def tearDown(self):
		self._aviso.stop()
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _doc(self):
		return frappe.get_doc(c.DOCTYPE_ASSEMBLEIA, self.name)

	def _salvar(self, campos, usuario="Administrator", modified=None):
		modified = modified or str(self._doc().modified)
		frappe.set_user(usuario)
		try:
			return sessao.salvar_sessao(self.name, json.dumps(campos), modified)
		finally:
			frappe.set_user("Administrator")

	def _ler(self, usuario, desde=None):
		frappe.set_user(usuario)
		try:
			return sessao.ler_sessao(self.name, desde)
		finally:
			frappe.set_user("Administrator")


class TestQuemEntra(_Base):
	def test_papeis(self):
		doc = self._doc()
		self.assertEqual(sessao.papel_na_assembleia(doc, "Administrator"), sessao.PAPEL_GESTOR)
		self.assertEqual(sessao.papel_na_assembleia(doc, SECRETARIO), sessao.PAPEL_SECRETARIO)
		self.assertEqual(sessao.papel_na_assembleia(doc, PRESIDENTE), sessao.PAPEL_PRESIDENTE)
		self.assertIsNone(sessao.papel_na_assembleia(doc, ESTRANHO))
		self.assertIsNone(sessao.papel_na_assembleia(doc, "Guest"))

	def test_mesa_perde_o_acesso_com_a_ata_finalizada(self):
		doc = self._doc()
		next(e for e in doc.checklist if e.chave == "finalizar_ata").concluido = 1
		doc.save()
		self.assertIsNone(sessao.papel_na_assembleia(doc, SECRETARIO))
		self.assertIsNone(sessao.papel_na_assembleia(doc, PRESIDENTE))
		self.assertEqual(sessao.papel_na_assembleia(doc, "Administrator"), sessao.PAPEL_GESTOR)

	def test_estranho_nao_le(self):
		with self.assertRaises(frappe.PermissionError):
			self._ler(ESTRANHO)

	def test_presidente_le_e_nao_grava(self):
		resposta = self._ler(PRESIDENTE)
		self.assertTrue(resposta["mudou"])
		self.assertEqual(resposta["papel"], sessao.PAPEL_PRESIDENTE)
		self.assertFalse(resposta["pode_editar"])
		self.assertEqual(self._ler(PRESIDENTE, desde=resposta["modified"]), {"mudou": False})
		with self.assertRaises(frappe.PermissionError):
			self._salvar({"ata": {"ata_presentes": 10}}, usuario=PRESIDENTE)

	def test_secretario_nao_troca_a_mesa(self):
		with self.assertRaises(frappe.PermissionError):
			self._salvar({"ata": {"secretario": f"Associado::{self.presidente}"}}, usuario=SECRETARIO)


class TestRegistro(_Base):
	def test_secretario_registra_o_item(self):
		item = self._doc().pauta[3].name
		self._salvar(
			{
				"itens": {
					item: {
						"anotacoes": "Balanço apresentado; houve oposição.",
						"resultado": "Aprovado",
						"votos_favor": 41,
						"votos_contra": 6,
						"votos_abstencao": 5,
						"concluido": 1,
					}
				}
			},
			usuario=SECRETARIO,
		)
		linha = next(i for i in self._doc().pauta if i.name == item)
		self.assertEqual(linha.resultado, "Aprovado")
		self.assertEqual((linha.votos_favor, linha.votos_contra, linha.votos_abstencao), (41, 6, 5))
		self.assertEqual(linha.concluido, 1)
		self.assertTrue(linha.concluido_em)
		self.assertTrue(linha.iniciado_em)

	def test_reabrir_limpa_o_horario_de_conclusao(self):
		item = self._doc().pauta[0].name
		self._salvar({"itens": {item: {"concluido": 1}}})
		self._salvar({"itens": {item: {"concluido": 0}}})
		linha = next(i for i in self._doc().pauta if i.name == item)
		self.assertEqual(linha.concluido, 0)
		self.assertFalse(linha.concluido_em)

	def test_resultado_invalido(self):
		item = self._doc().pauta[0].name
		with self.assertRaisesRegex(frappe.ValidationError, "Resultado inválido"):
			self._salvar({"itens": {item: {"resultado": "Talvez"}}})

	def test_abrir_e_encerrar(self):
		self._salvar({"abrir": 1}, usuario=SECRETARIO)
		doc = self._doc()
		self.assertTrue(doc.sessao_aberta_em)
		self.assertTrue(doc.ata_hora_inicio)
		self._salvar({"encerrar": 1}, usuario=SECRETARIO)
		self.assertTrue(self._doc().ata_hora_termino)

	def test_item_atual(self):
		doc = self._doc()
		primeiro, segundo = doc.pauta[0].name, doc.pauta[1].name
		self.assertEqual(self._ler("Administrator")["atual"], primeiro)
		self._salvar({"itens": {primeiro: {"concluido": 1}, segundo: {"iniciar": 1}}})
		self.assertEqual(self._ler("Administrator")["atual"], segundo)

	def test_anotacoes_gerais_e_presentes(self):
		self._salvar(
			{"ata": {"anotacoes_secretario": "- **15:12** chegaram mais 6", "ata_presentes": 58}},
			usuario=SECRETARIO,
		)
		doc = self._doc()
		self.assertIn("chegaram mais 6", doc.anotacoes_secretario)
		self.assertEqual(doc.ata_presentes, 58)

	def test_eleito_na_candidatura(self):
		candidatura = frappe.get_doc(
			{
				"doctype": c.DOCTYPE_CANDIDATURA,
				"assembleia": self.name,
				"cargo": c.CARGO_DELEGADO,
				"candidato_tipo": "Associado",
				"candidato": self.presidente,
				"nome": "Candidato",
				"status": "Ativa",
			}
		).insert(ignore_permissions=True)
		self._salvar({"candidaturas": {candidatura.name: "Eleito"}}, usuario=SECRETARIO)
		self.assertEqual(frappe.db.get_value(c.DOCTYPE_CANDIDATURA, candidatura.name, "resultado"), "Eleito")
		cargos = self._ler(PRESIDENTE)["inscricoes"]["cargos"]
		delegados = next(g for g in cargos if g["cargo"] == c.CARGO_DELEGADO)["candidaturas"]
		self.assertEqual(delegados[0]["resultado"], "Eleito")

	def test_candidatura_de_outra_assembleia_e_recusada(self):
		outra = _criar(add_days(getdate(), 60))["name"]
		candidatura = frappe.get_doc(
			{
				"doctype": c.DOCTYPE_CANDIDATURA,
				"assembleia": outra,
				"cargo": c.CARGO_DELEGADO,
				"candidato_tipo": "Associado",
				"candidato": self.presidente,
				"nome": "Candidato",
				"status": "Ativa",
			}
		).insert(ignore_permissions=True)
		with self.assertRaisesRegex(frappe.ValidationError, "não encontrada nesta assembleia"):
			self._salvar({"candidaturas": {candidatura.name: "Eleito"}})

	def test_conflito_de_modified(self):
		self.assertEqual(self._salvar({"abrir": 1}, modified="2000-01-01 00:00:00"), {"conflito": True})

	def test_aviso_vai_para_o_presidente(self):
		self._salvar({"ata": {"ata_presentes": 20}}, usuario=SECRETARIO)
		usuarios = {chamada.kwargs.get("user") for chamada in self.aviso.call_args_list}
		self.assertIn(PRESIDENTE, usuarios)
		self.assertNotIn(SECRETARIO, usuarios)
