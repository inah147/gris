"""Ferramentas MCP da agenda de visitas da recepção.

Delegam para ``gris.www.recepcao.agenda_visitas``, que já valida a
disponibilidade da data para o ramo (sábados livres de atividade da seção nos
próximos 60 dias) e mantém o campo ``visita_agendada`` do Novo Associado em dia.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import getdate

from gris.api.mcp.registry import ErroDeFerramenta, ferramenta, normalizar_limite

DOCTYPE = "Agenda de Visitas"
DOCTYPE_NOVO = "Novo Associado"

ROLES = ("Recepcao",)

RAMOS = ("Filhotes", "Lobinho", "Escoteiro", "Sênior", "Pioneiro")

ACOES = ("confirmar", "desconfirmar", "remarcar", "cancelar")


def _servico():
	from gris.www.recepcao import agenda_visitas

	return agenda_visitas


def _carregar_visita(visita: str) -> dict:
	dados = frappe.db.get_value(
		DOCTYPE, visita, ["name", "jovem", "data_da_visita", "ramo", "visita_confirmada"], as_dict=True
	)
	if dados is None:
		raise ErroDeFerramenta("NAO_ENCONTRADO", f"Visita '{visita}' não encontrada.")
	return dados


def _datas_disponiveis(ramo: str) -> list[dict]:
	return _servico().get_available_dates_for_ramo(ramo)


def _garantir_data_disponivel(ramo: str | None, data: str) -> None:
	if not ramo:
		raise ErroDeFerramenta(
			"VALIDACAO", "A pessoa não tem ramo definido — defina o ramo antes de agendar a visita."
		)
	alvo = getdate(data).strftime("%Y-%m-%d")
	disponiveis = {item["value"] for item in _datas_disponiveis(ramo)}
	if alvo not in disponiveis:
		raise ErroDeFerramenta(
			"VALIDACAO",
			f"{alvo} não está disponível para o ramo {ramo}. "
			"Consulte 'datas_disponiveis_visita' para ver as datas livres.",
			{"datas_disponiveis": sorted(disponiveis)},
		)


@ferramenta(
	nome="listar_visitas",
	titulo="Listar visitas agendadas",
	descricao=(
		"Lista as visitas da recepção por período, ramo e situação de confirmação, "
		"com o nome de quem vai visitar o grupo."
	),
	parametros={
		"data_inicio": {"type": "string", "description": "Início do período (AAAA-MM-DD)."},
		"data_fim": {"type": "string", "description": "Fim do período (AAAA-MM-DD)."},
		"ramo": {"type": "string", "enum": list(RAMOS), "description": "Filtra por ramo."},
		"confirmada": {
			"type": "boolean",
			"description": "true traz só as confirmadas; false, só as pendentes de confirmação.",
		},
		"limite": {
			"type": "integer",
			"default": 25,
			"minimum": 1,
			"maximum": 100,
			"description": "Registros por página (máx. 100).",
		},
		"inicio": {"type": "integer", "default": 0, "minimum": 0, "description": "Deslocamento."},
	},
	roles=ROLES,
)
def listar_visitas(
	data_inicio: str | None = None,
	data_fim: str | None = None,
	ramo: str | None = None,
	confirmada: bool | None = None,
	limite: int = 25,
	inicio: int = 0,
) -> dict:
	filtros: dict[str, Any] = {}
	if data_inicio and data_fim:
		filtros["data_da_visita"] = ["between", [data_inicio, data_fim]]
	elif data_inicio:
		filtros["data_da_visita"] = [">=", data_inicio]
	elif data_fim:
		filtros["data_da_visita"] = ["<=", data_fim]
	if ramo:
		filtros["ramo"] = ramo
	if confirmada is not None:
		filtros["visita_confirmada"] = 1 if confirmada else 0

	visitas = frappe.get_all(
		DOCTYPE,
		filters=filtros,
		fields=["name", "jovem", "data_da_visita", "ramo", "visita_confirmada"],
		order_by="data_da_visita asc",
		limit_page_length=normalizar_limite(limite),
		limit_start=max(0, int(inicio or 0)),
	)

	nomes = [visita["jovem"] for visita in visitas if visita.get("jovem")]
	pessoas = (
		{
			linha["name"]: linha["nome_completo"]
			for linha in frappe.get_all(
				DOCTYPE_NOVO, filters={"name": ["in", nomes]}, fields=["name", "nome_completo"]
			)
		}
		if nomes
		else {}
	)
	for visita in visitas:
		visita["nome_completo"] = pessoas.get(visita.get("jovem"))

	return {
		"visitas": visitas,
		"paginacao": {
			"inicio": max(0, int(inicio or 0)),
			"limite": normalizar_limite(limite),
			"retornados": len(visitas),
			"total_com_filtros": frappe.db.count(DOCTYPE, filtros),
		},
	}


@ferramenta(
	nome="datas_disponiveis_visita",
	titulo="Datas disponíveis para visita",
	descricao=(
		"Sábados livres nos próximos 60 dias para o ramo informado (exclui os dias com "
		"atividade da seção que não seja de abertura geral). Informe 'ramo' ou 'visita' "
		"— com 'visita', usa o ramo da visita que será remarcada."
	),
	parametros={
		"ramo": {"type": "string", "enum": list(RAMOS), "description": "Ramo pretendido."},
		"visita": {
			"type": "string",
			"description": "Identificador de uma visita existente (para remarcação).",
		},
	},
	roles=ROLES,
)
def datas_disponiveis_visita(ramo: str | None = None, visita: str | None = None) -> dict:
	if not ramo and not visita:
		raise ErroDeFerramenta("ARGUMENTO_INVALIDO", "Informe 'ramo' ou 'visita'.")

	if visita:
		_carregar_visita(visita)
		datas = _servico().get_available_visit_dates_for_reschedule(visita)
	else:
		datas = _datas_disponiveis(ramo)

	return {"ramo": ramo, "visita": visita, "datas": datas, "total": len(datas)}


@ferramenta(
	nome="agendar_visita",
	titulo="Agendar visita",
	descricao=(
		"Agenda a primeira visita de um novo associado em uma data disponível para o ramo "
		"dele. Marca a etapa 'visita_agendada' e move o status para 'Visita Agendada'."
	),
	parametros={
		"novo_associado": {"type": "string", "description": "Identificador do Novo Associado."},
		"data": {"type": "string", "description": "Data da visita (AAAA-MM-DD)."},
	},
	obrigatorios=("novo_associado", "data"),
	roles=ROLES,
	somente_leitura=False,
)
def agendar_visita(novo_associado: str, data: str, simular: bool = False) -> dict:
	dados = frappe.db.get_value(
		DOCTYPE_NOVO, novo_associado, ["name", "nome_completo", "ramo", "status"], as_dict=True
	)
	if dados is None:
		raise ErroDeFerramenta("NAO_ENCONTRADO", f"Novo Associado '{novo_associado}' não encontrado.")

	_garantir_data_disponivel(dados.get("ramo"), data)

	if simular:
		return {
			"simulacao": True,
			"agendado": False,
			"novo_associado": dados,
			"data": str(getdate(data)),
		}

	_servico().schedule_visit(novo_associado, data)
	return {
		"agendado": True,
		"novo_associado": novo_associado,
		"nome_completo": dados.get("nome_completo"),
		"data": str(getdate(data)),
		"ramo": dados.get("ramo"),
	}


@ferramenta(
	nome="atualizar_visita",
	titulo="Confirmar, remarcar ou cancelar visita",
	descricao=(
		"Age sobre uma visita já agendada: 'confirmar' e 'desconfirmar' mudam a confirmação, "
		"'remarcar' exige nova_data disponível para o ramo e 'cancelar' apaga a visita e "
		"desmarca a etapa 'visita_agendada' da pessoa."
	),
	parametros={
		"visita": {"type": "string", "description": "Identificador da visita."},
		"acao": {
			"type": "string",
			"enum": list(ACOES),
			"description": "O que fazer com a visita.",
		},
		"nova_data": {
			"type": "string",
			"description": "Nova data (AAAA-MM-DD), obrigatória para 'remarcar'.",
		},
	},
	obrigatorios=("visita", "acao"),
	roles=ROLES,
	somente_leitura=False,
)
def atualizar_visita(visita: str, acao: str, nova_data: str | None = None, simular: bool = False) -> dict:
	dados = _carregar_visita(visita)

	if acao == "remarcar":
		if not nova_data:
			raise ErroDeFerramenta("ARGUMENTO_INVALIDO", "Informe 'nova_data' para remarcar.")
		ramo = dados.get("ramo") or frappe.db.get_value(DOCTYPE_NOVO, dados.get("jovem"), "ramo")
		_garantir_data_disponivel(ramo, nova_data)

	if acao == "confirmar" and dados.get("visita_confirmada"):
		return {"atualizada": False, "motivo": "A visita já está confirmada."}
	if acao == "desconfirmar" and not dados.get("visita_confirmada"):
		return {"atualizada": False, "motivo": "A visita já está sem confirmação."}

	if simular:
		return {"simulacao": True, "atualizada": False, "acao": acao, "visita": dados}

	servico = _servico()
	if acao == "confirmar":
		servico.confirm_visit(visita)
	elif acao == "desconfirmar":
		servico.unconfirm_visit(visita)
	elif acao == "remarcar":
		servico.reschedule_visit(visita, nova_data)
	else:
		servico.cancel_visit(visita)

	return {
		"atualizada": True,
		"acao": acao,
		"visita": visita,
		"novo_associado": dados.get("jovem"),
		"nova_data": str(getdate(nova_data)) if acao == "remarcar" else None,
	}
