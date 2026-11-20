"""Modelos editáveis da régua de vencimento: substituição, validação, rodapé e patch."""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api import associados_vencimento_modelos as modelos
from gris.utils import whatsapp


class _DocFalso(frappe._dict):
	meta = None


def _doc(**campos) -> _DocFalso:
	return _DocFalso(campos)


class TestModelos(FrappeTestCase):
	def test_substitui_so_variaveis_conhecidas_e_compacta_linhas(self):
		texto = "Olá, {nome}!\n\n{vazio}\n\n\nFim {desconhecida}."
		self.assertEqual(
			modelos.substituir(texto, {"nome": "Ana", "vazio": ""}),
			"Olá, Ana!\n\nFim {desconhecida}.",
		)

	def test_expressao_nao_e_avaliada(self):
		resultado = modelos.substituir("{x.__class__} {nome.upper} {nome}", {"nome": "Ana", "x": "y"})
		self.assertEqual(resultado, "{x.__class__} {nome.upper} Ana")

	def test_variavel_desconhecida_bloqueia_o_save(self):
		doc = _doc(modelo_venc_30="Olá {primeiro_nome} {data_vencimento}")
		with self.assertRaises(frappe.ValidationError) as erro:
			modelos.validar_configuracoes(doc)
		self.assertIn("{primeiro_nome}", str(erro.exception))
		self.assertIn("{primeiro_nome_destinatario}", str(erro.exception))

	def test_variavel_de_outro_publico_bloqueia(self):
		with self.assertRaises(frappe.ValidationError):
			modelos.validar_configuracoes(_doc(modelo_venc_chefe_7="{registro_de}"))

	def test_codigo_de_template_bloqueia(self):
		for texto in ("{{ frappe.session }}", "{% for x in y %}"):
			with self.subTest(texto=texto), self.assertRaises(frappe.ValidationError):
				modelos.validar_configuracoes(_doc(modelo_venc_7=texto))

	def test_modelos_padrao_sao_validos(self):
		modelos.validar_configuracoes(_doc(**modelos.MODELOS_PADRAO))
		for campo, texto in modelos.MODELOS_PADRAO.items():
			with self.subTest(campo=campo):
				self.assertEqual(modelos.variaveis_desconhecidas(campo, texto), [])

	def test_geral_ligado_sem_corte_e_recusado(self):
		with self.assertRaises(frappe.ValidationError):
			modelos.validar_configuracoes(_doc(regua_vencimento_ativa=1))
		modelos.validar_configuracoes(_doc(regua_vencimento_ativa=1, cobrar_vencidos_desde="2026-11-01"))

	def test_intervalo_minimo(self):
		with self.assertRaises(frappe.ValidationError):
			modelos.validar_configuracoes(_doc(intervalo_recorrente_dias=0))

	def test_modelo_vazio_usa_o_padrao(self):
		with patch.object(modelos, "_valor_do_single", return_value=""):
			self.assertEqual(
				modelos.modelo_configurado("modelo_venc_7"), modelos.MODELOS_PADRAO["modelo_venc_7"]
			)
		with patch.object(modelos, "_valor_do_single", return_value="Texto meu"):
			self.assertEqual(modelos.modelo_configurado("modelo_venc_7"), "Texto meu")

	def test_rodape_sempre_tem_a_linha_de_mensagem_automatica(self):
		with patch.object(modelos, "_valor_do_single", return_value=""):
			self.assertTrue(modelos.com_rodape("Oi").endswith(modelos.ASSINATURA_AUTOMATICA))
			self.assertIn(modelos.TEXTO_JA_RENOVADO_PADRAO, modelos.com_rodape("Oi"))
		# Mesmo com o "já renovado" apagado de propósito, a linha fixa continua.
		self.assertEqual(
			modelos.com_rodape("Oi", texto_ja_renovado=""), f"Oi\n\n{modelos.ASSINATURA_AUTOMATICA}"
		)

	def test_pre_visualizacao(self):
		with (
			patch.object(modelos.frappe, "only_for"),
			patch.object(modelos, "_valor_do_single", return_value=""),
		):
			texto = modelos.pre_visualizar_modelo("modelo_venc_chefe_pos", "")
			self.assertTrue(texto.startswith("Olá, Rafael!"))
			self.assertIn("Alcateia Exemplo", texto)
			self.assertIn("venceu em", texto)
			self.assertNotIn("vence em", texto)
			self.assertTrue(texto.endswith(modelos.ASSINATURA_AUTOMATICA))
			with self.assertRaises(frappe.ValidationError):
				modelos.pre_visualizar_modelo("modelo_venc_7", "{nao_existe}")
			with self.assertRaises(frappe.ValidationError):
				modelos.pre_visualizar_modelo("campo_qualquer", "")

	def test_mes_por_extenso(self):
		import datetime

		self.assertEqual(modelos.mes_por_extenso(datetime.date(2026, 3, 1)), "março de 2026")

	def test_patch_prepara_textos_e_mantem_geral_desligado(self):
		from gris.patches import preparar_regua_de_vencimento

		gravado = {}
		with (
			patch.object(preparar_regua_de_vencimento, "valor_bruto", return_value=None),
			patch.object(
				preparar_regua_de_vencimento.frappe.db,
				"set_single_value",
				side_effect=lambda _d, valores: gravado.update(valores),
			),
			patch.object(preparar_regua_de_vencimento.frappe.db, "commit"),
		):
			preparar_regua_de_vencimento.execute()
		for campo in modelos.CAMPOS_DE_INTERRUPTOR:
			self.assertEqual(gravado[campo], 1)
		for campo, texto in modelos.MODELOS_PADRAO.items():
			self.assertEqual(gravado[campo], texto)
		self.assertNotIn("regua_vencimento_ativa", gravado)
		self.assertEqual(gravado["cobrar_vencidos_desde"], "2026-11-01")
		self.assertEqual(gravado["instrucoes_renovacao"], modelos.INSTRUCOES_RENOVACAO_PADRAO)
		self.assertEqual(gravado["instrucoes_renovacao_vencido"], modelos.INSTRUCOES_RENOVACAO_VENCIDO_PADRAO)

	def test_patch_troca_o_texto_antigo_de_como_renovar(self):
		from gris.patches import preparar_regua_de_vencimento

		existentes = {"instrucoes_renovacao": preparar_regua_de_vencimento.INSTRUCOES_RENOVACAO_ANTIGA}
		gravado = {}
		with (
			patch.object(
				preparar_regua_de_vencimento, "valor_bruto", side_effect=lambda c: existentes.get(c, "0")
			),
			patch.object(
				preparar_regua_de_vencimento.frappe.db,
				"set_single_value",
				side_effect=lambda _d, valores: gravado.update(valores),
			),
			patch.object(preparar_regua_de_vencimento.frappe.db, "commit"),
		):
			preparar_regua_de_vencimento.execute()
		self.assertEqual(gravado, {"instrucoes_renovacao": modelos.INSTRUCOES_RENOVACAO_PADRAO})

	def test_como_renovar_padrao_por_situacao(self):
		with patch.object(modelos, "_valor_do_single", return_value=""):
			self.assertIn("Registro individual", modelos.instrucoes_renovacao())
			self.assertIn("diretoria", modelos.instrucoes_renovacao(vencido=True))
		with (
			patch.object(modelos.frappe, "only_for"),
			patch.object(modelos, "_valor_do_single", return_value=""),
		):
			self.assertIn("diretoria", modelos.pre_visualizar_modelo("modelo_venc_recorrente", ""))
			self.assertIn("Registro individual", modelos.pre_visualizar_modelo("modelo_venc_7", ""))

	def test_patch_nao_sobrescreve_o_que_existe(self):
		from gris.patches import preparar_regua_de_vencimento

		gravado = {}
		with (
			patch.object(preparar_regua_de_vencimento, "valor_bruto", return_value="0"),
			patch.object(
				preparar_regua_de_vencimento.frappe.db,
				"set_single_value",
				side_effect=lambda _d, valores: gravado.update(valores),
			),
			patch.object(preparar_regua_de_vencimento.frappe.db, "commit"),
		):
			preparar_regua_de_vencimento.execute()
		self.assertEqual(gravado, {})


class TestRegistroDoLog(FrappeTestCase):
	def test_grava_associado(self):
		with (
			patch.object(whatsapp, "now_datetime", return_value="2026-11-20 09:00:00"),
			patch.object(whatsapp.frappe, "get_doc") as get_doc,
		):
			whatsapp._registrar_log(
				{"associado": "A1", "assunto": "x", "destinatario_tipo": "Associado"},
				numero="+5511900000001",
				conteudo="oi",
				status=whatsapp.STATUS_ENVIADA,
			)
		linha = get_doc.call_args[0][0]
		self.assertEqual(linha["associado"], "A1")
		self.assertEqual(linha["destinatario_tipo"], "Associado")
