# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Cobrança da contribuição mensal por link de pagamento InfinitePay.

O ciclo completo mora aqui:

1. O gestor escolhe um contribuinte e as competências em aberto (a apuração de
   `gris.api.financeiro.contribuicoes` diz quais são e quanto falta em cada uma).
2. Uma `Cobranca Infinitepay` com `finalidade = "Contribuição Mensal"` é criada e
   o `after_insert` dela busca o link de pagamento na InfinitePay.
3. O link vai para o responsável pelo WhatsApp, no telefone de cobrança do
   associado.
4. Quando a InfinitePay confirma o pagamento — pelo webhook ou pela sincronização
   manual — `on_cobranca_atualizada` lança no extrato o crédito que quita as
   competências cobradas.

A baixa é um lançamento em `Transacao Extrato Geral` porque é dali que a apuração
lê: marcar o pagamento em qualquer outro lugar não mudaria a situação do mês na
tela. O lançamento nasce com a data real do pagamento em `data_transacao` (o caixa
não é distorcido) e a competência mais antiga cobrada em `mes_competencia` — as
competências seguintes são quitadas pelo crédito que sobra, que é como a apuração
já trata quem paga adiantado.
"""

from __future__ import annotations

import datetime
import re

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime

from gris.api.financeiro.contribuicoes import (
	CATEGORIA_CONTRIBUICAO,
	MESES_PADRAO,
	ROLE_GESTOR,
	apurar_associados,
	competencias_pendentes,
	normalizar_meses,
)

# Valor de `finalidade` que liga a cobrança ao fluxo da contribuição mensal.
FINALIDADE_CONTRIBUICAO = "Contribuição Mensal"

# Método de pagamento registrado no extrato: o link da InfinitePay é cartão.
METODO_LANCAMENTO = "Cartão"

# Prefixo do `id` (que dá nome ao documento) da transação de baixa. Deixa o
# lançamento rastreável até a cobrança que o originou e, como `id` é único,
# funciona como trava contra baixa duplicada mesmo se o vínculo se perder.
PREFIXO_ID_TRANSACAO = "COBIP-"

# Quantos meses para trás a tela oferece para cobrar.
MESES_COBRANCA = 12

PADRAO_COMPETENCIA = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _assert_gestor() -> None:
	if ROLE_GESTOR not in frappe.get_roles():
		frappe.throw(
			_("Requer acesso Gestor Contribuição Mensal para cobrar contribuições."),
			frappe.PermissionError,
		)


def _normalizar_competencias(competencias) -> list[str]:
	"""Aceita lista ou CSV e devolve competências AAAA-MM válidas, sem repetição."""
	if isinstance(competencias, str):
		bruto = competencias.split(",")
	elif isinstance(competencias, list | tuple):
		bruto = list(competencias)
	else:
		bruto = []

	vistas: list[str] = []
	for item in bruto:
		ym = str(item or "").strip()
		if not ym:
			continue
		if not PADRAO_COMPETENCIA.match(ym):
			frappe.throw(_("Competência inválida: {0}. Use o formato AAAA-MM.").format(ym))
		if ym not in vistas:
			vistas.append(ym)
	return sorted(vistas)


def _primeiro_dia(ym: str) -> datetime.date:
	ano, mes = ym.split("-")
	return datetime.date(int(ano), int(mes), 1)


def _rotulo(ym: str) -> str:
	return _primeiro_dia(ym).strftime("%m/%Y")


def get_situacao_para_cobranca(associado: str, meses=MESES_COBRANCA) -> dict:
	"""Apuração de um contribuinte com as competências que podem ser cobradas."""
	apuracoes = apurar_associados([associado], normalizar_meses(meses))
	if not apuracoes:
		frappe.throw(
			_("Associado não encontrado entre os contribuintes da contribuição mensal."),
			frappe.DoesNotExistError,
		)
	apuracao = apuracoes[0]
	return {
		"associado": apuracao,
		"pendentes": competencias_pendentes(apuracao),
		"cobrancas": listar_cobrancas(associado),
	}


def listar_cobrancas(associado: str, limite: int = 10) -> list[dict]:
	"""Cobranças de contribuição já emitidas para o associado, da mais recente."""
	return frappe.get_all(
		"Cobranca Infinitepay",
		filters={"associado": associado, "finalidade": FINALIDADE_CONTRIBUICAO},
		fields=[
			"name",
			"status",
			"link_pagamento",
			"competencias",
			"transacao_extrato",
			"creation",
		],
		order_by="creation desc",
		limit_page_length=limite,
	)


def _dados_do_associado(associado: str) -> dict:
	dados = frappe.db.get_value(
		"Associado",
		associado,
		["name", "nome_completo", "email_cobranca", "telefone_cobranca", "email", "telefone"],
		as_dict=True,
	)
	if not dados:
		frappe.throw(_("Associado {0} não encontrado.").format(associado), frappe.DoesNotExistError)
	return dados


def montar_cobranca(associado: str, competencias, meses=MESES_COBRANCA) -> dict:
	"""Cria a `Cobranca Infinitepay` das competências pedidas e devolve o link.

	As competências são conferidas contra a apuração no momento da emissão: só
	entra na cobrança o mês que continua em aberto e pelo valor que ainda falta.
	Cobrar um mês já quitado só geraria crédito e confundiria quem paga.
	"""
	_assert_gestor()

	pedidas = _normalizar_competencias(competencias)
	if not pedidas:
		frappe.throw(_("Selecione ao menos uma competência para cobrar."))

	situacao = get_situacao_para_cobranca(associado, meses)
	pendentes_por_ym = {p["ym"]: p for p in situacao["pendentes"]}

	fora = [ym for ym in pedidas if ym not in pendentes_por_ym]
	if fora:
		frappe.throw(
			_("Estas competências não estão em aberto para o associado: {0}.").format(
				", ".join(_rotulo(ym) for ym in fora)
			)
		)

	dados = _dados_do_associado(associado)
	nome = dados.get("nome_completo") or associado

	itens = [
		{
			"descricao": _("Contribuição mensal {0} — {1}").format(_rotulo(ym), nome),
			"quantidade": 1,
			"preco": pendentes_por_ym[ym]["valor"],
		}
		for ym in pedidas
	]

	cobranca = frappe.get_doc(
		{
			"doctype": "Cobranca Infinitepay",
			"order_nsu": _proximo_order_nsu(associado),
			"status": "Pendente",
			"finalidade": FINALIDADE_CONTRIBUICAO,
			"associado": associado,
			"competencias": ",".join(pedidas),
			"customer_name": nome,
			"customer_email": dados.get("email_cobranca") or dados.get("email") or "",
			"customer_phone": dados.get("telefone_cobranca") or dados.get("telefone") or "",
			"itens": itens,
		}
	)
	cobranca.insert()
	cobranca.reload()

	return {
		"name": cobranca.name,
		"link_pagamento": cobranca.link_pagamento or "",
		"competencias": pedidas,
		"valor_total": round(sum(item["preco"] for item in itens), 2),
		"telefone": cobranca.customer_phone or "",
	}


def _proximo_order_nsu(associado: str) -> str:
	"""Identificador único da cobrança, legível no painel da InfinitePay."""
	carimbo = now_datetime().strftime("%Y%m%d%H%M%S")
	return f"CM-{associado}-{carimbo}"


def montar_mensagem(cobranca: dict, nome_associado: str) -> str:
	"""Texto enviado ao responsável, com as competências e o link."""
	rotulos = ", ".join(_rotulo(ym) for ym in cobranca["competencias"])
	valor = frappe.utils.fmt_money(cobranca["valor_total"], currency="BRL")
	plural = "às contribuições" if len(cobranca["competencias"]) > 1 else "à contribuição"
	return (
		f"Olá! Segue o link para pagamento referente {plural} de {nome_associado}.\n\n"
		f"Competência: {rotulos}\n"
		f"Valor: {valor}\n\n"
		f"{cobranca['link_pagamento']}\n\n"
		"O pagamento é confirmado automaticamente e a contribuição fica quitada no sistema. "
		"Se já tiver pago, pode ignorar esta mensagem."
	)


@frappe.whitelist()
def get_cobranca_do_associado(associado: str, meses: str | int = MESES_COBRANCA):
	"""Competências em aberto e cobranças já emitidas, para montar a tela."""
	_assert_gestor()
	if not associado:
		frappe.throw(_("Parâmetro 'associado' é obrigatório."), frappe.ValidationError)
	return {"success": True, **get_situacao_para_cobranca(associado, meses)}


@frappe.whitelist()
def gerar_cobranca(
	associado: str,
	competencias: str | list | None = None,
	enviar_whatsapp: str | int | bool = 1,
	meses: str | int = MESES_COBRANCA,
):
	"""Gera o link de pagamento das competências e, se pedido, manda no WhatsApp.

	O envio é a última etapa de propósito: se o WhatsApp falhar, a cobrança e o
	link continuam válidos e a tela mostra o link para envio manual.
	"""
	_assert_gestor()
	if not associado:
		frappe.throw(_("Parâmetro 'associado' é obrigatório."), frappe.ValidationError)

	cobranca = montar_cobranca(associado, competencias, meses)

	if not cobranca["link_pagamento"]:
		frappe.throw(
			_("A InfinitePay não devolveu o link de pagamento. Verifique a cobrança {0}.").format(
				cobranca["name"]
			)
		)

	resultado = {"success": True, "cobranca": cobranca, "whatsapp": None}
	if frappe.utils.cint(enviar_whatsapp):
		resultado["whatsapp"] = _enviar_whatsapp(cobranca, associado)
	return resultado


@frappe.whitelist()
def enviar_cobranca_whatsapp(name: str):
	"""Reenvia pelo WhatsApp o link de uma cobrança já emitida."""
	_assert_gestor()
	cobranca = frappe.get_doc("Cobranca Infinitepay", name)
	if cobranca.finalidade != FINALIDADE_CONTRIBUICAO:
		frappe.throw(_("A cobrança {0} não é de contribuição mensal.").format(name))
	if not cobranca.link_pagamento:
		frappe.throw(_("A cobrança {0} ainda não tem link de pagamento.").format(name))

	dados = {
		"name": cobranca.name,
		"link_pagamento": cobranca.link_pagamento,
		"competencias": _normalizar_competencias(cobranca.competencias),
		"valor_total": round(
			sum(float(item.quantidade or 0) * float(item.preco or 0) for item in cobranca.itens), 2
		),
		"telefone": cobranca.customer_phone or "",
	}
	return {"success": True, "whatsapp": _enviar_whatsapp(dados, cobranca.associado)}


def _enviar_whatsapp(cobranca: dict, associado: str) -> dict:
	"""Envia o link e devolve o que aconteceu, sem derrubar a geração da cobrança.

	O envio é síncrono (`enqueue=False`) porque quem clicou no botão precisa saber
	na hora se a mensagem saiu — enfileirar engoliria a falha num job que ninguém
	acompanha. A falha volta como resultado, não como exceção: a cobrança e o link
	continuam válidos e a tela oferece o envio manual.
	"""
	from gris.utils.whatsapp import enviar_texto
	from gris.utils.whatsapp_errors import (
		WhatsAppConfigurationError,
		WhatsAppNumberNotFoundError,
		WhatsAppRequestError,
	)

	dados = _dados_do_associado(associado)
	nome = dados.get("nome_completo") or associado
	telefone = cobranca.get("telefone") or dados.get("telefone_cobranca") or dados.get("telefone")

	if not telefone:
		return {
			"enviado": False,
			"motivo": _("O associado não tem telefone de cobrança cadastrado."),
		}

	try:
		enviar_texto(telefone, montar_mensagem(cobranca, nome), enqueue=False)
	except (
		WhatsAppConfigurationError,
		WhatsAppNumberNotFoundError,
		WhatsAppRequestError,
	) as erro:
		frappe.log_error(
			title="Falha ao enviar cobrança de contribuição no WhatsApp",
			message=f"cobranca={cobranca.get('name')} associado={associado}: {erro}",
		)
		return {"enviado": False, "motivo": str(erro)}

	return {"enviado": True, "telefone": telefone}


def on_cobranca_atualizada(doc, method=None):
	"""Dá baixa na contribuição quando a InfinitePay confirma o pagamento.

	Registrado em `doc_events` do `on_update` de `Cobranca Infinitepay`, o mesmo
	gancho por onde o módulo de festas escuta. Roda tanto no webhook quanto na
	sincronização manual, e é idempotente: a cobrança que já tem
	`transacao_extrato` não lança de novo.
	"""
	if doc.finalidade != FINALIDADE_CONTRIBUICAO or doc.status != "Pago":
		return
	if doc.transacao_extrato:
		return
	if not doc.associado:
		frappe.log_error(
			title="Cobrança de contribuição paga sem associado",
			message=f"cobranca={doc.name}: baixa não lançada porque o associado está vazio.",
		)
		return

	lancar_baixa(doc)


def lancar_baixa(doc) -> str | None:
	"""Cria o crédito no extrato que quita as competências cobradas."""
	competencias = _normalizar_competencias(doc.competencias)
	if not competencias:
		frappe.log_error(
			title="Cobrança de contribuição paga sem competências",
			message=f"cobranca={doc.name}: baixa não lançada porque não há competência cobrada.",
		)
		return None

	id_transacao = f"{PREFIXO_ID_TRANSACAO}{doc.name}"
	existente = frappe.db.exists("Transacao Extrato Geral", id_transacao)
	if existente:
		# Baixa já lançada numa passagem anterior que não conseguiu gravar o
		# vínculo. Reaponta em vez de duplicar o crédito.
		frappe.db.set_value("Cobranca Infinitepay", doc.name, "transacao_extrato", id_transacao)
		return id_transacao

	# `paid_amount` vem em centavos da InfinitePay; quando faltar, o valor dos
	# itens é o que foi cobrado.
	valor = (
		round(float(doc.paid_amount) / 100.0, 2)
		if doc.paid_amount
		else round(sum(float(i.quantidade or 0) * float(i.preco or 0) for i in doc.itens), 2)
	)

	nome_associado = frappe.db.get_value("Associado", doc.associado, "nome_completo") or doc.associado
	rotulos = ", ".join(_rotulo(ym) for ym in competencias)

	transacao = frappe.get_doc(
		{
			"doctype": "Transacao Extrato Geral",
			"id": id_transacao,
			"descricao": f"Contribuição mensal {rotulos} — {nome_associado}",
			"debito_credito": "Crédito",
			"valor": valor,
			"data_transacao": getdate(),
			"mes_competencia": _primeiro_dia(competencias[0]),
			"metodo": METODO_LANCAMENTO,
			"categoria": CATEGORIA_CONTRIBUICAO,
			"beneficiario": doc.associado,
			"ordinaria_extraordinaria": "Ordinária",
			"observacoes": (
				f"Baixa automática da cobrança InfinitePay {doc.name}. "
				f"Competências quitadas: {rotulos}. "
				f"transaction_nsu={doc.transaction_nsu or '—'}."
			),
		}
	)
	transacao.insert(ignore_permissions=True)

	frappe.db.set_value("Cobranca Infinitepay", doc.name, "transacao_extrato", transacao.name)
	frappe.logger().info(
		f"Contribuição quitada pela cobrança {doc.name}: transação {transacao.name} "
		f"para {doc.associado} nas competências {rotulos}."
	)
	return transacao.name
