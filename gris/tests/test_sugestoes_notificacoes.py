# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Testes dos avisos por WhatsApp do módulo Sugestões e Problemas."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.sugestoes import constantes as c
from gris.api.sugestoes import notificacoes
from gris.api.sugestoes.portal import submeter_solicitacao
from gris.gestao_de_tarefas.board_sync_sugestoes import ensure_board_desenvolvimento
from gris.utils.contato import telefone_do_usuario

GRUPO_JID = "120363408543428156@g.us"

SOLICITANTE_EMAIL = "solicitante.avisos@teste.gris"
SEM_TELEFONE_EMAIL = "sem.telefone.avisos@teste.gris"
ASSOCIADO_EMAIL = "associado.avisos@teste.gris"


def _criar_user(email: str, *, mobile_no: str = "") -> str:
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
		user.enabled = 1
		# `mobile_no` é UNIQUE em tabUser: gravar "" repetido colide entre usuários.
		user.mobile_no = mobile_no or None
		user.save(ignore_permissions=True)
		return email

	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": email.split(".")[0].capitalize(),
			"last_name": "da Silva",
			"send_welcome_email": 0,
			"mobile_no": mobile_no or None,
		}
	)
	user.insert(ignore_permissions=True)
	return user.name


def _criar_desenvolvedor(email: str, *, mobile_no: str = "") -> str:
	"""Usuário com o papel Desenvolvedor — único aceito no campo `responsavel`."""
	if not frappe.db.exists("Role", c.ROLE_DESENVOLVEDOR):
		frappe.get_doc({"doctype": "Role", "role_name": c.ROLE_DESENVOLVEDOR, "desk_access": 0}).insert(
			ignore_permissions=True
		)

	user = _criar_user(email, mobile_no=mobile_no)
	user_doc = frappe.get_doc("User", user)
	if c.ROLE_DESENVOLVEDOR not in {linha.role for linha in user_doc.roles}:
		user_doc.append("roles", {"role": c.ROLE_DESENVOLVEDOR})
		user_doc.save(ignore_permissions=True)
	return user


