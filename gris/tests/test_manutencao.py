# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Testes do módulo Manutenção: solicitação, acompanhamento e gestão da fila."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, nowdate

from gris.api.manutencao import constantes as c
from gris.api.manutencao.portal import (
	atualizar,
	listar_acompanhamento,
	listar_gestao,
	pode_gerir,
	solicitar,
)
from gris.api.portal_access import PAGE_ROLES, SIDEBAR_STRUCTURE, user_has_access

GESTOR_EMAIL = "gestor.manutencao@teste.gris"
MEMBRO_EMAIL = "membro.manutencao@teste.gris"
OUTRO_EMAIL = "outro.manutencao@teste.gris"


def _criar_user(email: str, roles: list[str]) -> str:
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
		user.enabled = 1
		user.set("roles", [])
		for role in roles:
			user.append("roles", {"role": role})
		user.save(ignore_permissions=True)
		return email

	frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": email.split("@")[0],
			"send_welcome_email": 0,
			"roles": [{"role": role} for role in roles],
		}
	).insert(ignore_permissions=True)
	return email


def _payload(**kwargs) -> dict:
	dados = {
		"titulo": "Lâmpada queimada",
		"local": "Sala da alcateia",
		"categoria": "Elétrica e iluminação",
		"urgencia_informada": c.URGENCIA_ATRAPALHA,
		"descricao": "A lâmpada do fundo apagou.",
	}
	dados.update(kwargs)
	return dados


