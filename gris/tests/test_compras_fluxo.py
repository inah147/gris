from typing import ClassVar

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from gris.api.compras import consultas, endpoints, permissoes
from gris.gris.doctype.solicitacao_de_compra.solicitacao_de_compra import (
	STATUS_CANCELADA,
	STATUS_COMPRADA,
	STATUS_ENTREGUE,
	STATUS_RECEBIDA,
	STATUS_SOLICITADA,
	TRANSICOES_PERMITIDAS,
	SolicitacaodeCompra,
)

PE = permissoes.AREA_PROGRAMA_EDUCATIVO
MANUTENCAO = permissoes.AREA_MANUTENCAO
ADMINISTRATIVO = permissoes.AREA_ADMINISTRATIVO


class TestTransicoesDeStatus(FrappeTestCase):
	def test_fluxo_feliz_encadeia_todas_as_etapas(self):
		self.assertIn(STATUS_COMPRADA, TRANSICOES_PERMITIDAS[STATUS_SOLICITADA])
		self.assertIn(STATUS_RECEBIDA, TRANSICOES_PERMITIDAS[STATUS_COMPRADA])
		self.assertIn(STATUS_ENTREGUE, TRANSICOES_PERMITIDAS[STATUS_RECEBIDA])

	def test_status_finais_nao_reabrem(self):
		self.assertEqual(TRANSICOES_PERMITIDAS[STATUS_ENTREGUE], set())
		self.assertEqual(TRANSICOES_PERMITIDAS[STATUS_CANCELADA], set())

	def test_nao_pula_etapa_da_compra(self):
		# Um pedido não pode ir direto de "Solicitada" para "Recebida"/"Entregue".
		self.assertNotIn(STATUS_RECEBIDA, TRANSICOES_PERMITIDAS[STATUS_SOLICITADA])
		self.assertNotIn(STATUS_ENTREGUE, TRANSICOES_PERMITIDAS[STATUS_SOLICITADA])

	def test_nao_cancela_depois_de_recebida(self):
		self.assertNotIn(STATUS_CANCELADA, TRANSICOES_PERMITIDAS[STATUS_RECEBIDA])


