# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Avisos por WhatsApp do modulo Sugestoes e Problemas.

Tres avisos, todos disparados por `doc_events` registrados em `hooks.py`:

1. **Nova solicitacao** (`after_insert` de `Sugestao ou Problema`) — publica no
   grupo de desenvolvimento quem pediu, tipo, modulo, titulo e descricao, com
   link para o card.
2. **Conclusao** (`on_update` de `Sugestao ou Problema`) — avisa quem abriu
   quando o card chega em `Concluido`, se a pessoa marcou a opcao no formulario.
3. **Comentario** (`after_insert` de `Comment`, filtrado por
   `reference_doctype`) — avisa quem abriu e o responsavel pelo
   desenvolvimento (quando ha um, e quando nao e a propria pessoa que
   comentou). Um hook em `Comment` em vez de um em cada caminho de escrita
   cobre o portal, o MCP e o Desk com um handler so.

O envio nunca pode derrubar o save do card nem o insert do comentario: tudo
passa por `try/except` com `frappe.log_error`, e a entrega em si e enfileirada
por `gris.utils.whatsapp`. Por isso os carimbos `aviso_*_enviado_em` significam
"enfileirado em", e nao "entregue em" — mesma semantica de
`whatsapp_notificado_em` em `Convite Festa`.
"""

from __future__ import annotations

import frappe
from frappe.utils import get_fullname, get_url, now_datetime, strip_html

from gris.api.sugestoes.constantes import COLUNA_CONCLUIDO
from gris.utils.contato import telefone_do_usuario
from gris.utils.whatsapp import enviar_para_grupo, enviar_texto

DOCTYPE = "Sugestao ou Problema"
SETTINGS_DOCTYPE = "Configuracoes de Desenvolvimento"

# A descricao vem de um editor WYSIWYG que aceita ate 10.000 caracteres. Um relato
# longo inteiro no grupo afogaria a mensagem; o link logo abaixo tem o texto todo.
DESCRICAO_RESUMO_MAX = 500


def _logger():
	return frappe.logger("sugestoes_notificacoes", allow_site=True)


# ───────────────────────────── configuracao ─────────────────────────────


def _avisos_habilitados() -> bool:
	return bool(frappe.db.get_single_value(SETTINGS_DOCTYPE, "habilitar_avisos_whatsapp"))


def _grupo_desenvolvimento() -> str:
	return (frappe.db.get_single_value(SETTINGS_DOCTYPE, "grupo_desenvolvimento_whatsapp") or "").strip()


# ───────────────────────────── texto ─────────────────────────────


def _primeiro_nome(doc) -> str:
	"""Primeiro nome de quem abriu, para a mensagem soar como conversa.

	Cai no e-mail quando `solicitante_nome` esta vazio: e feio, mas um "Ola, !"
	seria pior.
	"""
	nome = (getattr(doc, "solicitante_nome", "") or "").strip()
	if nome:
		return nome.split()[0]
	return (getattr(doc, "solicitante", "") or "").strip()


def _descricao_em_texto(html: str | None) -> str:
	"""HTML do editor em texto puro, truncado para caber numa mensagem.

	As quebras precisam virar `\\n` antes do `strip_html`, senao paragrafos
	distintos colam num paredao unico — mesma conversao usada ao serializar
	comentarios em `gris.api.sugestoes.portal`.
	"""
	bruto = (html or "").replace("</p>", "\n").replace("<br>", "\n").replace("<br/>", "\n")
	texto = strip_html(bruto).strip()

	# Junta as linhas em branco que o editor deixa entre paragrafos.
	linhas = [linha.strip() for linha in texto.splitlines()]
	texto = "\n".join(linha for linha in linhas if linha)

	if len(texto) > DESCRICAO_RESUMO_MAX:
		texto = texto[:DESCRICAO_RESUMO_MAX].rstrip() + "..."

	return texto or "(sem descricao)"


def _link_do_card(name: str) -> str:
	"""URL que abre o dialog do card direto no quadro."""
	return f"{get_url('/sugestoes/acompanhamento')}?item={name}"


def _montar_mensagem_nova_solicitacao(doc) -> str:
	solicitante = (getattr(doc, "solicitante_nome", "") or "").strip() or (
		getattr(doc, "solicitante", "") or "Nao informado"
	)
	return (
		"@todos\n\n"
		"🆕 Nova solicitação no GRIS\n\n"
		f"*{solicitante}*\n"
		f"- *Tipo*: {doc.tipo}\n"
		f"- *Módulo*: {doc.modulo}\n"
		f"- *Título*: {doc.titulo}\n"
		f"- *Descrição*: {_descricao_em_texto(doc.descricao)}\n\n"
		f"Abrir no quadro: {_link_do_card(doc.name)}"
	)


def _montar_mensagem_conclusao(doc) -> str:
	return (
		f"Olá, {_primeiro_nome(doc)}!\n\n"
		"Vim falar da sua solicitação:\n"
		f"{doc.titulo}\n\n"
		"Ela já foi implementada! Se tiver algum problema é só avisar!\n\n"
		"_Esta é uma mensagem automática_"
	)


def _montar_mensagem_comentario_solicitante(doc, texto: str) -> str:
	return (
		f"Olá, {_primeiro_nome(doc)}!\n\n"
		"Chegou um novo comentário na sua solicitação:\n"
		f"{doc.titulo}\n\n"
		f"{texto}\n\n"
		f"Abrir no quadro: {_link_do_card(doc.name)}\n\n"
		"_Esta é uma mensagem automática_"
	)


def _montar_mensagem_comentario_responsavel(doc, texto: str) -> str:
	nome = (get_fullname(doc.responsavel) or doc.responsavel or "").split()[0]
	return (
		f"Olá, {nome}!\n\n"
		"Novo comentário na solicitação que você está desenvolvendo:\n"
		f"{doc.titulo}\n\n"
		f"{texto}\n\n"
		f"Abrir no quadro: {_link_do_card(doc.name)}\n\n"
		"_Esta é uma mensagem automática_"
	)


# ───────────────────────────── envio ─────────────────────────────


def _carimbar(name: str, campo: str) -> None:
	"""Marca o aviso como despachado, sem mexer em `modified`.

	`db.set_value` de proposito: um `doc.save()` aqui dispararia `on_update` de
	novo e criaria uma versao de `track_changes` por causa de um carimbo interno.
	"""
	frappe.db.set_value(DOCTYPE, name, campo, now_datetime(), update_modified=False)


def notificar_nova_solicitacao(doc) -> None:
	"""Publica a solicitacao recem-aberta no grupo de desenvolvimento.

	Falha silenciosa com log: o relato ja foi gravado, e recusar o insert porque
	o WhatsApp esta fora do ar seria perder o relato junto.
	"""
	if getattr(doc, "aviso_grupo_enviado_em", None):
		return

	if not _avisos_habilitados():
		return

	grupo_jid = _grupo_desenvolvimento()
	if not grupo_jid:
		_logger().warning(
			f"Aviso de nova solicitação não enviado ({doc.name}): "
			f"grupo de desenvolvimento não configurado em {SETTINGS_DOCTYPE}."
		)
		return

	try:
		enviar_para_grupo(grupo_jid, _montar_mensagem_nova_solicitacao(doc), mencionar_todos=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Aviso de nova solicitação: {doc.name}")
		return

	_carimbar(doc.name, "aviso_grupo_enviado_em")
	_logger().info(f"Aviso de nova solicitação enfileirado para o grupo de desenvolvimento ({doc.name}).")


def notificar_conclusao(doc) -> None:
	"""Avisa quem abriu que a solicitacao foi entregue.

	So sai para quem marcou a opcao no formulario. O telefone e resolvido na hora
	porque a pessoa pode ter atualizado o cadastro entre a abertura e a entrega;
	o snapshot gravado no insert cobre o caso inverso, de um cadastro que perdeu
	o numero no meio do caminho.
	"""
	if getattr(doc, "aviso_conclusao_enviado_em", None):
		return

	if not doc.avisar_por_whatsapp:
		return

	if not _avisos_habilitados():
		return

	telefone = telefone_do_usuario(doc.solicitante) or (getattr(doc, "telefone_aviso", "") or "").strip()
	if not telefone:
		_logger().warning(
			f"Aviso de conclusão não enviado ({doc.name}): nenhum telefone encontrado para {doc.solicitante}."
		)
		return

	try:
		enviar_texto(telefone, _montar_mensagem_conclusao(doc))
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Aviso de conclusão: {doc.name}")
		return

	_carimbar(doc.name, "aviso_conclusao_enviado_em")
	_logger().info(f"Aviso de conclusão enfileirado para {doc.solicitante} ({doc.name}).")


def _avisar_por_texto(destinatario: str, papel: str, mensagem: str, nome_do_card: str) -> None:
	"""Resolve o telefone e envia, sem deixar uma falha isolada quebrar o resto."""
	telefone = telefone_do_usuario(destinatario)
	if not telefone:
		_logger().warning(
			f"Aviso de comentário não enviado ({nome_do_card}, {papel}): "
			f"nenhum telefone encontrado para {destinatario}."
		)
		return

	try:
		enviar_texto(telefone, mensagem)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Aviso de comentário ({papel}): {nome_do_card}")
		return

	_logger().info(f"Aviso de comentário enfileirado para {papel} ({nome_do_card}).")


def notificar_comentario(comment) -> None:
	"""Avisa quem abriu e o responsável pelo desenvolvimento de um novo comentário.

	Nunca avisa quem escreveu o próprio comentário — comentar na sua própria
	solicitação, ou na que você mesmo desenvolve, não merece uma mensagem sobre
	si mesmo. Os dois avisos são independentes: solicitante e responsável podem
	ser a mesma pessoa (então só um é enviado) ou nenhum ter telefone.
	"""
	if not _avisos_habilitados():
		return

	try:
		sugestao = frappe.get_doc("Sugestao ou Problema", comment.reference_name)
	except frappe.DoesNotExistError:
		return

	autor = (comment.comment_email or comment.owner or "").strip()
	texto = _descricao_em_texto(comment.content)

	if sugestao.solicitante and sugestao.solicitante != autor:
		_avisar_por_texto(
			sugestao.solicitante,
			"solicitante",
			_montar_mensagem_comentario_solicitante(sugestao, texto),
			sugestao.name,
		)

	if sugestao.responsavel and sugestao.responsavel != autor and sugestao.responsavel != sugestao.solicitante:
		_avisar_por_texto(
			sugestao.responsavel,
			"responsável",
			_montar_mensagem_comentario_responsavel(sugestao, texto),
			sugestao.name,
		)


# ───────────────────────────── hooks ─────────────────────────────


def _fora_de_operacao_normal() -> bool:
	"""Migracao, patch e instalacao mexem em documentos sem ninguem pedindo."""
	return bool(frappe.flags.in_install or frappe.flags.in_patch or frappe.flags.in_migrate)


def on_sugestao_criada(doc, method=None) -> None:
	"""`doc_events` `after_insert`: avisa o grupo de desenvolvimento.

	No `after_insert` (e nao no endpoint do portal) para cobrir tambem quem cria
	a solicitacao direto no Desk.
	"""
	if _fora_de_operacao_normal():
		return

	notificar_nova_solicitacao(doc)


def on_sugestao_atualizada(doc, method=None) -> None:
	"""`doc_events` `on_update`: avisa o solicitante quando o card e concluido.

	Todos os caminhos que levam a `Concluido` passam por `doc.save()` — o
	arrasto no kanban, o sync reverso da tarefa espelho e a edicao no Desk —
	entao um unico `on_update` cobre os tres. O carimbo em
	`aviso_conclusao_enviado_em` garante que reabrir e concluir de novo nao
	dispare uma segunda mensagem.
	"""
	if _fora_de_operacao_normal():
		return

	anterior = doc.get_doc_before_save()
	if not anterior:
		return

	if doc.status == COLUNA_CONCLUIDO and anterior.status != COLUNA_CONCLUIDO:
		notificar_conclusao(doc)


def on_comentario_criado(doc, method=None) -> None:
	"""`doc_events` `after_insert` de `Comment`, filtrado a este DocType.

	Um hook em `Comment` em vez de um em cada endpoint que comenta (portal,
	MCP) cobre também quem comenta direto pelo Desk com o mesmo handler.
	"""
	if _fora_de_operacao_normal():
		return

	if doc.reference_doctype != "Sugestao ou Problema" or not doc.reference_name:
		return
	if doc.comment_type != "Comment":
		return

	notificar_comentario(doc)
