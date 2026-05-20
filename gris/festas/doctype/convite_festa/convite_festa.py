# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import re
import uuid

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, today

STATUS_PAGAMENTO_PAGO = "Pago"
STATUS_ENVIO_PENDENTE = "Pendente"
STATUS_ENVIO_ENVIADO = "Enviado"
STATUS_ENVIO_ERRO = "Erro"

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ConviteFesta(Document):
	def before_insert(self):
		self._validar_periodo_de_vendas()

	def validate(self):
		self._sanitizar_pagador()
		self._validar_itens()
		self._calcular_valor_total()
		self._aplicar_pagador_aos_convidados()
		self._validar_convidados()
		self._gerar_payloads_qr_code()

	def after_insert(self):
		self._criar_cobranca_infinitepay()

	@property
	def status_pagamento(self):
		"""Virtual field: lê o status diretamente da Cobranca Infinitepay vinculada."""
		if not self.cobranca_infinitepay:
			return STATUS_ENVIO_PENDENTE
		return (
			frappe.db.get_value("Cobranca Infinitepay", self.cobranca_infinitepay, "status")
			or STATUS_ENVIO_PENDENTE
		)

	# ---------- Validações ----------

	def _validar_periodo_de_vendas(self):
		data_limite = frappe.db.get_value("Festa", self.festa, "data_limite_vendas")
		if not data_limite:
			frappe.throw(
				_("A festa selecionada não possui data limite de vendas configurada.")
			)
		if getdate(today()) > getdate(data_limite):
			frappe.throw(_("O período de vendas para esta festa foi encerrado."))

	def _sanitizar_pagador(self):
		if self.email_pagador:
			email = self.email_pagador.strip().lower()
			if not EMAIL_REGEX.match(email):
				frappe.throw(_("E-mail do pagador inválido."))
			self.email_pagador = email
		if self.telefone_pagador:
			self.telefone_pagador = re.sub(r"\D", "", self.telefone_pagador)
			if not self.telefone_pagador:
				frappe.throw(_("Telefone do pagador inválido."))
		if self.nome_pagador:
			self.nome_pagador = self.nome_pagador.strip()

	def _validar_itens(self):
		if not self.itens:
			frappe.throw(_("Adicione pelo menos um item ao pedido."))

		aceitar_doacoes = frappe.db.get_value("Festa", self.festa, "aceitar_doacoes")
		tem_convite = False

		for item in self.itens:
			if item.eh_convite:
				tem_convite = True
				if not item.opcao_convite:
					frappe.throw(
						_("Item de convite precisa ter uma Opção de Convite vinculada.")
					)
				opcao = frappe.db.get_value(
					"Opcao Convite Festa",
					item.opcao_convite,
					["festa", "ativo", "nome_convite", "valor"],
					as_dict=True,
				)
				if not opcao:
					frappe.throw(_("Opção de Convite inválida no item."))
				if opcao.festa != self.festa:
					frappe.throw(
						_("A Opção de Convite '{0}' pertence a outra festa.").format(
							item.opcao_convite
						)
					)
				if not opcao.ativo:
					frappe.throw(
						_("A Opção de Convite '{0}' está inativa.").format(item.opcao_convite)
					)
				item.descricao = opcao.nome_convite
				item.valor = opcao.valor
			else:
				if not aceitar_doacoes:
					frappe.throw(
						_(
							"A festa selecionada não aceita doações junto com os convites."
						)
					)
				item.opcao_convite = None
				if not item.descricao:
					frappe.throw(_("Item sem descrição."))
				if flt(item.valor) <= 0:
					frappe.throw(_("Item de doação precisa ter valor maior que zero."))

			if not item.quantidade or item.quantidade <= 0:
				frappe.throw(_("Quantidade dos itens deve ser maior que zero."))

		if not tem_convite:
			frappe.throw(_("O pedido precisa conter ao menos um item de convite."))

	def _calcular_valor_total(self):
		total = sum(flt(it.quantidade) * flt(it.valor) for it in self.itens)
		self.valor_total = total

	def _aplicar_pagador_aos_convidados(self):
		"""Quando o pagador recebe todos os QR codes, a lista de convidados
		é totalmente gerenciada pelo servidor: garante uma linha por convite
		preenchida com os dados do pagador, preservando UUIDs já gerados.
		"""
		if not self.pagador_recebe_qr_codes:
			return
		total = sum(
			int(it.quantidade or 0) for it in self.itens or [] if it.eh_convite
		)
		if len(self.convidados or []) != total:
			self.set("convidados", [])
			for _ in range(total):
				self.append("convidados", {})
		for convidado in self.convidados:
			convidado.nome = self.nome_pagador
			convidado.email = self.email_pagador
			convidado.telefone = self.telefone_pagador

	def _validar_convidados(self):
		total_convites = sum(
			int(it.quantidade or 0) for it in self.itens if it.eh_convite
		)
		convidados = list(self.convidados or [])

		if len(convidados) != total_convites:
			frappe.throw(
				_(
					"A lista de convidados precisa ter exatamente {0} entradas (1 por convite). Atual: {1}."
				).format(total_convites, len(convidados))
			)

		for convidado in convidados:
			if not convidado.nome:
				frappe.throw(_("Todo convidado precisa de nome."))
			if not convidado.email:
				frappe.throw(_("Todo convidado precisa de e-mail."))
			email = convidado.email.strip().lower()
			if not EMAIL_REGEX.match(email):
				frappe.throw(
					_("E-mail do convidado '{0}' é inválido.").format(convidado.nome)
				)
			convidado.email = email
			if convidado.telefone:
				convidado.telefone = re.sub(r"\D", "", convidado.telefone)

	# ---------- Lifecycle helpers ----------

	def _gerar_payloads_qr_code(self):
		for convidado in self.convidados or []:
			if not convidado.qr_code_payload:
				convidado.qr_code_payload = uuid.uuid4().hex
			if not convidado.status_envio:
				convidado.status_envio = STATUS_ENVIO_PENDENTE

	def _criar_cobranca_infinitepay(self):
		cobranca = frappe.get_doc(
			{
				"doctype": "Cobranca Infinitepay",
				"order_nsu": f"CF-{self.name}",
				"customer_name": self.nome_pagador,
				"customer_email": self.email_pagador,
				"customer_phone": self.telefone_pagador,
				"itens": [
					{
						"descricao": it.descricao,
						"quantidade": int(it.quantidade or 0),
						"preco": flt(it.valor),
					}
					for it in self.itens
				],
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value(
			self.doctype, self.name, "cobranca_infinitepay", cobranca.name
		)
		self.cobranca_infinitepay = cobranca.name


# ---------- doc_events handler (Cobranca Infinitepay.on_update) ----------


def on_cobranca_atualizada(doc, method=None):
	"""Reage a Cobranca Infinitepay.on_update via doc_events.

	A própria Cobranca permanece agnóstica; este handler vive no módulo Festas
	e enfileira o envio dos QR codes quando a cobrança transita para Pago.
	"""
	from gris.financeiro.utils.cobranca_eventos import status_mudou_para

	if not status_mudou_para(doc, STATUS_PAGAMENTO_PAGO):
		return

	convites = frappe.get_all(
		"Convite Festa",
		filters={"cobranca_infinitepay": doc.name},
		pluck="name",
	)
	for convite_name in convites:
		_atualizar_contadores_opcoes(convite_name)
		frappe.enqueue(
			"gris.festas.doctype.convite_festa.convite_festa.enviar_qr_codes",
			queue="long",
			enqueue_after_commit=True,
			convite_name=convite_name,
		)


def _atualizar_contadores_opcoes(convite_name: str) -> None:
	"""Soma a quantidade de cada Opcao Convite Festa referenciada pelos itens convite."""
	itens = frappe.get_all(
		"Item Convite Festa",
		filters={"parent": convite_name, "eh_convite": 1},
		fields=["opcao_convite", "quantidade"],
	)
	agregado: dict[str, int] = {}
	for item in itens:
		if not item.opcao_convite:
			continue
		agregado[item.opcao_convite] = agregado.get(item.opcao_convite, 0) + int(
			item.quantidade or 0
		)
	for opcao_name, quantidade in agregado.items():
		atual = (
			frappe.db.get_value("Opcao Convite Festa", opcao_name, "quantidade_vendida")
			or 0
		)
		frappe.db.set_value(
			"Opcao Convite Festa",
			opcao_name,
			"quantidade_vendida",
			int(atual) + quantidade,
			update_modified=False,
		)


# ---------- Envio de QR codes ----------


EMAIL_TEMPLATE_CONVITE = "Convite Festa - QR Code"


def enviar_qr_codes(convite_name: str) -> None:
	"""Job de background: gera PDFs com QR code e envia por e-mail.

	- Só age sobre convidados com status_envio em {Pendente, Erro}.
	- Se pagador_recebe_qr_codes=1, envia um único e-mail com todos os anexos
	  para o e-mail do pagador.
	- Caso contrário, envia 1 e-mail por convidado.
	- Em qualquer falha, marca o convidado afetado como Erro e dispara
	  uma mensagem consolidada via WhatsApp para o coordenador da Portaria.
	"""
	from gris.festas.utils.convite_qr import gerar_pdf_convite
	from gris.festas.utils.portaria import get_coordenador_portaria
	from gris.utils.whatsapp import enviar_texto

	doc = frappe.get_doc("Convite Festa", convite_name)
	if doc.status_pagamento != STATUS_PAGAMENTO_PAGO:
		return

	pendentes = [
		c
		for c in (doc.convidados or [])
		if c.status_envio in (STATUS_ENVIO_PENDENTE, STATUS_ENVIO_ERRO)
	]
	if not pendentes:
		return

	festa = frappe.get_doc("Festa", doc.festa)
	contexto_template = _carregar_template(doc, festa)
	falhas: list[tuple[str, str, str]] = []  # (nome, email, descricao_erro)

	if doc.pagador_recebe_qr_codes:
		anexos = []
		for convidado in pendentes:
			try:
				pdf_bytes = gerar_pdf_convite(doc, convidado)
				anexos.append(
					{
						"fname": _safe_filename(festa.nome_festa, convidado.nome),
						"fcontent": pdf_bytes,
					}
				)
			except Exception as exc:
				_marcar_erro(convidado, str(exc))
				falhas.append((convidado.nome, convidado.email, str(exc)))
		if anexos:
			try:
				_enviar_email(
					destinatarios=[doc.email_pagador],
					contexto={
						**contexto_template,
						"convidados": [c.as_dict() for c in pendentes],
					},
					attachments=anexos,
				)
				for convidado in pendentes:
					if convidado.status_envio != STATUS_ENVIO_ERRO:
						_marcar_enviado(convidado)
			except Exception as exc:
				for convidado in pendentes:
					_marcar_erro(convidado, str(exc))
					falhas.append((convidado.nome, convidado.email, str(exc)))
	else:
		for convidado in pendentes:
			try:
				pdf_bytes = gerar_pdf_convite(doc, convidado)
				_enviar_email(
					destinatarios=[convidado.email],
					contexto={
						**contexto_template,
						"convidados": [convidado.as_dict()],
					},
					attachments=[
						{
							"fname": _safe_filename(festa.nome_festa, convidado.nome),
							"fcontent": pdf_bytes,
						}
					],
				)
				_marcar_enviado(convidado)
			except Exception as exc:
				_marcar_erro(convidado, str(exc))
				falhas.append((convidado.nome, convidado.email, str(exc)))

	doc.save(ignore_permissions=True)
	frappe.db.commit()

	if falhas:
		coordenador = get_coordenador_portaria(doc.festa)
		numero = coordenador.get("telefone")
		if numero:
			mensagem = _mensagem_whatsapp_erro(doc.name, festa.nome_festa, falhas)
			try:
				enviar_texto(numero, mensagem)
			except Exception:
				frappe.log_error(
					message=frappe.get_traceback(),
					title=f"Falha ao notificar Portaria via WhatsApp ({doc.name})",
				)


def _carregar_template(doc, festa) -> dict:
	template = frappe.get_doc("Email Template", EMAIL_TEMPLATE_CONVITE)
	return {
		"doc": doc,
		"festa": festa,
		"_template_subject": template.subject,
		# response é armazenado com entidades HTML escapadas (&gt;, &lt;);
		# o Jinja precisa do operador original para parsear corretamente.
		"_template_response": (template.response or "")
		.replace("&gt;", ">")
		.replace("&lt;", "<"),
	}


def _enviar_email(*, destinatarios, contexto, attachments):
	subject = frappe.render_template(contexto["_template_subject"], contexto)
	message = frappe.render_template(contexto["_template_response"], contexto)
	frappe.sendmail(
		recipients=destinatarios,
		subject=subject,
		message=message,
		attachments=attachments,
		now=True,
	)


def _marcar_enviado(convidado):
	convidado.status_envio = STATUS_ENVIO_ENVIADO
	convidado.descricao_erro_envio = None


def _marcar_erro(convidado, mensagem: str):
	convidado.status_envio = STATUS_ENVIO_ERRO
	convidado.descricao_erro_envio = (mensagem or "Erro desconhecido")[:500]


def _safe_filename(festa_nome: str, convidado_nome: str) -> str:
	parte_festa = re.sub(r"[^A-Za-z0-9_-]+", "_", festa_nome or "festa")[:40]
	parte_conv = re.sub(r"[^A-Za-z0-9_-]+", "_", convidado_nome or "convidado")[:40]
	return f"convite_{parte_festa}_{parte_conv}.pdf"


def _mensagem_whatsapp_erro(
	convite_name: str, festa_nome: str, falhas: list[tuple[str, str, str]]
) -> str:
	linhas = "\n".join(
		f"- {nome} ({email}): {erro[:120]}" for nome, email, erro in falhas
	)
	return (
		f"[GRIS] Falha ao enviar QR codes do Convite Festa {convite_name} "
		f"({festa_nome}).\nConvidados em erro:\n{linhas}"
	)


@frappe.whitelist()
def reenviar_qr_codes(convite_name: str) -> dict:
	"""Endpoint para botão 'Reenviar QR codes' no Desk.

	Validação canônica no backend: permissão e status Pago são checados aqui.
	"""
	doc = frappe.get_doc("Convite Festa", convite_name)
	doc.check_permission("write")
	if doc.status_pagamento != STATUS_PAGAMENTO_PAGO:
		frappe.throw(_("A cobrança ainda não foi paga; envio não está liberado."))

	frappe.enqueue(
		"gris.festas.doctype.convite_festa.convite_festa.enviar_qr_codes",
		queue="long",
		convite_name=convite_name,
	)
	return {"ok": True}
