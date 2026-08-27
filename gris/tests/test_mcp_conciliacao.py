"""Testes das ferramentas MCP de conciliação de transações."""

from unittest import TestCase
from unittest.mock import patch

from gris.api.mcp import conciliacao
from gris.api.mcp.registry import ErroDeFerramenta

TRANSACAO_SISTEMA = {
	"name": "SIS-1",
	"fonte": "Sistema",
	"descricao": "PIX RECEBIDO M S SILVA",
	"valor": 60.0,
	"status_conciliacao": "Não conciliada",
	"transacao_conciliada": None,
}
TRANSACAO_PLANILHA = {
	"name": "PLA-1",
	"fonte": "Planilha",
	"descricao": "Contribuição Ago/Mariana Silva",
	"valor": 60.0,
	"status_conciliacao": "Não conciliada",
	"transacao_conciliada": None,
}


def _get_value(mapa):
	def _interno(_doctype, name, _campos, as_dict=True):
		return mapa.get(name)

	return _interno


class TestListagemEcandidatos(TestCase):
	def test_pendentes_normaliza_limite(self):
		with patch.object(conciliacao.servico, "get_sistema_pendentes", return_value=[]) as servico:
			conciliacao.listar_pendentes_conciliacao(carteira="Caixa", limite=999)

		servico.assert_called_once_with(carteira="Caixa", instituicao=None, limit=100)

	def test_candidatos_renomeia_metricas_e_limita(self):
		resposta = {
			"sistema": TRANSACAO_SISTEMA,
			"candidatos": [
				{"name": "PLA-1", "_score": 0.4444, "_diff_valor": 0.0},
				{"name": "PLA-2", "_score": 0.1, "_diff_valor": 0.5},
			],
		}
		with patch.object(conciliacao.servico, "get_candidatos_planilha", return_value=resposta):
			resultado = conciliacao.sugerir_candidatos_conciliacao("SIS-1", limite=1)

		self.assertEqual(len(resultado["candidatos"]), 1)
		self.assertEqual(resultado["total_candidatos"], 2)
		candidato = resultado["candidatos"][0]
		self.assertEqual(candidato["similaridade_descricao"], 0.444)
		self.assertEqual(candidato["diferenca_valor"], 0.0)
		self.assertNotIn("_score", candidato)
		self.assertIn("valor", resultado["tolerancias"])


class TestConciliar(TestCase):
	def test_recusa_par_identico(self):
		with self.assertRaises(ErroDeFerramenta) as ctx:
			conciliacao.conciliar_transacoes("SIS-1", "SIS-1")
		self.assertEqual(ctx.exception.codigo, "ARGUMENTO_INVALIDO")

	def test_transacao_inexistente(self):
		with patch.object(conciliacao.frappe.db, "get_value", return_value=None):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				conciliacao.conciliar_transacoes("SIS-1", "PLA-1")
		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")

	def test_recusa_transacao_ja_conciliada_com_terceiro(self):
		sistema = dict(TRANSACAO_SISTEMA, status_conciliacao="Conciliada", transacao_conciliada="PLA-9")
		mapa = {"SIS-1": sistema, "PLA-1": TRANSACAO_PLANILHA}
		with patch.object(conciliacao.frappe.db, "get_value", side_effect=_get_value(mapa)):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				conciliacao.conciliar_transacoes("SIS-1", "PLA-1")

		self.assertEqual(ctx.exception.codigo, "VALIDACAO")
		self.assertIn("PLA-9", ctx.exception.mensagem)

	def test_valida_categoria_antes_de_conciliar(self):
		with (
			patch.object(conciliacao.frappe.db, "exists", return_value=False),
			patch.object(conciliacao.servico, "conciliar") as servico,
		):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				conciliacao.conciliar_transacoes("SIS-1", "PLA-1", categoria="Inexistente")

		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")
		servico.assert_not_called()

	def test_simulacao_mostra_mantido_sem_gravar(self):
		mapa = {"SIS-1": TRANSACAO_SISTEMA, "PLA-1": TRANSACAO_PLANILHA}
		with (
			patch.object(conciliacao.frappe.db, "get_value", side_effect=_get_value(mapa)),
			patch.object(conciliacao.servico, "conciliar") as servico,
		):
			resultado = conciliacao.conciliar_transacoes("SIS-1", "PLA-1", manter="planilha", simular=True)

		servico.assert_not_called()
		self.assertTrue(resultado["simulacao"])
		self.assertEqual(resultado["mantido"], "PLA-1")
		self.assertEqual(resultado["excluido_do_total"], "SIS-1")

	def test_execucao_delega_com_categorizacao(self):
		mapa = {"SIS-1": TRANSACAO_SISTEMA, "PLA-1": TRANSACAO_PLANILHA}
		with (
			patch.object(conciliacao.frappe.db, "get_value", side_effect=_get_value(mapa)),
			patch.object(conciliacao.frappe.db, "exists", return_value=True),
			patch.object(
				conciliacao.servico,
				"conciliar",
				return_value={"mantido": "SIS-1", "excluido": "PLA-1"},
			) as servico,
		):
			resultado = conciliacao.conciliar_transacoes(
				"SIS-1", "PLA-1", categoria="Contribuições", descricao_reduzida="Mensalidade Ana"
			)

		servico.assert_called_once_with(
			sistema_id="SIS-1",
			planilha_id="PLA-1",
			manter="sistema",
			categoria="Contribuições",
			descricao_reduzida="Mensalidade Ana",
		)
		self.assertTrue(resultado["conciliado"])
		self.assertEqual(resultado["mantido"], "SIS-1")


