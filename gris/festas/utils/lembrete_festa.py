# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Lembrete da festa pelo WhatsApp, disparado pela aba Convites de /festas/festa.

Cada número recebe uma única mensagem:

- quem comprou mais de um convite (somando todos os pedidos com o mesmo telefone) recebe o
  texto do comprador, com os convites que estão no telefone dele anexados e a lista de para
  onde foram os convites dos demais convidados;
- todo outro convidado com telefone recebe o texto do convidado, com o próprio convite.

Ficam de fora os pedidos não pagos, as vendas na porta (presencial ou Opção de portaria) e
quem já entrou na festa.
"""

from __future__ import annotations

import base64
import re
import time
from collections import defaultdict

import frappe
from frappe.utils import add_days, getdate, today

TIPO_CONVIDADO = "convidado"
TIPO_COMPRADOR = "comprador"
STATUS_ENTROU = "Entrou"
# Pausa entre um número e o seguinte: o lembrete vai para a festa inteira de uma vez, e uma
# rajada de centenas de mensagens pela Evolution arrisca o bloqueio do número do grupo.
INTERVALO_ENVIO = 1.5
DIAS_DA_SEMANA = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


# ---------- Destinatários ----------


def _chave_telefone(telefone: str | None) -> str:
	"""Telefone no formato da Evolution: é o que diz se duas linhas são o mesmo WhatsApp."""
	from gris.utils.whatsapp import _normalize_phone

	digitos = re.sub(r"\D", "", telefone or "")
	return _normalize_phone(digitos) if digitos else ""


def _convidados_da_festa(festa_name: str) -> list[frappe._dict]:
	return frappe.db.sql(
		"""
		SELECT cf.name AS convite,
		       cf.nome_pagador,
		       cf.telefone_pagador,
		       ccf.name AS convidado_row,
		       ccf.nome,
		       ccf.email,
		       ccf.telefone,
		       lef.status AS status_entrada
		  FROM `tabConvite Festa` cf
		  JOIN `tabCobranca Infinitepay` ci ON ci.name = cf.cobranca_infinitepay
		  JOIN `tabConvidado Convite Festa` ccf
		    ON ccf.parent = cf.name
		   AND ccf.parenttype = 'Convite Festa'
		   AND ccf.parentfield = 'convidados'
		  LEFT JOIN `tabLista Entrada Festa` lef ON lef.convidado_row = ccf.name
		 WHERE cf.festa = %(festa)s
		   AND IFNULL(cf.presencial, 0) = 0
		   AND ci.status = 'Pago'
		   AND NOT EXISTS (
		       SELECT 1
		         FROM `tabItem Convite Festa` it
		         JOIN `tabOpcao Convite Festa` op ON op.name = it.opcao_convite
		        WHERE it.parent = cf.name
		          AND it.parenttype = 'Convite Festa'
		          AND it.eh_convite = 1
		          AND op.portaria = 1
		   )
		 ORDER BY cf.creation, ccf.idx
		""",
		{"festa": festa_name},
		as_dict=True,
	)


def montar_lembretes(festa_name: str) -> dict:
	"""Decide quem recebe qual mensagem, sem enviar nada.

	Returns:
		`{"destinatarios": [...], "sem_telefone": int}`. Cada destinatário tem `telefone`
		(normalizado), `tipo` (convidado/comprador), `nome`, `anexos` (linhas cujo PDF vai
		junto) e `lista` (convidados citados na mensagem do comprador).
	"""
	linhas = _convidados_da_festa(festa_name)

	compradas: dict[str, list] = defaultdict(list)
	proprias: dict[str, list] = defaultdict(list)
	ordem: dict[str, None] = {}
	sem_telefone = 0
	for linha in linhas:
		linha.chave = _chave_telefone(linha.telefone)
		linha.entrou = linha.status_entrada == STATUS_ENTROU
		chave_pagador = _chave_telefone(linha.telefone_pagador)
		if chave_pagador:
			compradas[chave_pagador].append(linha)
			ordem.setdefault(chave_pagador)
		if linha.chave:
			proprias[linha.chave].append(linha)
			ordem.setdefault(linha.chave)
		elif not linha.entrou:
			sem_telefone += 1

	destinatarios = []
	for chave in ordem:
		minhas = proprias.get(chave, [])
		anexos = [linha for linha in minhas if not linha.entrou]
		if minhas and not anexos:
			# Já está na festa.
			continue
		pedidos = compradas.get(chave, [])
		if len(pedidos) > 1:
			destinatarios.append(
				frappe._dict(
					telefone=chave,
					tipo=TIPO_COMPRADOR,
					nome=pedidos[0].nome_pagador,
					anexos=anexos,
					lista=[linha for linha in pedidos if linha.chave != chave],
				)
			)
		elif anexos:
			destinatarios.append(
				frappe._dict(
					telefone=chave,
					tipo=TIPO_CONVIDADO,
					nome=anexos[0].nome,
					anexos=anexos,
					lista=[],
				)
			)
	return {"destinatarios": destinatarios, "sem_telefone": sem_telefone}


# ---------- Textos ----------


def quando_e_a_festa(festa, hoje=None) -> str:
	"""'é hoje, às 19:00' / 'é amanhã (25/10), às 19:00' / 'é no dia 25/10 (sábado), às 19:00'."""
	from gris.www.festas.convite_confirmado import _formatar_horario

	hoje = getdate(hoje or today())
	data = getdate(festa.data)
	if data == hoje:
		quando = "é hoje"
	elif data == getdate(add_days(hoje, 1)):
		quando = f"é amanhã ({data:%d/%m})"
	else:
		quando = f"é no dia {data:%d/%m} ({DIAS_DA_SEMANA[data.weekday()]})"
	horario = _formatar_horario(festa.horario_inicio)
	if horario:
		quando += f", às {horario}"
	return quando


def mascarar_email(email: str | None) -> str:
	if not email or "@" not in email:
		return ""
	local, _, dominio = email.partition("@")
	return f"{local[:3]}***@{dominio}"


def mascarar_telefone(telefone: str | None) -> str:
	digitos = re.sub(r"\D", "", telefone or "")
	if len(digitos) <= 4:
		return "*" * len(digitos)
	return f"{digitos[:2]}{'*' * (len(digitos) - 4)}{digitos[-2:]}"


def _linha_da_lista(convidado) -> str:
	from gris.festas.doctype.convite_festa.convite_festa import _primeiro_nome

	contatos = [c for c in (mascarar_email(convidado.email), mascarar_telefone(convidado.telefone)) if c]
	linha = f"- {_primeiro_nome(convidado.nome)}"
	if contatos:
		linha += f" - {' | '.join(contatos)}"
	return linha


def texto_do_lembrete(festa, destinatario, hoje=None) -> str:
	from gris.festas.doctype.convite_festa.convite_festa import _primeiro_nome

	festa_nome = festa.nome_festa or festa.name
	lembrete = f"Passando para te lembrar que a festa {festa_nome} {quando_e_a_festa(festa, hoje)}!"
	paragrafos = [f"Oi, {_primeiro_nome(destinatario.nome)}!"]

	varios = len(destinatario.anexos) > 1
	if destinatario.tipo == TIPO_CONVIDADO:
		convite = "aqui estão seus convites" if varios else "aqui está seu convite"
		paragrafos.append(f"{lembrete} Para facilitar, {convite}.")
	else:
		if destinatario.anexos:
			convite = "aqui estão os seus convites" if varios else "aqui está o seu convite"
			lembrete += f" Para te ajudar, {convite}."
		paragrafos.append(lembrete)
		if destinatario.lista:
			paragrafos.append(
				"Além disso, os convites dos seus convidados foram enviados para:\n"
				+ "\n".join(_linha_da_lista(c) for c in destinatario.lista)
			)

	paragrafos.append("Te esperamos lá para se divertir com a gente ❤️")
	return "\n\n".join(paragrafos)


# ---------- Envio ----------


def enviar_lembrete_festa(festa_name: str) -> None:
	"""Job de background: manda o lembrete a todos os destinatários de `montar_lembretes`.

	Não grava nada no Convite Festa nem nas linhas de convidado (o job do e-mail e o do
	WhatsApp gravam nelas por linha); o histórico fica no Log de Mensagem.
	"""
	from gris.utils.whatsapp_errors import WhatsAppConfigurationError

	festa = frappe.db.get_value(
		"Festa", festa_name, ["name", "nome_festa", "data", "horario_inicio"], as_dict=True
	)
	if not festa:
		return

	destinatarios = montar_lembretes(festa_name)["destinatarios"]
	convites: dict = {}
	falhas: list[str] = []
	for posicao, destinatario in enumerate(destinatarios):
		if posicao:
			time.sleep(INTERVALO_ENVIO)
		try:
			_enviar_lembrete(festa, destinatario, convites)
		except WhatsAppConfigurationError:
			# Integração desligada ou incompleta: nenhum envio vai passar.
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"WhatsApp indisponível para o lembrete da festa ({festa_name})",
			)
			return
		except Exception as exc:
			falhas.append(f"- {destinatario.nome} ({mascarar_telefone(destinatario.telefone)}): {exc}")
		# Commit por número: as mensagens já saíram, e o Log de Mensagem de cada uma precisa
		# sobreviver se o job morrer no meio.
		frappe.db.commit()  # nosemgrep

	if falhas:
		frappe.log_error(
			message="\n".join(falhas),
			title=f"Lembrete da festa não chegou a {len(falhas)} número(s) ({festa_name})",
		)


def _enviar_lembrete(festa, destinatario, convites: dict) -> None:
	from gris.api.festas.convite_publico import url_convite
	from gris.festas.doctype.convite_festa.convite_festa import DESTINATARIO_CONVIDADO, _safe_filename
	from gris.festas.utils import convite_qr
	from gris.utils.whatsapp import enviar_midia, enviar_texto
	from gris.utils.whatsapp_errors import WhatsAppConfigurationError, WhatsAppNumberNotFoundError

	festa_nome = festa.nome_festa or festa.name
	texto = texto_do_lembrete(festa, destinatario)
	contexto = {
		"assunto": f"Lembrete da festa {festa_nome}",
		"destinatario_tipo": DESTINATARIO_CONVIDADO,
		"destinatario_nome": destinatario.nome,
	}
	if not destinatario.anexos:
		enviar_texto(destinatario.telefone, texto, enqueue=False, contexto=contexto)
		return

	for indice, linha in enumerate(destinatario.anexos):
		legenda = texto if indice == 0 else f"🎟️ Convite de {linha.nome}"
		if linha.convite not in convites:
			convites[linha.convite] = frappe.get_doc("Convite Festa", linha.convite)
		convite = convites[linha.convite]
		convidado = next(c for c in convite.convidados if c.name == linha.convidado_row)
		try:
			pdf = convite_qr.gerar_pdf_convite(convite, convidado)
			enviar_midia(
				destinatario.telefone,
				"document",
				base64.b64encode(pdf).decode(),
				caption=legenda,
				nome_arquivo=_safe_filename(festa_nome, linha.nome),
				mimetype="application/pdf",
				enqueue=False,
				contexto=contexto,
			)
		except (WhatsAppConfigurationError, WhatsAppNumberNotFoundError):
			raise
		except Exception:
			# Sem o PDF, vai o texto com o link do convite (como no envio do convite).
			enviar_texto(
				destinatario.telefone,
				f"{legenda}\n\nVeja o QR code do convite de {linha.nome} em:\n"
				f"{url_convite(linha.convidado_row)}\n"
				"(confirme com os 4 últimos dígitos deste WhatsApp)",
				enqueue=False,
				contexto=contexto,
			)
