# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# See license.txt

"""Testes da sincronizacao de feriados (gris/api/calendario/sync_feriados.py)."""

from datetime import date
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.calendario import sync_feriados as modulo

# Santo Andre (SP). O prefixo 35 do codigo do IBGE identifica a UF.
CODIGO_IBGE = "3547809"
ANO = 2026

NACIONAIS = [
	{
		"data": "01/01/2026",
		"nome": "Ano Novo",
		"tipo": "NACIONAL",
		"descricao": "Confraternização Universal",
		"uf": None,
		"codigo_ibge": None,
	},
	{
		"data": "03/04/2026",
		"nome": "Sexta-Feira Santa",
		"tipo": "NACIONAL",
		"descricao": "Paixão de Cristo",
		"uf": None,
		"codigo_ibge": None,
	},
]

ESTADUAIS = [
	{
		"data": "09/07/2026",
		"nome": "Revolução Constitucionalista",
		"tipo": "ESTADUAL",
		"descricao": "Feriado estadual de São Paulo",
		"uf": "SP",
		"codigo_ibge": None,
	},
	{
		"data": "23/01/2026",
		"nome": "Dia do Evangélico",
		"tipo": "ESTADUAL",
		"descricao": "Feriado estadual do Acre",
		"uf": "AC",
		"codigo_ibge": None,
	},
]

MUNICIPAIS = [
	{
		"data": "08/04/2026",
		"nome": "Aniversário da Cidade",
		"tipo": "MUNICIPAL",
		"descricao": "conforme Lei Municipal nº 4.148 de 11/05/1973",
		"uf": "SP",
		"codigo_ibge": 3547809,
	},
	{
		# Mesma data do feriado nacional: a lei do municipio repete a data.
		"data": "03/04/2026",
		"nome": "Sexta-feira Santa",
		"tipo": "MUNICIPAL",
		"descricao": "conforme Lei Municipal nº 4.148 de 11/05/1973",
		"uf": "SP",
		"codigo_ibge": 3547809,
	},
	{
		"data": "25/01/2026",
		"nome": "Aniversário de São Paulo",
		"tipo": "MUNICIPAL",
		"descricao": "Outro municipio",
		"uf": "SP",
		"codigo_ibge": 3550308,
	},
]

POR_ABRANGENCIA = {"nacional": NACIONAIS, "estadual": ESTADUAIS, "municipal": MUNICIPAIS}


class RespostaFalsa:
	def __init__(self, dados, status_code=200):
		self._dados = dados
		self.status_code = status_code

	def json(self):
		return self._dados

	def raise_for_status(self):
		if self.status_code >= 400:
			raise AssertionError(f"HTTP {self.status_code}")


def _get_falso(url, **_kwargs):
	for abrangencia, dados in POR_ABRANGENCIA.items():
		if f"/{abrangencia}/json/" in url:
			return RespostaFalsa(dados)
	return RespostaFalsa(None, status_code=404)


class TestSyncFeriados(FrappeTestCase):
	def setUp(self):
		frappe.db.delete("Feriados", {"data": ["between", [f"{ANO}-01-01", f"{ANO}-12-31"]]})
		settings = frappe.get_single("Configuracoes de Feriados")
		settings.codigo_municipio_ibge = CODIGO_IBGE
		settings.save()
		frappe.db.commit()

	def _sincronizar(self):
		with (
			mock.patch.object(modulo.requests, "get", side_effect=_get_falso),
			mock.patch.object(modulo, "datetime", wraps=modulo.datetime) as relogio,
		):
			relogio.now.return_value = date(ANO, 6, 1)
			modulo.sync_feriados()

	def _gravados(self):
		return frappe.get_all(
			"Feriados",
			filters={"data": ["between", [f"{ANO}-01-01", f"{ANO}-12-31"]]},
			fields=["name", "nome", "data", "tipo", "descricao"],
			order_by="data asc",
		)

	def test_grava_nacional_estadual_da_uf_e_municipal_do_municipio(self):
		self._sincronizar()

		gravados = self._gravados()
		self.assertEqual(
			[(f.data, f.nome, f.tipo) for f in gravados],
			[
				(date(2026, 1, 1), "Ano Novo", "Nacional"),
				(date(2026, 4, 3), "Sexta-Feira Santa", "Nacional"),
				(date(2026, 4, 8), "Aniversário da Cidade", "Municipal"),
				(date(2026, 7, 9), "Revolução Constitucionalista", "Estadual"),
			],
		)

	def test_ignora_estadual_de_outra_uf_e_municipal_de_outro_municipio(self):
		self._sincronizar()

		nomes = [f.nome for f in self._gravados()]
		self.assertNotIn("Dia do Evangélico", nomes)
		self.assertNotIn("Aniversário de São Paulo", nomes)

	def test_nao_duplica_feriado_que_o_municipio_repete(self):
		"""Sexta-feira Santa e nacional e tambem lei municipal: vale uma vez so."""
		self._sincronizar()

		na_data = [f for f in self._gravados() if f.data == date(2026, 4, 3)]
		self.assertEqual(len(na_data), 1)
		self.assertEqual(na_data[0].tipo, "Nacional")

	def test_rodar_de_novo_nao_duplica_nem_altera(self):
		self._sincronizar()
		antes = self._gravados()

		self._sincronizar()
		depois = self._gravados()

		self.assertEqual(len(antes), len(depois))
		self.assertEqual([f.name for f in antes], [f.name for f in depois])

	def test_reaproveita_registro_da_integracao_anterior(self):
		"""O id antigo vinha da API paga: a troca de fonte nao pode duplicar o feriado."""
		frappe.get_doc(
			{
				"doctype": "Feriados",
				"id": "id-antigo-da-api",
				"nome": "Ano Novo",
				"data": date(2026, 1, 1),
				"tipo": "nacional",
				"descricao": "Descrição antiga",
			}
		).insert()
		frappe.db.commit()

		self._sincronizar()

		em_1_de_janeiro = [f for f in self._gravados() if f.data == date(2026, 1, 1)]
		self.assertEqual(len(em_1_de_janeiro), 1)
		self.assertEqual(em_1_de_janeiro[0].name, "id-antigo-da-api")
		self.assertEqual(em_1_de_janeiro[0].tipo, "Nacional")

	def test_sem_codigo_do_municipio_nao_grava_nada(self):
		settings = frappe.get_single("Configuracoes de Feriados")
		settings.codigo_municipio_ibge = ""
		settings.save()
		frappe.db.commit()

		self._sincronizar()

		self.assertEqual(self._gravados(), [])

	def test_codigo_do_municipio_sem_uf_correspondente_nao_grava_nada(self):
		settings = frappe.get_single("Configuracoes de Feriados")
		settings.codigo_municipio_ibge = "9999999"
		settings.save()
		frappe.db.commit()

		self._sincronizar()

		self.assertEqual(self._gravados(), [])

	def test_ano_ainda_nao_publicado_nao_quebra_o_job(self):
		def so_404(url, **_kwargs):
			return RespostaFalsa(None, status_code=404)

		with (
			mock.patch.object(modulo.requests, "get", side_effect=so_404),
			mock.patch.object(modulo, "datetime", wraps=modulo.datetime) as relogio,
		):
			relogio.now.return_value = date(ANO, 6, 1)
			modulo.sync_feriados()

		self.assertEqual(self._gravados(), [])

	def test_identificador_e_estavel_e_derivado_da_data_e_do_nome(self):
		self.assertEqual(
			modulo._identificador("2026-04-08", "Aniversário da Cidade"),
			"2026-04-08-aniversario-da-cidade",
		)
