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

	def test_sem_prazo_em_maos_usa_o_do_ramo(self):
		"""22 dias: já venceu para o Lobinho (20), ainda não para o Filhote (25)."""
		efetivado = {"data_registro_provisorio_efetivado": date(2026, 3, 8)}
		with patch.object(recepcao_funil.frappe.db, "get_single_value", return_value=None):
			lobinho = recepcao_funil.sinal_registro_definitivo(_jovem(ramo="Lobinho", **efetivado), hoje=HOJE)
			filhote = recepcao_funil.sinal_registro_definitivo(
				_jovem(ramo="Filhotes", **efetivado), hoje=HOJE
			)

		self.assertTrue(lobinho["pendente"])
		self.assertFalse(filhote["pendente"])


class TestDiasParaRegistroDefinitivo(TestCase):
	"""A espera sai das Configurações de Recepção, com 20 dias como piso seguro."""

	def test_usa_o_valor_configurado(self):
		self.assertEqual(
			recepcao_funil.dias_para_registro_definitivo({"dias_aviso_seguimento_provisorio": 30}), 30
		)

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

	def test_filhotes_tem_prazo_proprio_com_padrao_de_25(self):
		for valor in (None, "", 0, -5, "vinte"):
			with self.subTest(valor=valor):
				self.assertEqual(
					recepcao_funil.dias_para_registro_definitivo(
						{"dias_aviso_seguimento_provisorio_filhotes": valor}, "Filhotes"
					),
					recepcao_funil.DIAS_PADRAO_REGISTRO_DEFINITIVO_FILHOTES,
				)

	def test_filhotes_usam_o_valor_configurado_e_os_demais_ignoram(self):
		config = {"dias_aviso_seguimento_provisorio": 20, "dias_aviso_seguimento_provisorio_filhotes": 40}

		self.assertEqual(recepcao_funil.dias_para_registro_definitivo(config, "Filhotes"), 40)
		self.assertEqual(recepcao_funil.dias_para_registro_definitivo(config, "Lobinho"), 20)
		self.assertEqual(recepcao_funil.dias_para_registro_definitivo(config), 20)

	def test_aviso_por_whatsapp_conta_o_mesmo_prazo(self):
		self.assertIs(
			registro_provisorio_notificacoes.dias_para_registro_definitivo,
			recepcao_funil.dias_para_registro_definitivo,
		)


class _ContextoDaVisaoGeral:
	"""Monta o contexto do kanban com o banco trocado por listas em memória."""

	def _contexto(self, jovens, vinculos=(), responsaveis=()):
		respostas = {
			"Novo Associado": jovens,
			"Responsavel Vinculo": vinculos,
			"Responsavel": responsaveis,
		}

		def _get_all(doctype, *args, **kwargs):
			return [frappe._dict(linha) for linha in respostas.get(doctype, ())]

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


class TestSeloNaVisaoGeral(_ContextoDaVisaoGeral, TestCase):
	"""O kanban precisa entregar o sinal pronto ao template, card a card."""

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

	def test_filhote_dentro_do_prazo_do_ramo_nao_leva_o_selo(self):
		"""22 dias desde o provisório: abaixo dos 25 dos Filhotes."""
		context = self._contexto(
			[
				_jovem(
					name="NA-F",
					nome_completo="Filó",
					ramo="Filhotes",
					data_registro_provisorio_efetivado=date(2026, 3, 8),
				)
			]
		)

		self.assertFalse(self._card(context, "NA-F").registro_definitivo_pendente)


class TestSinaisNovosDoCard(_ContextoDaVisaoGeral, TestCase):
	"""Selos "sem número de registro" e "só falta a acolhida" no kanban."""

	def _jovem_completo(self, **campos):
		"""Definitivo com todas as etapas feitas menos a acolhida, e com número."""
		base = {
			"name": "NA-OK",
			"nome_completo": "Ana",
			"tipo_de_registro": "Definitivo",
			"status": "Acompanhamento",
			"numero_de_registro": "123456-7",
			"data_de_nascimento": date(2010, 1, 1),
			**{campo: 1 for campo in recepcao_funil.ORDEM_DEFINITIVO},
			"reuniao_de_acolhida_realizada": 0,
		}
		base.update(campos)
		return frappe._dict(base)

	def test_jovem_sem_numero_em_acompanhamento_e_sinalizado(self):
		context = self._contexto([self._jovem_completo(numero_de_registro="")])

		card = self._card(context, "NA-OK")
		self.assertTrue(card.numero_registro_pendente)
		self.assertEqual(card.numero_registro_pendente_texto, "o jovem")

	def test_responsavel_que_sera_registrado_sem_numero_e_sinalizado(self):
		context = self._contexto(
			[self._jovem_completo()],
			vinculos=[
				{"beneficiario_novo_associado": "NA-OK", "responsavel": "R-1", "sera_registrado": 1},
				{"beneficiario_novo_associado": "NA-OK", "responsavel": "R-2", "sera_registrado": 0},
			],
			responsaveis=[
				{"name": "R-1", "nome_completo": "Bia Mãe", "numero_de_registro": ""},
				{"name": "R-2", "nome_completo": "Caio Pai", "numero_de_registro": ""},
			],
		)

		card = self._card(context, "NA-OK")
		self.assertTrue(card.numero_registro_pendente)
		# Quem não será registrado não precisa de número próprio.
		self.assertEqual(card.numero_registro_pendente_texto, "Bia Mãe")

	def test_todos_com_numero_nao_sinaliza(self):
		context = self._contexto(
			[self._jovem_completo()],
			vinculos=[{"beneficiario_novo_associado": "NA-OK", "responsavel": "R-1", "sera_registrado": 1}],
			responsaveis=[{"name": "R-1", "nome_completo": "Bia Mãe", "numero_de_registro": "999"}],
		)

		self.assertFalse(self._card(context, "NA-OK").numero_registro_pendente)

	def test_antes_do_acompanhamento_falta_de_numero_nao_e_sinal(self):
		context = self._contexto(
			[self._jovem_completo(status="Fazer Registro", numero_de_registro="", registro_criado_no_paxtu=0)]
		)

		self.assertFalse(self._card(context, "NA-OK").numero_registro_pendente)

	def test_so_falta_a_acolhida_e_sinalizado(self):
		context = self._contexto([self._jovem_completo()])

		self.assertTrue(self._card(context, "NA-OK").so_falta_acolhida)

	def test_etapa_pendente_alem_da_acolhida_nao_sinaliza(self):
		context = self._contexto([self._jovem_completo(ficha_medica_preenchida=0)])

		self.assertFalse(self._card(context, "NA-OK").so_falta_acolhida)
