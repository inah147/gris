# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Notificacoes WhatsApp para alteracoes no Calendario."""

from __future__ import annotations

import frappe

from gris.utils.whatsapp import enviar_texto

_ROLES_METODOS = ("Gestor de Metodos", "Equipe de Metodos")

_LABEL_CAMPOS = {
	"atividade": "Atividade",
	"inicio": "Início",
	"termino": "Término",
	"local": "Local",
	"secao": "Seção",
	"nivel": "Nível",
	"sem_atividade": "Sem Atividade",
	"abertura_geral": "Abertura Geral",
}


def _buscar_telefones_por_roles(roles: tuple[str, ...]) -> list[dict]:
	"""Retorna lista de {"nome": ..., "telefone": ...} para usuarios com as roles informadas.

	Utiliza query agregada para evitar N+1: primeiro obtém todos os emails via Has Role,
	depois busca os Associados correspondentes em uma única consulta.
	"""
	user_emails = frappe.get_all(
		"Has Role",
		filters={"role": ["in", list(roles)], "parenttype": "User"},
		fields=["parent"],
		distinct=True,
	)
	if not user_emails:
		return []

	emails = [r.parent for r in user_emails]

	associados = frappe.get_all(
		"Associado",
		filters={"id_escoteiros": ["in", emails]},
		fields=["nome_completo", "telefone"],
	)

	return [
		{"nome": a.nome_completo, "telefone": a.telefone}
		for a in associados
		if (a.telefone or "").strip()
	]


def _formatar_detalhes_alteracao(changed_fields: dict[str, tuple]) -> str:
	"""Formata os campos alterados no estilo 'Campo: valor_antigo → valor_novo'."""
	if not changed_fields:
		return ""

	linhas = []
	for campo, (antes, depois) in changed_fields.items():
		label = _LABEL_CAMPOS.get(campo, campo)
		antes_str = str(antes) if antes is not None else "—"
		depois_str = str(depois) if depois is not None else "—"
		linhas.append(f"  • {label}: {antes_str} → {depois_str}")

	return "\n".join(linhas)


def notificar_alteracao_calendario(
	evento_name: str,
	tipo_alteracao: str,
	atividade: str = "",
	inicio: str = "",
	secao: str = "",
	local: str = "",
	changed_fields: dict | None = None,
) -> None:
	"""Envia notificacao WhatsApp para Gestor de Metodos e Equipe de Metodos.

	Args:
		evento_name: Name do documento Calendario.
		tipo_alteracao: "criado", "atualizado" ou "excluido".
		atividade: Nome da atividade do evento.
		inicio: Data/hora de início do evento (string formatada).
		secao: Seção do evento.
		local: Local do evento.
		changed_fields: Dict {campo: (valor_antes, valor_depois)} para tipo "atualizado".
	"""
	logger = frappe.logger("calendario_notificacoes", allow_site=True)

	try:
		destinatarios = _buscar_telefones_por_roles(_ROLES_METODOS)
		if not destinatarios:
			logger.info(
				f"Notificacao de calendario '{evento_name}' nao enviada: "
				"nenhum destinatario com Gestor de Metodos ou Equipe de Metodos possui telefone."
			)
			return

		icone = {"criado": "🗓️ Novo evento", "atualizado": "✏️ Evento atualizado", "excluido": "🗑️ Evento removido"}.get(
			tipo_alteracao, "📅 Alteração no calendário"
		)

		linhas = [icone, ""]

		if atividade:
			linhas.append(f"*Atividade:* {atividade}")
		if inicio:
			linhas.append(f"*Data/Hora:* {inicio}")
		if secao:
			linhas.append(f"*Seção:* {secao}")
		if local:
			linhas.append(f"*Local:* {local}")

		if tipo_alteracao == "atualizado" and changed_fields:
			detalhes = _formatar_detalhes_alteracao(changed_fields)
			if detalhes:
				linhas.append("")
				linhas.append("*Alterações:*")
				linhas.append(detalhes)

		linhas.append("")
		linhas.append("_Mensagem automática do Gris_")

		mensagem = "\n".join(linhas)

		for dest in destinatarios:
			try:
				enviar_texto(dest["telefone"], mensagem)
			except Exception:
				frappe.log_error(
					frappe.get_traceback(),
					f"Notificacao calendario para {dest.get('nome')} ({dest.get('telefone')})",
				)

		logger.info(
			f"Notificacao de calendario '{evento_name}' ({tipo_alteracao}) "
			f"enfileirada para {len(destinatarios)} destinatario(s)."
		)

	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Notificacao calendario {evento_name}")
