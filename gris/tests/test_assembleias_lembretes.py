# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Lembretes do prazo do edital no grupo da Diretoria (spec RF-14)."""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate

from gris.api.assembleias import constantes as c
from gris.api.assembleias import lembretes
from gris.tests.test_assembleias_criacao import _criar

GRUPO = "120363000000000000@g.us"
ENVIO = "gris.utils.whatsapp.enviar_para_grupo"


class TestMarcoDoEdital(FrappeTestCase):
	def test_janelas(self):
		esperado = {61: None, 60: 60, 31: 60, 30: 30, 26: 30, 25: 25, 8: 25, 7: 7, 0: 7, -1: None}
		for dias, marco in esperado.items():
			self.assertEqual(lembretes.marco_do_edital(dias, None), marco, dias)

	def test_so_marco_depois_do_ultimo(self):
		self.assertIsNone(lembretes.marco_do_edital(45, 60))
		self.assertEqual(lembretes.marco_do_edital(28, 60), 30)
		self.assertIsNone(lembretes.marco_do_edital(27, 30))
		# Dia perdido: o de 30 não saiu, e hoje já é janela do 25 — sai só o 25.
		self.assertEqual(lembretes.marco_do_edital(24, 60), 25)

	def test_mensagem(self):
		doc = frappe._dict(name="ASM-X", tipo="Ordinária", data="2026-12-05")
		texto = lembretes.mensagem(doc, "2026-11-05", 7)
		self.assertIn("05 de novembro de 2026", texto)
		self.assertIn("faltam *7* dias", texto)
		self.assertIn("/administracao/assembleias/assembleia?name=ASM-X", texto)
		self.assertTrue(texto.endswith(c.ASSINATURA_AUTOMATICA))
		self.assertIn("termina *hoje*", lembretes.mensagem(doc, "2026-11-05", 0))


class TestRodada(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		for name in frappe.get_all(c.DOCTYPE_ASSEMBLEIA, pluck="name"):
			frappe.delete_doc(c.DOCTYPE_ASSEMBLEIA, name, force=True)
		self._grupo = frappe.db.get_single_value(c.DOCTYPE_CONFIGURACOES, "grupo_diretoria_whatsapp")
		self._whatsapp = frappe.db.get_single_value("Configuracoes WhatsApp", "habilitar_integracao")
		frappe.db.set_single_value(c.DOCTYPE_CONFIGURACOES, "grupo_diretoria_whatsapp", GRUPO)
		frappe.db.set_single_value("Configuracoes WhatsApp", "habilitar_integracao", 1)
		# A rodada faz commit por envio; no teste, nada pode ficar gravado de vez.
		self._commit = patch("frappe.db.commit")
		self._commit.start()

	def tearDown(self):
		self._commit.stop()
		frappe.db.rollback()
		frappe.db.set_single_value(c.DOCTYPE_CONFIGURACOES, "grupo_diretoria_whatsapp", self._grupo)
		frappe.db.set_single_value("Configuracoes WhatsApp", "habilitar_integracao", self._whatsapp)

	def _assembleia(self, dias_ate_o_prazo: int) -> str:
		# O prazo é a data menos 30 dias.
		return _criar(add_days(getdate(), dias_ate_o_prazo + 30))["name"]

	def test_envia_e_carimba_uma_vez(self):
		name = self._assembleia(7)
		with patch(ENVIO) as envio:
			self.assertEqual(lembretes.lembrar_publicacao_edital()["enviados"], 1)
			lembretes.lembrar_publicacao_edital()
		self.assertEqual(envio.call_count, 1)
		args, kwargs = envio.call_args
		self.assertEqual(args[0], GRUPO)
		self.assertFalse(kwargs["enqueue"])
		self.assertEqual(kwargs["contexto"]["destinatario_tipo"], "Grupo da diretoria")
		self.assertEqual(frappe.db.get_value(c.DOCTYPE_ASSEMBLEIA, name, "lembrete_edital_marco"), 7)

	def test_criada_dentro_da_janela_recebe_so_o_marco_atual(self):
		self._assembleia(20)
		with patch(ENVIO) as envio:
			lembretes.lembrar_publicacao_edital()
		self.assertEqual(envio.call_count, 1)
		self.assertIn("faltam *20* dias", envio.call_args.args[1])

	def test_falha_nao_carimba(self):
		name = self._assembleia(7)
		with (
			patch(ENVIO, side_effect=RuntimeError("fora do ar")),
			patch("gris.api.assembleias.lembretes.frappe.log_error"),
		):
			self.assertEqual(lembretes.lembrar_publicacao_edital()["enviados"], 0)
		self.assertFalse(frappe.db.get_value(c.DOCTYPE_ASSEMBLEIA, name, "lembrete_edital_marco"))

	def test_edital_publicado_nao_recebe(self):
		name = self._assembleia(7)
		frappe.db.set_value(c.DOCTYPE_ASSEMBLEIA, name, "edital_publicado", 1)
		with patch(ENVIO) as envio:
			lembretes.lembrar_publicacao_edital()
		envio.assert_not_called()

	def test_longe_do_prazo_nao_recebe(self):
		self._assembleia(90)
		with patch(ENVIO) as envio:
			lembretes.lembrar_publicacao_edital()
		envio.assert_not_called()

	def test_sem_grupo(self):
		frappe.db.set_single_value(c.DOCTYPE_CONFIGURACOES, "grupo_diretoria_whatsapp", "")
		self._assembleia(7)
		with patch(ENVIO) as envio:
			resultado = lembretes.lembrar_publicacao_edital()
		envio.assert_not_called()
		self.assertIn("Sem grupo", resultado["motivo"])

	def test_whatsapp_desligado(self):
		frappe.db.set_single_value("Configuracoes WhatsApp", "habilitar_integracao", 0)
		self._assembleia(7)
		with patch(ENVIO) as envio:
			resultado = lembretes.lembrar_publicacao_edital()
		envio.assert_not_called()
		self.assertIn("desabilitada", resultado["motivo"])
