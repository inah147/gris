# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import base64
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

MEIO_PAGAMENTO_CHECKOUT = "Checkout Infinitepay"
MEIO_PAGAMENTO_DINHEIRO = "Dinheiro"
MEIO_PAGAMENTO_CARTAO = "Cartão"
MEIOS_PAGAMENTO_PRESENCIAL = (MEIO_PAGAMENTO_DINHEIRO, MEIO_PAGAMENTO_CARTAO)

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ConviteFesta(Document):
	def before_insert(self):
		self._validar_periodo_de_vendas()

	def validate(self):
		self._aplicar_meio_pagamento()
		self._sanitizar_pagador()
		self._validar_itens()
		self._calcular_valor_total()
		self._aplicar_pagador_aos_convidados()
		self._validar_convidados()
		self._gerar_payloads_qr_code()

	def after_insert(self):
		if self.presencial:
			_atualizar_contadores_opcoes(self.name)
			_criar_lista_entrada(self.name)
			return
		self._criar_cobranca_infinitepay()

	def on_trash(self):
		# Remove Lista Entrada Festa em cascata para manter integridade referencial.
		frappe.db.delete("Lista Entrada Festa", {"convite": self.name})

	@property
	def status_pagamento(self):
		"""Virtual field: lê o status diretamente da Cobranca Infinitepay vinculada.

		Para convites presenciais o pagamento é confirmado no ato da venda
		(dinheiro/cartão físico), sem cobrança Infinitepay.
		"""
		if self.presencial:
			return STATUS_PAGAMENTO_PAGO
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
			frappe.throw(_("A festa selecionada não possui data limite de vendas configurada."))
		if getdate(today()) > getdate(data_limite):
			frappe.throw(_("O período de vendas para esta festa foi encerrado."))

	def _aplicar_meio_pagamento(self):
		"""Garante o invariante meio_pagamento ↔ presencial.

		Convite online: meio_pagamento sempre 'Checkout Infinitepay'.
		Convite presencial: usuário escolhe entre 'Dinheiro' ou 'Cartão'.
		"""
		if not self.presencial:
			self.meio_pagamento = MEIO_PAGAMENTO_CHECKOUT
			return
		if self.meio_pagamento not in MEIOS_PAGAMENTO_PRESENCIAL:
			frappe.throw(_("Meio de pagamento inválido para venda presencial: escolha Dinheiro ou Cartão."))

	def _sanitizar_pagador(self):
		if self.nome_pagador:
			self.nome_pagador = self.nome_pagador.strip()
		if not self.nome_pagador:
			frappe.throw(_("Nome do pagador é obrigatório."))
		if self.email_pagador:
			email = self.email_pagador.strip().lower()
			if not EMAIL_REGEX.match(email):
				frappe.throw(_("E-mail do pagador inválido."))
			self.email_pagador = email
		elif not self.presencial:
			frappe.throw(_("E-mail do pagador é obrigatório."))
		if self.telefone_pagador:
			self.telefone_pagador = re.sub(r"\D", "", self.telefone_pagador)
			if not self.telefone_pagador:
				frappe.throw(_("Telefone do pagador inválido."))
		elif not self.presencial:
			frappe.throw(_("Telefone do pagador é obrigatório."))

	def _validar_itens(self):
		if not self.itens:
			frappe.throw(_("Adicione pelo menos um item ao pedido."))

		aceitar_doacoes = frappe.db.get_value("Festa", self.festa, "aceitar_doacoes")
		tem_convite = False

		for item in self.itens:
			if item.eh_convite:
				tem_convite = True
				if not item.opcao_convite:
					frappe.throw(_("Item de convite precisa ter uma Opção de Convite vinculada."))
				opcao = frappe.db.get_value(
					"Opcao Convite Festa",
					item.opcao_convite,
					["festa", "ativo", "nome_convite", "valor", "valor_consumacao"],
					as_dict=True,
				)
				if not opcao:
					frappe.throw(_("Opção de Convite inválida no item."))
				if opcao.festa != self.festa:
					frappe.throw(
						_("A Opção de Convite '{0}' pertence a outra festa.").format(item.opcao_convite)
					)
				if not opcao.ativo:
					frappe.throw(_("A Opção de Convite '{0}' está inativa.").format(item.opcao_convite))
				item.descricao = opcao.nome_convite
				item.valor = opcao.valor
				item.valor_consumacao = opcao.valor_consumacao
			else:
				if not aceitar_doacoes:
					frappe.throw(_("A festa selecionada não aceita doações junto com os convites."))
				item.opcao_convite = None
				item.valor_consumacao = 0
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
		"""Quando o pagador recebe todos os QR codes, garantimos que existe
		uma linha de Convidado Convite Festa por convite (criando vazias
		quando faltar) — o nome de cada convidado vem do formulário. Cada
		convidado sem e-mail/telefone próprios herda os dados do pagador
		(que já são usados na entrega dos QR codes): isso permite reenviar
		o convite individualmente pela portaria/Desk caso não tenha chegado,
		em vez de deixar o registro do convidado sem contato nenhum.
		"""
		if not self.pagador_recebe_qr_codes:
			return
		total = sum(int(it.quantidade or 0) for it in self.itens or [] if it.eh_convite)
		# Só ajustamos o tamanho quando ainda não houver convidados (cobre o
		# caso degenerado de fluxos legados); a coleta do nome é responsabilidade
		# do front, que envia uma linha por convite.
		if not (self.convidados or []) and total:
			self.set("convidados", [])
			for _ in range(total):
				self.append("convidados", {})
		for convidado in self.convidados or []:
			if not convidado.email:
				convidado.email = self.email_pagador
			if not convidado.telefone:
				convidado.telefone = self.telefone_pagador

	def _validar_convidados(self):
		total_convites = sum(int(it.quantidade or 0) for it in self.itens if it.eh_convite)
		convidados = list(self.convidados or [])

		if len(convidados) != total_convites:
			frappe.throw(
				_(
					"A lista de convidados precisa ter exatamente {0} entradas (1 por convite). Atual: {1}."
				).format(total_convites, len(convidados))
			)

		for convidado in convidados:
			if convidado.nome:
				convidado.nome = convidado.nome.strip()
			if not convidado.nome:
				frappe.throw(_("Todo convidado precisa de nome."))
			if convidado.email:
				email = convidado.email.strip().lower()
				if not EMAIL_REGEX.match(email):
					frappe.throw(_("E-mail do convidado '{0}' é inválido.").format(convidado.nome))
				convidado.email = email
			elif not self.presencial and not self.pagador_recebe_qr_codes:
				frappe.throw(_("Todo convidado precisa de e-mail."))
			if convidado.telefone:
				convidado.telefone = re.sub(r"\D", "", convidado.telefone)

	# ---------- Lifecycle helpers ----------

	def _gerar_payloads_qr_code(self):
		from gris.api.festas.convite_publico import gerar_token

		for convidado in self.convidados or []:
			if not convidado.qr_code_payload:
				convidado.qr_code_payload = uuid.uuid4().hex
			if not convidado.token_link:
				convidado.token_link = gerar_token()
			if not convidado.status_envio:
				convidado.status_envio = STATUS_ENVIO_PENDENTE

	def _criar_cobranca_infinitepay(self):
		from gris.api.festas.convite_confirmado import _build_redirect_url

		cobranca = frappe.get_doc(
			{
				"doctype": "Cobranca Infinitepay",
				"order_nsu": f"CF-{self.name}",
				"customer_name": self.nome_pagador,
				"customer_email": self.email_pagador,
				"customer_phone": self.telefone_pagador,
				"redirect_url": _build_redirect_url(self.name),
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
		# db_set grava no banco e sincroniza o documento em memória de uma vez só.
		self.db_set("cobranca_infinitepay", cobranca.name)


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
		_criar_lista_entrada(convite_name)
		frappe.enqueue(
			"gris.festas.doctype.convite_festa.convite_festa.enviar_qr_codes",
			queue="long",
			enqueue_after_commit=True,
			convite_name=convite_name,
		)
		frappe.enqueue(
			"gris.festas.doctype.convite_festa.convite_festa.enviar_whatsapp_confirmacao_convite",
			queue="short",
			enqueue_after_commit=True,
			convite_name=convite_name,
		)


def _convite_eh_portaria(convite_name: str) -> bool:
	"""True se algum item do convite referencia uma Opcao com portaria=1."""
	row = frappe.db.sql(
		"""
		SELECT 1
		  FROM `tabItem Convite Festa` it
		  JOIN `tabOpcao Convite Festa` op ON op.name = it.opcao_convite
		 WHERE it.parent = %s
		   AND it.parenttype = 'Convite Festa'
		   AND it.eh_convite = 1
		   AND op.portaria = 1
		 LIMIT 1
		""",
		(convite_name,),
	)
	return bool(row)


def _criar_lista_entrada(convite_name: str) -> None:
	"""Cria 1 Lista Entrada Festa por convidado do convite, idempotentemente.

	Chamada pela confirmação de pagamento — webhook InfinitePay, `sincronizar_pagamento`
	ou `marcar_pago_manualmente` — sempre via o `on_update` da Cobranca (doc_event
	`on_cobranca_atualizada`). `ignore_permissions=True` é seguro porque o gatilho vem
	do sistema (não do usuário). Se algum item do convite for de Opcao com portaria=1,
	marca o status como 'Entrou' diretamente (compra na porta, presença implícita).

	Garantia: a `Lista Entrada Festa` é a ÚNICA fonte da portaria e do relatório, então
	materializá-la é uma pós-condição *obrigatória* da confirmação de pagamento. Se a
	entrada de algum convidado não puder ser criada, propagamos o erro para que a
	transição para "Pago" falhe de forma visível — em vez de confirmar o pagamento
	deixando convidados silenciosamente fora da portaria.
	"""
	from frappe.utils import now

	convite = frappe.get_doc("Convite Festa", convite_name)
	if not convite.convidados:
		return

	eh_portaria = _convite_eh_portaria(convite_name)
	falhas: list[str] = []

	for convidado in convite.convidados:
		if not convidado.qr_code_payload:
			continue
		# Idempotência forte: a chave `convidado_row` é única por linha.
		if frappe.db.exists("Lista Entrada Festa", {"convidado_row": convidado.name}):
			continue
		try:
			doc = frappe.new_doc("Lista Entrada Festa")
			doc.festa = convite.festa
			doc.convite = convite.name
			doc.convidado_row = convidado.name
			doc.codigo_convite = convidado.qr_code_payload
			doc.nome_convidado = convidado.nome
			doc.email = convidado.email
			doc.telefone = convidado.telefone
			doc.nome_pagador = convite.nome_pagador
			doc.email_pagador = convite.email_pagador
			doc.telefone_pagador = convite.telefone_pagador
			doc.presencial = 1 if convite.presencial else 0
			if eh_portaria:
				doc.status = "Entrou"
				doc.hora_entrada = now()
				doc.entrada_registrada_por = frappe.session.user or "Administrator"
			else:
				doc.status = "Não entrou"
			doc.insert(ignore_permissions=True)
		except frappe.UniqueValidationError:
			# Concorrência: outro processo criou no meio do caminho. Ignorar.
			continue
		except Exception:
			# A `Lista Entrada Festa` é a única fonte da portaria e do relatório, então
			# uma falha inesperada NÃO pode ser silenciosa. Logamos no logger de arquivo
			# (sobrevive ao rollback do `frappe.throw` abaixo) e acumulamos para abortar
			# a confirmação ao final, depois de tentar todos os convidados.
			frappe.logger("festas").error(
				f"Falha ao criar Lista Entrada Festa "
				f"({convite_name}/{convidado.name}): {frappe.get_traceback()}"
			)
			falhas.append(convidado.name)

	if falhas:
		# Propaga: a transição para "Pago" (webhook, sincronização ou marcação manual)
		# deve falhar de forma visível em vez de confirmar o pagamento deixando
		# convidados fora da portaria/relatório.
		frappe.throw(
			_(
				"Não foi possível registrar a entrada de {0} convidado(s) do pedido {1}. "
				"A confirmação do pagamento foi abortada para não deixar convidados fora "
				"da portaria. Verifique os logs e tente novamente."
			).format(len(falhas), convite_name)
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
		agregado[item.opcao_convite] = agregado.get(item.opcao_convite, 0) + int(item.quantidade or 0)
	for opcao_name, quantidade in agregado.items():
		atual = frappe.db.get_value("Opcao Convite Festa", opcao_name, "quantidade_vendida") or 0
		frappe.db.set_value(
			"Opcao Convite Festa",
			opcao_name,
			"quantidade_vendida",
			int(atual) + quantidade,
			update_modified=False,
		)


# ---------- Envio de QR codes ----------


EMAIL_TEMPLATE_CONVITE = "Convite Festa - QR Code"


def enviar_qr_codes(
	convite_name: str,
	forcar_todos: bool = False,
	convidado_row_name: str | None = None,
) -> None:
	"""Job de background: gera PDFs com QR code e envia por e-mail.

	- Por padrão age só sobre convidados com status_envio em {Pendente, Erro}.
	- Quando `forcar_todos=True`, reenvia também para quem já está `Enviado`.
	- Quando `convidado_row_name` é informado, envia apenas para aquele
	  convidado (e sempre para o e-mail individual dele, mesmo que o convite
	  tenha `pagador_recebe_qr_codes=1`). Usado pela portaria para reenvio
	  pontual.
	- Se pagador_recebe_qr_codes=1 (sem filtro de convidado), envia um único
	  e-mail com todos os anexos para o e-mail do pagador.
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

	if convidado_row_name:
		# Reenvio individual: sempre força (ignora status_envio) e envia para o
		# convidado específico, mesmo em modo "pagador recebe todos".
		pendentes = [c for c in (doc.convidados or []) if c.name == convidado_row_name]
		if not pendentes:
			return
		envio_individual_forcado = True
	elif forcar_todos:
		pendentes = list(doc.convidados or [])
		envio_individual_forcado = False
	else:
		pendentes = [
			c for c in (doc.convidados or []) if c.status_envio in (STATUS_ENVIO_PENDENTE, STATUS_ENVIO_ERRO)
		]
		envio_individual_forcado = False
	if not pendentes:
		return

	festa = frappe.get_doc("Festa", doc.festa)
	contexto_template = _carregar_template(doc, festa)
	falhas: list[tuple[str, str, str]] = []  # (nome, email, descricao_erro)

	if doc.pagador_recebe_qr_codes and not envio_individual_forcado:
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

	# Grava só os campos do e-mail, linha a linha. Salvar o pedido regravaria as linhas
	# com a cópia carregada no início — desfazendo o que o job do WhatsApp, que roda ao
	# mesmo tempo, marcou — e revalidaria os itens contra a Opção atual (que pode estar
	# inativa ou com outro preço).
	for convidado in pendentes:
		frappe.db.set_value(
			"Convidado Convite Festa",
			convidado.name,
			{
				"status_envio": convidado.status_envio,
				"descricao_erro_envio": convidado.descricao_erro_envio,
			},
			update_modified=False,
		)
	# Commit explícito: os e-mails com os QR codes já saíram. As marcações de
	# enviado/erro precisam sobreviver a uma falha no aviso ao coordenador logo
	# abaixo, senão a próxima execução reenvia convites já entregues.
	frappe.db.commit()  # nosemgrep

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
	numero = (frappe.db.get_single_value("Configuracoes WhatsApp", "telefone_contato") or "").strip()
	numero_digits = re.sub(r"\D", "", numero)
	whatsapp_link = f"https://wa.me/{numero_digits}" if numero_digits else ""
	return {
		"doc": doc,
		"festa": festa,
		"whatsapp_link": whatsapp_link,
		"_template_subject": template.subject,
		# response é armazenado com entidades HTML escapadas (&gt;, &lt;);
		# o Jinja precisa do operador original para parsear corretamente.
		"_template_response": (template.response or "").replace("&gt;", ">").replace("&lt;", "<"),
	}


def _enviar_email(*, destinatarios, contexto, attachments):
	# Os templates vêm do DocType Email Template, editável só no Desk por quem tem
	# permissão nele — mesma origem de confiança que o frappe.sendmail padrão usa.
	subject = frappe.render_template(contexto["_template_subject"], contexto)  # nosemgrep
	message = frappe.render_template(contexto["_template_response"], contexto)  # nosemgrep
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


def _mensagem_whatsapp_erro(convite_name: str, festa_nome: str, falhas: list[tuple[str, str, str]]) -> str:
	linhas = "\n".join(f"- {nome} ({email}): {erro[:120]}" for nome, email, erro in falhas)
	return (
		f"[GRIS] Falha ao enviar QR codes do Convite Festa {convite_name} "
		f"({festa_nome}).\nConvidados em erro:\n{linhas}"
	)


# ---------- WhatsApp: confirmação de pagamento ----------


def enviar_whatsapp_confirmacao_convite(convite_name: str) -> None:
	"""Job de background: avisa o pagador pelo WhatsApp e enfileira os convites em PDF.

	- Idempotente: usa `whatsapp_notificado_em` no Convite Festa para não repetir o
	  texto ao pagador quando o webhook é reentrante. O job dos PDFs
	  (`enviar_convites_whatsapp`) é idempotente por convidado.
	- Disparada apenas pelo handler `on_cobranca_atualizada` (sistema), nunca por
	  ações do usuário/visita de página.
	- Os PDFs são enfileirados depois do texto, para o pagador entender o que chega
	  em seguida.
	"""
	from frappe.utils import now

	from gris.api.festas.convite_confirmado import (
		_build_redirect_url,
		_mask_email,
	)
	from gris.utils.whatsapp import enviar_texto

	doc = frappe.get_doc("Convite Festa", convite_name)
	if doc.status_pagamento != STATUS_PAGAMENTO_PAGO:
		return

	festa_nome = frappe.db.get_value("Festa", doc.festa, "nome_festa") or doc.festa
	primeiro_nome_pagador = _primeiro_nome(doc.nome_pagador)
	qtd_convites = sum(int(it.quantidade or 0) for it in doc.itens if it.eh_convite)
	link_assinado = _build_redirect_url(doc.name)
	pagador_recebe_tudo = bool(doc.pagador_recebe_qr_codes)

	# Mensagem para o pagador (uma única vez)
	if not doc.whatsapp_notificado_em and doc.telefone_pagador:
		if pagador_recebe_tudo:
			mensagem_pagador = (
				f"Olá, {primeiro_nome_pagador}!\n\n"
				f"Recebemos o pagamento da sua compra de {qtd_convites} convite(s) para {festa_nome}.\n\n"
				"Em seguida você vai receber aqui no WhatsApp os convites em PDF, um para cada convidado. "
				f"Eles também vão para o e-mail {_mask_email(doc.email_pagador)}.\n\n"
				"Para entrar na festa você precisará apresentar os convites. Não se esqueça de salvá-los em um lugar de fácil acesso para não ter problemas na entrada, combinado?!\n\n"
				f"Aqui está a confirmação de sua compra: {link_assinado}"
				"\n\nNos vemos na festa! 🎉"
			)
		else:
			mensagem_pagador = (
				f"Olá, {primeiro_nome_pagador}!\n\n"
				f"Recebemos o pagamento da sua compra de {qtd_convites} convite(s) para {festa_nome}.\n\n"
				"Cada convidado vai receber o próprio convite em PDF no WhatsApp e no e-mail informados na compra.\n\n"
				"Para entrar na festa cada convidado precisará apresentar os convites, lembre-se de deixar seu convite em um lugar de fácil acesso para não ter problemas na entrada, combinado?!\n\n"
				f"Aqui está a confirmação de sua compra: {link_assinado}"
				"\n\nNos vemos na festa! 🎉"
			)
		try:
			# Síncrono (já estamos num job): numa fila à parte, o texto poderia chegar
			# depois dos PDFs enfileirados logo abaixo.
			enviar_texto(
				doc.telefone_pagador,
				mensagem_pagador,
				enqueue=False,
				contexto={
					"assunto": f"Compra de convites confirmada ({festa_nome})",
					"destinatario_nome": doc.nome_pagador,
				},
			)
		except Exception:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"Falha ao notificar pagador via WhatsApp ({doc.name})",
			)

	frappe.db.set_value(
		"Convite Festa",
		doc.name,
		"whatsapp_notificado_em",
		now(),
		update_modified=False,
	)

	frappe.enqueue(
		"gris.festas.doctype.convite_festa.convite_festa.enviar_convites_whatsapp",
		queue="long",
		enqueue_after_commit=True,
		convite_name=doc.name,
	)


# ---------- WhatsApp: convite em PDF ----------


STATUS_WHATSAPP_ENVIADO = "Enviado"
STATUS_WHATSAPP_ERRO = "Erro"
STATUS_WHATSAPP_SEM_TELEFONE = "Sem telefone"
DESTINATARIO_CONVIDADO = "Convidado de festa"


def enviar_convites_whatsapp(
	convite_name: str,
	convidado_row_name: str | None = None,
	forcar: bool = False,
) -> None:
	"""Job de background: manda o PDF de cada convite pelo WhatsApp do convidado.

	- No modo "pagador recebe todos" os convidados herdam o telefone do pagador
	  (`_aplicar_pagador_aos_convidados`), então é ele quem recebe um PDF por convidado.
	- A legenda leva o link `/convite/<código>`: se o arquivo não abrir, o convidado
	  mostra o QR na tela depois de conferir os 4 últimos dígitos do telefone.
	- Se o PDF não sair (geração ou envio), manda só o texto com o link.
	- Idempotente por convidado (`status_envio_whatsapp`); `forcar` e
	  `convidado_row_name` reenviam mesmo para quem já recebeu.
	- Grava o status direto em cada linha e não salva o Convite Festa: o save
	  reescreveria os valores dos itens a partir da Opção atual e disputaria o
	  documento com o job do e-mail, que roda ao mesmo tempo.
	"""
	from gris.api.festas.convite_publico import url_convite
	from gris.festas.utils import convite_qr
	from gris.utils.whatsapp import enviar_midia, enviar_texto
	from gris.utils.whatsapp_errors import WhatsAppConfigurationError, WhatsAppNumberNotFoundError

	doc = frappe.get_doc("Convite Festa", convite_name)
	if doc.presencial or doc.status_pagamento != STATUS_PAGAMENTO_PAGO:
		return

	if convidado_row_name:
		alvos = [c for c in (doc.convidados or []) if c.name == convidado_row_name]
	elif forcar:
		alvos = list(doc.convidados or [])
	else:
		alvos = [c for c in (doc.convidados or []) if c.status_envio_whatsapp != STATUS_WHATSAPP_ENVIADO]
	if not alvos:
		return

	festa = frappe.db.get_value(
		"Festa",
		doc.festa,
		["name", "nome_festa", "data", "horario_inicio", "horario_termino"],
		as_dict=True,
	)
	tipo_convite = convite_qr._descobrir_tipo_convite(doc)

	for posicao, convidado in enumerate(alvos):
		telefone = re.sub(r"\D", "", convidado.telefone or "")
		if not telefone:
			_marcar_whatsapp(convidado.name, STATUS_WHATSAPP_SEM_TELEFONE)
			continue

		link = url_convite(convidado.name)
		contexto = {
			"assunto": f"Convite da festa {festa.nome_festa or festa.name}",
			"destinatario_tipo": DESTINATARIO_CONVIDADO,
			"destinatario_nome": convidado.nome,
		}
		try:
			pdf = convite_qr.gerar_pdf_convite(doc, convidado)
			enviar_midia(
				telefone,
				"document",
				base64.b64encode(pdf).decode(),
				caption=_mensagem_convite_whatsapp(doc, festa, convidado, tipo_convite, link),
				nome_arquivo=_safe_filename(festa.nome_festa, convidado.nome),
				mimetype="application/pdf",
				enqueue=False,
				contexto=contexto,
			)
			_marcar_whatsapp(convidado.name, STATUS_WHATSAPP_ENVIADO)
		except WhatsAppConfigurationError as exc:
			# Integração desligada ou incompleta: nenhum envio vai passar. Para aqui em vez
			# de gerar os PDFs dos demais à toa.
			for restante in alvos[posicao:]:
				if re.sub(r"\D", "", restante.telefone or ""):
					_marcar_whatsapp(restante.name, STATUS_WHATSAPP_ERRO, erro=str(exc))
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"WhatsApp indisponível para os convites ({doc.name})",
			)
			break
		except WhatsAppNumberNotFoundError as exc:
			# O número não tem WhatsApp: o texto com o link também não chegaria.
			_marcar_whatsapp(convidado.name, STATUS_WHATSAPP_ERRO, erro=str(exc))
		except Exception as exc_pdf:
			try:
				enviar_texto(
					telefone,
					_mensagem_convite_whatsapp(doc, festa, convidado, tipo_convite, link, com_pdf=False),
					enqueue=False,
					contexto=contexto,
				)
				_marcar_whatsapp(
					convidado.name,
					STATUS_WHATSAPP_ENVIADO,
					erro=f"PDF não enviado ({exc_pdf}); enviado só o link.",
				)
			except Exception as exc_texto:
				_marcar_whatsapp(convidado.name, STATUS_WHATSAPP_ERRO, erro=str(exc_texto))
				frappe.log_error(
					message=frappe.get_traceback(),
					title=f"Falha ao enviar convite via WhatsApp ({doc.name}/{convidado.name})",
				)
		# Commit por convidado: as mensagens já saíram. Se o job morrer no meio, a
		# próxima execução não reenvia o que já foi entregue.
		frappe.db.commit()  # nosemgrep


def _mensagem_convite_whatsapp(
	doc, festa, convidado, tipo_convite: str, link: str, *, com_pdf: bool = True
) -> str:
	"""Legenda do PDF (ou, sem ele, o texto com o link).

	Quem recebe tudo é o pagador: a mensagem destaca de quem é cada convite. No modo
	individual ela se apresenta ao convidado, que pode nem saber que ganhou o convite.
	"""
	from gris.api.festas.convite_publico import horario_da_festa
	from gris.www.festas.convite_confirmado import _formatar_data

	festa_nome = festa.nome_festa or festa.name
	quando = " · ".join(parte for parte in (_formatar_data(festa.data), horario_da_festa(festa)) if parte)

	if doc.pagador_recebe_qr_codes:
		linhas = [f"🎟️ *Convite de {convidado.nome}*", festa_nome]
		if quando:
			linhas.append(f"📅 {quando}")
		if tipo_convite:
			linhas.append(tipo_convite)
	else:
		linhas = [
			f"Olá, {_primeiro_nome(convidado.nome)}! 🎉",
			f"Um convite para *{festa_nome}* foi comprado em seu nome.",
			"",
		]
		if quando:
			linhas.append(f"📅 {quando}")
		if tipo_convite:
			linhas.append(f"🎟️ {tipo_convite}")

	linhas.append("")
	if com_pdf:
		linhas += [
			"Apresente o QR code deste PDF na entrada da festa.",
			"",
			"Se o arquivo não abrir, veja o QR code em:",
		]
	else:
		linhas.append("Para ver o QR code e apresentar na entrada da festa, acesse:")
	linhas += [link, "(confirme com os 4 últimos dígitos deste WhatsApp)"]
	return "\n".join(linhas)


def _marcar_whatsapp(convidado_row: str, status: str, *, erro: str | None = None) -> None:
	from frappe.utils import now

	valores = {
		"status_envio_whatsapp": status,
		"descricao_erro_whatsapp": (erro or "")[:500] or None,
	}
	if status == STATUS_WHATSAPP_ENVIADO:
		valores["whatsapp_notificado_em"] = now()
	frappe.db.set_value("Convidado Convite Festa", convidado_row, valores, update_modified=False)


def _primeiro_nome(nome: str | None) -> str:
	if not nome:
		return ""
	return (nome.strip().split(" ", 1)[0] or "").strip()


# ---------- Reenvio (Desk, painel da festa e portaria) ----------


def enfileirar_envio_convite(
	convite_name: str,
	*,
	convidado_row_name: str | None = None,
	forcar_todos: bool = False,
) -> dict:
	"""Enfileira o (re)envio do convite por e-mail e pelo WhatsApp.

	Cada canal só sai se houver para onde mandar: e-mail do convidado (ou o do pagador,
	no reenvio do pedido inteiro em "pagador recebe todos") e telefone do convidado.
	Sem nenhum dos dois, recusa. Quem chama já checou permissão e pagamento.

	Returns: `{"email": bool, "whatsapp": bool}` — os canais acionados.
	"""
	filtros = {"parent": convite_name, "parenttype": "Convite Festa"}
	if convidado_row_name:
		filtros["name"] = convidado_row_name
	convidados = frappe.get_all("Convidado Convite Festa", filters=filtros, fields=["email", "telefone"])

	por_email = any(c.email for c in convidados)
	if not convidado_row_name and not por_email:
		pagador = frappe.db.get_value(
			"Convite Festa", convite_name, ["email_pagador", "pagador_recebe_qr_codes"], as_dict=True
		)
		por_email = bool(pagador and pagador.pagador_recebe_qr_codes and pagador.email_pagador)
	por_whatsapp = any(re.sub(r"\D", "", c.telefone or "") for c in convidados)
	if not (por_email or por_whatsapp):
		frappe.throw(_("Convidado não possui e-mail nem telefone cadastrado."))

	if por_email:
		frappe.enqueue(
			"gris.festas.doctype.convite_festa.convite_festa.enviar_qr_codes",
			queue="long",
			enqueue_after_commit=True,
			convite_name=convite_name,
			convidado_row_name=convidado_row_name,
			forcar_todos=forcar_todos,
		)
	if por_whatsapp:
		frappe.enqueue(
			"gris.festas.doctype.convite_festa.convite_festa.enviar_convites_whatsapp",
			queue="long",
			enqueue_after_commit=True,
			convite_name=convite_name,
			convidado_row_name=convidado_row_name,
			forcar=forcar_todos,
		)
	return {"email": por_email, "whatsapp": por_whatsapp}


def mensagem_de_reenvio(canais: dict) -> str:
	"""Texto do aviso de sucesso, dizendo por onde o convite vai sair."""
	if canais.get("email") and canais.get("whatsapp"):
		return _("Convite reenviado por e-mail e WhatsApp.")
	if canais.get("whatsapp"):
		return _("Convite reenviado pelo WhatsApp.")
	return _("Convite reenviado por e-mail.")


@frappe.whitelist()
def reenviar_qr_codes(convite_name: str, forcar_todos: int | bool = 0) -> dict:
	"""Endpoint para o botão 'Reenviar convites' no Desk (e-mail e WhatsApp).

	`forcar_todos` (default False): quando True, reenvia inclusive para
	convidados que já receberam.
	Validação canônica no backend: permissão e status Pago são checados aqui.
	"""
	doc = frappe.get_doc("Convite Festa", convite_name)
	doc.check_permission("write")
	if doc.status_pagamento != STATUS_PAGAMENTO_PAGO:
		frappe.throw(_("A cobrança ainda não foi paga; envio não está liberado."))

	canais = enfileirar_envio_convite(
		convite_name,
		forcar_todos=bool(int(forcar_todos)) if forcar_todos else False,
	)
	return {"ok": True, **canais, "mensagem": mensagem_de_reenvio(canais)}
