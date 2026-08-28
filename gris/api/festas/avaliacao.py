from __future__ import annotations

import base64
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint

from gris.utils.whatsapp import enviar_texto

ALLOWED_ROLES = {"Gestor de festas", "System Manager"}

STATUS_EM_ANDAMENTO = "Em andamento"
RESUMO_EM_PROCESSAMENTO = "Gerando resumo..."

EMAIL_BTN_STYLE = (
	"background-color: #0d4d91; color: #fff; padding: 12px 24px; text-decoration: none; "
	"border-radius: 6px; display: inline-block; font-weight: 600;"
)

QR_PDF_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
	<meta charset="utf-8" />
	<style>
		@page { margin: 1.5cm; }
		body { font-family: 'Helvetica Neue', Arial, sans-serif; color: #1a1a1a; text-align: center; }
		.wrap { max-width: 520px; margin: 0 auto; padding-top: 1cm; }
		.eyebrow { text-transform: uppercase; letter-spacing: 0.08em; font-size: 13px; color: #0d4d91; font-weight: 700; margin: 0 0 6px; }
		.festa { font-size: 30px; font-weight: 800; margin: 0 0 18px; line-height: 1.15; }
		.titulo { font-size: 22px; font-weight: 700; margin: 0 0 8px; }
		.qr { width: 300px; height: 300px; margin: 8px auto 16px; display: block; }
		.texto { font-size: 16px; line-height: 1.6; color: #333; margin: 0 auto; max-width: 440px; }
		.destaque { color: #0d4d91; font-weight: 700; }
		.link { margin-top: 18px; font-size: 12px; color: #777; word-break: break-all; }
	</style>
</head>
<body>
	<div class="wrap">
		<p class="eyebrow">Avaliação da festa</p>
		<h1 class="festa">{{ festa_titulo }}</h1>
		<h2 class="titulo">Conte como foi sua experiência!</h2>
		<img class="qr" src="data:image/png;base64,{{ qr_b64 }}" alt="QR code de avaliação da festa" />
		<p class="texto">Aponte a câmera do seu celular para o <span class="destaque">QR code</span> acima e responda nossa avaliação rapidinho. <strong>Sua opinião é muito importante e nos ajuda muito a melhorar cada vez mais as nossas festas!</strong></p>
		<p class="link">{{ link }}</p>
	</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Acesso e helpers
# ---------------------------------------------------------------------------


def _can_edit() -> bool:
	return bool(set(frappe.get_roles(frappe.session.user)) & ALLOWED_ROLES)


def _ensure_gestor() -> None:
	if not _can_edit():
		frappe.throw(_("Permissão negada."), frappe.PermissionError)


def _get_festa(festa_name: str):
	if not festa_name:
		frappe.throw(_("Festa não informada."))
	if not frappe.db.exists("Festa", festa_name):
		frappe.throw(_("Festa não encontrada."), frappe.DoesNotExistError)
	return frappe.get_doc("Festa", festa_name)


def _pode_enviar_convidados(festa_doc) -> bool:
	"""O envio de avaliação aos convidados só fica disponível a partir do dia seguinte à festa."""
	if not festa_doc.data:
		return False
	return frappe.utils.getdate() > frappe.utils.getdate(festa_doc.data)


def _whatsapp_integracao_ativa() -> bool:
	"""True se a integração de WhatsApp está habilitada e configurada (não lança)."""
	from gris.utils.whatsapp import _get_config
	from gris.utils.whatsapp_errors import WhatsAppConfigurationError

	try:
		_get_config()
		return True
	except WhatsAppConfigurationError:
		return False


def _get_avaliacao_for_festa(festa_name: str):
	name = frappe.db.get_value("Avaliacao Festa", {"festa": festa_name}, "name")
	return frappe.get_doc("Avaliacao Festa", name) if name else None


def ensure_avaliacao_festa(festa_name: str):
	"""Retorna a Avaliacao Festa da festa, criando-a (com token de convidados) se faltar.

	A avaliação existe desde a criação da festa para que o link público e o QR code
	de convidados estejam sempre disponíveis.
	"""
	existing = _get_avaliacao_for_festa(festa_name)
	if existing:
		return existing
	doc = frappe.new_doc("Avaliacao Festa")
	doc.festa = festa_name
	doc.status = STATUS_EM_ANDAMENTO
	doc.insert(ignore_permissions=True)
	return doc


def criar_avaliacao_festa_automatica(doc, method=None):
	"""Hook after_insert da Festa: garante a Avaliacao Festa para coleta de convidados."""
	ensure_avaliacao_festa(doc.name)


def _first_name(nome: str, fallback: str = "") -> str:
	nome = (nome or "").strip()
	return nome.split()[0] if nome else (fallback or "").strip()


def _collect_festa_team(festa_doc) -> list[dict[str, str]]:
	"""Reúne todos os envolvidos na organização da festa, sem duplicar por e-mail.

	Papéis considerados: coordenador geral, coordenadores de área e de barraca e
	membros das equipes de área e de barraca.
	"""
	team: list[dict[str, str]] = []
	seen: set[str] = set()

	def add(nome: str, email: str, telefone: str) -> None:
		nome = (nome or "").strip()
		email = (email or "").strip()
		telefone = (telefone or "").strip()
		key = email.lower()
		if not nome or not email or key in seen:
			return
		team.append({"nome": nome, "email": email, "telefone": telefone})
		seen.add(key)

	add(festa_doc.nome_coord_geral, festa_doc.email_coord_geral, festa_doc.telefone_coord_geral)

	for doctype in ("Area da Festa", "Barraca da Festa"):
		for ref in frappe.get_all(doctype, filters={"festa": festa_doc.name}, fields=["name"]):
			grupo = frappe.get_doc(doctype, ref.name)
			add(grupo.nome_coord, grupo.email_coord, grupo.telefone_coord)
			for membro in grupo.equipe or []:
				add(membro.nome, membro.email, membro.telefone)

	return team


def _telefones_equipe_festa(festa_doc) -> set[str]:
	"""Telefones (normalizados) de todos os envolvidos na organização da festa.

	Coordenador geral, coordenadores e membros das equipes de área e de barraca — usado
	para que a equipe não receba a mensagem de avaliação destinada aos convidados.
	"""
	from gris.utils.whatsapp import _normalize_phone

	telefones: set[str] = set()

	def add(telefone: str) -> None:
		telefone = (telefone or "").strip()
		if telefone:
			telefones.add(_normalize_phone(telefone))

	add(festa_doc.telefone_coord_geral)
	for doctype in ("Area da Festa", "Barraca da Festa"):
		for ref in frappe.get_all(doctype, filters={"festa": festa_doc.name}, fields=["name"]):
			grupo = frappe.get_doc(doctype, ref.name)
			add(grupo.telefone_coord)
			for membro in grupo.equipe or []:
				add(membro.telefone)

	return telefones


def _send_whatsapp(numero: str, mensagem: str, *, contexto: str) -> bool:
	numero = (numero or "").strip()
	if not numero or not mensagem:
		return False
	try:
		enviar_texto(numero, mensagem, enqueue=True)
		return True
	except Exception:
		frappe.log_error(message=frappe.get_traceback(), title=f"Falha ao enviar WhatsApp ({contexto})")
		return False


def _enviar_convite_individual(
	festa_titulo: str, row, telefone: str = "", *, lembrete: bool = False
) -> dict[str, bool]:
	"""Envia (ou reenvia) o convite de avaliação por e-mail e WhatsApp para um membro."""
	email = (row.email or "").strip()
	token = (row.token or "").strip()
	nome = (row.avaliador or "").strip()
	if not email or not token:
		return {"email_sent": False, "whatsapp_sent": False}

	link = f"{frappe.utils.get_url()}/festas/avaliacao_individual?token={token}"
	titulo = "Lembrete de Avaliação" if lembrete else "Avaliação de Festa"
	subject = (
		f"Lembrete: Avaliação da festa {festa_titulo}" if lembrete else f"Avaliação da festa: {festa_titulo}"
	)
	message = f"""
	<div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 24px;">
		<h2 style="color: #0d4d91;">{titulo}</h2>
		<p>Olá, <strong>{frappe.utils.escape_html(nome)}</strong>!</p>
		<p>Você foi convidado(a) a avaliar a festa <strong>{frappe.utils.escape_html(festa_titulo)}</strong>.</p>
		<p>Sua opinião é fundamental para melhorarmos nossas festas. A avaliação leva apenas alguns minutos.</p>
		<p style="margin: 24px 0;">
			<a href="{link}" style="{EMAIL_BTN_STYLE}">Preencher avaliação</a>
		</p>
		<p style="color: #666; font-size: 13px;">
			Este é um link exclusivo para você. Não compartilhe com outras pessoas.<br>
			<a href="{link}" style="color: #0d4d91;">{link}</a>
		</p>
	</div>
	"""

	email_sent = True
	try:
		frappe.sendmail(recipients=[email], subject=subject, message=message, now=True)
	except Exception:
		email_sent = False
		frappe.log_error(
			message=frappe.get_traceback(), title=f"Falha ao enviar email de avaliação para {email}"
		)

	telefone = (telefone or "").strip()
	whatsapp_sent = False
	if telefone:
		primeiro_nome = _first_name(nome, fallback="avaliador")
		if lembrete:
			whatsapp_message = (
				f"Oi, {primeiro_nome}!\n\n"
				f"Este é um lembrete para avaliar a festa *{festa_titulo}*. "
				f"Acesse o link para preencher sua avaliação:\n{link}\n\n"
				"Obrigado por contribuir para melhorar nossas festas!"
			)
		else:
			whatsapp_message = (
				f"Oi, {primeiro_nome}!\n\n"
				f"Chegou o momento de avaliar a festa *{festa_titulo}*! "
				f"Para isso, basta acessar o link abaixo e preencher sua avaliação:\n{link}\n\n"
				"Ahh, este é o mesmo link enviado por e-mail, então não precisa se preocupar "
				"em responder duas vezes, combinado?\n\n"
				"Obrigado por contribuir para melhorar nossas festas!"
			)
		whatsapp_sent = _send_whatsapp(
			telefone, whatsapp_message, contexto=f"avaliacao_festa:{festa_titulo}:{email}"
		)

	return {"email_sent": email_sent, "whatsapp_sent": whatsapp_sent}


# ---------------------------------------------------------------------------
# Serialização
# ---------------------------------------------------------------------------


def _serialize_avaliacao(avaliacao_doc) -> dict[str, Any]:
	individuais = [
		{
			"idx": row.idx,
			"name": row.name,
			"avaliador": row.avaliador,
			"email": row.email,
			"avaliacao_concluida": cint(row.avaliacao_concluida),
			"resultado_festa": row.resultado_festa if cint(row.avaliacao_concluida) else None,
			"satisfacao_colaboracao": row.satisfacao_colaboracao if cint(row.avaliacao_concluida) else None,
			"muito_bom": row.muito_bom if cint(row.avaliacao_concluida) else None,
			"pontos_melhoria": row.pontos_melhoria if cint(row.avaliacao_concluida) else None,
		}
		for row in avaliacao_doc.avaliacoes_individuais or []
	]
	convidados = [
		{
			"idx": row.idx,
			"name": row.name,
			"email": row.email or None,
			"recomendacao": row.recomendacao,
			"mais_gostou": row.mais_gostou,
			"pode_melhorar": row.pode_melhorar,
		}
		for row in avaliacao_doc.avaliacoes_convidados or []
	]
	total = len(individuais)
	concluidas = sum(1 for i in individuais if i["avaliacao_concluida"])

	return {
		"name": avaliacao_doc.name,
		"status": avaliacao_doc.status or STATUS_EM_ANDAMENTO,
		"avaliacao_geral": avaliacao_doc.avaliacao_geral or 0,
		"satisfacao_dos_participantes": avaliacao_doc.satisfacao_dos_participantes or 0,
		"recomendacao_media_convidados": avaliacao_doc.recomendacao_media_convidados or 0,
		"individuais": individuais,
		"total_individuais": total,
		"concluidas_individuais": concluidas,
		"convidados": convidados,
		"total_convidados": len(convidados),
		"o_que_funcionou_bem_na_dinamica_da_equipe": avaliacao_doc.o_que_funcionou_bem_na_dinamica_da_equipe
		or "",
		"o_que_nao_funcionou_na_dinamica_da_equipe": avaliacao_doc.o_que_nao_funcionou_na_dinamica_da_equipe
		or "",
		"pontos_positivos_adicionais": avaliacao_doc.pontos_positivos_adicionais or "",
		"pontos_de_melhoria_adicionais": avaliacao_doc.pontos_de_melhoria_adicionais or "",
		"resumo_avaliacoes_individuais": avaliacao_doc.resumo_avaliacoes_individuais or "",
		"resumo_avaliacao_completa": avaliacao_doc.resumo_avaliacao_completa or "",
		"resumo_avaliacoes_convidados": avaliacao_doc.resumo_avaliacoes_convidados or "",
	}


def _team_phone(festa_doc, email: str) -> str:
	"""Telefone do membro a partir da equipe da festa (para reenvio por WhatsApp)."""
	email = (email or "").strip().lower()
	if not email:
		return ""
	for membro in _collect_festa_team(festa_doc):
		if (membro["email"] or "").strip().lower() == email:
			return membro["telefone"]
	return ""


def _public_link(avaliacao_doc) -> str:
	return f"{frappe.utils.get_url()}/festas/avaliacao_convidado?token={avaliacao_doc.token_convidado}"


def _public_link_qr(avaliacao_doc) -> str:
	"""QR code (data URI PNG) do link público de avaliação dos convidados."""
	from gris.festas.utils.convite_qr import gerar_png

	try:
		png = gerar_png(_public_link(avaliacao_doc))
		return "data:image/png;base64," + base64.b64encode(png).decode()
	except Exception:
		frappe.log_error(message=frappe.get_traceback(), title="Falha ao gerar QR de avaliação de convidados")
		return ""


@frappe.whitelist()
def gerar_pdf_qr_convidados(festa_name: str) -> None:
	"""Gera um PDF imprimível com o nome da festa, o QR code e o convite à avaliação."""
	from frappe.utils.pdf import get_pdf

	from gris.festas.utils.convite_qr import gerar_png

	_ensure_gestor()
	festa_doc = _get_festa(festa_name)
	avaliacao_doc = ensure_avaliacao_festa(festa_name)

	link = _public_link(avaliacao_doc)
	festa_titulo = festa_doc.nome_festa or festa_doc.name
	qr_b64 = base64.b64encode(gerar_png(link)).decode()
	# QR_PDF_TEMPLATE é constante deste módulo; o contexto não é interpretado como template.
	html = frappe.render_template(  # nosemgrep
		QR_PDF_TEMPLATE, {"festa_titulo": festa_titulo, "qr_b64": qr_b64, "link": link}
	)

	frappe.local.response.filename = f"avaliacao-{frappe.scrub(festa_titulo)}.pdf"
	frappe.local.response.filecontent = get_pdf(html)
	frappe.local.response.type = "pdf"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@frappe.whitelist()
def enviar_avaliacao_convidados_whatsapp(festa_name: str) -> dict[str, Any]:
	"""Envia o link de avaliação de convidados por WhatsApp.

	Alcança apenas convidados que compraram ingresso E entraram na festa (registro em
	Lista Entrada Festa com status "Entrou") e que tenham telefone próprio preenchido.
	Os telefones são deduplicados (um envio por número único). Disponível somente a
	partir do dia seguinte à festa.
	"""
	from gris.festas.doctype.lista_entrada_festa.lista_entrada_festa import STATUS_ENTROU
	from gris.utils.whatsapp import _get_config, _normalize_phone
	from gris.utils.whatsapp_errors import WhatsAppConfigurationError

	_ensure_gestor()
	festa_doc = _get_festa(festa_name)
	if not _pode_enviar_convidados(festa_doc):
		frappe.throw(_("O envio só fica disponível a partir do dia seguinte à festa."))

	# Falha cedo se a integração estiver desabilitada/mal configurada — assim o gestor
	# recebe o motivo real em vez de um "envio iniciado" que nunca é entregue (o envio
	# real roda em background e só valida a config dentro do worker).
	try:
		_get_config()
	except WhatsAppConfigurationError as exc:
		frappe.throw(str(exc))

	avaliacao_doc = ensure_avaliacao_festa(festa_name)
	link = _public_link(avaliacao_doc)

	rows = frappe.get_all(
		"Lista Entrada Festa",
		filters={"festa": festa_name, "status": STATUS_ENTROU},
		fields=["telefone"],
	)

	equipe_telefones = _telefones_equipe_festa(festa_doc)
	vistos: set[str] = set()
	telefones: list[str] = []
	for r in rows:
		bruto = (r.telefone or "").strip()
		if not bruto:
			continue
		chave = _normalize_phone(bruto)
		if chave in equipe_telefones or chave in vistos:
			continue
		vistos.add(chave)
		telefones.append(bruto)

	festa_titulo = festa_doc.nome_festa or festa_doc.name
	mensagem = (
		f"Olá! Ficamos muito felizes em ter recebido você na festa *{festa_titulo}*! 🎉\n\n"
		"Gostaríamos muito de saber a sua opinião sobre como foi. "
		"É bem rapidinho, é só acessar o link abaixo:\n"
		f"{link}\n\n"
		"Muito obrigado por contribuir para melhorarmos nossas festas!"
	)

	enviados = 0
	for numero in telefones:
		if _send_whatsapp(numero, mensagem, contexto=f"avaliacao_convidados:{festa_name}"):
			enviados += 1

	return {"ok": True, "enviados": enviados, "total_telefones": len(telefones)}


@frappe.whitelist()
def get_festa_avaliacao_data(festa_name: str) -> dict[str, Any]:
	"""Retorna os dados da aba de avaliação (carregado sob demanda na abertura da aba).

	A coleta de convidados (link público + QR) está disponível desde a criação da
	festa; a avaliação da equipe só começa quando o gestor a inicia.
	"""
	festa_doc = _get_festa(festa_name)
	can_edit = _can_edit()
	can_send_convidados = can_edit and _pode_enviar_convidados(festa_doc)
	whatsapp_integracao_ativa = can_edit and _whatsapp_integracao_ativa()
	avaliacao_doc = _get_avaliacao_for_festa(festa_name)
	if not avaliacao_doc and can_edit:
		avaliacao_doc = ensure_avaliacao_festa(festa_name)

	if not avaliacao_doc:
		return {
			"ok": True,
			"avaliacao": None,
			"team_started": False,
			"can_edit": False,
			"can_start_evaluation": False,
			"can_edit_general": False,
			"can_send_convidados_whatsapp": False,
			"whatsapp_integracao_ativa": False,
			"public_link": "",
			"public_link_qr": "",
		}

	team_started = bool(avaliacao_doc.avaliacoes_individuais)
	return {
		"ok": True,
		"avaliacao": _serialize_avaliacao(avaliacao_doc),
		"team_started": team_started,
		"can_edit": can_edit,
		"can_start_evaluation": can_edit and not team_started,
		"can_edit_general": can_edit and team_started,
		"can_send_convidados_whatsapp": can_send_convidados,
		"whatsapp_integracao_ativa": whatsapp_integracao_ativa,
		"public_link": _public_link(avaliacao_doc),
		"public_link_qr": _public_link_qr(avaliacao_doc),
	}


@frappe.whitelist()
def iniciar_avaliacao_festa(festa_name: str) -> dict[str, Any]:
	"""Inicia a avaliação da equipe: gera os links individuais e os envia por e-mail/WhatsApp.

	Justificativa para ignore_permissions: o gestor já é autenticado e a operação ocorre
	em contexto controlado após validação das pré-condições.
	"""
	_ensure_gestor()
	festa_doc = _get_festa(festa_name)
	avaliacao_doc = ensure_avaliacao_festa(festa_name)

	if avaliacao_doc.avaliacoes_individuais:
		frappe.throw(_("A avaliação da equipe já foi iniciada."))

	team = _collect_festa_team(festa_doc)
	if not team:
		frappe.throw(_("Nenhum envolvido com e-mail encontrado na organização da festa."))

	for membro in team:
		avaliacao_doc.append(
			"avaliacoes_individuais",
			{
				"avaliador": membro["nome"],
				"email": membro["email"],
				"token": frappe.generate_hash(length=32),
			},
		)
	avaliacao_doc.save(ignore_permissions=True)

	festa_titulo = festa_doc.nome_festa or festa_doc.name
	phone_by_email = {m["email"].lower(): m["telefone"] for m in team}
	for row in avaliacao_doc.avaliacoes_individuais:
		_enviar_convite_individual(festa_titulo, row, phone_by_email.get((row.email or "").lower(), ""))

	return {"ok": True, "avaliacao_name": avaliacao_doc.name}


@frappe.whitelist()
def reenviar_email_avaliacao_festa(festa_name: str, avaliador_idx: int) -> dict[str, Any]:
	"""Reenvia o convite (e-mail e WhatsApp) para um membro pendente."""
	_ensure_gestor()
	festa_doc = _get_festa(festa_name)
	avaliacao_doc = _get_avaliacao_for_festa(festa_name)
	if not avaliacao_doc:
		frappe.throw(_("Nenhuma avaliação encontrada para esta festa."))

	target = next((r for r in avaliacao_doc.avaliacoes_individuais if r.idx == cint(avaliador_idx)), None)
	if not target:
		frappe.throw(_("Avaliador não encontrado."))
	if cint(target.avaliacao_concluida):
		frappe.throw(_("Este avaliador já respondeu a avaliação."))

	telefone = _team_phone(festa_doc, target.email)
	resultado = _enviar_convite_individual(
		festa_doc.nome_festa or festa_doc.name, target, telefone, lembrete=True
	)
	return {"ok": True, **resultado}


@frappe.whitelist()
def salvar_avaliacao_geral_festa(festa_name: str, data: str | dict[str, Any]) -> dict[str, Any]:
	"""Salva os campos de texto da avaliação geral da festa."""
	_ensure_gestor()
	_get_festa(festa_name)
	avaliacao_doc = _get_avaliacao_for_festa(festa_name)
	if not avaliacao_doc:
		frappe.throw(_("Nenhuma avaliação encontrada para esta festa."))

	payload = frappe.parse_json(data) if isinstance(data, str) else (data or {})
	for field in (
		"o_que_funcionou_bem_na_dinamica_da_equipe",
		"o_que_nao_funcionou_na_dinamica_da_equipe",
		"pontos_positivos_adicionais",
		"pontos_de_melhoria_adicionais",
	):
		if field in payload:
			avaliacao_doc.set(field, (payload.get(field) or "").strip())

	avaliacao_doc.save(ignore_permissions=True)
	return {"ok": True, "avaliacao": _serialize_avaliacao(avaliacao_doc)}


def _solicitar_resumo(festa_name: str, campo: str, task: str) -> dict[str, Any]:
	_ensure_gestor()
	_get_festa(festa_name)
	avaliacao_doc = _get_avaliacao_for_festa(festa_name)
	if not avaliacao_doc:
		frappe.throw(_("Nenhuma avaliação encontrada para esta festa."))

	if campo == "resumo_avaliacoes_individuais":
		if not any(cint(r.avaliacao_concluida) for r in avaliacao_doc.avaliacoes_individuais):
			frappe.throw(_("Nenhuma avaliação individual foi concluída ainda."))
	elif campo == "resumo_avaliacoes_convidados" and not avaliacao_doc.avaliacoes_convidados:
		frappe.throw(_("Nenhuma avaliação de convidado foi registrada ainda."))

	frappe.db.set_value(
		"Avaliacao Festa", avaliacao_doc.name, campo, RESUMO_EM_PROCESSAMENTO, update_modified=True
	)
	frappe.enqueue(
		method=f"gris.api.festas.avaliacao_tasks.{task}",
		queue="long",
		timeout=600,
		enqueue_after_commit=True,
		avaliacao_name=avaliacao_doc.name,
	)
	return {"ok": True, "pending": True, campo: RESUMO_EM_PROCESSAMENTO}


@frappe.whitelist()
def solicitar_resumo_avaliacoes_individuais_festa(festa_name: str) -> dict[str, Any]:
	return _solicitar_resumo(
		festa_name, "resumo_avaliacoes_individuais", "processar_resumo_individuais_festa"
	)


@frappe.whitelist()
def solicitar_resumo_avaliacao_completa_festa(festa_name: str) -> dict[str, Any]:
	return _solicitar_resumo(festa_name, "resumo_avaliacao_completa", "processar_resumo_completo_festa")


@frappe.whitelist()
def solicitar_resumo_avaliacoes_convidados_festa(festa_name: str) -> dict[str, Any]:
	return _solicitar_resumo(festa_name, "resumo_avaliacoes_convidados", "processar_resumo_convidados_festa")


@frappe.whitelist()
def consultar_resumo_avaliacao_festa(festa_name: str) -> dict[str, Any]:
	"""Consulta o estado dos três resumos da avaliação (polling)."""
	_ensure_gestor()
	avaliacao_doc = _get_avaliacao_for_festa(festa_name)
	if not avaliacao_doc:
		return {
			"ok": True,
			"resumo_avaliacoes_individuais": "",
			"resumo_avaliacao_completa": "",
			"resumo_avaliacoes_convidados": "",
			"pending_individuais": False,
			"pending_completa": False,
			"pending_convidados": False,
		}

	ind = avaliacao_doc.resumo_avaliacoes_individuais or ""
	comp = avaliacao_doc.resumo_avaliacao_completa or ""
	conv = avaliacao_doc.resumo_avaliacoes_convidados or ""
	return {
		"ok": True,
		"resumo_avaliacoes_individuais": ind,
		"resumo_avaliacao_completa": comp,
		"resumo_avaliacoes_convidados": conv,
		"pending_individuais": ind == RESUMO_EM_PROCESSAMENTO,
		"pending_completa": comp == RESUMO_EM_PROCESSAMENTO,
		"pending_convidados": conv == RESUMO_EM_PROCESSAMENTO,
	}
