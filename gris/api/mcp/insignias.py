"""Ferramentas MCP do fluxo de insígnias e distintivos.

Reaproveita a regra de negócio já existente em ``gris.api.insignias``: o
catálogo (``consultas``), o fluxo de status da solicitação (``endpoints``) e
as regras de acesso (``permissoes``). Aqui só expomos leitura, listas
paginadas e as ações de escrita com simulação, seguindo o mesmo padrão dos
demais módulos desta integração.

Fluxo da solicitação: Solicitada -> Comprada -> Recebida -> Entregue, com
Cancelada como saída até a etapa de recebimento (ver
``solicitacao_de_insignias.TRANSICOES_PERMITIDAS``).
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import flt

from gris.api.insignias import consultas, endpoints, permissoes
from gris.api.mcp.registry import ErroDeFerramenta, ferramenta, normalizar_limite
from gris.gris.doctype.solicitacao_de_insignias.solicitacao_de_insignias import (
	STATUS_CANCELADA,
	STATUS_COMPRADA,
	STATUS_ENTREGUE,
	STATUS_RECEBIDA,
	STATUS_SOLICITADA,
)

DOCTYPE = "Solicitacao de Insignias"
CATALOGO_DOCTYPE = "Insignia ou Distintivo"

ROLES_SOLICITANTE = ("Equipe de Metodos", "Gestor de Metodos")
ROLES_GESTOR_METODOS = ("Gestor de Metodos",)
ROLES_FINANCEIRO = ("Gestor Financeiro",)
# Quem lê o catálogo e a fila (a visibilidade de "quais pedidos" é aplicada no handler).
ROLES_LEITURA = ("Equipe de Metodos", "Gestor de Metodos", "Gestor Financeiro")
# Entrega e cancelamento dependem do status: o solicitante, a gestão de métodos e o
# financeiro podem chamar a ferramenta, mas ``permissoes`` decide caso a caso.
ROLES_ENTREGA_OU_CANCELAMENTO = ("Equipe de Metodos", "Gestor de Metodos", "Gestor Financeiro")

STATUS_VALIDOS = (STATUS_SOLICITADA, STATUS_COMPRADA, STATUS_RECEBIDA, STATUS_ENTREGUE, STATUS_CANCELADA)

# Teto defensivo para a listagem de solicitações antes de paginar em memória
# (mesmo padrão do funil de recepção).
MAX_REGISTROS_ANALISADOS = 500


@ferramenta(
	nome="listar_catalogo_insignias",
	titulo="Listar catálogo de insígnias e distintivos",
	descricao=(
		"Lista os itens do catálogo (distintivos de progressão, especialidades, insígnias "
		"especiais, distintivos de identificação/função) com tipo, ramo e valor unitário de "
		"referência usado no cálculo do valor estimado das solicitações."
	),
	parametros={
		"apenas_ativos": {
			"type": "boolean",
			"default": True,
			"description": "Se falso, inclui também os itens inativados.",
		},
		"tipo": {"type": "string", "enum": list(endpoints.TIPOS_VALIDOS), "description": "Filtra por tipo."},
		"ramo": {
			"type": "string",
			"enum": list(endpoints.RAMOS_CATALOGO_VALIDOS),
			"description": "Filtra por ramo.",
		},
	},
	roles=ROLES_LEITURA,
)
def listar_catalogo_insignias(
	apenas_ativos: bool = True, tipo: str | None = None, ramo: str | None = None
) -> dict:
	itens = consultas.listar_catalogo_completo()
	if apenas_ativos:
		itens = [item for item in itens if item["ativo"]]
	if tipo:
		itens = [item for item in itens if item.get("tipo") == tipo]
	if ramo:
		itens = [item for item in itens if item.get("ramo") == ramo]
	return {"catalogo": itens, "total": len(itens)}


@ferramenta(
	nome="salvar_item_catalogo_insignias",
	titulo="Criar ou editar item do catálogo",
	descricao=(
		"Cria um novo item do catálogo de insígnias/distintivos ou edita um existente "
		"(informe 'name' para editar). O nome é a chave do registro e não muda depois de "
		"criado. Use simular=true para conferir antes de gravar."
	),
	parametros={
		"name": {
			"type": "string",
			"description": "Identificador do item a editar. Deixe vazio para criar um novo.",
		},
		"nome": {"type": "string", "description": "Nome do item (obrigatório ao criar; mín. 3 caracteres)."},
		"tipo": {"type": "string", "enum": list(endpoints.TIPOS_VALIDOS), "description": "Tipo do item."},
		"ramo": {
			"type": "string",
			"enum": list(endpoints.RAMOS_CATALOGO_VALIDOS),
			"description": "Ramo do item ('Todos' quando não é específico de um ramo).",
		},
		"valor_unitario": {"type": "number", "description": "Valor unitário de referência."},
		"codigo": {"type": "string", "description": "Código no catálogo da Loja Escoteira, se houver."},
		"descricao": {"type": "string", "description": "Descrição do item."},
	},
	obrigatorios=("tipo", "ramo", "valor_unitario"),
	roles=ROLES_GESTOR_METODOS,
	somente_leitura=False,
)
def salvar_item_catalogo_insignias(
	name: str | None = None,
	nome: str | None = None,
	tipo: str | None = None,
	ramo: str | None = None,
	valor_unitario: float | None = None,
	codigo: str | None = None,
	descricao: str | None = None,
	simular: bool = False,
) -> dict:
	if tipo not in endpoints.TIPOS_VALIDOS:
		raise ErroDeFerramenta(
			"ARGUMENTO_INVALIDO", "Selecione um tipo válido.", {"opcoes": list(endpoints.TIPOS_VALIDOS)}
		)
	if ramo not in endpoints.RAMOS_CATALOGO_VALIDOS:
		raise ErroDeFerramenta(
			"ARGUMENTO_INVALIDO", "Selecione um ramo válido.", {"opcoes": list(endpoints.RAMOS_CATALOGO_VALIDOS)}
		)
	if flt(valor_unitario) < 0:
		raise ErroDeFerramenta("ARGUMENTO_INVALIDO", "O valor unitário não pode ser negativo.")

	criado = not name
	if name and not frappe.db.exists(CATALOGO_DOCTYPE, name):
		raise ErroDeFerramenta("NAO_ENCONTRADO", f"Item do catálogo '{name}' não encontrado.")

	nome_normalizado = (nome or "").strip()
	if criado:
		if len(nome_normalizado) < 3:
			raise ErroDeFerramenta("ARGUMENTO_INVALIDO", "Informe um nome com pelo menos 3 caracteres.")
		if frappe.db.exists(CATALOGO_DOCTYPE, nome_normalizado):
			raise ErroDeFerramenta("VALIDACAO", f"Já existe um item chamado '{nome_normalizado}'.")

	dados = {
		"name": name,
		"nome": nome,
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
	nome="alternar_item_catalogo_insignias",
	titulo="Ativar ou inativar item do catálogo",
	descricao=(
		"Alterna o item entre ativo e inativo. Não há exclusão: itens inativos continuam "
		"visíveis em pedidos antigos, só somem das opções para novas solicitações."
	),
	parametros={"name": {"type": "string", "description": "Identificador do item do catálogo."}},
	obrigatorios=("name",),
	roles=ROLES_GESTOR_METODOS,
	somente_leitura=False,
)
def alternar_item_catalogo_insignias(name: str, simular: bool = False) -> dict:
	atual = frappe.db.get_value(CATALOGO_DOCTYPE, name, ["ativo"], as_dict=True)
	if atual is None:
		raise ErroDeFerramenta("NAO_ENCONTRADO", f"Item do catálogo '{name}' não encontrado.")

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
	nome="listar_solicitacoes_insignias",
	titulo="Listar solicitações de insígnias e distintivos",
	descricao=(
		"Lista as solicitações do fluxo Solicitada -> Comprada -> Recebida -> Entregue, com "
		"resumo por status. Quem só pode solicitar (Equipe de Metodos) enxerga apenas os "
		"próprios pedidos; gestão de métodos e financeiro enxergam a fila completa e podem "
		"filtrar por solicitante."
	),
	parametros={
		"status": {"type": "string", "enum": list(STATUS_VALIDOS), "description": "Filtra por status."},
		"ramo": {
			"type": "string",
			"enum": list(endpoints.RAMOS_VALIDOS),
			"description": "Filtra por ramo/seção.",
		},
		"solicitante": {
			"type": "string",
			"description": "E-mail do solicitante (só tem efeito para quem enxerga a fila completa).",
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
	roles=ROLES_LEITURA,
)
def listar_solicitacoes_insignias(
	status: str | None = None,
	ramo: str | None = None,
	solicitante: str | None = None,
	limite: int = 25,
	inicio: int = 0,
) -> dict:
	filtros: dict[str, Any] = {}
	if status:
		filtros["status"] = status
	if ramo:
		filtros["ramo"] = ramo

	if permissoes.pode_ver_todas():
		if solicitante:
			filtros["solicitante"] = solicitante
	else:
		filtros["solicitante"] = frappe.session.user

	linhas = consultas.listar_solicitacoes(filtros, limite=MAX_REGISTROS_ANALISADOS)
	resumo = consultas.resumo_por_status(linhas)

	limite = normalizar_limite(limite)
	inicio = max(0, int(inicio or 0))
	pagina = linhas[inicio : inicio + limite]

	return {
		"solicitacoes": pagina,
		"resumo_por_status": resumo,
		"paginacao": {
			"inicio": inicio,
			"limite": limite,
			"retornados": len(pagina),
			"total_com_filtros": len(linhas),
			"teto_analisado": MAX_REGISTROS_ANALISADOS,
		},
	}


@ferramenta(
	nome="obter_solicitacao_insignias",
	titulo="Detalhar solicitação de insígnias",
	descricao=(
		"Ficha completa de uma solicitação: itens com beneficiário, linha do tempo, dados de "
		"compra/recebimento/entrega e o que o usuário atual pode fazer com ela."
	),
	parametros={"name": {"type": "string", "description": "Identificador da solicitação."}},
	obrigatorios=("name",),
	roles=ROLES_LEITURA,
)
def obter_solicitacao_insignias(name: str) -> dict:
	dados = consultas.carregar_solicitacao(name)
	if dados is None:
		raise ErroDeFerramenta("NAO_ENCONTRADO", f"Solicitação '{name}' não encontrada.")
	return {"solicitacao": dados}


@ferramenta(
	nome="criar_solicitacao_insignias",
	titulo="Criar solicitação de insígnias",
	descricao=(
		"Abre uma solicitação de insígnias/distintivos para um ramo, com uma lista de itens. "
		"Cada item precisa de 'insignia' (nome do item no catálogo) e 'quantidade'; "
		"opcionalmente 'beneficiario' (associado) e 'observacao'. O valor unitário vem sempre "
		"do catálogo, nunca do que for informado aqui. Use simular=true para ver o valor "
		"estimado antes de gravar."
	),
	parametros={
		"ramo": {
			"type": "string",
			"enum": list(endpoints.RAMOS_VALIDOS),
			"description": "Ramo/seção da solicitação.",
		},
		"itens": {
			"type": "array",
			"maxItems": endpoints.MAX_ITENS,
			"description": "Lista de itens (objetos com insignia, quantidade, beneficiario, observacao).",
		},
		"justificativa": {"type": "string", "description": "Justificativa ou observações gerais."},
	},
	obrigatorios=("ramo", "itens"),
	roles=ROLES_SOLICITANTE,
	somente_leitura=False,
)
def criar_solicitacao_insignias(
	ramo: str, itens: list, justificativa: str | None = None, simular: bool = False
) -> dict:
	if ramo not in endpoints.RAMOS_VALIDOS:
		raise ErroDeFerramenta(
			"ARGUMENTO_INVALIDO", "Selecione o ramo ou seção da solicitação.", {"opcoes": list(endpoints.RAMOS_VALIDOS)}
		)

	itens_normalizados = endpoints._normalizar_itens(itens)
	valor_estimado = flt(
		sum(item["valor_unitario"] * item["quantidade"] for item in itens_normalizados), 2
	)

	if simular:
		return {
			"simulacao": True,
			"criada": False,
			"ramo": ramo,
			"itens": itens_normalizados,
			"valor_estimado": valor_estimado,
		}

	resultado = endpoints.criar_solicitacao({"ramo": ramo, "itens": itens, "justificativa": justificativa})
	return {"criada": True, "name": resultado.get("name"), "valor_estimado": valor_estimado}


@ferramenta(
	nome="registrar_compra_insignias",
	titulo="Registrar compra de insígnias",
	descricao=(
		"Financeiro registra que a compra de uma solicitação em 'Solicitada' foi realizada, "
		"avançando o status para 'Comprada'."
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
	roles=ROLES_FINANCEIRO,
	somente_leitura=False,
)
def registrar_compra_insignias(
	name: str,
	data_compra: str,
	valor_pago: float,
	fornecedor: str | None = None,
	numero_documento: str | None = None,
	observacoes_compra: str | None = None,
	simular: bool = False,
) -> dict:
	atual = frappe.db.get_value(DOCTYPE, name, "status")
	if atual is None:
		raise ErroDeFerramenta("NAO_ENCONTRADO", f"Solicitação '{name}' não encontrada.")
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
	nome="registrar_recebimento_insignias",
	titulo="Registrar recebimento de insígnias",
	descricao=(
		"Financeiro confirma que o material de uma solicitação 'Comprada' chegou ao grupo, "
		"avançando o status para 'Recebida'."
	),
	parametros={
		"name": {"type": "string", "description": "Identificador da solicitação."},
		"data_recebimento": {
			"type": "string",
			"description": "Data de recebimento no grupo (AAAA-MM-DD, não pode ser futura).",
		},
	},
	obrigatorios=("name", "data_recebimento"),
	roles=ROLES_FINANCEIRO,
	somente_leitura=False,
)
def registrar_recebimento_insignias(name: str, data_recebimento: str, simular: bool = False) -> dict:
	atual = frappe.db.get_value(DOCTYPE, name, "status")
	if atual is None:
		raise ErroDeFerramenta("NAO_ENCONTRADO", f"Solicitação '{name}' não encontrada.")
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
	nome="registrar_entrega_insignias",
	titulo="Registrar entrega de insígnias",
	descricao=(
		"Confirma que o material foi entregue ao solicitante, encerrando o pedido. Pode ser "
		"registrada pelo próprio solicitante ou pela gestão de métodos/financeiro, mas só "
		"quando a solicitação está em 'Recebida'."
	),
	parametros={
		"name": {"type": "string", "description": "Identificador da solicitação."},
		"data_entrega": {"type": "string", "description": "Data da entrega (AAAA-MM-DD, não pode ser futura)."},
		"observacoes_entrega": {"type": "string", "description": "Observações da entrega."},
	},
	obrigatorios=("name", "data_entrega"),
	roles=ROLES_ENTREGA_OU_CANCELAMENTO,
	somente_leitura=False,
)
def registrar_entrega_insignias(
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
	nome="cancelar_solicitacao_insignias",
	titulo="Cancelar solicitação de insígnias",
	descricao=(
		"Cancela uma solicitação ainda não recebida. Antes da compra, o próprio solicitante ou "
		"a gestão de métodos cancelam; depois da compra, só financeiro/gestão de métodos "
		"desfazem (ex.: pedido cancelado no fornecedor)."
	),
	parametros={
		"name": {"type": "string", "description": "Identificador da solicitação."},
		"motivo": {"type": "string", "description": "Motivo do cancelamento."},
	},
	obrigatorios=("name", "motivo"),
	roles=ROLES_ENTREGA_OU_CANCELAMENTO,
	somente_leitura=False,
)
def cancelar_solicitacao_insignias(name: str, motivo: str, simular: bool = False) -> dict:
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
