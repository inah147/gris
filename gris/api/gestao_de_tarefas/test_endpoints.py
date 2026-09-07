# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Testes de excluir tarefa e do filtro server-side "ocultar concluidos"
(SUG-00027) para os quadros pessoal e de projeto/solto de Gestao de Tarefas."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.gestao_de_tarefas.minhas_tarefas import (
	_ensure_board_pessoal,
	_listar_tarefas_do_usuario,
	excluir_tarefa_pessoal,
)
from gris.api.gestao_de_tarefas.quadros import (
	_listar_tarefas_do_quadro,
	excluir_tarefa_quadro,
)

EDITOR_EMAIL = "editor.tarefas@teste.gris"
VIEWER_EMAIL = "visualizador.tarefas@teste.gris"
OUTSIDER_EMAIL = "fora.tarefas@teste.gris"


def _criar_user(email: str) -> str:
	# Em producao todo usuario recebe "Visualizador de projetos" e "Editor de
	# projetos" via patch (add_project_roles_to_all_users); sem elas, o `Board`
	# nega leitura antes mesmo do hook de membro entrar em jogo.
	roles = ["Visualizador de projetos", "Editor de projetos"]
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
		user.enabled = 1
		user.set("roles", [])
		for role in roles:
			user.append("roles", {"role": role})
		user.save(ignore_permissions=True)
		return email

	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": email.split("@")[0],
			"send_welcome_email": 0,
			"user_type": "System User",
			"roles": [{"role": role} for role in roles],
		}
	)
	user.insert(ignore_permissions=True)
	return user.name


def _criar_tarefa(board: str, descricao: str, status: str = "Nao iniciado", **kwargs) -> str:
	dados = {
		"doctype": "Gestao de Tarefas",
		"board": board,
		"descricao": descricao,
		"status": status,
	}
	dados.update(kwargs)
	return frappe.get_doc(dados).insert(ignore_permissions=True).name


