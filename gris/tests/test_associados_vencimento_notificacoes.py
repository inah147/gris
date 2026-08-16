import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api import associados_vencimento_notificacoes


class _FakeLogger:
	def info(self, *_args, **_kwargs):
		return None

	def warning(self, *_args, **_kwargs):
		return None


class TestAssociadosVencimentoNotificacoes(FrappeTestCase):
	def _executar_rotina(self, associados, links=None, responsaveis=None, data_hoje="2026-05-11"):
		links = links or []
		responsaveis = responsaveis or []

		orig_get_all = associados_vencimento_notificacoes.frappe.get_all
		orig_set_value = associados_vencimento_notificacoes.frappe.db.set_value
		orig_logger = associados_vencimento_notificacoes.frappe.logger
		orig_today = associados_vencimento_notificacoes.today
		orig_enviar_texto = associados_vencimento_notificacoes.enviar_texto

		enviadas = []
		atualizacoes = []

		def _to_dict(rows):
			return [frappe._dict(row) for row in rows]

		def _fake_get_all(doctype, *args, **kwargs):
			if doctype == "Associado":
				return _to_dict(associados)
			if doctype == "Responsavel Vinculo":
				return _to_dict(links)
			if doctype == "Responsavel":
				return _to_dict(responsaveis)
			return []

		def _fake_set_value(doctype, docname, fieldname, value, update_modified=False):
			atualizacoes.append(
				{
					"doctype": doctype,
					"docname": docname,
					"fieldname": fieldname,
					"value": str(value),
					"update_modified": update_modified,
				}
			)

		def _fake_enviar_texto(numero, mensagem, enqueue=True):
			enviadas.append({"numero": numero, "mensagem": mensagem, "enqueue": enqueue})

		try:
			associados_vencimento_notificacoes.frappe.get_all = _fake_get_all
			associados_vencimento_notificacoes.frappe.db.set_value = _fake_set_value
			associados_vencimento_notificacoes.frappe.logger = lambda *args, **kwargs: _FakeLogger()
			associados_vencimento_notificacoes.today = lambda: data_hoje
			associados_vencimento_notificacoes.enviar_texto = _fake_enviar_texto

			associados_vencimento_notificacoes.enviar_lembretes_vencimento_registro_associados()
		finally:
			associados_vencimento_notificacoes.frappe.get_all = orig_get_all
			associados_vencimento_notificacoes.frappe.db.set_value = orig_set_value
			associados_vencimento_notificacoes.frappe.logger = orig_logger
			associados_vencimento_notificacoes.today = orig_today
			associados_vencimento_notificacoes.enviar_texto = orig_enviar_texto

		return enviadas, atualizacoes

	def test_envia_para_responsavel_no_marco_de_30_dias(self):
		associados = [
			{
				"name": "ASSOC-001",
				"nome_completo": "Joao da Silva",
				"telefone": "+5511999991111",
				"validade_registro": "2026-06-10",
				"data_notificacao_vencimento_30_dias": None,
				"data_notificacao_vencimento_7_dias": None,
				"data_notificacao_vencimento": None,
			}
		]
		links = [
			{
				"beneficiario_associado": "ASSOC-001",
				"responsavel": "RESP-001",
				"é_guardiao_legal": 1,
				"primeiro_responsavel": 1,
			}
		]
		responsaveis = [
			{
				"name": "RESP-001",
				"nome_completo": "Maria da Silva",
				"celular": "+5511999992222",
				"telefone_secundario": "",
			}
		]

		enviadas, atualizacoes = self._executar_rotina(associados, links, responsaveis)

		self.assertEqual(len(enviadas), 1)
		self.assertEqual(enviadas[0]["numero"], "+5511999992222")
		self.assertIn("vence em 30 dia(s)", enviadas[0]["mensagem"])
		self.assertEqual(len(atualizacoes), 1)
		self.assertEqual(atualizacoes[0]["fieldname"], "data_notificacao_vencimento_30_dias")

	def test_fallback_para_associado_quando_sem_responsavel(self):
		associados = [
			{
				"name": "ASSOC-002",
				"nome_completo": "Pedro Souza",
				"telefone": "+5511988887777",
				"validade_registro": "2026-05-18",
				"data_notificacao_vencimento_30_dias": None,
				"data_notificacao_vencimento_7_dias": None,
				"data_notificacao_vencimento": None,
			}
		]

		enviadas, atualizacoes = self._executar_rotina(associados)

		self.assertEqual(len(enviadas), 1)
		self.assertEqual(enviadas[0]["numero"], "+5511988887777")
		self.assertIn("seu registro escoteiro vence em 7 dia(s)", enviadas[0]["mensagem"])
		self.assertEqual(atualizacoes[0]["fieldname"], "data_notificacao_vencimento_7_dias")

	def test_fallback_para_associado_quando_responsavel_sem_telefone(self):
		associados = [
			{
				"name": "ASSOC-003",
				"nome_completo": "Ana Lima",
				"telefone": "+5511977776666",
				"validade_registro": "2026-05-11",
				"data_notificacao_vencimento_30_dias": None,
				"data_notificacao_vencimento_7_dias": None,
				"data_notificacao_vencimento": None,
			}
		]
		links = [
			{
				"beneficiario_associado": "ASSOC-003",
				"responsavel": "RESP-003",
				"é_guardiao_legal": 1,
				"primeiro_responsavel": 0,
			}
		]
		responsaveis = [
			{
				"name": "RESP-003",
				"nome_completo": "Carlos Lima",
				"celular": "",
				"telefone_secundario": "",
			}
		]

		enviadas, atualizacoes = self._executar_rotina(associados, links, responsaveis)

		self.assertEqual(len(enviadas), 1)
		self.assertEqual(enviadas[0]["numero"], "+5511977776666")
		self.assertIn("vence hoje", enviadas[0]["mensagem"])
		self.assertEqual(atualizacoes[0]["fieldname"], "data_notificacao_vencimento")

	def test_nao_duplica_envio_quando_ja_notificado_no_dia(self):
		associados = [
			{
				"name": "ASSOC-004",
				"nome_completo": "Rafa Oliveira",
				"telefone": "+5511966665555",
				"validade_registro": "2026-06-10",
				"data_notificacao_vencimento_30_dias": "2026-05-11",
				"data_notificacao_vencimento_7_dias": None,
				"data_notificacao_vencimento": None,
			}
		]

		enviadas, atualizacoes = self._executar_rotina(associados)

		self.assertEqual(enviadas, [])
		self.assertEqual(atualizacoes, [])

	def test_nao_envia_fora_dos_marcos(self):
		associados = [
			{
				"name": "ASSOC-005",
				"nome_completo": "Bruna Costa",
				"telefone": "+5511955554444",
				"validade_registro": "2026-05-25",
				"data_notificacao_vencimento_30_dias": None,
				"data_notificacao_vencimento_7_dias": None,
				"data_notificacao_vencimento": None,
			}
		]

		enviadas, atualizacoes = self._executar_rotina(associados)

		self.assertEqual(enviadas, [])
		self.assertEqual(atualizacoes, [])
