# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Aviso WhatsApp de seguimento do registro provisório de novos associados.

Regra de negócio: quando um Novo Associado está com o registro provisório ativado
(``tipo_de_registro`` "Provisório" + ``registro_provisorio_efetivado``) há mais de N dias
(padrão 20, configurável em Configurações de Recepção), o responsável administrativo recebe
um aviso por WhatsApp para entrar em contato com o responsável do novo associado e questionar
se o registro efetivo (definitivo) vai seguir.

O aviso é enviado uma única vez por ciclo — o campo ``data_aviso_seguimento_provisorio``
do Novo Associado registra o envio e é limpo caso o registro provisório seja desmarcado.
"""

from __future__ import annotations

import frappe
from frappe.utils import add_days, date_diff, format_date, get_url, getdate, today

from gris.api.recepcao_mensagens import _buscar_contatos_responsaveis, _extrair_primeiro_nome
from gris.utils.job_logger import definir_resumo, metrica, obter_logger
from gris.utils.whatsapp import enviar_texto

SETTINGS_DOCTYPE = "Configuracoes de Recepcao"
DIAS_PADRAO_AVISO = 20
STATUS_IGNORADOS = ["Fila de espera", "Concluído"]


def _dias_para_aviso() -> int:
	"""Dias de espera configurados em Configurações de Recepção (padrão: 20)."""
	valor = frappe.db.get_single_value(SETTINGS_DOCTYPE, "dias_aviso_seguimento_provisorio")
	try:
		dias = int(valor)
	except (TypeError, ValueError):
		return DIAS_PADRAO_AVISO

	return dias if dias > 0 else DIAS_PADRAO_AVISO


def _buscar_responsavel_administrativo() -> frappe._dict | None:
	"""Associado configurado como responsável administrativo em Configurações de Recepção."""
	associado_name = frappe.db.get_single_value(SETTINGS_DOCTYPE, "responsavel_administrativo")
	if not associado_name:
		return None

	return frappe.db.get_value(
		"Associado",
		associado_name,
		["name", "nome_completo", "telefone"],
		as_dict=True,
	)


def _montar_mensagem_aviso(
	*,
	responsavel_administrativo: frappe._dict,
	nome_jovem: str,
	data_ativacao,
	dias_decorridos: int,
	contato_responsavel: frappe._dict | None,
) -> str:
	primeiro_nome_admin = _extrair_primeiro_nome(responsavel_administrativo.get("nome_completo"))

	if contato_responsavel and (contato_responsavel.get("nome") or contato_responsavel.get("telefone")):
		nome_responsavel = contato_responsavel.get("nome") or "Responsável"
		telefone_responsavel = contato_responsavel.get("telefone")
		contato_texto = (
			f"*Responsável*: {nome_responsavel} ({telefone_responsavel})"
			if telefone_responsavel
			else f"*Responsável*: {nome_responsavel} (sem telefone cadastrado)"
		)
	else:
		contato_texto = "*Responsável*: não cadastrado no Gris"

	return (
		f"Oi, {primeiro_nome_admin}!\n\n"
		f"⏰ O registro provisório de *{nome_jovem}* foi ativado em {format_date(data_ativacao)} "
		f"e já faz {dias_decorridos} dia(s).\n\n"
		f"{contato_texto}\n\n"
		"Entre em contato e confirme se a família vai seguir com o registro efetivo (definitivo).\n\n"
		f"Acompanhe na Visão Geral: {get_url('/recepcao/visao_geral')}\n\n"
		"_Mensagem automática do Gris_"
	)


def enviar_avisos_seguimento_registro_provisorio() -> None:
	"""Scheduler diário: avisa o responsável administrativo sobre registros provisórios parados."""
	logger = obter_logger("registro_provisorio_notificacoes")
	data_hoje = getdate(today())
	dias_limite = _dias_para_aviso()
	data_limite = add_days(data_hoje, -dias_limite)

	novos_associados = frappe.get_all(
		"Novo Associado",
		filters={
			"tipo_de_registro": "Provisório",
			"registro_provisorio_efetivado": 1,
			"registro_definitivo_efetivado": 0,
			"registro_definitivo_pago": 0,
			"status": ["not in", STATUS_IGNORADOS],
			"data_registro_provisorio_efetivado": ["<=", data_limite],
			"data_aviso_seguimento_provisorio": ["is", "not set"],
		},
		fields=["name", "nome_completo", "data_registro_provisorio_efetivado"],
	)

	if not novos_associados:
		logger.info(
			"Aviso de seguimento do registro provisório: nenhum novo associado elegível "
			f"({dias_limite} dia(s) de espera)."
		)
		definir_resumo(f"Nenhum registro provisório parado há mais de {dias_limite} dia(s) — nada a avisar.")
		return

	logger.info(f"{len(novos_associados)} registro(s) provisório(s) elegíveis para aviso.")
	metrica("elegiveis", len(novos_associados), incrementar=False)

	responsavel_administrativo = _buscar_responsavel_administrativo()
	if not responsavel_administrativo:
		logger.warning(
			"Aviso de seguimento do registro provisório não enviado: responsavel_administrativo "
			f"não configurado em {SETTINGS_DOCTYPE}."
		)
		definir_resumo("Responsável administrativo não configurado — nenhum aviso enviado.")
		return

	telefone_administrativo = (responsavel_administrativo.get("telefone") or "").strip()
	if not telefone_administrativo:
		logger.warning(
			"Aviso de seguimento do registro provisório não enviado: associado "
			f"{responsavel_administrativo.get('name')} sem telefone cadastrado."
		)
		definir_resumo("Responsável administrativo sem telefone — nenhum aviso enviado.")
		return

	contatos = _buscar_contatos_responsaveis([str(na.name) for na in novos_associados])

	enviados = 0
	for novo_associado in novos_associados:
		try:
			data_ativacao = getdate(novo_associado.data_registro_provisorio_efetivado)
			mensagem = _montar_mensagem_aviso(
				responsavel_administrativo=responsavel_administrativo,
				nome_jovem=novo_associado.nome_completo or str(novo_associado.name),
				data_ativacao=data_ativacao,
				dias_decorridos=date_diff(data_hoje, data_ativacao),
				contato_responsavel=contatos.get(str(novo_associado.name)),
			)

			enviar_texto(telefone_administrativo, mensagem)
			frappe.db.set_value(
				"Novo Associado",
				novo_associado.name,
				"data_aviso_seguimento_provisorio",
				data_hoje,
				update_modified=False,
			)
			enviados += 1
			logger.info(
				f"Aviso enviado sobre {novo_associado.nome_completo or novo_associado.name} "
				f"({date_diff(data_hoje, data_ativacao)} dia(s) desde a ativação)."
			)
		except Exception:
			logger.exception(f"Falha ao avisar sobre o registro provisório {novo_associado.name}.")
			metrica("falhas_no_envio")
			frappe.log_error(
				frappe.get_traceback(),
				f"Aviso seguimento registro provisório: {novo_associado.name}",
			)

	metrica("enviados", enviados, incrementar=False)
	logger.info(
		"Avisos de seguimento do registro provisório processados: "
		f"elegiveis={len(novos_associados)}, enviados={enviados}, espera={dias_limite} dia(s)."
	)
	definir_resumo(
		f"{enviados} de {len(novos_associados)} aviso(s) de seguimento enviado(s) "
		f"(espera de {dias_limite} dia(s))."
	)