class TestPermissoesPorArea(FrappeTestCase):
	def _com_roles(self, roles):
		"""Substitui frappe.get_roles para simular papéis sem tocar no banco."""
		original = permissoes.frappe.get_roles
		permissoes.frappe.get_roles = lambda user=None: list(roles)
		self.addCleanup(lambda: setattr(permissoes.frappe, "get_roles", original))

	def test_qualquer_pessoa_logada_solicita(self):
		self._com_roles([])
		self.assertTrue(permissoes.pode_solicitar("membro@exemplo.com"))
		self.assertFalse(permissoes.pode_solicitar("Guest"))

	def test_qualquer_pessoa_cadastra_item_de_manutencao_e_administrativo(self):
		self._com_roles([])
		self.assertTrue(permissoes.pode_cadastrar_item(MANUTENCAO, "membro@exemplo.com"))
		self.assertTrue(permissoes.pode_cadastrar_item(ADMINISTRATIVO, "membro@exemplo.com"))

	def test_so_gestor_de_metodos_cadastra_distintivo(self):
		self._com_roles(["Equipe de Metodos"])
		self.assertFalse(permissoes.pode_cadastrar_item(PE, "escotista@exemplo.com"))

		self._com_roles(["Gestor de Metodos"])
		self.assertTrue(permissoes.pode_cadastrar_item(PE, "gestor@exemplo.com"))

	def test_area_invalida_nao_aceita_cadastro(self):
		self._com_roles(["System Manager"])
		self.assertFalse(permissoes.pode_cadastrar_item("Cozinha", "admin@exemplo.com"))

	def test_gestor_de_metodos_compra_so_o_programa_educativo(self):
		self._com_roles(["Gestor de Metodos"])
		self.assertTrue(permissoes.pode_comprar(PE, "gestor@exemplo.com"))
		self.assertFalse(permissoes.pode_comprar(MANUTENCAO, "gestor@exemplo.com"))
		self.assertFalse(permissoes.pode_comprar(ADMINISTRATIVO, "gestor@exemplo.com"))

	def test_gestor_de_manutencao_compra_so_manutencao(self):
		self._com_roles(["Gestor de Manutencao"])
		self.assertTrue(permissoes.pode_comprar(MANUTENCAO, "manut@exemplo.com"))
		self.assertFalse(permissoes.pode_comprar(PE, "manut@exemplo.com"))

	def test_financeiro_ve_a_fila_mas_nao_compra(self):
		self._com_roles(["Gestor Financeiro"])
		for area in permissoes.AREAS:
			self.assertTrue(permissoes.pode_ver_fila(area, "financeiro@exemplo.com"))
			self.assertFalse(permissoes.pode_comprar(area, "financeiro@exemplo.com"))

	def test_equipe_de_metodos_nao_ve_a_fila(self):
		self._com_roles(["Equipe de Metodos"])
		self.assertFalse(permissoes.pode_ver_alguma_fila("escotista@exemplo.com"))

	def test_gestor_ve_a_fila_so_da_propria_area(self):
		self._com_roles(["Gestor Administrativo"])
		self.assertEqual(permissoes.areas_para(permissoes.pode_ver_fila, "adm@exemplo.com"), [ADMINISTRATIVO])

	def test_quem_cadastrou_edita_o_proprio_item_fora_do_pe(self):
		self._com_roles([])
		item = frappe._dict(area=MANUTENCAO, owner="membro@exemplo.com")
		self.assertTrue(permissoes.pode_editar_item(item, "membro@exemplo.com"))
		self.assertFalse(permissoes.pode_editar_item(item, "outro@exemplo.com"))

	def test_no_pe_so_o_gestor_de_metodos_edita(self):
		self._com_roles([])
		item = frappe._dict(area=PE, owner="membro@exemplo.com")
		self.assertFalse(permissoes.pode_editar_item(item, "membro@exemplo.com"))

		self._com_roles(["Gestor de Metodos"])
		self.assertTrue(permissoes.pode_editar_item(item, "gestor@exemplo.com"))

	def test_gestor_da_area_edita_item_de_outra_pessoa(self):
		self._com_roles(["Gestor de Manutencao"])
		item = frappe._dict(area=MANUTENCAO, owner="membro@exemplo.com")
		self.assertTrue(permissoes.pode_editar_item(item, "manut@exemplo.com"))

	def test_solicitante_ve_o_proprio_pedido(self):
		self._com_roles([])
		doc = frappe._dict(solicitante="membro@exemplo.com", status=STATUS_SOLICITADA, area=MANUTENCAO)
		self.assertTrue(permissoes.pode_ver_solicitacao(doc, "membro@exemplo.com"))
		self.assertFalse(permissoes.pode_ver_solicitacao(doc, "outro@exemplo.com"))

	def test_solicitante_cancela_antes_da_compra(self):
		self._com_roles([])
		doc = frappe._dict(solicitante="membro@exemplo.com", status=STATUS_SOLICITADA, area=MANUTENCAO)
		self.assertTrue(permissoes.pode_cancelar(doc, "membro@exemplo.com"))

	def test_solicitante_nao_cancela_depois_da_compra(self):
		self._com_roles([])
		doc = frappe._dict(solicitante="membro@exemplo.com", status=STATUS_COMPRADA, area=MANUTENCAO)
		self.assertFalse(permissoes.pode_cancelar(doc, "membro@exemplo.com"))

	def test_gestor_da_area_cancela_pedido_ja_comprado(self):
		self._com_roles(["Gestor de Metodos"])
		doc = frappe._dict(solicitante="escotista@exemplo.com", status=STATUS_COMPRADA, area=PE)
		self.assertTrue(permissoes.pode_cancelar(doc, "gestor@exemplo.com"))

	def test_financeiro_nao_cancela_pedido_ja_comprado(self):
		self._com_roles(["Gestor Financeiro"])
		doc = frappe._dict(solicitante="escotista@exemplo.com", status=STATUS_COMPRADA, area=PE)
		self.assertFalse(permissoes.pode_cancelar(doc, "financeiro@exemplo.com"))

	def test_entrega_so_e_registrada_apos_recebimento(self):
		self._com_roles([])
		doc = frappe._dict(solicitante="membro@exemplo.com", status=STATUS_COMPRADA, area=PE)
		self.assertFalse(permissoes.pode_registrar_entrega(doc, "membro@exemplo.com"))

		doc.status = STATUS_RECEBIDA
		self.assertTrue(permissoes.pode_registrar_entrega(doc, "membro@exemplo.com"))

	def test_gestor_de_outra_area_nao_registra_entrega(self):
		self._com_roles(["Gestor de Manutencao"])
		doc = frappe._dict(solicitante="escotista@exemplo.com", status=STATUS_RECEBIDA, area=PE)
		self.assertFalse(permissoes.pode_registrar_entrega(doc, "manut@exemplo.com"))


