"""Avisa por e-mail quando o WhatsApp do GRIS cai.

Em 24/10/2026 o WhatsApp desvinculou o aparelho da instância e o GRIS passou 16 dias sem
mandar nada, sem que ninguém soubesse: cada envio só deixava um "Falhou" na ficha do jovem.
O aviso vai por e-mail porque é justamente o WhatsApp que está fora.

Roda a cada 12 horas e só manda quando há problema. Com a conexão aberta, não faz nada.
"""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import frappe
from frappe.utils import escape_html, get_system_timezone, validate_email_address

from gris.utils.job_logger import definir_resumo
from gris.utils.whatsapp import ESTADO_CONECTADO, SETTINGS_DOCTYPE, _get, _get_config, estado_da_conexao
from gris.utils.whatsapp_errors import WhatsAppConfigurationError

PAPEL_PADRAO = "System Manager"
USUARIOS_DE_SISTEMA = {"Administrator", "Guest"}

# Códigos que a Evolution grava em `disconnectionReasonCode` (os do Baileys).
MOTIVOS = {
	401: "o WhatsApp desvinculou o aparelho (alguém o removeu em Aparelhos conectados ou o "
	"WhatsApp o derrubou, por exemplo depois de muitas mensagens seguidas)",
	403: "o número foi bloqueado pelo WhatsApp",
	408: "a conexão expirou",
	428: "a conexão foi fechada",
	440: "a sessão foi aberta em outro lugar",
	500: "a sessão ficou inválida",
	515: "o WhatsApp pediu para reiniciar a conexão",
}


def verificar_conexao_whatsapp() -> None:
	"""Scheduler (8h e 20h): manda o e-mail de alerta se a instância não estiver conectada."""
	if not frappe.db.get_single_value(SETTINGS_DOCTYPE, "habilitar_integracao"):
		definir_resumo("Integração com o WhatsApp desligada: nada a conferir.")
		return

	problema = _problema_na_conexao()
	if problema is None:
		definir_resumo("WhatsApp conectado.")
		return

	destinatarios = destinatarios_do_alerta()
	if not destinatarios:
		frappe.log_error(title="WhatsApp desconectado e ninguém para avisar", message=problema["texto"])
		definir_resumo("WhatsApp desconectado, mas não há e-mail para avisar.")
		return

	frappe.sendmail(
		recipients=destinatarios,
		subject="GRIS: o WhatsApp está desconectado e as mensagens não estão saindo",
		message=_corpo_do_email(problema),
	)
	definir_resumo(f"WhatsApp fora: {problema['texto']} Aviso enviado a {len(destinatarios)} e-mail(s).")


def _problema_na_conexao() -> dict | None:
	"""``None`` quando está tudo certo; senão, o que dizer no e-mail."""
	try:
		config = _get_config()
	except WhatsAppConfigurationError as erro:
		return {"texto": f"A configuração do WhatsApp está incompleta: {erro}", "instancia": None}

	try:
		estado = estado_da_conexao(config)
	except Exception as erro:
		return {
			"texto": f"A Evolution API não respondeu à consulta da conexão: {erro}",
			"instancia": config["nome_instancia"],
		}

	if estado == ESTADO_CONECTADO:
		return None

	problema = {
		"texto": f"A instância {config['nome_instancia']} está com o estado '{estado}'.",
		"instancia": config["nome_instancia"],
	}
	problema.update(_detalhes_da_desconexao(config))
	return problema


def _detalhes_da_desconexao(config: dict) -> dict:
	"""Desde quando e por quê, como a Evolution registrou. Opcional: falhar aqui não cala o aviso."""
	try:
		instancias = _get(
			"/instance/fetchInstances", params={"instanceName": config["nome_instancia"]}, config=config
		)
	except Exception:
		return {}

	instancia = next(
		(i for i in instancias or [] if isinstance(i, dict) and i.get("name") == config["nome_instancia"]),
		None,
	)
	if not instancia:
		return {}

	detalhes: dict = {}
	desde = _data_local(instancia.get("disconnectionAt"))
	if desde:
		detalhes["desde"] = desde
	codigo = instancia.get("disconnectionReasonCode")
	if codigo:
		detalhes["motivo"] = MOTIVOS.get(int(codigo), f"código {codigo} da Evolution")
	return detalhes


def _data_local(valor: str | None) -> str | None:
	if not valor:
		return None
	try:
		momento = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
	except ValueError:
		return None
	return momento.astimezone(ZoneInfo(get_system_timezone())).strftime("%d/%m/%Y às %H:%M")


def destinatarios_do_alerta() -> list[str]:
	"""Os e-mails configurados; sem nenhum, os System Managers ativos."""
	configurados = frappe.db.get_single_value(SETTINGS_DOCTYPE, "emails_alerta_desconexao") or ""
	emails = [
		email.strip()
		for email in re.split(r"[\s,;]+", configurados)
		if email.strip() and validate_email_address(email.strip())
	]
	if emails:
		return list(dict.fromkeys(emails))

	usuarios = frappe.get_all(
		"Has Role",
		filters={"role": PAPEL_PADRAO, "parenttype": "User", "parent": ["not in", list(USUARIOS_DE_SISTEMA)]},
		pluck="parent",
	)
	if not usuarios:
		return []
	return frappe.get_all(
		"User",
		filters={"name": ["in", usuarios], "enabled": 1, "email": ["is", "set"]},
		pluck="email",
		order_by="email asc",
	)


def _corpo_do_email(problema: dict) -> str:
	linhas = [f"<p>{escape_html(problema['texto'])}</p>"]
	if problema.get("desde"):
		linhas.append(f"<p><strong>Desconectado desde:</strong> {escape_html(problema['desde'])}.</p>")
	if problema.get("motivo"):
		linhas.append(f"<p><strong>Motivo:</strong> {escape_html(problema['motivo'])}.</p>")
	linhas.append(
		"<p>Enquanto isso, nenhuma mensagem automática do GRIS sai pelo WhatsApp: recepção de "
		"novos associados, festas, contribuições. Cada tentativa fica registrada como "
		'"Falhou" no Log de Mensagem, e elas <strong>não</strong> são reenviadas depois.</p>'
	)
	if problema.get("instancia"):
		linhas.append(
			"<p><strong>Para reconectar:</strong></p><ol>"
			"<li>Abra o Evolution Manager e entre na instância "
			f"<strong>{escape_html(problema['instancia'])}</strong>.</li>"
			"<li>Peça o QR code da conexão.</li>"
			"<li>No celular do número do grupo, abra o WhatsApp em <em>Aparelhos conectados</em> → "
			"<em>Conectar um aparelho</em> e leia o QR code.</li>"
			"</ol>"
		)
	linhas.append("<p>Este aviso se repete a cada 12 horas enquanto a conexão estiver fora.</p>")
	return "\n".join(linhas)
