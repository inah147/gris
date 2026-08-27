"""Ferramentas MCP do módulo de Associados."""

from __future__ import annotations

from typing import Any

import frappe

from gris.api.mcp.registry import (
	ErroDeFerramenta,
	ferramenta,
	normalizar_limite,
)

DOCTYPE = "Associado"

ROLES_LEITURA = ("Gestor de Associados", "Visualizador Associados")
ROLES_ESCRITA = ("Gestor de Associados",)

CAMPOS_LISTA = [
	"name",
	"nome_completo",
	"data_de_nascimento",
	"ramo",
	"secao",
	"categoria",
	"funcao",
	"area",
	"status",
	"status_no_grupo",
	"validade_registro",
	"email",
	"telefone",
]

CAMPOS_DETALHE = [
	*CAMPOS_LISTA,
	"cpf",
	"sexo",
	"etnia",
	"registro",
	"tipo_registro",
	"registro_isento",
	"id_escoteiros",
	"eleito",
	"anos_afastamento",
	"cep_residencia",
	"numero_residencia",
	"nome_responsavel_1",
	"telefone_responsavel_1",
	"email_responsavel_1",
	"nome_responsavel_2",
	"telefone_responsavel_2",
	"email_responsavel_2",
	"valor_contribuicao",
	"qt_contribuicoes_pagas",
	"qt_contribuicoes_atrasadas",
	"email_cobranca",
	"telefone_cobranca",
	"status_cobranca",
	"inicio_do_pagamento",
]

# Campos que o Claude pode alterar. Deixamos de fora CPF (naming), campos de
# controle de notificação e contadores calculados pelo backend.
CAMPOS_EDITAVEIS = {
	"nome_completo",
	"email",
	"telefone",
	"sexo",
	"etnia",
	"religiao",
	"estado_civil",
	"id_escoteiros",
	"cep_residencia",
	"numero_residencia",
	"ramo",
	"secao",
	"area",
	"funcao",
	"categoria",
	"status",
	"status_no_grupo",
	"registro",
	"registro_isento",
	"tipo_registro",
	"validade_registro",
	"eleito",
	"nome_responsavel_1",
	"telefone_responsavel_1",
	"email_responsavel_1",
	"nome_responsavel_2",
	"telefone_responsavel_2",
	"email_responsavel_2",
	"valor_contribuicao",
	"email_cobranca",
	"telefone_cobranca",
	"status_cobranca",
	"inicio_do_pagamento",
}


def _validar_campo(meta, campo: str, valor: Any) -> Any:
	df = meta.get_field(campo)
	if not df:
		raise ErroDeFerramenta("ARGUMENTO_INVALIDO", f"Campo '{campo}' não existe em {DOCTYPE}.")

	if df.fieldtype == "Select":
		opcoes = [o for o in (df.options or "").split("\n") if o]
		if opcoes and valor not in opcoes:
			raise ErroDeFerramenta(
				"ARGUMENTO_INVALIDO",
				f"Valor inválido para '{campo}'. Opções aceitas: {', '.join(opcoes)}.",
				{"campo": campo, "opcoes": opcoes},
			)
	elif df.fieldtype == "Link":
		if valor and not frappe.db.exists(df.options, valor):
			raise ErroDeFerramenta(
				"NAO_ENCONTRADO",
				f"'{valor}' não existe em {df.options} (campo '{campo}').",
				{"campo": campo, "doctype": df.options},
			)
	elif df.fieldtype == "Check":
		valor = 1 if str(valor).strip().lower() in {"1", "true", "sim", "yes"} else 0

	return valor


