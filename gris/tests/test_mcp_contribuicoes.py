"""Testes das ferramentas MCP de contribuição mensal e contas fixas.

A apuração da contribuição vem do Pagamento Contribuicao Mensal
(gris.api.financeiro.pagamentos_contribuicao); aqui checamos o recorte, os
filtros e as guardas das ferramentas.
"""

from unittest import TestCase
from unittest.mock import patch

from gris.api.mcp import contas_fixas, contribuicoes
from gris.api.mcp.registry import ErroDeFerramenta

APURACAO = {
	"periodo": {"inicio": "2026-01-01", "fim": "2026-03-01"},
	"quantidade_meses": 3,
	"dia_vencimento": 10,
	"meses": [{"ym": "2026-01", "rotulo": "01/2026"}],
	"associados": [
		{
			"id": "111",
			"nome": "Ana",
			"categoria": "Beneficiário",
			"secao": "Alcateia",
			"situacao": "Atrasado",
			"acao_cadastro": None,
			"total_recebido": 60.0,
			"total_esperado": 180.0,
			"linhas": [{"ym": "2026-01", "status": "Atrasado"}],
		},
		{
			"id": "222",
			"nome": "Bruno",
			"categoria": "Escotista",
			"secao": "Tropa",
			"situacao": "Pago",
			"acao_cadastro": "Cancelar",
			"total_recebido": 180.0,
			"total_esperado": 180.0,
			"linhas": [{"ym": "2026-01", "status": "Pago"}],
		},
		{
			"id": "333",
			"nome": "Carla",
			"categoria": "Beneficiário",
			"secao": "Alcateia",
			"situacao": "Em Aberto",
			"acao_cadastro": "Cadastrar",
			"total_recebido": 30.0,
			"total_esperado": 180.0,
			"linhas": [{"ym": "2026-01", "status": "Em Aberto"}],
		},
	],
	"nao_vinculadas": [
		{"name": "T1", "data": "2026-02-05", "valor": 60.0, "descricao": "PIX RECEBIDO"},
		{"name": "T2", "data": "2026-02-07", "valor": 60.0, "descricao": "PIX RECEBIDO"},
	],
	"series": {
		"labels": ["01/2026", "02/2026"],
		"recebido": [120.0, 240.0],
		"nao_vinculado": [0.0, 120.0],
		"esperado": [180.0, 180.0],
		"adimplencia": [66.67, 100.0],
	},
	"totais": {
		"contribuintes": 3,
		"recebido_vinculado": 360.0,
		"recebido_nao_vinculado": 120.0,
		"adimplencia": 80.0,
		"com_pendencia": 2,
		"a_cadastrar": 1,
		"a_cancelar": 1,
	},
}


def _com_apuracao():
	return patch.object(
		contribuicoes.servico, "get_apuracao", return_value={"success": True, "dados": APURACAO}
	)


class TestResumoContribuicoes(TestCase):
	def test_tabula_series_por_mes_e_repassa_totais(self):
		with _com_apuracao():
			resultado = contribuicoes.resumo_contribuicoes(meses=3)

		self.assertEqual(resultado["totais"]["adimplencia"], 80.0)
		self.assertEqual(
			resultado["por_mes"][1],
			{
				"mes": "02/2026",
				"recebido": 240.0,
				"nao_vinculado": 120.0,
				"esperado": 180.0,
				"adimplencia": 100.0,
			},
		)

	def test_repassa_a_janela_pedida(self):
		with _com_apuracao() as servico:
			contribuicoes.resumo_contribuicoes(meses=24)
		servico.assert_called_once_with(24)


