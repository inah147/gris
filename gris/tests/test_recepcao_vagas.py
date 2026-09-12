"""Ocupação de vagas por ramo, o selo "Seção sem vagas" e o dialog "Cálculo de Vagas".

Ocupam vaga os associados ativos e os novos associados da visita agendada em diante,
cada pessoa uma vez só: o Novo Associado de quem já é Associado ativo não conta de
novo. A Fila de Espera e a visão geral leem a mesma conta.
"""

import json
from datetime import date
from itertools import count
from unittest import TestCase
from unittest.mock import patch

import frappe

from gris.api import recepcao_vagas
from gris.utils.documento import id_por_cpf
from gris.www.recepcao import fila_espera, visao_geral

HOJE = date(2026, 9, 12)

CPF_ANA = "123.456.789-09"
CPF_BETO = "987.654.321-00"


def _calcular(associados=(), vagas=None, **kwargs):
	"""Roda a conta com o banco simulado e devolve ``(resultado, filtros por DocType)``."""
	consultas = {}

	def _get_all(doctype, *args, **kw):
		consultas[doctype] = kw.get("filters")
		if doctype == "Associado":
			return [frappe._dict(a) for a in associados]
		return []

	with (
		patch.object(recepcao_vagas.frappe, "get_single", return_value=frappe._dict(vagas or {})),
		patch.object(recepcao_vagas.frappe, "get_all", side_effect=_get_all),
	):
		resultado = recepcao_vagas.calcular_vagas_por_ramo(hoje=HOJE, **kwargs)
	return resultado, consultas


_sequencia_de_cpf = count(1)


def _novo(status, ramo="Lobinho", cpf=None, name=None):
	# Sem CPF informado, cada linha ganha um próprio: são pessoas diferentes.
	cpf = cpf or f"{next(_sequencia_de_cpf):011d}"
	return frappe._dict(name=name or id_por_cpf(cpf), cpf=cpf, ramo=ramo, status=status)


class TestOcupacaoPorStatus(TestCase):
	def test_quem_ainda_nao_agendou_a_visita_nao_ocupa_vaga(self):
		novos = [_novo("Novo Contato"), _novo("Conversa Inicial"), _novo("Fila de espera")]

		resultado, _ = _calcular(novos_associados=novos)

		self.assertEqual(resultado["Lobinho"].novos, 0)

	def test_da_visita_agendada_em_diante_ocupa_vaga(self):
		novos = [
			_novo("Visita Agendada"),
			_novo("Aguardar Dados"),
			_novo("Fazer Registro"),
			_novo("Acompanhamento"),
		]

		resultado, _ = _calcular(novos_associados=novos)

		self.assertEqual(resultado["Lobinho"].novos, 4)

	def test_sem_linhas_informadas_consulta_so_quem_ocupa_vaga(self):
		_, consultas = _calcular()

		self.assertEqual(
			consultas["Novo Associado"]["status"],
			["not in", list(recepcao_vagas.STATUS_QUE_NAO_OCUPAM_VAGA)],
		)
		self.assertIn("Fila de espera", recepcao_vagas.STATUS_QUE_NAO_OCUPAM_VAGA)

	def test_ativos_sao_os_beneficiarios_ativos(self):
		_, consultas = _calcular(novos_associados=[])

		self.assertEqual(consultas["Associado"]["status_no_grupo"], "Ativo")
		self.assertEqual(consultas["Associado"]["categoria"], "Beneficiário")


