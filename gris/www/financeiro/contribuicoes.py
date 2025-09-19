import frappe
from frappe.utils import getdate, nowdate

from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1

STATUS_KEYS = ["Aguardar", "Atrasado", "Em Aberto", "Pago"]


def get_context(context):
	# Bloqueio para usuários não autenticados
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect_to=/financeiro/contribuicoes"
		raise frappe.Redirect

	# Recupera logo e define para sidebar
	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		if uel_data.get("nome_da_uel"):
			context.sidebar_title = f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
		else:
			context.sidebar_title = "Portal"
	else:
		context.sidebar_title = "Portal"

	context.active_link = "/financeiro/contribuicoes"

	# Dados de contribuições
	beneficiarios = _get_beneficiarios()
	pagamentos_map = _get_pagamentos_por_associado([b["name"] for b in beneficiarios])
	agrupado = {k: [] for k in STATUS_KEYS}
	hoje = getdate(nowdate())

	for b in beneficiarios:
		inicio = b.get("início_do_pagamento") or b.get("in\u00edcio_do_pagamento")
		inicio_date = getdate(inicio) if inicio else None
		pagamentos = pagamentos_map.get(b["name"], [])
		status_geral = _calcular_status_geral(
			inicio_date, b.get("qt_contribuicoes_atrasadas") or 0, pagamentos, hoje
		)
		item = {
			"nome": b.get("nome_completo"),
			"id": b.get("name"),
			"inicio_do_pagamento": inicio_date,
			"valor_contribuicao": b.get("valor_contribuicao"),
			"qt_contribuicoes_pagas": b.get("qt_contribuicoes_pagas") or 0,
			"qt_contribuicoes_atrasadas": b.get("qt_contribuicoes_atrasadas") or 0,
			"status_geral": status_geral,
			"pagamentos": pagamentos,
		}
		agrupado[status_geral].append(item)

	context.contribuicoes = agrupado
	context.titulo = "Contribuições Mensais"

	enrich_context(context, "/financeiro/contribuicoes")
	return context


def _get_beneficiarios():
	campos = [
		"name",
		"nome_completo",
		"`início_do_pagamento`",
		"valor_contribuicao",
		"qt_contribuicoes_pagas",
		"qt_contribuicoes_atrasadas",
	]
	beneficiarios = frappe.get_all(
		"Associado",
		filters={
			"status_no_grupo": "Ativo",
			"categoria": "Beneficiário",
		},
		fields=campos,
		order_by="nome_completo asc",
	)
	return beneficiarios


def _get_pagamentos_por_associado(associados):
	if not associados:
		return {}
	pagamentos = frappe.get_all(
		"Pagamento Contribuicao Mensal",
		filters={"associado": ["in", associados]},
		fields=["name", "associado", "mês_de_referência", "status"],
		order_by="`mês_de_referência` desc",
	)
	mapa = {}
	for p in pagamentos:
		lista = mapa.setdefault(p["associado"], [])
		lista.append(
			{
				"mes_de_referencia": p.get("mês_de_referência"),
				"status": p.get("status"),
			}
		)
	return mapa


def _calcular_status_geral(inicio, qt_atrasadas, pagamentos, hoje):
	if inicio and inicio > hoje:
		return "Aguardar"
	if (qt_atrasadas or 0) > 0:
		return "Atrasado"
	for p in pagamentos:
		if p.get("status") == "Em Aberto":
			return "Em Aberto"
	return "Pago"


# Melhorias futuras sugeridas:
# - Criar endpoint separado (whitelisted) que retorne JSON para permitir front 100% dinâmico.
# - Aplicar cache curto (ex: 5 min) para evitar múltiplas queries pesadas.
# - Suporte a filtros (ramo, seção) via query params.
# - Paginação quando nº de associados crescer.