class TestApuracaoPorAssociado(TestCase):
	def test_omite_a_grade_mensal_por_padrao(self):
		with _com_apuracao():
			resultado = contribuicoes.apuracao_contribuicoes()

		self.assertTrue(all("linhas" not in a for a in resultado["associados"]))
		self.assertIsNone(resultado["meses"])

	def test_incluir_meses_traz_a_grade(self):
		with _com_apuracao():
			resultado = contribuicoes.apuracao_contribuicoes(incluir_meses=True)

		self.assertEqual(resultado["associados"][0]["linhas"][0]["ym"], "2026-01")
		self.assertEqual(resultado["meses"][0]["rotulo"], "01/2026")

	def test_filtra_por_situacao(self):
		with _com_apuracao():
			resultado = contribuicoes.apuracao_contribuicoes(situacao="Atrasado")

		self.assertEqual([a["id"] for a in resultado["associados"]], ["111"])
		self.assertEqual(resultado["paginacao"]["total_com_filtros"], 1)
		self.assertEqual(resultado["paginacao"]["total_contribuintes"], 3)

	def test_com_pendencia_junta_atrasado_e_parcial(self):
		with _com_apuracao():
			resultado = contribuicoes.apuracao_contribuicoes(com_pendencia=True)

		self.assertEqual([a["id"] for a in resultado["associados"]], ["111", "333"])

	def test_filtra_por_acao_de_cadastro(self):
		with _com_apuracao():
			resultado = contribuicoes.apuracao_contribuicoes(acao_cadastro="Cadastrar")

		self.assertEqual([a["id"] for a in resultado["associados"]], ["333"])

	def test_filtra_por_secao_categoria_e_busca(self):
		with _com_apuracao():
			por_secao = contribuicoes.apuracao_contribuicoes(secao="Tropa")
			por_categoria = contribuicoes.apuracao_contribuicoes(categoria="Beneficiário")
			por_busca = contribuicoes.apuracao_contribuicoes(busca="car")

		self.assertEqual([a["id"] for a in por_secao["associados"]], ["222"])
		self.assertEqual([a["id"] for a in por_categoria["associados"]], ["111", "333"])
		self.assertEqual([a["id"] for a in por_busca["associados"]], ["333"])

	def test_pagina_em_memoria(self):
		with _com_apuracao():
			resultado = contribuicoes.apuracao_contribuicoes(limite=1, inicio=1)

		self.assertEqual([a["id"] for a in resultado["associados"]], ["222"])
		self.assertEqual(resultado["paginacao"]["retornados"], 1)

	def test_nao_muta_a_apuracao_original(self):
		with _com_apuracao():
			contribuicoes.apuracao_contribuicoes()

		self.assertIn("linhas", APURACAO["associados"][0])


class TestExtratoDoAssociado(TestCase):
	def test_associado_inexistente(self):
		with patch.object(contribuicoes.frappe.db, "exists", return_value=False):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				contribuicoes.extrato_contribuicoes_associado("999")
		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")

	def test_soma_o_recebido(self):
		transacoes = [{"name": "T1", "valor": 60.0}, {"name": "T2", "valor": 30.0}]
		with (
			patch.object(contribuicoes.frappe.db, "exists", return_value=True),
			patch.object(
				contribuicoes.servico,
				"get_extrato_do_associado",
				return_value={"success": True, "transacoes": transacoes},
			) as servico,
		):
			resultado = contribuicoes.extrato_contribuicoes_associado("111", meses=6)

		servico.assert_called_once_with("111", 6)
		self.assertEqual(resultado["total_recebido"], 90.0)
		self.assertEqual(resultado["quantidade"], 2)


class TestNaoVinculadas(TestCase):
	def test_lista_com_total_e_valor(self):
		with _com_apuracao():
			resultado = contribuicoes.listar_contribuicoes_nao_vinculadas()

		self.assertEqual(resultado["paginacao"]["total"], 2)
		self.assertEqual(resultado["valor_total_nao_vinculado"], 120.0)

	def test_pagina(self):
		with _com_apuracao():
			resultado = contribuicoes.listar_contribuicoes_nao_vinculadas(limite=1, inicio=1)

		self.assertEqual([t["name"] for t in resultado["transacoes"]], ["T2"])


