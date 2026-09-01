"""Detalhe da contribuição mensal de um associado.

Tela cheia aberta pela lista de `/financeiro/contribuicoes`. A apuração aqui é a
mesma da lista (`gris.api.financeiro.contribuicoes`), recortada num contribuinte
só: mês a mês, transações identificadas no período e as ações de gestão
(valor, dados de cobrança e cobrança pela InfinitePay).

O mês a mês e as transações são renderizados no servidor — a tela nasce pronta,
sem depender de JavaScript para mostrar o que já foi apurado.
"""

import frappe

from gris.api.financeiro.contribuicoes import (
	MESES_PADRAO,
	ROLE_GESTOR,
	apurar_associados,
	get_extrato_do_associado,
	normalizar_meses,
)
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1

ROTA = "/financeiro/contribuicao"
ROTA_LISTA = "/financeiro/contribuicoes"

# Mesmas janelas de apuração da lista: trocar o período aqui não pode mudar a
# régua com que os números foram calculados lá.
OPCOES_PERIODO = [
	{"label": "Últimos 6 meses", "value": "6"},
	{"label": "Últimos 12 meses", "value": "12"},
	{"label": "Últimos 24 meses", "value": "24"},
]


def get_context(context):
	# A sidebar continua destacando a lista: o detalhe é um passo dentro dela.
	context.active_link = ROTA_LISTA
	enrich_context(context, ROTA)

	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = f"/login?redirect-to={ROTA_LISTA}"
		raise frappe.Redirect

	# Usuário autenticado sem uma das roles de PAGE_ROLES: 403 em vez de voltar
	# ao login, que só produziria um laço de redirecionamento.
	if context.access_denied:
		frappe.local.flags.redirect_location = "/403"
		raise frappe.Redirect

	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		if uel_data.get("nome_da_uel"):
			context.sidebar_title = f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
		else:
			context.sidebar_title = "Portal"
	else:
		context.sidebar_title = "Portal"

	context.titulo = "Contribuição do associado"
	context.can_manage_contributions = ROLE_GESTOR in frappe.get_roles()

	meses = normalizar_meses(frappe.form_dict.get("meses") or MESES_PADRAO)
	context.meses_selecionado = str(meses)
	context.opcoes_periodo = OPCOES_PERIODO
	# O período volta com o usuário para a lista: ele saiu de lá com essa janela.
	context.voltar_url = f"{ROTA_LISTA}?meses={meses}"

	associado = (frappe.form_dict.get("associado") or "").strip()
	context.associado_id = associado
	if not associado:
		context.not_found = True
		context.missing_reason = "Parâmetro 'associado' não informado."
		return context

	# Dados de cobrança e pendência de cadastro só entram para quem pode geri-los.
	apuracoes = apurar_associados([associado], meses, incluir_gestao=context.can_manage_contributions)
	if not apuracoes:
		context.not_found = True
		context.missing_reason = (
			"Associado não encontrado entre os contribuintes da contribuição mensal. "
			"Escotistas e Dirigentes não contribuem."
		)
		return context

	assoc = apuracoes[0]

	# O que falta é a soma dos meses ainda não quitados — inclui a diferença do
	# mês parcial, não só o mês que ninguém pagou.
	pendentes = [linha for linha in assoc["linhas"] if float(linha["falta"] or 0) > 0]
	assoc["total_falta"] = round(sum(float(linha["falta"]) for linha in pendentes), 2)
	assoc["meses_pendentes"] = len(pendentes)
	# Lista os meses em aberto na própria métrica — "5 meses a quitar" sozinho
	# não diz quais, e é justo isso que quem cobra precisa saber de cara.
	assoc["pendentes"] = pendentes
	# A linha do valor de atraso só interessa quando ele é maior que o valor em dia.
	assoc["mostrar_valor_atraso"] = float(assoc["valor_em_atraso"]) > float(assoc["esperado_mensal"])

	context.assoc = assoc

	transacoes = get_extrato_do_associado(associado, meses)["transacoes"]
	context.transacoes = transacoes
	context.total_transacoes = round(sum(float(t["valor"] or 0) for t in transacoes), 2)

	return context
