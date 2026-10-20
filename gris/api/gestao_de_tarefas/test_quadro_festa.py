# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Permissao do quadro de tarefas da festa: qualquer usuario logado le, mas so
a equipe da festa (Editar/Gerenciar) e o papel "Gestor de festas" editam.

O quadro e marcado como de festa via `frappe.db.set_value` em vez de criar uma
Festa de verdade, que dispararia a criacao de pasta no Drive e outros jobs. O
hook de permissao so le `referencia_doctype`/`referencia_nome`.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.gestao_de_tarefas.minhas_tarefas import adicionar_comentario, get_comentarios
from gris.api.gestao_de_tarefas.quadros import (
	atualizar_status_quadro,
	bootstrap_quadro,
	buscar_usuarios,
	excluir_tarefa_quadro,
	listar_quadros_publicos,
	salvar_tarefa_quadro,
)

PAPEIS_DE_PROJETO = ["Visualizador de projetos", "Editor de projetos"]

# Sem os papeis de projeto, de proposito: o quadro de festa nao pode depender
# deles para ser lido.
FORA_DA_FESTA = "fora.festa@teste.gris"
MEMBRO_DA_FESTA = "membro.festa@teste.gris"
GESTOR_DE_FESTAS = "gestor.festa@teste.gris"
# Com papeis de projeto, para provar que quadro solto segue fechado a quem e de fora.
FORA_COM_PAPEIS_DE_PROJETO = "fora.projetos@teste.gris"


def _criar_user(email: str, roles: list[str]) -> str:
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
		user.enabled = 1
		user.set("roles", [])
		for role in roles:
			user.append("roles", {"role": role})
		user.save(ignore_permissions=True)
		return email

	return (
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"user_type": "System User",
				"roles": [{"role": role} for role in roles],
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def _criar_tarefa(board: str, descricao: str) -> str:
	return (
		frappe.get_doc(
			{
				"doctype": "Gestao de Tarefas",
				"board": board,
				"descricao": descricao,
				"status": "Nao iniciado",
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


class TestQuadroDaFesta(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.fora = _criar_user(FORA_DA_FESTA, ["Visualizador de festas"])
		cls.membro = _criar_user(MEMBRO_DA_FESTA, ["Visualizador de festas"])
		cls.gestor = _criar_user(GESTOR_DE_FESTAS, ["Gestor de festas"])
		cls.fora_projetos = _criar_user(FORA_COM_PAPEIS_DE_PROJETO, PAPEIS_DE_PROJETO)
		# FrappeTestCase reverte cada teste ate um savepoint criado antes desta
		# classe rodar; sem commitar aqui, os usuarios de fixture somem depois do
		# primeiro teste (mesmo padrao de test_endpoints.py).
		frappe.db.commit()  # nosemgrep: frappe-manual-commit

	def setUp(self):
		self.usuario_original = frappe.session.user
		self.quadro = frappe.get_doc(
			{
				"doctype": "Board",
				"titulo": "Quadro de teste — festa",
				"ativo": 1,
				"usuarios_autorizados": [{"user": self.membro, "nivel_acesso": "Editar"}],
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value(
			"Board",
			self.quadro.name,
			{"referencia_doctype": "Festa", "referencia_nome": "Festa de teste"},
			update_modified=False,
		)
		self.tarefa = _criar_tarefa(self.quadro.name, "Tarefa da festa")

	def tearDown(self):
		frappe.set_user(self.usuario_original)
		# FrappeTestCase so faz rollback por classe: sem isto os documentos de um
		# teste vazam para o proximo.
		frappe.db.rollback()

	def _salvar(self, descricao: str = "Nova tarefa") -> dict:
		return salvar_tarefa_quadro({"board": self.quadro.name, "descricao": descricao})

	# ───────────────────────── quem e de fora le, mas nao edita ─────────────────────────

	def test_fora_da_festa_le_o_quadro_sem_poder_editar(self):
		frappe.set_user(self.fora)
		dados = bootstrap_quadro(self.quadro.name)
		self.assertFalse(dados["pode_editar"])
		self.assertEqual([t["name"] for t in dados["tarefas"]], [self.tarefa])

	def test_fora_da_festa_le_comentarios(self):
		frappe.set_user(self.fora)
		self.assertTrue(get_comentarios(self.tarefa)["ok"])

	def test_fora_da_festa_nao_cria_tarefa(self):
		frappe.set_user(self.fora)
		with self.assertRaises(frappe.PermissionError):
			self._salvar()

	def test_fora_da_festa_nao_move_tarefa(self):
		frappe.set_user(self.fora)
		with self.assertRaises(frappe.PermissionError):
			atualizar_status_quadro(self.tarefa, "Em andamento")

	def test_fora_da_festa_nao_comenta(self):
		frappe.set_user(self.fora)
		with self.assertRaises(frappe.PermissionError):
			adicionar_comentario(self.tarefa, "Comentario de quem so le")

	def test_fora_da_festa_nao_exclui_tarefa(self):
		frappe.set_user(self.fora)
		with self.assertRaises(frappe.PermissionError):
			excluir_tarefa_quadro(self.tarefa)

	def test_fora_da_festa_nao_busca_usuarios(self):
		frappe.set_user(self.fora)
		with self.assertRaises(frappe.PermissionError):
			buscar_usuarios(self.quadro.name, "a")

	# ───────────────────────── quem edita ─────────────────────────

	def test_membro_da_festa_edita(self):
		frappe.set_user(self.membro)
		self.assertTrue(bootstrap_quadro(self.quadro.name)["pode_editar"])
		tarefas = self._salvar("Criada pelo membro")["tarefas"]
		self.assertIn("Criada pelo membro", [t["descricao"] for t in tarefas])
		atualizar_status_quadro(self.tarefa, "Em andamento")
		self.assertEqual(frappe.db.get_value("Gestao de Tarefas", self.tarefa, "status"), "Em andamento")

	def test_membro_com_nivel_visualizar_nao_edita(self):
		frappe.db.set_value(
			"Board User",
			{"parent": self.quadro.name, "user": self.membro},
			"nivel_acesso",
			"Visualizar",
		)
		frappe.set_user(self.membro)
		self.assertFalse(bootstrap_quadro(self.quadro.name)["pode_editar"])
		with self.assertRaises(frappe.PermissionError):
			self._salvar()

	def test_gestor_de_festas_fora_da_equipe_edita(self):
		frappe.set_user(self.gestor)
		self.assertTrue(bootstrap_quadro(self.quadro.name)["pode_editar"])
		tarefas = self._salvar("Criada pelo gestor")["tarefas"]
		self.assertIn("Criada pelo gestor", [t["descricao"] for t in tarefas])
		excluir_tarefa_quadro(self.tarefa)
		self.assertFalse(frappe.db.exists("Gestao de Tarefas", self.tarefa))

	# ───────────────────────── regressao: outros quadros e indice ─────────────────────────

	def test_quadro_solto_segue_fechado_para_quem_e_de_fora(self):
		frappe.db.set_value(
			"Board",
			self.quadro.name,
			{"referencia_doctype": "", "referencia_nome": ""},
			update_modified=False,
		)
		frappe.set_user(self.fora_projetos)
		with self.assertRaises(frappe.PermissionError):
			bootstrap_quadro(self.quadro.name)

	def test_indice_nao_lista_quadro_de_festa_para_quem_e_de_fora(self):
		frappe.set_user(self.fora_projetos)
		self.assertNotIn(self.quadro.name, [q["name"] for q in listar_quadros_publicos()])
