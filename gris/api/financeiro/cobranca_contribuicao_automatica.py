# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Cobrança automática da contribuição mensal por link InfinitePay.

Um job diário faz, para o mês corrente, o que o gestor faria à mão na tela do
contribuinte (`cobranca_contribuicao`):

1. **Emissão.** A partir do dia de emissão configurado, cada contribuinte ativo
   com cobrança ativa e competências em aberto recebe uma `Cobranca Infinitepay`
   com todas elas, e o link vai pelo WhatsApp. "Em aberto" é o que a apuração mês
   a mês mostra na tela do contribuinte — o job cobra o mesmo que o gestor
   cobraria à mão, nem um mês a mais. É uma cobrança automática por associado por
   mês (`mes_emissao`); rodar de novo no mesmo mês só completa quem ficou para
   trás — link que falhou, WhatsApp que não saiu.
2. **Lembrete.** Depois do vencimento, a cada `dias_lembrete_apos_vencimento`
   dias, quem ainda não pagou o link do mês recebe o mesmo link de novo, até
   `max_lembretes` vezes.

Nada acontece antes de `cobranca_automatica_desde`: é a data do corte das
assinaturas da InfinitePay, que convivem com o link até lá.

Cada associado é tratado na sua própria transação — a falha de um (InfinitePay
fora do ar, cadastro inconsistente) não desfaz as cobranças já emitidas nem
impede as seguintes.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

import frappe
from frappe.utils import getdate
from frappe.utils.background_jobs import enqueue

from gris.api.financeiro.cobranca_contribuicao import (
	FINALIDADE_CONTRIBUICAO,
	MESES_COBRANCA,
	ORIGEM_AUTOMATICA,
	STATUS_COBRANCA_PENDENTE,
	_normalizar_competencias,
	emitir_cobranca,
	enviar_cobranca,
)
from gris.api.financeiro.contribuicoes import (
	CATEGORIAS_CONTRIBUINTES,
	calcular_vencimento,
	get_parametros,
)
from gris.api.financeiro.pagamentos_contribuicao import (
	apurar_associados,
	competencias_pendentes,
)
from gris.utils.job_logger import definir_resumo, metrica, obter_logger

CONFIG_DOCTYPE = "Configuracoes Contribuicao Mensal"
NOME_LOGGER = "cobranca_contribuicao_automatica"
# Desfaz só a emissão do associado que falhou, sem tocar no que já foi gravado.
SAVEPOINT_EMISSAO = "cobranca_contribuicao_automatica"


@dataclass(frozen=True)
class ConfigCobrancaAutomatica:
	ativa: bool = False
	desde: datetime.date | None = None
	dia_emissao: int = 1
	dias_lembrete: int = 3
	max_lembretes: int = 2


def get_config() -> ConfigCobrancaAutomatica:
	config = frappe.get_single(CONFIG_DOCTYPE)
	dia_emissao = int(config.get("dia_emissao_cobranca") or 1)
	return ConfigCobrancaAutomatica(
		ativa=bool(config.get("cobranca_automatica_ativa")),
		desde=getdate(config.cobranca_automatica_desde) if config.get("cobranca_automatica_desde") else None,
		dia_emissao=min(max(dia_emissao, 1), 28),
		dias_lembrete=max(int(config.get("dias_lembrete_apos_vencimento") or 0), 0),
		max_lembretes=max(int(config.get("max_lembretes") or 0), 0),
	)


def motivo_para_nao_rodar(config: ConfigCobrancaAutomatica, hoje: datetime.date) -> str | None:
	if not config.ativa:
		return "Cobrança automática desativada em Configuracoes Contribuicao Mensal."
	if not config.desde:
		return "Cobrança automática sem data de início configurada."
	if hoje.replace(day=1) < config.desde.replace(day=1):
		return f"Cobrança automática só começa em {config.desde.strftime('%m/%Y')}."
	return None


def enqueue_cobrancas_automaticas():
	"""Job diário: se a cobrança automática estiver valendo, enfileira na fila longa."""
	logger = obter_logger(NOME_LOGGER)
	motivo = motivo_para_nao_rodar(get_config(), getdate())
	if motivo:
		logger.info(motivo)
		definir_resumo(motivo)
		return

	definir_resumo("Cobrança automática da contribuição enviada para a fila longa.")
	enqueue(
		"gris.api.financeiro.cobranca_contribuicao_automatica.executar_cobrancas_automaticas",
		queue="long",
		timeout=3600,
		job_name=f"{frappe.local.site}:cobranca-contribuicao-automatica",
	)


