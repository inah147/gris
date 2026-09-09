"""Sinal "hora do registro definitivo" no kanban da recepção (SUG-00047).

Quem entrou com registro provisório precisa gerar o definitivo. Passados os dias
configurados desde a efetivação do provisório, o card ganha o selo na visão geral
— a mesma condição e o mesmo prazo do aviso por WhatsApp
(``gris.api.registro_provisorio_notificacoes``), para a recepção não ver dois
prazos diferentes para a mesma pessoa.
"""

from datetime import date
from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.utils import format_date

from gris.api import recepcao_funil, registro_provisorio_notificacoes
from gris.www.recepcao import visao_geral

HOJE = date(2026, 3, 30)


def _jovem(**campos):
	base = {
		"tipo_de_registro": "Provisório",
		"status": "Acompanhamento",
		"registro_provisorio_efetivado": 1,
		"registro_definitivo_efetivado": 0,
		"data_registro_provisorio_efetivado": date(2026, 3, 1),
	}
	base.update(campos)
	return frappe._dict(base)


class TestSinalRegistroDefinitivo(TestCase):
	def _sinal(self, **campos):
		return recepcao_funil.sinal_registro_definitivo(_jovem(**campos), 20, HOJE)

	def test_provisorio_parado_alem_do_prazo_e_sinalizado(self):
		sinal = self._sinal()

		self.assertTrue(sinal["pendente"])
		self.assertEqual(sinal["dias"], 29)
		self.assertEqual(sinal["desde"], date(2026, 3, 1))

	def test_no_dia_exato_do_prazo_ja_sinaliza(self):
		sinal = self._sinal(data_registro_provisorio_efetivado=date(2026, 3, 10))

		self.assertTrue(sinal["pendente"])
		self.assertEqual(sinal["dias"], 20)

	def test_dentro_do_prazo_nao_sinaliza(self):
		sinal = self._sinal(data_registro_provisorio_efetivado=date(2026, 3, 11))

		self.assertFalse(sinal["pendente"])
		self.assertIsNone(sinal["dias"])
		self.assertIsNone(sinal["desde"])

	def test_registro_definitivo_ja_efetivado_encerra_o_sinal(self):
		self.assertFalse(self._sinal(registro_definitivo_efetivado=1)["pendente"])

	def test_provisorio_ainda_nao_efetivado_nao_sinaliza(self):
		self.assertFalse(self._sinal(registro_provisorio_efetivado=0)["pendente"])

	def test_quem_entrou_como_definitivo_nunca_sinaliza(self):
		self.assertFalse(self._sinal(tipo_de_registro="Definitivo")["pendente"])

	def test_sem_data_de_efetivacao_nao_inventa_prazo(self):
		self.assertFalse(self._sinal(data_registro_provisorio_efetivado=None)["pendente"])

	def test_quem_saiu_do_funil_nao_e_cobrado(self):
		for status in recepcao_funil.STATUS_FORA_DO_FUNIL:
			with self.subTest(status=status):
				self.assertFalse(self._sinal(status=status)["pendente"])

	def test_prazo_configurado_maior_adia_o_sinal(self):
		sinal = recepcao_funil.sinal_registro_definitivo(_jovem(), 45, HOJE)

		self.assertFalse(sinal["pendente"])


class TestDiasParaRegistroDefinitivo(TestCase):
	"""A espera sai das Configurações de Recepção, com 20 dias como piso seguro."""

	def test_usa_o_valor_configurado(self):
		self.assertEqual(recepcao_funil.dias_para_registro_definitivo({"dias_aviso_seguimento_provisorio": 30}), 30)

	def test_valor_ausente_invalido_ou_zerado_cai_no_padrao(self):
		for valor in (None, "", 0, -5, "trinta"):
			with self.subTest(valor=valor):
				self.assertEqual(
					recepcao_funil.dias_para_registro_definitivo({"dias_aviso_seguimento_provisorio": valor}),
					recepcao_funil.DIAS_PADRAO_REGISTRO_DEFINITIVO,
				)

	def test_sem_configuracao_em_maos_le_o_single(self):
		with patch.object(recepcao_funil.frappe.db, "get_single_value", return_value=25) as ler:
			self.assertEqual(recepcao_funil.dias_para_registro_definitivo(), 25)

		ler.assert_called_once_with(
			recepcao_funil.DOCTYPE_CONFIGURACOES, recepcao_funil.CAMPO_DIAS_REGISTRO_DEFINITIVO
		)

	def test_aviso_por_whatsapp_conta_o_mesmo_prazo(self):
		self.assertIs(
			registro_provisorio_notificacoes.dias_para_registro_definitivo,
			recepcao_funil.dias_para_registro_definitivo,
		)


class TestSeloNaVisaoGeral(TestCase):
	"""O kanban precisa entregar o sinal pronto ao template, card a card."""

	def _contexto(self, jovens):
		def _get_all(doctype, *args, **kwargs):
			if doctype == "Novo Associado":
				return [frappe._dict(j) for j in jovens]
			return []

		context = frappe._dict()
		with (
			patch.object(visao_geral, "enrich_context"),
			patch.object(visao_geral, "carregar_configuracao", return_value={}),
			patch.object(visao_geral.frappe, "get_all", side_effect=_get_all),
			patch.object(visao_geral, "getdate", return_value=HOJE),
		):
			visao_geral.get_context(context)
		return context

	def _card(self, context, nome):
		for cards in context.kanban_data.values():
			for card in cards:
				if card.name == nome:
					return card
		self.fail(f"card {nome} não foi renderizado")

	def test_card_atrasado_leva_o_selo_com_a_data_de_efetivacao(self):
		context = self._contexto([_jovem(name="NA-1", nome_completo="Ana")])

		card = self._card(context, "NA-1")
		self.assertTrue(card.registro_definitivo_pendente)
		self.assertEqual(card.registro_definitivo_dias, 29)
		self.assertEqual(card.registro_definitivo_desde, format_date(date(2026, 3, 1)))

	def test_card_dentro_do_prazo_nao_leva_o_selo(self):
		context = self._contexto(
			[
				_jovem(
					name="NA-2",
					nome_completo="Beto",
					data_registro_provisorio_efetivado=date(2026, 3, 20),
				)
			]
		)

		card = self._card(context, "NA-2")
		self.assertFalse(card.registro_definitivo_pendente)
		self.assertIsNone(card.registro_definitivo_desde)

	def test_a_data_da_efetivacao_e_buscada_do_banco(self):
		"""Sem o campo na consulta o selo nunca apareceria — e o erro seria mudo."""
		capturados = {}

		def _get_all(doctype, *args, **kwargs):
			if doctype == "Novo Associado":
				capturados["fields"] = kwargs.get("fields") or []
			return []

		with (
			patch.object(visao_geral, "enrich_context"),
			patch.object(visao_geral, "carregar_configuracao", return_value={}),
			patch.object(visao_geral.frappe, "get_all", side_effect=_get_all),
		):
			visao_geral.get_context(frappe._dict())

		self.assertIn("data_registro_provisorio_efetivado", capturados["fields"])
