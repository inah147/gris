"""Sync de integrantes da Festa para o Board vinculado (append-only).

Disparado via hooks `on_update`/`after_insert` em `Festa`, `Area da Festa` e
`Barraca da Festa` (registrados em `hooks.py`). Faz uniao (append-only):
adiciona coordenadores e equipes a `usuarios_autorizados` do Board sem remover
quem ja estava la.

Niveis: coordenadores (geral, de area e de barraca) -> Gerenciar;
integrantes de equipe -> Editar.
"""

from __future__ import annotations

import frappe
from frappe.utils import nowdate

_PESO = {"Visualizar": 1, "Editar": 2, "Gerenciar": 3}

_ESTRUTURAS = ("Area da Festa", "Barraca da Festa")


def sync_from_festa(doc, method=None) -> None:
	sync_festa_board_membros(doc.name)


def sync_from_area(doc, method=None) -> None:
	sync_festa_board_membros((getattr(doc, "festa", None) or "").strip())


def sync_from_barraca(doc, method=None) -> None:
	sync_festa_board_membros((getattr(doc, "festa", None) or "").strip())


def sync_festa_board_membros(festa_name: str) -> None:
	festa_name = (festa_name or "").strip()
	if not festa_name:
		return

	board_name = _localizar_board_da_festa(festa_name)
	if not board_name:
		return

	usuarios = coletar_usuarios_da_festa(festa_name)
	if not usuarios:
		return

	try:
		board = frappe.get_doc("Board", board_name)
	except frappe.DoesNotExistError:
		return

	_unir_usuarios(board, usuarios)


def _localizar_board_da_festa(festa_name: str) -> str | None:
	board = frappe.db.get_value("Festa", festa_name, "board_tarefas")
	if board:
		return board
	return frappe.db.get_value(
		"Board",
		{"referencia_doctype": "Festa", "referencia_nome": festa_name},
		"name",
	)


def coletar_usuarios_da_festa(festa_name: str) -> dict[str, str]:
	"""Retorna {user_email: nivel_acesso} a partir do coordenador geral e dos
	coordenadores/equipes de areas e barracas da festa."""
	usuarios: dict[str, str] = {}

	festa = frappe.db.get_value(
		"Festa",
		festa_name,
		["tipo_coord_geral", "associado_coord_geral", "responsavel_coord_geral", "email_coord_geral"],
		as_dict=True,
	) or {}
	_registrar(
		usuarios,
		_resolver_email(
			festa.get("tipo_coord_geral"),
			festa.get("associado_coord_geral"),
			festa.get("responsavel_coord_geral"),
			festa.get("email_coord_geral"),
		),
		"Gerenciar",
	)

	for doctype in _ESTRUTURAS:
		estruturas = frappe.get_all(
			doctype,
			filters={"festa": festa_name},
			fields=["name", "tipo_coord", "associado_coord", "responsavel_coord", "email_coord"],
			limit_page_length=0,
		)
		for est in estruturas:
			_registrar(
				usuarios,
				_resolver_email(
					est.get("tipo_coord"),
					est.get("associado_coord"),
					est.get("responsavel_coord"),
					est.get("email_coord"),
				),
				"Gerenciar",
			)
			equipe = frappe.get_all(
				"Membro Equipe Festa",
				filters={"parent": est.get("name"), "parenttype": doctype, "parentfield": "equipe"},
				fields=["tipo_pessoa", "associado", "responsavel", "email"],
				limit_page_length=0,
			)
			for membro in equipe:
				_registrar(
					usuarios,
					_resolver_email(
						membro.get("tipo_pessoa"),
						membro.get("associado"),
						membro.get("responsavel"),
						membro.get("email"),
					),
					"Editar",
				)

	return usuarios


def _resolver_email(tipo, associado, responsavel, email_direto) -> str:
	tipo = (tipo or "").strip()
	if tipo == "Associado" and associado:
		# O User (login) do associado é criado com o id@escoteiros, então
		# priorizamos esse e-mail; senão cai para o e-mail comum.
		dados = frappe.db.get_value("Associado", associado, ["id_escoteiros", "email"], as_dict=True) or {}
		email = dados.get("id_escoteiros") or dados.get("email")
	elif tipo == "Responsavel" and responsavel:
		email = frappe.db.get_value("Responsavel", responsavel, "email")
	else:
		email = email_direto
	return (email or "").strip()


def _registrar(usuarios: dict[str, str], email: str, nivel: str) -> None:
	if not email or not frappe.db.exists("User", email):
		return
	if _PESO.get(nivel, 0) > _PESO.get(usuarios.get(email, ""), 0):
		usuarios[email] = nivel


def _unir_usuarios(board, usuarios: dict[str, str]) -> None:
	existentes = {(row.user or "").strip() for row in (board.usuarios_autorizados or [])}
	mudou = False
	for user, nivel in usuarios.items():
		if user and user not in existentes:
			board.append(
				"usuarios_autorizados",
				{"user": user, "nivel_acesso": nivel, "adicionado_em": nowdate()},
			)
			mudou = True

	if not mudou:
		return

	board.flags.ignore_version = True
	board.save(ignore_permissions=True)
