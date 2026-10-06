"""Licenças de ferramentas quando o associado fica inativo.

Inativo (``status_no_grupo``) é o gatilho, e não o registro vencido: é quando a pessoa
deixa o grupo. Drive e usuário do Gris já têm revogação automática na inativação
(``access_manager.revoke_all_access_for_associate`` e ``manage_associate_users``). As
ferramentas sem API (Canva, Microsoft 365) não: as licenças entram em "revogação
pendente" e o grupo de tecnologia recebe a lista do que remover à mão. A vaga só volta
quando a gestão confirma a remoção.

Se a pessoa voltar a ficar ativa antes disso, as licenças pendentes por inativação
voltam a valer — a conta ainda existe na ferramenta.
"""

from __future__ import annotations

import frappe
from frappe.utils import now_datetime

from gris.api.acessos import notificacoes
from gris.api.acessos.constantes import (
	LICENCA_ATIVA,
	LICENCA_DOCTYPE,
	LICENCA_REVOGACAO_PENDENTE,
	MOTIVO_INATIVACAO,
	SOLICITACAO_DOCTYPE,
	STATUS_ABERTOS,
	STATUS_CANCELADA,
)
from gris.utils.job_logger import definir_resumo, metrica, obter_logger

INATIVO = "Inativo"
ATIVO = "Ativo"


def _logger():
	return obter_logger("acessos_inatividade")


def _tem_o_que_fazer(associado: str) -> bool:
	return bool(
		frappe.db.exists(LICENCA_DOCTYPE, {"associado": associado, "status": LICENCA_ATIVA})
		or frappe.db.exists(SOLICITACAO_DOCTYPE, {"associado": associado, "status": ["in", STATUS_ABERTOS]})
		or frappe.db.exists(
			LICENCA_DOCTYPE,
			{
				"associado": associado,
				"status": LICENCA_REVOGACAO_PENDENTE,
				"motivo_revogacao": MOTIVO_INATIVACAO,
			},
		)
	)


def ao_atualizar_associado(doc, method=None) -> None:
	"""`doc_events` `on_update` de Associado: reage à mudança de ``status_no_grupo``."""
	if frappe.flags.in_install or frappe.flags.in_patch or frappe.flags.in_migrate:
		return

	anterior = doc.get_doc_before_save()
	status_anterior = anterior.status_no_grupo if anterior else None
	if status_anterior == doc.status_no_grupo or not _tem_o_que_fazer(doc.name):
		return

	if doc.status_no_grupo == INATIVO:
		frappe.enqueue(
			"gris.api.acessos.inatividade.processar_inativacoes",
			queue="short",
			enqueue_after_commit=True,
			associados=[doc.name],
		)
	elif doc.status_no_grupo == ATIVO and status_anterior == INATIVO:
		frappe.enqueue(
			"gris.api.acessos.inatividade.processar_reativacoes",
			queue="short",
			enqueue_after_commit=True,
			associados=[doc.name],
		)


def processar_inativacoes(associados: list[str]) -> dict:
	"""Licenças ativas viram pendentes, pedidos abertos são cancelados e o grupo é avisado."""
	if not associados:
		return {"licencas": 0, "solicitacoes": 0, "avisados": 0}

	licencas = 0
	for nome in frappe.get_all(
		LICENCA_DOCTYPE,
		filters={"associado": ["in", associados], "status": LICENCA_ATIVA},
		pluck="name",
	):
		licenca = frappe.get_doc(LICENCA_DOCTYPE, nome)
		licenca.status = LICENCA_REVOGACAO_PENDENTE
		licenca.motivo_revogacao = MOTIVO_INATIVACAO
		licenca.save(ignore_permissions=True)
		licencas += 1

	solicitacoes = 0
	for nome in frappe.get_all(
		SOLICITACAO_DOCTYPE,
		filters={"associado": ["in", associados], "status": ["in", STATUS_ABERTOS]},
		pluck="name",
	):
		solicitacao = frappe.get_doc(SOLICITACAO_DOCTYPE, nome)
		solicitacao.status = STATUS_CANCELADA
		solicitacao.motivo = "Cancelada automaticamente: o associado ficou inativo."
		solicitacao.save(ignore_permissions=True)
		solicitacoes += 1

	avisados = avisar_pendentes(associados)
	return {"licencas": licencas, "solicitacoes": solicitacoes, "avisados": avisados}


