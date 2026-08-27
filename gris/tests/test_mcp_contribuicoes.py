"""Testes das ferramentas MCP de contribuições mensais e contas fixas."""

from unittest import TestCase
from unittest.mock import patch

from gris.api.mcp import contas_fixas, contribuicoes
from gris.api.mcp.registry import ErroDeFerramenta


class TestListarContribuicoes(TestCase):
	def test_mes_referencia_vira_primeiro_dia(self):
		with (
			patch.object(contribuicoes.frappe, "get_all", return_value=[]) as get_all,
			patch.object(contribuicoes.frappe.db, "count", return_value=0),
		):
			contribuicoes.listar_contribuicoes(mes_referencia="2026-03", status="Atrasado")

		filtros = get_all.call_args.kwargs["filters"]
		self.assertEqual(filtros["mes_de_referencia"], "2026-03-01")
		self.assertEqual(filtros["status"], "Atrasado")

	def test_intervalo_de_meses_usa_between(self):
		with (
			patch.object(contribuicoes.frappe, "get_all", return_value=[]) as get_all,
			patch.object(contribuicoes.frappe.db, "count", return_value=0),
		):
			contribuicoes.listar_contribuicoes(mes_inicio="2026-01", mes_fim="2026-03")

		self.assertEqual(
			get_all.call_args.kwargs["filters"]["mes_de_referencia"],
			["between", ["2026-01-01", "2026-03-01"]],
		)

	def test_mes_invalido(self):
		with self.assertRaises(ErroDeFerramenta) as ctx:
			contribuicoes.listar_contribuicoes(mes_referencia="marco/2026")
		self.assertEqual(ctx.exception.codigo, "ARGUMENTO_INVALIDO")

	def test_anexa_nome_do_associado_em_uma_consulta(self):
		pagamentos = [
			{"name": "P1", "associado": "111", "status": "Atrasado"},
			{"name": "P2", "associado": "222", "status": "Pago"},
		]
		associados = [
			{"name": "111", "nome_completo": "Ana"},
			{"name": "222", "nome_completo": "Bruno"},
		]
		with (
			patch.object(contribuicoes.frappe, "get_all", side_effect=[pagamentos, associados]) as get_all,
			patch.object(contribuicoes.frappe.db, "count", return_value=2),
		):
			resultado = contribuicoes.listar_contribuicoes()

		self.assertEqual(get_all.call_count, 2)
		self.assertEqual(resultado["contribuicoes"][0]["nome_associado"], "Ana")
		self.assertEqual(resultado["contribuicoes"][1]["nome_associado"], "Bruno")


class TestResumoInadimplencia(TestCase):
	def test_consolida_por_status_e_percentual(self):
		agregados = [
			{"status": "Pago", "quantidade": 30, "total": 1800.0},
			{"status": "Atrasado", "quantidade": 10, "total": 600.0},
		]
		devedores = [{"name": "P1", "associado": "111", "mes_de_referencia": "2026-03", "valor": 60.0}]
		with patch.object(
			contribuicoes.frappe,
			"get_all",
			side_effect=[agregados, devedores, [{"name": "111", "nome_completo": "Ana"}]],
		):
			resultado = contribuicoes.resumo_inadimplencia(mes_referencia="2026-03")

		self.assertEqual(resultado["periodo"], {"inicio": "2026-03-01", "fim": "2026-03-01"})
		self.assertEqual(resultado["total_registros"], 40)
		self.assertEqual(resultado["inadimplencia"]["percentual"], 25.0)
		self.assertEqual(resultado["a_receber"]["valor"], 600.0)
		self.assertEqual(resultado["devedores"][0]["nome_associado"], "Ana")

	def test_sem_registros_nao_divide_por_zero(self):
		with patch.object(contribuicoes.frappe, "get_all", side_effect=[[], [], []]):
			resultado = contribuicoes.resumo_inadimplencia(mes_referencia="2026-03")
		self.assertEqual(resultado["inadimplencia"]["percentual"], 0.0)


class TestMarcarContribuicoesPagas(TestCase):
	def test_simulacao_nao_chama_o_servico(self):
		from gris.api.financeiro import monthly_payments

		valores = {"status": "Em Aberto", "associado": "111", "mes_de_referencia": "2026-03"}
		with (
			patch.object(contribuicoes.frappe.db, "get_value", return_value=valores),
			patch.object(monthly_payments, "mark_payment_as_paid") as servico,
		):
			resultado = contribuicoes.marcar_contribuicoes_pagas(["P1"], simular=True)

		servico.assert_not_called()
		self.assertTrue(resultado["simulacao"])
		self.assertEqual(resultado["seriam_marcadas"], ["P1"])
		self.assertEqual(resultado["marcadas_como_pagas"], 0)

	def test_separa_ja_pagos_e_inexistentes(self):
		from gris.api.financeiro import monthly_payments

		def get_value(_doctype, name, _campos, as_dict=True):
			if name == "P1":
				return {"status": "Em Aberto"}
			if name == "P2":
				return {"status": "Pago"}
			return None

		with (
			patch.object(contribuicoes.frappe.db, "get_value", side_effect=get_value),
			patch.object(monthly_payments, "mark_payment_as_paid") as servico,
		):
			resultado = contribuicoes.marcar_contribuicoes_pagas(["P1", "P2", "P3"])

		servico.assert_called_once_with("P1")
		self.assertEqual(resultado["marcadas_como_pagas"], 1)
		self.assertEqual(resultado["ja_estavam_pagas"], ["P2"])
		self.assertEqual(resultado["falhas"][0]["id"], "P3")

	def test_exige_ids(self):
		with self.assertRaises(ErroDeFerramenta):
			contribuicoes.marcar_contribuicoes_pagas(["  "])


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
		self.assertEqual(
			sorted(resultado["alteracoes"]), ["email_cobranca", "status_cobranca", "valor_contribuicao"]
		)


class TestGerarContribuicoesDoMes(TestCase):
	def test_simulacao_conta_pendentes(self):
		from gris.api.financeiro import monthly_payments

		with (
			patch.object(contribuicoes.frappe, "get_all", side_effect=[["111", "222", "333"], ["111"]]),
			patch.object(monthly_payments, "generate_monthly_payments") as servico,
		):
			resultado = contribuicoes.gerar_contribuicoes_do_mes(simular=True)

		servico.assert_not_called()
		self.assertEqual(resultado["beneficiarios_ativos"], 3)
		self.assertEqual(resultado["ja_possuem_registro"], 1)
		self.assertEqual(resultado["seriam_criados"], 2)

	def test_execucao_delega_ao_servico(self):
		from gris.api.financeiro import monthly_payments

		with (
			patch.object(contribuicoes.frappe, "get_all", side_effect=[["111", "222"], []]),
			patch.object(monthly_payments, "generate_monthly_payments", return_value=2) as servico,
		):
			resultado = contribuicoes.gerar_contribuicoes_do_mes()

		servico.assert_called_once_with()
		self.assertEqual(resultado["criados"], 2)


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


class TestRegistroDeFerramentas(TestCase):
	def test_ferramentas_da_onda_estao_no_catalogo(self):
		from gris.api.mcp import registry

		nomes = set(registry.carregar_ferramentas())
		esperadas = {
			"listar_contribuicoes",
			"resumo_inadimplencia",
			"marcar_contribuicoes_pagas",
			"atualizar_cobranca_associado",
			"gerar_contribuicoes_do_mes",
			"listar_contas_fixas",
			"listar_pagamentos_contas_fixas",
			"marcar_contas_fixas_pagas",
		}
		self.assertTrue(esperadas.issubset(nomes), esperadas - nomes)
