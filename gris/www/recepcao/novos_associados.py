"""Lista de novos associados em tabela, com link para a ficha e para o formulário de registro.

A visão geral do funil é um kanban: boa para mover o fluxo, ruim para achar alguém que está
fora da coluna em que se procura. Esta página é a lista completa — todo mundo que está em
integração, em qualquer status, com busca e filtros — e é por ela que se chega na ficha de
registro (`/recepcao/ficha_registro`) e no formulário do responsável (`/responsavel/registro`)
de qualquer jovem, sem depender do status em que ele está.

As linhas chegam por ``listar``, e não no contexto da página: é o mesmo desenho das outras
listas do portal (`/associados/lista`, `/recepcao/pesquisa_novos_respostas`), em que filtrar e
paginar não recarrega a página inteira.
"""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, format_date, get_fullname

from gris.api.portal_access import enrich_context, user_has_access
from gris.api.recepcao import formatar_idade

no_cache = 1

CAMINHO = "/recepcao/novos_associados"

RAMOS = ["Filhotes", "Lobinho", "Escoteiro", "Sênior", "Pioneiro"]

STATUS = [
	"Novo Contato",
	"Conversa Inicial",
	"Visita Agendada",
	"Aguardar Dados",
	"Fazer Registro",
	"Acompanhamento",
	"Fila de espera",
	"Concluído",
]

TIPOS_DE_REGISTRO = ["Provisório", "Definitivo"]

# Variantes do badge Basecoat por ramo, as mesmas de visao_geral.py e fila_espera.py.
VARIANTE_POR_RAMO = {
	"Filhotes": "ramo-filhotes",
	"Lobinho": "ramo-lobinho",
	"Escoteiro": "ramo-escoteiro",
	"Sênior": "ramo-senior",
	"Pioneiro": "ramo-pioneiro",
}

POR_PAGINA = 50

CAMPOS_DA_LISTA = [
	"name",
	"nome_completo",
	"data_de_nascimento",
	"ramo",
	"status",
	"tipo_de_registro",
	"dados_para_registro_enviados",
	"registro_criado_no_paxtu",
	"responsavel_recepcao",
	"modified",
]


def _pode_ver() -> bool:
	"""Mesma regra das outras páginas de `/recepcao`: papel Recepcao (ou System Manager)."""
	return user_has_access(CAMINHO)


def _itens(valores: list[str], rotulo_vazio: str) -> list[dict]:
	return [{"value": "", "label": rotulo_vazio}] + [{"value": v, "label": v} for v in valores]


def _filtros(
	busca: str | None,
	status: str | None,
	ramo: str | None,
	tipo_de_registro: str | None,
	dados_enviados: str | None,
) -> dict:
	"""Filtros da listagem, validados contra as opções do schema.

	Os valores vêm do cliente, então nada entra em ``filters`` sem estar na lista de opções —
	um status inventado viraria um filtro silencioso que devolve lista vazia.
	"""
	filtros: dict[str, object] = {}

	if (status or "").strip() in STATUS:
		filtros["status"] = status.strip()

	if (ramo or "").strip() in RAMOS:
		filtros["ramo"] = ramo.strip()

	if (tipo_de_registro or "").strip() in TIPOS_DE_REGISTRO:
		filtros["tipo_de_registro"] = tipo_de_registro.strip()

	if (dados_enviados or "").strip() in ("sim", "nao"):
		filtros["dados_para_registro_enviados"] = 1 if dados_enviados.strip() == "sim" else 0

	busca = (busca or "").strip()
	if busca:
		filtros["nome_completo"] = ["like", f"%{busca}%"]

	return filtros


def _responsaveis_por_jovem(nomes: list[str]) -> dict[str, str]:
	"""Nome do primeiro responsável de cada jovem, em duas consultas (e não uma por linha)."""
	if not nomes:
		return {}

	vinculos = frappe.get_all(
		"Responsavel Vinculo",
		filters={"beneficiario_novo_associado": ["in", nomes]},
		fields=["beneficiario_novo_associado", "responsavel"],
		order_by="primeiro_responsavel desc, creation asc",
	)

	primeiro_por_jovem: dict[str, str] = {}
	for vinculo in vinculos:
		jovem = vinculo.beneficiario_novo_associado
		if vinculo.responsavel and jovem not in primeiro_por_jovem:
			primeiro_por_jovem[jovem] = vinculo.responsavel

	if not primeiro_por_jovem:
		return {}

	nomes_de_responsavel = {
		resp.name: resp.nome_completo
		for resp in frappe.get_all(
			"Responsavel",
			filters={"name": ["in", list(set(primeiro_por_jovem.values()))]},
			fields=["name", "nome_completo"],
		)
	}

	return {
		jovem: nomes_de_responsavel.get(responsavel) or ""
		for jovem, responsavel in primeiro_por_jovem.items()
	}


