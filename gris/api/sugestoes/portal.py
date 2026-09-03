# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Endpoints do portal para /sugestoes/nova e /sugestoes/acompanhamento.

Contrato de resposta segue o mesmo formato de `gris.api.gestao_de_tarefas`:
sucesso devolve `{"ok": True, ...}` e falha usa `frappe.throw`, que o helper
`callApi` das paginas de portal ja traduz em toast de erro.

Nenhum endpoint aqui e `allow_guest`. Tres niveis de acesso:

* **submeter** — qualquer usuario autenticado, sem exigir papel nenhum;
* **acompanhar** (ler o quadro e os detalhes) — papel `Acompanhamento de
  Sugestoes`, concedido automaticamente a todo Associado;
* **triar** (mover, reordenar, alocar, reclassificar) — papel `Desenvolvedor`.

O papel `All` do Frappe nao e usado de proposito: ele inclui Website User, que
aqui sao os responsaveis, e exporia o quadro interno a eles.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import add_to_date, get_fullname, now_datetime, strip_html

from gris.api.sugestoes.constantes import (
	COLUNAS,
	DESCRICAO_MAX,
	LIMITE_ENVIOS_POR_HORA,
	MODULOS,
	ROLE_ACOMPANHAMENTO,
	ROLE_DESENVOLVEDOR,
	TIPOS,
	TITULO_MAX,
	coluna_inicial,
	modulos_para_tipo,
)

DOCTYPE = "Sugestao ou Problema"

CARD_FIELDS: tuple[str, ...] = (
	"name",
	"titulo",
	"tipo",
	"modulo",
	"status",
	"ordem",
	"responsavel",
	"solicitante",
	"solicitante_nome",
	"data_submissao",
	"tarefa",
)

# `ordem` é a prioridade definida arrastando; entre itens de mesma ordem (o
# padrão 0 de quem nunca foi arrastado) o mais recente vem primeiro, para uma
# submissão nova aparecer no topo da coluna de triagem em vez de se enterrar.
CARD_ORDER_BY = "ordem asc, creation desc"


def _require_logged_user() -> str:
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Você precisa estar autenticado."), frappe.PermissionError)
	return user


def pode_acompanhar(user: str | None = None) -> bool:
	"""Quem enxerga o quadro.

	Submeter é aberto a qualquer usuário autenticado; acompanhar não, para o
	quadro interno não ficar visível aos responsáveis (Website Users).
	"""
	roles = frappe.get_roles(user or frappe.session.user)
	return ROLE_ACOMPANHAMENTO in roles or ROLE_DESENVOLVEDOR in roles or "System Manager" in roles


def pode_triar(user: str | None = None) -> bool:
	"""Quem move cards e aloca responsável no quadro."""
	roles = frappe.get_roles(user or frappe.session.user)
	return ROLE_DESENVOLVEDOR in roles or "System Manager" in roles


def _require_acompanhamento() -> str:
	user = _require_logged_user()
	if not pode_acompanhar(user):
		frappe.throw(
			_("Você não tem permissão para acompanhar as solicitações."),
			frappe.PermissionError,
		)
	return user


def _require_desenvolvedor() -> str:
	user = _require_logged_user()
	if not pode_triar(user):
		frappe.throw(
			_("Apenas quem tem o papel '{0}' pode organizar o quadro.").format(ROLE_DESENVOLVEDOR),
			frappe.PermissionError,
		)
	return user


def _parse_payload(value: Any) -> dict[str, Any]:
	if isinstance(value, dict):
		return value
	if isinstance(value, str):
		import json

		try:
			parsed = json.loads(value)
		except Exception:
			frappe.throw(_("Dados da solicitação inválidos."))
		if not isinstance(parsed, dict):
			frappe.throw(_("Dados da solicitação inválidos."))
		return parsed
	frappe.throw(_("Dados da solicitação inválidos."))
	return {}


def _texto(payload: dict[str, Any], campo: str) -> str:
	valor = payload.get(campo)
	return valor.strip() if isinstance(valor, str) else ""


