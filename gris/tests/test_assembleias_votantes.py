# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Lista de presença: regra de voto do estatuto (art. 9º) e edição à mão (spec RF-07)."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate

from gris.api.assembleias import constantes as c
from gris.api.assembleias import votantes
from gris.api.assembleias.pessoas import idade_em_meses
from gris.tests.test_assembleias_criacao import _criar

DATA = getdate("2026-12-05")
VALIDADE = "2027-03-31"

REGRAS = {
	"escotistas": 1,
	"dirigentes": 1,
	"demais": 1,
	"exigir_registro": 1,
	"jovens": 1,
	"idade_voto_meses": 16 * 12,
	"representacao": 1,
	"idade_representacao_meses": 78,
	"equipes": [],
}


def _a(name, categoria, nascimento=None, ramo="", equipe="", status="Válido", validade=VALIDADE, nome=None):
	return frappe._dict(
		name=name,
		nome_completo=nome or f"Pessoa {name}",
		categoria=categoria,
		ramo=ramo,
		equipe=equipe,
		data_de_nascimento=nascimento,
		status=status,
		validade_registro=validade,
	)


def _tipos(linhas):
	return {linha["pessoa"] or linha["nome"]: linha["tipo_linha"] for linha in linhas}


class TestRegraDeVoto(FrappeTestCase):
	def test_categorias_adultas(self):
		linhas, _avisos = votantes.montar_votantes(
			REGRAS,
			[_a("e", "Escotista", "1990-01-01"), _a("d", "Dirigente"), _a("x", "Contribuinte")],
			DATA,
		)
		self.assertEqual(
			_tipos(linhas), {"e": c.LINHA_ESCOTISTA, "d": c.LINHA_DIRIGENTE, "x": c.LINHA_ASSOCIADO}
		)

	def test_checks_desligados(self):
		regras = {**REGRAS, "escotistas": 0, "demais": 0}
		linhas, _avisos = votantes.montar_votantes(
			regras, [_a("e", "Escotista"), _a("d", "Dirigente"), _a("x", "Contribuinte")], DATA
		)
		self.assertEqual(_tipos(linhas), {"d": c.LINHA_DIRIGENTE})

	def test_idades_do_estatuto(self):
		associados = [
			_a("16", "Beneficiário", "2010-12-05"),  # faz 16 no dia: vota
			_a("15", "Beneficiário", "2010-12-06"),  # 15 anos: representado
			_a("6m6", "Beneficiário", "2020-06-05"),  # 6 anos e 6 meses: representado
			_a("6m5", "Beneficiário", "2020-06-06"),  # um dia antes dos 6,5: fora
			_a("pio", "Beneficiário", "2004-01-01", ramo="Pioneiro"),
		]
		linhas, _avisos = votantes.montar_votantes(REGRAS, associados, DATA)
		self.assertEqual(
			_tipos(linhas),
			{
				"16": c.LINHA_JOVEM,
				"15": c.LINHA_JOVEM_REPRESENTADO,
				"6m6": c.LINHA_JOVEM_REPRESENTADO,
				"pio": c.LINHA_JOVEM,
			},
		)
		self.assertEqual(idade_em_meses("2020-06-05", DATA), 78)

	def test_sem_representacao(self):
		regras = {**REGRAS, "representacao": 0}
		linhas, _avisos = votantes.montar_votantes(regras, [_a("15", "Beneficiário", "2010-12-06")], DATA)
		self.assertEqual(linhas, [])

	def test_registro_vencido_fica_de_fora_e_e_contado(self):
		associados = [
			_a("ok", "Escotista"),
			_a("venc", "Escotista", status="Vencido"),
			_a("valido_mas_expira", "Dirigente", validade="2026-12-04"),
		]
		linhas, avisos = votantes.montar_votantes(REGRAS, associados, DATA)
		self.assertEqual(_tipos(linhas), {"ok": c.LINHA_ESCOTISTA})
		self.assertEqual(avisos["registro_vencido"], 2)

		linhas, avisos = votantes.montar_votantes({**REGRAS, "exigir_registro": 0}, associados, DATA)
		self.assertEqual(len(linhas), 3)
		self.assertEqual(avisos["registro_vencido"], 0)

	def test_beneficiario_sem_nascimento(self):
		linhas, avisos = votantes.montar_votantes(REGRAS, [_a("b", "Beneficiário")], DATA)
		self.assertEqual(linhas, [])
		self.assertEqual(avisos["sem_nascimento"], 1)

	def test_equipe_soma_as_linhas_dos_jovens(self):
		regras = {**REGRAS, "equipes": ["Escoteiro"]}
		associados = [
			_a("j1", "Beneficiário", "2013-01-01", ramo="Escoteiro", equipe="Patrulha Lobo"),
			_a("j2", "Beneficiário", "2013-02-01", ramo="Escoteiro", equipe="patrulha  lobo"),
			_a("j3", "Beneficiário", "2013-03-01", ramo="Escoteiro", equipe="Patrulha Águia"),
			_a("j4", "Beneficiário", "2013-04-01", ramo="Escoteiro"),
			_a("l1", "Beneficiário", "2018-01-01", ramo="Lobinho", equipe="Matilha Cinza"),
		]
		linhas, avisos = votantes.montar_votantes(regras, associados, DATA)
		equipes = [linha["nome"] for linha in linhas if linha["tipo_linha"] == c.LINHA_EQUIPE]
		self.assertEqual(
			equipes,
			["Representante — Patrulha Águia (Escoteiro)", "Representante — Patrulha Lobo (Escoteiro)"],
		)
		# Os jovens continuam com a própria linha (soma, não substitui).
		self.assertEqual(sum(1 for linha in linhas if linha["tipo_linha"] == c.LINHA_JOVEM_REPRESENTADO), 5)
		self.assertEqual(avisos["sem_equipe"], {"Escoteiro": 1})

	def test_pessoa_repetida_aparece_uma_vez(self):
		linhas, _avisos = votantes.montar_votantes(REGRAS, [_a("e", "Escotista"), _a("e", "Dirigente")], DATA)
		self.assertEqual(len(linhas), 1)