def avisar_pendentes(associados: list[str] | None = None) -> int:
	"""Uma mensagem ao grupo com as licenças pendentes por inativação ainda não avisadas.

	O carimbo ``aviso_tecnologia_enviado_em`` garante que cada licença apareça uma vez
	só; sem grupo configurado ela fica sem carimbo e a próxima rodada tenta de novo.
	"""
	filtros = {
		"status": LICENCA_REVOGACAO_PENDENTE,
		"motivo_revogacao": MOTIVO_INATIVACAO,
		"aviso_tecnologia_enviado_em": ["is", "not set"],
	}
	if associados:
		filtros["associado"] = ["in", associados]

	pendentes = frappe.get_all(
		LICENCA_DOCTYPE,
		filters=filtros,
		fields=["name", "associado", "nome", "email", "acesso"],
		order_by="nome asc, acesso asc",
	)
	if not pendentes:
		return 0

	por_associado: dict[str, dict] = {}
	for licenca in pendentes:
		item = por_associado.setdefault(
			licenca.associado, {"nome": licenca.nome, "email": licenca.email, "licencas": []}
		)
		item["licencas"].append(licenca.acesso)

	if not notificacoes.avisar_tecnologia_inativos(list(por_associado.values())):
		return 0

	agora = now_datetime()
	for licenca in pendentes:
		frappe.db.set_value(
			LICENCA_DOCTYPE, licenca.name, "aviso_tecnologia_enviado_em", agora, update_modified=False
		)
	return len(por_associado)


def processar_reativacoes(associados: list[str]) -> int:
	"""Quem voltou a ficar ativo antes da revogação mantém as licenças."""
	if not associados:
		return 0
	reativadas = 0
	for nome in frappe.get_all(
		LICENCA_DOCTYPE,
		filters={
			"associado": ["in", associados],
			"status": LICENCA_REVOGACAO_PENDENTE,
			"motivo_revogacao": MOTIVO_INATIVACAO,
		},
		pluck="name",
	):
		licenca = frappe.get_doc(LICENCA_DOCTYPE, nome)
		licenca.status = LICENCA_ATIVA
		licenca.save(ignore_permissions=True)
		reativadas += 1
	return reativadas


def processar_inativos() -> None:
	"""Job diário, rede de segurança do ``on_update``.

	Pega mudanças de ``status_no_grupo`` que não passaram pelo ``on_update`` (gravações
	diretas no banco, importações) e reenvia avisos que ficaram sem grupo configurado.
	"""
	logger = _logger()

	licenca = frappe.qb.DocType(LICENCA_DOCTYPE)
	associado = frappe.qb.DocType("Associado")

	inativos = [
		linha[0]
		for linha in (
			frappe.qb.from_(licenca)
			.join(associado)
			.on(associado.name == licenca.associado)
			.select(licenca.associado)
			.distinct()
			.where(licenca.status == LICENCA_ATIVA)
			.where(associado.status_no_grupo == INATIVO)
		).run()
	]
	reativados = [
		linha[0]
		for linha in (
			frappe.qb.from_(licenca)
			.join(associado)
			.on(associado.name == licenca.associado)
			.select(licenca.associado)
			.distinct()
			.where(licenca.status == LICENCA_REVOGACAO_PENDENTE)
			.where(licenca.motivo_revogacao == MOTIVO_INATIVACAO)
			.where(associado.status_no_grupo == ATIVO)
		).run()
	]

	resultado = (
		processar_inativacoes(inativos) if inativos else {"licencas": 0, "solicitacoes": 0, "avisados": 0}
	)
	# Pendências antigas que ficaram sem aviso (grupo não configurado na época).
	avisados = resultado["avisados"] + avisar_pendentes()
	reativadas = processar_reativacoes(reativados)

	metrica("licencas_pendentes", resultado["licencas"], incrementar=False)
	metrica("solicitacoes_canceladas", resultado["solicitacoes"], incrementar=False)
	metrica("associados_avisados", avisados, incrementar=False)
	metrica("licencas_reativadas", reativadas, incrementar=False)
	logger.info(
		f"{resultado['licencas']} licença(s) marcadas para revogação, "
		f"{avisados} associado(s) avisados ao grupo de tecnologia, {reativadas} licença(s) reativadas."
	)
	definir_resumo(
		f"{resultado['licencas']} licença(s) pendentes de revogação; "
		f"{avisados} associado(s) avisados; {reativadas} licença(s) reativadas."
	)