def _booleano(payload: dict[str, Any], campo: str, *, padrao: bool) -> bool:
	"""Lê um campo de marcar do payload.

	`cint` não serve: ele devolve 0 para a string "true", e o valor chega ora
	como booleano JSON (pelo `frappe.call` da página), ora como string (por quem
	monta a chamada na mão).
	"""
	if campo not in payload:
		return padrao

	valor = payload.get(campo)
	if isinstance(valor, str):
		return valor.strip().lower() in {"1", "true", "yes", "on"}
	return bool(valor)


def _carregar(name: str):
	"""Carrega a solicitação recusando o 404 do `frappe.get_doc`.

	`DoesNotExistError` vira HTTP 404, e o handler de 404 do request.js chama
	`frappe.msgprint` **incondicionalmente** — o `silent: true` não o alcança.
	Numa página de portal isso abre o modal do Desk sem estilo, que trava a tela.
	Um `frappe.throw` normal responde 417, que o cliente trata como erro comum e
	transforma em toast. Vale para link antigo, item apagado ou URL digitada.
	"""
	name = (name or "").strip()
	if not name or not frappe.db.exists(DOCTYPE, name):
		frappe.throw(_("Solicitação {0} não existe mais.").format(name or "?"))
	return frappe.get_doc(DOCTYPE, name)


# ───────────────────────────── leitura ─────────────────────────────


def _resolver_usuarios(emails: set[str]) -> dict[str, dict[str, str]]:
	"""Nome e avatar de vários usuários numa consulta só (evita N+1 nos cards)."""
	emails = {e for e in emails if e}
	if not emails:
		return {}

	linhas = frappe.get_all(
		"User",
		filters={"name": ["in", list(emails)]},
		fields=["name", "full_name", "user_image"],
		limit_page_length=0,
		ignore_permissions=True,
	)
	return {
		linha["name"]: {
			"nome": linha.get("full_name") or linha["name"],
			"avatar": linha.get("user_image") or "",
		}
		for linha in linhas
	}


@frappe.whitelist()
def listar_board() -> dict[str, Any]:
	"""Todas as solicitações agrupadas nas colunas do kanban.

	O volume é de dezenas de registros, então uma consulta única sem paginação
	é adequada e deixa o filtro de tipo/módulo acontecer no cliente.
	"""
	_require_acompanhamento()

	linhas = frappe.get_all(
		DOCTYPE,
		fields=list(CARD_FIELDS),
		order_by=CARD_ORDER_BY,
		limit_page_length=0,
	)

	usuarios = _resolver_usuarios({linha.get("responsavel") for linha in linhas})

	colunas: dict[str, list[dict[str, Any]]] = {coluna: [] for coluna in COLUNAS}
	for linha in linhas:
		responsavel = linha.get("responsavel") or ""
		dados = usuarios.get(responsavel, {})
		linha["responsavel_nome"] = dados.get("nome", "")
		linha["responsavel_avatar"] = dados.get("avatar", "")
		colunas.setdefault(linha.get("status") or COLUNAS[0], []).append(linha)

	return {
		"ok": True,
		"colunas": [{"status": coluna, "itens": colunas.get(coluna, [])} for coluna in COLUNAS],
		"pode_triar": pode_triar(),
		"usuario_atual": frappe.session.user,
	}


@frappe.whitelist()
def detalhes(name: str) -> dict[str, Any]:
	_require_acompanhamento()

	doc = _carregar(name)

	responsavel = (doc.responsavel or "").strip()
	dados = _resolver_usuarios({responsavel}).get(responsavel, {})

	return {
		"ok": True,
		"item": {
			"name": doc.name,
			"titulo": doc.titulo,
			"tipo": doc.tipo,
			"modulo": doc.modulo,
			"status": doc.status,
			"descricao": doc.descricao or "",
			"solicitante": doc.solicitante or "",
			"solicitante_nome": doc.solicitante_nome or "",
			"data_submissao": doc.data_submissao,
			"data_inicio_desenvolvimento": doc.data_inicio_desenvolvimento,
			"data_conclusao": doc.data_conclusao,
			"responsavel": responsavel,
			"responsavel_nome": dados.get("nome", ""),
			"responsavel_avatar": dados.get("avatar", ""),
			"tarefa": doc.tarefa or "",
		},
		"comentarios": _serializar_comentarios(doc.name),
		"pode_triar": pode_triar(),
		"pode_editar": _pode_editar(doc),
	}


