"""Notificacoes WhatsApp de vencimento de registro de associados."""

from __future__ import annotations

from collections import defaultdict

import frappe
from frappe.utils import date_diff, getdate, today

from gris.utils.gestores import buscar_destinatarios_gestores
from gris.utils.whatsapp import enviar_texto

CAMPO_POR_MARCO = {
	30: "data_notificacao_vencimento_30_dias",
	7: "data_notificacao_vencimento_7_dias",
	0: "data_notificacao_vencimento",
}


def _extrair_primeiro_nome(nome_completo: str | None) -> str:
	nome = (nome_completo or "").strip()
	if not nome:
		return "amigo"
	return nome.split()[0]


def _buscar_links_responsavel(associado_names: list[str]) -> dict[str, list[frappe._dict]]:
	if not associado_names:
		return {}

	links = frappe.get_all(
		"Responsavel Vinculo",
		filters={"beneficiario_associado": ["in", associado_names]},
		fields=["beneficiario_associado", "responsavel", "é_guardiao_legal", "primeiro_responsavel"],
	)

	links_por_associado: dict[str, list[frappe._dict]] = defaultdict(list)
	for link in links:
		associado_name = link.get("beneficiario_associado")
		if associado_name:
			links_por_associado[str(associado_name)].append(link)

	return links_por_associado


def _buscar_contatos_responsavel(
	links_por_associado: dict[str, list[frappe._dict]],
) -> dict[str, frappe._dict]:
	responsavel_names: set[str] = set()
	for links in links_por_associado.values():
		for link in links:
			responsavel_name = link.get("responsavel")
			if responsavel_name:
				responsavel_names.add(str(responsavel_name))

	if not responsavel_names:
		return {}

	responsaveis = frappe.get_all(
		"Responsavel",
		filters={"name": ["in", list(responsavel_names)]},
		fields=["name", "nome_completo", "celular", "telefone_secundario"],
	)
	return {str(row.get("name")): row for row in responsaveis if row.get("name")}


def _resolver_destinatario(
	associado: frappe._dict,
	links_por_associado: dict[str, list[frappe._dict]],
	contatos_responsavel: dict[str, frappe._dict],
) -> frappe._dict | None:
	links = links_por_associado.get(str(associado.name), [])
	if links:
		links_ordenados = sorted(
			links,
			key=lambda lnk: (
				1 if lnk.get("é_guardiao_legal") else 0,
				1 if lnk.get("primeiro_responsavel") else 0,
			),
			reverse=True,
		)

		for link in links_ordenados:
			responsavel_name = str(link.get("responsavel") or "").strip()
			if not responsavel_name:
				continue

			contato = contatos_responsavel.get(responsavel_name)
			if not contato:
				continue

			telefone = (contato.get("celular") or contato.get("telefone_secundario") or "").strip()
			if not telefone:
				continue

			return frappe._dict(
				{
					"telefone": telefone,
					"nome": contato.get("nome_completo") or "Responsavel",
					"tipo": "responsavel",
				}
			)

	telefone_associado = (associado.get("telefone") or "").strip()
	if telefone_associado:
		return frappe._dict(
			{
				"telefone": telefone_associado,
				"nome": associado.get("nome_completo") or "Associado",
				"tipo": "associado",
			}
		)

	return None


def _montar_mensagem_aviso(*, dias_para_vencer: int, associado_nome: str, destinatario: frappe._dict) -> str:
	"""Monta mensagem de aviso manual com suporte a qualquer número de dias (positivo, zero ou negativo)."""
	primeiro_nome_destinatario = _extrair_primeiro_nome(destinatario.get("nome"))
	primeiro_nome_associado = _extrair_primeiro_nome(associado_nome)

	if destinatario.get("tipo") == "associado":
		if dias_para_vencer < 0:
			corpo = f"seu registro escoteiro venceu há {abs(dias_para_vencer)} dia(s)."
		elif dias_para_vencer == 0:
			corpo = "seu registro escoteiro vence hoje."
		else:
			corpo = f"seu registro escoteiro vence em {dias_para_vencer} dia(s)."
	else:
		if dias_para_vencer < 0:
			corpo = f"o registro de {primeiro_nome_associado} venceu há {abs(dias_para_vencer)} dia(s)."
		elif dias_para_vencer == 0:
			corpo = f"o registro de {primeiro_nome_associado} vence hoje."
		else:
			corpo = f"o registro de {primeiro_nome_associado} vence em {dias_para_vencer} dia(s)."

	return (
		f"Oi, {primeiro_nome_destinatario}!\n\n"
		f"Aviso do Gris: {corpo}\n"
		"Por favor, organize a renovação o quanto antes para evitar pendências.\n\n"
		"_Mensagem automática do Gris_"
	)


def _montar_mensagem_gestor_vencimento(
	*, dias_para_vencer: int, associado_nome: str, gestor: frappe._dict
) -> str:
	primeiro_nome_gestor = _extrair_primeiro_nome(gestor.get("nome"))
	primeiro_nome_associado = _extrair_primeiro_nome(associado_nome)

	if dias_para_vencer < 0:
		situacao = f"venceu há {abs(dias_para_vencer)} dia(s)"
	else:
		situacao = "venceu hoje"

	return (
		f"Oi, {primeiro_nome_gestor}!\n\n"
		f"Atenção: o registro escoteiro de {primeiro_nome_associado} {situacao}.\n"
		"Verifique o status e tome as providências necessárias.\n\n"
		"_Mensagem automática do Gris_"
	)