class TestAtualizarCobranca(TestCase):
	def test_exige_algum_campo(self):
		with self.assertRaises(ErroDeFerramenta):
			contribuicoes.atualizar_cobranca_associado("111")

	def test_recusa_valor_negativo(self):
		with self.assertRaises(ErroDeFerramenta) as ctx:
			contribuicoes.atualizar_cobranca_associado("111", valor_contribuicao=-10)
		self.assertIn("negativo", ctx.exception.mensagem)

	def test_associado_inexistente(self):
		with patch.object(contribuicoes.frappe.db, "get_value", return_value=None):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				contribuicoes.atualizar_cobranca_associado("111", status_cobranca="Ativo")
		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")

	def test_sem_mudanca_nao_grava(self):
		atuais = {"valor_contribuicao": 60.0, "status_cobranca": "Ativo"}
		with patch.object(contribuicoes.frappe.db, "get_value", return_value=atuais):
			resultado = contribuicoes.atualizar_cobranca_associado("111", status_cobranca="Ativo")
		self.assertFalse(resultado["atualizado"])

	def test_simulacao_mostra_antes_e_depois(self):
		atuais = {"valor_contribuicao": 60.0, "status_cobranca": "Ativo"}
		with patch.object(contribuicoes.frappe.db, "get_value", return_value=atuais):
			resultado = contribuicoes.atualizar_cobranca_associado("111", valor_contribuicao=75, simular=True)
		self.assertTrue(resultado["simulacao"])
		self.assertEqual(resultado["alteracoes"]["valor_contribuicao"], {"de": 60.0, "para": 75})

	def test_delega_para_os_servicos_corretos(self):
		from gris.api.financeiro import monthly_payments

		atuais = {
			"valor_contribuicao": 60.0,
			"status_cobranca": "Ativo",
			"email_cobranca": None,
			"telefone_cobranca": None,
		}
		with (
			patch.object(contribuicoes.frappe.db, "get_value", return_value=atuais),
			patch.object(monthly_payments, "update_contribution_value") as valor,
			patch.object(monthly_payments, "deactivate_billing_status") as desativar,
			patch.object(monthly_payments, "activate_billing_status") as ativar,
			patch.object(monthly_payments, "update_billing_contacts") as contatos,
		):
			resultado = contribuicoes.atualizar_cobranca_associado(
				"111",
				valor_contribuicao=75,
				status_cobranca="Inativo",
				email_cobranca="ana@example.com",
			)

		valor.assert_called_once_with("111", 75.0)
		desativar.assert_called_once_with("111")
		ativar.assert_not_called()
		contatos.assert_called_once_with("111", email="ana@example.com", phone=None)
		self.assertTrue(resultado["atualizado"])


class TestContasFixas(TestCase):
	def test_lista_filtra_por_tipo_e_soma_ativas(self):
		contas = [
			{"name": "Aluguel", "valor": 2000.0, "ativa": 1},
			{"name": "Internet", "valor": 150.0, "ativa": 1},
			{"name": "Antiga", "valor": 90.0, "ativa": 0},
		]
		with patch.object(contas_fixas.frappe, "get_all", return_value=contas) as get_all:
			resultado = contas_fixas.listar_contas_fixas(tipo="temporarias")

		self.assertEqual(get_all.call_args.kwargs["filters"], {"ativa": 1, "despesa_temporaria": 1})
		self.assertEqual(resultado["custo_mensal_ativas"], 2150.0)

	def test_pagamentos_somam_em_aberto_da_pagina(self):
		pagamentos = [
			{"name": "PG1", "status": "Em Aberto", "valor": 200.0},
			{"name": "PG2", "status": "Pago", "valor": 150.0},
		]
		with (
			patch.object(contas_fixas.frappe, "get_all", return_value=pagamentos),
			patch.object(contas_fixas.frappe.db, "count", return_value=2),
		):
			resultado = contas_fixas.listar_pagamentos_contas_fixas(mes="2026-03")

		self.assertEqual(resultado["valor_em_aberto_na_pagina"], 200.0)

	def test_mes_invalido(self):
		with self.assertRaises(ErroDeFerramenta):
			contas_fixas.listar_pagamentos_contas_fixas(mes="03/2026")

	def test_marcar_pagas_respeita_simulacao(self):
		from gris.api.financeiro import conta_fixa as servico

		with (
			patch.object(contas_fixas.frappe.db, "get_value", return_value={"status": "Em Aberto"}),
			patch.object(servico, "marcar_pagamento_pago") as marcar,
		):
			simulado = contas_fixas.marcar_contas_fixas_pagas(["PG1"], simular=True)
			real = contas_fixas.marcar_contas_fixas_pagas(["PG1"])

		marcar.assert_called_once_with("PG1")
		self.assertTrue(simulado["simulacao"])
		self.assertEqual(real["marcadas_como_pagas"], 1)