def _pode_editar(doc) -> bool:
	"""Quem pode reescrever a descrição.

	Quem abriu, para completar o relato depois de lembrar de um detalhe, e quem
	tria, para organizar o texto antes de virar tarefa.
	"""
	return (doc.solicitante or "") == frappe.session.user or pode_triar()


def desenvolvedores() -> list[dict[str, str]]:
	"""Candidatos a responsável — só quem tem a role Desenvolvedor e está ativo.

	Chamada pelo `get_context` de /sugestoes/acompanhamento, que renderiza as
	opções do select no HTML. Não é um endpoint: o `select.js` do Basecoat só
	reconhece os `[role="option"]` presentes na inicialização, então a lista
	precisa vir pronta do servidor.
	"""
	linhas = frappe.get_all(
		"Has Role",
		filters={"role": ROLE_DESENVOLVEDOR, "parenttype": "User"},
		fields=["parent"],
		limit_page_length=0,
		ignore_permissions=True,
	)
	candidatos = {linha["parent"] for linha in linhas if linha.get("parent")}
	if not candidatos:
		return []

	ativos = frappe.get_all(
		"User",
		filters={"name": ["in", list(candidatos)], "enabled": 1},
		fields=["name", "full_name", "user_image"],
		order_by="full_name asc",
		limit_page_length=0,
		ignore_permissions=True,
	)
	return [
		{
			"email": linha["name"],
			"nome": linha.get("full_name") or linha["name"],
			"avatar": linha.get("user_image") or "",
		}
		for linha in ativos
	]


# ───────────────────────────── escrita ─────────────────────────────


def _checar_rate_limit(user: str) -> None:
	desde = add_to_date(now_datetime(), hours=-1)
	recentes = frappe.db.count(DOCTYPE, {"solicitante": user, "creation": [">=", desde]})
	if recentes >= LIMITE_ENVIOS_POR_HORA:
		frappe.throw(
			_("Você já enviou {0} solicitações na última hora. Tente novamente mais tarde.").format(
				LIMITE_ENVIOS_POR_HORA
			)
		)


@frappe.whitelist()
def submeter_solicitacao(payload: Any) -> dict[str, Any]:
	user = _require_logged_user()
	dados = _parse_payload(payload)

	tipo = _texto(dados, "tipo")
	modulo = _texto(dados, "modulo")
	titulo = _texto(dados, "titulo")
	descricao = _texto(dados, "descricao")

	if not titulo:
		frappe.throw(_("Informe um título para a solicitação."))
	# O editor WYSIWYG devolve "<p><br></p>" quando está vazio, então testar a
	# string crua deixaria passar uma descrição em branco.
	if not strip_html(descricao).strip():
		frappe.throw(_("Descreva a solicitação."))
	if tipo not in TIPOS:
		frappe.throw(_("Escolha o que você deseja fazer."))
	if modulo not in MODULOS:
		frappe.throw(_("Escolha o módulo da solicitação."))
	# O formulário já esconde "Novo módulo" para problemas; aqui é a regra de
	# verdade, porque o client pode ser contornado.
	if modulo not in modulos_para_tipo(tipo):
		frappe.throw(_("O módulo '{0}' não vale para '{1}'.").format(modulo, tipo))
	if len(titulo) > TITULO_MAX:
		frappe.throw(_("O título deve ter no máximo {0} caracteres.").format(TITULO_MAX))
	# Mede o texto escrito, não as tags que o editor gera — o limite existe para
	# o conteúdo, e contar markup recusaria um relato legítimo bem formatado.
	if len(strip_html(descricao)) > DESCRICAO_MAX:
		frappe.throw(_("A descrição deve ter no máximo {0} caracteres.").format(DESCRICAO_MAX))

	_checar_rate_limit(user)

	# `ignore_permissions` porque a regra de negócio é justamente "todo mundo com
	# login pode reportar", e o DocType não concede `create` a ninguém além da
	# equipe — dar `create` ao papel "All" exporia também a leitura do quadro aos
	# responsáveis. A autorização aqui é `_require_logged_user` mais o rate limit
	# acima; o conteúdo é validado pelo controller.
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"titulo": titulo,
			"tipo": tipo,
			"modulo": modulo,
			"descricao": descricao,
			# O `before_insert` zera isto de novo quando não há telefone para
			# avisar: o formulário desabilita a opção, mas o cliente pode ser
			# contornado e a promessa ficaria gravada sem ter como cumprir.
			"avisar_por_whatsapp": int(_booleano(dados, "avisar_por_whatsapp", padrao=True)),
		}
	).insert(ignore_permissions=True)

	return {
		"ok": True,
		"name": doc.name,
		"status": doc.status,
		# Pode ter sido zerado no `before_insert` por falta de telefone; o cliente
		# usa isto para não prometer um aviso que não vai acontecer.
		"avisar_por_whatsapp": bool(doc.avisar_por_whatsapp),
		# O formulário só manda para o quadro quem consegue vê-lo.
		"pode_acompanhar": pode_acompanhar(),
	}