def executar_cobrancas_automaticas(
	hoje: datetime.date | str | None = None, associados: list[str] | None = None
) -> dict:
	"""Emite as cobranças do mês e envia os lembretes devidos hoje.

	`associados` restringe a execução a um conjunto conhecido — para testar ou para
	rodar à mão (`bench execute`) só para algumas famílias.
	"""
	logger = obter_logger(NOME_LOGGER)
	hoje = getdate(hoje) if hoje else getdate()
	config = get_config()

	motivo = motivo_para_nao_rodar(config, hoje)
	if motivo:
		logger.info(motivo)
		definir_resumo(motivo)
		return {"executado": False, "motivo": motivo}

	emissao = emitir_cobrancas_do_mes(config, hoje, associados)
	lembretes = enviar_lembretes(config, hoje, associados)

	for chave, valor in {**emissao, **{f"lembretes_{k}": v for k, v in lembretes.items()}}.items():
		metrica(chave, valor, incrementar=False)

	definir_resumo(
		f"{emissao['emitidas']} cobrança(s) emitida(s), {emissao['enviadas']} enviada(s) pelo WhatsApp, "
		f"{emissao['nao_enviadas']} sem envio, {emissao['falhas']} falha(s) na emissão; "
		f"{lembretes['enviados']} lembrete(s) enviado(s)."
	)
	return {"executado": True, "emissao": emissao, "lembretes": lembretes}


def _commit() -> None:
	# Commit por associado: a cobrança emitida já tem link na InfinitePay e a
	# mensagem já pode ter saído. A falha do associado seguinte não pode desfazer
	# isso com um rollback.
	frappe.db.commit()  # nosemgrep


def emitir_cobrancas_do_mes(
	config: ConfigCobrancaAutomatica, hoje: datetime.date, associados: list[str] | None = None
) -> dict:
	"""Emite e envia a cobrança do mês de cada contribuinte que ainda não tem uma."""
	logger = obter_logger(NOME_LOGGER)
	resultado = {"emitidas": 0, "enviadas": 0, "nao_enviadas": 0, "falhas": 0, "reenvios": 0}
	if hoje.day < config.dia_emissao:
		logger.info(f"Antes do dia de emissão ({config.dia_emissao}); nenhuma cobrança nova hoje.")
		return resultado

	mes = hoje.replace(day=1)
	filtros_cobranca = {
		"finalidade": FINALIDADE_CONTRIBUICAO,
		"origem": ORIGEM_AUTOMATICA,
		"mes_emissao": mes,
	}
	filtros_associado: dict = {
		"status_no_grupo": "Ativo",
		"status_cobranca": "Ativo",
		"categoria": ["in", list(CATEGORIAS_CONTRIBUINTES)],
	}
	if associados is not None:
		filtros_cobranca["associado"] = ["in", associados or [""]]
		filtros_associado["name"] = ["in", associados or [""]]

	do_mes = frappe.get_all(
		"Cobranca Infinitepay",
		filters=filtros_cobranca,
		fields=["name", "associado", "status", "ultimo_envio_whatsapp"],
	)
	ja_emitidos = {c.associado for c in do_mes}

	# Cobrança do mês emitida mas cuja mensagem não saiu (sem telefone, WhatsApp
	# fora do ar): tenta de novo a cada execução até sair ou até ser paga.
	for cobranca in do_mes:
		if cobranca.status != STATUS_COBRANCA_PENDENTE or cobranca.ultimo_envio_whatsapp:
			continue
		resultado["reenvios"] += 1
		if _enviar(cobranca.name, lembrete=False):
			resultado["enviadas"] += 1
		else:
			resultado["nao_enviadas"] += 1
		_commit()

	contribuintes = frappe.get_all("Associado", filters=filtros_associado, pluck="name", limit_page_length=0)
	a_cobrar = [nome for nome in contribuintes if nome not in ja_emitidos]
	logger.info(
		f"{len(contribuintes)} contribuinte(s) com cobrança ativa; "
		f"{len(ja_emitidos)} já com cobrança automática em {mes.strftime('%m/%Y')}."
	)

	for apuracao in apurar_associados(a_cobrar, MESES_COBRANCA, hoje):
		pendentes = competencias_pendentes(apuracao)
		if not pendentes:
			continue
		associado = apuracao["id"]
		frappe.db.savepoint(SAVEPOINT_EMISSAO)
		try:
			cobranca = emitir_cobranca(
				associado,
				[p["ym"] for p in pendentes],
				origem=ORIGEM_AUTOMATICA,
				pendentes=pendentes,
				hoje=hoje,
			)
			if not cobranca["link_pagamento"]:
				raise frappe.ValidationError(
					f"A InfinitePay não devolveu link para a cobrança {cobranca['name']}."
				)
			resultado["emitidas"] += 1
			_commit()
		except Exception:
			frappe.db.rollback(save_point=SAVEPOINT_EMISSAO)
			resultado["falhas"] += 1
			logger.exception(f"Falha ao emitir a cobrança de {apuracao['nome']} ({associado}).")
			frappe.log_error(frappe.get_traceback(), f"Cobrança automática: {associado}")
			continue

		if _enviar(cobranca["name"], lembrete=False):
			resultado["enviadas"] += 1
		else:
			resultado["nao_enviadas"] += 1
		_commit()

	return resultado