class TestNormalizacaoDeItens(FrappeTestCase):
	CATALOGO: ClassVar[dict[str, dict]] = {
		"Distintivo de Progressão I": {
			"name": "Distintivo de Progressão I",
			"area": PE,
			"tipo": "Distintivo de Progressão",
			"ramo": "Lobinho",
			"valor_unitario": 12.5,
			"ativo": 1,
		},
		"Insígnia Inativa": {
			"name": "Insígnia Inativa",
			"area": PE,
			"tipo": "Especialidade",
			"ramo": "Todos",
			"valor_unitario": 8.0,
			"ativo": 0,
		},
		"Lâmpada LED": {
			"name": "Lâmpada LED",
			"area": MANUTENCAO,
			"tipo": None,
			"ramo": None,
			"valor_unitario": 15.0,
			"ativo": 1,
		},
	}

	def setUp(self):
		super().setUp()
		original_get_value = endpoints.frappe.db.get_value

		def fake_get_value(doctype, name, fields=None, as_dict=False, **kwargs):
			if doctype == endpoints.CATALOGO_DOCTYPE:
				registro = self.CATALOGO.get(name)
				return frappe._dict(registro) if registro else None
			return original_get_value(doctype, name, fields, as_dict=as_dict, **kwargs)

		endpoints.frappe.db.get_value = fake_get_value
		self.addCleanup(lambda: setattr(endpoints.frappe.db, "get_value", original_get_value))

	def _normalizar(self, itens, area=PE):
		return endpoints._normalizar_itens(itens, area)

	def test_valor_unitario_vem_do_catalogo_e_ignora_o_cliente(self):
		itens = self._normalizar(
			[{"item_catalogo": "Distintivo de Progressão I", "quantidade": 3, "valor_unitario": 0.01}]
		)
		self.assertEqual(len(itens), 1)
		self.assertEqual(itens[0]["valor_unitario"], 12.5)
		self.assertEqual(itens[0]["tipo"], "Distintivo de Progressão")

	def test_recusa_item_de_outra_area(self):
		with self.assertRaises(frappe.ValidationError):
			self._normalizar([{"item_catalogo": "Lâmpada LED", "quantidade": 1}], area=PE)

	def test_aceita_item_da_propria_area(self):
		itens = self._normalizar([{"item_catalogo": "Lâmpada LED", "quantidade": 2}], area=MANUTENCAO)
		self.assertEqual(itens[0]["valor_unitario"], 15.0)

	def test_recusa_item_inexistente(self):
		with self.assertRaises(frappe.ValidationError):
			self._normalizar([{"item_catalogo": "Não existe", "quantidade": 1}])

	def test_recusa_item_inativo(self):
		with self.assertRaises(frappe.ValidationError):
			self._normalizar([{"item_catalogo": "Insígnia Inativa", "quantidade": 1}])

	def test_recusa_quantidade_zero_ou_negativa(self):
		for quantidade in (0, -5):
			with self.assertRaises(frappe.ValidationError):
				self._normalizar([{"item_catalogo": "Distintivo de Progressão I", "quantidade": quantidade}])

	def test_recusa_quantidade_acima_do_limite(self):
		with self.assertRaises(frappe.ValidationError):
			self._normalizar(
				[{"item_catalogo": "Distintivo de Progressão I", "quantidade": endpoints.MAX_QUANTIDADE + 1}]
			)

	def test_recusa_lista_vazia(self):
		with self.assertRaises(frappe.ValidationError):
			self._normalizar([])

	def test_ignora_beneficiario_enviado_pelo_cliente(self):
		# O pedido é por quantidade: quem recebe cada peça é controle da seção.
		itens = self._normalizar(
			[{"item_catalogo": "Distintivo de Progressão I", "quantidade": 1, "beneficiario": "ASSOC-001"}]
		)
		self.assertNotIn("beneficiario", itens[0])