@frappe.whitelist()
def atualizar_status(name: str, status: str) -> dict[str, Any]:
	"""Move o card de coluna. Usado pelo drag-and-drop do kanban."""
	_require_desenvolvedor()

	status = (status or "").strip()
	if status not in COLUNAS:
		frappe.throw(_("Coluna inválida: {0}.").format(status or "vazia"))

	doc = _carregar(name)
	if doc.status == status:
		return {"ok": True, "status": doc.status}

	doc.status = status
	doc.save()

	return {"ok": True, "status": doc.status, "tarefa": doc.tarefa or ""}


@frappe.whitelist()
def reordenar(status: str, nomes: Any) -> dict[str, Any]:
	"""Grava a prioridade dos cards de uma coluna, na ordem recebida.

	Recebe a coluna inteira em vez de uma posição só: reescrever `0..n` de uma
	vez é idempotente e imune a empates, enquanto ajustar um índice isolado vai
	acumulando furos e desempates ambíguos a cada arrasto.
	"""
	_require_desenvolvedor()

	status = (status or "").strip()
	if status not in COLUNAS:
		frappe.throw(_("Coluna inválida: {0}.").format(status or "vazia"))

	if isinstance(nomes, str):
		nomes = frappe.parse_json(nomes)
	if not isinstance(nomes, list):
		frappe.throw(_("Lista de solicitações inválida."))

	# Só considera o que de fato está na coluna: um nome inexistente ou de outra
	# coluna vindo de um quadro defasado não pode reordenar o que não é dele.
	da_coluna = set(frappe.get_all(DOCTYPE, filters={"status": status}, pluck="name", limit_page_length=0))

	ordem = 0
	for nome in nomes:
		nome = (nome or "").strip()
		if nome not in da_coluna:
			continue
		# `ordem` é só apresentação: `db.set_value` evita disparar o sync com a
		# tarefa e não mexe em `modified` por um arrasto.
		frappe.db.set_value(DOCTYPE, nome, "ordem", ordem, update_modified=False)
		ordem += 1

	return {"ok": True, "quantidade": ordem}


@frappe.whitelist()
def reclassificar(name: str, tipo: str) -> dict[str, Any]:
	"""Troca o tipo e move para a coluna de triagem correspondente.

	As duas primeiras colunas do quadro representam o tipo, então arrastar um
	card para a coluna do outro tipo é um pedido de reclassificação — não um
	erro. O cliente confirma com o usuário antes de chamar isto.
	"""
	_require_desenvolvedor()

	tipo = (tipo or "").strip()
	if tipo not in TIPOS:
		frappe.throw(_("Tipo inválido: {0}.").format(tipo or "vazio"))

	doc = _carregar(name)
	if doc.tipo == tipo:
		return {"ok": True, "tipo": doc.tipo, "status": doc.status}

	# "Novo módulo" só existe para funcionalidade. Reclassificar sem avisar
	# deixaria o item num estado que a validação recusa no próximo save.
	if doc.modulo not in modulos_para_tipo(tipo):
		frappe.throw(
			_(
				"Esta solicitação está no módulo '{0}', que não vale para '{1}'. "
				"Troque o módulo antes de reclassificar."
			).format(doc.modulo, tipo)
		)

	doc.tipo = tipo
	doc.status = coluna_inicial(tipo)
	doc.save()

	return {"ok": True, "tipo": doc.tipo, "status": doc.status}