def _enviar(nome_cobranca: str, *, lembrete: bool) -> bool:
	logger = obter_logger(NOME_LOGGER)
	try:
		envio = enviar_cobranca(nome_cobranca, lembrete=lembrete)
	except Exception:
		logger.exception(f"Falha ao enviar a cobrança {nome_cobranca} pelo WhatsApp.")
		frappe.log_error(frappe.get_traceback(), f"Cobrança automática (envio): {nome_cobranca}")
		return False
	if not envio["enviado"]:
		logger.warning(f"Cobrança {nome_cobranca} não enviada: {envio.get('motivo')}")
	return bool(envio["enviado"])


def enviar_lembretes(
	config: ConfigCobrancaAutomatica, hoje: datetime.date, associados: list[str] | None = None
) -> dict:
	"""Reenvia o link do mês a quem ainda não pagou, depois do vencimento.

	O n-ésimo lembrete sai `n * dias_lembrete` dias depois do vencimento. Antes de
	lembrar, a apuração é refeita: se algum mês da cobrança já foi quitado por outro
	caminho (PIX direto, pagamento manual), o link está com o valor errado e o
	lembrete não sai — a emissão do mês seguinte refaz a cobrança com o que faltar.
	"""
	logger = obter_logger(NOME_LOGGER)
	resultado = {"elegiveis": 0, "enviados": 0, "quitadas_por_outro_meio": 0}
	if config.max_lembretes <= 0 or config.dias_lembrete <= 0:
		return resultado

	mes = hoje.replace(day=1)
	vencimento = calcular_vencimento(mes, get_parametros().dia_vencimento)
	dias_apos_vencimento = (hoje - vencimento).days
	if dias_apos_vencimento < config.dias_lembrete:
		return resultado

	filtros = {
		"finalidade": FINALIDADE_CONTRIBUICAO,
		"origem": ORIGEM_AUTOMATICA,
		"status": STATUS_COBRANCA_PENDENTE,
		"mes_emissao": mes,
		"lembretes_enviados": ["<", config.max_lembretes],
		"link_pagamento": ["is", "set"],
	}
	if associados is not None:
		filtros["associado"] = ["in", associados or [""]]
	cobrancas = frappe.get_all(
		"Cobranca Infinitepay",
		filters=filtros,
		fields=["name", "associado", "competencias", "lembretes_enviados", "ultimo_envio_whatsapp"],
	)
	elegiveis = [
		c
		for c in cobrancas
		if dias_apos_vencimento >= config.dias_lembrete * (int(c.lembretes_enviados or 0) + 1)
		and not (c.ultimo_envio_whatsapp and getdate(c.ultimo_envio_whatsapp) == hoje)
	]
	resultado["elegiveis"] = len(elegiveis)
	if not elegiveis:
		return resultado

	em_aberto = {
		apuracao["id"]: {p["ym"] for p in competencias_pendentes(apuracao)}
		for apuracao in apurar_associados([c.associado for c in elegiveis], MESES_COBRANCA, hoje)
	}
	for cobranca in elegiveis:
		competencias = _normalizar_competencias(cobranca.competencias)
		if not set(competencias) <= em_aberto.get(cobranca.associado, set()):
			resultado["quitadas_por_outro_meio"] += 1
			logger.info(f"Lembrete da cobrança {cobranca.name} não enviado: mês já quitado por outro meio.")
			continue
		if _enviar(cobranca.name, lembrete=True):
			resultado["enviados"] += 1
		_commit()

	return resultado


