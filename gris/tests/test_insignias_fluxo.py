from typing import ClassVar

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.insignias import consultas, endpoints, permissoes
from gris.gris.doctype.solicitacao_de_insignias.solicitacao_de_insignias import (
	STATUS_CANCELADA,
	STATUS_COMPRADA,
	STATUS_ENTREGUE,
	STATUS_RECEBIDA,
	STATUS_SOLICITADA,
	TRANSICOES_PERMITIDAS,
)


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


class TestPermissoesDoFluxo(FrappeTestCase):
	def _com_roles(self, roles):
		"""Substitui frappe.get_roles para simular papéis sem tocar no banco."""
		original = permissoes.frappe.get_roles
		permissoes.frappe.get_roles = lambda user=None: list(roles)
		self.addCleanup(lambda: setattr(permissoes.frappe, "get_roles", original))

	def test_equipe_de_metodos_solicita_mas_nao_compra(self):
		self._com_roles(["Equipe de Metodos"])
		self.assertTrue(permissoes.pode_solicitar("escotista@exemplo.com"))
		self.assertFalse(permissoes.pode_comprar("escotista@exemplo.com"))

	def test_financeiro_compra_mas_nao_solicita(self):
		self._com_roles(["Gestor Financeiro"])
		self.assertTrue(permissoes.pode_comprar("financeiro@exemplo.com"))
		self.assertFalse(permissoes.pode_solicitar("financeiro@exemplo.com"))

	def test_equipe_de_metodos_nao_ve_fila_completa(self):
		self._com_roles(["Equipe de Metodos"])
		self.assertFalse(permissoes.pode_ver_todas("escotista@exemplo.com"))

	def test_solicitante_ve_o_proprio_pedido(self):
		self._com_roles(["Equipe de Metodos"])
		doc = frappe._dict(solicitante="escotista@exemplo.com", status=STATUS_SOLICITADA)
		self.assertTrue(permissoes.pode_ver_solicitacao(doc, "escotista@exemplo.com"))
		self.assertFalse(permissoes.pode_ver_solicitacao(doc, "outro@exemplo.com"))

	def test_solicitante_cancela_antes_da_compra(self):
		self._com_roles(["Equipe de Metodos"])
		doc = frappe._dict(solicitante="escotista@exemplo.com", status=STATUS_SOLICITADA)
		self.assertTrue(permissoes.pode_cancelar(doc, "escotista@exemplo.com"))

	def test_solicitante_nao_cancela_depois_da_compra(self):
		self._com_roles(["Equipe de Metodos"])
		doc = frappe._dict(solicitante="escotista@exemplo.com", status=STATUS_COMPRADA)
		self.assertFalse(permissoes.pode_cancelar(doc, "escotista@exemplo.com"))

	def test_financeiro_cancela_pedido_ja_comprado(self):
		self._com_roles(["Gestor Financeiro"])
		doc = frappe._dict(solicitante="escotista@exemplo.com", status=STATUS_COMPRADA)
		self.assertTrue(permissoes.pode_cancelar(doc, "financeiro@exemplo.com"))

	def test_entrega_so_e_registrada_apos_recebimento(self):
		self._com_roles(["Equipe de Metodos"])
		doc = frappe._dict(solicitante="escotista@exemplo.com", status=STATUS_COMPRADA)
		self.assertFalse(permissoes.pode_registrar_entrega(doc, "escotista@exemplo.com"))

		doc.status = STATUS_RECEBIDA
		self.assertTrue(permissoes.pode_registrar_entrega(doc, "escotista@exemplo.com"))

	def test_terceiro_sem_papel_nao_registra_entrega(self):
		self._com_roles(["Responsavel"])
		doc = frappe._dict(solicitante="escotista@exemplo.com", status=STATUS_RECEBIDA)
		self.assertFalse(permissoes.pode_registrar_entrega(doc, "estranho@exemplo.com"))

	def test_apenas_gestor_de_metodos_mantem_o_catalogo(self):
		self._com_roles(["Gestor de Metodos"])
		self.assertTrue(permissoes.pode_gerenciar_catalogo("gestor@exemplo.com"))

	def test_equipe_de_metodos_nao_mantem_o_catalogo(self):
		self._com_roles(["Equipe de Metodos"])
		self.assertFalse(permissoes.pode_gerenciar_catalogo("escotista@exemplo.com"))

	def test_financeiro_nao_mantem_o_catalogo(self):
		self._com_roles(["Gestor Financeiro"])
		self.assertFalse(permissoes.pode_gerenciar_catalogo("financeiro@exemplo.com"))


