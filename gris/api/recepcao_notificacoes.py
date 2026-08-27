# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Notificações WhatsApp para o fluxo de recepção de novos associados.

Responsabilidades:
- Notificar responsável quando uma visita é agendada (chamado via after_insert do controller).
- Enviar lembrete com botões de confirmação 2 dias antes da visita (scheduler diário).
"""

from __future__ import annotations

import frappe
from frappe.utils import add_days, get_url, getdate, today

from gris.api.recepcao import nomes_desistentes
from gris.utils.whatsapp import enviar_mensagem_formatada, enviar_para_grupo, enviar_texto


def _buscar_telefone_responsavel(novo_associado_name: str) -> str | None:
	"""Retorna o telefone do responsável prioritário vinculado ao Novo Associado.

	Prioridade: guardião legal > primeiro responsável.
	Usa celular como campo primário e telefone_secundario como fallback.
	"""
	links = frappe.get_all(
		"Responsavel Vinculo",
		filters={"beneficiario_novo_associado": novo_associado_name},
		fields=["responsavel", "é_guardiao_legal", "primeiro_responsavel"],
	)

	if not links:
		return None

	ordered = sorted(
		links,
		key=lambda lnk: (
			1 if lnk.get("é_guardiao_legal") else 0,
			1 if lnk.get("primeiro_responsavel") else 0,
		),
		reverse=True,
	)

	resp_ids = [lnk.get("responsavel") for lnk in ordered if lnk.get("responsavel")]
	if not resp_ids:
		return None

	responsaveis = frappe.get_all(
		"Responsavel",
		filters={"name": ["in", resp_ids]},
		fields=["name", "celular", "telefone_secundario"],
	)
	resp_map = {r.name: r for r in responsaveis}

	for lnk in ordered:
		resp = resp_map.get(lnk.get("responsavel"))
		if not resp:
			continue
		telefone = resp.get("celular") or resp.get("telefone_secundario")
		if telefone:
			return telefone

	return None


def _buscar_endereco_grupo() -> str:
	"""Monta o endereço do grupo a partir do DocType Single 'Definicao da UEL'."""
	uel = frappe.get_single("Definicao da UEL")
	partes = []
	if uel.rua:
		partes.append(uel.rua)
	if uel.numero:
		partes.append(f"nº{uel.numero}")
	if uel.bairro:
		partes.append(uel.bairro)
	return ", ".join(partes) if partes else "a confirmar"


def _calcular_idade_em_anos(data_nascimento: str | None) -> int | None:
	"""Calcula a idade completa em anos a partir da data de nascimento."""
	if not data_nascimento:
		return None

	try:
		nascimento = getdate(data_nascimento)
		hoje = getdate(today())
		idade = hoje.year - nascimento.year - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))
		return max(idade, 0)
	except Exception:
		return None


def _montar_mensagem_nova_manifestacao(
	*,
	nome_jovem: str,
	nome_responsavel: str,
	idade_anos: int | None,
) -> str:
	idade_texto = f"{idade_anos} anos" if idade_anos is not None else "não informada"
	link_visao_geral = get_url("/recepcao/visao_geral")
	return (
		"@todos\n\n"
		"🎉 Nova manifestação de interesse recebida! 🎉\n\n"
		f"*Jovem*: {nome_jovem}\n"
		f"*Responsável*: {nome_responsavel}\n"
		f"*Idade do jovem*: {idade_texto}.\n\n"
		f"Acompanhe na Visão Geral: {link_visao_geral}"
	)


def notificar_nova_manifestacao_no_grupo_recepcao(
	*,
	nome_jovem: str,
	nome_responsavel: str,
	data_nascimento_jovem: str | None,
	contexto: str,
) -> None:
	"""Envia aviso para o grupo WhatsApp da recepção sobre novo associado adicionado.

	O grupo destinatário é definido em Configurações de Recepção > Grupo de recepção (WhatsApp).
	Falha silenciosa com log para não interromper os fluxos de cadastro.
	"""
	logger = frappe.logger("recepcao_notificacoes", allow_site=True)

	grupo_jid = (
		frappe.db.get_single_value("Configuracoes de Recepcao", "grupo_recepcao_whatsapp") or ""
	).strip()
	if not grupo_jid:
		logger.warning(
			f"Notificação de nova manifestação não enviada: grupo de recepção não configurado ({contexto})."
		)
		return

	mensagem = _montar_mensagem_nova_manifestacao(
		nome_jovem=(nome_jovem or "").strip() or "Não informado",
		nome_responsavel=(nome_responsavel or "").strip() or "Não informado",
		idade_anos=_calcular_idade_em_anos(data_nascimento_jovem),
	)

	try:
		enviar_para_grupo(grupo_jid, mensagem, mencionar_todos=True)
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			f"Notificação nova manifestação (grupo recepção): {contexto}",
		)


def notificar_visita_agendada(novo_associado_name: str, data_visita: str) -> None:
	"""Envia notificação de visita agendada para o responsável via WhatsApp.

	Chamado pelo after_insert do DocType Agenda de Visitas.
	Falha silenciosa com log de aviso caso não haja telefone ou WhatsApp desabilitado.
	"""
	logger = frappe.logger("recepcao_notificacoes", allow_site=True)

	telefone = _buscar_telefone_responsavel(novo_associado_name)
	if not telefone:
		logger.warning(
			f"Notificação de visita não enviada: nenhum telefone encontrado para {novo_associado_name}."
		)
		return

	nome = frappe.db.get_value("Novo Associado", novo_associado_name, "nome_completo") or novo_associado_name
	endereco = _buscar_endereco_grupo()

	try:
		data_formatada = getdate(data_visita).strftime("%d/%m")
	except Exception:
		data_formatada = data_visita

	mensagem = (
		f"Olá! A visita de {nome} ao Grupo Escoteiro foi agendada para o dia "
		f"{data_formatada} no endereço {endereco}. Te esperamos lá! 😊"
	)

	try:
		enviar_texto(telefone, mensagem)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Notificação de agendamento: {novo_associado_name}")


def enviar_lembretes_visita() -> None:
	"""Scheduler diário: notifica responsáveis com visitas marcadas para daqui a 2 dias.

	Envia mensagem formatada com botões de confirmação para visitas ainda não confirmadas.
	Em caso de erro por visita, registra e continua as demais.
	"""
	logger = frappe.logger("recepcao_notificacoes", allow_site=True)

	data_alvo = add_days(today(), 2)
	# Quem desistiu mantém a visita registrada, mas não recebe lembrete.
	filtros = {"data_da_visita": data_alvo, "visita_confirmada": 0}
	desistentes = nomes_desistentes()
	if desistentes:
		filtros["jovem"] = ["not in", list(desistentes)]

	visitas = frappe.get_all(
		"Agenda de Visitas",
		filters=filtros,
		fields=["name", "jovem", "data_da_visita"],
	)

	if not visitas:
		return

	logger.info(f"Enviando {len(visitas)} lembrete(s) de visita para {data_alvo}.")

	botoes = [
		{"buttonId": "confirmar", "buttonText": {"displayText": "Sim, irei! ✅"}, "type": "reply"},
		{"buttonId": "cancelar", "buttonText": {"displayText": "Não poderei ir ❌"}, "type": "reply"},
	]

	for visita in visitas:
		try:
			telefone = _buscar_telefone_responsavel(visita.jovem)
			if not telefone:
				logger.warning(f"Lembrete não enviado: nenhum telefone encontrado para {visita.jovem}.")
				continue

			nome = frappe.db.get_value("Novo Associado", visita.jovem, "nome_completo") or visita.jovem

			try:
				data_formatada = getdate(visita.data_da_visita).strftime("%d/%m")
			except Exception:
				data_formatada = str(visita.data_da_visita)

			enviar_mensagem_formatada(
				telefone,
				titulo="Lembrete de Visita",
				descricao=(
					f"A visita de {nome} ao Grupo Escoteiro está marcada para {data_formatada}. "
					f"Você confirma a presença?"
				),
				botoes=botoes,
			)

		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"Lembrete de visita: {visita.jovem} ({visita.name})",
			)
