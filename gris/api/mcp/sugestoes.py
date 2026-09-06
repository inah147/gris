"""Ferramentas MCP do módulo Sugestões e Problemas.

Casca fina sobre `gris.api.sugestoes.portal`: a autorização (quem acompanha o
quadro, quem tria) e a regra de negócio (sync com a tarefa espelho, aviso por
WhatsApp ao comentar) já vivem lá e no hook de `Comment` registrado em
`hooks.py`. Nada aqui reimplementa isso.
"""

from __future__ import annotations

import frappe

from gris.api.mcp.registry import ErroDeFerramenta, ferramenta, normalizar_limite
from gris.api.sugestoes import portal as servico
from gris.api.sugestoes.constantes import COLUNAS, MODULOS, ROLE_ACOMPANHAMENTO, ROLE_DESENVOLVEDOR, TIPOS

DOCTYPE = "Sugestao ou Problema"

ROLES_LEITURA = (ROLE_ACOMPANHAMENTO, ROLE_DESENVOLVEDOR)
ROLES_TRIAGEM = (ROLE_DESENVOLVEDOR,)


def _garantir_registro(name: str) -> None:
	if not frappe.db.exists(DOCTYPE, name):
		raise ErroDeFerramenta(
			"NAO_ENCONTRADO", f"Solicitação '{name}' não encontrada. Use 'listar_sugestoes'."
		)


@ferramenta(
	nome="listar_sugestoes",
	titulo="Listar sugestões e problemas",
	descricao=(
		"Lista o quadro de Sugestões e Problemas com filtros por status (coluna), tipo, "
		"módulo, responsável e busca por título."
	),
	parametros={
		"status": {"type": "string", "enum": list(COLUNAS), "description": "Coluna do quadro."},
		"tipo": {"type": "string", "enum": list(TIPOS), "description": "Problema ou Nova funcionalidade."},
		"modulo": {"type": "string", "enum": list(MODULOS), "description": "Módulo do sistema."},
		"responsavel": {"type": "string", "description": "E-mail de quem está desenvolvendo."},
		"sem_responsavel": {
			"type": "boolean",
			"description": "Se true, traz apenas quem ainda não tem responsável alocado.",
		},
		"busca": {"type": "string", "description": "Parte do título."},
		"limite": {
			"type": "integer",
			"default": 25,
			"minimum": 1,
			"maximum": 100,
			"description": "Registros por página (máx. 100).",
		},
		"inicio": {"type": "integer", "default": 0, "minimum": 0, "description": "Deslocamento."},
	},
	roles=ROLES_LEITURA,
)
def listar_sugestoes(
	status: str | None = None,
	tipo: str | None = None,
	modulo: str | None = None,
	responsavel: str | None = None,
	sem_responsavel: bool | None = None,
	busca: str | None = None,
	limite: int = 25,
	inicio: int = 0,
) -> dict:
	filtros: dict = {}
	if status:
		filtros["status"] = status
	if tipo:
		filtros["tipo"] = tipo
	if modulo:
		filtros["modulo"] = modulo
	if sem_responsavel:
		filtros["responsavel"] = ["in", [None, ""]]
	elif responsavel:
		filtros["responsavel"] = responsavel
	if busca:
		filtros["titulo"] = ["like", f"%{busca}%"]

	total = frappe.db.count(DOCTYPE, filtros)

	limite = normalizar_limite(limite)
	inicio = max(0, int(inicio or 0))

	linhas = frappe.get_all(
		DOCTYPE,
		filters=filtros,
		fields=list(servico.CARD_FIELDS),
		order_by=servico.CARD_ORDER_BY,
		limit_page_length=limite,
		limit_start=inicio,
	)

	return {
		"sugestoes": linhas,
		"paginacao": {
			"inicio": inicio,
			"limite": limite,
			"retornados": len(linhas),
			"total_com_filtros": total,
		},
	}


@ferramenta(
	nome="obter_sugestao",
	titulo="Detalhar sugestão ou problema",
	descricao="Ficha completa de uma solicitação: descrição, linha do tempo e comentários.",
	parametros={"name": {"type": "string", "description": "Identificador da solicitação (ex.: SUG-00001)."}},
	obrigatorios=("name",),
	roles=ROLES_LEITURA,
)
def obter_sugestao(name: str) -> dict:
	_garantir_registro(name)
	resposta = servico.detalhes(name)
	resposta.pop("ok", None)
	return resposta


