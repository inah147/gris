# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_months, getdate

from gris.api.financeiro.previsao_orcamentaria import (
	_agrupar,
	_mes_label,
	_normalizar_item,
	atualizar_previsao,
	criar_previsao,
	excluir_item,
	excluir_previsao,
	obter_comparativo,
	salvar_item,
)
from gris.www.financeiro.previsao_orcamentaria import previsao_padrao

CENTRO_TESTE = "Centro Previsão Teste"


def _centro_de_custo():
	"""Centro de custo exclusivo do teste — isola o realizado de outros dados do site."""
	if not frappe.db.exists("Centro de Custo", CENTRO_TESTE):
		frappe.get_doc({"doctype": "Centro de Custo", "nome": CENTRO_TESTE}).insert(ignore_permissions=True)
	return CENTRO_TESTE


def _transacao(
	id_transacao: str,
	data: str,
	valor: float,
	categoria: str | None = None,
	excluir_do_total: int = 0,
):
	"""Cria uma transação no extrato geral usada como 'realizado' do comparativo."""
	return frappe.get_doc(
		{
			"doctype": "Transacao Extrato Geral",
			"id": id_transacao,
			"descricao": id_transacao,
			"debito_credito": "Crédito" if valor > 0 else "Débito",
			"valor": valor,
			"valor_absoluto": abs(valor),
			"data_deposito": data,
			"metodo": "Pix",
			"centro_de_custo": CENTRO_TESTE,
			"categoria": categoria,
			"excluir_do_total": excluir_do_total,
		}
	).insert(ignore_permissions=True)


class TestPrevisaoOrcamentariaHelpers(FrappeTestCase):
	def test_mes_label(self):
		self.assertEqual(_mes_label("2026-03"), "03/26")

	def test_normalizar_item_aceita_item_valido(self):
		item = _normalizar_item(
			{
				"tipo": "Despesa",
				"descricao": "  Aluguel  ",
				"valor_previsto": "1200.50",
				"distribuicao": "Mês específico",
				"mes_referencia": "2026-04-19",
			}
		)
		self.assertEqual(item["descricao"], "Aluguel")
		self.assertEqual(item["valor_previsto"], 1200.50)
		self.assertEqual(str(item["mes_referencia"]), "2026-04-01")

	def test_normalizar_item_limpa_mes_na_distribuicao_uniforme(self):
		item = _normalizar_item(
			{
				"tipo": "Receita",
				"descricao": "Mensalidades",
				"valor_previsto": 100,
				"distribuicao": "Uniforme no período",
				"mes_referencia": "2026-04-01",
			}
		)
		self.assertIsNone(item["mes_referencia"])

	def test_normalizar_item_rejeita_tipo_invalido(self):
		with self.assertRaises(frappe.ValidationError):
			_normalizar_item({"tipo": "Outro", "descricao": "X", "valor_previsto": 10})

	def test_normalizar_item_rejeita_valor_nao_positivo(self):
		with self.assertRaises(frappe.ValidationError):
			_normalizar_item({"tipo": "Despesa", "descricao": "X", "valor_previsto": 0})

	def test_normalizar_item_exige_mes_quando_especifico(self):
		with self.assertRaises(frappe.ValidationError):
			_normalizar_item(
				{
					"tipo": "Despesa",
					"descricao": "X",
					"valor_previsto": 10,
					"distribuicao": "Mês específico",
				}
			)

	def test_agrupar_junta_previsto_e_realizado(self):
		linhas = _agrupar(
			{"Aluguel": 300.0, "Água": 50.0},
			{"Aluguel": 300.0, "Água": 50.0},
			{"Aluguel": 420.0, "Luz": 80.0},
			"Sem categoria",
		)
		por_rotulo = {linha["rotulo"]: linha for linha in linhas}
		self.assertEqual(por_rotulo["Aluguel"]["desvio"], 120.0)
		self.assertEqual(por_rotulo["Água"]["realizado"], 0.0)
		self.assertEqual(por_rotulo["Luz"]["previsto"], 0.0)
		# Ordenado pelo maior valor entre previsto e realizado.
		self.assertEqual(linhas[0]["rotulo"], "Aluguel")

	def test_agrupar_mede_o_desvio_contra_o_previsto_ate_hoje(self):
		# Metade do ano corrido: o previsto do período inteiro não pode virar base.
		linhas = _agrupar({"Aluguel": 1200.0}, {"Aluguel": 600.0}, {"Aluguel": 700.0}, "Sem categoria")
		self.assertEqual(linhas[0]["previsto"], 1200.0)
		self.assertEqual(linhas[0]["previsto_ate_hoje"], 600.0)
		self.assertEqual(linhas[0]["desvio"], 100.0)

	def test_agrupar_descarta_linhas_zeradas(self):
		self.assertEqual(_agrupar({"Vazia": 0.0}, {"Vazia": 0.0}, {"Vazia": 0.0}, "Sem categoria"), [])


