# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Cobrança da contribuição mensal por link de pagamento InfinitePay.

O ciclo completo mora aqui:

1. Uma `Cobranca Infinitepay` com `finalidade = "Contribuição Mensal"` é emitida
   para as competências em aberto de um contribuinte — pelo gestor, na tela do
   contribuinte, ou pelo job mensal de `cobranca_contribuicao_automatica`. A
   apuração de `gris.api.financeiro.contribuicoes` diz quais meses estão em
   aberto e quanto falta em cada um. O `after_insert` da cobrança busca o link na
   InfinitePay, e a cobrança pendente anterior do mesmo associado passa a
   "Substituída".
2. O link vai para o responsável pelo WhatsApp, no telefone de cobrança do
   associado.
3. Quando a InfinitePay confirma o pagamento — pelo webhook ou pela sincronização
   manual — `on_cobranca_atualizada` lança no extrato o crédito que quita as
   competências cobradas, mês a mês.
4. Quando o fechamento mensal da InfinitePay é importado, a mesma venda chega de
   novo como transação de Sistema. `conciliar_baixas_de_cobranca` casa as duas e
   deixa só a baixa contando nos totais.

A baixa é um lançamento em `Transacao Extrato Geral` porque é dali que a apuração
lê: marcar o pagamento em qualquer outro lugar não mudaria a situação do mês na
tela. O lançamento nasce com a data real do pagamento em `data_transacao` (o caixa
não é distorcido) e declara em `competencias_contribuicao` quanto quitou de cada
mês — o que também marca como pagos os `Pagamento Contribuicao Mensal`.
"""

from __future__ import annotations

import datetime
import re

import frappe
from frappe import _
from frappe.utils import add_days, getdate, now_datetime

from gris.api.financeiro.contribuicoes import (
	CATEGORIA_CONTRIBUICAO,
	MESES_MAXIMO,
	ROLE_GESTOR,
	STATUS_ATRASADO,
	apurar_associados,
	chave_mes,
	competencias_pendentes,
	normalizar_meses,
)

# Valor de `finalidade` que liga a cobrança ao fluxo da contribuição mensal.
FINALIDADE_CONTRIBUICAO = "Contribuição Mensal"

# Situações da `Cobranca Infinitepay` que este fluxo lê ou escreve.
STATUS_COBRANCA_PENDENTE = "Pendente"
STATUS_COBRANCA_PAGA = "Pago"
STATUS_COBRANCA_SUBSTITUIDA = "Substituída"

# Quem emitiu a cobrança.
ORIGEM_MANUAL = "Manual"
ORIGEM_AUTOMATICA = "Automática"

# Método registrado no extrato quando a InfinitePay não informa como foi pago.
METODO_LANCAMENTO = "Cartão"

# `capture_method` da InfinitePay → `metodo` do extrato.
METODO_POR_CAPTURA = {"pix": "Pix", "credit_card": "Cartão"}

# Carteira e instituição onde o dinheiro do link cai. A baixa só as preenche se
# existirem no site: o saldo da carteira é recalculado a cada lançamento.
CARTEIRA_INFINITEPAY = "Infinitepay"
INSTITUICAO_INFINITEPAY = "Infinitepay"

# Prefixo do `id` (que dá nome ao documento) da transação de baixa. Deixa o
# lançamento rastreável até a cobrança que o originou e, como `id` é único,
# funciona como trava contra baixa duplicada mesmo se o vínculo se perder.
PREFIXO_ID_TRANSACAO = "COBIP-"

# Quantos meses para trás a tela oferece para cobrar.
MESES_COBRANCA = 12

# Conciliação com o fechamento importado. A importação grava o valor líquido da
# venda, então o cartão chega menor que a baixa pela taxa da InfinitePay; o PIX
# chega igual. A janela de dias cobre a diferença entre a data do webhook e a
# data da venda no relatório.
TAXA_MAXIMA_CONCILIACAO = 0.06
JANELA_DIAS_CONCILIACAO = 3
# Baixas mais antigas que isso já passaram por um fechamento; não vale varrê-las.
DIAS_BUSCA_CONCILIACAO = 120

PADRAO_COMPETENCIA = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _assert_gestor() -> None:
	if ROLE_GESTOR not in frappe.get_roles():
		frappe.throw(
			_("Requer acesso Gestor Contribuição Mensal para cobrar contribuições."),
			frappe.PermissionError,
		)


def _normalizar_competencias(competencias) -> list[str]:
	"""Aceita lista ou CSV e devolve competências AAAA-MM válidas, sem repetição."""
	if isinstance(competencias, str):
		bruto = competencias.split(",")
	elif isinstance(competencias, list | tuple):
		bruto = list(competencias)
	else:
		bruto = []

	vistas: list[str] = []
	for item in bruto:
		ym = str(item or "").strip()
		if not ym:
			continue
		if not PADRAO_COMPETENCIA.match(ym):
			frappe.throw(_("Competência inválida: {0}. Use o formato AAAA-MM.").format(ym))
		if ym not in vistas:
			vistas.append(ym)
	return sorted(vistas)


def _primeiro_dia(ym: str) -> datetime.date:
	ano, mes = ym.split("-")
	return datetime.date(int(ano), int(mes), 1)


def _rotulo(ym: str) -> str:
	return _primeiro_dia(ym).strftime("%m/%Y")


def _meses_ate(ym: str, hoje: datetime.date) -> int:
	"""Janela de apuração que ainda enxerga a competência `ym`."""
	inicio = _primeiro_dia(ym)
	meses = (hoje.year - inicio.year) * 12 + (hoje.month - inicio.month) + 1
	return normalizar_meses(max(1, min(meses, MESES_MAXIMO)))


def get_situacao_para_cobranca(associado: str, meses=MESES_COBRANCA) -> dict:
	"""Apuração de um contribuinte com as competências que podem ser cobradas."""
	apuracoes = apurar_associados([associado], normalizar_meses(meses))
	if not apuracoes:
		frappe.throw(
			_("Associado não encontrado entre os contribuintes da contribuição mensal."),
			frappe.DoesNotExistError,
		)
	apuracao = apuracoes[0]
	return {
		"associado": apuracao,
		"pendentes": competencias_pendentes(apuracao),
		"cobrancas": listar_cobrancas(associado),
	}


def listar_cobrancas(associado: str, limite: int = 10) -> list[dict]:
	"""Cobranças de contribuição já emitidas para o associado, da mais recente."""
	return frappe.get_all(
		"Cobranca Infinitepay",
		filters={"associado": associado, "finalidade": FINALIDADE_CONTRIBUICAO},
		fields=[
			"name",
			"status",
			"link_pagamento",
			"competencias",
			"transacao_extrato",
			"origem",
			"ultimo_envio_whatsapp",
			"resultado_ultimo_envio",
			"creation",
		],
		order_by="creation desc",
		limit_page_length=limite,
	)


def _dados_do_associado(associado: str) -> dict:
	dados = frappe.db.get_value(
		"Associado",
		associado,
		["name", "nome_completo", "email_cobranca", "telefone_cobranca", "email", "telefone"],
		as_dict=True,
	)
	if not dados:
		frappe.throw(_("Associado {0} não encontrado.").format(associado), frappe.DoesNotExistError)
	return dados


def montar_cobranca(associado: str, competencias, meses=MESES_COBRANCA) -> dict:
	"""Cria, a pedido do gestor, a `Cobranca Infinitepay` das competências e devolve o link."""
	_assert_gestor()
	return emitir_cobranca(associado, competencias, meses, origem=ORIGEM_MANUAL)


def emitir_cobranca(
	associado: str,
	competencias,
	meses=MESES_COBRANCA,
	*,
	origem: str = ORIGEM_MANUAL,
	pendentes: list[dict] | None = None,
	hoje: datetime.date | None = None,
) -> dict:
	"""Cria a `Cobranca Infinitepay` das competências pedidas e devolve o link.

	Não checa papel: quem chama é o endpoint do gestor (`montar_cobranca`) ou o
	job da cobrança automática, que roda sem sessão de usuário.

	As competências são conferidas contra a apuração no momento da emissão: só
	entra na cobrança o mês que continua em aberto e pelo valor que ainda falta.
	Cobrar um mês já quitado só geraria crédito e confundiria quem paga. O job
	passa `pendentes` já apurados em lote para não apurar um associado por vez.

	A cobrança pendente anterior do associado vira "Substituída" depois que a nova
	ganha link: o responsável fica com um só link valendo, e o portal mostra só
	esse. Se o link antigo for pago mesmo assim, o webhook aceita o pagamento.
	"""
	hoje = hoje or getdate()
	pedidas = _normalizar_competencias(competencias)
	if not pedidas:
		frappe.throw(_("Selecione ao menos uma competência para cobrar."))

	if pendentes is None:
		pendentes = get_situacao_para_cobranca(associado, meses)["pendentes"]
	pendentes_por_ym = {p["ym"]: p for p in pendentes}

	fora = [ym for ym in pedidas if ym not in pendentes_por_ym]
	if fora:
		frappe.throw(
			_("Estas competências não estão em aberto para o associado: {0}.").format(
				", ".join(_rotulo(ym) for ym in fora)
			)
		)

	dados = _dados_do_associado(associado)
	nome = dados.get("nome_completo") or associado

	itens = [
		{
			"descricao": _("Contribuição mensal {0} — {1}").format(_rotulo(ym), nome),
			"quantidade": 1,
			"preco": pendentes_por_ym[ym]["valor"],
			"competencia": _primeiro_dia(ym),
			"em_atraso": 1 if pendentes_por_ym[ym].get("status") == STATUS_ATRASADO else 0,
		}
		for ym in pedidas
	]

	anteriores = frappe.get_all(
		"Cobranca Infinitepay",
		filters={
			"associado": associado,
			"finalidade": FINALIDADE_CONTRIBUICAO,
			"status": STATUS_COBRANCA_PENDENTE,
		},
		pluck="name",
	)

	cobranca = frappe.get_doc(
		{
			"doctype": "Cobranca Infinitepay",
			"order_nsu": _proximo_order_nsu(associado),
			"status": STATUS_COBRANCA_PENDENTE,
			"finalidade": FINALIDADE_CONTRIBUICAO,
			"associado": associado,
			"competencias": ",".join(pedidas),
			"origem": origem,
			"mes_emissao": hoje.replace(day=1),
			"customer_name": nome,
			"customer_email": dados.get("email_cobranca") or dados.get("email") or "",
			"customer_phone": dados.get("telefone_cobranca") or dados.get("telefone") or "",
			"itens": itens,
		}
	)
	# O gestor já passou por `_assert_gestor`; o job roda como Administrator. A
	# permissão de criação do DocType não acrescenta nada aos dois caminhos.
	cobranca.insert(ignore_permissions=True)
	cobranca.reload()

	if cobranca.link_pagamento:
		for nome_anterior in anteriores:
			frappe.db.set_value("Cobranca Infinitepay", nome_anterior, "status", STATUS_COBRANCA_SUBSTITUIDA)

	return {
		"name": cobranca.name,
		"link_pagamento": cobranca.link_pagamento or "",
		"competencias": pedidas,
		"valor_total": round(sum(item["preco"] for item in itens), 2),
		"telefone": cobranca.customer_phone or "",
		"substituidas": anteriores if cobranca.link_pagamento else [],
	}


def _proximo_order_nsu(associado: str) -> str:
	"""Identificador único da cobrança, legível no painel da InfinitePay."""
	carimbo = now_datetime().strftime("%Y%m%d%H%M%S")
	return f"CM-{associado}-{carimbo}"


def montar_mensagem(cobranca: dict, nome_associado: str) -> str:
	"""Texto enviado ao responsável, com as competências e o link."""
	rotulos = ", ".join(_rotulo(ym) for ym in cobranca["competencias"])
	valor = frappe.utils.fmt_money(cobranca["valor_total"], currency="BRL")
	plural = "às contribuições" if len(cobranca["competencias"]) > 1 else "à contribuição"
	return (
		f"Olá! Segue o link para pagamento referente {plural} de {nome_associado}.\n\n"
		f"Competência: {rotulos}\n"
		f"Valor: {valor}\n\n"
		f"{cobranca['link_pagamento']}\n\n"
		"O pagamento é confirmado automaticamente e a contribuição fica quitada no sistema. "
		"Se já tiver pago, pode ignorar esta mensagem."
	)


def montar_mensagem_lembrete(cobranca: dict, nome_associado: str) -> str:
	"""Lembrete para quem ainda não pagou o link do mês."""
	rotulos = ", ".join(_rotulo(ym) for ym in cobranca["competencias"])
	valor = frappe.utils.fmt_money(cobranca["valor_total"], currency="BRL")
	return (
		f"Olá! Lembrete: a contribuição mensal de {nome_associado} ainda está em aberto.\n\n"
		f"Competência: {rotulos}\n"
		f"Valor: {valor}\n\n"
		f"{cobranca['link_pagamento']}\n\n"
		"O pagamento pelo link é confirmado automaticamente. "
		"Se já tiver pago, pode ignorar esta mensagem."
	)


@frappe.whitelist()
def get_cobranca_do_associado(associado: str, meses: str | int = MESES_COBRANCA):
	"""Competências em aberto e cobranças já emitidas, para montar a tela."""
	_assert_gestor()
	if not associado:
		frappe.throw(_("Parâmetro 'associado' é obrigatório."), frappe.ValidationError)
	return {"success": True, **get_situacao_para_cobranca(associado, meses)}


@frappe.whitelist()
def gerar_cobranca(
	associado: str,
	competencias: str | list | None = None,
	enviar_whatsapp: str | int | bool = 1,
	meses: str | int = MESES_COBRANCA,
):
	"""Gera o link de pagamento das competências e, se pedido, manda no WhatsApp.

	O envio é a última etapa de propósito: se o WhatsApp falhar, a cobrança e o
	link continuam válidos e a tela mostra o link para envio manual.
	"""
	_assert_gestor()
	if not associado:
		frappe.throw(_("Parâmetro 'associado' é obrigatório."), frappe.ValidationError)

	cobranca = montar_cobranca(associado, competencias, meses)

	if not cobranca["link_pagamento"]:
		frappe.throw(
			_("A InfinitePay não devolveu o link de pagamento. Verifique a cobrança {0}.").format(
				cobranca["name"]
			)
		)

	resultado = {"success": True, "cobranca": cobranca, "whatsapp": None}
	if frappe.utils.cint(enviar_whatsapp):
		resultado["whatsapp"] = enviar_cobranca(cobranca["name"])
	return resultado


@frappe.whitelist()
def enviar_cobranca_whatsapp(name: str):
	"""Reenvia pelo WhatsApp o link de uma cobrança já emitida."""
	_assert_gestor()
	return {"success": True, "whatsapp": enviar_cobranca(name)}


def _dados_da_cobranca(cobranca) -> dict:
	"""Resumo da cobrança no formato que as mensagens usam."""
	return {
		"name": cobranca.name,
		"link_pagamento": cobranca.link_pagamento,
		"competencias": _normalizar_competencias(cobranca.competencias),
		"valor_total": round(
			sum(float(item.quantidade or 0) * float(item.preco or 0) for item in cobranca.itens), 2
		),
		"telefone": cobranca.customer_phone or "",
	}


def enviar_cobranca(name: str, *, lembrete: bool = False) -> dict:
	"""Manda o link de uma cobrança pelo WhatsApp e registra o resultado na cobrança.

	Serve ao gestor (envio e reenvio) e ao job (envio do mês e lembretes). O
	carimbo `ultimo_envio_whatsapp` só é gravado quando a mensagem sai — é por ele
	que o job sabe quem ainda precisa receber.
	"""
	cobranca = frappe.get_doc("Cobranca Infinitepay", name)
	if cobranca.finalidade != FINALIDADE_CONTRIBUICAO:
		frappe.throw(_("A cobrança {0} não é de contribuição mensal.").format(name))
	if not cobranca.link_pagamento:
		frappe.throw(_("A cobrança {0} ainda não tem link de pagamento.").format(name))

	dados = _dados_da_cobranca(cobranca)
	nome = frappe.db.get_value("Associado", cobranca.associado, "nome_completo") or cobranca.associado
	mensagem = montar_mensagem_lembrete(dados, nome) if lembrete else montar_mensagem(dados, nome)
	resultado = _enviar_whatsapp(dados, cobranca.associado, mensagem)

	if resultado["enviado"]:
		valores: dict = {
			"ultimo_envio_whatsapp": now_datetime(),
			"resultado_ultimo_envio": _("Enviado para {0}.").format(resultado.get("telefone")),
		}
		if lembrete:
			valores["lembretes_enviados"] = int(cobranca.lembretes_enviados or 0) + 1
			valores["resultado_ultimo_envio"] = _("Lembrete enviado para {0}.").format(
				resultado.get("telefone")
			)
	else:
		valores = {"resultado_ultimo_envio": _("Não enviado: {0}").format(resultado.get("motivo") or "")}
	frappe.db.set_value("Cobranca Infinitepay", name, valores)
	return resultado


def _enviar_whatsapp(cobranca: dict, associado: str, mensagem: str | None = None) -> dict:
	"""Envia o link e devolve o que aconteceu, sem derrubar a geração da cobrança.

	O envio é síncrono (`enqueue=False`) porque quem clicou no botão precisa saber
	na hora se a mensagem saiu, e o job precisa registrar na cobrança quem não
	recebeu — enfileirar engoliria a falha num job que ninguém acompanha. A falha
	volta como resultado, não como exceção: a cobrança e o link continuam válidos e
	a tela oferece o envio manual.
	"""
	from gris.utils.whatsapp import enviar_texto
	from gris.utils.whatsapp_errors import (
		WhatsAppConfigurationError,
		WhatsAppNumberNotFoundError,
		WhatsAppRequestError,
	)

	dados = _dados_do_associado(associado)
	nome = dados.get("nome_completo") or associado
	telefone = cobranca.get("telefone") or dados.get("telefone_cobranca") or dados.get("telefone")

	if not telefone:
		return {
			"enviado": False,
			"motivo": _("O associado não tem telefone de cobrança cadastrado."),
		}

	try:
		enviar_texto(
			telefone,
			mensagem or montar_mensagem(cobranca, nome),
			enqueue=False,
			contexto={
				"assunto": "Cobrança de contribuição mensal",
				"destinatario_tipo": "Responsável",
				"destinatario_nome": nome,
			},
		)
	except (
		WhatsAppConfigurationError,
		WhatsAppNumberNotFoundError,
		WhatsAppRequestError,
	) as erro:
		frappe.log_error(
			title="Falha ao enviar cobrança de contribuição no WhatsApp",
			message=f"cobranca={cobranca.get('name')} associado={associado}: {erro}",
		)
		return {"enviado": False, "motivo": str(erro)}

	return {"enviado": True, "telefone": telefone}


def on_cobranca_atualizada(doc, method=None):
	"""Dá baixa na contribuição quando a InfinitePay confirma o pagamento.

	Registrado em `doc_events` do `on_update` de `Cobranca Infinitepay`, o mesmo
	gancho por onde o módulo de festas escuta. Roda tanto no webhook quanto na
	sincronização manual, e é idempotente: a cobrança que já tem
	`transacao_extrato` não lança de novo.
	"""
	if doc.finalidade != FINALIDADE_CONTRIBUICAO or doc.status != STATUS_COBRANCA_PAGA:
		return
	if doc.transacao_extrato:
		return
	if not doc.associado:
		frappe.log_error(
			title="Cobrança de contribuição paga sem associado",
			message=f"cobranca={doc.name}: baixa não lançada porque o associado está vazio.",
		)
		return

	lancar_baixa(doc)


def _valor_dos_itens(doc) -> float:
	return round(sum(float(i.quantidade or 0) * float(i.preco or 0) for i in doc.itens), 2)


def _competencias_da_baixa(doc, competencias: list[str], hoje: datetime.date) -> list[dict]:
	"""Quanto a baixa quita de cada mês, ou `[]` quando não dá para detalhar.

	Cada item da cobrança carrega o mês e o valor que quita. Cobranças emitidas
	antes de o item guardar o mês são pareadas pela ordem, que é a mesma das
	competências.

	Sem detalhar é o caminho seguro quando algum mês cobrado já não está em aberto
	— o link antigo pago depois de o mês ter sido quitado por outro pagamento.
	Declarar o mês de novo tomaria o `Pagamento Contribuicao Mensal` de quem
	realmente o quitou; sem detalhamento, o crédito entra pela competência mais
	antiga e a apuração o trata como pagamento adiantado.
	"""
	itens = list(doc.itens)
	por_ym: dict[str, dict] = {}
	if all(item.competencia for item in itens):
		for item in itens:
			ym = chave_mes(getdate(item.competencia))
			por_ym[ym] = {
				"ym": ym,
				"valor": round(float(item.quantidade or 0) * float(item.preco or 0), 2),
				"em_atraso": bool(item.em_atraso),
			}
	elif len(itens) == len(competencias):
		for ym, item in zip(competencias, itens, strict=True):
			por_ym[ym] = {
				"ym": ym,
				"valor": round(float(item.quantidade or 0) * float(item.preco or 0), 2),
				"em_atraso": False,
			}

	if sorted(por_ym) != competencias:
		return []

	apuracoes = apurar_associados([doc.associado], _meses_ate(competencias[0], hoje), hoje)
	em_aberto = {p["ym"] for p in competencias_pendentes(apuracoes[0])} if apuracoes else set()
	ja_quitadas = [ym for ym in competencias if ym not in em_aberto]
	if ja_quitadas:
		frappe.log_error(
			title="Cobrança de contribuição paga para mês já quitado",
			message=(
				f"cobranca={doc.name} associado={doc.associado}: "
				f"{', '.join(_rotulo(ym) for ym in ja_quitadas)} já não estava(m) em aberto. "
				"A baixa entrou como crédito, sem detalhar os meses."
			),
		)
		return []

	return [por_ym[ym] for ym in competencias]


def lancar_baixa(doc) -> str | None:
	"""Cria o crédito no extrato que quita as competências cobradas."""
	competencias = _normalizar_competencias(doc.competencias)
	if not competencias:
		frappe.log_error(
			title="Cobrança de contribuição paga sem competências",
			message=f"cobranca={doc.name}: baixa não lançada porque não há competência cobrada.",
		)
		return None

	id_transacao = f"{PREFIXO_ID_TRANSACAO}{doc.name}"
	existente = frappe.db.exists("Transacao Extrato Geral", id_transacao)
	if existente:
		# Baixa já lançada numa passagem anterior que não conseguiu gravar o
		# vínculo. Reaponta em vez de duplicar o crédito.
		frappe.db.set_value("Cobranca Infinitepay", doc.name, "transacao_extrato", id_transacao)
		return id_transacao

	hoje = getdate()
	# O que quita a contribuição é o valor cobrado. `paid_amount` (centavos) pode
	# ser maior — juros de parcelamento, que ficam com a InfinitePay — e só serve
	# de valor quando a cobrança não tem itens com preço.
	valor = _valor_dos_itens(doc) or round(float(doc.paid_amount or 0) / 100.0, 2)
	detalhes = _competencias_da_baixa(doc, competencias, hoje)

	nome_associado = frappe.db.get_value("Associado", doc.associado, "nome_completo") or doc.associado
	rotulos = ", ".join(_rotulo(ym) for ym in competencias)
	metodo = METODO_POR_CAPTURA.get((doc.capture_method or "").strip().lower(), METODO_LANCAMENTO)

	transacao = frappe.get_doc(
		{
			"doctype": "Transacao Extrato Geral",
			"id": id_transacao,
			"descricao": f"Contribuição mensal {rotulos} — {nome_associado}",
			"descricao_reduzida": CATEGORIA_CONTRIBUICAO,
			"debito_credito": "Crédito",
			"valor": valor,
			"valor_absoluto": valor,
			"data_transacao": hoje,
			"mes_competencia": _primeiro_dia(competencias[0]),
			"metodo": metodo,
			"categoria": CATEGORIA_CONTRIBUICAO,
			"beneficiario": doc.associado,
			"ordinaria_extraordinaria": "Ordinária",
			"transacao_revisada": 1,
			"competencias_contribuicao": [
				{
					"mes_referencia": _primeiro_dia(item["ym"]),
					"valor": item["valor"],
					"em_atraso": 1 if item["em_atraso"] else 0,
				}
				for item in detalhes
			],
			"observacoes": (
				f"Baixa automática da cobrança InfinitePay {doc.name}. "
				f"Competências quitadas: {rotulos}. "
				f"transaction_nsu={doc.transaction_nsu or '—'}. "
				f"paid_amount={doc.paid_amount or 0} centavos."
			),
		}
	)
	if frappe.db.exists("Carteira", CARTEIRA_INFINITEPAY):
		transacao.carteira = CARTEIRA_INFINITEPAY
	if frappe.db.exists("Instituicao Financeira", INSTITUICAO_INFINITEPAY):
		transacao.instituicao = INSTITUICAO_INFINITEPAY
	# Quem confirma o pagamento é o webhook da InfinitePay, sem sessão; a
	# `Transacao Extrato Geral` só dá escrita a System Manager.
	transacao.insert(ignore_permissions=True)

	frappe.db.set_value("Cobranca Infinitepay", doc.name, "transacao_extrato", transacao.name)
	frappe.logger().info(
		f"Contribuição quitada pela cobrança {doc.name}: transação {transacao.name} "
		f"para {doc.associado} nas competências {rotulos}."
	)
	return transacao.name


def conciliar_baixas_de_cobranca(hoje: datetime.date | None = None) -> dict:
	"""Concilia as baixas de cobrança com as vendas que chegaram no fechamento importado.

	O mesmo pagamento entra duas vezes no extrato: pela baixa do webhook (com
	beneficiário e meses, fonte Planilha) e pela importação do fechamento da
	InfinitePay (fonte Sistema, sem beneficiário). Sem conciliar, os dois contam.

	A baixa é mantida e a importada sai dos totais, porque é a baixa que diz de
	quem é o dinheiro e que meses quita. O par é achado primeiro pelo
	`transaction_nsu` da cobrança, que é o `id` da venda no relatório. Sem ele, vale
	a busca por valor e data — e só quando não há dúvida: um grupo de baixas de
	mesmo valor no mesmo dia só é conciliado se houver exatamente o mesmo número de
	vendas candidatas (qualquer pareamento dá o mesmo total). O que sobrar fica na
	fila de conciliação manual, como hoje.
	"""
	from gris.api.financeiro.conciliacao import vincular_par

	hoje = hoje or getdate()
	cobrancas = frappe.get_all(
		"Cobranca Infinitepay",
		filters={
			"finalidade": FINALIDADE_CONTRIBUICAO,
			"status": STATUS_COBRANCA_PAGA,
			"transacao_extrato": ["is", "set"],
			"modified": [">=", add_days(hoje, -DIAS_BUSCA_CONCILIACAO)],
		},
		fields=["name", "transaction_nsu", "transacao_extrato"],
		order_by="modified asc",
	)
	if not cobrancas:
		return {"conciliadas": 0, "sem_par": 0}

	baixas = {
		b.name: b
		for b in frappe.get_all(
			"Transacao Extrato Geral",
			filters={
				"name": ["in", [c.transacao_extrato for c in cobrancas]],
				"status_conciliacao": ["!=", "Conciliada"],
				"excluir_do_total": 0,
			},
			fields=["name", "valor", "data_transacao"],
		)
	}

	conciliadas = 0
	usadas: set[str] = set()
	sem_nsu: dict[tuple, list] = {}

	for cobranca in cobrancas:
		baixa = baixas.get(cobranca.transacao_extrato)
		if not baixa:
			continue
		par = _venda_pelo_nsu(cobranca.transaction_nsu)
		if par and par not in usadas:
			vincular_par(par, baixa.name, manter="planilha", ignore_permissions=True)
			usadas.add(par)
			conciliadas += 1
			continue
		chave = (round(float(baixa.valor or 0), 2), getdate(baixa.data_transacao))
		sem_nsu.setdefault(chave, []).append(baixa.name)

	sem_par = 0
	for (valor, data), nomes in sem_nsu.items():
		candidatas = [c for c in _vendas_candidatas(valor, data) if c not in usadas]
		if len(candidatas) != len(nomes):
			sem_par += len(nomes)
			continue
		for venda, baixa in zip(candidatas, sorted(nomes), strict=True):
			vincular_par(venda, baixa, manter="planilha", ignore_permissions=True)
			usadas.add(venda)
			conciliadas += 1

	return {"conciliadas": conciliadas, "sem_par": sem_par}


def _filtros_venda_importada() -> list[list]:
	"""Venda que chegou pelo fechamento da InfinitePay e ainda não tem dono nem par.

	Em lista, e não em dict, porque a busca por valor e data põe dois limites no
	mesmo campo — e o "between" do Frappe trata os limites como datas.
	"""
	return [
		["fonte", "=", "Sistema"],
		["debito_credito", "=", "Crédito"],
		["status_conciliacao", "!=", "Conciliada"],
		["excluir_do_total", "=", 0],
		["beneficiario", "is", "not set"],
		["instituicao", "=", INSTITUICAO_INFINITEPAY],
	]


def _venda_pelo_nsu(transaction_nsu: str | None) -> str | None:
	nsu = (transaction_nsu or "").strip()
	if not nsu:
		return None
	encontradas = frappe.get_all(
		"Transacao Extrato Geral",
		filters=[*_filtros_venda_importada(), ["id", "=", nsu]],
		pluck="name",
		limit_page_length=1,
	)
	return encontradas[0] if encontradas else None


def _vendas_candidatas(valor: float, data: datetime.date) -> list[str]:
	"""Vendas importadas que podem ser o mesmo pagamento da baixa, sem o NSU."""
	return frappe.get_all(
		"Transacao Extrato Geral",
		filters=[
			*_filtros_venda_importada(),
			["valor", ">=", round(valor * (1 - TAXA_MAXIMA_CONCILIACAO), 2)],
			["valor", "<=", round(valor + 0.01, 2)],
			["data_transacao", ">=", add_days(data, -JANELA_DIAS_CONCILIACAO)],
			["data_transacao", "<=", add_days(data, JANELA_DIAS_CONCILIACAO)],
		],
		order_by="timestamp_transacao asc, name asc",
		pluck="name",
	)