@ferramenta(
	nome="atualizar_sugestao",
	titulo="Atualizar sugestão ou problema",
	descricao=(
		"Move de coluna (status), reclassifica o tipo, aloca um responsável ou reescreve a "
		"descrição. Informe só os campos que quer alterar. Reservado a quem tria o quadro."
	),
	parametros={
		"name": {"type": "string", "description": "Identificador da solicitação."},
		"status": {"type": "string", "enum": list(COLUNAS), "description": "Nova coluna do quadro."},
		"tipo": {"type": "string", "enum": list(TIPOS), "description": "Reclassifica o tipo."},
		"responsavel": {
			"type": "string",
			"description": "E-mail de quem vai desenvolver (precisa ter o papel Desenvolvedor).",
		},
		"descricao": {"type": "string", "description": "Novo texto da descrição."},
	},
	obrigatorios=("name",),
	roles=ROLES_TRIAGEM,
	somente_leitura=False,
)
def atualizar_sugestao(
	name: str,
	status: str | None = None,
	tipo: str | None = None,
	responsavel: str | None = None,
	descricao: str | None = None,
	simular: bool = False,
) -> dict:
	_garantir_registro(name)

	if not any([status, tipo, responsavel, descricao]):
		raise ErroDeFerramenta("ARGUMENTO_INVALIDO", "Informe ao menos um campo para atualizar.")

	if simular:
		atual = frappe.db.get_value(DOCTYPE, name, ["status", "tipo", "responsavel"], as_dict=True) or {}
		alteracoes: dict = {}
		if status and status != atual.get("status"):
			alteracoes["status"] = {"de": atual.get("status"), "para": status}
		if tipo and tipo != atual.get("tipo"):
			alteracoes["tipo"] = {"de": atual.get("tipo"), "para": tipo}
		if responsavel and responsavel != atual.get("responsavel"):
			alteracoes["responsavel"] = {"de": atual.get("responsavel"), "para": responsavel}
		if descricao:
			alteracoes["descricao"] = {"alterada": True}
		return {"simulacao": True, "atualizado": False, "name": name, "alteracoes": alteracoes}

	resultado: dict = {"name": name}
	# Cada chamada reaproveita o endpoint do portal, que já valida e já
	# dispara o sync com a tarefa espelho quando necessário.
	if status:
		resultado["status"] = servico.atualizar_status(name, status).get("status")
	if tipo:
		saida = servico.reclassificar(name, tipo)
		resultado["tipo"] = saida.get("tipo")
		resultado["status"] = saida.get("status")
	if responsavel:
		saida = servico.alocar_responsavel(name, responsavel)
		resultado["responsavel"] = saida.get("responsavel")
		resultado["responsavel_nome"] = saida.get("responsavel_nome")
	if descricao:
		resultado["descricao"] = servico.atualizar_descricao(name, descricao).get("descricao")

	return {"atualizado": True, **resultado}


@ferramenta(
	nome="comentar_sugestao",
	titulo="Comentar em uma sugestão ou problema",
	descricao=(
		"Adiciona um comentário na solicitação. Dispara um aviso por WhatsApp para quem "
		"abriu e para o responsável pelo desenvolvimento, quando houver um e não for quem "
		"comentou."
	),
	parametros={
		"name": {"type": "string", "description": "Identificador da solicitação."},
		"texto": {"type": "string", "description": "Conteúdo do comentário."},
	},
	obrigatorios=("name", "texto"),
	roles=ROLES_LEITURA,
	somente_leitura=False,
)
def comentar_sugestao(name: str, texto: str, simular: bool = False) -> dict:
	_garantir_registro(name)

	texto = (texto or "").strip()
	if not texto:
		raise ErroDeFerramenta("ARGUMENTO_INVALIDO", "O comentário não pode estar vazio.")

	if simular:
		return {"simulacao": True, "comentado": False, "name": name, "texto": texto}

	resposta = servico.adicionar_comentario(name, texto)
	return {"comentado": True, "name": name, "comentarios": resposta.get("comentarios", [])}
