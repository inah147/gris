# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Comentários livres de um documento, pelo portal, sobre o DocType `Comment`.

Genérico de propósito: quem chama já decidiu que o usuário pode ver o documento.
Aqui só se garante que o comentário pertence ao documento informado e que editar e
apagar são do autor (ou de um `System Manager`).

Gravação com `ignore_permissions`: o `Comment` do Frappe exige permissão no documento
de referência, e no portal essa permissão é decidida pela regra da feature, não por
papel no DocType.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import escape_html, get_fullname, strip_html
from frappe.utils.html_utils import unescape_html

LIMITE_DE_CARACTERES = 5000


def listar(doctype: str, name: str, user: str | None = None) -> list[dict]:
	user = user or frappe.session.user
	admin = _eh_admin(user)
	linhas = frappe.get_all(
		"Comment",
		filters={"reference_doctype": doctype, "reference_name": name, "comment_type": "Comment"},
		fields=["name", "content", "comment_by", "comment_email", "owner", "creation", "modified"],
		order_by="creation asc",
		limit_page_length=500,
	)
	comentarios = []
	for linha in linhas:
		autor = (linha.owner or linha.comment_email or "").strip()
		comentarios.append(
			{
				"name": linha.name,
				"texto": _texto_puro(linha.content),
				"autor": linha.comment_by or get_fullname(autor) or autor,
				"criado_em": str(linha.creation),
				"editado": bool(linha.modified and linha.creation and linha.modified > linha.creation),
				"pode_editar": admin or autor.lower() == (user or "").lower(),
			}
		)
	return comentarios


def adicionar(doctype: str, name: str, texto: str) -> None:
	texto = _validar_texto(texto)
	user = frappe.session.user
	frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Comment",
			"reference_doctype": doctype,
			"reference_name": name,
			"content": _para_html(texto),
			"comment_email": user,
			"comment_by": get_fullname(user),
		}
	).insert(ignore_permissions=True)


def editar(doctype: str, name: str, comentario: str, texto: str) -> None:
	texto = _validar_texto(texto)
	doc = _carregar_do_autor(doctype, name, comentario)
	doc.content = _para_html(texto)
	doc.save(ignore_permissions=True)


def apagar(doctype: str, name: str, comentario: str) -> None:
	doc = _carregar_do_autor(doctype, name, comentario)
	frappe.delete_doc("Comment", doc.name, ignore_permissions=True)


def _carregar_do_autor(doctype: str, name: str, comentario: str):
	comentario = (comentario or "").strip()
	if not comentario or not frappe.db.exists("Comment", comentario):
		frappe.throw(_("Comentário não encontrado."), frappe.DoesNotExistError)
	doc = frappe.get_doc("Comment", comentario)
	if doc.comment_type != "Comment" or doc.reference_doctype != doctype or doc.reference_name != name:
		frappe.throw(_("Comentário não encontrado."), frappe.DoesNotExistError)

	user = frappe.session.user
	autor = (doc.owner or doc.comment_email or "").strip().lower()
	if not _eh_admin(user) and autor != (user or "").lower():
		frappe.throw(_("Só quem escreveu o comentário pode editá-lo ou apagá-lo."), frappe.PermissionError)
	return doc


def _validar_texto(texto: str) -> str:
	texto = (texto or "").strip()
	if not texto:
		frappe.throw(_("Escreva algo antes de comentar."))
	if len(texto) > LIMITE_DE_CARACTERES:
		frappe.throw(_("O comentário passou de {0} caracteres.").format(LIMITE_DE_CARACTERES))
	return texto


def _para_html(texto: str) -> str:
	"""Texto puro vira HTML escapado: o `Comment` é renderizado como HTML no Desk."""
	return escape_html(texto).replace("\n", "<br>")


def _texto_puro(html: str | None) -> str:
	texto = (html or "").replace("<br>", "\n").replace("<br/>", "\n").replace("</p>", "\n")
	return unescape_html(strip_html(texto)).strip()


def _eh_admin(user: str | None) -> bool:
	return "System Manager" in frappe.get_roles(user)
