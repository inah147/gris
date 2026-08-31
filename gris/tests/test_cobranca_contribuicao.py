"""Testes da cobrança da contribuição mensal por link InfinitePay.

Cobrem as três pontas do fluxo que o gestor enxerga: quais competências entram
numa cobrança, o que a baixa automática escreve no extrato quando o pagamento é
confirmado, e o recorte que garante que o responsável só vê os beneficiários
vinculados a ele.
"""

import datetime
import hashlib
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from gris.api.financeiro.cobranca_contribuicao import (
	FINALIDADE_CONTRIBUICAO,
	PREFIXO_ID_TRANSACAO,
	_normalizar_competencias,
	lancar_baixa,
	montar_cobranca,
	montar_mensagem,
	on_cobranca_atualizada,
)
from gris.api.financeiro.contribuicoes import (
	CATEGORIA_CONTRIBUICAO,
	STATUS_ATRASADO,
	STATUS_PAGO,
	STATUS_PARCIAL,
	apurar_associados,
	calcular_vencimento,
	chave_mes,
	competencias_pendentes,
	construir_meses,
	montar_grade,
)
from gris.api.responsavel_acesso import get_beneficiarios_associados
from gris.financeiro.doctype.cobranca_infinitepay import cobranca_infinitepay as cobranca_doctype

HOJE = datetime.date(2026, 8, 22)
VALOR = 60.0
VALOR_ATRASO = 70.0


def _apagar(doctype: str, filtros: dict) -> None:
	for nome in frappe.get_all(doctype, filters=filtros, pluck="name"):
		frappe.delete_doc(doctype, nome, force=True, ignore_permissions=True)


def _nome_por_cpf(cpf: str) -> str:
	"""Associado e Responsavel são nomeados pelo md5 do CPF, que também é gravado hasheado.

	Procurar pelo CPF em claro não acha nada — o nome derivado é o único jeito de
	saber se o registro do teste já existe.
	"""
	return hashlib.md5(cpf.encode("utf-8")).hexdigest()


class TestCompetenciasDaCobranca(FrappeTestCase):
	"""Seleção das competências cobradas — lógica pura, sem banco."""

	def setUp(self):
		self.meses = construir_meses(6, HOJE)
		self.vencimentos = {chave_mes(mes): calcular_vencimento(mes, 10) for mes in self.meses}

	def _grade(self, recebido):
		contribuinte = {"valor_contribuicao": VALOR, "inicio_do_pagamento": "2026-01-01"}
		return montar_grade(contribuinte, self.meses, recebido, HOJE, self.vencimentos, VALOR)

	def test_normalizar_aceita_csv_e_lista_sem_repetir(self):
		self.assertEqual(_normalizar_competencias("2026-07,2026-06,2026-07"), ["2026-06", "2026-07"])
		self.assertEqual(_normalizar_competencias(["2026-06", " 2026-05 "]), ["2026-05", "2026-06"])
		self.assertEqual(_normalizar_competencias(None), [])
		self.assertEqual(_normalizar_competencias(""), [])

	def test_normalizar_recusa_competencia_invalida(self):
		for invalida in ("2026-13", "26-07", "julho", "2026/07"):
			with self.assertRaises(frappe.ValidationError):
				_normalizar_competencias(invalida)

	def test_pendentes_listam_os_meses_nao_quitados(self):
		grade = self._grade({})
		pendentes = competencias_pendentes(grade)
		self.assertEqual(
			[p["ym"] for p in pendentes],
			["2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"],
		)
		self.assertTrue(all(p["valor"] == VALOR for p in pendentes))

	def test_mes_parcial_entra_pelo_que_falta(self):
		grade = self._grade({"2026-07": {"valor": 20.0, "qtd": 1}})
		pendentes = {p["ym"]: p for p in competencias_pendentes(grade)}
		self.assertEqual(pendentes["2026-07"]["status"], STATUS_PARCIAL)
		self.assertEqual(pendentes["2026-07"]["valor"], 40.0)

	def test_mes_quitado_fica_fora_da_cobranca(self):
		grade = self._grade({"2026-07": {"valor": VALOR, "qtd": 1}})
		self.assertNotIn("2026-07", [p["ym"] for p in competencias_pendentes(grade)])

	def test_mensagem_traz_competencias_valor_e_link(self):
		texto = montar_mensagem(
			{
				"name": "CM-teste",
				"competencias": ["2026-06", "2026-07"],
				"valor_total": 120.0,
				"link_pagamento": "https://pag.exemplo/abc",
			},
			"Fulano de Tal",
		)
		self.assertIn("06/2026, 07/2026", texto)
		self.assertIn("https://pag.exemplo/abc", texto)
		self.assertIn("Fulano de Tal", texto)
		self.assertIn("às contribuições", texto)


