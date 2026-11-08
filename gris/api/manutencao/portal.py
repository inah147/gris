# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Endpoints e consultas do portal de Manutenção.

Três níveis de acesso, nenhum deles `allow_guest`:

* **solicitar** — qualquer usuário autenticado;
* **acompanhar** (ver a fila de próximas manutenções) — qualquer usuário
  autenticado. A lista devolvida leva só o que interessa a quem pediu: nada de
  observações internas, custo ou nome de quem abriu as solicitações dos outros;
* **gerir** (prioridade, data prevista, execução, andamento) — papel
  `Gestor de Manutencao` ou System Manager.

O DocType não concede `create` nem `read` ao papel `All` de propósito: isso
abriria o Desk e a API REST com todos os campos, internos inclusive. Por isso
`solicitar` insere com `ignore_permissions` e as leituras públicas montam a
resposta campo a campo.

Contrato de resposta: sucesso devolve `{"ok": True, ...}`; falha usa
`frappe.throw`, que a página traduz em toast.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

import frappe
from frappe import _
from frappe.query_builder.functions import Count
from frappe.utils import add_days, add_to_date, flt, formatdate, getdate, now_datetime, nowdate

from gris.api.manutencao import constantes as c

DOCTYPE = c.DOCTYPE

# Campos que qualquer pessoa logada vê no acompanhamento.
CAMPOS_PUBLICOS: tuple[str, ...] = (
	"name",
	"titulo",
	"local",
	"categoria",
	"status",
	"prioridade",
	"descricao",
	"data_prevista",
	"data_solicitacao",
	"data_inicio",
	"data_conclusao",
	"resumo_execucao",
	"solicitante",
)

# A tela de gestão vê tudo.
CAMPOS_GESTAO: tuple[str, ...] = (
	*CAMPOS_PUBLICOS,
	"urgencia_informada",
	"responsavel_execucao",
	"custo_estimado",
	"observacoes_internas",
	"solicitante_nome",
)

# Campos que a gestão pode alterar pelo portal. O resto (solicitante, datas do
# fluxo, urgência informada) é registro do que aconteceu, não decisão.
CAMPOS_EDITAVEIS: tuple[str, ...] = (
	"titulo",
	"local",
	"categoria",
	"descricao",
	"status",
	"prioridade",
	"data_prevista",
	"responsavel_execucao",
	"custo_estimado",
	"observacoes_internas",
	"resumo_execucao",
)

FILTRO_ABERTAS = "abertas"
FILTRO_TODAS = "todas"

_DATA_MAXIMA = datetime.date.max


# ───────────────────────────── acesso ─────────────────────────────


def _require_logged_user() -> str:
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Você precisa estar autenticado."), frappe.PermissionError)
	return user


def pode_gerir(user: str | None = None) -> bool:
	"""Quem organiza a fila de manutenção."""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return False
	roles = frappe.get_roles(user)
	return c.ROLE_GESTOR in roles or "System Manager" in roles


def _require_gestor() -> str:
	user = _require_logged_user()
	if not pode_gerir(user):
		frappe.throw(
			_("Apenas quem tem o papel '{0}' pode organizar as manutenções.").format(c.ROLE_GESTOR),
			frappe.PermissionError,
		)
	return user


# ───────────────────────────── utilitários ─────────────────────────────


def _parse_payload(value: Any) -> dict[str, Any]:
	if isinstance(value, dict):
		return value
	if isinstance(value, str):
		try:
			parsed = json.loads(value)
		except ValueError:
			parsed = None
		if isinstance(parsed, dict):
			return parsed
	frappe.throw(_("Dados da solicitação inválidos."))
	return {}


def _texto(payload: dict[str, Any], campo: str) -> str:
	valor = payload.get(campo)
	return valor.strip() if isinstance(valor, str) else ""


def _carregar(name: str):
	"""Carrega a solicitação sem deixar escapar o 404 do `frappe.get_doc`.

	O handler de 404 do request.js abre o modal do Desk, que no portal aparece
	sem estilo; um `frappe.throw` comum vira toast.
	"""
	name = (name or "").strip()
	if not name or not frappe.db.exists(DOCTYPE, name):
		frappe.throw(_("Solicitação {0} não existe mais.").format(name or "?"))
	return frappe.get_doc(DOCTYPE, name)


def _como_data(valor: Any) -> datetime.date | None:
	if not valor:
		return None
	if isinstance(valor, datetime.datetime):
		return valor.date()
	if isinstance(valor, datetime.date):
		return valor
	return getdate(valor)


def _iso(valor: Any) -> str:
	data = _como_data(valor)
	return data.isoformat() if data else ""