class TestSugestoesNotificacoes(FrappeTestCase):
	def setUp(self):
		self.solicitante = _criar_user(SOLICITANTE_EMAIL, mobile_no="+5511988887777")
		self.sem_telefone = _criar_user(SEM_TELEFONE_EMAIL)

		self.grupos: list[dict] = []
		self.textos: list[dict] = []

		self._originais = {
			"enviar_para_grupo": notificacoes.enviar_para_grupo,
			"enviar_texto": notificacoes.enviar_texto,
			"_avisos_habilitados": notificacoes._avisos_habilitados,
			"_grupo_desenvolvimento": notificacoes._grupo_desenvolvimento,
		}

		notificacoes.enviar_para_grupo = self._fake_grupo
		notificacoes.enviar_texto = self._fake_texto
		notificacoes._avisos_habilitados = lambda: True
		notificacoes._grupo_desenvolvimento = lambda: GRUPO_JID

	def tearDown(self):
		for nome, original in self._originais.items():
			setattr(notificacoes, nome, original)

		# FrappeTestCase só faz rollback por classe: sem isto os User criados aqui
		# vazam para o próximo teste e quebram com DuplicateEntryError.
		frappe.db.rollback()

	def _fake_grupo(self, grupo_jid, mensagem, *, mencionar_todos=False, mencionar=None, enqueue=True):
		self.grupos.append({"grupo_jid": grupo_jid, "mensagem": mensagem, "mencionar_todos": mencionar_todos})

	def _fake_texto(self, numero, mensagem, *, enqueue=True):
		self.textos.append({"numero": numero, "mensagem": mensagem})

	def _nova(self, **kwargs):
		dados = {
			"doctype": "Sugestao ou Problema",
			"titulo": "Erro ao salvar contribuição",
			"tipo": c.TIPO_PROBLEMA,
			"modulo": "Financeiro",
			"descricao": "<p>Ao clicar em salvar aparece uma tela branca.</p>",
			"solicitante": self.solicitante,
		}
		dados.update(kwargs)
		return frappe.get_doc(dados).insert(ignore_permissions=True)

	def _concluir(self, doc):
		doc.status = c.COLUNA_CONCLUIDO
		doc.save(ignore_permissions=True)
		doc.reload()
		return doc

	# ───────────────────── aviso ao grupo (nova solicitação) ─────────────────────

	def test_nova_solicitacao_avisa_o_grupo_com_todos_os_campos(self):
		doc = self._nova()

		self.assertEqual(len(self.grupos), 1)
		envio = self.grupos[0]
		self.assertEqual(envio["grupo_jid"], GRUPO_JID)
		self.assertTrue(envio["mencionar_todos"])

		mensagem = envio["mensagem"]
		self.assertIn("@todos", mensagem)
		self.assertIn(doc.solicitante_nome, mensagem)
		self.assertIn(c.TIPO_PROBLEMA, mensagem)
		self.assertIn("Financeiro", mensagem)
		self.assertIn("Erro ao salvar contribuição", mensagem)
		self.assertIn("tela branca", mensagem)
		self.assertIn(f"?item={doc.name}", mensagem)

		doc.reload()
		self.assertTrue(doc.aviso_grupo_enviado_em)

	def test_grupo_nao_configurado_nao_envia_nada(self):
		notificacoes._grupo_desenvolvimento = lambda: ""

		doc = self._nova()

		self.assertEqual(self.grupos, [])
		doc.reload()
		self.assertFalse(doc.aviso_grupo_enviado_em)

	def test_avisos_desabilitados_nao_enviam_nada(self):
		notificacoes._avisos_habilitados = lambda: False

		doc = self._nova()
		self._concluir(doc)

		self.assertEqual(self.grupos, [])
		self.assertEqual(self.textos, [])

	def test_descricao_html_vira_texto_puro_e_trunca(self):
		paragrafo = "a" * 400
		self._nova(descricao=f"<p>{paragrafo}</p><p>{paragrafo}</p>")

		mensagem = self.grupos[0]["mensagem"]
		self.assertNotIn("<p>", mensagem)
		self.assertIn("...", mensagem)
		# O limite vale para a descrição, não para a mensagem inteira.
		self.assertNotIn("a" * (notificacoes.DESCRICAO_RESUMO_MAX + 1), mensagem)

	# ───────────────────── aviso de conclusão (solicitante) ─────────────────────

	def test_conclusao_avisa_o_solicitante_no_formato_pedido(self):
		doc = self._nova()
		self._concluir(doc)

		self.assertEqual(len(self.textos), 1)
		envio = self.textos[0]
		self.assertEqual(envio["numero"], "+5511988887777")

		mensagem = envio["mensagem"]
		self.assertTrue(mensagem.startswith("Olá, Solicitante!"))
		self.assertIn("Vim falar da sua solicitação:", mensagem)
		self.assertIn("Erro ao salvar contribuição", mensagem)
		self.assertIn("Ela já foi implementada!", mensagem)
		self.assertIn("_Esta é uma mensagem automática_", mensagem)

		doc.reload()
		self.assertTrue(doc.aviso_conclusao_enviado_em)

	def test_sem_opt_in_nao_avisa_na_conclusao(self):
		doc = self._nova(avisar_por_whatsapp=0)
		self._concluir(doc)

		self.assertEqual(self.textos, [])

	def test_solicitante_sem_telefone_nao_recebe_e_nao_quebra(self):
		doc = self._nova(solicitante=self.sem_telefone)
		# O `before_insert` desliga a promessa que não tem como cumprir.
		self.assertFalse(doc.avisar_por_whatsapp)
		self.assertFalse(doc.telefone_aviso)

		self._concluir(doc)
		self.assertEqual(self.textos, [])

	def test_nao_reenvia_ao_salvar_de_novo_ja_concluido(self):
		doc = self._nova()
		self._concluir(doc)
		self.assertEqual(len(self.textos), 1)

		doc.titulo = "Erro ao salvar contribuição mensal"
		doc.save(ignore_permissions=True)

		self.assertEqual(len(self.textos), 1)

	def test_reabrir_e_concluir_de_novo_nao_reenvia(self):
		doc = self._nova()
		self._concluir(doc)
		self.assertEqual(len(self.textos), 1)

		doc.status = c.COLUNA_EM_DESENVOLVIMENTO
		doc.save(ignore_permissions=True)
		doc.reload()

		self._concluir(doc)
		self.assertEqual(len(self.textos), 1)

	def test_mudanca_de_status_que_nao_e_conclusao_nao_avisa(self):
		doc = self._nova()
		doc.status = c.COLUNA_EM_DESENVOLVIMENTO
		doc.save(ignore_permissions=True)

		self.assertEqual(self.textos, [])

	# ───────────────────────── resolução de telefone ─────────────────────────

	def test_telefone_cai_no_associado_quando_o_user_nao_tem_mobile_no(self):
		user = _criar_user(ASSOCIADO_EMAIL)
		frappe.get_doc(
			{
				"doctype": "Associado",
				"cpf": "39053344705",
				"nome_completo": "Associado de Teste",
				"data_de_nascimento": "2000-01-01",
				"categoria": "Beneficiário",
				"status_no_grupo": "Ativo",
				"id_escoteiros": user,
				"telefone": "+5511977776666",
			}
		).insert(ignore_permissions=True)

		self.assertEqual(telefone_do_usuario(user), "+5511977776666")

		doc = self._nova(solicitante=user)
		self.assertEqual(doc.telefone_aviso, "+5511977776666")

		self._concluir(doc)
		self.assertEqual(self.textos[0]["numero"], "+5511977776666")

	def test_telefone_do_usuario_sem_cadastro_nenhum_volta_vazio(self):
		self.assertEqual(telefone_do_usuario(self.sem_telefone), "")
		self.assertEqual(telefone_do_usuario("Guest"), "")
		self.assertEqual(telefone_do_usuario(""), "")

	# ───────────────────────── endpoint do portal ─────────────────────────

	def _submeter(self, **extras):
		frappe.set_user(self.solicitante)
		self.addCleanup(frappe.set_user, "Administrator")

		payload = {
			"tipo": c.TIPO_PROBLEMA,
			"modulo": "Financeiro",
			"titulo": "Erro ao salvar contribuição",
			"descricao": "<p>Tela branca ao salvar.</p>",
		}
		payload.update(extras)
		return submeter_solicitacao(payload)

	def test_endpoint_respeita_o_opt_in_desmarcado(self):
		resposta = self._submeter(avisar_por_whatsapp=False)

		self.assertFalse(resposta["avisar_por_whatsapp"])
		self.assertFalse(frappe.db.get_value("Sugestao ou Problema", resposta["name"], "avisar_por_whatsapp"))

	def test_endpoint_aceita_o_opt_in_como_booleano_ou_string(self):
		"""O `frappe.call` da página manda booleano JSON; um cliente na mão, string."""
		por_booleano = self._submeter(avisar_por_whatsapp=True)
		por_string = self._submeter(avisar_por_whatsapp="true")
		omitido = self._submeter()

		for resposta in (por_booleano, por_string, omitido):
			self.assertTrue(resposta["avisar_por_whatsapp"])

	# ────────────────── conclusão vinda da tarefa espelho ──────────────────

	# ───────────────────────── aviso de comentário ─────────────────────────

	def _comentar(self, doc, texto: str, autor: str) -> None:
		frappe.get_doc(
			{
				"doctype": "Comment",
				"comment_type": "Comment",
				"reference_doctype": "Sugestao ou Problema",
				"reference_name": doc.name,
				"content": texto,
				"comment_email": autor,
				"comment_by": autor,
			}
		).insert(ignore_permissions=True)

	def test_comentario_de_terceiro_avisa_solicitante_e_responsavel(self):
		responsavel = _criar_desenvolvedor("responsavel.avisos@teste.gris", mobile_no="+5511977778888")
		terceiro = _criar_user("terceiro.avisos@teste.gris", mobile_no="+5511966665555")

		doc = self._nova()
		doc.responsavel = responsavel
		doc.save(ignore_permissions=True)
		doc.reload()

		self._comentar(doc, "Já comecei a olhar isso.", terceiro)

		self.assertEqual(len(self.textos), 2)
		numeros = {envio["numero"] for envio in self.textos}
		self.assertEqual(numeros, {"+5511988887777", "+5511977778888"})
		self.assertIn("Já comecei a olhar isso.", self.textos[0]["mensagem"])

	def test_comentario_do_proprio_solicitante_nao_avisa_ele_mesmo(self):
		responsavel = _criar_desenvolvedor("responsavel2.avisos@teste.gris", mobile_no="+5511977778888")

		doc = self._nova()
		doc.responsavel = responsavel
		doc.save(ignore_permissions=True)
		doc.reload()

		self._comentar(doc, "Só complementando o relato.", self.solicitante)

		self.assertEqual(len(self.textos), 1)
		self.assertEqual(self.textos[0]["numero"], "+5511977778888")

	def test_comentario_do_responsavel_nao_avisa_ele_mesmo(self):
		responsavel = _criar_desenvolvedor("responsavel3.avisos@teste.gris", mobile_no="+5511977778888")

		doc = self._nova()
		doc.responsavel = responsavel
		doc.save(ignore_permissions=True)
		doc.reload()

		self._comentar(doc, "Já já resolvo.", responsavel)

		self.assertEqual(len(self.textos), 1)
		self.assertEqual(self.textos[0]["numero"], "+5511988887777")

	def test_comentario_sem_responsavel_avisa_so_o_solicitante(self):
		doc = self._nova()

		self._comentar(doc, "Alguém vai olhar em breve.", "terceiro.sem.role@teste.gris")

		self.assertEqual(len(self.textos), 1)
		self.assertEqual(self.textos[0]["numero"], "+5511988887777")

	def test_avisos_desabilitados_nao_avisam_no_comentario(self):
		notificacoes._avisos_habilitados = lambda: False

		doc = self._nova()
		self._comentar(doc, "Comentário qualquer.", "terceiro.sem.role@teste.gris")

		self.assertEqual(self.textos, [])

	def test_comentario_de_outro_tipo_nao_dispara_aviso(self):
		"""Um `comment_type` diferente de "Comment" (ex.: log automático) não é um recado."""
		doc = self._nova()

		frappe.get_doc(
			{
				"doctype": "Comment",
				"comment_type": "Info",
				"reference_doctype": "Sugestao ou Problema",
				"reference_name": doc.name,
				"content": "Status alterado.",
				"comment_email": "sistema@teste.gris",
			}
		).insert(ignore_permissions=True)

		self.assertEqual(self.textos, [])

	def test_conclusao_pela_tarefa_espelho_tambem_avisa(self):
		"""O dev marca a tarefa como concluída em "Minhas tarefas", não no quadro.

		O sync reverso salva a solicitação, então o mesmo `on_update` cobre este
		caminho — é a razão de o aviso não morar no endpoint do kanban.
		"""
		if not frappe.db.exists("Role", c.ROLE_DESENVOLVEDOR):
			frappe.get_doc({"doctype": "Role", "role_name": c.ROLE_DESENVOLVEDOR, "desk_access": 0}).insert(
				ignore_permissions=True
			)

		dev = _criar_user("dev.avisos@teste.gris")
		dev_doc = frappe.get_doc("User", dev)
		if c.ROLE_DESENVOLVEDOR not in {linha.role for linha in dev_doc.roles}:
			dev_doc.append("roles", {"role": c.ROLE_DESENVOLVEDOR})
			dev_doc.save(ignore_permissions=True)

		ensure_board_desenvolvimento()

		doc = self._nova()
		doc.responsavel = dev
		doc.save(ignore_permissions=True)
		doc.reload()
		self.assertTrue(doc.tarefa)

		tarefa = frappe.get_doc("Gestao de Tarefas", doc.tarefa)
		tarefa.status = c.TAREFA_CONCLUIDO
		tarefa.save(ignore_permissions=True)

		doc.reload()
		self.assertEqual(doc.status, c.COLUNA_CONCLUIDO)
		self.assertEqual(len(self.textos), 1)
		self.assertIn("Ela já foi implementada!", self.textos[0]["mensagem"])
