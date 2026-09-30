# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Fluxo da Captação de Recursos: da ideia ao banco de projetos, pela lotação."""

from __future__ import annotations

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from gris.api.captacao import consultas, endpoints
from gris.utils import diretoria

PREFIXO = "ZZ Teste Captacao"
DOMINIO = "captacao.teste.gris"

PRESIDENTE = f"presidente@{DOMINIO}"
DIRETOR = f"diretor@{DOMINIO}"
RI = f"ri@{DOMINIO}"
PROPONENTE = f"proponente@{DOMINIO}"
ESTRANHO = f"estranho@{DOMINIO}"

DETALHAMENTO_COMPLETO = {
	"descricao": "Reformar a cozinha da sede.",
	"publico_alvo": "Os 120 jovens do grupo.",
	"justificativa": "A cozinha atual não atende às normas.",
	"metodologia": "Mutirões com as famílias.",
	"impacto_social": "Espaço aberto também à comunidade.",
	"equipe": [{"nome": "Fulana", "papel": "Coordenação", "apresentacao": "Engenheira civil."}],
	"atividades": [
		{"atividade": "Orçamentos", "dia_inicio": "0", "dia_termino": "10"},
		{"atividade": "Obra", "dia_inicio": 10, "dia_termino": 54, "descricao": "Mutirões"},
	],
	"recursos": [{"categoria": "Material", "descricao": "Azulejos", "quantidade": 40, "valor_unitario": 25}],
}