class TestObterComparativo(FrappeTestCase):
	# FrappeTestCase só faz rollback no fim da classe, então o cenário é montado
	# uma única vez em setUpClass — em setUp ele colidiria a partir do 2º teste.
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.previsao = frappe.get_doc(
			{
				"doctype": "Previsao Orcamentaria",
				"titulo": "Comparativo Teste",
				"exercicio": 2026,
				"status": "Aprovada",
				"data_inicio": "2026-01-01",
				"data_fim": "2026-03-31",
				"centro_de_custo": _centro_de_custo(),
				"itens": [
					{"tipo": "Receita", "descricao": "Contribuições", "valor_previsto": 3000},
					{
						"tipo": "Despesa",
						"descricao": "Acampamento",
						"valor_previsto": 900,
						"distribuicao": "Mês específico",
						"mes_referencia": "2026-02-01",
					},
				],
			}
		).insert()

		_transacao("PREV-TESTE-C1", "2026-01-10", 800)
		_transacao("PREV-TESTE-D1", "2026-02-15", -1100)
		# Fora do período: não deve entrar no comparativo.
		_transacao("PREV-TESTE-FORA", "2026-06-01", -5000)

	def test_series_mensais_cobrem_todo_o_periodo(self):
		resultado = obter_comparativo(self.previsao.name)
		self.assertTrue(resultado["success"])
		self.assertEqual(resultado["meses"], ["2026-01", "2026-02", "2026-03"])
		self.assertEqual(resultado["labels"], ["01/26", "02/26", "03/26"])
		self.assertEqual(resultado["series"]["receitas_previstas"], [1000.0, 1000.0, 1000.0])
		self.assertEqual(resultado["series"]["despesas_previstas"], [0.0, 900.0, 0.0])

	def test_realizado_respeita_o_periodo_da_previsao(self):
		resultado = obter_comparativo(self.previsao.name)
		self.assertEqual(resultado["series"]["receitas_realizadas"], [800.0, 0.0, 0.0])
		self.assertEqual(resultado["series"]["despesas_realizadas"], [0.0, 1100.0, 0.0])
		self.assertEqual(resultado["totais"]["despesas_realizadas"], 1100.0)

	def test_totais_e_desvios(self):
		totais = obter_comparativo(self.previsao.name)["totais"]
		self.assertEqual(totais["receitas_previstas"], 3000.0)
		self.assertEqual(totais["despesas_previstas"], 900.0)
		self.assertEqual(totais["desvio_receitas"], -2200.0)
		self.assertEqual(totais["desvio_despesas"], 200.0)
		self.assertEqual(totais["resultado_realizado"], -300.0)


