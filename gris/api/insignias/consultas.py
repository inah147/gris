"""Consultas e formatação compartilhadas pelas páginas de portal de insígnias."""

from __future__ import annotations

import frappe
from frappe.utils import flt, fmt_money, format_date

from gris.api.insignias import permissoes

DOCTYPE = "Solicitacao de Insignias"

# Ordem do fluxo, usada para a linha do tempo e para ordenar a fila do financeiro.
STATUS_ORDEM = ["Solicitada", "Comprada", "Recebida", "Entregue"]

STATUS_META: dict[str, dict[str, str]] = {
	"Solicitada": {
		"variant": "outline",
		"descricao": "Aguardando o financeiro realizar a compra.",
	},
	"Comprada": {
		"variant": "secondary",
		"descricao": "Compra realizada. Aguardando o material chegar ao grupo.",
	},
	"Recebida": {
		"variant": "primary",
		"descricao": "Material recebido no grupo. Aguardando entrega ao solicitante.",
	},
	"Entregue": {
		"variant": "default",
		"descricao": "Entregue ao solicitante. Pedido concluído.",
	},
	"Cancelada": {
		"variant": "destructive",
		"descricao": "Solicitação cancelada.",
	},
}

CAMPOS_LISTA = [
	"name",
	"solicitante",
	"solicitante_nome",
	"ramo",
	"data_solicitacao",
	"status",
	"valor_estimado",
	"valor_pago",
	"data_compra",
	"data_recebimento",
	"data_entrega",
]


def formatar_moeda(valor) -> str:
	return fmt_money(flt(valor), currency="BRL")


def _hidratar_linha(linha: dict) -> dict:
	linha = dict(linha)
	meta = STATUS_META.get(linha.get("status") or "", {})
	linha["status_variant"] = meta.get("variant", "default")
	linha["status_descricao"] = meta.get("descricao", "")
	linha["data_solicitacao_fmt"] = (
		format_date(linha["data_solicitacao"], "dd/MM/yyyy") if linha.get("data_solicitacao") else "—"
	)
	linha["data_compra_fmt"] = (
		format_date(linha["data_compra"], "dd/MM/yyyy") if linha.get("data_compra") else "—"
	)
	linha["data_recebimento_fmt"] = (
		format_date(linha["data_recebimento"], "dd/MM/yyyy") if linha.get("data_recebimento") else "—"
	)
	linha["data_entrega_fmt"] = (
		format_date(linha["data_entrega"], "dd/MM/yyyy") if linha.get("data_entrega") else "—"
	)
	linha["valor_estimado_fmt"] = formatar_moeda(linha.get("valor_estimado"))
	linha["valor_pago_fmt"] = formatar_moeda(linha.get("valor_pago")) if linha.get("valor_pago") else "—"
	return linha


def _contar_itens(nomes: list[str]) -> dict[str, int]:
	"""Total de peças por solicitação em uma única query (evita N+1)."""
	if not nomes:
		return {}

	linhas = frappe.get_all(
		"Item de Solicitacao de Insignias",
		filters={"parent": ["in", nomes], "parenttype": DOCTYPE},
		fields=["parent", "sum(quantidade) as total"],
		group_by="parent",
	)
	return {linha["parent"]: int(linha["total"] or 0) for linha in linhas}


def listar_solicitacoes(filtros: dict | None = None, limite: int = 200) -> list[dict]:
	# O recorte de acesso é responsabilidade de quem chama: as páginas de portal já
	# validam o papel do usuário e passam os filtros correspondentes (ex.: solicitante).
	registros = frappe.get_all(
		DOCTYPE,
		filters=filtros or {},
		fields=CAMPOS_LISTA,
		order_by="creation desc",
		limit_page_length=limite,
	)

	totais = _contar_itens([r["name"] for r in registros])
	linhas = []
	for registro in registros:
		linha = _hidratar_linha(registro)
		linha["total_pecas"] = totais.get(registro["name"], 0)
		linhas.append(linha)
	return linhas


def minhas_solicitacoes(user: str | None = None) -> list[dict]:
	return listar_solicitacoes({"solicitante": user or frappe.session.user})


def resumo_por_status(linhas: list[dict]) -> dict[str, int]:
	resumo = dict.fromkeys([*STATUS_ORDEM, "Cancelada"], 0)
	for linha in linhas:
		status = linha.get("status")
		if status in resumo:
			resumo[status] += 1
	return resumo