class TestNormalizacaoDeItens(FrappeTestCase):
	CATALOGO: ClassVar[dict[str, dict]] = {
		"Distintivo de Progressão I": {
			"name": "Distintivo de Progressão I",
			"tipo": "Distintivo de Progressão",
			"ramo": "Lobinho",
			"valor_unitario": 12.5,
			"ativo": 1,
		},
		"Insígnia Inativa": {
			"name": "Insígnia Inativa",
			"tipo": "Especialidade",
			"ramo": "Todos",
			"valor_unitario": 8.0,
			"ativo": 0,
		},
	}

	def setUp(self):
		super().setUp()
		original_get_value = endpoints.frappe.db.get_value
		original_exists = endpoints.frappe.db.exists

		def fake_get_value(doctype, name, fields=None, as_dict=False, **kwargs):
			if doctype == "Insignia ou Distintivo":
				registro = self.CATALOGO.get(name)
				return frappe._dict(registro) if registro else None
			return original_get_value(doctype, name, fields, as_dict=as_dict, **kwargs)

		def fake_exists(doctype, name=None, **kwargs):
			if doctype == "Associado":
				return name == "ASSOC-001"
			return original_exists(doctype, name, **kwargs)

		endpoints.frappe.db.get_value = fake_get_value
		endpoints.frappe.db.exists = fake_exists
		self.addCleanup(lambda: setattr(endpoints.frappe.db, "get_value", original_get_value))
		self.addCleanup(lambda: setattr(endpoints.frappe.db, "exists", original_exists))

	def test_valor_unitario_vem_do_catalogo_e_ignora_o_cliente(self):
		itens = endpoints._normalizar_itens(
			[{"insignia": "Distintivo de Progressão I", "quantidade": 3, "valor_unitario": 0.01}]
		)
		self.assertEqual(len(itens), 1)
		self.assertEqual(itens[0]["valor_unitario"], 12.5)
		self.assertEqual(itens[0]["tipo"], "Distintivo de Progressão")

	def test_recusa_insignia_inexistente(self):
		with self.assertRaises(frappe.ValidationError):
			endpoints._normalizar_itens([{"insignia": "Não existe", "quantidade": 1}])

	def test_recusa_insignia_inativa(self):
		with self.assertRaises(frappe.ValidationError):
			endpoints._normalizar_itens([{"insignia": "Insígnia Inativa", "quantidade": 1}])

	def test_recusa_quantidade_zero_ou_negativa(self):
		for quantidade in (0, -5):
			with self.assertRaises(frappe.ValidationError):
				endpoints._normalizar_itens(
					[{"insignia": "Distintivo de Progressão I", "quantidade": quantidade}]
				)

	def test_recusa_quantidade_acima_do_limite(self):
		with self.assertRaises(frappe.ValidationError):
			endpoints._normalizar_itens(
				[
					{
						"insignia": "Distintivo de Progressão I",
						"quantidade": endpoints.MAX_QUANTIDADE + 1,
					}
				]
			)

	def test_recusa_lista_vazia(self):
		with self.assertRaises(frappe.ValidationError):
			endpoints._normalizar_itens([])

	def test_recusa_beneficiario_inexistente(self):
		with self.assertRaises(frappe.ValidationError):
			endpoints._normalizar_itens(
				[
					{
						"insignia": "Distintivo de Progressão I",
						"quantidade": 1,
						"beneficiario": "ASSOC-999",
					}
				]
			)

	def test_aceita_beneficiario_valido(self):
		itens = endpoints._normalizar_itens(
			[
				{
					"insignia": "Distintivo de Progressão I",
					"quantidade": 1,
					"beneficiario": "ASSOC-001",
				}
			]
		)
		self.assertEqual(itens[0]["beneficiario"], "ASSOC-001")


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