class TestRealizadoSegueOsFiltrosDoDashboard(FrappeTestCase):
	"""O realizado do comparativo tem que excluir o mesmo que o dashboard exclui."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.previsao = frappe.get_doc(
			{
				"doctype": "Previsao Orcamentaria",
				"titulo": "Filtros Teste",
				"exercicio": 2026,
				"status": "Aprovada",
				"data_inicio": "2026-01-01",
				"data_fim": "2026-03-31",
				"centro_de_custo": _centro_de_custo(),
				"itens": [{"tipo": "Despesa", "descricao": "Aluguel", "valor_previsto": 3000}],
			}
		).insert()
		_transacao("FILTRO-VALE", "2026-01-10", -1000)

	def _despesas(self):
		return obter_comparativo(self.previsao.name)["totais"]["despesas_realizadas"]

	def test_transacao_marcada_como_excluida_do_total_nao_entra(self):
		# É a marca que a conciliação põe na cópia redundante planilha/sistema.
		self.assertEqual(self._despesas(), 1000.0)
		_transacao("FILTRO-DUPLICATA", "2026-02-10", -5000, excluir_do_total=1)
		self.assertEqual(self._despesas(), 1000.0)

	def test_dinheiro_e_repasse_continuam_fora(self):
		antes = self._despesas()
		doc = _transacao("FILTRO-DINHEIRO", "2026-02-11", -700)
		doc.db_set("metodo", "Dinheiro")
		self.assertEqual(self._despesas(), antes)


class TestDesvioContraPrevistoAteHoje(FrappeTestCase):
	"""O desvio compara janelas iguais — realizado até hoje contra previsto até hoje."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		# Período de 12 meses com metade já decorrida, seja qual for a data do teste.
		inicio = getdate(add_months(getdate(), -5)).replace(day=1)
		cls.inicio = inicio
		cls.previsao = frappe.get_doc(
			{
				"doctype": "Previsao Orcamentaria",
				"titulo": "Desvio Teste",
				"exercicio": inicio.year,
				"status": "Aprovada",
				"data_inicio": inicio,
				"data_fim": add_days(add_months(inicio, 12), -1),
				"centro_de_custo": _centro_de_custo(),
				"itens": [
					{"tipo": "Receita", "descricao": "Contribuições", "valor_previsto": 12000},
					{"tipo": "Despesa", "descricao": "Aluguel", "valor_previsto": 12000},
				],
			}
		).insert()
		# Gasto acima do ritmo previsto; receita abaixo dele.
		_transacao("DESVIO-D1", add_days(inicio, 10), -7000)
		_transacao("DESVIO-C1", add_days(inicio, 11), 5000)

	def test_base_do_desvio_e_o_previsto_ate_o_mes_corrente(self):
		resultado = obter_comparativo(self.previsao.name)
		self.assertEqual(resultado["meses_decorridos"], 6)
		totais = resultado["totais"]
		self.assertEqual(totais["despesas_previstas"], 12000.0)
		self.assertEqual(totais["previsto_ate_hoje_despesas"], 6000.0)
		self.assertEqual(totais["desvio_despesas"], 1000.0)
		self.assertEqual(totais["desvio_receitas"], -1000.0)

	def test_desvio_e_execucao_apontam_para_o_mesmo_lado(self):
		# O bug anterior: desvio negativo ("abaixo do previsto") com execução acima de 100%.
		totais = obter_comparativo(self.previsao.name)["totais"]
		self.assertGreater(totais["execucao_despesas"], 100)
		self.assertGreater(totais["desvio_despesas"], 0)
		self.assertLess(totais["execucao_receitas"], 100)
		self.assertLess(totais["desvio_receitas"], 0)

	def test_quebra_por_categoria_usa_a_mesma_base(self):
		linhas = obter_comparativo(self.previsao.name)["por_categoria"]["despesas"]
		linha = next(l for l in linhas if l["realizado"])
		self.assertEqual(linha["previsto"], 12000.0)
		self.assertEqual(linha["previsto_ate_hoje"], 6000.0)
		self.assertEqual(linha["desvio"], 1000.0)

	def test_mes_de_corte_acompanha_os_meses_decorridos(self):
		resultado = obter_comparativo(self.previsao.name)
		self.assertEqual(resultado["mes_corte"], resultado["labels"][5])

	def test_previsao_futura_nao_acusa_desvio(self):
		futura = frappe.get_doc(
			{
				"doctype": "Previsao Orcamentaria",
				"titulo": "Desvio Teste Futuro",
				"exercicio": self.inicio.year + 2,
				"status": "Rascunho",
				"data_inicio": add_months(self.inicio, 24),
				"data_fim": add_days(add_months(self.inicio, 36), -1),
				"centro_de_custo": CENTRO_TESTE,
				"itens": [{"tipo": "Despesa", "descricao": "Aluguel", "valor_previsto": 12000}],
			}
		).insert()
		resultado = obter_comparativo(futura.name)
		self.assertEqual(resultado["meses_decorridos"], 0)
		self.assertIsNone(resultado["mes_corte"])
		self.assertEqual(resultado["totais"]["desvio_despesas"], 0.0)
		self.assertIsNone(resultado["totais"]["execucao_despesas"])