class TestItensDoPedidoPorQuantidade(FrappeTestCase):
	"""Sem beneficiário por item, o mesmo item precisa vir numa única linha."""

	def _validar(self, itens):
		doc = frappe._dict(itens=[frappe._dict(item) for item in itens])
		SolicitacaodeCompra._validar_itens(doc)
		return doc

	def test_recusa_o_mesmo_item_em_duas_linhas(self):
		with self.assertRaises(frappe.ValidationError):
			self._validar(
				[
					{"item_catalogo": "Distintivo de Progressão I", "quantidade": 1},
					{"item_catalogo": "Distintivo de Progressão I", "quantidade": 2},
				]
			)

	def test_aceita_itens_diferentes(self):
		doc = self._validar(
			[
				{"item_catalogo": "Distintivo de Progressão I", "quantidade": 1},
				{"item_catalogo": "Distintivo de Progressão II", "quantidade": 2},
			]
		)
		self.assertEqual([item.quantidade for item in doc.itens], [1, 2])


class TestTimelineEResumo(FrappeTestCase):
	def test_timeline_marca_etapa_atual(self):
		etapas = consultas._montar_timeline({"status": STATUS_COMPRADA})
		estados = {etapa["label"]: etapa["estado"] for etapa in etapas}
		self.assertEqual(estados["Solicitada"], "concluida")
		self.assertEqual(estados["Comprada"], "atual")
		self.assertEqual(estados["Recebida"], "pendente")
		self.assertEqual(estados["Entregue"], "pendente")

	def test_timeline_de_cancelada_encerra_o_fluxo(self):
		etapas = consultas._montar_timeline({"status": STATUS_CANCELADA})
		self.assertEqual([etapa["label"] for etapa in etapas], ["Solicitada", "Cancelada"])
		self.assertEqual(etapas[-1]["estado"], "cancelada")

	def test_resumo_conta_por_status(self):
		linhas = [
			{"status": STATUS_SOLICITADA},
			{"status": STATUS_SOLICITADA},
			{"status": STATUS_ENTREGUE},
		]
		resumo = consultas.resumo_por_status(linhas)
		self.assertEqual(resumo[STATUS_SOLICITADA], 2)
		self.assertEqual(resumo[STATUS_ENTREGUE], 1)
		self.assertEqual(resumo[STATUS_COMPRADA], 0)


class TestStatusVisiveisPorPadrao(FrappeTestCase):
	"""Comprado ou encerrado só aparece nas listas quando a pessoa pede."""

	def test_sem_parametro_mostra_so_aguardando_compra(self):
		self.assertEqual(consultas.status_visiveis(), [STATUS_SOLICITADA])

	def test_status_explicito_mostra_aquele_status(self):
		self.assertEqual(consultas.status_visiveis(STATUS_COMPRADA), [STATUS_COMPRADA])
		self.assertEqual(consultas.status_visiveis(STATUS_ENTREGUE), [STATUS_ENTREGUE])

	def test_mostrar_todas_tira_o_filtro(self):
		self.assertIsNone(consultas.status_visiveis(None, "todas"))
		self.assertIsNone(consultas.status_visiveis(STATUS_COMPRADA, "todas"))

	def test_status_desconhecido_volta_ao_padrao(self):
		self.assertEqual(consultas.status_visiveis("Qualquer"), [STATUS_SOLICITADA])

	def test_slug_desconhecido_nao_e_area(self):
		self.assertEqual(consultas.area_da_requisicao("manutencao"), MANUTENCAO)
		with self.assertRaises(frappe.DoesNotExistError):
			consultas.area_da_requisicao("cozinha")