class TestExcluirTarefaEOcultarConcluidos(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.editor = _criar_user(EDITOR_EMAIL)
		cls.viewer = _criar_user(VIEWER_EMAIL)
		cls.outsider = _criar_user(OUTSIDER_EMAIL)
		# FrappeTestCase reverte cada teste ate um savepoint criado antes desta
		# classe rodar; sem commitar aqui, os usuarios de fixture somem depois do
		# primeiro teste (mesmo padrao usado em tests/test_sugestoes.py).
		frappe.db.commit()  # nosemgrep: frappe-manual-commit

	def setUp(self):
		self.usuario_original = frappe.session.user
		self.quadro = frappe.get_doc(
			{
				"doctype": "Board",
				"titulo": "Quadro de teste — excluir tarefa",
				"ativo": 1,
				"usuarios_autorizados": [
					{"user": self.editor, "nivel_acesso": "Editar"},
					{"user": self.viewer, "nivel_acesso": "Visualizar"},
				],
			}
		).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user(self.usuario_original)
		# FrappeTestCase so faz rollback por classe: sem isto os documentos de um
		# teste vazam para o proximo e quebram com DuplicateEntryError.
		frappe.db.rollback()

	# ───────────────────────── filtro "ocultar concluidos" ─────────────────────────

	def test_listar_tarefas_do_quadro_oculta_concluidos_quando_pedido(self):
		_criar_tarefa(self.quadro.name, "Tarefa aberta")
		_criar_tarefa(self.quadro.name, "Tarefa concluida", status="Concluido")

		todas = _listar_tarefas_do_quadro(self.quadro.name)
		self.assertEqual(len(todas), 2)

		abertas = _listar_tarefas_do_quadro(self.quadro.name, ocultar_concluidos=True)
		self.assertEqual([t["descricao"] for t in abertas], ["Tarefa aberta"])

	def test_listar_tarefas_do_usuario_oculta_concluidos_quando_pedido(self):
		board_pessoal = _ensure_user_board_para(self.editor)
		_criar_tarefa(board_pessoal, "Pessoal aberta", responsavel=self.editor)
		_criar_tarefa(board_pessoal, "Pessoal concluida", status="Concluido", responsavel=self.editor)

		todas = _listar_tarefas_do_usuario(self.editor, apenas_urgentes=False)
		self.assertEqual(len(todas), 2)

		abertas = _listar_tarefas_do_usuario(self.editor, apenas_urgentes=False, ocultar_concluidos=True)
		self.assertEqual([t["descricao"] for t in abertas], ["Pessoal aberta"])

	# ───────────────────────── excluir_tarefa_quadro ─────────────────────────

	def test_excluir_tarefa_quadro_membro_editor_consegue_excluir(self):
		tarefa_name = _criar_tarefa(self.quadro.name, "Para excluir")
		frappe.set_user(self.editor)

		resultado = excluir_tarefa_quadro(tarefa_name)

		self.assertTrue(resultado["ok"])
		self.assertFalse(frappe.db.exists("Gestao de Tarefas", tarefa_name))
		self.assertNotIn(tarefa_name, [t["name"] for t in resultado["tarefas"]])

	def test_excluir_tarefa_quadro_visualizador_e_bloqueado(self):
		tarefa_name = _criar_tarefa(self.quadro.name, "Protegida")
		frappe.set_user(self.viewer)

		with self.assertRaises(frappe.PermissionError):
			excluir_tarefa_quadro(tarefa_name)
		self.assertTrue(frappe.db.exists("Gestao de Tarefas", tarefa_name))

	def test_excluir_tarefa_quadro_nao_membro_e_bloqueado(self):
		tarefa_name = _criar_tarefa(self.quadro.name, "Fora do quadro")
		frappe.set_user(self.outsider)

		with self.assertRaises(frappe.PermissionError):
			excluir_tarefa_quadro(tarefa_name)
		self.assertTrue(frappe.db.exists("Gestao de Tarefas", tarefa_name))

	def test_excluir_tarefa_quadro_tarefa_inexistente_lanca_erro(self):
		frappe.set_user(self.editor)
		with self.assertRaises(frappe.ValidationError):
			excluir_tarefa_quadro("TAR-INEXISTENTE-0001")

	# ───────────────────────── excluir_tarefa_pessoal ─────────────────────────

	def test_excluir_tarefa_pessoal_apaga_tarefa_do_board_pessoal(self):
		frappe.set_user(self.editor)
		board_pessoal = _ensure_user_board_para(self.editor)
		tarefa_name = _criar_tarefa(board_pessoal, "Minha tarefa", responsavel=self.editor)

		resultado = excluir_tarefa_pessoal(tarefa_name)

		self.assertTrue(resultado["ok"])
		self.assertFalse(frappe.db.exists("Gestao de Tarefas", tarefa_name))

	def test_excluir_tarefa_pessoal_bloqueia_quando_nao_e_responsavel(self):
		board_pessoal = _ensure_user_board_para(self.editor)
		tarefa_name = _criar_tarefa(board_pessoal, "Tarefa do editor", responsavel=self.editor)
		frappe.set_user(self.viewer)

		with self.assertRaises(frappe.PermissionError):
			excluir_tarefa_pessoal(tarefa_name)
		self.assertTrue(frappe.db.exists("Gestao de Tarefas", tarefa_name))

	def test_excluir_tarefa_pessoal_bloqueia_tarefa_de_quadro_compartilhado(self):
		# Tarefa de um quadro de projeto/solto atribuida ao editor: aparece na
		# visao "Minhas tarefas" dele, mas so pode ser excluida pelo quadro
		# (onde o nivel de acesso e checado), nao por aqui.
		tarefa_name = _criar_tarefa(self.quadro.name, "Tarefa do quadro atribuida a mim", responsavel=self.editor)
		frappe.set_user(self.editor)

		with self.assertRaises(frappe.PermissionError):
			excluir_tarefa_pessoal(tarefa_name)
		self.assertTrue(frappe.db.exists("Gestao de Tarefas", tarefa_name))


def _ensure_user_board_para(user: str) -> str:
	usuario_original = frappe.session.user
	frappe.set_user(user)
	try:
		return _ensure_board_pessoal(user)
	finally:
		frappe.set_user(usuario_original)