class TestSemDuplicata(TestCase):
	def test_simulacao_nao_grava(self):
		with (
			patch.object(conciliacao.frappe.db, "get_value", return_value=TRANSACAO_SISTEMA),
			patch.object(conciliacao.servico, "marcar_sem_duplicata") as servico,
		):
			resultado = conciliacao.marcar_sem_duplicata("SIS-1", simular=True)

		servico.assert_not_called()
		self.assertTrue(resultado["simulacao"])

	def test_execucao_delega(self):
		with (
			patch.object(conciliacao.frappe.db, "get_value", return_value=TRANSACAO_SISTEMA),
			patch.object(conciliacao.frappe.db, "exists", return_value=True),
			patch.object(
				conciliacao.servico, "marcar_sem_duplicata", return_value={"resolvido": "SIS-1"}
			) as servico,
		):
			resultado = conciliacao.marcar_sem_duplicata("SIS-1", categoria="Doações")

		servico.assert_called_once_with(sistema_id="SIS-1", categoria="Doações")
		self.assertEqual(resultado["resolvido"], "SIS-1")


class TestDesfazerConciliacao(TestCase):
	def test_recusa_transacao_nao_conciliada(self):
		with patch.object(conciliacao.frappe.db, "get_value", return_value=TRANSACAO_SISTEMA):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				conciliacao.desfazer_conciliacao("SIS-1")
		self.assertEqual(ctx.exception.codigo, "VALIDACAO")

	def test_simulacao_lista_o_par(self):
		conciliada = dict(TRANSACAO_SISTEMA, status_conciliacao="Conciliada", transacao_conciliada="PLA-1")
		with (
			patch.object(conciliacao.frappe.db, "get_value", return_value=conciliada),
			patch.object(conciliacao.servico, "desconciliar") as servico,
		):
			resultado = conciliacao.desfazer_conciliacao("SIS-1", simular=True)

		servico.assert_not_called()
		self.assertEqual(resultado["seriam_desconciliadas"], ["SIS-1", "PLA-1"])

	def test_execucao_delega(self):
		conciliada = dict(TRANSACAO_SISTEMA, status_conciliacao="Conciliada", transacao_conciliada="PLA-1")
		with (
			patch.object(conciliacao.frappe.db, "get_value", return_value=conciliada),
			patch.object(
				conciliacao.servico, "desconciliar", return_value={"desconciliados": ["SIS-1", "PLA-1"]}
			) as servico,
		):
			resultado = conciliacao.desfazer_conciliacao("SIS-1")

		servico.assert_called_once_with("SIS-1")
		self.assertEqual(resultado["desconciliadas"], ["SIS-1", "PLA-1"])