@frappe.whitelist()
def atualizar_descricao(name: str, descricao: str) -> dict[str, Any]:
	"""Reescreve a descrição a partir do editor do dialog."""
	_require_logged_user()

	doc = _carregar(name)
	if not _pode_editar(doc):
		frappe.throw(
			_("Só quem abriu a solicitação ou quem tria o quadro pode editar a descrição."),
			frappe.PermissionError,
		)

	descricao = (descricao or "").strip()
	if not strip_html(descricao).strip():
		frappe.throw(_("A descrição não pode ficar vazia."))
	if len(strip_html(descricao)) > DESCRICAO_MAX:
		frappe.throw(_("A descrição deve ter no máximo {0} caracteres.").format(DESCRICAO_MAX))

	doc.descricao = descricao
	# O solicitante não tem `write` no DocType (a role `All` só recebe read e
	# create); a autorização de quem pode editar já foi feita em `_pode_editar`.
	doc.save(ignore_permissions=True)

	return {"ok": True, "descricao": doc.descricao}


@frappe.whitelist()
def alocar_responsavel(name: str, user: str | None = None) -> dict[str, Any]:
	"""Aloca (ou desaloca, com `user` vazio) quem vai desenvolver.

	A tarefa espelho é criada pelo hook `on_update`, em
	`gris.gestao_de_tarefas.board_sync_sugestoes`.
	"""
	_require_desenvolvedor()

	alvo = (user or "").strip()
	if alvo and ROLE_DESENVOLVEDOR not in frappe.get_roles(alvo):
		frappe.throw(_("{0} não tem o papel '{1}'.").format(get_fullname(alvo) or alvo, ROLE_DESENVOLVEDOR))

	doc = _carregar(name)
	doc.responsavel = alvo or None
	doc.save()
	doc.reload()

	dados = _resolver_usuarios({alvo}).get(alvo, {}) if alvo else {}
	return {
		"ok": True,
		"responsavel": alvo,
		"responsavel_nome": dados.get("nome", ""),
		"responsavel_avatar": dados.get("avatar", ""),
		"tarefa": doc.tarefa or "",
	}


# ──────────────────────────── comentários ────────────────────────────


def _serializar_comentarios(name: str) -> list[dict[str, Any]]:
	linhas = frappe.get_all(
		"Comment",
		filters={
			"reference_doctype": DOCTYPE,
			"reference_name": name,
			"comment_type": "Comment",
		},
		fields=["name", "content", "comment_by", "comment_email", "owner", "creation"],
		order_by="creation asc",
		limit_page_length=200,
		ignore_permissions=True,
	)

	comentarios: list[dict[str, Any]] = []
	for linha in linhas:
		email = (linha.get("comment_email") or linha.get("owner") or "").strip()
		autor = (linha.get("comment_by") or "").strip()
		if not autor and email:
			autor = frappe.db.get_value("User", email, "full_name") or email
		conteudo = linha.get("content") or ""
		comentarios.append(
			{
				"name": linha.get("name"),
				"texto": strip_html(conteudo.replace("</p>", "\n").replace("<br>", "\n")).strip(),
				"autor": autor or email or _("Usuário"),
				"autor_email": email,
				"creation": linha.get("creation"),
			}
		)
	return comentarios


@frappe.whitelist()
def get_comentarios(name: str) -> dict[str, Any]:
	_require_acompanhamento()
	doc = _carregar(name)
	return {"ok": True, "comentarios": _serializar_comentarios(doc.name)}


@frappe.whitelist()
def adicionar_comentario(name: str, texto: str) -> dict[str, Any]:
	user = _require_acompanhamento()

	texto = (texto or "").strip()
	if not texto:
		frappe.throw(_("Escreva algo antes de comentar."))
	if len(texto) > 5000:
		frappe.throw(_("O comentário deve ter no máximo 5000 caracteres."))

	doc = _carregar(name)

	frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Comment",
			"reference_doctype": DOCTYPE,
			"reference_name": doc.name,
			"content": frappe.utils.escape_html(texto).replace("\n", "<br>"),
			"comment_email": user,
			"comment_by": get_fullname(user) or user,
		}
	).insert(ignore_permissions=True)

	return {"ok": True, "comentarios": _serializar_comentarios(doc.name)}
