"""Solicitações de acesso: pedir, cancelar e decidir cada etapa do fluxo."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now_datetime

from gris.api.acessos import notificacoes
from gris.api.acessos.catalogo import SITUACAO_NAO_TEM, estado_do_item
from gris.api.acessos.constantes import (
	ACESSO_DOCTYPE,
	DECISAO_APROVADA,
	DECISAO_RECUSADA,
	SOLICITACAO_DOCTYPE,
	STATUS_ABERTOS,
	STATUS_CANCELADA,
	STATUS_EM_APROVACAO,
	STATUS_RECUSADA,
)
from gris.api.acessos.permissoes import (
	associado_do_usuario,
	eh_gestor,
	garantir_decisao,
	garantir_portal,
	pode_decidir,
)

LIMITE_JUSTIFICATIVA = 1000
DECISOES = {"aprovar": DECISAO_APROVADA, "recusar": DECISAO_RECUSADA}


def _texto(valor: str | None, limite: int = LIMITE_JUSTIFICATIVA) -> str | None:
	texto = (valor or "").strip()
	if len(texto) > limite:
		frappe.throw(_("O texto pode ter no máximo {0} caracteres.").format(limite))
	return texto or None


def resumo(solicitacao, user: str | None = None) -> dict:
	"""O que a tela mostra de uma solicitação, inclusive o fluxo de etapas."""
	user = user or frappe.session.user
	return {
		"name": solicitacao.name,
		"acesso": solicitacao.acesso,
		"tipo": solicitacao.tipo,
		"status": solicitacao.status,
		"solicitante": solicitacao.solicitante,
		"solicitante_nome": solicitacao.solicitante_nome,
		"email_concessao": solicitacao.email_concessao,
		"justificativa": solicitacao.justificativa,
		"motivo": solicitacao.motivo,
		"etapa_atual": solicitacao.etapa_atual,
		"total_etapas": solicitacao.total_de_etapas(),
		"criada_em": str(solicitacao.creation),
		"concedido_em": str(solicitacao.concedido_em) if solicitacao.concedido_em else None,
		"etapas": [
			{
				"ordem": etapa.ordem,
				"descricao": etapa.descricao,
				"papel_aprovador": etapa.papel_aprovador,
				"decisao": etapa.decisao,
				"decidido_por": frappe.utils.get_fullname(etapa.decidido_por) if etapa.decidido_por else None,
				"decidido_em": str(etapa.decidido_em) if etapa.decidido_em else None,
				"observacao": etapa.observacao,
			}
			for etapa in solicitacao.etapas or []
		],
		"pode_cancelar": solicitacao.status in STATUS_ABERTOS
		and (solicitacao.solicitante == user or eh_gestor(user)),
		"pode_decidir": pode_decidir(solicitacao, user),
	}


def solicitacoes_de(user: str, limite: int = 30) -> list[dict]:
	nomes = frappe.get_all(
		SOLICITACAO_DOCTYPE,
		filters={"solicitante": user},
		pluck="name",
		order_by="creation desc",
		limit_page_length=limite,
	)
	return [resumo(frappe.get_doc(SOLICITACAO_DOCTYPE, nome), user) for nome in nomes]


def pendentes_para(user: str) -> list[dict]:
	"""Pedidos de outras pessoas cuja etapa corrente ``user`` pode decidir.

	O volume em aprovação é de dezenas: carregar cada uma e reusar `pode_decidir` mantém
	uma única regra de quem decide, em vez de uma consulta paralela que pode divergir.
	"""
	nomes = frappe.get_all(
		SOLICITACAO_DOCTYPE,
		filters={"status": STATUS_EM_APROVACAO, "solicitante": ["!=", user]},
		pluck="name",
		order_by="creation asc",
	)
	pendentes = []
	for nome in nomes:
		solicitacao = frappe.get_doc(SOLICITACAO_DOCTYPE, nome)
		if pode_decidir(solicitacao, user):
			pendentes.append(resumo(solicitacao, user))
	return pendentes


@frappe.whitelist(methods=["POST"])
def solicitar(acesso: str, justificativa: str | None = None) -> dict:
	garantir_portal()
	user = frappe.session.user

	if not frappe.db.exists(ACESSO_DOCTYPE, {"name": acesso, "ativo": 1}):
		frappe.throw(_("Acesso não encontrado."))

	associado = associado_do_usuario(user)
	estado = estado_do_item(user, associado, acesso)
	if not estado:
		frappe.throw(_("Acesso não encontrado."))
	if not estado["pode_solicitar"]:
		frappe.throw(estado["motivo_bloqueio"] or _("Este acesso não pode ser solicitado agora."))
	if estado["estado"]["situacao"] != SITUACAO_NAO_TEM:
		frappe.throw(_("Você já tem este acesso."))

	solicitacao = frappe.get_doc(
		{
			"doctype": SOLICITACAO_DOCTYPE,
			"acesso": acesso,
			"solicitante": user,
			"associado": associado.name if associado else None,
			"email_concessao": estado.get("email_concessao"),
			"justificativa": _texto(justificativa),
		}
	)
	# A permissão foi checada acima (portal + item solicitável); o solicitante não
	# tem permissão de escrita no DocType, que é da gestão.
	solicitacao.insert(ignore_permissions=True)
	notificacoes.avisar_aprovadores(solicitacao)
	return {"ok": True, "solicitacao": resumo(solicitacao, user)}


@frappe.whitelist(methods=["POST"])
def cancelar(solicitacao: str, motivo: str | None = None) -> dict:
	garantir_portal()
	user = frappe.session.user
	doc = frappe.get_doc(SOLICITACAO_DOCTYPE, solicitacao, for_update=True)

	if doc.solicitante != user and not eh_gestor(user):
		frappe.throw(_("Você só pode cancelar as suas solicitações."), frappe.PermissionError)
	if doc.status not in STATUS_ABERTOS:
		frappe.throw(_("Esta solicitação já foi encerrada."))

	doc.status = STATUS_CANCELADA
	doc.motivo = _texto(motivo) or (
		_("Cancelada por quem solicitou.")
		if doc.solicitante == user
		else _("Cancelada pela gestão de acessos.")
	)
	doc.save(ignore_permissions=True)
	return {"ok": True, "solicitacao": resumo(doc, user)}


@frappe.whitelist(methods=["POST"])
def decidir(solicitacao: str, decisao: str, observacao: str | None = None) -> dict:
	"""Aprova ou recusa a etapa corrente. A última aprovação dispara a concessão."""
	garantir_portal()
	user = frappe.session.user

	valor = DECISOES.get((decisao or "").strip().lower())
	if not valor:
		frappe.throw(_("Decisão inválida."))

	doc = frappe.get_doc(SOLICITACAO_DOCTYPE, solicitacao, for_update=True)
	garantir_decisao(doc, user)
	observacao = _texto(observacao)

	etapa = doc.etapa_corrente()
	etapa.decisao = valor
	etapa.decidido_por = user
	etapa.decidido_em = now_datetime()
	etapa.observacao = observacao

	if valor == DECISAO_RECUSADA:
		if not observacao:
			frappe.throw(_("Informe o motivo da recusa: ele é enviado a quem pediu."))
		doc.status = STATUS_RECUSADA
		doc.motivo = observacao
		doc.save(ignore_permissions=True)
		notificacoes.avisar_solicitante(doc, notificacoes.EVENTO_RECUSADA)
		return {"ok": True, "solicitacao": resumo(doc, user)}

	if doc.etapa_atual < doc.total_de_etapas():
		doc.etapa_atual += 1
		doc.save(ignore_permissions=True)
		notificacoes.avisar_aprovadores(doc)
		return {"ok": True, "solicitacao": resumo(doc, user)}

	from gris.api.acessos.provisionamento import finalizar_aprovacao

	finalizar_aprovacao(doc)
	return {"ok": True, "solicitacao": resumo(doc, user)}
