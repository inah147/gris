"""Ferramentas MCP do módulo de Compras (Manutenção, Programa Educativo e Administrativo).

Reaproveita a regra de negócio já existente em ``gris.api.compras``: o catálogo
(``consultas``), o fluxo de status da solicitação (``endpoints``) e as regras de
acesso por área (``permissoes``). Aqui só expomos leitura, listas paginadas e as
ações de escrita com simulação, seguindo o mesmo padrão dos demais módulos desta
integração.

Fluxo da solicitação: Solicitada -> Comprada -> Recebida -> Entregue, com
Cancelada como saída até a etapa de recebimento (ver
``solicitacao_de_compra.TRANSICOES_PERMITIDAS``).

Quem pode o quê (decidido por ``permissoes``, não pelos papéis da ferramenta):
qualquer pessoa logada solicita em qualquer área e cadastra itens de Manutenção e
Administrativo; insígnias e distintivos (Programa Educativo) só o Gestor de Metodos
cadastra; comprar, receber e editar/inativar itens é do gestor da área; o Gestor
Financeiro acompanha a fila sem agir.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import flt

from gris.api.compras import consultas, endpoints, permissoes
from gris.api.mcp.registry import ErroDeFerramenta, ferramenta, normalizar_limite
from gris.gris.doctype.solicitacao_de_compra.solicitacao_de_compra import (
	STATUS_CANCELADA,
	STATUS_COMPRADA,
	STATUS_ENTREGUE,
	STATUS_RECEBIDA,
	STATUS_SOLICITADA,
)

DOCTYPE = "Solicitacao de Compra"
CATALOGO_DOCTYPE = "Item de Catalogo de Compras"

# Compra, recebimento e inativação de item: só os gestores de área chamam a
# ferramenta; ``permissoes`` confere a área de cada registro.
ROLES_GESTORES = permissoes.ROLES_GESTORES

STATUS_VALIDOS = (STATUS_SOLICITADA, STATUS_COMPRADA, STATUS_RECEBIDA, STATUS_ENTREGUE, STATUS_CANCELADA)
AREAS_VALIDAS = list(permissoes.AREAS_VALIDAS)

# Teto defensivo para a listagem de solicitações antes de paginar em memória
# (mesmo padrão do funil de recepção).
MAX_REGISTROS_ANALISADOS = 500

PARAMETRO_AREA = {
	"type": "string",
	"enum": AREAS_VALIDAS,
	"description": "Área de compras: Manutenção, Programa Educativo (insígnias e distintivos) ou Administrativo.",
}


def _validar_area(area: str | None) -> str:
	if area not in permissoes.AREAS:
		raise ErroDeFerramenta("ARGUMENTO_INVALIDO", "Informe uma área válida.", {"opcoes": AREAS_VALIDAS})
	return area


@ferramenta(
	nome="listar_catalogo_compras",
	titulo="Listar catálogo de compras",
	descricao=(
		"Lista os itens do catálogo de compras com área, valor unitário de referência (usado "
		"no valor estimado das solicitações) e, no Programa Educativo, tipo e ramo das "
		"insígnias e distintivos. Cada item diz se o usuário atual pode editá-lo."
	),
	parametros={
		"area": PARAMETRO_AREA,
		"apenas_ativos": {
			"type": "boolean",
			"default": True,
			"description": "Se falso, inclui também os itens inativados.",
		},
		"tipo": {
			"type": "string",
			"enum": list(endpoints.TIPOS_VALIDOS),
			"description": "Filtra por tipo (só Programa Educativo).",
		},
		"ramo": {
			"type": "string",
			"enum": list(endpoints.RAMOS_CATALOGO_VALIDOS),
			"description": "Filtra por ramo (só Programa Educativo).",
		},
	},
)
def listar_catalogo_compras(
	area: str | None = None, apenas_ativos: bool = True, tipo: str | None = None, ramo: str | None = None
) -> dict:
	itens = consultas.listar_catalogo_completo([_validar_area(area)] if area else None)
	if apenas_ativos:
		itens = [item for item in itens if item["ativo"]]
	if tipo:
		itens = [item for item in itens if item.get("tipo") == tipo]
	if ramo:
		itens = [item for item in itens if item.get("ramo") == ramo]
	return {"catalogo": itens, "total": len(itens)}


@ferramenta(
	nome="salvar_item_catalogo_compras",
	titulo="Criar ou editar item do catálogo de compras",
	descricao=(
		"Cria um novo item do catálogo de compras ou edita um existente (informe 'name' para "
		"editar). Qualquer pessoa cadastra itens de Manutenção e Administrativo; insígnias e "
		"distintivos (Programa Educativo) só o Gestor de Metodos. Editar é do gestor da área "
		"(ou de quem cadastrou, fora do Programa Educativo). Tipo e ramo só valem para o "
		"Programa Educativo. O nome é a chave do registro e não muda depois de criado. Use "
		"simular=true para conferir antes de gravar."
	),
	parametros={
		"name": {
			"type": "string",
			"description": "Identificador do item a editar. Deixe vazio para criar um novo.",
		},
		"nome": {"type": "string", "description": "Nome do item (obrigatório ao criar; mín. 3 caracteres)."},
		"area": PARAMETRO_AREA,
		"tipo": {
			"type": "string",
			"enum": list(endpoints.TIPOS_VALIDOS),
			"description": "Tipo do item (obrigatório no Programa Educativo).",
		},
		"ramo": {
			"type": "string",
			"enum": list(endpoints.RAMOS_CATALOGO_VALIDOS),
			"description": "Ramo do item, no Programa Educativo ('Todos' quando não é específico).",
		},
		"valor_unitario": {"type": "number", "description": "Valor unitário de referência."},
		"codigo": {"type": "string", "description": "Código do item no fornecedor, se houver."},
		"descricao": {"type": "string", "description": "Descrição do item."},
	},
	obrigatorios=("area", "valor_unitario"),
	somente_leitura=False,
)
def salvar_item_catalogo_compras(
	area: str,
	name: str | None = None,
	nome: str | None = None,
	tipo: str | None = None,
	ramo: str | None = None,
	valor_unitario: float | None = None,
	codigo: str | None = None,
	descricao: str | None = None,
	simular: bool = False,
) -> dict:
	_validar_area(area)
	if area == permissoes.AREA_PROGRAMA_EDUCATIVO:
		if tipo not in endpoints.TIPOS_VALIDOS:
			raise ErroDeFerramenta(
				"ARGUMENTO_INVALIDO", "Selecione um tipo válido.", {"opcoes": list(endpoints.TIPOS_VALIDOS)}
			)
		if ramo not in endpoints.RAMOS_CATALOGO_VALIDOS:
			raise ErroDeFerramenta(
				"ARGUMENTO_INVALIDO",
				"Selecione um ramo válido.",
				{"opcoes": list(endpoints.RAMOS_CATALOGO_VALIDOS)},
			)
	else:
		tipo = ramo = None
	if flt(valor_unitario) < 0:
		raise ErroDeFerramenta("ARGUMENTO_INVALIDO", "O valor unitário não pode ser negativo.")

	criado = not name
	if name:
		existente = frappe.db.get_value(CATALOGO_DOCTYPE, name, ["area", "owner"], as_dict=True)
		if existente is None:
			raise ErroDeFerramenta("NAO_ENCONTRADO", f"Item do catálogo '{name}' não encontrado.")
		if not permissoes.pode_editar_item(existente) or (
			area != existente.area and not permissoes.pode_cadastrar_item(area)
		):
			raise ErroDeFerramenta("PERMISSAO_NEGADA", "Apenas o gestor da área pode alterar este item.")
	elif not permissoes.pode_cadastrar_item(area):
		raise ErroDeFerramenta(
			"PERMISSAO_NEGADA", "Apenas a gestão de métodos cadastra insígnias e distintivos no catálogo."
		)

	nome_normalizado = (nome or "").strip()
	if criado:
		if len(nome_normalizado) < 3:
			raise ErroDeFerramenta("ARGUMENTO_INVALIDO", "Informe um nome com pelo menos 3 caracteres.")
		if frappe.db.exists(CATALOGO_DOCTYPE, nome_normalizado):
			raise ErroDeFerramenta("VALIDACAO", f"Já existe um item chamado '{nome_normalizado}'.")

	dados = {
		"name": name,
		"nome": nome,
		"area": area,
		"tipo": tipo,
		"ramo": ramo,
		"valor_unitario": valor_unitario,
		"codigo": codigo,
		"descricao": descricao,
	}

	if simular:
		return {"simulacao": True, "salvo": False, "criado": criado, "previa": dados}

	resultado = endpoints.salvar_item_catalogo(dados)
	return {"salvo": True, "criado": resultado.get("criado", criado), "name": resultado.get("name")}


@ferramenta(
	nome="alternar_item_catalogo_compras",
	titulo="Ativar ou inativar item do catálogo",
	descricao=(
		"Alterna o item entre ativo e inativo. Não há exclusão: itens inativos continuam "
		"visíveis em pedidos antigos, só somem das opções para novas solicitações."
	),
	parametros={"name": {"type": "string", "description": "Identificador do item do catálogo."}},
	obrigatorios=("name",),
	somente_leitura=False,
)
def alternar_item_catalogo_compras(name: str, simular: bool = False) -> dict:
	atual = frappe.db.get_value(CATALOGO_DOCTYPE, name, ["ativo", "area", "owner"], as_dict=True)
	if atual is None:
		raise ErroDeFerramenta("NAO_ENCONTRADO", f"Item do catálogo '{name}' não encontrado.")
	if not permissoes.pode_editar_item(atual):
		raise ErroDeFerramenta("PERMISSAO_NEGADA", "Apenas o gestor da área pode alterar este item.")

	novo_ativo = not bool(atual.ativo)
	if simular:
		return {
			"simulacao": True,
			"alternado": False,
			"name": name,
			"alteracao": {"ativo": {"de": bool(atual.ativo), "para": novo_ativo}},
		}

	resultado = endpoints.alternar_item_catalogo({"name": name})
	return {"alternado": True, "name": name, "ativo": resultado.get("ativo")}


@ferramenta(
	nome="listar_solicitacoes_compra",
	titulo="Listar solicitações de compra",
	descricao=(
		"Lista as solicitações do fluxo Solicitada -> Comprada -> Recebida -> Entregue, com "
		"resumo por status. Por padrão traz só as que aguardam compra ('Solicitada'): o que "
		"já foi comprado ou encerrado só aparece pedindo explicitamente, com 'status' ou "
		"incluir_todas=true. Cada pessoa vê os próprios pedidos e, nas áreas que gerencia "
		"(ou todas, para o Gestor Financeiro), a fila inteira, podendo filtrar por solicitante."
	),
	parametros={
		"area": PARAMETRO_AREA,
		"status": {"type": "string", "enum": list(STATUS_VALIDOS), "description": "Filtra por status."},
		"incluir_todas": {
			"type": "boolean",
			"default": False,
			"description": "Se verdadeiro (e sem 'status'), inclui também comprados, recebidos e encerrados.",
		},
		"ramo": {
			"type": "string",
			"enum": list(endpoints.RAMOS_VALIDOS),
			"description": "Filtra por ramo/seção.",
		},
		"solicitante": {
			"type": "string",
			"description": "E-mail do solicitante (só tem efeito nas áreas cuja fila o usuário enxerga).",
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
)
def listar_solicitacoes_compra(
	area: str | None = None,
	status: str | None = None,
	incluir_todas: bool = False,
	ramo: str | None = None,
	solicitante: str | None = None,
	limite: int = 25,
	inicio: int = 0,
) -> dict:
	filtros: dict[str, Any] = {}
	if area:
		filtros["area"] = _validar_area(area)
	if ramo:
		filtros["ramo"] = ramo

	areas_fila = permissoes.areas_para(permissoes.pode_ver_fila)
	if area:
		areas_fila = [a for a in areas_fila if a == area]
	usuario = frappe.session.user

	if areas_fila and solicitante:
		filtros["solicitante"] = solicitante
		filtros["area"] = ["in", areas_fila]
		or_filtros = None
	elif areas_fila:
		# Fila inteira das áreas que acompanha, mais os próprios pedidos nas demais.
		or_filtros = {"area": ["in", areas_fila], "solicitante": usuario}
	else:
		filtros["solicitante"] = usuario
		or_filtros = None

	# O resumo conta todos os status; a lista segue o filtro (por padrão, só 'Solicitada').
	todas = consultas.listar_solicitacoes(filtros, limite=MAX_REGISTROS_ANALISADOS, or_filtros=or_filtros)
	resumo = consultas.resumo_por_status(todas)
	visiveis = consultas.status_visiveis(status, consultas.MOSTRAR_TODAS if incluir_todas else None)
	linhas = todas if visiveis is None else [linha for linha in todas if linha["status"] in visiveis]

	limite = normalizar_limite(limite)
	inicio = max(0, int(inicio or 0))
	pagina = linhas[inicio : inicio + limite]

	return {
		"solicitacoes": pagina,
		"resumo_por_status": resumo,
		"status_listados": visiveis or list(STATUS_VALIDOS),
		"paginacao": {
			"inicio": inicio,
			"limite": limite,
			"retornados": len(pagina),
			"total_com_filtros": len(linhas),
			"teto_analisado": MAX_REGISTROS_ANALISADOS,
		},
	}


@ferramenta(
	nome="obter_solicitacao_compra",
	titulo="Detalhar solicitação de compra",
	descricao=(
		"Ficha completa de uma solicitação: área, itens, linha do tempo, dados de "
		"compra/recebimento/entrega e o que o usuário atual pode fazer com ela."
	),
	parametros={"name": {"type": "string", "description": "Identificador da solicitação."}},
	obrigatorios=("name",),
)
def obter_solicitacao_compra(name: str) -> dict:
	dados = consultas.carregar_solicitacao(name)
	if dados is None:
		raise ErroDeFerramenta("NAO_ENCONTRADO", f"Solicitação '{name}' não encontrada.")
	return {"solicitacao": dados}


@ferramenta(
	nome="criar_solicitacao_compra",
	titulo="Criar solicitação de compra",
	descricao=(
		"Abre uma solicitação de compra numa área, com uma lista de itens do catálogo daquela "
		"área. Qualquer pessoa logada pode solicitar. Cada item precisa de 'item_catalogo' "
		"(nome do item no catálogo) e 'quantidade'; 'observacao' é opcional. No Programa "
		"Educativo (insígnias e distintivos) informe também o 'ramo'. O valor unitário vem "
		"sempre do catálogo, nunca do que for informado aqui. Se o item não existir, cadastre-o "
		"antes com salvar_item_catalogo_compras. Use simular=true para ver o valor estimado."
	),
	parametros={
		"area": PARAMETRO_AREA,
		"ramo": {
			"type": "string",
			"enum": list(endpoints.RAMOS_VALIDOS),
			"description": "Ramo/seção da solicitação (obrigatório no Programa Educativo).",
		},
		"itens": {
			"type": "array",
			"maxItems": endpoints.MAX_ITENS,
			"description": "Lista de itens (objetos com item_catalogo, quantidade e observacao).",
		},
		"justificativa": {"type": "string", "description": "Justificativa ou observações gerais."},
	},
	obrigatorios=("area", "itens"),
	somente_leitura=False,
)
def criar_solicitacao_compra(
	area: str, itens: list, ramo: str | None = None, justificativa: str | None = None, simular: bool = False
) -> dict:
	_validar_area(area)
	if area == permissoes.AREA_PROGRAMA_EDUCATIVO and ramo not in endpoints.RAMOS_VALIDOS:
		raise ErroDeFerramenta(
			"ARGUMENTO_INVALIDO",
			"Selecione o ramo ou seção da solicitação.",
			{"opcoes": list(endpoints.RAMOS_VALIDOS)},
		)
	if area != permissoes.AREA_PROGRAMA_EDUCATIVO:
		ramo = None

	itens_normalizados = endpoints._normalizar_itens(itens, area)
	valor_estimado = flt(sum(item["valor_unitario"] * item["quantidade"] for item in itens_normalizados), 2)

	if simular:
		return {
			"simulacao": True,
			"criada": False,
			"area": area,
			"ramo": ramo,
			"itens": itens_normalizados,
			"valor_estimado": valor_estimado,
		}

	resultado = endpoints.criar_solicitacao(
		{"area": area, "ramo": ramo, "itens": itens, "justificativa": justificativa}
	)
	return {"criada": True, "name": resultado.get("name"), "valor_estimado": valor_estimado}


@ferramenta(
	nome="registrar_compra",
	titulo="Registrar compra",
	descricao=(
		"O gestor da área (Gestor de Metodos no Programa Educativo, Gestor de Manutencao, "
		"Gestor Administrativo) registra que a compra de uma solicitação em 'Solicitada' foi "
		"realizada, avançando o status para 'Comprada'."
	),
	parametros={
		"name": {"type": "string", "description": "Identificador da solicitação."},
		"data_compra": {"type": "string", "description": "Data da compra (AAAA-MM-DD, não pode ser futura)."},
		"valor_pago": {"type": "number", "description": "Valor efetivamente pago."},
		"fornecedor": {"type": "string", "description": "Fornecedor da compra."},
		"numero_documento": {"type": "string", "description": "Nota fiscal ou número do pedido."},
		"observacoes_compra": {"type": "string", "description": "Observações da compra."},
	},
	obrigatorios=("name", "data_compra", "valor_pago"),
	roles=ROLES_GESTORES,
	somente_leitura=False,
)
def registrar_compra(
	name: str,
	data_compra: str,
	valor_pago: float,
	fornecedor: str | None = None,
	numero_documento: str | None = None,
	observacoes_compra: str | None = None,
	simular: bool = False,
) -> dict:
	registro = frappe.db.get_value(DOCTYPE, name, ["status", "area"], as_dict=True)
	if registro is None:
		raise ErroDeFerramenta("NAO_ENCONTRADO", f"Solicitação '{name}' não encontrada.")
	if not permissoes.pode_comprar(registro.area):
		raise ErroDeFerramenta(
			"PERMISSAO_NEGADA", f"Apenas o gestor de {registro.area} registra a compra desta solicitação."
		)
	atual = registro.status
	if atual != STATUS_SOLICITADA:
		raise ErroDeFerramenta(
			"VALIDACAO",
			f"Só é possível registrar a compra de uma solicitação em '{STATUS_SOLICITADA}' (está em '{atual}').",
		)

	if simular:
		return {
			"simulacao": True,
			"registrado": False,
			"name": name,
			"alteracao": {"status": {"de": atual, "para": STATUS_COMPRADA}, "valor_pago": valor_pago},
		}

	resultado = endpoints.registrar_compra(
		{
			"name": name,
			"data_compra": data_compra,
			"valor_pago": valor_pago,
			"fornecedor": fornecedor,
			"numero_documento": numero_documento,
			"observacoes_compra": observacoes_compra,
		}
	)
	return {"registrado": True, "name": resultado.get("name"), "status": resultado.get("status")}


@ferramenta(
	nome="registrar_recebimento_compra",
	titulo="Registrar recebimento da compra",
	descricao=(
		"O gestor da área confirma que o material de uma solicitação 'Comprada' chegou ao "
		"grupo, avançando o status para 'Recebida'."
	),
	parametros={
		"name": {"type": "string", "description": "Identificador da solicitação."},
		"data_recebimento": {
			"type": "string",
			"description": "Data de recebimento no grupo (AAAA-MM-DD, não pode ser futura).",
		},
	},
	obrigatorios=("name", "data_recebimento"),
	roles=ROLES_GESTORES,
	somente_leitura=False,
)
def registrar_recebimento_compra(name: str, data_recebimento: str, simular: bool = False) -> dict:
	registro = frappe.db.get_value(DOCTYPE, name, ["status", "area"], as_dict=True)
	if registro is None:
		raise ErroDeFerramenta("NAO_ENCONTRADO", f"Solicitação '{name}' não encontrada.")
	if not permissoes.pode_comprar(registro.area):
		raise ErroDeFerramenta(
			"PERMISSAO_NEGADA",
			f"Apenas o gestor de {registro.area} registra o recebimento desta solicitação.",
		)
	atual = registro.status
	if atual != STATUS_COMPRADA:
		raise ErroDeFerramenta(
			"VALIDACAO",
			f"Só é possível registrar o recebimento de uma solicitação em '{STATUS_COMPRADA}' (está em '{atual}').",
		)

	if simular:
		return {
			"simulacao": True,
			"registrado": False,
			"name": name,
			"alteracao": {"status": {"de": atual, "para": STATUS_RECEBIDA}},
		}

	resultado = endpoints.registrar_recebimento({"name": name, "data_recebimento": data_recebimento})
	return {"registrado": True, "name": resultado.get("name"), "status": resultado.get("status")}


@ferramenta(
	nome="registrar_entrega_compra",
	titulo="Registrar entrega da compra",
	descricao=(
		"Confirma que o material foi entregue ao solicitante, encerrando o pedido. Pode ser "
		"registrada pelo próprio solicitante ou pelo gestor da área, mas só quando a "
		"solicitação está em 'Recebida'."
	),
	parametros={
		"name": {"type": "string", "description": "Identificador da solicitação."},
		"data_entrega": {
			"type": "string",
			"description": "Data da entrega (AAAA-MM-DD, não pode ser futura).",
		},
		"observacoes_entrega": {"type": "string", "description": "Observações da entrega."},
	},
	obrigatorios=("name", "data_entrega"),
	somente_leitura=False,
)
def registrar_entrega_compra(
	name: str, data_entrega: str, observacoes_entrega: str | None = None, simular: bool = False
) -> dict:
	if not frappe.db.exists(DOCTYPE, name):
		raise ErroDeFerramenta("NAO_ENCONTRADO", f"Solicitação '{name}' não encontrada.")

	doc = frappe.get_doc(DOCTYPE, name)
	if not permissoes.pode_registrar_entrega(doc):
		raise ErroDeFerramenta(
			"PERMISSAO_NEGADA", "Você não tem permissão para registrar a entrega desta solicitação."
		)

	if simular:
		return {
			"simulacao": True,
			"registrado": False,
			"name": name,
			"alteracao": {"status": {"de": doc.status, "para": STATUS_ENTREGUE}},
		}

	resultado = endpoints.registrar_entrega(
		{"name": name, "data_entrega": data_entrega, "observacoes_entrega": observacoes_entrega}
	)
	return {"registrado": True, "name": resultado.get("name"), "status": resultado.get("status")}


@ferramenta(
	nome="cancelar_solicitacao_compra",
	titulo="Cancelar solicitação de compra",
	descricao=(
		"Cancela uma solicitação ainda não recebida. Antes da compra, o próprio solicitante ou "
		"o gestor da área cancelam; depois da compra, só o gestor da área desfaz (ex.: pedido "
		"cancelado no fornecedor)."
	),
	parametros={
		"name": {"type": "string", "description": "Identificador da solicitação."},
		"motivo": {"type": "string", "description": "Motivo do cancelamento."},
	},
	obrigatorios=("name", "motivo"),
	somente_leitura=False,
)
def cancelar_solicitacao_compra(name: str, motivo: str, simular: bool = False) -> dict:
	if not frappe.db.exists(DOCTYPE, name):
		raise ErroDeFerramenta("NAO_ENCONTRADO", f"Solicitação '{name}' não encontrada.")

	doc = frappe.get_doc(DOCTYPE, name)
	if not permissoes.pode_cancelar(doc):
		raise ErroDeFerramenta("PERMISSAO_NEGADA", "Você não tem permissão para cancelar esta solicitação.")

	if simular:
		return {
			"simulacao": True,
			"cancelada": False,
			"name": name,
			"alteracao": {"status": {"de": doc.status, "para": STATUS_CANCELADA}},
		}

	resultado = endpoints.cancelar_solicitacao({"name": name, "motivo": motivo})
	return {"cancelada": True, "name": resultado.get("name"), "status": resultado.get("status")}