class TestListaDeCompras(FrappeTestCase):
	"""Consolidação dos itens dos pedidos aguardando compra em uma lista única."""

	ITENS: ClassVar[list[dict]] = [
		{
			"parent": "SC-001",
			"item_catalogo": "Acampamento",
			"tipo": "Especialidade",
			"ramo": "Todos",
			"quantidade": 2,
			"valor_unitario": 5,
		},
		{
			"parent": "SC-001",
			"item_catalogo": "Lis de Ouro",
			"tipo": "Distintivo de Progressão",
			"ramo": "Escoteiro",
			"quantidade": 1,
			"valor_unitario": 8,
		},
		{
			"parent": "SC-002",
			"item_catalogo": "Acampamento",
			"tipo": "Especialidade",
			"ramo": "Todos",
			"quantidade": 3,
			"valor_unitario": 5,
		},
		{
			"parent": "SC-003",
			"item_catalogo": "Lâmpada LED",
			"tipo": None,
			"ramo": None,
			"quantidade": 4,
			"valor_unitario": 15,
		},
	]
	CATALOGO: ClassVar[list[dict]] = [
		{
			"name": "Acampamento",
			"nome": "Acampamento",
			"tipo": "Especialidade",
			"ramo": "Todos",
			"codigo": "ESP-01",
			"valor_unitario": 6,
		},
		{
			"name": "Lis de Ouro",
			"nome": "Lis de Ouro",
			"tipo": "Distintivo de Progressão",
			"ramo": "Escoteiro",
			"codigo": "",
			"valor_unitario": 8,
		},
		{
			"name": "Lâmpada LED",
			"nome": "Lâmpada LED",
			"tipo": None,
			"ramo": None,
			"codigo": "",
			"valor_unitario": 15,
		},
	]

	def setUp(self):
		original = consultas.frappe.get_all

		def fake_get_all(doctype, *args, **kwargs):
			if doctype == consultas.ITEM_DOCTYPE:
				pedidos = kwargs["filters"]["parent"][1]
				return [dict(item) for item in self.ITENS if item["parent"] in pedidos]
			if doctype == consultas.CATALOGO_DOCTYPE:
				return [dict(registro) for registro in self.CATALOGO]
			return original(doctype, *args, **kwargs)

		consultas.frappe.get_all = fake_get_all
		self.addCleanup(lambda: setattr(consultas.frappe, "get_all", original))

	def test_soma_o_mesmo_item_de_pedidos_diferentes(self):
		linhas = {linha["item_catalogo"]: linha for linha in consultas.lista_de_compras(["SC-001", "SC-002"])}
		self.assertEqual(linhas["Acampamento"]["quantidade"], 5)
		self.assertEqual(linhas["Acampamento"]["pedidos"], ["SC-001", "SC-002"])
		self.assertEqual(linhas["Lis de Ouro"]["quantidade"], 1)
		self.assertEqual(linhas["Lis de Ouro"]["pedidos"], ["SC-001"])

	def test_usa_preco_e_codigo_atuais_do_catalogo(self):
		linhas = {linha["item_catalogo"]: linha for linha in consultas.lista_de_compras(["SC-001", "SC-002"])}
		self.assertEqual(linhas["Acampamento"]["codigo"], "ESP-01")
		self.assertEqual(linhas["Acampamento"]["valor_unitario"], 6)
		self.assertEqual(linhas["Acampamento"]["valor_total"], 30)

	def test_ordena_por_tipo_e_nome(self):
		linhas = consultas.lista_de_compras(["SC-001", "SC-002"])
		self.assertEqual([linha["item_catalogo"] for linha in linhas], ["Lis de Ouro", "Acampamento"])

	def test_item_sem_tipo_entra_na_lista(self):
		linhas = consultas.lista_de_compras(["SC-003"])
		self.assertEqual(linhas[0]["tipo"], "—")
		self.assertEqual(linhas[0]["valor_total"], 60)

	def test_sem_pedidos_devolve_lista_vazia(self):
		self.assertEqual(consultas.lista_de_compras([]), [])


