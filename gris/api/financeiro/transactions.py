"""
API para gerenciamento de transações financeiras em lote
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, getdate

from gris.api.portal_access import user_has_access


@frappe.whitelist()
def batch_update_transactions(transaction_ids: str | list, updates: str | dict):
	"""
	Atualiza múltiplas transações de uma vez

	Args:
		transaction_ids: Lista de IDs das transações a serem atualizadas (JSON string ou lista)
		updates: Dicionário com os campos a serem atualizados (JSON string ou dict)

	Returns:
		dict: Resultado da operação com contagem de registros atualizados
	"""
	# Parse JSON strings se necessário
	if isinstance(transaction_ids, str):
		transaction_ids = json.loads(transaction_ids)

	if isinstance(updates, str):
		updates = json.loads(updates)

	if not transaction_ids or not isinstance(transaction_ids, list):
		frappe.throw(_("IDs de transações inválidos"))

	if not updates or not isinstance(updates, dict):
		frappe.throw(_("Dados de atualização inválidos"))

	# Campos permitidos para atualização em lote
	allowed_fields = [
		"descricao_reduzida",
		"categoria",
		"centro_de_custo",
		"ordinaria_extraordinaria",
		"transacao_revisada",
	]

	# Valida que apenas campos permitidos estão sendo atualizados
	for field in updates.keys():
		if field not in allowed_fields:
			frappe.throw(f"Campo '{field}' não permitido para atualização em lote")

	updated_count = 0

	for transaction_id in transaction_ids:
		try:
			doc = frappe.get_doc("Transacao Extrato Geral", transaction_id)

			# Aplica as atualizações
			for field, value in updates.items():
				if hasattr(doc, field):
					setattr(doc, field, value)

			doc.save(ignore_permissions=False)
			updated_count += 1

		except frappe.DoesNotExistError:
			frappe.log_error(f"Transação {transaction_id} não encontrada")
			continue
		except Exception as e:
			frappe.log_error(f"Erro ao atualizar transação {transaction_id}: {e!s}")
			continue

	return {"success": True, "updated_count": updated_count, "total_requested": len(transaction_ids)}


# ---------------------------------------------------------------------------
# Listagem do extrato (grid compacto + scroll infinito)
# ---------------------------------------------------------------------------

#: Quantidade de transações carregadas por lote no extrato.
EXTRATO_PAGE_SIZE = 100

#: Teto de segurança para o lote pedido pelo cliente.
EXTRATO_MAX_PAGE_SIZE = 200

#: Template compartilhado entre o render inicial (Jinja) e o scroll infinito (API).
EXTRATO_ROWS_TEMPLATE = "templates/includes/financeiro/extrato_linhas.html"

#: Campos aceitos como filtro de igualdade na listagem do extrato.
EXTRATO_FILTER_FIELDS = (
	"instituicao",
	"carteira",
	"categoria",
	"centro_de_custo",
	"fixo_variavel",
	"ordinaria_extraordinaria",
	"conta_fixa",
	"repasse_entre_contas",
	"transacao_revisada",
	"fonte",
)

#: Campos lidos do DocType para montar cada linha do grid.
EXTRATO_FIELDS = (
	"name",
	"transacao_revisada",
	"timestamp_transacao",
	"valor",
	"descricao_reduzida",
	"instituicao",
	"carteira",
	"centro_de_custo",
	"categoria",
	"fixo_variavel",
	"ordinaria_extraordinaria",
	"conta_fixa",
	"repasse_entre_contas",
	"data_deposito",
	"fonte",
	"status_conciliacao",
)

#: Ordenação com desempate por `name` para paginação estável no scroll infinito.
EXTRATO_ORDER_BY = "timestamp_transacao desc, name desc"


def _parse_data_extrato(valor) -> str | None:
	"""Normaliza uma data vinda da query string; devolve None se inválida."""
	if not valor:
		return None
	try:
		return getdate(valor).isoformat()
	except Exception:
		return None


def build_extrato_filters(request_args: dict | None) -> dict:
	"""Monta os filtros do extrato a partir dos argumentos da requisição.

	Apenas campos previstos em `EXTRATO_FILTER_FIELDS` (mais o intervalo de
	datas) são considerados, então valores arbitrários do cliente não viram
	filtro de banco.
	"""
	request_args = request_args or {}
	filters: dict = {}

	data_inicio = _parse_data_extrato(request_args.get("data_inicio"))
	data_fim = _parse_data_extrato(request_args.get("data_fim"))
	if data_inicio and data_fim:
		filters["data_deposito"] = ["between", [data_inicio, data_fim]]
	elif data_inicio:
		filters["data_deposito"] = [">=", data_inicio]
	elif data_fim:
		filters["data_deposito"] = ["<=", data_fim]

	for campo in EXTRATO_FILTER_FIELDS:
		valor = request_args.get(campo)
		if valor not in (None, "", "null"):
			filters[campo] = valor

	return filters


def get_extrato_transacoes(
	filters: dict, start: int = 0, page_length: int = EXTRATO_PAGE_SIZE, with_descricao: bool = False
) -> list[dict]:
	"""Busca um lote de transações do extrato já ordenado para paginação estável."""
	fields = list(EXTRATO_FIELDS)
	if with_descricao:
		fields.insert(4, "descricao")

	return frappe.get_all(
		"Transacao Extrato Geral",
		fields=fields,
		filters=filters,
		order_by=EXTRATO_ORDER_BY,
		limit=page_length,
		start=start,
	)


def render_extrato_rows(transacoes: list[dict], can_view_full_description: bool) -> str:
	"""Renderiza as linhas do grid com o mesmo template usado no carregamento inicial."""
	# Template interno da app (constante deste módulo); o contexto não é interpretado como template.
	return frappe.render_template(  # nosemgrep
		EXTRATO_ROWS_TEMPLATE,
		{"transacoes": transacoes, "can_view_full_description": can_view_full_description},
		is_path=True,
	)


@frappe.whitelist()
def get_extrato_rows(filtros: str | dict | None = None, start: int = 0, page_length: int | None = None):
	"""Devolve o próximo lote de linhas do extrato para o scroll infinito.

	Args:
		filtros: filtros ativos da tela (JSON string ou dict), com as mesmas
			chaves aceitas pela query string de `/financeiro/extrato`.
		start: deslocamento (quantas linhas já foram carregadas).
		page_length: tamanho do lote; limitado a `EXTRATO_MAX_PAGE_SIZE`.

	Returns:
		dict: `html` das linhas, `count` do lote e `has_more`.
	"""
	if frappe.session.user == "Guest" or not user_has_access("/financeiro/extrato"):
		frappe.throw(_("Sem permissão para consultar o extrato"), frappe.PermissionError)

	if isinstance(filtros, str):
		try:
			filtros = json.loads(filtros)
		except ValueError:
			filtros = {}
	if not isinstance(filtros, dict):
		filtros = {}

	start = max(cint(start), 0)
	page_length = cint(page_length) or EXTRATO_PAGE_SIZE
	page_length = max(1, min(page_length, EXTRATO_MAX_PAGE_SIZE))

	can_view_full_description = "Gestor Financeiro" in frappe.get_roles()

	# Busca uma linha extra para saber se ainda há próximo lote sem novo count().
	transacoes = get_extrato_transacoes(
		build_extrato_filters(filtros),
		start=start,
		page_length=page_length + 1,
		with_descricao=can_view_full_description,
	)
	has_more = len(transacoes) > page_length
	transacoes = transacoes[:page_length]

	return {
		"html": render_extrato_rows(transacoes, can_view_full_description),
		"count": len(transacoes),
		"has_more": has_more,
	}
