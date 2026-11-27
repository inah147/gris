# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Ata: salvamento automático e rascunho por IA (spec RF-08)."""

from __future__ import annotations

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate

from gris.api.assembleias import ata_ia, pagina
from gris.api.assembleias import constantes as c
from gris.api.llm.errors import LLMRequestError
from gris.tests.test_assembleias_criacao import _criar

CPF = "52998224725"
TELEFONE = "5511912345678"
EMAIL = "zz-ata-teste@example.com"


class _Base(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.name = _criar(add_days(getdate(), 30))["name"]

	def tearDown(self):
		frappe.db.rollback()

	def _doc(self):
		return frappe.get_doc(c.DOCTYPE_ASSEMBLEIA, self.name)

	def _salvar(self, ata: dict):
		return pagina.salvar_campos(self.name, json.dumps({"ata": ata}), str(self._doc().modified))

	def _associado(self) -> str:
		doc = frappe.get_doc(
			{
				"doctype": "Associado",
				"nome_completo": "ZZ Teste Ata Presidente",
				"cpf": CPF,
				"telefone": TELEFONE,
				"email": EMAIL,
				"data_de_nascimento": "1980-01-01",
				"categoria": "Dirigente",
				"status_no_grupo": "Ativo",
				"historico_no_grupo": [{"data_de_ingresso": "2020-01-01"}],
			}
		).insert(ignore_permissions=True)
		return doc.name


class TestAta(_Base):
	def test_salva_campos_da_aba(self):
		resposta = self._salvar(
			{
				"ata_hora_inicio": "14:42",
				"ata_hora_termino": "17:05",
				"ata_presentes": "37",
				"anotacoes_secretario": "Mesa eleita por aclamação.",
				"ata_texto": "Texto com [A CONFIRMAR: votos] e [A CONFIRMAR: horário].",
			}
		)
		self.assertEqual(resposta["marcadores"], 2)
		doc = self._doc()
		self.assertEqual(str(doc.ata_hora_inicio), "14:42:00")
		self.assertEqual(doc.ata_presentes, 37)
		self.assertEqual(doc.anotacoes_secretario, "Mesa eleita por aclamação.")

	def test_campos_fora_da_whitelist_sao_ignorados(self):
		self._salvar({"edital_publicado": 1, "data": "2000-01-01", "anotacoes_secretario": "ok"})
		doc = self._doc()
		self.assertEqual(doc.edital_publicado, 0)
		self.assertNotEqual(str(doc.data), "2000-01-01")

	def test_presidente_e_secretario(self):
		associado = self._associado()
		resposta = self._salvar(
			{"presidente": f"Associado::{associado}", "secretario": "User::Administrator"}
		)
		self.assertEqual(resposta["presidente_nome"], "Zz Teste Ata Presidente")
		doc = self._doc()
		self.assertEqual(doc.presidente, associado)
		self.assertFalse(doc.secretario)
		self.assertIn("Zz Teste Ata Presidente", pagina.dados_da_pagina(doc)["presidente"])

	def test_horario_invalido(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Horário inválido"):
			self._salvar({"ata_hora_inicio": "25:99"})

	def test_conflito(self):
		resposta = pagina.salvar_campos(self.name, json.dumps({"ata": {"ata_presentes": 1}}), "2000-01-01")
		self.assertEqual(resposta, {"conflito": True})


class TestAtaIA(_Base):
	def test_prompt_sem_dados_sensiveis(self):
		associado = self._associado()
		self._salvar(
			{"presidente": f"Associado::{associado}", "anotacoes_secretario": "Aprovado por aclamação."}
		)
		prompt = ata_ia.montar_prompt(self._doc())
		self.assertIn("Zz Teste Ata Presidente", prompt)
		self.assertIn("Aprovado por aclamação.", prompt)
		self.assertIn("1. Eleição da mesa diretora", prompt)
		for sensivel in (CPF, "529.982.247-25", TELEFONE, EMAIL):
			self.assertNotIn(sensivel, prompt)
		self.assertNotIn("{nome_uel}", prompt)

	def test_prompt_leva_o_registro_da_sessao(self):
		doc = self._doc()
		item = doc.pauta[3]
		item.update(
			{
				"resultado": "Aprovado",
				"votos_favor": 41,
				"votos_contra": 6,
				"votos_abstencao": 5,
				"anotacoes": "Balanço apresentado pelo diretor financeiro.",
				"concluido": 1,
				"iniciado_em": "2026-12-05 15:02:00",
				"concluido_em": "2026-12-05 15:20:00",
			}
		)
		doc.save()
		prompt = ata_ia.montar_prompt(self._doc())
		self.assertIn("Resultado: Aprovado (41 a favor, 6 contra, 5 abstenções)", prompt)
		self.assertIn("Anotações do item: Balanço apresentado pelo diretor financeiro.", prompt)
		self.assertIn("iniciado às 15:02, concluído às 15:20", prompt)
		self.assertIn("ANOTAÇÕES GERAIS DO SECRETÁRIO", prompt)

	def test_prompt_leva_os_eleitos(self):
		frappe.get_doc(
			{
				"doctype": c.DOCTYPE_CANDIDATURA,
				"assembleia": self.name,
				"cargo": c.CARGO_DELEGADO,
				"candidato_tipo": "Associado",
				"candidato": self._associado(),
				"nome": "Fulana de Tal",
				"status": "Ativa",
				"resultado": "Eleito",
			}
		).insert(ignore_permissions=True)
		self.assertIn("Fulana de Tal (eleito(a))", ata_ia.montar_prompt(self._doc()))

	def test_marcador_na_forma_curta_tambem_conta(self):
		from gris.api.assembleias.ata import contar_marcadores

		self.assertEqual(contar_marcadores("[A CONFIRMAR: horário] e [A CONFIRM: o que falta]"), 2)

	def test_exige_anotacoes(self):
		with self.assertRaisesRegex(frappe.ValidationError, "anotações"):
			ata_ia.solicitar_ata_ia(self.name)

	def test_texto_existente_pede_confirmacao(self):
		self._salvar({"anotacoes_secretario": "Notas", "ata_texto": "Texto antigo"})
		self.assertEqual(ata_ia.solicitar_ata_ia(self.name), {"precisa_confirmar": True})

	def test_solicitar_enfileira(self):
		self._salvar({"anotacoes_secretario": "Notas"})
		with patch("gris.api.assembleias.ata_ia.frappe.enqueue") as enqueue:
			resposta = ata_ia.solicitar_ata_ia(self.name)
		self.assertTrue(resposta["pendente"])
		self.assertEqual(resposta["status_geracao"], ata_ia.STATUS_GERANDO)
		enqueue.assert_called_once()
		self.assertEqual(enqueue.call_args.kwargs["queue"], "long")

	def test_gerar_grava_texto_sem_mudar_modified(self):
		self._salvar({"anotacoes_secretario": "Notas"})
		antes = self._doc().modified
		with patch("gris.api.llm.gerar_resposta_modelo", return_value="  Ata pronta [A CONFIRMAR: votos]  "):
			ata_ia.gerar_ata(self.name)
		doc = self._doc()
		self.assertEqual(doc.ata_texto, "Ata pronta [A CONFIRMAR: votos]")
		self.assertEqual(doc.ata_status_geracao, ata_ia.STATUS_CONCLUIDA)
		self.assertEqual(doc.modified, antes)
		self.assertEqual(ata_ia.status_ata_ia(self.name)["marcadores"], 1)

	def test_falha_preserva_texto(self):
		self._salvar({"anotacoes_secretario": "Notas", "ata_texto": "Texto que já existia"})
		with (
			patch("gris.api.llm.gerar_resposta_modelo", side_effect=LLMRequestError("HTTP 429")),
			patch("gris.api.assembleias.ata_ia.frappe.log_error"),
		):
			ata_ia.gerar_ata(self.name)
		doc = self._doc()
		self.assertEqual(doc.ata_texto, "Texto que já existia")
		self.assertEqual(doc.ata_status_geracao, ata_ia.STATUS_FALHOU)
		self.assertEqual(doc.ata_erro_geracao, ata_ia.ERRO_LIMITE)