class TestFluxoComUsuarioSemPapel(FrappeTestCase):
	"""Ponta a ponta no banco: quem não tem papel nenhum solicita e cadastra item."""

	MEMBRO = "membro.compras@exemplo.com"
	GESTOR = "gestor.manutencao@exemplo.com"

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		for email, papeis in ((cls.MEMBRO, []), (cls.GESTOR, ["Gestor de Manutencao"])):
			if not frappe.db.exists("User", email):
				user = frappe.get_doc(
					{
						"doctype": "User",
						"email": email,
						"first_name": email.split("@")[0],
						"send_welcome_email": 0,
					}
				)
				user.insert(ignore_permissions=True)
			else:
				user = frappe.get_doc("User", email)
			if papeis:
				user.add_roles(*papeis)

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def _cadastrar(self, area, nome, **extra):
		return endpoints.salvar_item_catalogo({"area": area, "nome": nome, "valor_unitario": 10, **extra})

	def test_membro_cadastra_item_e_solicita_em_manutencao(self):
		frappe.set_user(self.MEMBRO)
		item = self._cadastrar(MANUTENCAO, "Fita isolante teste compras")
		self.assertTrue(item["criado"])
		self.assertEqual(item["area"], MANUTENCAO)

		resultado = endpoints.criar_solicitacao(
			{"area": MANUTENCAO, "itens": [{"item_catalogo": item["name"], "quantidade": 3}]}
		)
		doc = frappe.get_doc(endpoints.DOCTYPE, resultado["name"])
		self.assertEqual(doc.area, MANUTENCAO)
		self.assertIsNone(doc.ramo)
		self.assertEqual(doc.valor_estimado, 30)
		self.assertTrue(resultado["redirect"].startswith("/compras/solicitacao"))

	def test_membro_nao_cadastra_distintivo(self):
		frappe.set_user(self.MEMBRO)
		with self.assertRaises(frappe.PermissionError):
			self._cadastrar(PE, "Distintivo teste compras", tipo="Especialidade", ramo="Todos")

	def test_membro_nao_compra_e_gestor_da_area_compra(self):
		frappe.set_user(self.MEMBRO)
		item = self._cadastrar(ADMINISTRATIVO, "Resma teste compras")
		self.assertTrue(item["criado"])
		item_manut = self._cadastrar(MANUTENCAO, "Parafuso teste compras")
		resultado = endpoints.criar_solicitacao(
			{"area": MANUTENCAO, "itens": [{"item_catalogo": item_manut["name"], "quantidade": 1}]}
		)
		with self.assertRaises(frappe.PermissionError):
			endpoints.registrar_compra({"name": resultado["name"], "data_compra": today(), "valor_pago": 9})

		frappe.set_user(self.GESTOR)
		endpoints.registrar_compra({"name": resultado["name"], "data_compra": today(), "valor_pago": 9})
		self.assertEqual(
			frappe.db.get_value(endpoints.DOCTYPE, resultado["name"], "comprado_por"), self.GESTOR
		)

	def test_membro_edita_o_proprio_item_mas_nao_o_alheio(self):
		frappe.set_user(self.GESTOR)
		alheio = self._cadastrar(MANUTENCAO, "Serrote teste compras")

		frappe.set_user(self.MEMBRO)
		proprio = self._cadastrar(MANUTENCAO, "Martelo teste compras")
		endpoints.salvar_item_catalogo({"name": proprio["name"], "area": MANUTENCAO, "valor_unitario": 20})
		with self.assertRaises(frappe.PermissionError):
			endpoints.alternar_item_catalogo({"name": alheio["name"]})

	def test_item_fora_do_pe_nao_guarda_tipo_e_ramo(self):
		frappe.set_user(self.MEMBRO)
		item = self._cadastrar(MANUTENCAO, "Cadeado teste compras", tipo="Especialidade", ramo="Lobinho")
		registro = frappe.db.get_value(
			endpoints.CATALOGO_DOCTYPE, item["name"], ["tipo", "ramo"], as_dict=True
		)
		self.assertIsNone(registro.tipo)
		self.assertIsNone(registro.ramo)

	def test_solicitacao_recusa_area_invalida(self):
		frappe.set_user(self.MEMBRO)
		with self.assertRaises(frappe.ValidationError):
			endpoints.criar_solicitacao({"area": "Cozinha", "itens": []})