def _linhas(registros: list[dict]) -> list[dict]:
	"""Linhas da tabela, já com o que a página precisa mostrar em cada coluna."""
	responsaveis = _responsaveis_por_jovem([registro.name for registro in registros])
	emails_da_recepcao = {
		registro.responsavel_recepcao for registro in registros if registro.responsavel_recepcao
	}
	nomes_da_recepcao = {email: get_fullname(email) for email in emails_da_recepcao}

	return [
		{
			"name": registro.name,
			"nome_completo": registro.nome_completo or _("(sem nome)"),
			"idade": formatar_idade(registro.data_de_nascimento) or "",
			"ramo": registro.ramo or "",
			"ramo_variante": VARIANTE_POR_RAMO.get(registro.ramo or "", "secondary"),
			"status": registro.status or "",
			"tipo_de_registro": registro.tipo_de_registro or "",
			"dados_enviados": 1 if cint(registro.dados_para_registro_enviados) else 0,
			"registro_criado_no_paxtu": 1 if cint(registro.registro_criado_no_paxtu) else 0,
			"responsavel_legal": responsaveis.get(registro.name) or "",
			"responsavel_recepcao": nomes_da_recepcao.get(registro.responsavel_recepcao) or "",
			"atualizado_em": format_date(registro.modified) if registro.modified else "",
		}
		for registro in registros
	]


@frappe.whitelist()
@rate_limit(key="recepcao-lista-novos", limit=120, seconds=60)
def listar(
	busca: str | None = None,
	status: str | None = None,
	ramo: str | None = None,
	tipo_de_registro: str | None = None,
	dados_enviados: str | None = None,
	pagina: int | str = 1,
) -> dict:
	"""Página da lista de novos associados, com os filtros aplicados."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Você precisa estar logado."), frappe.PermissionError)

	if not _pode_ver():
		frappe.throw(_("Acesso permitido apenas para Recepção."), frappe.PermissionError)

	filtros = _filtros(busca, status, ramo, tipo_de_registro, dados_enviados)

	total = frappe.db.count("Novo Associado", filtros)
	ultima_pagina = max(1, -(-total // POR_PAGINA))
	# Página além do fim (o filtro mudou e a paginação ficou para trás) volta para a primeira,
	# senão a tela aparece vazia enquanto o contador diz que há registros.
	pagina = max(1, cint(pagina) or 1)
	if pagina > ultima_pagina:
		pagina = 1

	registros = frappe.get_all(
		"Novo Associado",
		filters=filtros,
		fields=CAMPOS_DA_LISTA,
		order_by="nome_completo asc",
		limit_start=(pagina - 1) * POR_PAGINA,
		limit_page_length=POR_PAGINA,
	)

	return {
		"linhas": _linhas(registros),
		"total": total,
		"pagina": pagina,
		"ultima_pagina": ultima_pagina,
		"por_pagina": POR_PAGINA,
		"com_filtro": bool(filtros),
	}


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = f"/login?redirect-to={CAMINHO}"
		raise frappe.Redirect

	if not _pode_ver():
		frappe.throw(_("Acesso permitido apenas para Recepção."), frappe.PermissionError)

	context.itens_status = _itens(STATUS, "Todos")
	context.itens_ramo = _itens(RAMOS, "Todos")
	context.itens_tipo_de_registro = _itens(TIPOS_DE_REGISTRO, "Todos")
	context.itens_dados_enviados = [
		{"value": "", "label": "Todos"},
		{"value": "sim", "label": "Enviados"},
		{"value": "nao", "label": "Pendentes"},
	]
	context.por_pagina = POR_PAGINA

	context.active_link = CAMINHO
	enrich_context(context, CAMINHO)

	return context