def _fmt(valor: Any) -> str:
	data = _como_data(valor)
	return formatdate(data, "dd/MM/yyyy") if data else ""


def _peso(prioridade: str | None) -> int:
	return c.PESO_PRIORIDADE.get(prioridade or "", 0)


def _chave_proximas(item: dict[str, Any]) -> tuple:
	"""Ordem da fila pública: o que tem data mais cedo vem antes.

	Sem data prevista vai para o fim; entre iguais, a prioridade maior e depois
	quem pediu primeiro.
	"""
	return (
		_como_data(item.get("data_prevista")) or _DATA_MAXIMA,
		-_peso(item.get("prioridade")),
		item.get("data_solicitacao") or datetime.datetime.max,
	)


def _chave_gestao(item: dict[str, Any]) -> tuple:
	"""Ordem da tela de gestão: prioridade manda, depois a data prevista."""
	return (
		-_peso(item.get("prioridade")),
		_como_data(item.get("data_prevista")) or _DATA_MAXIMA,
		item.get("data_solicitacao") or datetime.datetime.max,
	)


def _atrasada(item: dict[str, Any], hoje: datetime.date) -> bool:
	data = _como_data(item.get("data_prevista"))
	return bool(data and data < hoje and item.get("status") in c.STATUS_ABERTOS)


# ───────────────────────────── solicitar ─────────────────────────────


def _checar_rate_limit(user: str) -> None:
	desde = add_to_date(now_datetime(), hours=-1)
	recentes = frappe.db.count(DOCTYPE, {"solicitante": user, "creation": [">=", desde]})
	if recentes >= c.LIMITE_ENVIOS_POR_HORA:
		frappe.throw(
			_("Você já enviou {0} solicitações na última hora. Tente novamente mais tarde.").format(
				c.LIMITE_ENVIOS_POR_HORA
			)
		)


@frappe.whitelist(methods=["POST"])
def solicitar(payload: Any) -> dict[str, Any]:
	"""Abre uma solicitação de manutenção. Aberto a qualquer usuário logado."""
	user = _require_logged_user()
	dados = _parse_payload(payload)

	titulo = _texto(dados, "titulo")
	local = _texto(dados, "local")
	categoria = _texto(dados, "categoria")
	urgencia = _texto(dados, "urgencia_informada")
	descricao = _texto(dados, "descricao")

	if not titulo:
		frappe.throw(_("Conte em poucas palavras o que precisa ser feito."))
	if not local:
		frappe.throw(_("Informe onde fica o problema."))
	if categoria not in c.CATEGORIAS:
		frappe.throw(_("Escolha a categoria da manutenção."))
	if urgencia not in c.URGENCIAS:
		frappe.throw(_("Escolha a urgência."))
	if not descricao:
		frappe.throw(_("Descreva o problema."))

	_checar_rate_limit(user)

	# `ignore_permissions` porque a regra de negócio é "todo mundo com login pode
	# pedir", e o DocType não dá `create` ao papel `All` — isso abriria também a
	# leitura de todos os campos pelo Desk e pela API REST. A autorização aqui é
	# o login mais o rate limit; o conteúdo é validado pelo controller.
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"titulo": titulo,
			"local": local,
			"categoria": categoria,
			"urgencia_informada": urgencia,
			"descricao": descricao,
		}
	).insert(ignore_permissions=True)

	return {"ok": True, "name": doc.name, "status": doc.status}


# ───────────────────────────── acompanhar ─────────────────────────────


def _serializar_publico(linha: dict[str, Any], user: str, hoje: datetime.date) -> dict[str, Any]:
	finalizada = linha.get("status") in c.STATUS_FINAIS
	return {
		"name": linha["name"],
		"titulo": linha.get("titulo") or "",
		"local": linha.get("local") or "",
		"categoria": linha.get("categoria") or "",
		"status": linha.get("status") or "",
		"prioridade": linha.get("prioridade") or "",
		"descricao": linha.get("descricao") or "",
		"data_prevista": _iso(linha.get("data_prevista")),
		"data_prevista_fmt": _fmt(linha.get("data_prevista")),
		"data_solicitacao_fmt": _fmt(linha.get("data_solicitacao")),
		"data_inicio_fmt": _fmt(linha.get("data_inicio")),
		"data_conclusao_fmt": _fmt(linha.get("data_conclusao")),
		# O resumo da execução é escrito para quem pediu, mas só faz sentido
		# depois de encerrada; antes disso pode ser rascunho da gestão.
		"resumo_execucao": (linha.get("resumo_execucao") or "") if finalizada else "",
		"atrasada": _atrasada(linha, hoje),
		"eh_minha": linha.get("solicitante") == user,
	}


