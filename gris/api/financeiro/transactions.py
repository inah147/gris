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

	# Campos permitidos para atualização em lote (mesmo registro usado pela
	# edição inline do grid, em EXTRATO_COLUNAS).
	for field in updates.keys():
		if field not in EXTRATO_CAMPOS_EDITAVEIS:
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

#: Campo usado na busca textual por descrição; é o mesmo exibido por padrão
#: no grid (`descricao_reduzida`), então a busca não vaza o conteúdo da
#: coluna `descricao`, restrita ao Gestor Financeiro.
EXTRATO_BUSCA_DESCRICAO_CAMPO = "descricao_reduzida"

#: Campo da busca textual pela descrição completa; só é aplicado quando o
#: usuário pode ver a coluna `descricao` (Gestor Financeiro), senão a busca
#: vazaria o conteúdo de uma coluna restrita através do resultado filtrado.
EXTRATO_BUSCA_DESCRICAO_COMPLETA_CAMPO = "descricao"

#: Colunas do grid do extrato, na ordem em que aparecem na tabela.
#:
#: Todas as informações da transação estão disponíveis; `padrao` define quais
#: já vêm visíveis e as demais são ligadas pelo seletor de colunas da tela.
#: `restrita` marca colunas visíveis apenas para o Gestor Financeiro.
EXTRATO_COLUNAS = (
	{
		"key": "transacao_revisada",
		"label": "Revisão",
		"tipo": "revisao",
		"padrao": True,
		"editavel": {"tipo": "booleano"},
	},
	{"key": "timestamp_transacao", "label": "Data/Hora", "tipo": "datahora", "padrao": True},
	{
		"key": "descricao_reduzida",
		"label": "Descrição reduzida",
		"tipo": "texto",
		"destaque": True,
		"padrao": True,
		"editavel": {"tipo": "texto"},
	},
	{
		"key": "descricao",
		"label": "Descrição",
		"tipo": "texto",
		"largura": "lg",
		"padrao": True,
		"restrita": True,
	},
	{"key": "valor", "label": "Valor", "tipo": "moeda", "padrao": True},
	{"key": "instituicao", "label": "Instituição", "tipo": "instituicao", "padrao": True},
	{"key": "fonte", "label": "Fonte", "tipo": "fonte", "padrao": True},
	{
		"key": "status_conciliacao",
		"label": "Conciliação",
		"tipo": "badge",
		"variante": "success",
		"outline": True,
		"padrao": True,
	},
	{"key": "carteira", "label": "Carteira", "tipo": "badge", "variante": "secondary", "padrao": True},
	{
		"key": "categoria",
		"label": "Categoria",
		"tipo": "badge",
		"variante": "default",
		"outline": True,
		"padrao": True,
		"editavel": {"tipo": "opcoes", "doctype": "Categoria de Transacao"},
	},
	{
		"key": "centro_de_custo",
		"label": "Centro de custo",
		"tipo": "badge",
		"variante": "info",
		"outline": True,
		"padrao": True,
		"editavel": {"tipo": "opcoes", "doctype": "Centro de Custo"},
	},
	{"key": "id", "label": "ID", "tipo": "texto"},
	{"key": "debito_credito", "label": "Débito/Crédito", "tipo": "badge", "variante": "secondary"},
	{"key": "metodo", "label": "Método", "tipo": "badge", "variante": "secondary", "outline": True},
	{"key": "origem", "label": "Origem", "tipo": "texto"},
	{"key": "destino", "label": "Destino", "tipo": "texto"},
	{"key": "valor_absoluto", "label": "Valor absoluto", "tipo": "moeda"},
	{"key": "data_transacao", "label": "Data da transação", "tipo": "data"},
	{"key": "mes_competencia", "label": "Mês de competência", "tipo": "data"},
	{"key": "data_deposito", "label": "Data de depósito", "tipo": "datahora"},
	{
		"key": "fixo_variavel",
		"label": "Fixo/Variável",
		"tipo": "badge",
		"variante": "secondary",
		"outline": True,
	},
	{
		"key": "ordinaria_extraordinaria",
		"label": "Ordinária/Extraordinária",
		"tipo": "badge",
		"variante": "secondary",
		"outline": True,
		"editavel": {"tipo": "opcoes", "opcoes": ["Ordinária", "Extraordinária"]},
	},
	{"key": "conta_fixa", "label": "Conta fixa", "tipo": "badge", "variante": "secondary", "outline": True},
	{"key": "beneficiario", "label": "Beneficiário", "tipo": "texto"},
	{"key": "repasse_entre_contas", "label": "Repasse entre contas", "tipo": "sim_nao"},
	{"key": "excluir_do_total", "label": "Excluir do total", "tipo": "sim_nao"},
	{"key": "numero_liquidacao", "label": "Número de liquidação", "tipo": "texto"},
	{"key": "nome_atividade", "label": "Nome da atividade", "tipo": "texto"},
	{"key": "observacoes", "label": "Observações", "tipo": "texto", "largura": "lg"},
	{"key": "transacao_conciliada", "label": "Transação conciliada", "tipo": "texto"},
)