@ferramenta(
	nome="listar_associados",
	titulo="Listar associados",
	descricao=(
		"Lista associados do grupo escoteiro com filtros e paginação. "
		"Use 'busca' para procurar por nome, CPF ou e-mail. "
		"Por padrão retorna apenas associados com status_no_grupo='Ativo'."
	),
	parametros={
		"busca": {"type": "string", "description": "Texto livre: nome, CPF ou e-mail."},
		"ramo": {
			"type": "string",
			"enum": ["Não se aplica", "Filhotes", "Lobinho", "Escoteiro", "Sênior", "Pioneiro"],
			"description": "Ramo do associado.",
		},
		"secao": {"type": "string", "description": "Seção (ex.: Alcateia, Tropa)."},
		"categoria": {"type": "string", "description": "Categoria do registro (ex.: Beneficiário)."},
		"area": {"type": "string", "description": "Unidade Organizacional (campo 'area')."},
		"status": {
			"type": "string",
			"enum": ["Válido", "Vencido", "Desconhecido"],
			"description": "Status do registro nacional.",
		},
		"status_no_grupo": {
			"type": "string",
			"enum": ["Ativo", "Inativo", "Todos"],
			"default": "Ativo",
			"description": "Situação no grupo. Use 'Todos' para não filtrar.",
		},
		"limite": {
			"type": "integer",
			"default": 25,
			"minimum": 1,
			"maximum": 100,
			"description": "Quantidade de registros por página (máx. 100).",
		},
		"inicio": {
			"type": "integer",
			"default": 0,
			"minimum": 0,
			"description": "Deslocamento para paginação.",
		},
	},
	roles=ROLES_LEITURA,
)
def listar_associados(
	busca: str | None = None,
	ramo: str | None = None,
	secao: str | None = None,
	categoria: str | None = None,
	area: str | None = None,
	status: str | None = None,
	status_no_grupo: str = "Ativo",
	limite: int = 25,
	inicio: int = 0,
) -> dict:
	filtros: dict[str, Any] = {}
	if status_no_grupo and status_no_grupo != "Todos":
		filtros["status_no_grupo"] = status_no_grupo
	for campo, valor in (
		("ramo", ramo),
		("secao", secao),
		("categoria", categoria),
		("area", area),
		("status", status),
	):
		if valor:
			filtros[campo] = valor

	or_filters = None
	if busca:
		termo = f"%{busca}%"
		or_filters = {
			"nome_completo": ["like", termo],
			"cpf": ["like", termo],
			"email": ["like", termo],
		}

	registros = frappe.get_all(
		DOCTYPE,
		filters=filtros,
		or_filters=or_filters,
		fields=CAMPOS_LISTA,
		order_by="nome_completo asc",
		limit_page_length=normalizar_limite(limite),
		limit_start=max(0, int(inicio or 0)),
	)
	total = frappe.db.count(DOCTYPE, filtros) if not or_filters else None

	return {
		"associados": registros,
		"paginacao": {
			"inicio": max(0, int(inicio or 0)),
			"limite": normalizar_limite(limite),
			"retornados": len(registros),
			"total_com_filtros": total,
		},
	}


@ferramenta(
	nome="obter_associado",
	titulo="Detalhar associado",
	descricao=(
		"Retorna a ficha completa de um associado a partir do CPF (que é o identificador "
		"do registro), incluindo responsáveis, dados de contribuição e histórico no grupo."
	),
	parametros={
		"cpf": {"type": "string", "description": "CPF do associado (identificador do registro)."},
	},
	obrigatorios=("cpf",),
	roles=ROLES_LEITURA,
)
def obter_associado(cpf: str) -> dict:
	if not frappe.db.exists(DOCTYPE, cpf):
		raise ErroDeFerramenta(
			"NAO_ENCONTRADO",
			f"Nenhum associado encontrado com o CPF '{cpf}'. Use 'listar_associados' com busca.",
		)

	doc = frappe.get_doc(DOCTYPE, cpf)
	doc.check_permission("read")

	dados = {campo: doc.get(campo) for campo in CAMPOS_DETALHE}
	dados["name"] = doc.name
	dados["historico_no_grupo"] = [
		{
			"data_de_ingresso": linha.data_de_ingresso,
			"data_de_desligamento": linha.data_de_desligamento,
		}
		for linha in (doc.get("historico_no_grupo") or [])
	]
	return {"associado": dados, "campos_editaveis": sorted(CAMPOS_EDITAVEIS)}


