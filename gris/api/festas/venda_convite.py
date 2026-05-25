"""Endpoints públicos da página /festas/venda_convite.

Toda a precificação ocorre no servidor: o front envia apenas
`opcao_convite` + `quantidade`. O valor de cada item de convite é resolvido
no controller `Convite Festa` a partir da `Opcao Convite Festa` linkada.
A doação aceita um valor numérico do front, mas é validada e só aplicada
quando a festa tem `aceitar_doacoes = 1` e o valor é > 0.
"""

from __future__ import annotations

import json
import re

import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils import flt, getdate, today

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DOACAO_MIN_VALOR = 1.0
DOACAO_MAX_VALOR = 100.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_json(value, label: str) -> list | dict:
	if value is None:
		return []
	if isinstance(value, (list, dict)):
		return value
	try:
		return json.loads(value)
	except (ValueError, TypeError):
		frappe.throw(f"{label} inválido(a).")


def _festa_aberta(festa_name: str) -> dict:
	row = frappe.db.get_value(
		"Festa",
		festa_name,
		[
			"name",
			"nome_festa",
			"data",
			"aceitar_doacoes",
			"data_limite_vendas",
			"status",
		],
		as_dict=True,
	)
	if not row:
		frappe.throw("Festa não encontrada.", frappe.DoesNotExistError)
	if not row.data_limite_vendas:
		frappe.throw("As vendas para esta festa ainda não foram abertas.")
	if getdate(today()) > getdate(row.data_limite_vendas):
		frappe.throw("O período de vendas para esta festa foi encerrado.")
	if row.status and row.status != "Em andamento":
		frappe.throw("Esta festa não está mais aceitando vendas.")
	return {
		"name": row.name,
		"nome_festa": row.nome_festa or row.name,
		"data": row.data.isoformat() if row.data else "",
		"aceitar_doacoes": bool(row.aceitar_doacoes),
		"data_limite_vendas": row.data_limite_vendas.isoformat()
		if row.data_limite_vendas
		else "",
	}


def _validar_itens(festa_name: str, itens_raw) -> tuple[list[dict], float, int]:
	itens = _parse_json(itens_raw, "Itens")
	if not isinstance(itens, list) or not itens:
		frappe.throw("Adicione pelo menos um convite ao carrinho.")

	# Agrega quantidades por opção (evita duplicatas no payload).
	agregado: dict[str, int] = {}
	for item in itens:
		if not isinstance(item, dict):
			frappe.throw("Item inválido.")
		opcao_name = (item.get("opcao_convite") or "").strip()
		quantidade = item.get("quantidade")
		if not opcao_name:
			frappe.throw("Selecione uma opção de convite válida.")
		try:
			quantidade = int(quantidade)
		except (ValueError, TypeError):
			frappe.throw("Quantidade inválida.")
		if quantidade <= 0:
			continue
		agregado[opcao_name] = agregado.get(opcao_name, 0) + quantidade

	if not agregado:
		frappe.throw("Adicione pelo menos um convite ao carrinho.")

	opcoes = frappe.get_all(
		"Opcao Convite Festa",
		filters={"name": ("in", list(agregado.keys()))},
		fields=["name", "festa", "ativo", "nome_convite", "valor", "portaria"],
	)
	indexado = {row.name: row for row in opcoes}

	resumo_itens: list[dict] = []
	subtotal = 0.0
	total_convites = 0
	tem_portaria = False
	tem_nao_portaria = False
	for opcao_name, quantidade in agregado.items():
		opcao = indexado.get(opcao_name)
		if not opcao:
			frappe.throw("Opção de convite inválida.")
		if opcao.festa != festa_name:
			frappe.throw("Opção de convite não pertence a esta festa.")
		if not opcao.ativo:
			frappe.throw(f"A opção '{opcao.nome_convite}' está inativa.")
		if opcao.portaria:
			tem_portaria = True
		else:
			tem_nao_portaria = True
		valor = flt(opcao.valor)
		subtotal += valor * quantidade
		total_convites += quantidade
		resumo_itens.append(
			{
				"opcao_convite": opcao_name,
				"nome_convite": opcao.nome_convite,
				"quantidade": quantidade,
				"valor_unitario": valor,
				"subtotal": valor * quantidade,
			}
		)

	# Regra de negócio: convite de portaria não pode ser misturado com outros.
	if tem_portaria and tem_nao_portaria:
		frappe.throw(
			"Convites de portaria não podem ser comprados junto com outros tipos."
		)

	return resumo_itens, subtotal, total_convites


