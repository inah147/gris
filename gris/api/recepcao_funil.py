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
from frappe.utils import add_days, format_date, getdate

DOCTYPE = "Novo Associado"

# Ramos na ordem crescente de idade, como aparecem no Select de ``Novo Associado``.
# Ordem canônica para qualquer listagem por ramo do fluxo de recepção.
RAMOS: tuple[str, ...] = ("Filhotes", "Lobinho", "Escoteiro", "Sênior", "Pioneiro")

STEPS_DEF: list[dict[str, Any]] = [
	{"field": "visita_agendada", "label": "Visita Agendada"},
	{"field": "primeira_visita_realizada", "label": "Primeira Visita Realizada"},
	{"field": "dados_para_registro_enviados", "label": "Dados Enviados"},
	{"field": "registro_criado_no_paxtu", "label": "Registro no Paxtu"},
	{
		"field": "registro_provisorio_efetivado",
		"label": "Registro Provisório Efetivado",
		"conditional": True,
	},
	{"field": "pesquisa_de_novos_associados_respondida", "label": "Pesquisa Respondida"},
	{"field": "ficha_medica_preenchida", "label": "Ficha Médica"},
	{"field": "id_escoteiros_criado", "label": "ID Escoteiros Criado"},
	{"field": "registro_definitivo_efetivado", "label": "Registro Definitivo Efetivado"},
	{"field": "reuniao_de_acolhida_realizada", "label": "Reunião de Acolhida"},
]

# Campo da etapa -> campo de intervalo (em dias) nas Configuracoes de Recepcao.
FIELD_INTERVAL_MAP: dict[str, str] = {
	"dados_para_registro_enviados": "dados_para_registro_enviados",
	"registro_criado_no_paxtu": "registro_criado_no_paxtu",
	"registro_provisorio_efetivado": "registro_provisorio_efetivado",
	"pesquisa_de_novos_associados_respondida": "pesquisa_de_novos_associados_respondida",
	"ficha_medica_preenchida": "ficha_medica_preenchida",
	"id_escoteiros_criado": "id_escoteiros_criado",
	"registro_definitivo_efetivado": "registro_definitivo_efetivado",
	"reuniao_de_acolhida_realizada": "reuniao_de_acolhida_realizada",
}

CAMPOS_DE_ETAPA: tuple[str, ...] = tuple(step["field"] for step in STEPS_DEF)

# Etapas que efetivam o registro do jovem. As duas exigem o número de registro do
# jovem (e dos responsáveis que serão registrados) antes de serem marcadas — ver
# ``gris.www.recepcao.visao_geral.update_step_status``.
CAMPOS_DE_EFETIVACAO: tuple[str, ...] = (
	"registro_provisorio_efetivado",
	"registro_definitivo_efetivado",
)

# A coluna "Acompanhamento" do kanban é dividida em duas listas. A separação é
# derivada dos dados, não gravada em ``status``: quem ainda espera o registro
# provisório fica na lista provisória e migra sozinho para a definitiva assim que
# ``registro_provisorio_efetivado`` é marcado. Quem já entrou como Definitivo
# nunca passa pela lista provisória.
STATUS_ACOMPANHAMENTO = "Acompanhamento"
COLUNA_ACOMPANHAMENTO_PROVISORIO = "Acompanhamento Provisório"
COLUNA_ACOMPANHAMENTO_DEFINITIVO = "Acompanhamento Definitivo"
COLUNAS_DE_ACOMPANHAMENTO = (
	COLUNA_ACOMPANHAMENTO_PROVISORIO,
	COLUNA_ACOMPANHAMENTO_DEFINITIVO,
)


def coluna_de_acompanhamento(dados) -> str:
	"""Qual das duas listas de acompanhamento recebe o card.

	Mesma condição de ``calcular_etapas``: só quem não é "Definitivo" enxerga a
	etapa do registro provisório, então só esse grupo pode ficar na lista provisória
	— e sai dela quando a etapa é concluída.
	"""
	e_definitivo = dados.get("tipo_de_registro") == "Definitivo"
	if not e_definitivo and not dados.get("registro_provisorio_efetivado"):
		return COLUNA_ACOMPANHAMENTO_PROVISORIO
	return COLUNA_ACOMPANHAMENTO_DEFINITIVO


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


def calcular_etapas(dados, config: dict | None = None, data_base=None, hoje=None) -> list[dict]:
	"""Etapas de uma pessoa, com data estimada e marcação de atraso.

	``dados`` precisa conter ``tipo_de_registro`` e os campos de etapa.
	``data_base`` é a data da visita mais recente (None desliga as estimativas).

	As chaves ``label``/``completed``/``field``/``estimated_date``/``is_overdue``
	são consumidas pelo JavaScript do kanban da recepção; ``data_estimada``
	(ISO) existe para consumo programático.
	"""
	config = config if config is not None else carregar_configuracao()
	hoje = getdate(hoje) if hoje else getdate()
	is_definitivo = dados.get("tipo_de_registro") == "Definitivo"

	etapas: list[dict] = []
	data_corrente = getdate(data_base) if data_base else None

	for step in STEPS_DEF:
		if step.get("conditional") and is_definitivo:
			continue

		concluida = bool(dados.get(step["field"]))
		etapa = {"label": step["label"], "completed": concluida, "field": step["field"]}

		if data_corrente:
			campo_config = FIELD_INTERVAL_MAP.get(step["field"])
			if campo_config:
				try:
					dias = int(config.get(campo_config) or 0)
				except (ValueError, TypeError):
					dias = None
				if dias is not None:
					data_corrente = getdate(add_days(data_corrente, dias))
					if not concluida:
						etapa["estimated_date"] = format_date(data_corrente)
						etapa["data_estimada"] = data_corrente.isoformat()
						if data_corrente < hoje:
							etapa["is_overdue"] = True

		etapas.append(etapa)

	return etapas


def resumo_etapas(etapas: list[dict]) -> dict:
	"""Consolida o progresso: concluídas, pendentes, atrasadas e a próxima etapa."""
	concluidas = [etapa for etapa in etapas if etapa.get("completed")]
	pendentes = [etapa for etapa in etapas if not etapa.get("completed")]
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
