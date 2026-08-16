import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api import registro_provisorio_notificacoes


class _FakeLogger:
	def info(self, *_args, **_kwargs):
		return None

	def warning(self, *_args, **_kwargs):
		return None


class TestRegistroProvisorioNotificacoes(FrappeTestCase):
	def _executar_rotina(
		self,
		novos_associados,
		*,
		links=None,
		responsaveis=None,
		responsavel_administrativo=None,
		dias_configurados=20,
		data_hoje="2026-05-11",
		sender=None,
	):
		links = links or []
		responsaveis = responsaveis or []

		modulo = registro_provisorio_notificacoes
		orig_get_all = modulo.frappe.get_all
		orig_get_single_value = modulo.frappe.db.get_single_value
		orig_get_value = modulo.frappe.db.get_value
		orig_set_value = modulo.frappe.db.set_value
		orig_logger = modulo.frappe.logger
		orig_today = modulo.today
		orig_get_url = modulo.get_url
		orig_enviar_texto = modulo.enviar_texto

		enviadas = []
		atualizacoes = []
		filtros_usados = []

		def _to_dict(rows):
			return [frappe._dict(row) for row in rows]

		def _fake_get_all(doctype, *args, **kwargs):
			if doctype == "Novo Associado":
				filtros_usados.append(kwargs.get("filters", {}))
				return _to_dict(novos_associados)
			if doctype == "Responsavel Vinculo":
				return _to_dict(links)
			if doctype == "Responsavel":
				return _to_dict(responsaveis)
			return []

		def _fake_get_single_value(_doctype, fieldname):
			if fieldname == "dias_aviso_seguimento_provisorio":
				return dias_configurados
			if fieldname == "responsavel_administrativo":
				return responsavel_administrativo.get("name") if responsavel_administrativo else None
			return None

		def _fake_get_value(doctype, *args, **kwargs):
			if doctype == "Associado" and responsavel_administrativo:
				return frappe._dict(responsavel_administrativo)
			return None

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
			if sender:
				sender(numero, mensagem)
			enviadas.append({"numero": numero, "mensagem": mensagem, "enqueue": enqueue})

		try:
			modulo.frappe.get_all = _fake_get_all
			modulo.frappe.db.get_single_value = _fake_get_single_value
			modulo.frappe.db.get_value = _fake_get_value
			modulo.frappe.db.set_value = _fake_set_value
			modulo.frappe.logger = lambda *args, **kwargs: _FakeLogger()
			modulo.today = lambda: data_hoje
			modulo.get_url = lambda path="": f"https://gris.test{path}"
			modulo.enviar_texto = _fake_enviar_texto

			modulo.enviar_avisos_seguimento_registro_provisorio()
		finally:
			modulo.frappe.get_all = orig_get_all
			modulo.frappe.db.get_single_value = orig_get_single_value
			modulo.frappe.db.get_value = orig_get_value
			modulo.frappe.db.set_value = orig_set_value
			modulo.frappe.logger = orig_logger
			modulo.today = orig_today
			modulo.get_url = orig_get_url
			modulo.enviar_texto = orig_enviar_texto

		return enviadas, atualizacoes, filtros_usados

	def test_envia_aviso_para_responsavel_administrativo(self):
		enviadas, atualizacoes, _ = self._executar_rotina(
			[
				{
					"name": "NA-001",
					"nome_completo": "Joao da Silva",
					"data_registro_provisorio_efetivado": "2026-04-21",
				}
			],
			links=[
				{
					"beneficiario_novo_associado": "NA-001",
					"responsavel": "RESP-001",
					"é_guardiao_legal": 1,
					"primeiro_responsavel": 1,
				}
			],
			responsaveis=[
				{
					"name": "RESP-001",
					"nome_completo": "Maria da Silva",
					"celular": "+5511999991111",
					"telefone_secundario": None,
				}
			],
			responsavel_administrativo={
				"name": "ASSOC-ADM",
				"nome_completo": "Carla Souza",
				"telefone": "+5511988882222",
			},
		)

		self.assertEqual(len(enviadas), 1)
		self.assertEqual(enviadas[0]["numero"], "+5511988882222")
		mensagem = enviadas[0]["mensagem"]
		self.assertIn("Carla", mensagem)
		self.assertIn("Joao da Silva", mensagem)
		self.assertIn("Maria da Silva", mensagem)
		self.assertIn("+5511999991111", mensagem)
		self.assertIn("20 dia(s)", mensagem)
		self.assertIn("registro efetivo", mensagem)

		self.assertEqual(len(atualizacoes), 1)
		self.assertEqual(atualizacoes[0]["doctype"], "Novo Associado")
		self.assertEqual(atualizacoes[0]["docname"], "NA-001")
		self.assertEqual(atualizacoes[0]["fieldname"], "data_aviso_seguimento_provisorio")
		self.assertEqual(atualizacoes[0]["value"], "2026-05-11")
		self.assertFalse(atualizacoes[0]["update_modified"])

	def test_filtra_por_data_limite_de_20_dias(self):
		_, _, filtros_usados = self._executar_rotina(
			[],
			responsavel_administrativo={
				"name": "ASSOC-ADM",
				"nome_completo": "Carla Souza",
				"telefone": "+5511988882222",
			},
		)

		self.assertEqual(len(filtros_usados), 1)
		filtros = filtros_usados[0]
		self.assertEqual(filtros["tipo_de_registro"], "Provisório")
		self.assertEqual(filtros["registro_provisorio_efetivado"], 1)
		self.assertEqual(filtros["registro_definitivo_efetivado"], 0)
		self.assertEqual(filtros["data_registro_provisorio_efetivado"][0], "<=")
		self.assertEqual(str(filtros["data_registro_provisorio_efetivado"][1]), "2026-04-21")
		self.assertEqual(filtros["data_aviso_seguimento_provisorio"], ["is", "not set"])

	def test_usa_dias_configurados_quando_valor_e_valido(self):
		_, _, filtros_usados = self._executar_rotina(
			[],
			dias_configurados=30,
			responsavel_administrativo={
				"name": "ASSOC-ADM",
				"nome_completo": "Carla Souza",
				"telefone": "+5511988882222",
			},
		)

		self.assertEqual(str(filtros_usados[0]["data_registro_provisorio_efetivado"][1]), "2026-04-11")

	def test_cai_para_padrao_de_20_dias_quando_configuracao_invalida(self):
		_, _, filtros_usados = self._executar_rotina(
			[],
			dias_configurados=0,
			responsavel_administrativo={
				"name": "ASSOC-ADM",
				"nome_completo": "Carla Souza",
				"telefone": "+5511988882222",
			},
		)

		self.assertEqual(str(filtros_usados[0]["data_registro_provisorio_efetivado"][1]), "2026-04-21")

	def test_nao_envia_sem_responsavel_administrativo_configurado(self):
		enviadas, atualizacoes, _ = self._executar_rotina(
			[
				{
					"name": "NA-001",
					"nome_completo": "Joao da Silva",
					"data_registro_provisorio_efetivado": "2026-04-21",
				}
			],
			responsavel_administrativo=None,
		)

		self.assertEqual(enviadas, [])
		self.assertEqual(atualizacoes, [])

	def test_nao_envia_quando_responsavel_administrativo_sem_telefone(self):
		enviadas, atualizacoes, _ = self._executar_rotina(
			[
				{
					"name": "NA-001",
					"nome_completo": "Joao da Silva",
					"data_registro_provisorio_efetivado": "2026-04-21",
				}
			],
			responsavel_administrativo={
				"name": "ASSOC-ADM",
				"nome_completo": "Carla Souza",
				"telefone": "",
			},
		)

		self.assertEqual(enviadas, [])
		self.assertEqual(atualizacoes, [])

	def test_envia_mesmo_sem_responsavel_vinculado_ao_novo_associado(self):
		enviadas, atualizacoes, _ = self._executar_rotina(
			[
				{
					"name": "NA-002",
					"nome_completo": "Ana Lima",
					"data_registro_provisorio_efetivado": "2026-04-01",
				}
			],
			responsavel_administrativo={
				"name": "ASSOC-ADM",
				"nome_completo": "Carla Souza",
				"telefone": "+5511988882222",
			},
		)

		self.assertEqual(len(enviadas), 1)
		self.assertIn("não cadastrado no Gris", enviadas[0]["mensagem"])
		self.assertIn("40 dia(s)", enviadas[0]["mensagem"])
		self.assertEqual(len(atualizacoes), 1)

	def test_prioriza_responsavel_com_telefone_entre_os_vinculos(self):
		enviadas, _, _ = self._executar_rotina(
			[
				{
					"name": "NA-003",
					"nome_completo": "Pedro Rocha",
					"data_registro_provisorio_efetivado": "2026-04-21",
				}
			],
			links=[
				{
					"beneficiario_novo_associado": "NA-003",
					"responsavel": "RESP-SEM-TEL",
					"é_guardiao_legal": 1,
					"primeiro_responsavel": 1,
				},
				{
					"beneficiario_novo_associado": "NA-003",
					"responsavel": "RESP-COM-TEL",
					"é_guardiao_legal": 0,
					"primeiro_responsavel": 0,
				},
			],
			responsaveis=[
				{
					"name": "RESP-SEM-TEL",
					"nome_completo": "Sem Telefone",
					"celular": None,
					"telefone_secundario": None,
				},
				{
					"name": "RESP-COM-TEL",
					"nome_completo": "Com Telefone",
					"celular": None,
					"telefone_secundario": "+5511977773333",
				},
			],
			responsavel_administrativo={
				"name": "ASSOC-ADM",
				"nome_completo": "Carla Souza",
				"telefone": "+5511988882222",
			},
		)

		self.assertEqual(len(enviadas), 1)
		self.assertIn("Com Telefone", enviadas[0]["mensagem"])
		self.assertIn("+5511977773333", enviadas[0]["mensagem"])

	def test_falha_de_envio_nao_marca_aviso_e_nao_interrompe_os_demais(self):
		modulo = registro_provisorio_notificacoes
		orig_log_error = modulo.frappe.log_error
		modulo.frappe.log_error = lambda *args, **kwargs: None

		chamadas = {"total": 0}

		def _enviar_com_falha_no_primeiro(_numero, _mensagem):
			chamadas["total"] += 1
			if chamadas["total"] == 1:
				raise RuntimeError("Evolution API indisponível")

		try:
			_, atualizacoes, _ = self._executar_rotina(
				[
					{
						"name": "NA-001",
						"nome_completo": "Joao da Silva",
						"data_registro_provisorio_efetivado": "2026-04-21",
					},
					{
						"name": "NA-002",
						"nome_completo": "Ana Lima",
						"data_registro_provisorio_efetivado": "2026-04-01",
					},
				],
				responsavel_administrativo={
					"name": "ASSOC-ADM",
					"nome_completo": "Carla Souza",
					"telefone": "+5511988882222",
				},
				sender=_enviar_com_falha_no_primeiro,
			)
		finally:
			modulo.frappe.log_error = orig_log_error

		self.assertEqual(chamadas["total"], 2)
		self.assertEqual([u["docname"] for u in atualizacoes], ["NA-002"])