class TestCadaPessoaContaUmaVez(TestCase):
	def test_novo_associado_que_ja_e_associado_ativo_conta_uma_vez(self):
		associados = [{"name": id_por_cpf(CPF_ANA), "ramo": "Lobinho"}]
		novos = [_novo("Acompanhamento", cpf=CPF_ANA)]

		resultado, _ = _calcular(associados=associados, novos_associados=novos)

		self.assertEqual(resultado["Lobinho"].ativos, 1)
		self.assertEqual(resultado["Lobinho"].novos, 0)

	def test_cpf_pontuado_casa_com_o_hash_dos_digitos(self):
		associados = [{"name": id_por_cpf("12345678909"), "ramo": "Lobinho"}]
		novos = [_novo("Acompanhamento", cpf="123.456.789-09", name="nome-antigo")]

		resultado, _ = _calcular(associados=associados, novos_associados=novos)

		self.assertEqual(resultado["Lobinho"].novos, 0)

	def test_ramos_divergentes_contam_pelo_associado(self):
		associados = [{"name": id_por_cpf(CPF_ANA), "ramo": "Lobinho"}]
		novos = [_novo("Acompanhamento", ramo="Filhotes", cpf=CPF_ANA)]

		resultado, _ = _calcular(associados=associados, novos_associados=novos)

		self.assertEqual(resultado["Lobinho"].ativos, 1)
		self.assertEqual(resultado["Filhotes"].novos, 0)

	def test_sem_associado_ativo_o_novo_associado_conta(self):
		associados = [{"name": id_por_cpf(CPF_BETO), "ramo": "Lobinho"}]
		novos = [_novo("Acompanhamento", cpf=CPF_ANA)]

		resultado, _ = _calcular(associados=associados, novos_associados=novos)

		self.assertEqual(resultado["Lobinho"].ativos, 1)
		self.assertEqual(resultado["Lobinho"].novos, 1)

	def test_novo_associado_sem_cpf_conta_pelo_name(self):
		novos = [frappe._dict(name="NA-sem-cpf", cpf=None, ramo="Lobinho", status="Fazer Registro")]

		resultado, _ = _calcular(novos_associados=novos)

		self.assertEqual(resultado["Lobinho"].novos, 1)


class TestVagasDisponiveis(TestCase):
	def test_disponiveis_desconta_ocupacao_e_soma_saidas_proximas(self):
		vagas = {"limite_de_vagas_lobinho": 10, "idade_maxima_lobinho": 10}
		associados = [
			# Faz 10 anos daqui a 2 meses: sai dentro do horizonte de 6 meses.
			{"name": "A1", "ramo": "Lobinho", "data_de_nascimento": date(2016, 11, 12)},
			# Já passou da idade e continua ativo: fora da conta de quem está saindo.
			{"name": "A2", "ramo": "Lobinho", "data_de_nascimento": date(2016, 1, 1)},
			{"name": "A3", "ramo": "Lobinho", "data_de_nascimento": date(2019, 1, 1)},
			{"name": "A4", "ramo": "Lobinho", "data_de_nascimento": None},
		]
		novos = [_novo("Visita Agendada", cpf=CPF_ANA), _novo("Fazer Registro", cpf=CPF_BETO)]

		resultado, _ = _calcular(associados=associados, vagas=vagas, novos_associados=novos)

		lobinho = resultado["Lobinho"]
		self.assertEqual((lobinho.limite, lobinho.ativos, lobinho.novos, lobinho.saindo), (10, 4, 2, 1))
		self.assertEqual(lobinho.disponiveis, 10 - 4 - 2 + 1)
		self.assertEqual(lobinho.saidas_futuras, [date(2026, 1, 1), date(2026, 11, 12), date(2029, 1, 1)])

	def test_ramo_sem_configuracao_fica_zerado(self):
		resultado, _ = _calcular(novos_associados=[])

		self.assertEqual(resultado["Pioneiro"].limite, 0)
		self.assertEqual(resultado["Pioneiro"].disponiveis, 0)
		self.assertEqual(resultado["Pioneiro"].saidas_futuras, [])