# Classe visual (badge da tela de contribuições) de cada situação da cobrança.
SLUG_STATUS_COBRANCA = {"Pago": "pago", "Pendente": "aberto", "Erro": "atrasado", "Substituída": "na"}


def resumo_cobrancas_do_mes(hoje: datetime.date | None = None, associados: set[str] | None = None) -> dict:
	"""Acompanhamento das cobranças emitidas no mês, para a tela do financeiro.

	Junta as automáticas e as manuais do mês: o que interessa ao gestor é quem já
	recebeu o link, quem pagou e quem ficou sem mensagem. `associados` recorta as
	cobranças (o chefe de seção só vê as dos próprios beneficiários).
	"""
	hoje = hoje or getdate()
	mes = hoje.replace(day=1)
	config = get_config()

	filtros: dict = {"finalidade": FINALIDADE_CONTRIBUICAO, "mes_emissao": mes}
	if associados is not None:
		filtros["associado"] = ["in", list(associados) or [""]]

	cobrancas = frappe.get_all(
		"Cobranca Infinitepay",
		filters=filtros,
		fields=[
			"name",
			"associado",
			"status",
			"origem",
			"competencias",
			"ultimo_envio_whatsapp",
			"resultado_ultimo_envio",
			"lembretes_enviados",
		],
		order_by="creation desc",
		limit_page_length=0,
	)

	nomes: dict[str, str] = {}
	valores: dict[str, float] = {}
	if cobrancas:
		associados = list({c.associado for c in cobrancas if c.associado})
		nomes = {
			a.name: a.nome_completo
			for a in frappe.get_all(
				"Associado", filters={"name": ["in", associados]}, fields=["name", "nome_completo"]
			)
		}
		for item in frappe.get_all(
			"Item Cobranca Infinitepay",
			filters={"parent": ["in", [c.name for c in cobrancas]], "parenttype": "Cobranca Infinitepay"},
			fields=["parent", "quantidade", "preco"],
		):
			valores[item.parent] = valores.get(item.parent, 0.0) + float(item.quantidade or 0) * float(
				item.preco or 0
			)

	linhas = []
	totais = {
		"emitidas": 0,
		"pagas": 0,
		"pendentes": 0,
		"sem_envio": 0,
		"valor_pago": 0.0,
		"valor_pendente": 0.0,
	}
	for cobranca in cobrancas:
		valor = round(valores.get(cobranca.name, 0.0), 2)
		sem_envio = cobranca.status == STATUS_COBRANCA_PENDENTE and not cobranca.ultimo_envio_whatsapp
		if cobranca.status != "Substituída":
			totais["emitidas"] += 1
		if cobranca.status == "Pago":
			totais["pagas"] += 1
			totais["valor_pago"] += valor
		elif cobranca.status == STATUS_COBRANCA_PENDENTE:
			totais["pendentes"] += 1
			totais["valor_pendente"] += valor
		totais["sem_envio"] += 1 if sem_envio else 0
		linhas.append(
			{
				"name": cobranca.name,
				"associado": cobranca.associado,
				"nome": nomes.get(cobranca.associado) or cobranca.associado,
				"status": cobranca.status,
				"status_slug": SLUG_STATUS_COBRANCA.get(cobranca.status, "na"),
				"origem": cobranca.origem,
				"competencias": ", ".join(
					f"{ym[5:]}/{ym[:4]}" for ym in _normalizar_competencias(cobranca.competencias)
				),
				"valor": valor,
				"ultimo_envio_whatsapp": cobranca.ultimo_envio_whatsapp,
				"resultado_ultimo_envio": cobranca.resultado_ultimo_envio,
				"lembretes_enviados": cobranca.lembretes_enviados or 0,
				"sem_envio": sem_envio,
			}
		)
	# Quem ainda não recebeu a mensagem vem primeiro: é a lista de trabalho do gestor.
	linhas.sort(key=lambda linha: (not linha["sem_envio"], linha["status"] != STATUS_COBRANCA_PENDENTE))

	return {
		"mes": mes.strftime("%m/%Y"),
		"automatica": {
			"ativa": config.ativa,
			"desde": config.desde.strftime("%m/%Y") if config.desde else None,
			"dia_emissao": config.dia_emissao,
			"motivo_parada": motivo_para_nao_rodar(config, hoje),
		},
		"totais": {
			**totais,
			"valor_pago": round(totais["valor_pago"], 2),
			"valor_pendente": round(totais["valor_pendente"], 2),
		},
		"cobrancas": linhas,
	}
