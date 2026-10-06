"""Cálculo do funil de recepção de novos associados.

Concentra a definição das etapas e a cadência esperada entre elas (configurada em
``Configuracoes de Recepcao``) para que a página ``/recepcao/visao_geral`` e a
integração MCP usem exatamente a mesma regra.

A data-base de cada pessoa é a data da visita mais recente. A partir dela, cada
etapa com intervalo configurado empurra a data estimada da próxima; uma etapa
pendente cuja data estimada já passou está atrasada.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import add_days, date_diff, format_date, getdate

DOCTYPE = "Novo Associado"

# Single com a cadência do funil e a espera do registro definitivo.
DOCTYPE_CONFIGURACOES = "Configuracoes de Recepcao"

# Ramos na ordem crescente de idade, como aparecem no Select de ``Novo Associado``.
# Ordem canônica para qualquer listagem por ramo do fluxo de recepção.
RAMOS: tuple[str, ...] = ("Filhotes", "Lobinho", "Escoteiro", "Sênior", "Pioneiro")

# Todas as etapas do funil, na ordem de quem entra com registro provisório. A ordem de
# quem entra direto no definitivo é outra — ver ``ORDEM_DEFINITIVO`` e ``etapas_do_fluxo``.
STEPS_DEF: list[dict[str, Any]] = [
	{"field": "visita_agendada", "label": "Visita Agendada"},
	{"field": "primeira_visita_realizada", "label": "Primeira Visita Realizada"},
	{"field": "dados_para_registro_enviados", "label": "Dados Enviados"},
	{"field": "registro_criado_no_paxtu", "label": "Registro no Paxtu"},
	# Emitir o boleto é uma etapa própria, e não parte da efetivação: entre gerar o boleto
	# e o registro sair há a espera do pagamento, e é justamente essa fila que a recepção
	# precisa enxergar no funil. Vale para os dois registros.
	{"field": "boleto_provisorio_gerado", "label": "Boleto Provisório Gerado"},
	{"field": "registro_provisorio_efetivado", "label": "Registro Provisório Efetivado"},
	{"field": "pesquisa_de_novos_associados_respondida", "label": "Pesquisa Respondida"},
	{"field": "ficha_medica_preenchida", "label": "Ficha Médica"},
	{"field": "id_escoteiros_criado", "label": "ID Escoteiros Criado"},
	{"field": "boleto_definitivo_gerado", "label": "Boleto Definitivo Gerado"},
	{"field": "registro_definitivo_efetivado", "label": "Registro Definitivo Efetivado"},
	{"field": "reuniao_de_acolhida_realizada", "label": "Reunião de Acolhida"},
]

# Etapas que só existem para quem entra com registro provisório.
ETAPAS_DO_PROVISORIO: tuple[str, ...] = ("boleto_provisorio_gerado", "registro_provisorio_efetivado")

# Quem entra direto no definitivo paga e efetiva o registro logo depois do Paxtu, antes
# das pendências que vêm com ele: a ficha médica só abre no Paxtu com o número de registro
# (o lembrete dela espera a mesma efetivação, ver
# ``gris.api.recepcao_mensagens.enviar_lembretes_ficha_medica``), e pesquisa, ficha,
# id@escoteiros e acolhida são o que a coluna "Acompanhamento Final" acompanha.
ORDEM_DEFINITIVO: tuple[str, ...] = (
	"visita_agendada",
	"primeira_visita_realizada",
	"dados_para_registro_enviados",
	"registro_criado_no_paxtu",
	"boleto_definitivo_gerado",
	"registro_definitivo_efetivado",
	"pesquisa_de_novos_associados_respondida",
	"ficha_medica_preenchida",
	"id_escoteiros_criado",
	"reuniao_de_acolhida_realizada",
)

# Campo da etapa -> campo de intervalo (em dias) nas Configuracoes de Recepcao.
FIELD_INTERVAL_MAP: dict[str, str] = {
	"dados_para_registro_enviados": "dados_para_registro_enviados",
	"registro_criado_no_paxtu": "registro_criado_no_paxtu",
	"boleto_provisorio_gerado": "boleto_provisorio_gerado",
	"registro_provisorio_efetivado": "registro_provisorio_efetivado",
	"pesquisa_de_novos_associados_respondida": "pesquisa_de_novos_associados_respondida",
	"ficha_medica_preenchida": "ficha_medica_preenchida",
	"id_escoteiros_criado": "id_escoteiros_criado",
	"boleto_definitivo_gerado": "boleto_definitivo_gerado",
	"registro_definitivo_efetivado": "registro_definitivo_efetivado",
	"reuniao_de_acolhida_realizada": "reuniao_de_acolhida_realizada",
}

CAMPOS_DE_ETAPA: tuple[str, ...] = tuple(step["field"] for step in STEPS_DEF)

_ETAPA_POR_CAMPO: dict[str, dict[str, Any]] = {step["field"]: step for step in STEPS_DEF}

# Etapas que efetivam o registro do jovem. As duas exigem o número de registro do
# jovem (e dos responsáveis que serão registrados) antes de serem marcadas — ver
# ``gris.www.recepcao.visao_geral.update_step_status``.
CAMPOS_DE_EFETIVACAO: tuple[str, ...] = (
	"registro_provisorio_efetivado",
	"registro_definitivo_efetivado",
)

# Colunas do kanban envolvidas na visita. Quando a visita cai e precisa ser
# remarcada, o card volta para a coluna anterior — é lá que a recepção tem o
# botão de agendar — carregando o sinal ``reagendamento_pendente``.
STATUS_VISITA_AGENDADA = "Visita Agendada"
STATUS_ANTES_DA_VISITA = "Conversa Inicial"
STATUS_AGUARDAR_DADOS = "Aguardar Dados"
STATUS_FAZER_REGISTRO = "Fazer Registro"

# A coluna "Acompanhamento" do kanban é dividida em três listas. A separação é
# derivada dos dados, não gravada em ``status``: quem ainda espera o registro
# provisório fica na lista provisória e migra sozinho para a definitiva assim que
# ``registro_provisorio_efetivado`` é marcado; efetivado o registro definitivo, vai
# para a final, onde restam pesquisa, ficha médica, id@escoteiros e acolhida. Quem já
# entrou como Definitivo nunca passa pela lista provisória.
STATUS_ACOMPANHAMENTO = "Acompanhamento"
COLUNA_ACOMPANHAMENTO_PROVISORIO = "Acompanhamento Provisório"
COLUNA_ACOMPANHAMENTO_DEFINITIVO = "Acompanhamento Definitivo"
COLUNA_ACOMPANHAMENTO_FINAL = "Acompanhamento Final"
COLUNAS_DE_ACOMPANHAMENTO = (
	COLUNA_ACOMPANHAMENTO_PROVISORIO,
	COLUNA_ACOMPANHAMENTO_DEFINITIVO,
	COLUNA_ACOMPANHAMENTO_FINAL,
)

# Etapas que também movem a coluna do funil, na ordem do fluxo.
#
# A regra existia espalhada pelos pontos de entrada — ``confirmar_registro_paxtu``,
# ``gris.api.recepcao.registrar_recepcao_realizada`` e ``gris.www.responsavel.registro`` — e a
# bolinha da timeline não passava por nenhum deles: marcava a etapa e deixava o card parado na
# coluna antiga. Centralizar em ``update_step_status``, por onde todos os caminhos passam, é o
# que mantém etapa e status em sincronia.
#
# É uma tupla ordenada, e não um dicionário, porque desmarcar precisa saber qual etapa vem
# antes para devolver o card à lista certa (ver ``status_por_etapas_concluidas``).
ETAPAS_QUE_MOVEM_O_FUNIL: tuple[tuple[str, str], ...] = (
	("visita_agendada", STATUS_VISITA_AGENDADA),
	("primeira_visita_realizada", STATUS_AGUARDAR_DADOS),
	("dados_para_registro_enviados", STATUS_FAZER_REGISTRO),
	("registro_criado_no_paxtu", STATUS_ACOMPANHAMENTO),
)

# Espera até cobrar o registro definitivo de quem entrou com registro provisório.
# É a mesma configuração do aviso por WhatsApp
# (``gris.api.registro_provisorio_notificacoes``): o selo do kanban e a mensagem
# contam o mesmo prazo, senão a recepção veria duas verdades para a mesma pessoa.
CAMPO_DIAS_REGISTRO_DEFINITIVO = "dias_aviso_seguimento_provisorio"
DIAS_PADRAO_REGISTRO_DEFINITIVO = 20

# O ramo Filhotes anda em outro ritmo: o envio dos dados, o definitivo e a acolhida demoram
# mais. Cada um tem o seu campo em ``Configuracoes de Recepcao``, lido no lugar do geral
# quando o jovem é Filhote — ver ``dias_para_registro_definitivo``, ``dias_de_dados_filhotes``
# e ``dias_de_acolhida_filhotes``.
RAMO_FILHOTES = "Filhotes"
CAMPO_DIAS_REGISTRO_DEFINITIVO_FILHOTES = "dias_aviso_seguimento_provisorio_filhotes"
DIAS_PADRAO_REGISTRO_DEFINITIVO_FILHOTES = 25
CAMPO_DIAS_DADOS_FILHOTES = "dados_para_registro_enviados_filhotes"
DIAS_PADRAO_DADOS_FILHOTES = 30
CAMPO_DIAS_ACOLHIDA_FILHOTES = "reuniao_de_acolhida_realizada_filhotes"
DIAS_PADRAO_ACOLHIDA_FILHOTES = 30

# O id@escoteiros só é exigido de quem já tem esta idade. Abaixo dela a etapa continua no
# fluxo, marcada como opcional, e a família não recebe cobrança (ver
# ``gris.api.recepcao_mensagens.enviar_lembretes_id_escoteiros``).
CAMPO_ID_ESCOTEIROS = "id_escoteiros_criado"
IDADE_ID_ESCOTEIROS_OBRIGATORIO = 15
SUFIXO_ETAPA_OPCIONAL = " (opcional)"

CAMPO_DADOS_ENVIADOS = "dados_para_registro_enviados"
CAMPO_ACOLHIDA = "reuniao_de_acolhida_realizada"

# Etapas em que o ramo Filhotes troca o intervalo geral por um prazo próprio:
# etapa -> (campo em ``Configuracoes de Recepcao``, padrão). Ao contrário do intervalo geral,
# onde zero quer dizer "mesmo dia", aqui zero ou vazio cai no padrão (``_dias_configurados``).
PRAZOS_PROPRIOS_DOS_FILHOTES: dict[str, tuple[str, int]] = {
	CAMPO_DADOS_ENVIADOS: (CAMPO_DIAS_DADOS_FILHOTES, DIAS_PADRAO_DADOS_FILHOTES),
	CAMPO_ACOLHIDA: (CAMPO_DIAS_ACOLHIDA_FILHOTES, DIAS_PADRAO_ACOLHIDA_FILHOTES),
}

# Status que não pertencem à esteira do funil: quem está neles saiu do fluxo por decisão da
# recepção, e desmarcar uma etapa não pode arrastar o card de volta para uma coluna do kanban.
STATUS_FORA_DO_FUNIL: tuple[str, ...] = ("Fila de espera", "Concluído")


def status_por_etapas_concluidas(dados) -> str:
	"""Status derivado das etapas que continuam marcadas — a lista certa para o card.

	Marcar uma etapa empurra o card para a frente; desmarcar tem de trazê-lo de volta, e não
	necessariamente uma coluna: desmarcar "Registro no Paxtu" de quem nunca enviou os dados
	devolve o card a "Visita Agendada", não a "Fazer Registro". Recalcular a partir do que
	sobrou marcado acerta os dois casos com a mesma regra.

	Nenhuma etapa marcada devolve ``STATUS_ANTES_DA_VISITA`` ("Conversa Inicial"), a coluna
	onde a recepção tem o botão de agendar. A divisão de "Acompanhamento" entre as listas
	provisória, definitiva e final continua com ``coluna_de_acompanhamento``: ela é derivada
	dos dados, não do ``status``.
	"""
	status = STATUS_ANTES_DA_VISITA
	for campo, alvo in ETAPAS_QUE_MOVEM_O_FUNIL:
		if dados.get(campo):
			status = alvo

	return status


def coluna_de_acompanhamento(dados) -> str:
	"""Qual das três listas de acompanhamento recebe o card.

	Registro definitivo efetivado leva à lista final, nos dois tipos de registro: dali em
	diante só restam as pendências que vêm depois dele. Antes disso, mesma condição de
	``etapas_do_fluxo``: só quem não é "Definitivo" enxerga a etapa do registro provisório,
	então só esse grupo pode ficar na lista provisória — e sai dela quando a etapa é
	concluída.
	"""
	if dados.get("registro_definitivo_efetivado"):
		return COLUNA_ACOMPANHAMENTO_FINAL

	e_definitivo = dados.get("tipo_de_registro") == "Definitivo"
	if not e_definitivo and not dados.get("registro_provisorio_efetivado"):
		return COLUNA_ACOMPANHAMENTO_PROVISORIO
	return COLUNA_ACOMPANHAMENTO_DEFINITIVO


def etapas_do_fluxo(tipo_de_registro) -> list[dict[str, Any]]:
	"""Definições das etapas (``field``/``label``) na ordem do tipo de registro.

	Provisório — ou tipo ainda não escolhido — segue ``STEPS_DEF``; Definitivo segue
	``ORDEM_DEFINITIVO``, sem as etapas do registro provisório. É a ordem única usada pelo
	kanban, pela ficha de registro, pelo portal do responsável e pelo MCP.
	"""
	if tipo_de_registro != "Definitivo":
		return list(STEPS_DEF)
	return [_ETAPA_POR_CAMPO[campo] for campo in ORDEM_DEFINITIVO]


def _dias_configurados(config: dict | None, campo: str, padrao: int) -> int:
	"""Prazo em dias de ``Configuracoes de Recepcao``; ausente, inválido ou ≤ 0 vira ``padrao``.

	``config`` evita reabrir o Single quando quem chama já carregou a configuração do funil.
	"""
	valor = frappe.db.get_single_value(DOCTYPE_CONFIGURACOES, campo) if config is None else config.get(campo)

	try:
		dias = int(valor)
	except (TypeError, ValueError):
		return padrao

	return dias if dias > 0 else padrao


def dias_para_registro_definitivo(config: dict | None = None, ramo: str | None = None) -> int:
	"""Dias corridos entre efetivar o provisório e cobrar o registro definitivo.

	Sai de ``Configuracoes de Recepcao``: o ramo Filhotes tem campo próprio (padrão 25),
	os demais usam o geral (padrão 20). Valor ausente, inválido ou não positivo cai no
	padrão do ramo.
	"""
	if ramo == RAMO_FILHOTES:
		return _dias_configurados(
			config, CAMPO_DIAS_REGISTRO_DEFINITIVO_FILHOTES, DIAS_PADRAO_REGISTRO_DEFINITIVO_FILHOTES
		)
	return _dias_configurados(config, CAMPO_DIAS_REGISTRO_DEFINITIVO, DIAS_PADRAO_REGISTRO_DEFINITIVO)


def dias_de_dados_filhotes(config: dict | None = None) -> int:
	"""Dias entre a visita e o envio dos dados para registro no ramo Filhotes (padrão 30).

	Vale para a data prevista da etapa na timeline e para segurar o primeiro lembrete de
	dados à família (``gris.api.recepcao_mensagens.enviar_lembretes_dados_registro``).
	"""
	return _dias_configurados(config, CAMPO_DIAS_DADOS_FILHOTES, DIAS_PADRAO_DADOS_FILHOTES)


def dias_de_acolhida_filhotes(config: dict | None = None) -> int:
	"""Dias entre o registro definitivo e a acolhida no ramo Filhotes (padrão 30).

	Vale para a data prevista da etapa na timeline e para segurar o primeiro aviso de
	acolhida aos chefes (``gris.api.recepcao_mensagens.enviar_lembretes_acolhida_lenco``).
	"""
	return _dias_configurados(config, CAMPO_DIAS_ACOLHIDA_FILHOTES, DIAS_PADRAO_ACOLHIDA_FILHOTES)


def id_escoteiros_obrigatorio(dados, hoje=None) -> bool:
	"""Se o id@escoteiros é exigido deste jovem: 15 anos completos ou mais.

	A idade é a de hoje, então quem faz 15 anos no meio do fluxo passa a ter a etapa
	obrigatória. Sem data de nascimento a etapa continua obrigatória, como sempre foi —
	afrouxar a regra por falta de dado esconderia uma pendência real.

	A conta é feita aqui, e não com ``idade_decimal`` do controller de ``Novo Associado``,
	porque o controller importa este módulo.
	"""
	nascimento = dados.get("data_de_nascimento")
	if not nascimento:
		return True

	nascimento = getdate(nascimento)
	hoje = getdate(hoje) if hoje else getdate()
	anos = hoje.year - nascimento.year - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))
	return anos >= IDADE_ID_ESCOTEIROS_OBRIGATORIO


def sinal_registro_definitivo(dados, dias_limite: int | None = None, hoje=None) -> dict:
	"""Se já passou da hora de gerar o registro definitivo deste jovem.

	Mesma condição do aviso por WhatsApp: registro provisório efetivado, definitivo
	ainda não, fora dos status que saíram do funil e ``dias_limite`` dias corridos
	desde ``data_registro_provisorio_efetivado``. Sem ``dias_limite``, o prazo é o do
	ramo do jovem (ver ``dias_para_registro_definitivo``).

	Devolve ``{"pendente", "dias", "desde"}`` — ``dias`` e ``desde`` só preenchidos
	quando pendente, para a interface poder dizer desde quando o relógio corre.
	"""
	ausente = {"pendente": False, "dias": None, "desde": None}

	if dados.get("tipo_de_registro") == "Definitivo":
		return ausente

	if not dados.get("registro_provisorio_efetivado") or dados.get("registro_definitivo_efetivado"):
		return ausente

	if dados.get("status") in STATUS_FORA_DO_FUNIL:
		return ausente

	efetivado_em = dados.get("data_registro_provisorio_efetivado")
	if not efetivado_em:
		return ausente

	desde = getdate(efetivado_em)
	dias = date_diff(getdate(hoje) if hoje else getdate(), desde)
	limite = dias_limite if dias_limite is not None else dias_para_registro_definitivo(ramo=dados.get("ramo"))

	if dias < limite:
		return ausente

	return {"pendente": True, "dias": dias, "desde": desde}


def anexar_historico(etapas: list[dict], historico: dict) -> list[dict]:
	"""Acrescenta às etapas concluídas quem marcou a conclusão e quando.

	``historico`` mapeia campo da etapa -> ``{"concluida_em", "concluido_por"}``
	(ver a tabela ``historico_de_etapas`` de ``Novo Associado``). Etapas concluídas
	antes de o histórico passar a ser gravado ficam sem as chaves, e a interface
	mostra isso em vez de inventar uma data.
	"""
	for etapa in etapas:
		if not etapa.get("completed"):
			continue
		registro = historico.get(etapa["field"]) or {}
		if registro.get("concluida_em"):
			etapa["concluida_em"] = registro["concluida_em"]
		if registro.get("concluido_por"):
			etapa["concluido_por"] = registro["concluido_por"]
	return etapas


def carregar_configuracao() -> dict:
	"""Intervalos configurados; dicionário vazio quando o Single não existe."""
	try:
		return frappe.get_doc("Configuracoes de Recepcao").as_dict()
	except (frappe.DoesNotExistError, ImportError):
		return {}


def _prazo_da_etapa(campo: str, ramo: str | None) -> dict | None:
	"""De onde sai o intervalo de ``campo`` no ``ramo``; None quando a etapa não tem intervalo.

	Nos Filhotes, o envio dos dados e a acolhida têm prazo próprio
	(``PRAZOS_PROPRIOS_DOS_FILHOTES``). As demais etapas, e essas duas nos outros ramos, usam
	o campo homônimo de ``FIELD_INTERVAL_MAP``.

	``padrao`` diz como ler o campo: ``None`` é o intervalo geral, em que zero vale "mesmo
	dia"; um número é o padrão que entra no lugar de zero ou vazio. É a regra que o funil
	aplica (``_intervalo_da_etapa``) e que a árvore de prazos mostra (``estrutura_dos_prazos``).
	"""
	if ramo == RAMO_FILHOTES and campo in PRAZOS_PROPRIOS_DOS_FILHOTES:
		campo_filhotes, padrao = PRAZOS_PROPRIOS_DOS_FILHOTES[campo]
		return {"campo": campo_filhotes, "padrao": padrao, "proprio_do_ramo": True}

	campo_config = FIELD_INTERVAL_MAP.get(campo)
	if not campo_config:
		return None

	return {"campo": campo_config, "padrao": None, "proprio_do_ramo": False}


def _intervalo_da_etapa(campo: str, config: dict, dados) -> int | None:
	"""Dias entre a etapa anterior e ``campo``; None quando a etapa não tem intervalo."""
	prazo = _prazo_da_etapa(campo, dados.get("ramo"))
	if not prazo:
		return None

	if prazo["padrao"] is not None:
		return _dias_configurados(config, prazo["campo"], prazo["padrao"])

	try:
		return int(config.get(prazo["campo"]) or 0)
	except (ValueError, TypeError):
		return None


def calcular_etapas(dados, config: dict | None = None, data_base=None, hoje=None) -> list[dict]:
	"""Etapas de uma pessoa, com data estimada e marcação de atraso.

	``dados`` precisa conter ``tipo_de_registro`` e os campos de etapa; a ordem das
	etapas, e portanto a das datas estimadas, é a de ``etapas_do_fluxo``.
	``data_de_nascimento`` decide se o id@escoteiros é opcional e ``ramo`` decide o
	prazo do envio dos dados e o da acolhida. ``data_base`` é a data da visita mais recente (None desliga as
	estimativas).

	As chaves ``label``/``completed``/``field``/``estimated_date``/``is_overdue``
	são consumidas pelo JavaScript do kanban da recepção; ``data_estimada``
	(ISO) existe para consumo programático. Etapa opcional leva ``opcional: True`` e,
	pendente, não tem data prevista nem atraso — mas o intervalo dela continua contando,
	para não puxar para trás a previsão das etapas seguintes.
	"""
	config = config if config is not None else carregar_configuracao()
	hoje = getdate(hoje) if hoje else getdate()
	id_escoteiros_opcional = not id_escoteiros_obrigatorio(dados, hoje)

	etapas: list[dict] = []
	data_corrente = getdate(data_base) if data_base else None

	for step in etapas_do_fluxo(dados.get("tipo_de_registro")):
		concluida = bool(dados.get(step["field"]))
		etapa = {"label": step["label"], "completed": concluida, "field": step["field"]}

		opcional = id_escoteiros_opcional and step["field"] == CAMPO_ID_ESCOTEIROS
		if opcional:
			etapa["label"] += SUFIXO_ETAPA_OPCIONAL
			etapa["opcional"] = True

		if data_corrente:
			dias = _intervalo_da_etapa(step["field"], config, dados)
			if dias is not None:
				data_corrente = getdate(add_days(data_corrente, dias))
				if not concluida and not opcional:
					etapa["estimated_date"] = format_date(data_corrente)
					etapa["data_estimada"] = data_corrente.isoformat()
					if data_corrente < hoje:
						etapa["is_overdue"] = True

		etapas.append(etapa)

	return etapas


def so_falta_acolhida(dados, etapas: list[dict]) -> bool:
	"""Se a acolhida é a única etapa obrigatória ainda pendente.

	``etapas`` é a saída de ``calcular_etapas`` para o mesmo jovem — é ela que sabe quais
	etapas o tipo de registro tem e qual é opcional. Quem saiu do funil não é sinalizado.
	"""
	if dados.get("status") in STATUS_FORA_DO_FUNIL:
		return False

	return _pendencias_obrigatorias(etapas) == {CAMPO_ACOLHIDA}


def pronto_para_finalizar(dados, etapas: list[dict]) -> bool:
	"""Se só falta clicar em "Finalizar Recepção": nenhuma etapa obrigatória pendente.

	A etapa opcional (id@escoteiros abaixo dos 15 anos) não segura a finalização. É o mesmo
	sinal que libera o botão no dialog do card e que pinta o card na visão geral. Quem saiu do
	funil não é sinalizado.
	"""
	if dados.get("status") in STATUS_FORA_DO_FUNIL:
		return False

	return bool(etapas) and not _pendencias_obrigatorias(etapas)


def _pendencias_obrigatorias(etapas: list[dict]) -> set[str]:
	"""Campos das etapas ainda pendentes, sem contar as opcionais."""
	return {etapa["field"] for etapa in etapas if not etapa.get("completed") and not etapa.get("opcional")}


def resumo_etapas(etapas: list[dict]) -> dict:
	"""Consolida o progresso: concluídas, pendentes, atrasadas e a próxima etapa.

	Etapa opcional ainda pendente não conta como pendência nem vira a próxima etapa.
	"""
	concluidas = [etapa for etapa in etapas if etapa.get("completed")]
	pendentes = [etapa for etapa in etapas if not etapa.get("completed") and not etapa.get("opcional")]
	atrasadas = [etapa for etapa in pendentes if etapa.get("is_overdue")]
	proxima = pendentes[0] if pendentes else None

	return {
		"total": len(etapas),
		"concluidas": len(concluidas),
		"pendentes": len(pendentes),
		"atrasadas": len(atrasadas),
		"proxima_etapa": proxima["field"] if proxima else None,
		"proxima_etapa_rotulo": proxima["label"] if proxima else None,
		"etapas_atrasadas": [etapa["field"] for etapa in atrasadas],
	}


def data_da_ultima_visita(nomes: list[str]) -> dict[str, Any]:
	"""Mapa nome do Novo Associado -> registro da visita mais recente."""
	if not nomes:
		return {}

	visitas = frappe.get_all(
		"Agenda de Visitas",
		filters={"jovem": ["in", nomes]},
		fields=["name", "jovem", "data_da_visita", "visita_confirmada"],
		order_by="data_da_visita desc",
	)

	mapa: dict[str, Any] = {}
	for visita in visitas:
		mapa.setdefault(visita.jovem, visita)
	return mapa


# Árvore de prazos de ``Configuracoes de Recepcao``: primeiro o ramo, porque os Filhotes têm
# prazos próprios, depois o tipo de registro, porque cada um tem a sua ordem de etapas.
_DEMAIS_RAMOS: tuple[str, ...] = tuple(ramo for ramo in RAMOS if ramo != RAMO_FILHOTES)
RAMOS_DA_ARVORE: tuple[tuple[str | None, str], ...] = (
	(None, f"{', '.join(_DEMAIS_RAMOS[:-1])} e {_DEMAIS_RAMOS[-1]}"),
	(RAMO_FILHOTES, RAMO_FILHOTES),
)
TIPOS_DA_ARVORE: tuple[tuple[str, str], ...] = (
	("Provisório", "Registro provisório"),
	("Definitivo", "Direto no definitivo"),
)


def _notas_da_etapa(campo: str, ramo: str | None) -> list[dict]:
	"""O que acontece além da data prevista, para a árvore contar o passo a passo inteiro.

	Uma nota com ``campo`` traz ``{dias}`` no texto, trocado na tela pelo valor do campo — ou
	pelo ``padrao``, quando ele está zerado ou vazio.
	"""
	e_filhote = ramo == RAMO_FILHOTES
	notas: list[dict] = []

	if campo == "registro_provisorio_efetivado":
		notas.append(
			{
				"texto": 'Selo "Hora do registro definitivo!" e aviso ao administrativo {dias} depois.',
				"campo": CAMPO_DIAS_REGISTRO_DEFINITIVO_FILHOTES
				if e_filhote
				else CAMPO_DIAS_REGISTRO_DEFINITIVO,
				"padrao": (
					DIAS_PADRAO_REGISTRO_DEFINITIVO_FILHOTES if e_filhote else DIAS_PADRAO_REGISTRO_DEFINITIVO
				),
			}
		)
	elif campo == CAMPO_ID_ESCOTEIROS:
		notas.append(
			{
				"texto": (
					f"Opcional abaixo de {IDADE_ID_ESCOTEIROS_OBRIGATORIO} anos: sem data prevista nem "
					"lembrete, mas o intervalo continua contando para as etapas seguintes."
				)
			}
		)
	elif e_filhote and campo == CAMPO_DADOS_ENVIADOS:
		notas.append({"texto": "Os lembretes de dados à família só começam quando este prazo vence."})
	elif e_filhote and campo == CAMPO_ACOLHIDA:
		notas.append({"texto": "O primeiro aviso de acolhida aos chefes só sai quando este prazo vence."})

	return notas


def estrutura_dos_prazos() -> dict:
	"""Esqueleto da árvore de prazos de ``Configuracoes de Recepcao``.

	Sai das mesmas regras de ``calcular_etapas`` — ``etapas_do_fluxo`` e ``_prazo_da_etapa`` —,
	então a árvore não tem como mostrar uma ordem ou um campo que o funil não segue. As etapas
	sem intervalo (as da visita) ficam de fora: a visita é a raiz, o dia zero.

	Os números também ficam de fora: a tela lê os valores do próprio formulário, para a árvore
	acompanhar a edição antes de salvar. ``campos`` lista todos os campos lidos, na ordem em
	que aparecem, para a tela saber quais edições redesenham a árvore.
	"""
	campos: list[str] = []
	ramos: list[dict] = []

	for ramo, rotulo_do_ramo in RAMOS_DA_ARVORE:
		tipos: list[dict] = []
		for tipo, rotulo_do_tipo in TIPOS_DA_ARVORE:
			etapas: list[dict] = []
			for step in etapas_do_fluxo(tipo):
				prazo = _prazo_da_etapa(step["field"], ramo)
				if not prazo:
					continue

				notas = _notas_da_etapa(step["field"], ramo)
				etapas.append({"field": step["field"], "label": step["label"], **prazo, "notas": notas})
				for item in (prazo, *notas):
					if item.get("campo") and item["campo"] not in campos:
						campos.append(item["campo"])

			tipos.append({"tipo": tipo, "rotulo": rotulo_do_tipo, "etapas": etapas})
		ramos.append({"ramo": ramo, "rotulo": rotulo_do_ramo, "tipos": tipos})

	return {"ramos": ramos, "campos": campos}