def enviar_lembretes_vencimento_registro_associados() -> None:
	"""Scheduler diario para lembretes de vencimento (30 dias, 7 dias e no vencimento)."""
	logger = frappe.logger("associados_vencimento_notificacoes", allow_site=True)
	data_hoje = getdate(today())

	associados = frappe.get_all(
		"Associado",
		filters={"validade_registro": ["is", "set"]},
		fields=[
			"name",
			"nome_completo",
			"telefone",
			"validade_registro",
			"data_notificacao_vencimento_30_dias",
			"data_notificacao_vencimento_7_dias",
			"data_notificacao_vencimento",
		],
	)

	if not associados:
		logger.info("Lembretes de vencimento nao enviados: nenhum associado com validade_registro.")
		return

	associado_names = [str(row.get("name")) for row in associados if row.get("name")]
	links_por_associado = _buscar_links_responsavel(associado_names)
	contatos_responsavel = _buscar_contatos_responsavel(links_por_associado)

	enviados = 0
	pulados = 0
	gestores_associado = buscar_destinatarios_gestores()

	for associado in associados:
		validade = associado.get("validade_registro")
		if not validade:
			pulados += 1
			continue

		dias_para_vencer = date_diff(getdate(validade), data_hoje)
		if dias_para_vencer not in CAMPO_POR_MARCO:
			pulados += 1
			continue

		campo_notificacao = CAMPO_POR_MARCO[dias_para_vencer]
		if getdate(associado.get(campo_notificacao)) == data_hoje:
			pulados += 1
			continue

		destinatario = _resolver_destinatario(associado, links_por_associado, contatos_responsavel)
		if not destinatario:
			logger.warning(f"Lembrete nao enviado: associado {associado.name} sem telefone elegivel.")
			pulados += 1
			continue

		mensagem = _montar_mensagem_aviso(
			dias_para_vencer=dias_para_vencer,
			associado_nome=associado.get("nome_completo") or str(associado.name),
			destinatario=destinatario,
		)

		try:
			enviar_texto(destinatario.telefone, mensagem)
			frappe.db.set_value(
				"Associado",
				associado.name,
				campo_notificacao,
				data_hoje,
				update_modified=False,
			)
			enviados += 1
			if dias_para_vencer == 0:
				for gestor in gestores_associado:
					try:
						enviar_texto(
							gestor.telefone,
							_montar_mensagem_gestor_vencimento(
								dias_para_vencer=0,
								associado_nome=associado.get("nome_completo") or str(associado.name),
								gestor=gestor,
							),
						)
					except Exception:
						frappe.log_error(
							frappe.get_traceback(),
							f"Aviso gestor vencimento: gestor={gestor.get('nome')}, associado={associado.name}",
						)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"Lembrete vencimento registro associado: {associado.name}",
			)

	logger.info(
		"Lembretes de vencimento processados: "
		f"total={len(associados)}, enviados={enviados}, pulados={pulados}."
	)


@frappe.whitelist()
def notificar_vencimento_manual(associado_name: str) -> dict:
	"""Envia aviso manual de vencimento de registro via WhatsApp.

	Resolve o destinatário com a mesma prioridade do scheduler:
	guardião legal > primeiro responsável > próprio associado.
	Não atualiza campos de idempotência (envio pode ser repetido pelo usuário).
	"""
	if not frappe.has_permission("Associado", "read", associado_name):
		frappe.throw("Sem permissão para acessar este Associado.", frappe.PermissionError)

	associado = frappe.get_doc("Associado", associado_name)

	if not associado.validade_registro:
		frappe.throw("Este associado não possui validade de registro informada.")

	data_hoje = getdate(today())
	dias_para_vencer = date_diff(getdate(associado.validade_registro), data_hoje)

	links_por_associado = _buscar_links_responsavel([str(associado_name)])
	contatos_responsavel = _buscar_contatos_responsavel(links_por_associado)

	associado_dict = frappe._dict(
		{
			"name": associado.name,
			"nome_completo": associado.nome_completo,
			"telefone": associado.telefone,
		}
	)

	destinatario = _resolver_destinatario(associado_dict, links_por_associado, contatos_responsavel)

	if not destinatario:
		frappe.throw("Não foi possível encontrar um número de telefone elegível para o aviso.")

	mensagem = _montar_mensagem_aviso(
		dias_para_vencer=dias_para_vencer,
		associado_nome=associado.nome_completo or str(associado_name),
		destinatario=destinatario,
	)

	enviar_texto(destinatario.telefone, mensagem)

	if dias_para_vencer <= 0:
		for gestor in buscar_destinatarios_gestores():
			try:
				enviar_texto(
					gestor.telefone,
					_montar_mensagem_gestor_vencimento(
						dias_para_vencer=dias_para_vencer,
						associado_nome=associado.nome_completo or str(associado_name),
						gestor=gestor,
					),
				)
			except Exception:
				frappe.log_error(
					frappe.get_traceback(),
					f"Aviso gestor vencimento manual: gestor={gestor.get('nome')}, associado={associado_name}",
				)

	frappe.logger("associados_vencimento_notificacoes", allow_site=True).info(
		f"Aviso manual de vencimento enviado para {destinatario.get('nome')} "
		f"({destinatario.get('tipo')}) — associado={associado_name}, dias={dias_para_vencer}."
	)

	return {
		"destinatario_nome": destinatario.get("nome"),
		"destinatario_tipo": destinatario.get("tipo"),
		"dias_para_vencer": dias_para_vencer,
	}
