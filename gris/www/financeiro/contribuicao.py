"""Detalhe da contribuição mensal de um associado.

Tela cheia aberta pela lista de `/financeiro/contribuicoes`. A apuração aqui é a
mesma da lista (`gris.api.financeiro.pagamentos_contribuicao`), recortada num
contribuinte só: mês a mês (lido do Pagamento Contribuicao Mensal, editável por
quem gerencia), transações identificadas no período e as ações de gestão
(valor, dados de cobrança e cobrança pela InfinitePay).

O mês a mês e as transações são renderizados no servidor — a tela nasce pronta,
sem depender de JavaScript para mostrar o que já foi apurado. A edição (trocar
status, vincular a transação certa) é que precisa de JavaScript, em
`contribuicao.js`.
"""

import frappe

from gris.api.financeiro.pagamentos_contribuicao import (
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

	# Meses gerados e ainda não pagos (Em Aberto ou Atrasado) — "Não gerado" não
	# entra aqui: sem registro, não há o que cobrar ainda.
	pendentes = [linha for linha in assoc["linhas"] if linha["status"] in ("Em Aberto", "Atrasado")]
	assoc["total_falta"] = round(sum(float(linha["valor"]) for linha in pendentes), 2)
	assoc["pendentes"] = pendentes

	context.assoc = assoc

	transacoes = get_extrato_do_associado(associado, meses)["transacoes"]
	context.transacoes = transacoes
	context.total_transacoes = round(sum(float(t["valor"] or 0) for t in transacoes), 2)

	return context