#: Ordenação com desempate por `name` para paginação estável no scroll infinito.
EXTRATO_ORDER_BY = "timestamp_transacao desc, name desc"

#: Campos que a tela permite alterar direto na célula (e em lote na seleção).
#:
#: Fonte única da verdade: o mesmo registro alimenta o `data-editavel` do grid,
#: as opções entregues ao editor inline e a validação do que pode ser gravado.
EXTRATO_CAMPOS_EDITAVEIS = {
	coluna["key"]: coluna["editavel"] for coluna in EXTRATO_COLUNAS if coluna.get("editavel")
}

#: Teto de transações alteradas numa única edição em lote.
EXTRATO_MAX_EDICAO_LOTE = 200


def _parse_data_extrato(valor) -> str | None:
	"""Normaliza uma data vinda da query string; devolve None se inválida."""
	if not valor:
		return None
	try:
		return getdate(valor).isoformat()
	except Exception:
		return None


def _termo_like(valor: str) -> str:
	"""Escapa curingas do LIKE (%, _) para o texto ser tratado como literal.

	O collation padrão do MySQL já torna a comparação case-insensitive.
	"""
	return valor.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


def build_extrato_filters(request_args: dict | None, pode_buscar_descricao_completa: bool = False) -> dict:
	"""Monta os filtros do extrato a partir dos argumentos da requisição.

	Apenas campos previstos em `EXTRATO_FILTER_FIELDS` (mais o intervalo de
	datas e as buscas textuais por descrição) são considerados, então valores
	arbitrários do cliente não viram filtro de banco.

	`pode_buscar_descricao_completa` habilita a busca na coluna `descricao`
	(texto completo); ela é restrita ao Gestor Financeiro, então o chamador
	deve repassar essa checagem de papel — nunca um valor vindo do cliente.
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

	busca_descricao = request_args.get("descricao")
	if busca_descricao not in (None, "", "null"):
		filters[EXTRATO_BUSCA_DESCRICAO_CAMPO] = ["like", f"%{_termo_like(busca_descricao)}%"]

	busca_descricao_completa = request_args.get("descricao_completa")
	if pode_buscar_descricao_completa and busca_descricao_completa not in (None, "", "null"):
		filters[EXTRATO_BUSCA_DESCRICAO_COMPLETA_CAMPO] = [
			"like",
			f"%{_termo_like(busca_descricao_completa)}%",
		]

	return filters


def get_extrato_colunas(can_view_full_description: bool = False) -> list[dict]:
	"""Colunas disponíveis no grid para o usuário atual."""
	return [coluna for coluna in EXTRATO_COLUNAS if can_view_full_description or not coluna.get("restrita")]


def get_extrato_transacoes(
	filters: dict, start: int = 0, page_length: int = EXTRATO_PAGE_SIZE, colunas: list[dict] | None = None
) -> list[dict]:
	"""Busca um lote de transações do extrato já ordenado para paginação estável."""
	colunas = colunas if colunas is not None else get_extrato_colunas()
	# `name` é o identificador usado na seleção e no link para o detalhe.
	fields = ["name"] + [coluna["key"] for coluna in colunas if coluna["key"] != "name"]

	return frappe.get_all(
		"Transacao Extrato Geral",
		fields=fields,
		filters=filters,
		order_by=EXTRATO_ORDER_BY,
		limit=page_length,
		start=start,
	)


def render_extrato_rows(transacoes: list[dict], colunas: list[dict]) -> str:
	"""Renderiza as linhas do grid com o mesmo template usado no carregamento inicial."""
	# Template interno da app (constante deste módulo); o contexto não é interpretado como template.
	return frappe.render_template(  # nosemgrep
		EXTRATO_ROWS_TEMPLATE,
		{"transacoes": transacoes, "colunas": colunas},
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

	pode_ver_descricao_completa = "Gestor Financeiro" in frappe.get_roles()
	colunas = get_extrato_colunas(pode_ver_descricao_completa)

	# Busca uma linha extra para saber se ainda há próximo lote sem novo count().
	transacoes = get_extrato_transacoes(
		build_extrato_filters(filtros, pode_buscar_descricao_completa=pode_ver_descricao_completa),
		start=start,
		page_length=page_length + 1,
		colunas=colunas,
	)
	has_more = len(transacoes) > page_length
	transacoes = transacoes[:page_length]

	return {
		"html": render_extrato_rows(transacoes, colunas),
		"count": len(transacoes),
		"has_more": has_more,
	}


# ---------------------------------------------------------------------------
# Edição em lote direto no grid
# ---------------------------------------------------------------------------


def get_extrato_opcoes_editaveis() -> dict:
	"""Opções de cada campo editável, para o editor inline montar o select.

	Campos `Link` buscam a lista no doctype de origem; campos `Select` já
	trazem as opções fixas no registro de colunas.
	"""
	opcoes: dict[str, list[str]] = {}
	for campo, meta in EXTRATO_CAMPOS_EDITAVEIS.items():
		if meta["tipo"] != "opcoes":
			continue
		if meta.get("doctype"):
			opcoes[campo] = frappe.get_all(meta["doctype"], pluck="name", order_by="name")
		else:
			opcoes[campo] = list(meta.get("opcoes") or [])
	return opcoes


def _normalizar_valor_editavel(campo: str, valor):
	"""Valida e converte o valor recebido do grid para o tipo do campo.

	Devolve `None` quando o usuário limpa o campo (opção "Sem valor" ou texto
	vazio), que é uma alteração legítima em lote.
	"""
	meta = EXTRATO_CAMPOS_EDITAVEIS.get(campo)
	if not meta:
		frappe.throw(_("Campo '{0}' não é editável no extrato").format(campo))

	if meta["tipo"] == "booleano":
		return cint(valor)

	valor = (valor or "").strip() if isinstance(valor, str) else valor
	if not valor:
		return None

	if meta["tipo"] == "opcoes":
		if meta.get("doctype"):
			if not frappe.db.exists(meta["doctype"], valor):
				frappe.throw(_("Valor inválido para {0}").format(campo))
		elif valor not in (meta.get("opcoes") or []):
			frappe.throw(_("Valor inválido para {0}").format(campo))

	return valor


@frappe.whitelist()
def update_extrato_celulas(transaction_ids: str | list, campo: str, valor: str | int | None = None):
	"""Grava um campo editável em uma ou mais transações e devolve as linhas atualizadas.

	É o endpoint da edição inline do grid: o mesmo caminho atende a alteração
	de uma célula e a aplicação do valor a toda a seleção.

	Args:
		transaction_ids: nomes das transações (JSON string ou lista).
		campo: chave em `EXTRATO_CAMPOS_EDITAVEIS`.
		valor: novo valor; vazio limpa o campo (exceto em booleano).

	Returns:
		dict: `updated_count`, `falhas` e o `html` das linhas já regravadas.
	"""
	if frappe.session.user == "Guest" or not user_has_access("/financeiro/extrato"):
		frappe.throw(_("Sem permissão para editar o extrato"), frappe.PermissionError)

	if isinstance(transaction_ids, str):
		try:
			transaction_ids = json.loads(transaction_ids)
		except ValueError:
			transaction_ids = []

	if not transaction_ids or not isinstance(transaction_ids, list):
		frappe.throw(_("Nenhuma transação selecionada"))

	if len(transaction_ids) > EXTRATO_MAX_EDICAO_LOTE:
		frappe.throw(_("Selecione no máximo {0} transações por edição").format(EXTRATO_MAX_EDICAO_LOTE))

	novo_valor = _normalizar_valor_editavel(campo, valor)

	atualizadas: list[str] = []
	falhas = 0
	for transaction_id in transaction_ids:
		try:
			doc = frappe.get_doc("Transacao Extrato Geral", transaction_id)
			setattr(doc, campo, novo_valor)
			doc.save(ignore_permissions=False)
			atualizadas.append(transaction_id)
		except frappe.PermissionError:
			# Sem permissão de escrita não há edição em lote possível: avisa e para.
			raise
		except Exception as erro:
			falhas += 1
			frappe.log_error(f"Erro ao editar transação {transaction_id}: {erro!s}")

	colunas = get_extrato_colunas("Gestor Financeiro" in frappe.get_roles())
	linhas = (
		get_extrato_transacoes(
			{"name": ["in", atualizadas]},
			start=0,
			page_length=len(atualizadas),
			colunas=colunas,
		)
		if atualizadas
		else []
	)

	return {
		"updated_count": len(atualizadas),
		"falhas": falhas,
		"html": render_extrato_rows(linhas, colunas),
	}
