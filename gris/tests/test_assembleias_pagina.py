# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Página da assembleia: Visão Geral, Edital, checklist, formulários e condução
(spec RF-05, RF-06, RF-10 e CA-12.4/12.5)."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate

from gris.api.assembleias import constantes as c
from gris.api.assembleias import documentos, formularios, pagina
from gris.api.assembleias.padroes import configuracoes
from gris.tests.test_assembleias_criacao import _criar


class _Base(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		for name in frappe.get_all(c.DOCTYPE_ASSEMBLEIA, pluck="name"):
			frappe.delete_doc(c.DOCTYPE_ASSEMBLEIA, name, force=True)
		# Publicar gera o edital final no Drive (e faz commit): aqui, nunca o Google real.
		self._sem_drive = patch("gris.api.assembleias.documentos.gerar_edital_final", return_value=b"")
		self._sem_drive.start()

	def tearDown(self):
		self._sem_drive.stop()
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _doc(self, dias=90):
		return frappe.get_doc(c.DOCTYPE_ASSEMBLEIA, _criar(add_days(getdate(), dias))["name"])

	def _payload_do_edital(self, doc, **extra):
		dados = pagina.dados_da_pagina(doc)
		payload = {
			"modified": dados["modified"],
			"pauta": dados["pauta"],
			"texto_topo": dados["edital"]["texto_topo"],
			"texto_rodape": dados["edital"]["texto_rodape"],
			"data_publicacao": "",
			"incluir_links": 1,
		}
		payload.update(extra)
		return json.dumps(payload)


class TestEdital(_Base):
	def test_salvar_edital_reordena_e_inclui_itens(self):
		doc = self._doc()
		dados = pagina.dados_da_pagina(doc)
		pauta = [*reversed(dados["pauta"]), {"titulo": "Item novo  com\nquebra", "tem_votacao": 1}]
		resposta = pagina.salvar_edital(doc.name, self._payload_do_edital(doc, pauta=pauta))
		self.assertEqual(resposta["pauta"][0]["titulo"], dados["pauta"][-1]["titulo"])
		self.assertEqual(resposta["pauta"][-1]["titulo"], "Item novo com quebra")
		# Item sem finalidade ganha a orientação de aprovação simples.
		self.assertEqual(resposta["pauta"][-1]["orientacao_conducao"], c.ORIENTACAO_APROVACAO_SIMPLES)

	def test_salvar_edital_preserva_orientacao_e_concluido_da_conducao(self):
		doc = self._doc()
		item = doc.pauta[0].name
		pagina.salvar_campos(
			doc.name,
			json.dumps({"pauta": {item: {"concluido": 1, "orientacao_conducao": "Editada na condução"}}}),
			str(doc.modified),
		)
		doc.reload()
		# A aba Edital não manda orientação nem concluído, só a estrutura da pauta.
		pauta = [
			{"name": i.name, "titulo": i.titulo, "tem_votacao": i.tem_votacao, "finalidade": i.finalidade}
			for i in doc.pauta
		]
		resposta = pagina.salvar_edital(doc.name, self._payload_do_edital(doc, pauta=pauta))
		self.assertEqual(resposta["pauta"][0]["orientacao_conducao"], "Editada na condução")
		self.assertEqual(resposta["pauta"][0]["concluido"], 1)

	def test_variavel_desconhecida_no_texto_e_recusada(self):
		doc = self._doc()
		with self.assertRaisesRegex(frappe.ValidationError, r"\{chapa\}"):
			pagina.salvar_edital(doc.name, self._payload_do_edital(doc, texto_topo="Chapa {chapa}"))

	def test_publicar_trava_edital_e_marca_checklist(self):
		doc = self._doc()
		dados = pagina.marcar_edital_publicado(doc.name)
		self.assertEqual(dados["edital"]["publicado"], 1)
		self.assertEqual(dados["edital"]["data_publicacao"], str(getdate()))
		divulgar = next(e for e in dados["checklist"] if e["chave"] == c.CHECKLIST_DIVULGAR_EDITAL)
		self.assertEqual(divulgar["concluido"], 1)

		doc.reload()
		with self.assertRaises(frappe.ValidationError):
			pagina.salvar_edital(doc.name, self._payload_do_edital(doc))
		doc.reload()
		doc.pauta[0].titulo = "Outro título"
		with self.assertRaisesRegex(frappe.ValidationError, "já foi publicado"):
			doc.save()
		doc.reload()
		doc.hora_primeira_convocacao = "10:00:00"
		with self.assertRaisesRegex(frappe.ValidationError, "já foi publicado"):
			doc.save()

	def test_publicado_deixa_concluido_e_orientacao_livres(self):
		doc = self._doc()
		pagina.marcar_edital_publicado(doc.name)
		doc.reload()
		doc.pauta[0].concluido = 1
		doc.pauta[0].orientacao_conducao = "Nova orientação"
		doc.local = "Outro local"
		doc.save()

	def test_publicar_de_novo_nao_muda_nada(self):
		doc = self._doc()
		primeira = pagina.marcar_edital_publicado(doc.name)
		segunda = pagina.marcar_edital_publicado(doc.name)
		self.assertEqual(primeira["edital"]["publicado_em"], segunda["edital"]["publicado_em"])

	def test_publicar_fora_do_prazo_pede_confirmacao(self):
		doc = self._doc(dias=10)
		resposta = pagina.marcar_edital_publicado(doc.name)
		self.assertTrue(resposta.get("precisa_confirmar"))
		self.assertFalse(frappe.db.get_value(c.DOCTYPE_ASSEMBLEIA, doc.name, "edital_publicado"))
		resposta = pagina.marcar_edital_publicado(doc.name, fora_do_prazo=1)
		self.assertEqual(resposta["edital"]["publicado"], 1)

	def test_restaurar_pauta(self):
		doc = self._doc()
		pagina.salvar_edital(doc.name, self._payload_do_edital(doc, pauta=[{"titulo": "Só um"}]))
		dados = pagina.restaurar_pauta_padrao(doc.name)
		self.assertEqual(len(dados["pauta"]), len(configuracoes().pauta_ordinaria))

	def test_conteudo_do_edital(self):
		doc = self._doc()
		texto = documentos.conteudo_do_edital(doc)
		self.assertIn("# REUNIÃO ORDINÁRIA DA ASSEMBLEIA DE GRUPO", texto)
		self.assertIn("1. Eleição da mesa diretora", texto)
		self.assertIn("/assembleias/candidatura?assembleia=", texto)
		self.assertIn("/assembleias/assunto_geral?assembleia=", texto)
		self.assertNotIn("{", texto)

		doc.edital_incluir_links = 0
		self.assertNotIn("/assembleias/", documentos.conteudo_do_edital(doc))

	def test_previa_nao_grava(self):
		doc = self._doc()
		antes = doc.modified
		resposta = pagina.previa_edital(
			doc.name, self._payload_do_edital(doc, texto_topo="Prévia em {data}.")
		)
		self.assertIn("Prévia em", resposta["html"])
		self.assertEqual(frappe.db.get_value(c.DOCTYPE_ASSEMBLEIA, doc.name, "modified"), antes)

	def test_previa_sanitiza_html(self):
		doc = self._doc()
		resposta = pagina.previa_edital(
			doc.name, self._payload_do_edital(doc, texto_topo="<script>alert(1)</script> Texto")
		)
		self.assertNotIn("<script>", resposta["html"])


class TestVisaoGeral(_Base):
	def _payload(self, doc, **extra):
		dados = pagina.dados_da_pagina(doc)
		payload = {
			"modified": dados["modified"],
			"data": dados["data"],
			"tipo": dados["tipo"],
			"local": dados["local"],
			"hora_primeira": dados["hora_primeira"],
			"hora_segunda": dados["hora_segunda"],
			"credenciamento": "",
			"vagas_delegados": 4,
		}
		payload.update(extra)
		return json.dumps(payload)

	def test_trocar_tipo_com_pauta(self):
		doc = self._doc()
		dados = pagina.salvar_visao_geral(
			doc.name, self._payload(doc, tipo=c.TIPO_EXTRAORDINARIA, trocar_pauta=1)
		)
		self.assertEqual(len(dados["pauta"]), len(configuracoes().pauta_extraordinaria))
		self.assertEqual(dados["vagas_delegados"], 4)

	def test_trocar_tipo_mantendo_pauta(self):
		doc = self._doc()
		antes = len(doc.pauta)
		dados = pagina.salvar_visao_geral(doc.name, self._payload(doc, tipo=c.TIPO_EXTRAORDINARIA))
		self.assertEqual(len(dados["pauta"]), antes)

	def test_modified_antigo_e_recusado(self):
		doc = self._doc()
		with self.assertRaisesRegex(frappe.ValidationError, "outra janela"):
			pagina.salvar_visao_geral(doc.name, self._payload(doc, modified="2000-01-01 00:00:00"))

	def test_credenciamento_invalido_fica_vazio(self):
		doc = self._doc()
		dados = pagina.salvar_visao_geral(doc.name, self._payload(doc, credenciamento="User::Administrator"))
		self.assertEqual(dados["credenciamento"], "")


class TestChecklist(_Base):
	def test_marca_e_guarda_quem(self):
		doc = self._doc()
		resposta = pagina.salvar_campos(
			doc.name, json.dumps({"checklist": {"imprimir_lista": 1}}), str(doc.modified)
		)
		doc.reload()
		etapa = next(e for e in doc.checklist if e.chave == "imprimir_lista")
		self.assertEqual(etapa.concluido, 1)
		self.assertEqual(etapa.concluido_por, "Administrator")
		self.assertEqual(resposta["modified"], str(doc.modified))

	def test_divulgar_nao_e_marcado_a_mao(self):
		doc = self._doc()
		pagina.salvar_campos(
			doc.name, json.dumps({"checklist": {c.CHECKLIST_DIVULGAR_EDITAL: 1}}), str(doc.modified)
		)
		doc.reload()
		etapa = next(e for e in doc.checklist if e.chave == c.CHECKLIST_DIVULGAR_EDITAL)
		self.assertEqual(etapa.concluido, 0)

	def test_itens_eletivos_somem_sem_eleicao_de_diretoria(self):
		doc = self._doc()
		self.assertTrue(doc.eletiva)
		chaves = {e["chave"] for e in pagina.dados_da_pagina(doc)["checklist"]}
		self.assertIn("registrar_cartorio", chaves)

		doc.set("pauta", [i for i in doc.pauta if i.finalidade != c.FINALIDADE_DIRETORIA])
		doc.save()
		chaves = {e["chave"] for e in pagina.dados_da_pagina(doc)["checklist"]}
		self.assertNotIn("registrar_cartorio", chaves)

	def test_conflito_de_modified(self):
		doc = self._doc()
		resposta = pagina.salvar_campos(
			doc.name, json.dumps({"checklist": {"imprimir_lista": 1}}), "2000-01-01"
		)
		self.assertEqual(resposta, {"conflito": True})


class TestConducao(_Base):
	def test_concluido_e_orientacao(self):
		doc = self._doc()
		item = doc.pauta[0].name
		resposta = pagina.salvar_campos(
			doc.name,
			json.dumps({"pauta": {item: {"concluido": 1, "orientacao_conducao": "**Abrir** a reunião"}}}),
			str(doc.modified),
		)
		self.assertIn("<strong>Abrir</strong>", resposta["pauta"][item])
		doc.reload()
		self.assertEqual(doc.pauta[0].concluido, 1)

	def test_orientacoes_gerais_em_html(self):
		doc = self._doc()
		self.assertIn("<strong>", pagina.dados_da_pagina(doc)["orientacoes_gerais_html"])


class TestFormularios(_Base):
	def _regras(self, **prazos):
		base = {chave: (c.PRAZO_SEM_LIMITE, 0) for chave in formularios.ORDEM_DOS_FORMULARIOS}
		base.update(prazos)
		return {"prazos": base, "manter_aberto": 1, "vagas_comissao_fiscal": 6}

	def _situacao(self, chave, agora, contagens=None, regras=None, finalidades=None, vagas=3):
		return formularios.situacao_do_formulario(
			chave,
			finalidades=finalidades if finalidades is not None else set(c.FINALIDADES),
			inicio=datetime(2026, 12, 5, 14, 30),
			regras=regras or self._regras(),
			agora=agora,
			contagens=contagens or {},
			vagas_delegados=vagas,
		)

	def test_prazo_em_dias(self):
		regras = self._regras(diretoria=(c.PRAZO_DIAS, 8))
		antes = self._situacao(c.FORMULARIO_DIRETORIA, datetime(2026, 11, 27, 14, 29), {"chapas": 1}, regras)
		depois = self._situacao(c.FORMULARIO_DIRETORIA, datetime(2026, 11, 27, 14, 31), {"chapas": 1}, regras)
		self.assertTrue(antes["aberto"])
		self.assertFalse(depois["aberto"])

	def test_prazo_em_horas(self):
		regras = self._regras(delegado=(c.PRAZO_HORAS, 1))
		contagens = {c.CARGO_DELEGADO: 5}
		self.assertTrue(
			self._situacao(c.FORMULARIO_DELEGADO, datetime(2026, 12, 5, 13, 29), contagens, regras)["aberto"]
		)
		self.assertFalse(
			self._situacao(c.FORMULARIO_DELEGADO, datetime(2026, 12, 5, 13, 31), contagens, regras)["aberto"]
		)

	def test_sem_limite_fecha_no_inicio(self):
		self.assertTrue(self._situacao(c.FORMULARIO_MESA, datetime(2026, 12, 5, 14, 29))["aberto"])
		self.assertFalse(self._situacao(c.FORMULARIO_MESA, datetime(2026, 12, 5, 14, 30))["aberto"])

	def test_reabre_sem_candidatos(self):
		regras = self._regras(comissao_fiscal=(c.PRAZO_DIAS, 8))
		agora = datetime(2026, 12, 1)
		faltando = self._situacao(c.FORMULARIO_COMISSAO_FISCAL, agora, {c.CARGO_COMISSAO_FISCAL: 5}, regras)
		completo = self._situacao(c.FORMULARIO_COMISSAO_FISCAL, agora, {c.CARGO_COMISSAO_FISCAL: 6}, regras)
		self.assertTrue(faltando["aberto"] and faltando["reaberto"])
		self.assertFalse(completo["aberto"])

	def test_sem_manter_aberto_nao_reabre(self):
		regras = self._regras(diretoria=(c.PRAZO_DIAS, 8))
		regras["manter_aberto"] = 0
		self.assertFalse(self._situacao(c.FORMULARIO_DIRETORIA, datetime(2026, 12, 1), {}, regras)["aberto"])

	def test_mesa_precisa_de_presidente_e_secretario(self):
		regras = self._regras(mesa=(c.PRAZO_DIAS, 1))
		agora = datetime(2026, 12, 5, 10)
		so_presidente = {c.CARGO_PRESIDENTE_MESA: 1}
		ambos = {c.CARGO_PRESIDENTE_MESA: 1, c.CARGO_SECRETARIO_MESA: 1}
		self.assertTrue(self._situacao(c.FORMULARIO_MESA, agora, so_presidente, regras)["reaberto"])
		self.assertFalse(self._situacao(c.FORMULARIO_MESA, agora, ambos, regras)["aberto"])

	def test_fora_da_pauta(self):
		situacao = self._situacao(c.FORMULARIO_DIRETORIA, datetime(2026, 11, 1), finalidades=set())
		self.assertFalse(situacao["previsto"])
		self.assertFalse(situacao["aberto"])

	def test_prazo_por_extenso(self):
		regras = self._regras(delegado=(c.PRAZO_HORAS, 1), diretoria=(c.PRAZO_DIAS, 8))
		inicio = datetime(2026, 12, 5, 14, 30)
		self.assertEqual(
			formularios.prazo_por_extenso(c.FORMULARIO_DELEGADO, regras, inicio),
			"uma hora antes da primeira convocação",
		)
		self.assertEqual(
			formularios.prazo_por_extenso(c.FORMULARIO_DIRETORIA, regras, inicio), "27 de novembro de 2026"
		)

	def test_estado_na_visao_geral(self):
		doc = self._doc()
		lista = pagina.dados_da_pagina(doc)["formularios"]
		self.assertEqual([f["chave"] for f in lista], list(formularios.ORDEM_DOS_FORMULARIOS))
		self.assertTrue(all(f["previsto"] for f in lista))
		self.assertTrue(lista[0]["aberto"])