class TestCompetenciasTransacao(TestCase):
	def test_transacao_inexistente(self):
		with patch.object(contribuicoes.frappe.db, "exists", return_value=False):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				contribuicoes.competencias_transacao("T-999")
		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")

	def test_le_a_transacao_pelo_servico(self):
		esperado = {"transacao": "T1", "competencias": [{"ym": "2026-01", "valor": 70.0}]}
		with (
			patch.object(contribuicoes.frappe.db, "exists", return_value=True),
			patch.object(
				contribuicoes.transacoes_servico, "get_competencias_transacao", return_value=esperado
			) as servico,
		):
			resultado = contribuicoes.competencias_transacao("T1")
		servico.assert_called_once_with("T1")
		self.assertEqual(resultado, esperado)


class TestDefinirCompetenciasTransacao(TestCase):
	def test_transacao_inexistente(self):
		with patch.object(contribuicoes.frappe.db, "exists", return_value=False):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				contribuicoes.definir_competencias_transacao("T-999", [])
		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")

	def test_recusa_item_que_nao_e_objeto(self):
		with patch.object(contribuicoes.frappe.db, "exists", return_value=True):
			with self.assertRaises(ErroDeFerramenta):
				contribuicoes.definir_competencias_transacao("T1", ["2026-01"])

	def test_simulacao_nao_grava(self):
		antes = {"transacao": "T1", "competencias": []}
		itens = [{"mes": "2026-01", "valor": 70.0, "em_atraso": True}]
		with (
			patch.object(contribuicoes.frappe.db, "exists", return_value=True),
			patch.object(contribuicoes.transacoes_servico, "get_competencias_transacao", return_value=antes),
			patch.object(contribuicoes.frappe, "get_doc") as get_doc,
			patch.object(contribuicoes.transacoes_servico, "definir_competencias_transacao") as definir,
		):
			resultado = contribuicoes.definir_competencias_transacao("T1", itens, simular=True)

		get_doc.return_value.check_permission.assert_called_once_with("write")
		definir.assert_not_called()
		self.assertTrue(resultado["simulacao"])
		self.assertEqual(resultado["depois"], itens)

	def test_delega_a_gravacao_para_o_servico(self):
		antes = {"transacao": "T1", "competencias": []}
		depois = {"transacao": "T1", "competencias": [{"ym": "2026-01", "valor": 70.0}]}
		itens = [{"mes": "2026-01", "valor": 70.0, "em_atraso": True}]
		with (
			patch.object(contribuicoes.frappe.db, "exists", return_value=True),
			patch.object(contribuicoes.transacoes_servico, "get_competencias_transacao", return_value=antes),
			patch.object(
				contribuicoes.transacoes_servico, "definir_competencias_transacao", return_value=depois
			) as definir,
		):
			resultado = contribuicoes.definir_competencias_transacao("T1", itens)

		definir.assert_called_once_with("T1", itens)
		self.assertEqual(resultado["depois"], depois["competencias"])