class TestCaptacaoFluxo(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.area_diretoria = self._criar_area("Diretoria")
		self.area_ri = self._criar_area("Relacoes Institucionais")
		self.funcao_presidente = self._criar_funcao("Presidente", "Eleita")
		self.funcao_diretor = self._criar_funcao("Diretor", "Nomeada")
		self.funcao_equipe = self._criar_funcao("Equipe RI", None)
		self._vincular(self.area_diretoria, self.funcao_presidente)
		self._vincular(self.area_diretoria, self.funcao_diretor)
		self._vincular(self.area_ri, self.funcao_equipe)

		frappe.db.set_single_value("Configuracoes de Captacao", "funcao_presidente", self.funcao_presidente)
		frappe.db.set_single_value("Configuracoes de Captacao", "area_relacoes_institucionais", self.area_ri)
		frappe.db.set_single_value("Configuracoes de Captacao", "somente_presidente_aprova", 0)

		for email in (PRESIDENTE, DIRETOR, RI, PROPONENTE, ESTRANHO):
			self._criar_usuario(email)
		self._criar_associado(PRESIDENTE, self.area_diretoria, self.funcao_presidente)
		self._criar_associado(DIRETOR, self.area_diretoria, self.funcao_diretor)
		self._criar_associado(RI, self.area_ri, self.funcao_equipe)
		self._criar_associado(PROPONENTE)

		self.tipo = f"{PREFIXO} Tipo"
		if not frappe.db.exists("Tipo de Projeto de Captacao", self.tipo):
			frappe.get_doc({"doctype": "Tipo de Projeto de Captacao", "tipo": self.tipo, "ativo": 1}).insert(
				ignore_permissions=True
			)

		self.enfileirar = patch("gris.api.captacao.endpoints.enfileirar_criacao_da_pasta").start()
		self.addCleanup(patch.stopall)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	# ------------------------------------------------------------------
	# Lotação
	# ------------------------------------------------------------------

	def test_papeis_saem_da_lotacao(self):
		self.assertEqual(
			{k: v for k, v in diretoria.papeis_na_diretoria(PRESIDENTE).items() if k != "pessoas"},
			{"membro": True, "presidente": True, "relacoes_institucionais": False},
		)
		self.assertTrue(diretoria.papeis_na_diretoria(DIRETOR)["membro"])
		self.assertFalse(diretoria.papeis_na_diretoria(DIRETOR)["presidente"])
		# Lotado na área de RI numa função que não é da Diretoria: revisa, não aprova.
		self.assertTrue(diretoria.papeis_na_diretoria(RI)["relacoes_institucionais"])
		self.assertFalse(diretoria.papeis_na_diretoria(RI)["membro"])
		self.assertFalse(diretoria.papeis_na_diretoria(PROPONENTE)["membro"])

	def test_funcao_encerrada_nao_conta(self):
		associado = frappe.db.get_value("Associado", {"id_escoteiros": DIRETOR})
		frappe.db.set_value(
			"Funcao do Associado",
			{"parent": associado, "parenttype": "Associado"},
			"data_fim",
			add_days(nowdate(), -1),
		)
		self.assertFalse(diretoria.eh_membro_da_diretoria(DIRETOR))

	# ------------------------------------------------------------------
	# Fluxo
	# ------------------------------------------------------------------

	def test_fluxo_completo_da_ideia_ao_banco(self):
		name = self._nova_ideia()
		self.assertEqual(self._status(name), "Preliminar")

		self._como(DIRETOR, endpoints.decidir_preliminar, name, "Enviar para detalhamento")
		self.assertEqual(self._status(name), "Aprovado inicialmente")
		self.enfileirar.assert_called_once_with(name)

		self._como(PROPONENTE, endpoints.salvar_detalhamento, name, json.dumps({"descricao": "Rascunho"}))
		self.assertEqual(self._status(name), "Em detalhamento")

		with self.assertRaisesRegex(frappe.ValidationError, "Preencha antes de enviar"):
			self._como(PROPONENTE, endpoints.enviar_para_revisao, name)

		self._como(PROPONENTE, endpoints.enviar_para_revisao, name, json.dumps(DETALHAMENTO_COMPLETO))
		self.assertEqual(self._status(name), "Revisão técnica")
		self.assertEqual(frappe.db.get_value("Projeto de Captacao", name, "valor_total"), 1000)

		pedidos = json.dumps([{"secao": "metodologia", "comentario": "Detalhe os mutirões."}])
		self._como(RI, endpoints.solicitar_alteracoes, name, pedidos)
		self.assertEqual(self._status(name), "Em detalhamento")

		with self.assertRaisesRegex(frappe.ValidationError, "pedidos de alteração"):
			self._como(PROPONENTE, endpoints.enviar_para_revisao, name)

		pendencia = frappe.get_doc("Projeto de Captacao", name).pendencias_abertas()[0]
		self.assertEqual(pendencia.secao, "metodologia")
		self._como(PROPONENTE, endpoints.resolver_pendencia, name, pendencia.name)
		self._como(PROPONENTE, endpoints.enviar_para_revisao, name)
		self.assertEqual(self._status(name), "Revisão técnica")

		with self.assertRaisesRegex(frappe.ValidationError, "motivo"):
			self._como(RI, endpoints.alterar_manualmente, name, json.dumps({"metodologia": "Nova"}), "")
		self._como(
			RI,
			endpoints.alterar_manualmente,
			name,
			json.dumps({"metodologia": "Mutirões aos sábados."}),
			"Ajuste de redação",
		)
		manual = frappe.get_doc("Projeto de Captacao", name).decisoes[-1]
		self.assertEqual(manual.decisao, "Alteração manual")
		self.assertEqual(manual.comentario, "Ajuste de redação")
		self.assertEqual(manual.resumo_alteracoes, "Metodologia")

		self._como(RI, endpoints.aprovar_revisao, name)
		self.assertEqual(self._status(name), "Aprovação final")

		self._como(PRESIDENTE, endpoints.decidir_aprovacao_final, name, "Aprovar")
		self.assertEqual(self._status(name), "Pronto para captação")
		self.assertTrue(frappe.db.get_value("Projeto de Captacao", name, "aprovado_final_em"))

		self._como(RI, endpoints.mover_card, name, "Captação em andamento")
		self.assertEqual(self._status(name), "Captação em andamento")
		self._como(DIRETOR, endpoints.mover_card, name, "Captação finalizada")
		self.assertEqual(self._status(name), "Captação finalizada")

	def test_historico_so_registra_o_que_mudou(self):
		"""A RI manda o formulário inteiro; só a metodologia mudou e só ela vai para o histórico."""
		name = self._ate_revisao()
		formulario = {
			**DETALHAMENTO_COMPLETO,
			"objetivos": [{"objetivo": "Cozinha dentro das normas"}],
			"metodologia": "Mutirões aos sábados.",
		}
		# O Frappe não grava `Version` com `in_test` ligado (document.py, `save`).
		with patch.dict(frappe.flags, {"in_test": False}):
			self._como(RI, endpoints.alterar_manualmente, name, json.dumps(formulario), "Ajuste")
		self.assertEqual(consultas.historico_de_versoes(name)[0]["campos"], ["Metodologia"])

	def test_alteracao_manual_sem_mudanca_e_recusada(self):
		name = self._ate_revisao()
		with self.assertRaisesRegex(frappe.ValidationError, "Nenhuma parte"):
			self._como(
				RI,
				endpoints.alterar_manualmente,
				name,
				json.dumps({"metodologia": DETALHAMENTO_COMPLETO["metodologia"]}),
				"Nada",
			)

	def test_diretoria_pede_alteracao_na_ideia_e_proponente_reenvia(self):
		name = self._nova_ideia()
		with self.assertRaisesRegex(frappe.ValidationError, "motivo"):
			self._como(DIRETOR, endpoints.decidir_preliminar, name, "Solicitar alteração", "")
		self._como(DIRETOR, endpoints.decidir_preliminar, name, "Solicitar alteração", "Detalhe o público.")
		self.assertEqual(self._status(name), "Preliminar")
		self.assertEqual(len(frappe.get_doc("Projeto de Captacao", name).pendencias_abertas()), 1)

		self._como(PROPONENTE, endpoints.submeter_ideia, self._payload_ideia(name=name, resumo="Novo resumo"))
		doc = frappe.get_doc("Projeto de Captacao", name)
		self.assertEqual(doc.resumo, "Novo resumo")
		self.assertEqual(doc.pendencias_abertas(), [])

	def test_aprovacao_final_pedindo_alteracao_volta_ao_detalhamento(self):
		name = self._ate_revisao()
		self._como(RI, endpoints.aprovar_revisao, name)
		with self.assertRaisesRegex(frappe.ValidationError, "Justifique"):
			self._como(DIRETOR, endpoints.decidir_aprovacao_final, name, "Solicitar alteração", "")
		self._como(
			DIRETOR, endpoints.decidir_aprovacao_final, name, "Solicitar alteração", "Revisar valores."
		)
		self.assertEqual(self._status(name), "Em detalhamento")

	def test_ideia_que_nao_cabe_encerra_e_nao_volta_pelo_arraste(self):
		name = self._nova_ideia()
		self._como(
			DIRETOR,
			endpoints.decidir_preliminar,
			name,
			"Não cabe em projetos de captação",
			"Vai para eventos.",
		)
		doc = frappe.get_doc("Projeto de Captacao", name)
		self.assertEqual(doc.status, "Cancelado")
		self.assertEqual(doc.categoria_encerramento, "Não cabe em projetos de captação")
		self.assertEqual(doc.motivo_encerramento, "Vai para eventos.")
		self.enfileirar.assert_not_called()

		with self.assertRaisesRegex(frappe.ValidationError, "cancelado antes da aprovação final"):
			self._como(RI, endpoints.mover_card, name, "Pronto para captação")

	def test_arraste_so_entre_colunas_de_captacao(self):
		name = self._ate_revisao()
		with self.assertRaisesRegex(frappe.ValidationError, "Só é possível arrastar"):
			self._como(RI, endpoints.mover_card, name, "Pronto para captação")

	def test_acao_fora_do_status_e_recusada(self):
		name = self._nova_ideia()
		with self.assertRaisesRegex(frappe.ValidationError, "Ação indisponível"):
			self._como(RI, endpoints.aprovar_revisao, name)

	# ------------------------------------------------------------------
	# Quem pode
	# ------------------------------------------------------------------

	def test_somente_presidente_aprova_quando_configurado(self):
		frappe.db.set_single_value("Configuracoes de Captacao", "somente_presidente_aprova", 1)
		name = self._nova_ideia()
		with self.assertRaises(frappe.PermissionError):
			self._como(DIRETOR, endpoints.decidir_preliminar, name, "Enviar para detalhamento")
		self._como(PRESIDENTE, endpoints.decidir_preliminar, name, "Enviar para detalhamento")
		self.assertEqual(self._status(name), "Aprovado inicialmente")

	def test_quem_nao_e_da_diretoria_nao_decide_nem_revisa(self):
		name = self._nova_ideia()
		for user in (PROPONENTE, RI, ESTRANHO):
			with self.assertRaises(frappe.PermissionError):
				self._como(user, endpoints.decidir_preliminar, name, "Enviar para detalhamento")
		name_revisao = self._ate_revisao()
		for user in (PROPONENTE, DIRETOR):
			with self.assertRaises(frappe.PermissionError):
				self._como(user, endpoints.aprovar_revisao, name_revisao)

	def test_so_o_proponente_detalha(self):
		name = self._nova_ideia()
		self._como(DIRETOR, endpoints.decidir_preliminar, name, "Enviar para detalhamento")
		for user in (ESTRANHO, DIRETOR):
			with self.assertRaises(frappe.PermissionError):
				self._como(user, endpoints.salvar_detalhamento, name, json.dumps({"descricao": "x"}))

	def test_proponente_nao_move_cards(self):
		name = self._ate_revisao()
		self._como(RI, endpoints.aprovar_revisao, name)
		self._como(DIRETOR, endpoints.decidir_aprovacao_final, name, "Aprovar")
		with self.assertRaises(frappe.PermissionError):
			self._como(PROPONENTE, endpoints.mover_card, name, "Captação em andamento")

	def test_visibilidade(self):
		name = self._nova_ideia()
		with self.assertRaises(frappe.PermissionError):
			self._como(ESTRANHO, endpoints.obter_projeto, name)

		def nomes(user):
			kanban = self._como(user, endpoints.listar_kanban)
			return {card["name"] for coluna in kanban["colunas"] for card in coluna["cards"]}

		self.assertIn(name, nomes(PROPONENTE))
		self.assertIn(name, nomes(RI))
		self.assertIn(name, nomes(DIRETOR))
		self.assertNotIn(name, nomes(ESTRANHO))

	# ------------------------------------------------------------------
	# Proponente
	# ------------------------------------------------------------------

	def test_proponente_e_quem_envia_a_ideia(self):
		name = self._nova_ideia()
		doc = frappe.get_doc("Projeto de Captacao", name)
		associado = frappe.db.get_value("Associado", {"id_escoteiros": PROPONENTE})
		self.assertEqual(doc.proponente_user, PROPONENTE)
		self.assertEqual(doc.proponente_tipo, "Associado")
		self.assertEqual(doc.proponente_associado, associado)
		self.assertEqual(doc.proponente_nome, frappe.db.get_value("Associado", associado, "nome_completo"))
		# A página do projeto mostra quem propôs e quando.
		serializado = self._como(DIRETOR, endpoints.obter_projeto, name)["projeto"]
		self.assertEqual(serializado["proponente"]["nome"], doc.proponente_nome)
		self.assertEqual(serializado["proponente"]["tipo_rotulo"], "Associado")
		self.assertTrue(serializado["criado_em"])

	def test_proponente_vem_da_sessao_mesmo_fora_do_portal(self):
		"""Criado pelo Desk ou pela API, o proponente continua sendo quem criou."""
		frappe.set_user(DIRETOR)
		doc = frappe.get_doc(
			{
				"doctype": "Projeto de Captacao",
				"titulo": f"{PREFIXO} Pelo Desk",
				"resumo": "x",
				"tipo_projeto": self.tipo,
				"objetivos": [{"objetivo": "y"}],
				"proponente_user": PROPONENTE,
			}
		).insert(ignore_permissions=True)
		frappe.set_user("Administrator")
		self.assertEqual(doc.proponente_user, DIRETOR)

	def test_proponente_nao_pode_ser_trocado(self):
		name = self._nova_ideia()
		doc = frappe.get_doc("Projeto de Captacao", name)
		doc.proponente_user = DIRETOR
		with self.assertRaisesRegex(frappe.ValidationError, "proponente"):
			doc.save(ignore_permissions=True)

	# ------------------------------------------------------------------
	# Atividades e cronograma (Gantt)
	# ------------------------------------------------------------------

	def test_cronograma_e_gravado_em_dias_do_projeto(self):
		name = self._ate_revisao()
		doc = frappe.get_doc("Projeto de Captacao", name)
		periodos = [(a.atividade, a.dia_inicio, a.dia_termino) for a in doc.atividades]
		self.assertEqual(periodos, [("Orçamentos", 0, 10), ("Obra", 10, 54)])
		serializado = self._como(PROPONENTE, endpoints.obter_projeto, name)["projeto"]["atividades"]
		self.assertEqual((serializado[1]["dia_inicio"], serializado[1]["dia_termino"]), (10, 54))
		self.assertEqual(serializado[1]["descricao"], "Mutirões")

	def test_rascunho_aceita_dias_em_branco_mas_o_envio_cobra(self):
		name = self._nova_ideia()
		self._como(DIRETOR, endpoints.decidir_preliminar, name, "Enviar para detalhamento")
		sem_dias = {"atividades": [{"atividade": "Orçamentos", "dia_inicio": "", "dia_termino": ""}]}
		self._como(PROPONENTE, endpoints.salvar_detalhamento, name, json.dumps(sem_dias))
		completo_sem_dias = {**DETALHAMENTO_COMPLETO, **sem_dias}
		with self.assertRaisesRegex(frappe.ValidationError, "Atividades e cronograma"):
			self._como(PROPONENTE, endpoints.enviar_para_revisao, name, json.dumps(completo_sem_dias))

	def test_dias_invalidos_sao_recusados(self):
		name = self._nova_ideia()
		self._como(DIRETOR, endpoints.decidir_preliminar, name, "Enviar para detalhamento")
		for atividade, erro in (
			({"atividade": "Obra", "dia_inicio": "54", "dia_termino": "10"}, "termina antes de começar"),
			({"atividade": "Obra", "dia_inicio": "-1", "dia_termino": "10"}, "começa no dia 0"),
			({"atividade": "Obra", "dia_inicio": "dez", "dia_termino": "10"}, "número inteiro"),
			({"atividade": "Obra", "dia_inicio": "0", "dia_termino": "9999"}, "vai até o dia"),
		):
			with self.subTest(atividade=atividade):
				with self.assertRaisesRegex(frappe.ValidationError, erro):
					self._como(
						PROPONENTE,
						endpoints.salvar_detalhamento,
						name,
						json.dumps({"atividades": [atividade]}),
					)

	def test_ri_altera_o_cronograma_com_motivo(self):
		name = self._ate_revisao()
		novo = [{"atividade": "Orçamentos", "dia_inicio": 0, "dia_termino": 20}]
		self._como(RI, endpoints.alterar_manualmente, name, json.dumps({"atividades": novo}), "Prazo real")
		ultima = frappe.get_doc("Projeto de Captacao", name).decisoes[-1]
		self.assertEqual(
			(ultima.decisao, ultima.resumo_alteracoes), ("Alteração manual", "Atividades e cronograma")
		)

	# ------------------------------------------------------------------
	# Comentários
	# ------------------------------------------------------------------

	def test_comentario_so_o_autor_edita_e_apaga(self):
		name = self._nova_ideia()
		resposta = self._como(PROPONENTE, endpoints.comentar, name, "Primeira versão <b>ok</b>")
		comentario = resposta["comentarios"][0]
		self.assertEqual(comentario["texto"], "Primeira versão <b>ok</b>")
		self.assertTrue(comentario["pode_editar"])

		visto_pelo_diretor = self._como(DIRETOR, endpoints.listar_comentarios, name)["comentarios"][0]
		self.assertFalse(visto_pelo_diretor["pode_editar"])
		with self.assertRaises(frappe.PermissionError):
			self._como(DIRETOR, endpoints.editar_comentario, name, comentario["name"], "Mudei")
		with self.assertRaises(frappe.PermissionError):
			self._como(DIRETOR, endpoints.apagar_comentario, name, comentario["name"])
		with self.assertRaises(frappe.PermissionError):
			self._como(ESTRANHO, endpoints.comentar, name, "Oi")

		editado = self._como(PROPONENTE, endpoints.editar_comentario, name, comentario["name"], "Segunda")
		self.assertEqual(editado["comentarios"][0]["texto"], "Segunda")
		self.assertEqual(
			self._como(PROPONENTE, endpoints.apagar_comentario, name, comentario["name"])["comentarios"], []
		)

	# ------------------------------------------------------------------
	# Apoio
	# ------------------------------------------------------------------

	def _como(self, user, metodo, *args):
		frappe.set_user(user)
		try:
			return metodo(*args)
		finally:
			frappe.set_user("Administrator")

	def _status(self, name):
		return frappe.db.get_value("Projeto de Captacao", name, "status")

	def _payload_ideia(self, **extra):
		dados = {
			"titulo": f"{PREFIXO} Cozinha",
			"resumo": "Reformar a cozinha.",
			"tipo_projeto": self.tipo,
			"objetivos": [{"objetivo": "Cozinha dentro das normas"}],
		}
		dados.update(extra)
		return json.dumps(dados)

	def _nova_ideia(self):
		return self._como(PROPONENTE, endpoints.submeter_ideia, self._payload_ideia())["projeto"]["name"]

	def _ate_revisao(self):
		name = self._nova_ideia()
		self._como(DIRETOR, endpoints.decidir_preliminar, name, "Enviar para detalhamento")
		self._como(PROPONENTE, endpoints.enviar_para_revisao, name, json.dumps(DETALHAMENTO_COMPLETO))
		return name

	def _criar_usuario(self, email):
		if frappe.db.exists("User", email):
			return
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)

	def _criar_area(self, sufixo):
		nome = f"{PREFIXO} {sufixo}"
		if not frappe.db.exists("Unidade Organizacional", nome):
			frappe.get_doc({"doctype": "Unidade Organizacional", "area": nome}).insert(
				ignore_permissions=True
			)
		return nome

	def _criar_funcao(self, sufixo, tipo_diretoria):
		titulo = f"{PREFIXO} {sufixo}"
		if not frappe.db.exists("Funcao Voluntario", titulo):
			frappe.get_doc(
				{
					"doctype": "Funcao Voluntario",
					"titulo": titulo,
					"categoria": "Dirigente",
					"diretoria": tipo_diretoria,
					"ativa": 1,
				}
			).insert(ignore_permissions=True)
		return titulo

	def _vincular(self, area, funcao):
		doc = frappe.get_doc("Unidade Organizacional", area)
		if not any(linha.funcao == funcao for linha in doc.funcoes):
			doc.append("funcoes", {"funcao": funcao})
			doc.save(ignore_permissions=True)

	def _criar_associado(self, email, area=None, funcao=None):
		doc = frappe.get_doc(
			{
				"doctype": "Associado",
				"nome_completo": f"{PREFIXO} {email.split('@')[0]}",
				"cpf": frappe.generate_hash(length=32),
				"data_de_nascimento": "1990-01-01",
				"categoria": "Dirigente",
				"status_no_grupo": "Ativo",
				"historico_no_grupo": [{"data_de_ingresso": "2020-01-01"}],
			}
		)
		if funcao:
			doc.append("funcoes_internas", {"funcao": funcao, "area": area, "data_inicio": "2025-01-01"})
		doc.insert(ignore_permissions=True)
		# Direto no banco: gravar `id_escoteiros` pelo documento dispara a criação do
		# usuário do associado, que aqui já existe.
		frappe.db.set_value("Associado", doc.name, "id_escoteiros", email, update_modified=False)
		return doc.name