class TestEscritaDaPrevisao(FrappeTestCase):
	"""CRUD via API: renomear de verdade e respeitar o status Encerrada."""

	def _nova(self, titulo, status="Rascunho"):
		criar_previsao(
			titulo=titulo,
			exercicio=2026,
			data_inicio="2026-01-01",
			data_fim="2026-06-30",
			status=status,
			itens=[{"tipo": "Despesa", "descricao": "Aluguel", "valor_previsto": 600}],
		)
		return titulo

	def test_trocar_o_titulo_renomeia_o_documento(self):
		nome = self._nova("Escrita Renomear")
		resultado = atualizar_previsao(name=nome, titulo="Escrita Renomeada")
		self.assertEqual(resultado["name"], "Escrita Renomeada")
		self.assertFalse(frappe.db.exists("Previsao Orcamentaria", nome))
		doc = frappe.get_doc("Previsao Orcamentaria", "Escrita Renomeada")
		self.assertEqual(doc.titulo, "Escrita Renomeada")
		# Os itens acompanham o documento renomeado.
		self.assertEqual(len(doc.itens), 1)

	def test_titulo_vazio_e_rejeitado(self):
		nome = self._nova("Escrita Titulo Vazio")
		with self.assertRaises(frappe.ValidationError):
			atualizar_previsao(name=nome, titulo="   ")

	def test_atualizar_sem_titulo_nao_renomeia(self):
		nome = self._nova("Escrita Sem Titulo")
		resultado = atualizar_previsao(name=nome, observacoes="ajuste")
		self.assertEqual(resultado["name"], nome)

	def test_previsao_encerrada_recusa_edicao_e_exclusao(self):
		nome = self._nova("Escrita Encerrada", status="Encerrada")
		with self.assertRaises(frappe.ValidationError):
			atualizar_previsao(name=nome, observacoes="alterando um orçamento fechado")
		with self.assertRaises(frappe.ValidationError):
			excluir_previsao(nome)
		with self.assertRaises(frappe.ValidationError):
			salvar_item(previsao=nome, tipo="Despesa", descricao="Novo", valor_previsto=10)
		item = frappe.get_doc("Previsao Orcamentaria", nome).itens[0].name
		with self.assertRaises(frappe.ValidationError):
			excluir_item(previsao=nome, item_name=item)
		self.assertTrue(frappe.db.exists("Previsao Orcamentaria", nome))

	def test_reabrir_uma_previsao_encerrada_e_permitido(self):
		nome = self._nova("Escrita Reabrir", status="Encerrada")
		atualizar_previsao(name=nome, status="Rascunho", observacoes="reaberta para correção")
		doc = frappe.get_doc("Previsao Orcamentaria", nome)
		self.assertEqual(doc.status, "Rascunho")
		self.assertEqual(doc.observacoes, "reaberta para correção")
		# Reaberta, volta a aceitar itens.
		salvar_item(previsao=nome, tipo="Despesa", descricao="Novo", valor_previsto=10)
		self.assertEqual(len(frappe.get_doc("Previsao Orcamentaria", nome).itens), 2)


class TestPrevisaoPadraoDoPortal(FrappeTestCase):
	"""Qual previsão a página abre quando a URL não pede nenhuma."""

	@staticmethod
	def _linha(nome, status, inicio, fim):
		return {"name": nome, "status": status, "data_inicio": getdate(inicio), "data_fim": getdate(fim)}

	def setUp(self):
		hoje = getdate()
		self.vigente = self._linha("Vigente", "Aprovada", add_months(hoje, -3), add_months(hoje, 3))
		self.rascunho_futuro = self._linha(
			"Rascunho futuro", "Rascunho", add_months(hoje, 12), add_months(hoje, 24)
		)
		self.encerrada = self._linha("Encerrada", "Encerrada", add_months(hoje, -24), add_months(hoje, -12))

	def test_prefere_a_previsao_que_cobre_hoje(self):
		# A lista chega ordenada por exercício desc — o rascunho futuro vem primeiro.
		previsoes = [self.rascunho_futuro, self.vigente, self.encerrada]
		self.assertEqual(previsao_padrao(previsoes), "Vigente")

	def test_entre_vigentes_prefere_a_aprovada(self):
		hoje = getdate()
		rascunho_vigente = self._linha(
			"Rascunho vigente", "Rascunho", add_months(hoje, -1), add_months(hoje, 1)
		)
		self.assertEqual(previsao_padrao([rascunho_vigente, self.vigente]), "Vigente")

	def test_sem_previsao_vigente_cai_na_aprovada_mais_recente(self):
		hoje = getdate()
		aprovada_passada = self._linha(
			"Aprovada passada", "Aprovada", add_months(hoje, -24), add_months(hoje, -12)
		)
		previsoes = [self.rascunho_futuro, aprovada_passada]
		self.assertEqual(previsao_padrao(previsoes), "Aprovada passada")

	def test_sem_aprovada_cai_na_primeira_da_lista(self):
		previsoes = [self.rascunho_futuro, self.encerrada]
		self.assertEqual(previsao_padrao(previsoes), "Rascunho futuro")

	def test_lista_vazia(self):
		self.assertIsNone(previsao_padrao([]))