class TestRamoSemVagas(TestCase):
	def test_selo_nos_cinco_status_com_zero_ou_negativo(self):
		for disponiveis in (0, -3):
			vagas = {"Lobinho": frappe._dict(disponiveis=disponiveis)}
			for status in recepcao_vagas.STATUS_COM_SELO_SEM_VAGAS:
				with self.subTest(status=status, disponiveis=disponiveis):
					self.assertTrue(recepcao_vagas.ramo_sem_vagas(vagas, "Lobinho", status))

		self.assertEqual(
			recepcao_vagas.STATUS_COM_SELO_SEM_VAGAS,
			("Novo Contato", "Conversa Inicial", "Visita Agendada", "Aguardar Dados", "Fazer Registro"),
		)

	def test_acompanhamento_nunca_leva_o_selo(self):
		vagas = {"Lobinho": frappe._dict(disponiveis=-3)}

		self.assertFalse(recepcao_vagas.ramo_sem_vagas(vagas, "Lobinho", "Acompanhamento"))

	def test_ramo_com_vaga_nao_leva_o_selo(self):
		vagas = {"Lobinho": frappe._dict(disponiveis=1)}

		self.assertFalse(recepcao_vagas.ramo_sem_vagas(vagas, "Lobinho", "Novo Contato"))

	def test_card_sem_ramo_nao_leva_o_selo(self):
		vagas = {"Lobinho": frappe._dict(disponiveis=0)}

		self.assertFalse(recepcao_vagas.ramo_sem_vagas(vagas, None, "Novo Contato"))
		self.assertFalse(recepcao_vagas.ramo_sem_vagas(vagas, "", "Novo Contato"))


class TestSeloSemVagasNaVisaoGeral(TestCase):
	"""O kanban entrega o selo pronto ao template, card a card."""

	def _contexto(self, jovens, capturados=None):
		capturados = {} if capturados is None else capturados

		def _get_all(doctype, *args, **kwargs):
			if doctype == "Novo Associado":
				capturados["fields"] = kwargs.get("fields") or []
				capturados["linhas"] = [frappe._dict(j) for j in jovens]
				return capturados["linhas"]
			return []

		def _calcular(novos_associados):
			capturados["recebidas"] = novos_associados
			return {
				"Lobinho": frappe._dict(disponiveis=0),
				"Filhotes": frappe._dict(disponiveis=2),
			}

		context = frappe._dict()
		with (
			patch.object(visao_geral, "enrich_context"),
			patch.object(visao_geral, "carregar_configuracao", return_value={}),
			patch.object(visao_geral.frappe, "get_all", side_effect=_get_all),
			patch.object(visao_geral, "getdate", return_value=HOJE),
			patch.object(visao_geral, "calcular_vagas_por_ramo", side_effect=_calcular),
		):
			visao_geral.get_context(context)
		return context

	def _card(self, context, nome):
		for cards in context.kanban_data.values():
			for card in cards:
				if card.name == nome:
					return card
		self.fail(f"card {nome} não foi renderizado")

	def test_card_de_ramo_lotado_leva_o_selo_com_o_numero(self):
		context = self._contexto(
			[{"name": "NA-1", "nome_completo": "Ana", "status": "Conversa Inicial", "ramo": "Lobinho"}]
		)

		card = self._card(context, "NA-1")
		self.assertTrue(card.sem_vagas)
		self.assertEqual(card.vagas_disponiveis, 0)

	def test_ramo_com_vaga_e_acompanhamento_ficam_sem_selo(self):
		context = self._contexto(
			[
				{"name": "NA-2", "nome_completo": "Beto", "status": "Conversa Inicial", "ramo": "Filhotes"},
				{"name": "NA-3", "nome_completo": "Caio", "status": "Acompanhamento", "ramo": "Lobinho"},
			]
		)

		for nome in ("NA-2", "NA-3"):
			card = self._card(context, nome)
			self.assertFalse(card.sem_vagas)
			self.assertIsNone(card.vagas_disponiveis)

	def test_a_conta_recebe_as_linhas_ja_carregadas_com_cpf(self):
		"""Sem o CPF na consulta, quem já é Associado seria contado duas vezes."""
		capturados = {}
		self._contexto(
			[{"name": "NA-4", "nome_completo": "Duda", "status": "Novo Contato", "ramo": "Lobinho"}],
			capturados,
		)

		self.assertIn("cpf", capturados["fields"])
		self.assertIs(capturados["recebidas"], capturados["linhas"])


