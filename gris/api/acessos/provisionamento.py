"""O que acontece quando a última etapa aprova um pedido.

* **Papel do Gris** — concedido na hora, sem passar por ``User.save()`` (que repopula os
  papéis a partir do Role Profile e apagaria concessões manuais).
* **Drive** — vira uma concessão manual no Single do Workspace; um job concede no Google
  em seguida, e a rodada diária do mecanismo existente é a garantia.
* **Ferramenta** — fica "Aguardando concessão" até a equipe criar a conta com o
  id@escoteiros e confirmar na gestão. A vaga é reservada já na aprovação.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now_datetime

from gris.api.acessos import drives, notificacoes
from gris.api.acessos.catalogo import vagas_por_ferramenta
from gris.api.acessos.constantes import (
	ACESSO_DOCTYPE,
	LICENCA_ATIVA,
	LICENCA_DOCTYPE,
	SOLICITACAO_DOCTYPE,
	STATUS_AGUARDANDO_CONCESSAO,
	STATUS_CONCEDIDA,
	TIPO_DRIVE,
	TIPO_FERRAMENTA,
	TIPO_PAPEL,
)
from gris.api.acessos.permissoes import garantir_gestor
from gris.api.users.roles import add_user_roles, remove_user_roles

ROLE_DESENVOLVEDOR = "Desenvolvedor"


def _logger():
	return frappe.logger("acessos_provisionamento", allow_site=True)


def registrar_no_usuario(user: str, texto: str) -> None:
	"""Deixa a concessão na linha do tempo do User.

	A gravação direta em ``Has Role`` não gera ``Version``: sem este comentário, não
	sobraria rastro de quem deu ou tirou o papel.
	"""
	frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Info",
			"reference_doctype": "User",
			"reference_name": user,
			"content": texto,
		}
	).insert(ignore_permissions=True)


def sincronizar_hooks_de_papel(papeis) -> None:
	"""O que o ``on_update`` de User faria se a concessão tivesse passado por ele."""
	if ROLE_DESENVOLVEDOR in set(papeis or []):
		from gris.gestao_de_tarefas.board_sync_sugestoes import sincronizar_desenvolvedores_no_board

		sincronizar_desenvolvedores_no_board()


def conceder_papel(user: str, papel: str, origem: str) -> bool:
	adicionados = add_user_roles(user, [papel])
	if adicionados:
		sincronizar_hooks_de_papel(adicionados)
		registrar_no_usuario(
			user,
			_("Papel {0} concedido pelo portal de acessos ({1}) por {2}.").format(
				papel, origem, frappe.session.user
			),
		)
	return bool(adicionados)


def revogar_papel(user: str, papel: str, origem: str) -> bool:
	removidos = remove_user_roles(user, [papel])
	if removidos:
		sincronizar_hooks_de_papel(removidos)
		registrar_no_usuario(
			user,
			_("Papel {0} revogado pelo portal de acessos ({1}) por {2}.").format(
				papel, origem, frappe.session.user
			),
		)
	return bool(removidos)


def garantir_vaga(acesso: str) -> None:
	"""Bloqueia a aprovação quando a ferramenta não tem mais licença livre.

	A linha do ``Acesso`` é travada (``for_update``) para duas aprovações simultâneas não
	ocuparem a mesma última vaga.
	"""
	limite = frappe.db.get_value(ACESSO_DOCTYPE, acesso, "limite_licencas", for_update=True)
	if not limite:
		return
	vagas = vagas_por_ferramenta([acesso])
	ocupadas = int(vagas["ocupadas"].get(acesso) or 0) + int(vagas["aguardando"].get(acesso) or 0)
	if ocupadas >= int(limite):
		frappe.throw(
			_("Não há licenças disponíveis de {0}: as {1} estão em uso ou reservadas.").format(acesso, limite)
		)


def finalizar_aprovacao(solicitacao) -> None:
	"""Concede (ou encaminha a concessão) depois da última etapa aprovada."""
	item = frappe.get_doc(ACESSO_DOCTYPE, solicitacao.acesso)

	if item.tipo == TIPO_PAPEL:
		conceder_papel(solicitacao.solicitante, item.papel, solicitacao.name)
		solicitacao.status = STATUS_CONCEDIDA
		solicitacao.concedido_em = now_datetime()
		solicitacao.concedido_por = frappe.session.user
		solicitacao.save(ignore_permissions=True)
		notificacoes.avisar_solicitante(solicitacao, notificacoes.EVENTO_CONCEDIDA)
		return

	if item.tipo == TIPO_DRIVE:
		linha = drives.registrar_concessao_manual(
			associado=solicitacao.associado,
			email=solicitacao.email_concessao,
			drive_id=item.drive_id,
			tipo_acesso=item.permissao_drive,
			observacao=_("Portal de acessos: {0}").format(solicitacao.name),
		)
		solicitacao.concessao_drive = linha
		solicitacao.status = STATUS_AGUARDANDO_CONCESSAO
		solicitacao.save(ignore_permissions=True)
		notificacoes.avisar_solicitante(solicitacao, notificacoes.EVENTO_APROVADA)
		drives.enfileirar_concessao(solicitacao.name, linha)
		return

	if item.tipo == TIPO_FERRAMENTA:
		garantir_vaga(item.name)
		solicitacao.status = STATUS_AGUARDANDO_CONCESSAO
		solicitacao.save(ignore_permissions=True)
		notificacoes.avisar_solicitante(solicitacao, notificacoes.EVENTO_APROVADA)
		notificacoes.avisar_concessao_manual(solicitacao)
		return

	frappe.throw(_("Tipo de acesso desconhecido: {0}.").format(item.tipo))


def marcar_concedida(solicitacao: str) -> None:
	"""Fecha um pedido de drive quando a concessão chega ao Google."""
	doc = frappe.get_doc(SOLICITACAO_DOCTYPE, solicitacao)
	if doc.status != STATUS_AGUARDANDO_CONCESSAO:
		return
	doc.status = STATUS_CONCEDIDA
	doc.concedido_em = now_datetime()
	doc.save(ignore_permissions=True)
	notificacoes.avisar_solicitante(doc, notificacoes.EVENTO_CONCEDIDA)


@frappe.whitelist(methods=["POST"])
def confirmar_concessao(solicitacao: str, observacao: str | None = None) -> dict:
	"""A equipe criou a conta na ferramenta: a licença passa a contar e a pessoa é avisada."""
	garantir_gestor()
	doc = frappe.get_doc(SOLICITACAO_DOCTYPE, solicitacao, for_update=True)
	if doc.tipo != TIPO_FERRAMENTA or doc.status != STATUS_AGUARDANDO_CONCESSAO:
		frappe.throw(_("Só pedidos de ferramenta aguardando concessão podem ser confirmados."))

	licenca = frappe.get_doc(
		{
			"doctype": LICENCA_DOCTYPE,
			"acesso": doc.acesso,
			"associado": doc.associado,
			"status": LICENCA_ATIVA,
			"solicitacao": doc.name,
			"observacao": (observacao or "").strip() or None,
		}
	).insert(ignore_permissions=True)

	doc.licenca = licenca.name
	doc.status = STATUS_CONCEDIDA
	doc.concedido_em = now_datetime()
	doc.concedido_por = frappe.session.user
	doc.save(ignore_permissions=True)
	notificacoes.avisar_solicitante(doc, notificacoes.EVENTO_CONCEDIDA)

	from gris.api.acessos.solicitacoes import resumo

	return {"ok": True, "solicitacao": resumo(doc)}


def reconciliar_concessoes_drive() -> None:
	"""Job diário: fecha os pedidos de drive que a rodada do Workspace já concedeu.

	Cobre o caso em que o job imediato falhou (ou a integração estava desligada) e a
	concessão só chegou ao Google pela rodada diária do mecanismo existente.
	"""
	pendentes = frappe.get_all(
		SOLICITACAO_DOCTYPE,
		filters={
			"status": STATUS_AGUARDANDO_CONCESSAO,
			"tipo": TIPO_DRIVE,
			"concessao_drive": ["is", "set"],
		},
		fields=["name", "concessao_drive"],
	)
	for pendente in pendentes:
		if drives.concessao_foi_aplicada(pendente.concessao_drive):
			marcar_concedida(pendente.name)
			_logger().info(f"Pedido de drive {pendente.name} concedido pela rodada diária.")