@ferramenta(
	nome="atualizar_associado",
	titulo="Atualizar dados do associado",
	descricao=(
		"Atualiza campos de um associado. Aceita apenas os campos listados em "
		"'campos_editaveis' de 'obter_associado'; valores de campos Select e Link "
		"são validados contra o schema antes de gravar."
	),
	parametros={
		"cpf": {"type": "string", "description": "CPF do associado a atualizar."},
		"campos": {
			"type": "object",
			"description": "Objeto {campo: valor} com os dados a gravar.",
		},
	},
	obrigatorios=("cpf", "campos"),
	roles=ROLES_ESCRITA,
	somente_leitura=False,
)
def atualizar_associado(cpf: str, campos: dict) -> dict:
	if not campos:
		raise ErroDeFerramenta("ARGUMENTO_INVALIDO", "Informe ao menos um campo para atualizar.")

	nao_permitidos = sorted(set(campos) - CAMPOS_EDITAVEIS)
	if nao_permitidos:
		raise ErroDeFerramenta(
			"ARGUMENTO_INVALIDO",
			f"Campos não editáveis por esta ferramenta: {', '.join(nao_permitidos)}.",
			{"campos_editaveis": sorted(CAMPOS_EDITAVEIS)},
		)

	if not frappe.db.exists(DOCTYPE, cpf):
		raise ErroDeFerramenta("NAO_ENCONTRADO", f"Nenhum associado encontrado com o CPF '{cpf}'.")

	doc = frappe.get_doc(DOCTYPE, cpf)
	doc.check_permission("write")
	meta = frappe.get_meta(DOCTYPE)

	alteracoes: dict[str, dict] = {}
	for campo, valor in campos.items():
		valor_validado = _validar_campo(meta, campo, valor)
		anterior = doc.get(campo)
		if anterior == valor_validado:
			continue
		doc.set(campo, valor_validado)
		alteracoes[campo] = {"de": anterior, "para": valor_validado}

	if not alteracoes:
		return {"atualizado": False, "motivo": "Nenhum valor diferente do atual.", "alteracoes": {}}

	doc.save()
	frappe.db.commit()

	return {"atualizado": True, "cpf": doc.name, "alteracoes": alteracoes}


@ferramenta(
	nome="estatisticas_associados",
	titulo="Estatísticas de associados",
	descricao=(
		"Totais de associados agrupados por ramo, categoria, seção, status de registro "
		"e situação no grupo. Útil para responder perguntas quantitativas sem listar tudo."
	),
	parametros={
		"somente_ativos": {
			"type": "boolean",
			"default": True,
			"description": "Considerar apenas associados com status_no_grupo='Ativo'.",
		},
	},
	roles=(*ROLES_LEITURA, "Visualizador de Métricas de Associados"),
)
def estatisticas_associados(somente_ativos: bool = True) -> dict:
	filtros = {"status_no_grupo": "Ativo"} if somente_ativos else {}

	def agrupar(campo: str) -> list[dict]:
		linhas = frappe.get_all(
			DOCTYPE,
			filters=filtros,
			fields=[campo, "count(name) as total"],
			group_by=campo,
			order_by="total desc",
		)
		return [{"valor": linha.get(campo) or "(vazio)", "total": linha["total"]} for linha in linhas]

	return {
		"total": frappe.db.count(DOCTYPE, filtros),
		"somente_ativos": bool(somente_ativos),
		"por_ramo": agrupar("ramo"),
		"por_categoria": agrupar("categoria"),
		"por_secao": agrupar("secao"),
		"por_status_registro": agrupar("status"),
		"por_status_no_grupo": agrupar("status_no_grupo"),
	}
