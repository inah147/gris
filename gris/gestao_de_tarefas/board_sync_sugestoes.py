# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Ponte entre "Sugestao ou Problema" e o modulo de Gestao de Tarefas.

Mantem tres coisas em dia, todas por hooks registrados em `hooks.py`:

1. **O quadro** "Desenvolvimento do GRIS" — um Board unico, cujo dono e o
   `Module Def` do proprio modulo (ver `_BOARD_FILTROS`).
2. **Os membros do quadro** — todo User ativo com a role `Desenvolvedor`.
3. **A tarefa espelho** — criada quando uma sugestao ganha responsavel, para o
   item aparecer em "Minhas tarefas". Status anda nos dois sentidos.

Sobre o sync bidirecional: `sincronizar_tarefa_da_sugestao` e
`sincronizar_sugestao_da_tarefa` escrevem uma no documento da outra, o que
fecharia um ciclo infinito de `on_update`. Duas travas evitam isso:
`frappe.flags.gris_sync_sugestao_tarefa`, que faz o hook do outro lado sair
cedo, e a comparacao campo a campo em `_aplicar`, que nao salva quando nada
mudou. A flag sozinha bastaria, mas a comparacao tambem evita versoes de
`track_changes` sem conteudo.
"""

from __future__ import annotations

import frappe
from frappe.utils import format_datetime, nowdate, strip_html

from gris.api.sugestoes.constantes import (
	BOARD_DESENVOLVIMENTO_TITULO,
	COLUNA_POR_STATUS_TAREFA,
	ROLE_DESENVOLVEDOR,
	STATUS_TAREFA_POR_COLUNA,
)

DOCTYPE_SUGESTAO = "Sugestao ou Problema"
DOCTYPE_TAREFA = "Gestao de Tarefas"
MODULE_DEF = "Sugestoes e Problemas"

_FLAG_SYNC = "gris_sync_sugestao_tarefa"
_NIVEL_DESENVOLVEDOR = "Editar"

# O quadro pertence ao modulo, nao a um registro de negocio: o `Module Def` do
# app e o dono natural e da um identificador estavel, criado pelo proprio
# `bench migrate`. Sobrevive a renomear o quadro no Desk, o que uma busca por
# titulo nao sobreviveria. "Module Def" esta em `BOARD_REFERENCIA_PERMITIDAS`.
_BOARD_FILTROS = {"referencia_doctype": "Module Def", "referencia_nome": MODULE_DEF}


# ───────────────────────────── Quadro ─────────────────────────────


def ensure_board_desenvolvimento() -> str:
	"""Garante que o quadro de desenvolvimento exista. Idempotente."""
	existente = frappe.db.get_value("Board", _BOARD_FILTROS, "name")
	if existente:
		return str(existente)

	board = frappe.get_doc(
		{
			"doctype": "Board",
			"titulo": BOARD_DESENVOLVIMENTO_TITULO,
			"referencia_doctype": "Module Def",
			"referencia_nome": MODULE_DEF,
		}
	).insert(ignore_permissions=True)
	return board.name


def _desenvolvedores_ativos() -> set[str]:
	linhas = frappe.get_all(
		"Has Role",
		filters={"role": ROLE_DESENVOLVEDOR, "parenttype": "User"},
		fields=["parent"],
		limit_page_length=0,
	)
	candidatos = {(linha["parent"] or "").strip() for linha in linhas if linha.get("parent")}
	if not candidatos:
		return set()

	ativos = frappe.get_all(
		"User",
		filters={"name": ["in", list(candidatos)], "enabled": 1},
		fields=["name"],
		limit_page_length=0,
	)
	return {linha["name"] for linha in ativos}


def sincronizar_desenvolvedores_no_board() -> None:
	"""Reconcilia `usuarios_autorizados` com quem tem a role Desenvolvedor.

	Diferente do append-only de `board_sync.py` e `board_sync_festa.py`: aqui
	perder a role precisa tirar o acesso ao quadro, entao a reconciliacao remove
	quem saiu.
	"""
	board_name = ensure_board_desenvolvimento()
	esperados = _desenvolvedores_ativos()

	board = frappe.get_doc("Board", board_name)
	atuais = {(linha.user or "").strip() for linha in (board.usuarios_autorizados or [])}

	if atuais == esperados:
		return

	board.usuarios_autorizados = []
	for user in sorted(esperados):
		board.append(
			"usuarios_autorizados",
			{"user": user, "nivel_acesso": _NIVEL_DESENVOLVEDOR, "adicionado_em": nowdate()},
		)

	board.flags.ignore_version = True
	board.save(ignore_permissions=True)


def on_user_update(doc, method=None) -> None:
	"""Hook `on_update` em User: entra ou sai do quadro conforme a role.

	Roda em todo save de User, entao decide com `doc.roles` (a versao recem
	salva, sem risco de cache de papeis defasado) e so escreve quando ha
	divergencia real — o caso comum e nao fazer nada.
	"""
	# Administrator nao e excluido aqui: `_desenvolvedores_ativos` tambem nao o
	# exclui, e divergir faria a role concedida a ele nunca chegar ao quadro.
	user = (getattr(doc, "name", "") or "").strip()
	if not user or user == "Guest":
		return

	tem_role = any(
		(getattr(linha, "role", "") or "").strip() == ROLE_DESENVOLVEDOR
		for linha in (getattr(doc, "roles", None) or [])
	)
	deveria_estar = bool(tem_role and getattr(doc, "enabled", 1))

	board_name = frappe.db.get_value("Board", _BOARD_FILTROS, "name")
	if not board_name:
		if not deveria_estar:
			return
		board_name = ensure_board_desenvolvimento()

	esta_no_board = bool(
		frappe.db.exists("Board User", {"parent": board_name, "parenttype": "Board", "user": user})
	)
	if esta_no_board == deveria_estar:
		return

	sincronizar_desenvolvedores_no_board()


# ───────────────────────── Tarefa espelho ─────────────────────────


def _titulo_da_tarefa(sugestao) -> str:
	tipo = (getattr(sugestao, "tipo", "") or "").strip()
	titulo = (getattr(sugestao, "titulo", "") or "").strip()
	return f"[{tipo}] {titulo}".strip() if tipo else titulo


def _observacoes_iniciais(sugestao) -> str:
	"""Contexto gravado uma unica vez, na criacao da tarefa.

	Nao e reescrito nos syncs seguintes de proposito: o desenvolvedor usa este
	campo para anotar o andamento em "Minhas tarefas", e sobrescrever apagaria
	essas anotacoes.
	"""
	partes = [f"Solicitação {sugestao.name} · Módulo: {sugestao.modulo}"]

	autor = (sugestao.solicitante_nome or sugestao.solicitante or "").strip()
	if autor:
		quando = format_datetime(sugestao.data_submissao, "dd/MM/yyyy") if sugestao.data_submissao else ""
		partes.append(f"Aberta por {autor}{f' em {quando}' if quando else ''}.")

	# `descricao` vem do editor WYSIWYG (HTML); `observacoes` da tarefa e Small
	# Text e e renderizado como texto puro em "Minhas tarefas".
	descricao = strip_html((sugestao.descricao or "").replace("</p>", "\n").replace("<br>", "\n")).strip()
	if descricao:
		partes.append("")
		partes.append(descricao)

	partes.append("")
	partes.append("Acompanhe em /sugestoes/acompanhamento")
	return "\n".join(partes)


def _aplicar(doc, valores: dict[str, object]) -> bool:
	"""Escreve so o que mudou. Retorna True se algum campo foi alterado."""
	mudou = False
	for campo, novo in valores.items():
		atual = doc.get(campo)
		# Normaliza vazios: "" e None sao o mesmo estado para Link e Select.
		if (atual or None) == (novo or None):
			continue
		doc.set(campo, novo)
		mudou = True
	return mudou


def sincronizar_tarefa_da_sugestao(doc, method=None) -> None:
	"""Hook `on_update` em Sugestao ou Problema: cria ou atualiza a tarefa espelho."""
	if frappe.flags.get(_FLAG_SYNC):
		return

	responsavel = (getattr(doc, "responsavel", "") or "").strip()
	tarefa_name = (getattr(doc, "tarefa", "") or "").strip()

	if not responsavel and not tarefa_name:
		# Ainda em triagem, sem ninguem alocado: nao ha tarefa a manter.
		return

	frappe.flags[_FLAG_SYNC] = True
	try:
		if not tarefa_name:
			if not responsavel:
				return
			tarefa = _criar_tarefa(doc, responsavel)
			doc.db_set("tarefa", tarefa.name, update_modified=False)
			return

		tarefa = frappe.get_doc(DOCTYPE_TAREFA, tarefa_name)
		valores = {
			"descricao": _titulo_da_tarefa(doc),
			# Sem responsavel a tarefa some de "Minhas tarefas", que e o efeito
			# desejado ao desalocar — sem apagar o registro nem os comentarios.
			"responsavel": responsavel or None,
			"status": STATUS_TAREFA_POR_COLUNA.get(doc.status, tarefa.status),
		}
		if _aplicar(tarefa, valores):
			tarefa.save(ignore_permissions=True)
	finally:
		frappe.flags[_FLAG_SYNC] = False


def _criar_tarefa(sugestao, responsavel: str):
	"""Cria a tarefa espelho.

	`ignore_permissions` e necessario aqui: quem aloca e um Desenvolvedor de
	portal, que nao tem permissao de criar "Gestao de Tarefas" (esse DocType so
	da create para System Manager e Editor de projetos). A autorizacao ja
	aconteceu no save da solicitacao — esta escrita e consequencia do sistema,
	nao uma acao direta do usuario.
	"""
	board_name = ensure_board_desenvolvimento()
	return frappe.get_doc(
		{
			"doctype": DOCTYPE_TAREFA,
			"board": board_name,
			"descricao": _titulo_da_tarefa(sugestao),
			"responsavel": responsavel,
			"status": STATUS_TAREFA_POR_COLUNA.get(sugestao.status),
			"data_inicio": nowdate(),
			"observacoes": _observacoes_iniciais(sugestao),
		}
	).insert(ignore_permissions=True)


def sincronizar_sugestao_da_tarefa(doc, method=None) -> None:
	"""Hook `on_update` em Gestao de Tarefas: devolve o status para a sugestao.

	`Atrasado` nao aparece em `COLUNA_POR_STATUS_TAREFA` de proposito. Ele e
	atribuido pelo cron das 03:00 (`validar_tarefas_atrasadas`), e mapea-lo faria
	um item em "Selecionado para desenvolvimento" saltar de coluna sozinho
	durante a madrugada.
	"""
	if frappe.flags.get(_FLAG_SYNC):
		return

	nova_coluna = COLUNA_POR_STATUS_TAREFA.get((getattr(doc, "status", "") or "").strip())
	if not nova_coluna:
		return

	sugestao_name = frappe.db.get_value(DOCTYPE_SUGESTAO, {"tarefa": doc.name}, "name")
	if not sugestao_name:
		return

	if frappe.db.get_value(DOCTYPE_SUGESTAO, sugestao_name, "status") == nova_coluna:
		return

	frappe.flags[_FLAG_SYNC] = True
	try:
		sugestao = frappe.get_doc(DOCTYPE_SUGESTAO, sugestao_name)
		sugestao.status = nova_coluna
		sugestao.save(ignore_permissions=True)
	finally:
		frappe.flags[_FLAG_SYNC] = False


def soltar_vinculo_da_tarefa(doc, method=None) -> None:
	"""Hook `on_trash` em Gestao de Tarefas: limpa o Link na solicitacao.

	Sem isto a solicitacao fica apontando para uma tarefa inexistente e nao
	consegue mais ser salva: `_validate_links` roda *antes* de `validate` e de
	`on_update`, entao nao ha ponto no ciclo de save onde consertar o vinculo —
	tem de ser no momento da exclusao.
	"""
	sugestao_name = frappe.db.get_value(DOCTYPE_SUGESTAO, {"tarefa": doc.name}, "name")
	if not sugestao_name:
		return

	frappe.db.set_value(DOCTYPE_SUGESTAO, sugestao_name, "tarefa", None, update_modified=False)