@frappe.whitelist()
def listar_acompanhamento(somente_minhas: Any = None) -> dict[str, Any]:
	"""Fila pública de manutenções, agrupada para a página de acompanhamento.

	Traz tudo que está aberto e o que foi encerrado nos últimos
	`DIAS_CONCLUIDAS_VISIVEIS` dias. O volume é pequeno (dezenas), então a
	ordenação acontece aqui, em Python, com as regras de `_chave_proximas`.
	"""
	user = _require_logged_user()
	minhas = str(somente_minhas or "").strip().lower() in {"1", "true", "sim", "on"}

	filtros: dict[str, Any] = {}
	if minhas:
		filtros["solicitante"] = user

	corte = add_days(nowdate(), -c.DIAS_CONCLUIDAS_VISIVEIS)
	# Abertas sempre; encerradas só as recentes. Duas consultas simples em vez
	# de um OR que o `get_all` não expressa junto com os demais filtros.
	abertas = frappe.get_all(
		DOCTYPE,
		filters={**filtros, "status": ["in", list(c.STATUS_ABERTOS)]},
		fields=list(CAMPOS_PUBLICOS),
		limit_page_length=0,
		ignore_permissions=True,
	)
	encerradas = frappe.get_all(
		DOCTYPE,
		filters={**filtros, "status": ["in", list(c.STATUS_FINAIS)], "modified": [">=", corte]},
		fields=list(CAMPOS_PUBLICOS),
		order_by="modified desc",
		limit_page_length=0,
		ignore_permissions=True,
	)

	hoje = getdate(nowdate())
	em_execucao, proximas, em_analise = [], [], []
	for linha in sorted(abertas, key=_chave_proximas):
		item = _serializar_publico(linha, user, hoje)
		if linha.get("status") in c.STATUS_EM_EXECUCAO:
			em_execucao.append(item)
		elif linha.get("status") == c.STATUS_PLANEJADA:
			proximas.append(item)
		else:
			em_analise.append(item)

	# Na fila de análise ainda não há data: a ordem que vale é a da prioridade
	# sugerida e, entre iguais, quem pediu primeiro.
	em_analise.sort(key=lambda item: -_peso(item["prioridade"]))

	return {
		"ok": True,
		"somente_minhas": minhas,
		"em_execucao": em_execucao,
		"proximas": proximas,
		"em_analise": em_analise,
		"encerradas": [_serializar_publico(linha, user, hoje) for linha in encerradas],
	}


# ───────────────────────────── gerir ─────────────────────────────


def _serializar_gestao(linha: dict[str, Any], hoje: datetime.date) -> dict[str, Any]:
	return {
		"name": linha["name"],
		"titulo": linha.get("titulo") or "",
		"local": linha.get("local") or "",
		"categoria": linha.get("categoria") or "",
		"status": linha.get("status") or "",
		"prioridade": linha.get("prioridade") or "",
		"urgencia_informada": linha.get("urgencia_informada") or "",
		"descricao": linha.get("descricao") or "",
		"data_prevista": _iso(linha.get("data_prevista")),
		"data_prevista_fmt": _fmt(linha.get("data_prevista")),
		"data_solicitacao_fmt": _fmt(linha.get("data_solicitacao")),
		"data_inicio_fmt": _fmt(linha.get("data_inicio")),
		"data_conclusao_fmt": _fmt(linha.get("data_conclusao")),
		"responsavel_execucao": linha.get("responsavel_execucao") or "",
		"custo_estimado": flt(linha.get("custo_estimado")) or None,
		"observacoes_internas": linha.get("observacoes_internas") or "",
		"resumo_execucao": linha.get("resumo_execucao") or "",
		"solicitante_nome": linha.get("solicitante_nome") or linha.get("solicitante") or "",
		"atrasada": _atrasada(linha, hoje),
	}


def _contagem_por_status() -> dict[str, int]:
	tabela = frappe.qb.DocType(DOCTYPE)
	linhas = (
		frappe.qb.from_(tabela)
		.select(tabela.status, Count(tabela.name).as_("total"))
		.groupby(tabela.status)
		.run(as_dict=True)
	)
	contagem = {status: 0 for status in c.STATUS}
	for linha in linhas:
		if linha.status in contagem:
			contagem[linha.status] = int(linha.total or 0)
	return contagem


def _contar_atrasadas() -> int:
	return frappe.db.count(
		DOCTYPE,
		{"status": ["in", list(c.STATUS_ABERTOS)], "data_prevista": ["<", nowdate()]},
	)