class TestAplicarLista(FrappeTestCase):
	def _gerada(self, pessoa, tipo=c.LINHA_ESCOTISTA, nome=None):
		return {
			"nome": nome or pessoa,
			"tipo_linha": tipo,
			"pessoa_tipo": "Associado",
			"pessoa": pessoa,
			"ramo": "",
			"equipe": "",
			"origem": "Automática",
			"removido": 0,
		}

	def test_manual_fica_e_removida_nao_volta(self):
		existentes = [
			{**self._gerada("a"), "removido": 1},
			{**self._gerada("", c.LINHA_MANUAL, "Convidado"), "origem": "Manual", "pessoa_tipo": ""},
		]
		resultado = votantes.aplicar_lista(existentes, [self._gerada("a"), self._gerada("b")])
		ativos = [linha["nome"] for linha in resultado if not linha["removido"]]
		self.assertEqual(ativos, ["b", "Convidado"])
		self.assertEqual([linha["nome"] for linha in resultado if linha["removido"]], ["a"])

	def test_removida_que_nao_e_mais_gerada_some(self):
		existentes = [{**self._gerada("a"), "removido": 1}]
		self.assertEqual(votantes.aplicar_lista(existentes, [self._gerada("b")])[0]["nome"], "b")

	def test_totais_e_maioria_absoluta(self):
		linhas = [self._gerada(str(i)) for i in range(7)] + [{**self._gerada("x"), "removido": 1}]
		t = votantes.totais(linhas)
		self.assertEqual(t["total"], 7)
		self.assertEqual(t["maioria_absoluta"], 4)
		self.assertEqual(t["por_tipo"], [{"tipo": c.LINHA_ESCOTISTA, "total": 7}])


class TestEndpointsDaLista(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		for name in frappe.get_all(c.DOCTYPE_ASSEMBLEIA, pluck="name"):
			frappe.delete_doc(c.DOCTYPE_ASSEMBLEIA, name, force=True)
		self.name = _criar(add_days(getdate(), 30))["name"]

	def tearDown(self):
		frappe.db.rollback()

	def test_incluir_remover_e_restaurar(self):
		dados = votantes.incluir_votante(self.name, nome_livre="  Convidada   da Região ")
		linha = next(linha for linha in dados["linhas"] if linha["nome"] == "Convidada da Região")
		self.assertEqual(linha["origem"], "Manual")

		votantes.gerar_lista(self.name)
		dados = votantes.gerar_lista(self.name)
		self.assertIn("Convidada da Região", [linha["nome"] for linha in dados["linhas"]])

		convidada = next(linha["name"] for linha in dados["linhas"] if linha["nome"] == "Convidada da Região")
		dados = votantes.remover_votante(self.name, convidada)
		self.assertNotIn("Convidada da Região", [linha["nome"] for linha in dados["linhas"]])
		self.assertFalse(dados["removidas"])  # manual removida sai de vez

	def test_automatica_removida_nao_volta_e_pode_ser_restaurada(self):
		dados = votantes.gerar_lista(self.name)
		if not dados["linhas"]:
			self.skipTest("dev.gris sem associados elegíveis")
		alvo = dados["linhas"][0]
		dados = votantes.remover_votante(self.name, alvo["name"])
		dados = votantes.gerar_lista(self.name)
		self.assertNotIn(alvo["nome"], [linha["nome"] for linha in dados["linhas"]])
		removida = next(linha for linha in dados["removidas"] if linha["nome"] == alvo["nome"])
		dados = votantes.restaurar_votante(self.name, removida["name"])
		self.assertIn(alvo["nome"], [linha["nome"] for linha in dados["linhas"]])

	def test_nao_edita_depois_da_assembleia(self):
		frappe.db.set_value(c.DOCTYPE_ASSEMBLEIA, self.name, "data", add_days(getdate(), -1))
		with self.assertRaisesRegex(frappe.ValidationError, "já aconteceu"):
			votantes.gerar_lista(self.name)

	def test_inclusao_sem_nome_e_recusada(self):
		with self.assertRaises(frappe.ValidationError):
			votantes.incluir_votante(self.name, nome_livre="   ")
