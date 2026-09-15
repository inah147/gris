"""Testes da cobrança automática da contribuição mensal por link InfinitePay.

O job roda com a data do teste (`hoje`) e restrito ao associado criado aqui, sem
sair para a rede: a InfinitePay e o WhatsApp são substituídos por mocks e o
commit por associado vira no-op, para o rollback do teste continuar valendo.
"""

import datetime
import hashlib
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.financeiro import cobranca_contribuicao_automatica as automatica
from gris.api.financeiro.cobranca_contribuicao import FINALIDADE_CONTRIBUICAO, ORIGEM_AUTOMATICA
from gris.financeiro.doctype.cobranca_infinitepay import cobranca_infinitepay as cobranca_doctype
from gris.utils.whatsapp_errors import WhatsAppRequestError

VALOR = 60.0
VALOR_ATRASO = 70.0
CPF = "99000000021"


def _apagar(doctype: str, filtros: dict) -> None:
	for nome in frappe.get_all(doctype, filters=filtros, pluck="name"):
		frappe.delete_doc(doctype, nome, force=True, ignore_permissions=True)


class TestCobrancaAutomatica(FrappeTestCase):
	def setUp(self):
		self.associado = self._criar_associado()
		_apagar("Cobranca Infinitepay", {"associado": self.associado})
		_apagar("Transacao Extrato Geral", {"beneficiario": self.associado})
		frappe.db.set_single_value("Configuracao infinitepay", "handle", "grupo-teste")
		frappe.db.set_single_value(
			"Configuracoes Contribuicao Mensal",
			{
				"valor_base": VALOR,
				"valor_atraso": VALOR_ATRASO,
				"dia_vencimento": 10,
				"cobranca_automatica_ativa": 1,
				"cobranca_automatica_desde": "2026-08-01",
				"dia_emissao_cobranca": 1,
				"dias_lembrete_apos_vencimento": 3,
				"max_lembretes": 2,
			},
		)
		self._gerar_pagamentos()
		self._sem_commit = mock.patch.object(automatica, "_commit")
		self._sem_commit.start()
		self.addCleanup(self._sem_commit.stop)

	def _gerar_pagamentos(self) -> None:
		"""A apuração mês a mês que o job lê — é dela que saem os meses a cobrar.

		No site, quem grava esses registros é a geração mensal
		(`monthly_payments.generate_monthly_payments`) e a virada de status depois
		do vencimento; o job de cobrança não inventa mês nenhum fora deles.
		"""
		_apagar("Pagamento Contribuicao Mensal", {"associado": self.associado})
		for ym, status in (("2026-07", "Atrasado"), ("2026-08", "Em Aberto"), ("2026-09", "Em Aberto")):
			frappe.get_doc(
				{
					"doctype": "Pagamento Contribuicao Mensal",
					"associado": self.associado,
					"mes_de_referencia": f"{ym}-01",
					"status": status,
					"valor": VALOR,
				}
			).insert(ignore_permissions=True)

	def _criar_associado(self) -> str:
		nome = hashlib.md5(CPF.encode("utf-8")).hexdigest()
		if not frappe.db.exists("Associado", nome):
			frappe.get_doc(
				{
					"doctype": "Associado",
					"cpf": CPF,
					"nome_completo": "Beneficiário da Cobrança Automática",
					"data_de_nascimento": "2015-01-01",
					"categoria": "Beneficiário",
					"status_no_grupo": "Ativo",
					"status_cobranca": "Ativo",
					"valor_contribuicao": VALOR,
				}
			).insert(ignore_permissions=True)
		# Julho vencido e agosto a vencer, em qualquer execução deste teste.
		frappe.db.set_value(
			"Associado",
			nome,
			{
				"inicio_do_pagamento": "2026-07-01",
				"telefone_cobranca": "11999990021",
				"status_cobranca": "Ativo",
				"status_no_grupo": "Ativo",
			},
		)
		return nome

	def _rodar(self, hoje: str, whatsapp_falha: bool = False) -> tuple[dict, mock.Mock]:
		resposta = mock.Mock()
		resposta.json.return_value = {"checkout_url": "https://pag.exemplo/automatica"}
		resposta.raise_for_status.return_value = None
		efeito = WhatsAppRequestError("Evolution API fora do ar") if whatsapp_falha else None
		with (
			mock.patch.object(cobranca_doctype.requests, "post", return_value=resposta),
			mock.patch("gris.utils.whatsapp.enviar_texto", side_effect=efeito) as enviar,
			mock.patch.object(frappe, "log_error"),
		):
			resultado = automatica.executar_cobrancas_automaticas(hoje, associados=[self.associado])
		return resultado, enviar

	def _cobrancas(self) -> list:
		return frappe.get_all(
			"Cobranca Infinitepay",
			filters={"associado": self.associado, "finalidade": FINALIDADE_CONTRIBUICAO},
			fields=[
				"name",
				"status",
				"origem",
				"competencias",
				"mes_emissao",
				"ultimo_envio_whatsapp",
				"lembretes_enviados",
			],
		)

	def test_nao_roda_antes_do_mes_de_inicio(self):
		resultado, enviar = self._rodar("2026-07-20")
		self.assertFalse(resultado["executado"])
		self.assertEqual(self._cobrancas(), [])
		enviar.assert_not_called()

	def test_nao_roda_desativada(self):
		frappe.db.set_single_value("Configuracoes Contribuicao Mensal", "cobranca_automatica_ativa", 0)
		resultado, _ = self._rodar("2026-08-05")
		self.assertFalse(resultado["executado"])

	def test_nao_emite_antes_do_dia_de_emissao(self):
		frappe.db.set_single_value("Configuracoes Contribuicao Mensal", "dia_emissao_cobranca", 6)
		resultado, _ = self._rodar("2026-08-05")
		self.assertEqual(resultado["emissao"]["emitidas"], 0)
		self.assertEqual(self._cobrancas(), [])

	def test_emite_uma_cobranca_por_mes_com_todos_os_meses_em_aberto(self):
		resultado, enviar = self._rodar("2026-08-05")

		self.assertEqual(resultado["emissao"]["emitidas"], 1)
		self.assertEqual(resultado["emissao"]["enviadas"], 1)
		enviar.assert_called_once()
		self.assertIn("https://pag.exemplo/automatica", enviar.call_args.args[1])

		[cobranca] = self._cobrancas()
		self.assertEqual(cobranca.origem, ORIGEM_AUTOMATICA)
		self.assertEqual(cobranca.competencias, "2026-07,2026-08")
		self.assertEqual(cobranca.mes_emissao, datetime.date(2026, 8, 1))
		self.assertTrue(cobranca.ultimo_envio_whatsapp)
		# Cada mês sai pelo valor gravado nele: o acréscimo de atraso é ajuste do
		# gestor no mês a mês, não um recálculo da cobrança.
		precos = frappe.get_all(
			"Item Cobranca Infinitepay", filters={"parent": cobranca.name}, pluck="preco", order_by="idx"
		)
		self.assertEqual(precos, [VALOR, VALOR])

		# Rodar de novo no mesmo mês não emite nem manda de novo.
		resultado, enviar = self._rodar("2026-08-06")
		self.assertEqual(resultado["emissao"]["emitidas"], 0)
		enviar.assert_not_called()
		self.assertEqual(len(self._cobrancas()), 1)

	def test_mes_seguinte_substitui_a_cobranca_nao_paga(self):
		self._rodar("2026-08-05")
		with mock.patch(
			"gris.api.financeiro.cobranca_contribuicao._proximo_order_nsu",
			return_value=f"CM-{self.associado}-setembro",
		):
			resultado, _ = self._rodar("2026-09-02")

		self.assertEqual(resultado["emissao"]["emitidas"], 1)
		por_mes = {c.mes_emissao: c for c in self._cobrancas()}
		self.assertEqual(por_mes[datetime.date(2026, 8, 1)].status, "Substituída")
		self.assertEqual(por_mes[datetime.date(2026, 9, 1)].status, "Pendente")
		self.assertEqual(por_mes[datetime.date(2026, 9, 1)].competencias, "2026-07,2026-08,2026-09")

	def test_whatsapp_que_falhou_e_tentado_de_novo(self):
		resultado, _ = self._rodar("2026-08-05", whatsapp_falha=True)
		self.assertEqual(resultado["emissao"]["emitidas"], 1)
		self.assertEqual(resultado["emissao"]["nao_enviadas"], 1)
		[cobranca] = self._cobrancas()
		self.assertFalse(cobranca.ultimo_envio_whatsapp)

		resultado, enviar = self._rodar("2026-08-06")
		self.assertEqual(resultado["emissao"]["reenvios"], 1)
		self.assertEqual(resultado["emissao"]["enviadas"], 1)
		enviar.assert_called_once()
		[cobranca] = self._cobrancas()
		self.assertTrue(cobranca.ultimo_envio_whatsapp)

	def test_lembretes_depois_do_vencimento_ate_o_maximo(self):
		self._rodar("2026-08-05")

		# Vencimento em 10/08 (segunda-feira); lembrete a cada 3 dias, no máximo 2.
		for dia, esperado in (("2026-08-12", 0), ("2026-08-13", 1), ("2026-08-15", 0), ("2026-08-16", 1)):
			resultado, _ = self._rodar(dia)
			self.assertEqual(resultado["lembretes"]["enviados"], esperado, dia)

		resultado, enviar = self._rodar("2026-08-25")
		self.assertEqual(resultado["lembretes"]["enviados"], 0)
		enviar.assert_not_called()
		self.assertEqual(self._cobrancas()[0].lembretes_enviados, 2)

	def test_resumo_do_mes_poe_quem_ficou_sem_mensagem_primeiro(self):
		self._rodar("2026-08-05", whatsapp_falha=True)

		resumo = automatica.resumo_cobrancas_do_mes(datetime.date(2026, 8, 20))

		self.assertEqual(resumo["mes"], "08/2026")
		self.assertIsNone(resumo["automatica"]["motivo_parada"])
		minhas = [c for c in resumo["cobrancas"] if c["associado"] == self.associado]
		self.assertEqual(len(minhas), 1)
		self.assertTrue(minhas[0]["sem_envio"])
		self.assertEqual(minhas[0]["competencias"], "07/2026, 08/2026")
		self.assertEqual(minhas[0]["valor"], 2 * VALOR)
		self.assertTrue(resumo["cobrancas"][0]["sem_envio"])
		self.assertGreaterEqual(resumo["totais"]["sem_envio"], 1)

	def test_lembrete_nao_sai_se_o_mes_foi_quitado_por_outro_meio(self):
		self._rodar("2026-08-05")
		frappe.get_doc(
			{
				"doctype": "Transacao Extrato Geral",
				"id": f"teste-pix-direto-{self.associado}",
				"descricao": "PIX direto",
				"debito_credito": "Crédito",
				"valor": VALOR,
				"data_transacao": "2026-08-08",
				"mes_competencia": "2026-08-01",
				"categoria": "Contribuição Mensal",
				"beneficiario": self.associado,
			}
		).insert(ignore_permissions=True)

		resultado, enviar = self._rodar("2026-08-13")
		self.assertEqual(resultado["lembretes"]["quitadas_por_outro_meio"], 1)
		self.assertEqual(resultado["lembretes"]["enviados"], 0)
		enviar.assert_not_called()