class TestManutencao(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Role", c.ROLE_GESTOR):
			frappe.get_doc({"doctype": "Role", "role_name": c.ROLE_GESTOR, "desk_access": 0}).insert(
				ignore_permissions=True
			)
		frappe.db.commit()

	def setUp(self):
		self.gestor = _criar_user(GESTOR_EMAIL, [c.ROLE_GESTOR])
		self.membro = _criar_user(MEMBRO_EMAIL, [])
		self.outro = _criar_user(OUTRO_EMAIL, [])
		# Isola os testes de solicitações que já existam no site.
		frappe.db.delete(c.DOCTYPE)

	def tearDown(self):
		frappe.set_user("Administrator")
		# O rollback do FrappeTestCase é por classe: sem este, os documentos de um
		# teste vazam para o próximo.
		frappe.db.rollback()

	def _como(self, user: str):
		frappe.set_user(user)

	def _nova(self, **kwargs):
		dados = {"doctype": c.DOCTYPE, **_payload()}
		dados.update(kwargs)
		return frappe.get_doc(dados).insert(ignore_permissions=True)

	# ───────────────────────── DocType ─────────────────────────

	def test_opcoes_do_doctype_batem_com_as_constantes(self):
		"""O Select do JSON e as constantes são duas listas escritas à mão."""
		meta = frappe.get_meta(c.DOCTYPE)

		def opcoes(fieldname: str) -> list[str]:
			return [linha for linha in (meta.get_field(fieldname).options or "").split("\n") if linha]

		self.assertEqual(opcoes("status"), list(c.STATUS))
		self.assertEqual(opcoes("prioridade"), list(c.PRIORIDADES))
		self.assertEqual(opcoes("categoria"), list(c.CATEGORIAS))
		self.assertEqual(opcoes("urgencia_informada"), list(c.URGENCIAS))

	def test_doctype_nao_concede_papel_all(self):
		"""`All` abriria Desk e API REST com observações internas e custo a todos."""
		papeis = {linha.role for linha in frappe.get_meta(c.DOCTYPE).permissions}
		self.assertNotIn("All", papeis)
		self.assertNotIn("Guest", papeis)
		self.assertIn(c.ROLE_GESTOR, papeis)

	def test_abertura_registra_solicitante_status_e_prioridade_sugerida(self):
		doc = self._nova(urgencia_informada=c.URGENCIA_RISCO)
		self.assertEqual(doc.status, c.STATUS_RECEBIDA)
		self.assertEqual(doc.prioridade, c.PRIORIDADE_ALTA)
		self.assertEqual(doc.solicitante, frappe.session.user)
		self.assertTrue(doc.solicitante_nome)
		self.assertTrue(doc.data_solicitacao)

	def test_prioridade_sugerida_segue_a_urgencia(self):
		for urgencia, esperada in c.PRIORIDADE_POR_URGENCIA.items():
			self.assertEqual(self._nova(urgencia_informada=urgencia).prioridade, esperada)

	def test_opcao_invalida_e_recusada(self):
		with self.assertRaises(frappe.ValidationError):
			self._nova(categoria="Astronomia")
		with self.assertRaises(frappe.ValidationError):
			self._nova(urgencia_informada="Para ontem")

	def test_custo_negativo_e_recusado(self):
		doc = self._nova()
		doc.custo_estimado = -10
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_em_andamento_carimba_o_inicio(self):
		doc = self._nova()
		self.assertFalse(doc.data_inicio)
		doc.status = c.STATUS_EM_ANDAMENTO
		doc.save(ignore_permissions=True)
		self.assertTrue(doc.data_inicio)
		self.assertFalse(doc.data_conclusao)

	def test_concluir_direto_preenche_inicio_e_conclusao(self):
		doc = self._nova()
		doc.status = c.STATUS_CONCLUIDA
		doc.save(ignore_permissions=True)
		self.assertTrue(doc.data_conclusao)
		self.assertEqual(doc.data_inicio, doc.data_conclusao)

	def test_reabrir_limpa_a_conclusao_e_mantem_o_inicio(self):
		doc = self._nova(status=c.STATUS_EM_ANDAMENTO)
		inicio = doc.data_inicio
		doc.status = c.STATUS_CONCLUIDA
		doc.save(ignore_permissions=True)
		doc.status = c.STATUS_PLANEJADA
		doc.save(ignore_permissions=True)
		self.assertFalse(doc.data_conclusao)
		self.assertEqual(doc.data_inicio, inicio)

	# ───────────────────────── solicitar ─────────────────────────

	def test_qualquer_autenticado_pode_solicitar(self):
		self._como(self.membro)
		resposta = solicitar(_payload())
		self.assertTrue(resposta["ok"])
		frappe.set_user("Administrator")
		doc = frappe.get_doc(c.DOCTYPE, resposta["name"])
		self.assertEqual(doc.solicitante, self.membro)
		self.assertEqual(doc.status, c.STATUS_RECEBIDA)

	def test_guest_nao_solicita(self):
		self._como("Guest")
		with self.assertRaises(frappe.PermissionError):
			solicitar(_payload())

	def test_solicitacao_sem_campo_obrigatorio_e_recusada(self):
		self._como(self.membro)
		for campo in ("titulo", "local", "descricao"):
			with self.assertRaises(frappe.ValidationError):
				solicitar(_payload(**{campo: "   "}))
		with self.assertRaises(frappe.ValidationError):
			solicitar(_payload(categoria=""))
		with self.assertRaises(frappe.ValidationError):
			solicitar(_payload(urgencia_informada="Muito"))

	def test_solicitante_nao_escolhe_status_nem_prioridade(self):
		"""Campos de gestão no payload de quem pede são ignorados."""
		self._como(self.membro)
		resposta = solicitar(
			_payload(
				urgencia_informada=c.URGENCIA_PODE_ESPERAR,
				status=c.STATUS_CONCLUIDA,
				prioridade=c.PRIORIDADE_URGENTE,
			)
		)
		frappe.set_user("Administrator")
		doc = frappe.get_doc(c.DOCTYPE, resposta["name"])
		self.assertEqual(doc.status, c.STATUS_RECEBIDA)
		self.assertEqual(doc.prioridade, c.PRIORIDADE_BAIXA)

	def test_rate_limit_por_hora(self):
		self._como(self.membro)
		for _ in range(c.LIMITE_ENVIOS_POR_HORA):
			solicitar(_payload())
		with self.assertRaises(frappe.ValidationError):
			solicitar(_payload())

	# ───────────────────────── acompanhar ─────────────────────────

	def test_acompanhamento_agrupa_por_andamento(self):
		recebida = self._nova()
		planejada = self._nova(status=c.STATUS_PLANEJADA, data_prevista=add_days(nowdate(), 3))
		andamento = self._nova(status=c.STATUS_EM_ANDAMENTO)
		aguardando = self._nova(status=c.STATUS_AGUARDANDO)
		concluida = self._nova(status=c.STATUS_CONCLUIDA)

		self._como(self.membro)
		dados = listar_acompanhamento()

		def nomes(secao):
			return {item["name"] for item in dados[secao]}

		self.assertEqual(nomes("em_analise"), {recebida.name})
		self.assertEqual(nomes("proximas"), {planejada.name})
		self.assertEqual(nomes("em_execucao"), {andamento.name, aguardando.name})
		self.assertEqual(nomes("encerradas"), {concluida.name})

	def test_proximas_seguem_a_data_prevista(self):
		depois = self._nova(
			status=c.STATUS_PLANEJADA,
			data_prevista=add_days(nowdate(), 10),
			prioridade=c.PRIORIDADE_URGENTE,
		)
		antes = self._nova(
			status=c.STATUS_PLANEJADA, data_prevista=add_days(nowdate(), 2), prioridade=c.PRIORIDADE_BAIXA
		)
		sem_data = self._nova(status=c.STATUS_PLANEJADA, prioridade=c.PRIORIDADE_URGENTE)

		self._como(self.membro)
		ordem = [item["name"] for item in listar_acompanhamento()["proximas"]]
		self.assertEqual(ordem, [antes.name, depois.name, sem_data.name])

	def test_acompanhamento_nao_expoe_dados_internos(self):
		doc = self._nova(
			status=c.STATUS_PLANEJADA,
			observacoes_internas="Orçamento do eletricista: R$ 300",
			custo_estimado=300,
			responsavel_execucao="Fulano",
		)
		self._como(self.membro)
		item = listar_acompanhamento()["proximas"][0]
		self.assertEqual(item["name"], doc.name)
		for campo in ("observacoes_internas", "custo_estimado", "solicitante", "solicitante_nome"):
			self.assertNotIn(campo, item)

	def test_resumo_da_execucao_so_aparece_depois_de_encerrada(self):
		doc = self._nova(status=c.STATUS_EM_ANDAMENTO, resumo_execucao="Rascunho")
		self._como(self.membro)
		self.assertEqual(listar_acompanhamento()["em_execucao"][0]["resumo_execucao"], "")

		frappe.set_user("Administrator")
		doc.status = c.STATUS_CONCLUIDA
		doc.resumo_execucao = "Lâmpada trocada."
		doc.save(ignore_permissions=True)
		self._como(self.membro)
		self.assertEqual(listar_acompanhamento()["encerradas"][0]["resumo_execucao"], "Lâmpada trocada.")

	def test_filtro_so_as_minhas(self):
		self._como(self.membro)
		minha = solicitar(_payload())["name"]
		self._como(self.outro)
		solicitar(_payload(titulo="Torneira pingando"))

		self._como(self.membro)
		dados = listar_acompanhamento(somente_minhas="1")
		self.assertEqual([item["name"] for item in dados["em_analise"]], [minha])
		self.assertTrue(dados["em_analise"][0]["eh_minha"])

		todas = listar_acompanhamento()
		self.assertEqual(len(todas["em_analise"]), 2)

	def test_atrasada_e_marcada(self):
		self._nova(status=c.STATUS_PLANEJADA, data_prevista=add_days(nowdate(), -2))
		self._como(self.membro)
		self.assertTrue(listar_acompanhamento()["proximas"][0]["atrasada"])

	def test_guest_nao_acompanha(self):
		self._como("Guest")
		with self.assertRaises(frappe.PermissionError):
			listar_acompanhamento()

	# ───────────────────────── gerir ─────────────────────────

	def test_sem_papel_nao_gerencia(self):
		doc = self._nova()
		self._como(self.membro)
		self.assertFalse(pode_gerir())
		with self.assertRaises(frappe.PermissionError):
			listar_gestao()
		with self.assertRaises(frappe.PermissionError):
			atualizar(doc.name, {"prioridade": c.PRIORIDADE_URGENTE})

	def test_gestor_organiza_a_solicitacao(self):
		doc = self._nova()
		data = add_days(nowdate(), 5)
		self._como(self.gestor)
		resposta = atualizar(
			doc.name,
			{
				"status": c.STATUS_PLANEJADA,
				"prioridade": c.PRIORIDADE_URGENTE,
				"data_prevista": data,
				"responsavel_execucao": "  Mutirão de sábado ",
				"custo_estimado": "150.50",
				"observacoes_internas": "Comprar lâmpada LED",
			},
		)
		self.assertTrue(resposta["alterou"])

		frappe.set_user("Administrator")
		doc.reload()
		self.assertEqual(doc.status, c.STATUS_PLANEJADA)
		self.assertEqual(doc.prioridade, c.PRIORIDADE_URGENTE)
		self.assertEqual(getdate(doc.data_prevista), getdate(data))
		self.assertEqual(doc.responsavel_execucao, "Mutirão de sábado")
		self.assertEqual(float(doc.custo_estimado), 150.5)
		# Campo ausente no payload não é tocado.
		self.assertEqual(doc.urgencia_informada, c.URGENCIA_ATRAPALHA)

	def test_gestor_limpa_a_data_prevista(self):
		doc = self._nova(status=c.STATUS_PLANEJADA, data_prevista=add_days(nowdate(), 5))
		self._como(self.gestor)
		atualizar(doc.name, {"data_prevista": ""})
		frappe.set_user("Administrator")
		doc.reload()
		self.assertFalse(doc.data_prevista)

	def test_atualizar_com_status_invalido_e_recusado(self):
		doc = self._nova()
		self._como(self.gestor)
		with self.assertRaises(frappe.ValidationError):
			atualizar(doc.name, {"status": "Arquivada"})

	def test_atualizar_item_inexistente_nao_gera_404(self):
		"""DoesNotExistError vira o modal do Desk no portal; o throw comum vira toast."""
		self._como(self.gestor)
		with self.assertRaises(frappe.ValidationError) as ctx:
			atualizar("MAN-99999", {"status": c.STATUS_PLANEJADA})
		self.assertNotIsInstance(ctx.exception, frappe.DoesNotExistError)

	def test_gestao_ordena_por_prioridade_e_filtra(self):
		baixa = self._nova(prioridade=c.PRIORIDADE_BAIXA)
		urgente = self._nova(prioridade=c.PRIORIDADE_URGENTE, local="Portão da rua")
		concluida = self._nova(status=c.STATUS_CONCLUIDA)

		self._como(self.gestor)
		dados = listar_gestao()
		self.assertEqual([item["name"] for item in dados["itens"]], [urgente.name, baixa.name])
		self.assertEqual(dados["contagem"][c.STATUS_CONCLUIDA], 1)

		todas = {item["name"] for item in listar_gestao(status="todas")["itens"]}
		self.assertIn(concluida.name, todas)

		busca = listar_gestao(busca="portão")["itens"]
		self.assertEqual([item["name"] for item in busca], [urgente.name])

		filtrada = listar_gestao(prioridade=c.PRIORIDADE_BAIXA)["itens"]
		self.assertEqual([item["name"] for item in filtrada], [baixa.name])

	def test_gestao_conta_atrasadas(self):
		self._nova(status=c.STATUS_PLANEJADA, data_prevista=add_days(nowdate(), -1))
		self._nova(status=c.STATUS_CONCLUIDA, data_prevista=add_days(nowdate(), -1))
		self._como(self.gestor)
		self.assertEqual(listar_gestao()["atrasadas"], 1)

	def test_filtro_invalido_e_recusado(self):
		self._como(self.gestor)
		with self.assertRaises(frappe.ValidationError):
			listar_gestao(status="qualquer")

	# ───────────────────────── portal ─────────────────────────

	def test_rotas_do_modulo_no_portal(self):
		rotas = ("/manutencao", "/manutencao/solicitar", "/manutencao/acompanhamento", "/manutencao/gestao")
		for rota in rotas:
			self.assertIn(rota, PAGE_ROLES)

		grupo = next(item for item in SIDEBAR_STRUCTURE if item["path"] == "/manutencao")
		self.assertEqual(
			[filho["path"] for filho in grupo["children"]],
			["/manutencao/solicitar", "/manutencao/acompanhamento", "/manutencao/gestao"],
		)

		self._como(self.membro)
		self.assertTrue(user_has_access("/manutencao/solicitar"))
		self.assertTrue(user_has_access("/manutencao/acompanhamento"))
		self.assertFalse(user_has_access("/manutencao/gestao"))

		self._como(self.gestor)
		self.assertTrue(user_has_access("/manutencao/gestao"))