class TestPrevisaoDeVagas(TestCase):
	"""O gráfico usa a fórmula do total: limite - ativos - novos + saídas de hoje em diante."""

	def test_saidas_que_ja_passaram_nao_somam_vaga(self):
		rotulos, valores = recepcao_vagas.previsao_mensal(
			4,
			[
				date(2026, 1, 1),  # já passou da idade e continua ativo
				date(2026, 9, 5),  # passou da idade neste mês, antes de hoje
				date(2026, 9, 20),
				date(2026, 11, 12),
				date(2029, 1, 1),
			],
			HOJE,
		)

		self.assertEqual(len(rotulos), 12)
		self.assertEqual(rotulos[:3], ["Set/26", "Out/26", "Nov/26"])
		# Soma 20/09 a partir de setembro e 12/11 a partir de novembro.
		self.assertEqual(valores, [5, 5] + [6] * 10)

	def test_sem_saidas_futuras_o_grafico_repete_o_total(self):
		_, valores = recepcao_vagas.previsao_mensal(4, [date(2025, 3, 1), date(2026, 2, 1)], HOJE)

		self.assertEqual(valores, [4] * 12)

	def test_a_conta_entrega_o_grafico_de_cada_ramo(self):
		vagas = {"limite_de_vagas_lobinho": 10, "idade_maxima_lobinho": 10}
		associados = [{"name": "A1", "ramo": "Lobinho", "data_de_nascimento": date(2016, 11, 12)}]

		resultado, _ = _calcular(associados=associados, vagas=vagas, novos_associados=[])

		# 10 - 1 - 0 = 9 agora; A1 atinge a idade máxima em 12/11/2026.
		self.assertEqual(resultado["Lobinho"].chart_labels[0], "Set/26")
		self.assertEqual(resultado["Lobinho"].chart_values, [9, 9] + [10] * 10)


def _ocupacao_de_exemplo():
	vagas = {"limite_de_vagas_lobinho": 10, "idade_maxima_lobinho": 10, "limite_de_vagas_filhotes": 12}
	associados = [{"name": "A1", "ramo": "Lobinho", "data_de_nascimento": date(2016, 11, 12)}]
	resultado, _ = _calcular(associados=associados, vagas=vagas, novos_associados=[_novo("Visita Agendada")])
	return resultado


class TestDadosDoDialog(TestCase):
	"""A Fila de Espera e os modais da visão geral abrem o mesmo dialog, com os mesmos números."""

	def test_leva_o_que_o_dialog_mostra_sem_as_datas_de_saida(self):
		dados = recepcao_vagas.dados_do_dialog(_ocupacao_de_exemplo())

		self.assertEqual(set(dados["Lobinho"]), set(recepcao_vagas.CAMPOS_DO_DIALOG))
		self.assertEqual(
			(dados["Lobinho"]["limite"], dados["Lobinho"]["ativos"], dados["Lobinho"]["novos"]), (10, 1, 1)
		)
		# Vai para o template como JSON: nenhuma data pode sobrar.
		self.assertEqual(json.loads(json.dumps(dados)), dados)

	def test_fila_de_espera_e_visao_geral_entregam_os_mesmos_dados(self):
		ocupacao = _ocupacao_de_exemplo()

		fila = frappe._dict()
		with (
			patch.object(fila_espera, "enrich_context"),
			patch.object(fila_espera, "calcular_vagas_por_ramo", return_value=ocupacao),
			patch.object(fila_espera.frappe, "get_all", return_value=[]),
		):
			fila_espera.get_context(fila)

		visao = frappe._dict()
		with (
			patch.object(visao_geral, "enrich_context"),
			patch.object(visao_geral, "carregar_configuracao", return_value={}),
			patch.object(visao_geral.frappe, "get_all", return_value=[]),
			patch.object(visao_geral, "calcular_vagas_por_ramo", return_value=ocupacao),
		):
			visao_geral.get_context(visao)

		esperado = recepcao_vagas.dados_do_dialog(ocupacao)
		self.assertEqual(fila.vagas_por_ramo, esperado)
		self.assertEqual(visao.vagas_por_ramo, esperado)
