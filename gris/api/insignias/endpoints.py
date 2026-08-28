"""Endpoints do fluxo de solicitação de insígnias e distintivos.

Fluxo: Solicitada -> Comprada -> Recebida -> Entregue (com Cancelada como saída).
Todas as mudanças de status passam por aqui para que a permissão de cada etapa
seja checada no servidor, e não apenas escondida na interface.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from gris.api.insignias import permissoes
from gris.gris.doctype.solicitacao_de_insignias.solicitacao_de_insignias import (
	STATUS_CANCELADA,
	STATUS_COMPRADA,
	STATUS_ENTREGUE,
	STATUS_RECEBIDA,
	STATUS_SOLICITADA,
)

DOCTYPE = "Solicitacao de Insignias"

RAMOS_VALIDOS = {
	"Filhotes",
	"Lobinho",
	"Escoteiro",
	"Sênior",
	"Pioneiro",
	"Escotistas e Dirigentes",
	"Grupo (geral)",
}

MAX_ITENS = 100
MAX_QUANTIDADE = 999

CATALOGO_DOCTYPE = "Insignia ou Distintivo"

TIPOS_VALIDOS = {
	"Distintivo de Progressão",
	"Especialidade",
	"Insígnia Especial",
	"Distintivo de Identificação",
	"Distintivo de Função",
	"Outro",
}

RAMOS_CATALOGO_VALIDOS = {
	"Todos",
	"Filhotes",
	"Lobinho",
	"Escoteiro",
	"Sênior",
	"Pioneiro",
	"Escotistas e Dirigentes",
}


def _parse_payload(payload: Any) -> dict:
	if isinstance(payload, str):
		try:
			payload = json.loads(payload)
		except ValueError:
			frappe.throw(_("Dados inválidos."))
	if not isinstance(payload, dict):
		frappe.throw(_("Dados inválidos."))
	return payload


def _texto(valor: Any, limite: int = 500) -> str | None:
	texto = (str(valor) if valor is not None else "").strip()
	if not texto:
		return None
	return texto[:limite]


def _data_valida(valor: Any, rotulo: str, obrigatoria: bool = True):
	bruto = _texto(valor, 20)
	if not bruto:
		if obrigatoria:
			frappe.throw(f"Informe {rotulo}.")
		return None
	try:
		data = getdate(bruto)
	except Exception:
		frappe.throw(f"{rotulo.capitalize()} inválida.")
	if data > getdate(today()):
		frappe.throw(f"{rotulo.capitalize()} não pode estar no futuro.")
	return data


def _valor_positivo(valor: Any, rotulo: str) -> float:
	numero = flt(valor)
	if numero < 0:
		frappe.throw(f"{rotulo} não pode ser negativo.")
	return numero


def _carregar(name: str):
	nome = _texto(name, 140)
	if not nome or not frappe.db.exists(DOCTYPE, nome):
		frappe.throw(_("Solicitação não encontrada."))
	return frappe.get_doc(DOCTYPE, nome)


def _normalizar_itens(itens_brutos: Any) -> list[dict]:
	if not isinstance(itens_brutos, list) or not itens_brutos:
		frappe.throw(_("Inclua ao menos um item na solicitação."))
	if len(itens_brutos) > MAX_ITENS:
		frappe.throw(_("Uma solicitação pode ter no máximo {0} itens.").format(MAX_ITENS))

	catalogo_cache: dict[str, dict] = {}
	itens: list[dict] = []

	for bruto in itens_brutos:
		if not isinstance(bruto, dict):
			frappe.throw(_("Item inválido na solicitação."))

		insignia = _texto(bruto.get("insignia"), 140)
		if not insignia:
			frappe.throw(_("Selecione a insígnia ou distintivo de cada item."))

		if insignia not in catalogo_cache:
			registro = frappe.db.get_value(
				"Insignia ou Distintivo",
				insignia,
				["name", "tipo", "ramo", "valor_unitario", "ativo"],
				as_dict=True,
			)
			if not registro:
				frappe.throw(f"A insígnia '{insignia}' não existe no catálogo.")
			if not registro.ativo:
				frappe.throw(f"A insígnia '{insignia}' está inativa e não pode ser solicitada.")
			catalogo_cache[insignia] = registro

		catalogo = catalogo_cache[insignia]

		try:
			quantidade = int(bruto.get("quantidade") or 0)
		except (TypeError, ValueError):
			frappe.throw(f"Quantidade inválida para '{insignia}'.")
		if quantidade < 1:
			frappe.throw(f"A quantidade de '{insignia}' deve ser maior que zero.")
		if quantidade > MAX_QUANTIDADE:
			frappe.throw(f"A quantidade de '{insignia}' excede o limite de {MAX_QUANTIDADE}.")

		beneficiario = _texto(bruto.get("beneficiario"), 140)
		if beneficiario and not frappe.db.exists("Associado", beneficiario):
			frappe.throw(_("Beneficiário selecionado não existe."))

		itens.append(
			{
				"insignia": insignia,
				"tipo": catalogo.tipo,
				"ramo": catalogo.ramo,
				"quantidade": quantidade,
				# Valor de referência vem sempre do catálogo — nunca do cliente.
				"valor_unitario": flt(catalogo.valor_unitario),
				"beneficiario": beneficiario,
				"observacao": _texto(bruto.get("observacao"), 140),
			}
		)

	return itens


@frappe.whitelist(methods=["POST"])
def salvar_item_catalogo(payload):
	"""Cria ou edita um item do catálogo a partir do portal.

	O nome é a chave do documento (autoname), então só pode ser definido na
	criação: renomear quebraria o vínculo com solicitações já registradas.
	"""
	permissoes.garantir_gestor_catalogo()
	dados = _parse_payload(payload)

	tipo = _texto(dados.get("tipo"), 60)
	if tipo not in TIPOS_VALIDOS:
		frappe.throw(_("Selecione um tipo válido."))

	ramo = _texto(dados.get("ramo"), 60)
	if ramo not in RAMOS_CATALOGO_VALIDOS:
		frappe.throw(_("Selecione um ramo válido."))

	valor_unitario = _valor_positivo(dados.get("valor_unitario"), "O valor unitário")
	codigo = _texto(dados.get("codigo"), 140)
	descricao = _texto(dados.get("descricao"), 500)

	name = _texto(dados.get("name"), 140)
	if name:
		if not frappe.db.exists(CATALOGO_DOCTYPE, name):
			frappe.throw(_("Item do catálogo não encontrado."))
		doc = frappe.get_doc(CATALOGO_DOCTYPE, name)
		criado = False
	else:
		nome = _texto(dados.get("nome"), 140)
		if not nome or len(nome) < 3:
			frappe.throw(_("Informe um nome com pelo menos 3 caracteres."))
		if frappe.db.exists(CATALOGO_DOCTYPE, nome):
			frappe.throw(f"Já existe um item chamado '{nome}'.")
		doc = frappe.new_doc(CATALOGO_DOCTYPE)
		doc.nome = nome
		doc.ativo = 1
		criado = True

	doc.tipo = tipo
	doc.ramo = ramo
	doc.valor_unitario = valor_unitario
	doc.codigo = codigo
	doc.descricao = descricao

	if criado:
		doc.insert()
	else:
		doc.save()

	return {"success": True, "name": doc.name, "criado": criado}


@frappe.whitelist(methods=["POST"])
def alternar_item_catalogo(payload):
	"""Ativa ou inativa um item. Não há exclusão: itens podem estar em pedidos antigos."""
	permissoes.garantir_gestor_catalogo()
	dados = _parse_payload(payload)

	name = _texto(dados.get("name"), 140)
	if not name or not frappe.db.exists(CATALOGO_DOCTYPE, name):
		frappe.throw(_("Item do catálogo não encontrado."))

	doc = frappe.get_doc(CATALOGO_DOCTYPE, name)
	doc.ativo = 0 if doc.ativo else 1
	doc.save()

	return {"success": True, "name": doc.name, "ativo": bool(doc.ativo)}


@frappe.whitelist(methods=["POST"])
def criar_solicitacao(payload):
	permissoes.garantir_solicitante()
	dados = _parse_payload(payload)

	ramo = _texto(dados.get("ramo"), 60)
	if ramo not in RAMOS_VALIDOS:
		frappe.throw(_("Selecione o ramo ou seção da solicitação."))

	itens = _normalizar_itens(dados.get("itens"))

	doc = frappe.new_doc(DOCTYPE)
	doc.solicitante = frappe.session.user
	doc.data_solicitacao = today()
	doc.status = STATUS_SOLICITADA
	doc.ramo = ramo
	doc.justificativa = _texto(dados.get("justificativa"), 1000)
	for item in itens:
		doc.append("itens", item)
	doc.insert()

	return {
		"success": True,
		"name": doc.name,
		"redirect": f"/insignias/solicitacao?name={doc.name}",
	}


@frappe.whitelist(methods=["POST"])
def registrar_compra(payload):
	"""Financeiro informa que a compra foi realizada."""
	permissoes.garantir_financeiro()
	dados = _parse_payload(payload)

	doc = _carregar(dados.get("name"))
	if doc.status != STATUS_SOLICITADA:
		frappe.throw(f"Só é possível registrar a compra de uma solicitação em '{STATUS_SOLICITADA}'.")

	doc.data_compra = _data_valida(dados.get("data_compra"), "a data da compra")
	doc.valor_pago = _valor_positivo(dados.get("valor_pago"), "O valor pago")
	doc.fornecedor = _texto(dados.get("fornecedor"), 140)
	doc.numero_documento = _texto(dados.get("numero_documento"), 140)
	doc.observacoes_compra = _texto(dados.get("observacoes_compra"), 1000)
	doc.comprado_por = frappe.session.user
	doc.status = STATUS_COMPRADA
	doc.save()

	return {"success": True, "name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def registrar_recebimento(payload):
	"""Financeiro confirma que o material chegou ao grupo."""
	permissoes.garantir_financeiro()
	dados = _parse_payload(payload)

	doc = _carregar(dados.get("name"))
	if doc.status != STATUS_COMPRADA:
		frappe.throw(_("Só é possível registrar o recebimento de uma solicitação comprada."))

	doc.data_recebimento = _data_valida(dados.get("data_recebimento"), "a data de recebimento")
	doc.recebido_por = frappe.session.user
	doc.status = STATUS_RECEBIDA
	doc.save()

	return {"success": True, "name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def registrar_entrega(payload):
	"""Solicitante (ou gestão) confirma que recebeu o material em mãos."""
	dados = _parse_payload(payload)
	doc = _carregar(dados.get("name"))

	if not permissoes.pode_registrar_entrega(doc):
		frappe.throw(
			_("Você não tem permissão para registrar a entrega desta solicitação."),
			frappe.PermissionError,
		)

	doc.data_entrega = _data_valida(dados.get("data_entrega"), "a data de entrega")
	doc.observacoes_entrega = _texto(dados.get("observacoes_entrega"), 1000)
	doc.entregue_por = frappe.session.user
	doc.status = STATUS_ENTREGUE
	doc.save()

	return {"success": True, "name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def cancelar_solicitacao(payload):
	dados = _parse_payload(payload)
	doc = _carregar(dados.get("name"))

	if not permissoes.pode_cancelar(doc):
		frappe.throw(_("Você não tem permissão para cancelar esta solicitação."), frappe.PermissionError)

	motivo = _texto(dados.get("motivo"), 1000)
	if not motivo:
		frappe.throw(_("Informe o motivo do cancelamento."))

	doc.motivo_cancelamento = motivo
	doc.cancelada_por = frappe.session.user
	doc.data_cancelamento = today()
	doc.status = STATUS_CANCELADA
	doc.save()

	return {"success": True, "name": doc.name, "status": doc.status}