@frappe.whitelist()
def listar_gestao(
	status: str | None = None,
	prioridade: str | None = None,
	categoria: str | None = None,
	busca: str | None = None,
) -> dict[str, Any]:
	"""Solicitações para a tela de gestão, com filtros e resumo por status."""
	_require_gestor()

	status = (status or FILTRO_ABERTAS).strip()
	prioridade = (prioridade or "").strip()
	categoria = (categoria or "").strip()
	busca = (busca or "").strip()[:100]

	filtros: dict[str, Any] = {}
	if status == FILTRO_ABERTAS:
		filtros["status"] = ["in", list(c.STATUS_ABERTOS)]
	elif status in c.STATUS:
		filtros["status"] = status
	elif status != FILTRO_TODAS:
		frappe.throw(_("Filtro de status inválido: {0}.").format(status))

	if prioridade:
		if prioridade not in c.PRIORIDADES:
			frappe.throw(_("Filtro de prioridade inválido: {0}.").format(prioridade))
		filtros["prioridade"] = prioridade
	if categoria:
		if categoria not in c.CATEGORIAS:
			frappe.throw(_("Filtro de categoria inválido: {0}.").format(categoria))
		filtros["categoria"] = categoria

	or_filters = None
	if busca:
		termo = f"%{busca}%"
		or_filters = [
			["titulo", "like", termo],
			["local", "like", termo],
			["descricao", "like", termo],
			["name", "like", termo],
			["responsavel_execucao", "like", termo],
		]

	linhas = frappe.get_all(
		DOCTYPE,
		filters=filtros,
		or_filters=or_filters,
		fields=list(CAMPOS_GESTAO),
		limit_page_length=0,
	)

	hoje = getdate(nowdate())
	itens = [_serializar_gestao(linha, hoje) for linha in sorted(linhas, key=_chave_gestao)]

	return {
		"ok": True,
		"itens": itens,
		"contagem": _contagem_por_status(),
		"atrasadas": _contar_atrasadas(),
		"filtros": {"status": status, "prioridade": prioridade, "categoria": categoria, "busca": busca},
	}


def _normalizar_valor(campo: str, valor: Any) -> Any:
	if campo == "data_prevista":
		if valor in (None, ""):
			return None
		try:
			return getdate(valor)
		except Exception:
			frappe.throw(_("Data prevista inválida."))
	if campo == "custo_estimado":
		if valor in (None, ""):
			return None
		# `flt` engoliria "abc" como 0 sem avisar; o custo some sem ninguém perceber.
		try:
			return round(float(str(valor).replace(",", ".")), 2)
		except ValueError:
			frappe.throw(_("Custo estimado inválido."))
	if valor is None:
		return ""
	if not isinstance(valor, str):
		frappe.throw(_("Valor inválido para o campo {0}.").format(campo))
	return valor.strip()


def _mesmo_valor(campo: str, atual: Any, novo: Any) -> bool:
	"""Compara pelo significado, não pelo tipo.

	O banco devolve `None` onde o formulário manda "", `0.0` onde o custo está
	vazio e `date` onde o payload traz texto. Comparar cru marcava todo save do
	dialog como alteração, mesmo sem a pessoa ter mexido em nada.
	"""
	if campo == "data_prevista":
		return _como_data(atual) == _como_data(novo)
	if campo == "custo_estimado":
		return flt(atual, 2) == flt(novo, 2)
	return (atual or "") == (novo or "")


@frappe.whitelist(methods=["POST"])
def atualizar(name: str, payload: Any) -> dict[str, Any]:
	"""Grava as decisões da gestão: andamento, prioridade, data e execução.

	Só os campos presentes no payload são alterados, para a tela poder mandar
	uma mudança pontual (ex.: só o status) sem reenviar o formulário inteiro.
	"""
	_require_gestor()
	dados = _parse_payload(payload)
	doc = _carregar(name)

	alterou = False
	for campo in CAMPOS_EDITAVEIS:
		if campo not in dados:
			continue
		novo = _normalizar_valor(campo, dados.get(campo))
		if not _mesmo_valor(campo, doc.get(campo), novo):
			doc.set(campo, novo)
			alterou = True

	if alterou:
		# Sem `ignore_permissions`: o papel de gestão tem `write` no DocType, e o
		# System Manager também — a permissão do Frappe é a segunda trava.
		doc.save()

	hoje = getdate(nowdate())
	linha = {campo: doc.get(campo) for campo in CAMPOS_GESTAO}
	return {"ok": True, "alterou": alterou, "item": _serializar_gestao(linha, hoje)}
