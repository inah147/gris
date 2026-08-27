# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""API de conciliação entre transações de Sistema e de Planilha.

Permite comparar uma transação vinda de integração de sistema com uma transação
importada por planilha (mesma transação real registrada nas duas fontes), vinculá-las,
escolher qual delas conta no total e ajustar categoria/descrição do registro mantido.

Nenhum método aqui chama frappe.db.commit(): o Frappe já commita ao final da requisição
bem-sucedida, e o commit explícito quebraria o rollback dos testes (FrappeTestCase),
persistindo dados de teste no site.
"""

import json
import unicodedata

import frappe

# Campos de categorização que podem ser aplicados ao registro mantido na conciliação.
# Mantém a mesma regra de gris.api.financeiro.transactions.batch_update_transactions.
CAMPOS_CATEGORIZACAO = (
	"descricao_reduzida",
	"categoria",
	"centro_de_custo",
	"ordinaria_extraordinaria",
)

# Janela de tolerância padrão para casar candidatos.
TOLERANCIA_VALOR = 1.0  # ±R$1,00
JANELA_DIAS = 5


def _verificar_permissao():
	"""Conciliar altera totais; exige permissão de escrita no doctype."""
	if not frappe.has_permission("Transacao Extrato Geral", ptype="write"):
		frappe.throw("Sem permissão para conciliar transações.", frappe.PermissionError)


def _normalizar(texto):
	if not texto:
		return ""
	texto = texto.lower()
	texto = unicodedata.normalize("NFD", texto)
	return "".join(c for c in texto if unicodedata.category(c) != "Mn").strip()


def _similaridade(a, b):
	"""Similaridade simples 0..1 por sobreposição de palavras (para ranquear candidatos)."""
	na, nb = _normalizar(a), _normalizar(b)
	if not na or not nb:
		return 0.0
	sa, sb = set(na.split()), set(nb.split())
	if not sa or not sb:
		return 0.0
	return len(sa & sb) / len(sa | sb)


def _serializar(doc_dict):
	"""Campos exibidos na tela de comparação."""
	return {
		"name": doc_dict.get("name"),
		"fonte": doc_dict.get("fonte"),
		"data_transacao": doc_dict.get("data_transacao"),
		"data_deposito": doc_dict.get("data_deposito"),
		"timestamp_transacao": doc_dict.get("timestamp_transacao"),
		"descricao": doc_dict.get("descricao"),
		"descricao_reduzida": doc_dict.get("descricao_reduzida"),
		"valor": doc_dict.get("valor"),
		"debito_credito": doc_dict.get("debito_credito"),
		"metodo": doc_dict.get("metodo"),
		"instituicao": doc_dict.get("instituicao"),
		"carteira": doc_dict.get("carteira"),
		"categoria": doc_dict.get("categoria"),
		"centro_de_custo": doc_dict.get("centro_de_custo"),
		"ordinaria_extraordinaria": doc_dict.get("ordinaria_extraordinaria"),
		"status_conciliacao": doc_dict.get("status_conciliacao"),
	}


_CAMPOS_LISTA = [
	"name",
	"fonte",
	"data_transacao",
	"data_deposito",
	"timestamp_transacao",
	"descricao",
	"descricao_reduzida",
	"valor",
	"debito_credito",
	"metodo",
	"instituicao",
	"carteira",
	"categoria",
	"centro_de_custo",
	"ordinaria_extraordinaria",
	"status_conciliacao",
]


@frappe.whitelist()
def get_sistema_pendentes(carteira=None, instituicao=None, limit=100):
	"""Lista transações de Sistema ainda não conciliadas."""
	_verificar_permissao()
	filtros = {
		"fonte": "Sistema",
		"status_conciliacao": ["!=", "Conciliada"],
	}
	if carteira:
		filtros["carteira"] = carteira
	if instituicao:
		filtros["instituicao"] = instituicao

	rows = frappe.get_all(
		"Transacao Extrato Geral",
		fields=_CAMPOS_LISTA,
		filters=filtros,
		order_by="COALESCE(data_deposito, timestamp_transacao) desc",
		limit_page_length=int(limit) if limit else 100,
	)
	return [_serializar(r) for r in rows]


@frappe.whitelist()
def get_candidatos_planilha(sistema_id):
	"""Retorna candidatos de Planilha para a transação de sistema informada.

	Casa por valor absoluto próximo (±R$1) e data próxima (janela de dias), ranqueando
	por proximidade de valor, data e similaridade de descrição.
	"""
	_verificar_permissao()
	sistema = frappe.db.get_value(
		"Transacao Extrato Geral",
		sistema_id,
		_CAMPOS_LISTA,
		as_dict=True,
	)
	if not sistema:
		frappe.throw("Transação de sistema não encontrada.")

	valor = float(sistema.get("valor") or 0)
	valor_abs = abs(valor)
	# Data de referência para janela de proximidade.
	data_ref = (
		sistema.get("data_deposito") or sistema.get("timestamp_transacao") or sistema.get("data_transacao")
	)

	params = {
		"valor_min": valor_abs - TOLERANCIA_VALOR,
		"valor_max": valor_abs + TOLERANCIA_VALOR,
		"self_id": sistema_id,
	}
	conditions = [
		"fonte = 'Planilha'",
		"COALESCE(status_conciliacao,'Não conciliada') != 'Conciliada'",
		"name != %(self_id)s",
		"ABS(valor) BETWEEN %(valor_min)s AND %(valor_max)s",
	]
	# Mesmo sinal (crédito/débito) para não casar entrada com saída.
	if valor > 0:
		conditions.append("valor > 0")
	elif valor < 0:
		conditions.append("valor < 0")

	if data_ref:
		conditions.append(
			"COALESCE(data_deposito, timestamp_transacao, data_transacao) "
			"BETWEEN DATE_SUB(%(data_ref)s, INTERVAL %(janela)s DAY) "
			"AND DATE_ADD(%(data_ref)s, INTERVAL %(janela)s DAY)"
		)
		params["data_ref"] = data_ref
		params["janela"] = JANELA_DIAS

	where_sql = " AND ".join(conditions)
	campos_sql = ", ".join(f"`{c}`" for c in _CAMPOS_LISTA)
	# A interpolação é segura: os campos vêm de _CAMPOS_LISTA e as condições são
	# literais deste módulo — todo valor de usuário entra por `params`.
	rows = frappe.db.sql(
		f"SELECT {campos_sql} FROM `tabTransacao Extrato Geral` WHERE {where_sql} LIMIT 50",
		params,
		as_dict=True,
	)

	desc_sistema = sistema.get("descricao") or sistema.get("descricao_reduzida") or ""
	candidatos = []
	for r in rows:
		desc_cand = r.get("descricao") or r.get("descricao_reduzida") or ""
		score = _similaridade(desc_sistema, desc_cand)
		diff_valor = abs(abs(float(r.get("valor") or 0)) - valor_abs)
		item = _serializar(r)
		item["_score"] = score
		item["_diff_valor"] = diff_valor
		candidatos.append(item)

	# Ordena: menor diferença de valor, maior similaridade de descrição.
	candidatos.sort(key=lambda c: (round(c["_diff_valor"], 2), -c["_score"]))
	return {"sistema": _serializar(sistema), "candidatos": candidatos}


@frappe.whitelist()
def conciliar(
	sistema_id,
	planilha_id,
	manter="sistema",
	categoria=None,
	descricao_reduzida=None,
	centro_de_custo=None,
	ordinaria_extraordinaria=None,
):
	"""Vincula o par sistema/planilha, define qual conta no total e categoriza o mantido.

	Args:
		sistema_id, planilha_id: nomes das transações a conciliar.
		manter: 'sistema' ou 'planilha' — qual registro permanece nos totais.
		categoria/descricao_reduzida/centro_de_custo/ordinaria_extraordinaria: opcionais,
			aplicados ao registro mantido.
	"""
	_verificar_permissao()

	if manter not in ("sistema", "planilha"):
		frappe.throw("Parâmetro 'manter' inválido (use 'sistema' ou 'planilha').")
	if sistema_id == planilha_id:
		frappe.throw("Não é possível conciliar uma transação com ela mesma.")

	doc_sistema = frappe.get_doc("Transacao Extrato Geral", sistema_id)
	doc_planilha = frappe.get_doc("Transacao Extrato Geral", planilha_id)

	# Evita reconciliar registros já vinculados a outros pares.
	for d in (doc_sistema, doc_planilha):
		if d.status_conciliacao == "Conciliada" and d.transacao_conciliada not in (
			sistema_id,
			planilha_id,
			None,
			"",
		):
			frappe.throw(f"A transação {d.name} já está conciliada com {d.transacao_conciliada}.")

	mantido = doc_sistema if manter == "sistema" else doc_planilha
	excluido = doc_planilha if manter == "sistema" else doc_sistema

	# Vínculo recíproco.
	doc_sistema.transacao_conciliada = planilha_id
	doc_planilha.transacao_conciliada = sistema_id
	doc_sistema.status_conciliacao = "Conciliada"
	doc_planilha.status_conciliacao = "Conciliada"

	mantido.excluir_do_total = 0
	excluido.excluir_do_total = 1
	mantido.transacao_revisada = 1

	# Categorização opcional aplicada ao registro mantido.
	valores = {
		"categoria": categoria,
		"descricao_reduzida": descricao_reduzida,
		"centro_de_custo": centro_de_custo,
		"ordinaria_extraordinaria": ordinaria_extraordinaria,
	}
	for campo, valor in valores.items():
		if campo in CAMPOS_CATEGORIZACAO and valor not in (None, ""):
			setattr(mantido, campo, valor)

	doc_sistema.save(ignore_permissions=False)
	doc_planilha.save(ignore_permissions=False)

	return {
		"success": True,
		"mantido": mantido.name,
		"excluido": excluido.name,
	}


@frappe.whitelist()
def marcar_sem_duplicata(
	sistema_id,
	categoria=None,
	descricao_reduzida=None,
	centro_de_custo=None,
	ordinaria_extraordinaria=None,
):
	"""Marca a transação de sistema como resolvida sem par (não é duplicata).

	Ela permanece contando nos totais (excluir_do_total=0), sai da fila de pendentes
	(status_conciliacao='Conciliada', sem transacao_conciliada) e é marcada como revisada.
	Aceita categorização opcional.
	"""
	_verificar_permissao()

	doc = frappe.get_doc("Transacao Extrato Geral", sistema_id)
	doc.transacao_conciliada = None
	doc.status_conciliacao = "Conciliada"
	doc.excluir_do_total = 0
	doc.transacao_revisada = 1

	valores = {
		"categoria": categoria,
		"descricao_reduzida": descricao_reduzida,
		"centro_de_custo": centro_de_custo,
		"ordinaria_extraordinaria": ordinaria_extraordinaria,
	}
	for campo, valor in valores.items():
		if campo in CAMPOS_CATEGORIZACAO and valor not in (None, ""):
			setattr(doc, campo, valor)

	doc.save(ignore_permissions=False)
	return {"success": True, "resolvido": doc.name}


@frappe.whitelist()
def desconciliar(transacao_id):
	"""Desfaz uma conciliação, devolvendo ambos os registros aos totais."""
	_verificar_permissao()

	doc = frappe.get_doc("Transacao Extrato Geral", transacao_id)
	par_id = doc.transacao_conciliada

	docs = [doc]
	if par_id and frappe.db.exists("Transacao Extrato Geral", par_id):
		docs.append(frappe.get_doc("Transacao Extrato Geral", par_id))

	for d in docs:
		d.transacao_conciliada = None
		d.status_conciliacao = "Não conciliada"
		d.excluir_do_total = 0
		d.save(ignore_permissions=False)

	return {"success": True, "desconciliados": [d.name for d in docs]}