class TestBaixaDaCobranca(FrappeTestCase):
	"""Do pagamento confirmado ao mês quitado na apuração."""

	CPF = "99000000001"

	def setUp(self):
		self.associado = self._criar_associado()
		_apagar("Cobranca Infinitepay", {"associado": self.associado})
		_apagar("Transacao Extrato Geral", {"beneficiario": self.associado})
		frappe.db.set_single_value("Configuracao infinitepay", "handle", "grupo-teste")
		# A apuração cobra o valor de atraso do mês vencido: o teste fixa os dois
		# valores para não depender do que estiver configurado no site.
		frappe.db.set_single_value(
			"Configuracoes Contribuicao Mensal",
			{"valor_base": VALOR, "valor_atraso": VALOR_ATRASO, "dia_vencimento": 10},
		)

	def _criar_associado(self) -> str:
		nome = _nome_por_cpf(self.CPF)
		if frappe.db.exists("Associado", nome):
			return nome
		doc = frappe.get_doc(
			{
				"doctype": "Associado",
				"cpf": self.CPF,
				"nome_completo": "Beneficiário de Teste",
				"data_de_nascimento": "2015-01-01",
				"categoria": "Beneficiário",
				"status_no_grupo": "Ativo",
				"status_cobranca": "Ativo",
				"valor_contribuicao": VALOR,
				"inicio_do_pagamento": "2026-01-01",
				"telefone_cobranca": "11999990000",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def _sem_rede(self):
		"""Substitui a chamada à InfinitePay do `after_insert` por um link falso."""
		resposta = mock.Mock()
		resposta.json.return_value = {"checkout_url": "https://pag.exemplo/teste"}
		resposta.raise_for_status.return_value = None
		return mock.patch.object(cobranca_doctype.requests, "post", return_value=resposta)

	def _criar_cobranca(self, competencias: str, status: str = "Pendente", paid_amount: int = 0):
		"""Cobrança gravada sem sair para a rede."""
		with self._sem_rede():
			doc = frappe.get_doc(
				{
					"doctype": "Cobranca Infinitepay",
					"order_nsu": f"CM-teste-{competencias.replace(',', '-')}-{status}",
					"status": status,
					"finalidade": FINALIDADE_CONTRIBUICAO,
					"associado": self.associado,
					"competencias": competencias,
					"paid_amount": paid_amount,
					"itens": [
						{"descricao": f"Contribuição {ym}", "quantidade": 1, "preco": VALOR}
						for ym in competencias.split(",")
					],
				}
			)
			doc.insert(ignore_permissions=True)
		doc.reload()
		return doc

	def test_baixa_lanca_credito_de_contribuicao_no_extrato(self):
		cobranca = self._criar_cobranca("2026-06,2026-07", status="Pago", paid_amount=12000)
		nome_transacao = lancar_baixa(cobranca)

		transacao = frappe.get_doc("Transacao Extrato Geral", nome_transacao)
		self.assertEqual(transacao.debito_credito, "Crédito")
		self.assertEqual(transacao.categoria, CATEGORIA_CONTRIBUICAO)
		self.assertEqual(transacao.beneficiario, self.associado)
		self.assertEqual(float(transacao.valor), 120.0)
		# A competência mais antiga cobrada é a que ancora a apuração; o crédito
		# que sobra quita as seguintes.
		self.assertEqual(getdate(transacao.mes_competencia), datetime.date(2026, 6, 1))
		self.assertEqual(
			frappe.db.get_value("Cobranca Infinitepay", cobranca.name, "transacao_extrato"),
			nome_transacao,
		)

	def test_baixa_e_idempotente(self):
		cobranca = self._criar_cobranca("2026-06", status="Pago", paid_amount=6000)
		primeira = lancar_baixa(cobranca)
		cobranca.reload()
		segunda = lancar_baixa(cobranca)

		self.assertEqual(primeira, segunda)
		self.assertEqual(primeira, f"{PREFIXO_ID_TRANSACAO}{cobranca.name}")
		self.assertEqual(frappe.db.count("Transacao Extrato Geral", {"beneficiario": self.associado}), 1)

	def test_handler_ignora_cobranca_que_nao_foi_paga(self):
		cobranca = self._criar_cobranca("2026-06", status="Pendente")
		on_cobranca_atualizada(cobranca)
		self.assertEqual(frappe.db.count("Transacao Extrato Geral", {"beneficiario": self.associado}), 0)

	def test_handler_ignora_cobranca_avulsa(self):
		cobranca = self._criar_cobranca("2026-06", status="Pendente")
		cobranca.finalidade = "Avulsa"
		cobranca.status = "Pago"
		cobranca.paid_amount = 6000
		on_cobranca_atualizada(cobranca)
		self.assertEqual(frappe.db.count("Transacao Extrato Geral", {"beneficiario": self.associado}), 0)

	def test_confirmacao_de_pagamento_da_baixa_pelo_doc_event(self):
		"""O caminho real: o webhook salva a cobrança como Paga e o extrato recebe o crédito.

		Nenhuma chamada explícita a `lancar_baixa` aqui — quem dispara é o
		`on_update` registrado em `doc_events`.
		"""
		cobranca = self._criar_cobranca("2026-06", status="Pendente")
		self.assertEqual(frappe.db.count("Transacao Extrato Geral", {"beneficiario": self.associado}), 0)

		cobranca.status = "Pago"
		cobranca.paid_amount = 6000
		with self._sem_rede():
			cobranca.save(ignore_permissions=True)

		self.assertEqual(frappe.db.count("Transacao Extrato Geral", {"beneficiario": self.associado}), 1)
		self.assertTrue(frappe.db.get_value("Cobranca Infinitepay", cobranca.name, "transacao_extrato"))

	def test_pagamento_quita_o_mes_atrasado_na_apuracao(self):
		antes = apurar_associados([self.associado], 6, HOJE)[0]
		situacao_antes = {linha["ym"]: linha["status"] for linha in antes["linhas"]}
		self.assertEqual(situacao_antes["2026-06"], STATUS_ATRASADO)
		self.assertEqual(situacao_antes["2026-07"], STATUS_ATRASADO)

		# Dois meses vencidos custam o valor de atraso, não o valor em dia.
		total = round(2 * VALOR_ATRASO * 100)
		cobranca = self._criar_cobranca("2026-06,2026-07", status="Pago", paid_amount=total)
		lancar_baixa(cobranca)

		depois = apurar_associados([self.associado], 6, HOJE)[0]
		situacao_depois = {linha["ym"]: linha["status"] for linha in depois["linhas"]}
		self.assertEqual(situacao_depois["2026-06"], STATUS_PAGO)
		self.assertEqual(situacao_depois["2026-07"], STATUS_PAGO)
		self.assertEqual(depois["total_recebido"], 2 * VALOR_ATRASO)

	def test_pagamento_do_valor_em_dia_quita_o_mes_atrasado(self):
		"""Pagar 60 num mês já vencido fecha o mês: o acréscimo é o que se cobra."""
		cobranca = self._criar_cobranca("2026-06", status="Pago", paid_amount=int(VALOR * 100))
		lancar_baixa(cobranca)

		depois = apurar_associados([self.associado], 6, HOJE)[0]
		junho = next(linha for linha in depois["linhas"] if linha["ym"] == "2026-06")
		self.assertEqual(junho["status"], STATUS_PAGO)
		self.assertEqual(junho["esperado"], VALOR_ATRASO)
		self.assertEqual(junho["falta"], 0.0)
		self.assertTrue(junho["quitado_sem_acrescimo"])

	def test_montar_cobranca_recusa_competencia_ja_quitada(self):
		cobranca = self._criar_cobranca("2026-06", status="Pago", paid_amount=int(VALOR * 100))
		lancar_baixa(cobranca)

		with self.assertRaises(frappe.ValidationError), self._sem_rede():
			montar_cobranca(self.associado, "2026-06", meses=6)

	def test_montar_cobranca_cria_um_item_por_competencia(self):
		with self._sem_rede():
			resultado = montar_cobranca(self.associado, "2026-06,2026-07", meses=12)

		emitida = frappe.get_doc("Cobranca Infinitepay", resultado["name"])
		self.assertEqual(emitida.finalidade, FINALIDADE_CONTRIBUICAO)
		self.assertEqual(emitida.associado, self.associado)
		self.assertEqual(emitida.competencias, "2026-06,2026-07")
		self.assertEqual(len(emitida.itens), 2)
		# Os dois meses já venceram: a cobrança sai pelo valor de atraso.
		self.assertEqual(resultado["valor_total"], 2 * VALOR_ATRASO)


class TestRecorteDoResponsavel(FrappeTestCase):
	"""O responsável só apura os beneficiários vinculados a ele."""

	CPF_RESPONSAVEL = "99000000010"
	CPF_FILHO = "99000000011"
	CPF_ALHEIO = "99000000012"

	def setUp(self):
		self.responsavel = self._criar_responsavel()
		self.filho = self._criar_beneficiario(self.CPF_FILHO, "Filho Vinculado")
		self.alheio = self._criar_beneficiario(self.CPF_ALHEIO, "Beneficiário de Outra Família")
		self._criar_vinculo(self.responsavel, self.filho)

	def _criar_responsavel(self) -> str:
		nome = _nome_por_cpf(self.CPF_RESPONSAVEL)
		if frappe.db.exists("Responsavel", nome):
			return nome
		doc = frappe.get_doc(
			{
				"doctype": "Responsavel",
				"cpf": self.CPF_RESPONSAVEL,
				"nome_completo": "Responsável de Teste",
				"email": "responsavel.teste@exemplo.org",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def _criar_beneficiario(self, cpf: str, nome: str) -> str:
		registro = _nome_por_cpf(cpf)
		if frappe.db.exists("Associado", registro):
			return registro
		doc = frappe.get_doc(
			{
				"doctype": "Associado",
				"cpf": cpf,
				"nome_completo": nome,
				"data_de_nascimento": "2015-01-01",
				"categoria": "Beneficiário",
				"status_no_grupo": "Ativo",
				"status_cobranca": "Ativo",
				"valor_contribuicao": VALOR,
				"inicio_do_pagamento": "2026-01-01",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def _criar_vinculo(self, responsavel: str, associado: str) -> None:
		if frappe.db.exists(
			"Responsavel Vinculo", {"responsavel": responsavel, "beneficiario_associado": associado}
		):
			return
		frappe.get_doc(
			{
				"doctype": "Responsavel Vinculo",
				"responsavel": responsavel,
				"beneficiario_associado": associado,
			}
		).insert(ignore_permissions=True)

	def test_vinculo_lista_so_os_beneficiarios_do_responsavel(self):
		vinculados = get_beneficiarios_associados(self.responsavel)
		self.assertIn(self.filho, vinculados)
		self.assertNotIn(self.alheio, vinculados)

	def test_responsavel_sem_vinculo_nao_apura_ninguem(self):
		self.assertEqual(get_beneficiarios_associados(None), [])
		self.assertEqual(apurar_associados([], 6, HOJE), [])

	def test_apuracao_do_responsavel_cobre_apenas_o_vinculado(self):
		apurados = apurar_associados(get_beneficiarios_associados(self.responsavel), 6, HOJE)
		self.assertEqual([a["id"] for a in apurados], [self.filho])

	def test_dirigente_fica_fora_mesmo_vinculado(self):
		frappe.db.set_value("Associado", self.filho, "categoria", "Dirigente")
		try:
			apurados = apurar_associados([self.filho], 6, HOJE)
			self.assertEqual(apurados, [])
		finally:
			frappe.db.set_value("Associado", self.filho, "categoria", "Beneficiário")