def _validar_doacao(festa: dict, doacao_valor) -> float:
	if doacao_valor in (None, ""):
		return 0.0
	try:
		valor = flt(doacao_valor)
	except (ValueError, TypeError):
		frappe.throw("Valor da doação inválido.")
	if valor <= 0:
		return 0.0
	if not festa.get("aceitar_doacoes"):
		frappe.throw("Esta festa não aceita doações.")
	if valor < DOACAO_MIN_VALOR or valor > DOACAO_MAX_VALOR:
		frappe.throw(
			f"O valor da doação deve estar entre R$ {DOACAO_MIN_VALOR:.0f} e R$ {DOACAO_MAX_VALOR:.0f}."
		)
	return float(valor)


def _validar_pagador(pagador_raw) -> dict:
	pagador = _parse_json(pagador_raw, "Dados do pagador")
	if not isinstance(pagador, dict):
		frappe.throw("Dados do pagador inválidos.")
	nome = (pagador.get("nome") or "").strip()
	email = (pagador.get("email") or "").strip().lower()
	telefone = re.sub(r"\D", "", (pagador.get("telefone") or ""))
	if not nome:
		frappe.throw("Informe o nome do pagador.")
	if not email or not EMAIL_REGEX.match(email):
		frappe.throw("E-mail do pagador inválido.")
	if not telefone or len(telefone) < 10:
		frappe.throw("Telefone do pagador inválido.")
	return {"nome": nome, "email": email, "telefone": telefone}


def _validar_convidados(convidados_raw, total_convites: int, pagador_recebe: bool, pagador: dict) -> list[dict]:
	"""Valida e normaliza a lista de convidados.

	Em qualquer cenário o front envia uma linha por convite com pelo menos o
	nome — a portaria precisa identificar quem entrou. Email e telefone são
	obrigatórios apenas quando o pagador NÃO recebe todos os QR codes (cada
	convidado recebe o próprio).
	"""
	convidados = _parse_json(convidados_raw, "Lista de convidados")
	if not isinstance(convidados, list) or len(convidados) != total_convites:
		frappe.throw(
			f"Informe o nome de exatamente {total_convites} convidado(s)."
		)
	saida: list[dict] = []
	for c in convidados:
		if not isinstance(c, dict):
			frappe.throw("Convidado inválido.")
		nome = (c.get("nome") or "").strip()
		email = (c.get("email") or "").strip().lower()
		telefone = re.sub(r"\D", "", (c.get("telefone") or ""))
		if not nome:
			frappe.throw("Todo convidado precisa de nome.")
		if pagador_recebe:
			# QR codes vão todos para o e-mail do pagador; ignoramos email/tel
			# individuais para evitar coleta desnecessária de dado pessoal.
			saida.append({"nome": nome, "email": "", "telefone": ""})
			continue
		if not email or not EMAIL_REGEX.match(email):
			frappe.throw(f"E-mail do convidado '{nome}' é inválido.")
		saida.append({"nome": nome, "email": email, "telefone": telefone})
	return saida


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@frappe.whitelist(allow_guest=True)
def listar_festas_abertas() -> list[dict]:
	rows = frappe.get_all(
		"Festa",
		filters={
			"data_limite_vendas": [">=", today()],
			"status": "Em andamento",
		},
		fields=["name", "nome_festa", "data", "aceitar_doacoes", "data_limite_vendas"],
		order_by="data asc",
	)
	return [
		{
			"name": r.name,
			"nome_festa": r.nome_festa or r.name,
			"data": r.data.isoformat() if r.data else "",
			"aceitar_doacoes": bool(r.aceitar_doacoes),
			"data_limite_vendas": r.data_limite_vendas.isoformat()
			if r.data_limite_vendas
			else "",
		}
		for r in rows
	]