def carregar_solicitacao(name: str) -> dict | None:
	if not name or not frappe.db.exists(DOCTYPE, name):
		return None

	doc = frappe.get_doc(DOCTYPE, name)
	permissoes.garantir_acesso_solicitacao(doc)

	dados = _hidratar_linha(
		{campo: doc.get(campo) for campo in CAMPOS_LISTA},
	)
	dados.update(
		{
			"justificativa": doc.justificativa,
			"fornecedor": doc.fornecedor,
			"numero_documento": doc.numero_documento,
			"observacoes_compra": doc.observacoes_compra,
			"observacoes_entrega": doc.observacoes_entrega,
			"motivo_cancelamento": doc.motivo_cancelamento,
			"comprado_por": doc.comprado_por,
			"recebido_por": doc.recebido_por,
			"entregue_por": doc.entregue_por,
			"data_cancelamento_fmt": (
				format_date(doc.data_cancelamento, "dd/MM/yyyy") if doc.data_cancelamento else "—"
			),
		}
	)

	beneficiarios = {item.beneficiario for item in doc.itens if item.beneficiario}
	nomes_beneficiarios: dict[str, str] = {}
	if beneficiarios:
		for registro in frappe.get_all(
			"Associado",
			filters={"name": ["in", list(beneficiarios)]},
			fields=["name", "nome_completo"],
		):
			nomes_beneficiarios[registro["name"]] = registro["nome_completo"] or registro["name"]

	dados["itens"] = [
		{
			"insignia": item.insignia,
			"tipo": item.tipo or "—",
			"ramo": item.ramo or "—",
			"quantidade": item.quantidade,
			"valor_unitario_fmt": formatar_moeda(item.valor_unitario),
			"valor_total_fmt": formatar_moeda(item.valor_total),
			"beneficiario": nomes_beneficiarios.get(item.beneficiario) if item.beneficiario else None,
			"observacao": item.observacao,
		}
		for item in doc.itens
	]
	dados["total_pecas"] = sum(int(item.quantidade or 0) for item in doc.itens)

	dados["pode_cancelar"] = permissoes.pode_cancelar(doc)
	dados["pode_comprar"] = permissoes.pode_comprar() and doc.status == "Solicitada"
	dados["pode_receber"] = permissoes.pode_comprar() and doc.status == "Comprada"
	dados["pode_entregar"] = permissoes.pode_registrar_entrega(doc)

	dados["timeline"] = _montar_timeline(dados)
	return dados


def _montar_timeline(dados: dict) -> list[dict]:
	"""Linha do tempo do pedido, com a etapa atual destacada."""
	# Cancelada não segue a ordem normal: mostra até onde chegou e encerra.
	status_atual = dados.get("status")
	if status_atual == "Cancelada":
		return [
			{
				"label": "Solicitada",
				"data": dados.get("data_solicitacao_fmt"),
				"estado": "concluida",
			},
			{
				"label": "Cancelada",
				"data": dados.get("data_cancelamento_fmt"),
				"estado": "cancelada",
			},
		]

	indice_atual = STATUS_ORDEM.index(status_atual) if status_atual in STATUS_ORDEM else 0
	datas = {
		"Solicitada": dados.get("data_solicitacao_fmt"),
		"Comprada": dados.get("data_compra_fmt"),
		"Recebida": dados.get("data_recebimento_fmt"),
		"Entregue": dados.get("data_entrega_fmt"),
	}

	etapas = []
	for indice, label in enumerate(STATUS_ORDEM):
		if indice < indice_atual:
			estado = "concluida"
		elif indice == indice_atual:
			estado = "atual"
		else:
			estado = "pendente"
		etapas.append({"label": label, "data": datas.get(label), "estado": estado})
	return etapas


def itens_catalogo() -> list[dict]:
	"""Itens ativos do catálogo agrupados por tipo, no formato do macro `select`."""
	registros = frappe.get_all(
		"Insignia ou Distintivo",
		filters={"ativo": 1},
		fields=["name", "nome", "tipo", "ramo", "valor_unitario"],
		order_by="tipo asc, nome asc",
	)

	grupos: dict[str, list[dict]] = {}
	for registro in registros:
		rotulo = registro["nome"] or registro["name"]
		if registro.get("ramo") and registro["ramo"] != "Todos":
			rotulo = f"{rotulo} · {registro['ramo']}"
		grupos.setdefault(registro["tipo"] or "Outro", []).append(
			{"label": rotulo, "value": registro["name"], "type": "item"}
		)

	items: list[dict] = []
	for tipo, filhos in grupos.items():
		items.append({"type": "group", "label": tipo, "items": filhos})
	return items


def precos_catalogo() -> dict[str, float]:
	"""Mapa nome -> valor unitário, usado pelo JS para o total estimado ao vivo."""
	return {
		registro["name"]: flt(registro["valor_unitario"])
		for registro in frappe.get_all(
			"Insignia ou Distintivo",
			filters={"ativo": 1},
			fields=["name", "valor_unitario"],
		)
	}


def itens_associados() -> list[dict]:
	registros = frappe.get_all(
		"Associado",
		filters={"status_no_grupo": "Ativo"},
		fields=["name", "nome_completo"],
		order_by="nome_completo asc",
	)
	return [
		{"label": registro["nome_completo"] or registro["name"], "value": registro["name"], "type": "item"}
		for registro in registros
	]
