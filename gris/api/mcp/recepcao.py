"""Ferramentas MCP do funil de recepção de novos associados.

O cálculo das etapas e da cadência esperada vem de ``gris.api.recepcao_funil`` —
o mesmo módulo que alimenta o kanban de ``/recepcao/visao_geral``. As ações
delegam para os serviços já existentes em ``gris.api.recepcao`` e nas páginas do
portal.

Fora do escopo por serem irreversíveis: ``processar_desistencia`` e
``registrar_desistencia`` da fila apagam registros e anonimizam o login do
responsável (LGPD). Continuam só pelo portal.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import getdate

from gris.api import recepcao as servico
from gris.api.mcp.registry import ErroDeFerramenta, ferramenta, normalizar_limite
from gris.api.recepcao_funil import (
	CAMPOS_DE_ETAPA,
	STEPS_DEF,
	calcular_etapas,
	carregar_configuracao,
	data_da_ultima_visita,
	resumo_etapas,
)

DOCTYPE = "Novo Associado"
DOCTYPE_FILA = "Fila de Espera"

ROLES = ("Recepcao",)

STATUS_VALIDOS = (
	"Novo Contato",
	"Conversa Inicial",
	"Visita Agendada",
	"Aguardar Dados",
	"Fazer Registro",
	"Acompanhamento",
	"Fila de espera",
	"Concluído",
)
RAMOS = ("Filhotes", "Lobinho", "Escoteiro", "Sênior", "Pioneiro")

# Teto defensivo: as etapas são calculadas em memória, então lemos um bloco
# limitado antes de filtrar e paginar.
MAX_REGISTROS_ANALISADOS = 500

CAMPOS_LISTA = [
	"name",
	"nome_completo",
	"status",
	"ramo",
	"tipo_de_registro",
	"responsavel_recepcao",
	"data_de_nascimento",
	"modified",
	*CAMPOS_DE_ETAPA,
]

CAMPOS_CONTATO = [
	"email",
	"celular",
	"telefone_secundario",
	"cep",
	"endereco",
	"numero",
	"bairro",
	"cidade",
	"estado",
	"escolaridade",
	"cpf",
	"rg",
]

ROTULOS_DE_ETAPA = {step["field"]: step["label"] for step in STEPS_DEF}


def _etapa_valida(etapa: str) -> str:
	if etapa not in CAMPOS_DE_ETAPA:
		raise ErroDeFerramenta(
			"ARGUMENTO_INVALIDO",
			f"Etapa '{etapa}' não existe no funil.",
			{"etapas": list(CAMPOS_DE_ETAPA)},
		)
	return etapa


def _garantir_registro(name: str) -> None:
	if not frappe.db.exists(DOCTYPE, name):
		raise ErroDeFerramenta(
			"NAO_ENCONTRADO",
			f"Novo Associado '{name}' não encontrado. Use 'listar_novos_associados'.",
		)


def _traduzir_etapas(etapas: list[dict]) -> list[dict]:
	"""Converte as chaves do kanban (inglês) para o vocabulário das ferramentas."""
	return [
		{
			"etapa": etapa["field"],
			"rotulo": etapa["label"],
			"concluida": etapa["completed"],
			"data_estimada": etapa.get("data_estimada"),
			"atrasada": bool(etapa.get("is_overdue")),
		}
		for etapa in etapas
	]


def _com_etapas(registros: list[dict], config: dict) -> list[dict]:
	"""Anexa etapas, progresso e dados da visita a cada registro da lista."""
	visitas = data_da_ultima_visita([linha["name"] for linha in registros])
	hoje = getdate()

	enriquecidos = []
	for linha in registros:
		visita = visitas.get(linha["name"])
		etapas = calcular_etapas(linha, config, visita.data_da_visita if visita else None, hoje)
		linha = dict(linha)
		for campo in CAMPOS_DE_ETAPA:
			linha.pop(campo, None)
		linha["progresso"] = resumo_etapas(etapas)
		linha["etapas"] = _traduzir_etapas(etapas)
		linha["visita"] = (
			{
				"name": visita.name,
				"data": str(visita.data_da_visita),
				"confirmada": bool(visita.visita_confirmada),
			}
			if visita
			else None
		)
		enriquecidos.append(linha)
	return enriquecidos


@ferramenta(
	nome="listar_novos_associados",
	titulo="Listar novos associados (funil)",
	descricao=(
		"Lista quem está no funil de recepção com o progresso das etapas. "
		"Use somente_atrasados=true para achar quem está travado, ou etapa_pendente "
		"para filtrar quem ainda não concluiu uma etapa específica. O atraso é medido "
		"pelos intervalos configurados em Configuracoes de Recepcao, a partir da visita."
	),
	parametros={
		"status": {
			"type": "string",
			"enum": list(STATUS_VALIDOS),
			"description": "Coluna do funil.",
		},
		"ramo": {"type": "string", "enum": list(RAMOS), "description": "Ramo pretendido."},
		"responsavel_recepcao": {
			"type": "string",
			"description": "E-mail do usuário responsável pelo acompanhamento.",
		},
		"sem_responsavel": {
			"type": "boolean",
			"description": "Se true, traz apenas quem está sem responsável de recepção.",
		},
		"busca": {"type": "string", "description": "Parte do nome da pessoa."},
		"etapa_pendente": {
			"type": "string",
			"enum": list(CAMPOS_DE_ETAPA),
			"description": "Traz apenas quem ainda não concluiu esta etapa.",
		},
		"somente_atrasados": {
			"type": "boolean",
			"description": "Traz apenas quem tem alguma etapa pendente com data estimada vencida.",
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
def listar_novos_associados(
	status: str | None = None,
	ramo: str | None = None,
	responsavel_recepcao: str | None = None,
	sem_responsavel: bool | None = None,
	busca: str | None = None,
	etapa_pendente: str | None = None,
	somente_atrasados: bool | None = None,
	limite: int = 25,
	inicio: int = 0,
) -> dict:
	filtros: dict[str, Any] = {}
	if status:
		filtros["status"] = status
	if ramo:
		filtros["ramo"] = ramo
	if responsavel_recepcao:
		filtros["responsavel_recepcao"] = responsavel_recepcao
	if sem_responsavel:
		filtros["responsavel_recepcao"] = ["in", [None, ""]]
	if busca:
		filtros["nome_completo"] = ["like", f"%{busca}%"]
	if etapa_pendente:
		filtros[_etapa_valida(etapa_pendente)] = 0

	registros = frappe.get_all(
		DOCTYPE,
		filters=filtros,
		fields=CAMPOS_LISTA,
		order_by="modified desc",
		limit_page_length=MAX_REGISTROS_ANALISADOS,
	)

	pessoas = _com_etapas(registros, carregar_configuracao())
	if somente_atrasados:
		pessoas = [pessoa for pessoa in pessoas if pessoa["progresso"]["atrasadas"]]

	limite = normalizar_limite(limite)
	inicio = max(0, int(inicio or 0))
	pagina = pessoas[inicio : inicio + limite]

	return {
		"novos_associados": pagina,
		"paginacao": {
			"inicio": inicio,
			"limite": limite,
			"retornados": len(pagina),
			"total_com_filtros": len(pessoas),
			"teto_analisado": MAX_REGISTROS_ANALISADOS,
		},
	}


@ferramenta(
	nome="obter_novo_associado",
	titulo="Detalhar novo associado",
	descricao=(
		"Ficha completa de quem está no funil: dados de contato, etapas com data estimada "
		"e atraso, visita agendada e responsáveis legais vinculados."
	),
	parametros={"name": {"type": "string", "description": "Identificador do Novo Associado."}},
	obrigatorios=("name",),
	roles=ROLES,
)
def obter_novo_associado(name: str) -> dict:
	_garantir_registro(name)

	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("read")

	dados = {campo: doc.get(campo) for campo in CAMPOS_LISTA if campo not in CAMPOS_DE_ETAPA}
	dados.update({campo: doc.get(campo) for campo in CAMPOS_CONTATO})
	dados["name"] = doc.name

	visita = data_da_ultima_visita([name]).get(name)
	etapas = calcular_etapas(
		doc.as_dict(), carregar_configuracao(), visita.data_da_visita if visita else None
	)

	vinculos = frappe.get_all(
		"Responsavel Vinculo",
		filters={"beneficiario_novo_associado": name},
		fields=["responsavel", "é_guardiao_legal", "primeiro_responsavel"],
	)
	responsaveis = []
	for vinculo in vinculos:
		if not vinculo.get("responsavel"):
			continue
		info = frappe.db.get_value(
			"Responsavel",
			vinculo["responsavel"],
			["name", "nome_completo", "celular", "telefone_secundario", "email"],
			as_dict=True,
		)
		if info:
			info["guardiao_legal"] = bool(vinculo.get("é_guardiao_legal"))
			info["primeiro_responsavel"] = bool(vinculo.get("primeiro_responsavel"))
			responsaveis.append(info)

	return {
		"novo_associado": dados,
		"progresso": resumo_etapas(etapas),
		"etapas": _traduzir_etapas(etapas),
		"visita": (
			{
				"name": visita.name,
				"data": str(visita.data_da_visita),
				"confirmada": bool(visita.visita_confirmada),
			}
			if visita
			else None
		),
		"responsaveis": responsaveis,
	}


@ferramenta(
	nome="funil_recepcao",
	titulo="Panorama do funil de recepção",
	descricao=(
		"Consolida o funil: quantidade por status, por ramo e por responsável, quantas "
		"pessoas têm etapa atrasada e quais etapas mais travam o processo."
	),
	parametros={},
	roles=ROLES,
)
def funil_recepcao() -> dict:
	registros = frappe.get_all(
		DOCTYPE,
		fields=CAMPOS_LISTA,
		order_by="modified desc",
		limit_page_length=MAX_REGISTROS_ANALISADOS,
	)
	pessoas = _com_etapas(registros, carregar_configuracao())

	por_status: dict[str, int] = {}
	por_ramo: dict[str, int] = {}
	por_responsavel: dict[str, int] = {}
	atrasos_por_etapa: dict[str, int] = {}
	atrasados = 0

	for pessoa in pessoas:
		por_status[pessoa.get("status") or "(sem status)"] = (
			por_status.get(pessoa.get("status") or "(sem status)", 0) + 1
		)
		por_ramo[pessoa.get("ramo") or "(sem ramo)"] = por_ramo.get(pessoa.get("ramo") or "(sem ramo)", 0) + 1
		responsavel = pessoa.get("responsavel_recepcao") or "(sem responsável)"
		por_responsavel[responsavel] = por_responsavel.get(responsavel, 0) + 1

		if pessoa["progresso"]["atrasadas"]:
			atrasados += 1
			for etapa in pessoa["progresso"]["etapas_atrasadas"]:
				atrasos_por_etapa[etapa] = atrasos_por_etapa.get(etapa, 0) + 1

	gargalos = [
		{"etapa": etapa, "rotulo": ROTULOS_DE_ETAPA.get(etapa, etapa), "pessoas_atrasadas": total}
		for etapa, total in sorted(atrasos_por_etapa.items(), key=lambda item: item[1], reverse=True)
	]

	return {
		"total_no_funil": len(pessoas),
		"com_etapa_atrasada": atrasados,
		"sem_visita_agendada": sum(1 for p in pessoas if not p.get("visita")),
		"por_status": por_status,
		"por_ramo": por_ramo,
		"por_responsavel": por_responsavel,
		"gargalos": gargalos,
	}


@ferramenta(
	nome="atualizar_etapa_recepcao",
	titulo="Marcar etapa do funil",
	descricao=(
		"Marca ou desmarca uma etapa do funil de recepção. Duas etapas movem o status "
		"junto, como no portal: 'primeira_visita_realizada' leva para 'Aguardar Dados' e "
		"'registro_criado_no_paxtu' leva para 'Acompanhamento'."
	),
	parametros={
		"name": {"type": "string", "description": "Identificador do Novo Associado."},
		"etapa": {
			"type": "string",
			"enum": list(CAMPOS_DE_ETAPA),
			"description": "Campo da etapa a alterar.",
		},
		"concluida": {
			"type": "boolean",
			"default": True,
			"description": "true marca como concluída; false desmarca.",
		},
	},
	obrigatorios=("name", "etapa"),
	roles=ROLES,
	somente_leitura=False,
)
def atualizar_etapa_recepcao(name: str, etapa: str, concluida: bool = True, simular: bool = False) -> dict:
	_garantir_registro(name)
	_etapa_valida(etapa)

	atual = bool(frappe.db.get_value(DOCTYPE, name, etapa))
	if atual == bool(concluida):
		return {
			"atualizado": False,
			"motivo": f"A etapa '{ROTULOS_DE_ETAPA.get(etapa, etapa)}' já está nesse estado.",
		}

	efeito_colateral = None
	if concluida and etapa == "registro_criado_no_paxtu":
		efeito_colateral = "status passa para 'Acompanhamento'"
	elif concluida and etapa == "primeira_visita_realizada":
		efeito_colateral = "status passa para 'Aguardar Dados'"

	if simular:
		return {
			"simulacao": True,
			"atualizado": False,
			"name": name,
			"etapa": etapa,
			"alteracao": {"de": atual, "para": bool(concluida)},
			"efeito_colateral": efeito_colateral,
		}

	from gris.www.recepcao import visao_geral

	if concluida and etapa == "registro_criado_no_paxtu":
		visao_geral.confirmar_registro_paxtu(name)
	elif concluida and etapa == "primeira_visita_realizada":
		servico.registrar_recepcao_realizada(name)
	else:
		visao_geral.update_step_status(name, etapa, 1 if concluida else 0)

	return {
		"atualizado": True,
		"name": name,
		"etapa": etapa,
		"alteracao": {"de": atual, "para": bool(concluida)},
		"efeito_colateral": efeito_colateral,
	}


@ferramenta(
	nome="atualizar_novo_associado",
	titulo="Atualizar cadastro do funil",
	descricao=(
		"Ajusta status (coluna do funil), ramo pretendido e responsável de recepção. "
		"Para desistências, use o portal: elas apagam e anonimizam dados pessoais."
	),
	parametros={
		"name": {"type": "string", "description": "Identificador do Novo Associado."},
		"status": {
			"type": "string",
			"enum": list(STATUS_VALIDOS),
			"description": "Nova coluna do funil.",
		},
		"ramo": {"type": "string", "enum": list(RAMOS), "description": "Novo ramo pretendido."},
		"responsavel_recepcao": {
			"type": "string",
			"description": "E-mail do usuário responsável (precisa ter o papel Recepcao).",
		},
	},
	obrigatorios=("name",),
	roles=ROLES,
	somente_leitura=False,
)
def atualizar_novo_associado(
	name: str,
	status: str | None = None,
	ramo: str | None = None,
	responsavel_recepcao: str | None = None,
	simular: bool = False,
) -> dict:
	_garantir_registro(name)

	solicitado = {"status": status, "ramo": ramo, "responsavel_recepcao": responsavel_recepcao}
	solicitado = {campo: valor for campo, valor in solicitado.items() if valor}
	if not solicitado:
		raise ErroDeFerramenta("ARGUMENTO_INVALIDO", "Informe ao menos um campo para atualizar.")

	if responsavel_recepcao:
		if not frappe.db.exists("User", responsavel_recepcao):
			raise ErroDeFerramenta("NAO_ENCONTRADO", f"Usuário '{responsavel_recepcao}' não existe.")
		if "Recepcao" not in frappe.get_roles(responsavel_recepcao):
			raise ErroDeFerramenta(
				"VALIDACAO",
				f"O usuário '{responsavel_recepcao}' não tem o papel Recepcao.",
			)

	atuais = frappe.db.get_value(DOCTYPE, name, list(solicitado), as_dict=True) or {}
	alteracoes = {
		campo: {"de": atuais.get(campo), "para": valor}
		for campo, valor in solicitado.items()
		if atuais.get(campo) != valor
	}
	if not alteracoes:
		return {"atualizado": False, "motivo": "Nenhum valor diferente do atual.", "alteracoes": {}}

	if simular:
		return {"simulacao": True, "atualizado": False, "name": name, "alteracoes": alteracoes}

	servico.update_novo_associado(name, **solicitado)
	return {"atualizado": True, "name": name, "alteracoes": alteracoes}


@ferramenta(
	nome="comentar_novo_associado",
	titulo="Comentar no registro da recepção",
	descricao=(
		"Adiciona um comentário interno no registro do novo associado — útil para deixar "
		"o combinado de um contato ou o motivo de uma pendência."
	),
	parametros={
		"name": {"type": "string", "description": "Identificador do Novo Associado."},
		"texto": {"type": "string", "description": "Conteúdo do comentário."},
	},
	obrigatorios=("name", "texto"),
	roles=ROLES,
	somente_leitura=False,
)
def comentar_novo_associado(name: str, texto: str, simular: bool = False) -> dict:
	_garantir_registro(name)
	texto = (texto or "").strip()
	if not texto:
		raise ErroDeFerramenta("ARGUMENTO_INVALIDO", "O comentário não pode estar vazio.")

	if simular:
		return {"simulacao": True, "comentado": False, "name": name, "texto": texto}

	comentario = servico.adicionar_comentario(name, texto)
	return {"comentado": True, "name": name, "comentario": comentario}


@ferramenta(
	nome="enviar_para_fila_espera",
	titulo="Enviar para a fila de espera",
	descricao=(
		"Move a pessoa para a fila de espera do ramo: o status vira 'Fila de espera' e "
		"uma entrada é criada na fila com a data de inclusão."
	),
	parametros={"name": {"type": "string", "description": "Identificador do Novo Associado."}},
	obrigatorios=("name",),
	roles=ROLES,
	somente_leitura=False,
)
def enviar_para_fila_espera(name: str, simular: bool = False) -> dict:
	_garantir_registro(name)

	dados = frappe.db.get_value(DOCTYPE, name, ["status", "ramo", "nome_completo"], as_dict=True)
	if dados.get("status") == "Fila de espera":
		return {"enviado": False, "motivo": "Esta pessoa já está na fila de espera."}

	if simular:
		return {
			"simulacao": True,
			"enviado": False,
			"name": name,
			"ramo": dados.get("ramo"),
			"status_atual": dados.get("status"),
		}

	servico.enviar_para_fila_espera(name)
	return {"enviado": True, "name": name, "ramo": dados.get("ramo")}


@ferramenta(
	nome="listar_fila_espera",
	titulo="Listar fila de espera",
	descricao=(
		"Lista a fila de espera por ramo, na ordem de entrada, com o nome de cada pessoa e a posição na fila."
	),
	parametros={
		"ramo": {"type": "string", "enum": list(RAMOS), "description": "Filtra por ramo."},
	},
	roles=ROLES,
)
def listar_fila_espera(ramo: str | None = None) -> dict:
	filtros = {"ramo": ramo} if ramo else {}
	fila = frappe.get_all(
		DOCTYPE_FILA,
		filters=filtros,
		fields=["name", "associado", "ramo", "dt_inclusao_fila"],
		order_by="dt_inclusao_fila asc",
	)

	nomes = [linha["associado"] for linha in fila if linha.get("associado")]
	pessoas = (
		{
			linha["name"]: linha["nome_completo"]
			for linha in frappe.get_all(
				DOCTYPE, filters={"name": ["in", nomes]}, fields=["name", "nome_completo"]
			)
		}
		if nomes
		else {}
	)

	posicoes: dict[str, int] = {}
	for linha in fila:
		chave = linha.get("ramo") or "(sem ramo)"
		posicoes[chave] = posicoes.get(chave, 0) + 1
		linha["posicao_no_ramo"] = posicoes[chave]
		linha["nome_completo"] = pessoas.get(linha.get("associado"))

	return {"fila": fila, "total": len(fila), "por_ramo": posicoes}


@ferramenta(
	nome="chamar_da_fila_espera",
	titulo="Chamar alguém da fila de espera",
	descricao=(
		"Tira a pessoa da fila de espera e devolve o registro ao início do funil "
		"(status 'Novo Contato'), como quando abre uma vaga no ramo."
	),
	parametros={
		"fila_id": {"type": "string", "description": "Identificador da entrada na fila."},
	},
	obrigatorios=("fila_id",),
	roles=ROLES,
	somente_leitura=False,
)
def chamar_da_fila_espera(fila_id: str, simular: bool = False) -> dict:
	dados = frappe.db.get_value(
		DOCTYPE_FILA, fila_id, ["name", "associado", "ramo", "dt_inclusao_fila"], as_dict=True
	)
	if dados is None:
		raise ErroDeFerramenta("NAO_ENCONTRADO", f"Entrada '{fila_id}' não existe na fila de espera.")

	if simular:
		return {"simulacao": True, "chamado": False, "fila": dados}

	from gris.www.recepcao import fila_espera

	fila_espera.chamar_associado(fila_id)
	return {"chamado": True, "novo_associado": dados.get("associado"), "ramo": dados.get("ramo")}


@ferramenta(
	nome="listar_respostas_pesquisa_recepcao",
	titulo="Listar respostas da pesquisa de novos associados",
	descricao=(
		"Lista as respostas da pesquisa aplicada às famílias novas, com a nota de NPS "
		"e o responsável que respondeu."
	),
	parametros={
		"limite": {
			"type": "integer",
			"default": 25,
			"minimum": 1,
			"maximum": 100,
			"description": "Quantas respostas retornar (mais recentes primeiro).",
		},
	},
	roles=ROLES,
)
def listar_respostas_pesquisa_recepcao(limite: int = 25) -> dict:
	from gris.www.recepcao import pesquisa_novos_respostas

	respostas = pesquisa_novos_respostas.get_surveys()
	limite = normalizar_limite(limite)
	return {"respostas": respostas[:limite], "total": len(respostas)}


@ferramenta(
	nome="obter_resposta_pesquisa_recepcao",
	titulo="Detalhar resposta da pesquisa",
	descricao=(
		"Retorna uma resposta completa da pesquisa de novos associados, com os textos "
		"abertos e os beneficiários ligados ao responsável."
	),
	parametros={"name": {"type": "string", "description": "Identificador da resposta."}},
	obrigatorios=("name",),
	roles=ROLES,
)
def obter_resposta_pesquisa_recepcao(name: str) -> dict:
	if not frappe.db.exists("Pesqusa de Novos Associados", name):
		raise ErroDeFerramenta("NAO_ENCONTRADO", f"Resposta '{name}' não encontrada.")

	from gris.www.recepcao import pesquisa_novos_respostas

	return pesquisa_novos_respostas.get_survey_details(name)


@ferramenta(
	nome="nps_recepcao",
	titulo="NPS da recepção",
	descricao=(
		"Calcula o NPS da recepção com as respostas dos últimos 6 meses: promotores "
		"(9-10), neutros (7-8) e detratores (0-6), além da série por período."
	),
	parametros={
		"periodo": {
			"type": "string",
			"enum": ["monthly", "weekly"],
			"default": "monthly",
			"description": "Agrupamento da série: mensal ou semanal.",
		},
	},
	roles=ROLES,
)
def nps_recepcao(periodo: str = "monthly") -> dict:
	from gris.www.recepcao import pesquisa_novos_respostas

	# A série já vem pronta do portal; aqui somamos o NPS consolidado do período.
	serie = pesquisa_novos_respostas.get_nps_chart_data(periodo)

	respostas = frappe.get_all("Pesqusa de Novos Associados", fields=["nps_recepcao"], limit_page_length=0)
	notas = [int(linha["nps_recepcao"]) for linha in respostas if linha.get("nps_recepcao")]
	promotores = sum(1 for nota in notas if nota >= 9)
	detratores = sum(1 for nota in notas if nota <= 6)
	total = len(notas)

	return {
		"serie": serie,
		"consolidado_geral": {
			"respostas_com_nota": total,
			"promotores": promotores,
			"neutros": total - promotores - detratores,
			"detratores": detratores,
			"nps": round(((promotores - detratores) / total) * 100, 1) if total else None,
		},
	}