@frappe.whitelist(allow_guest=True)
def listar_opcoes(festa_name: str) -> dict:
	festa = _festa_aberta(festa_name)
	opcoes_rows = frappe.get_all(
		"Opcao Convite Festa",
		filters={"festa": festa_name, "ativo": 1},
		fields=[
			"name",
			"nome_convite",
			"valor",
			"quantidade_esperada",
			"quantidade_vendida",
			"imagem_capa",
		],
		order_by="valor asc",
	)
	return {
		"festa": festa,
		"opcoes": [
			{
				"name": r.name,
				"nome_convite": r.nome_convite or "",
				"valor": flt(r.valor),
				"quantidade_esperada": int(r.quantidade_esperada or 0),
				"quantidade_vendida": int(r.quantidade_vendida or 0),
				"imagem_capa": r.imagem_capa or "",
			}
			for r in opcoes_rows
		],
	}


@frappe.whitelist(allow_guest=True)
def get_resumo_carrinho(festa_name: str, itens, doacao_valor=0) -> dict:
	festa = _festa_aberta(festa_name)
	resumo_itens, subtotal, total_convites = _validar_itens(festa_name, itens)
	valor_doacao = _validar_doacao(festa, doacao_valor)
	return {
		"itens": resumo_itens,
		"subtotal_convites": subtotal,
		"valor_doacao": valor_doacao,
		"total": subtotal + valor_doacao,
		"total_convites": total_convites,
		"aceitar_doacoes": festa["aceitar_doacoes"],
	}


@frappe.whitelist(allow_guest=True)
@rate_limit(key="venda-convite", limit=10, seconds=60)
def criar_convite(
	festa_name: str,
	pagador,
	itens,
	doacao_valor=0,
	convidados=None,
	pagador_recebe_qr_codes=1,
) -> dict:
	festa = _festa_aberta(festa_name)
	pagador_data = _validar_pagador(pagador)
	resumo_itens, _, total_convites = _validar_itens(festa_name, itens)
	valor_doacao = _validar_doacao(festa, doacao_valor)
	pagador_recebe_flag = 1 if pagador_recebe_qr_codes in ("1", "true", "True", True, 1) else 0
	convidados_data = _validar_convidados(
		convidados, total_convites, bool(pagador_recebe_flag), pagador_data
	)

	itens_doc = [
		{
			"eh_convite": 1,
			"opcao_convite": item["opcao_convite"],
			"quantidade": item["quantidade"],
		}
		for item in resumo_itens
	]
	if valor_doacao > 0:
		itens_doc.append(
			{
				"eh_convite": 0,
				"descricao": "Doação",
				"quantidade": 1,
				"valor": valor_doacao,
			}
		)

	savepoint = f"venda_convite_{frappe.generate_hash(length=8)}"
	frappe.db.savepoint(savepoint)
	try:
		convite = frappe.get_doc(
			{
				"doctype": "Convite Festa",
				"festa": festa_name,
				"nome_pagador": pagador_data["nome"],
				"email_pagador": pagador_data["email"],
				"telefone_pagador": pagador_data["telefone"],
				"pagador_recebe_qr_codes": pagador_recebe_flag,
				"itens": itens_doc,
				"convidados": convidados_data,
			}
		)
		convite.insert(ignore_permissions=True)
		frappe.db.commit()
	except Exception as exc:
		frappe.db.rollback(save_point=savepoint)
		frappe.log_error(
			message=frappe.get_traceback(),
			title="Erro em venda_convite.criar_convite",
		)
		if isinstance(exc, frappe.ValidationError):
			raise
		frappe.throw("Não foi possível registrar o pedido. Tente novamente.")

	link_pagamento = ""
	if convite.cobranca_infinitepay:
		link_pagamento = (
			frappe.db.get_value(
				"Cobranca Infinitepay", convite.cobranca_infinitepay, "link_pagamento"
			)
			or ""
		)

	return {
		"ok": True,
		"convite_name": convite.name,
		"link_pagamento": link_pagamento,
	}


@frappe.whitelist(allow_guest=True)
def get_status_pagamento(convite_name: str) -> dict:
	if not convite_name:
		frappe.throw("Parâmetro 'convite_name' obrigatório.")
	cobranca_name = frappe.db.get_value(
		"Convite Festa", convite_name, "cobranca_infinitepay"
	)
	if not cobranca_name:
		return {"status": "Pendente", "link_pagamento": ""}
	row = frappe.db.get_value(
		"Cobranca Infinitepay",
		cobranca_name,
		["status", "link_pagamento"],
		as_dict=True,
	) or {}
	return {
		"status": row.get("status") or "Pendente",
		"link_pagamento": row.get("link_pagamento") or "",
	}