class TestPagamentosContribuicaoMensal(TestCase):
	def test_lista_com_filtros_e_paginacao(self):
		registros = [{"name": "PG1", "associado": "111", "status": "Pago"}]
		with (
			patch.object(contribuicoes.frappe, "get_all", return_value=registros) as get_all,
			patch.object(contribuicoes.frappe.db, "count", return_value=1),
		):
			resultado = contribuicoes.listar_pagamentos_contribuicao_mensal(associado="111", status="Pago")

		self.assertEqual(get_all.call_args.kwargs["filters"], {"associado": "111", "status": "Pago"})
		self.assertEqual(resultado["paginacao"]["total"], 1)

	def test_atualizar_exige_registro_existente(self):
		with patch.object(contribuicoes.frappe.db, "exists", return_value=False):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				contribuicoes.atualizar_pagamento_contribuicao_mensal("PG1", status="Pago")
		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")

	def test_atualizar_exige_algum_campo(self):
		with patch.object(contribuicoes.frappe.db, "exists", return_value=True):
			with self.assertRaises(ErroDeFerramenta):
				contribuicoes.atualizar_pagamento_contribuicao_mensal("PG1")

	def test_sem_mudanca_nao_grava(self):
		atuais = {"status": "Pago", "valor": 60.0, "atrasou": 0, "transacao_extrato": None}
		with (
			patch.object(contribuicoes.frappe.db, "exists", return_value=True),
			patch.object(contribuicoes.frappe.db, "get_value", return_value=atuais),
		):
			resultado = contribuicoes.atualizar_pagamento_contribuicao_mensal("PG1", status="Pago")
		self.assertFalse(resultado["atualizado"])

	def test_simulacao_mostra_antes_e_depois(self):
		atuais = {"status": "Em Aberto", "valor": 60.0, "atrasou": 0, "transacao_extrato": None}
		with (
			patch.object(contribuicoes.frappe.db, "exists", return_value=True),
			patch.object(contribuicoes.frappe.db, "get_value", return_value=atuais),
		):
			resultado = contribuicoes.atualizar_pagamento_contribuicao_mensal(
				"PG1", status="Pago", simular=True
			)
		self.assertTrue(resultado["simulacao"])
		self.assertEqual(resultado["alteracoes"]["status"], {"de": "Em Aberto", "para": "Pago"})

	def test_grava_via_doc(self):
		atuais = {"status": "Em Aberto", "valor": 60.0, "atrasou": 0, "transacao_extrato": None}
		with (
			patch.object(contribuicoes.frappe.db, "exists", return_value=True),
			patch.object(contribuicoes.frappe.db, "get_value", return_value=atuais),
			patch.object(contribuicoes.frappe, "get_doc") as get_doc,
		):
			resultado = contribuicoes.atualizar_pagamento_contribuicao_mensal("PG1", status="Pago")

		get_doc.return_value.check_permission.assert_called_once_with("write")
		get_doc.return_value.save.assert_called_once()
		self.assertTrue(resultado["atualizado"])


class TestRegistroDeFerramentas(TestCase):
	def test_catalogo_reflete_a_apuracao_por_transacoes(self):
		from gris.api.mcp import registry

		nomes = set(registry.carregar_ferramentas())
		esperadas = {
			"resumo_contribuicoes",
			"apuracao_contribuicoes",
			"extrato_contribuicoes_associado",
			"listar_contribuicoes_nao_vinculadas",
			"atualizar_cobranca_associado",
			"competencias_transacao",
			"definir_competencias_transacao",
			"listar_pagamentos_contribuicao_mensal",
			"atualizar_pagamento_contribuicao_mensal",
			"definir_pagamento_mensal",
		}
		self.assertTrue(esperadas.issubset(nomes), esperadas - nomes)

		# Ferramentas antigas que escreviam direto em Pagamento Contribuicao Mensal sem
		# vínculo com a transação saíram do catálogo — a apuração continua vindo das
		# transações; o DocType volta só como registro de cobrança vinculado a elas.
		aposentadas = {"listar_contribuicoes", "resumo_inadimplencia", "marcar_contribuicoes_pagas"}
		self.assertFalse(aposentadas & nomes)
