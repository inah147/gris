import frappe
from frappe.utils import getdate, nowdate

from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1

# Ordem de exibição incluindo novos status "Cadastrar" e "Cancelar"
STATUS_KEYS = ["Cadastrar", "Cancelar", "Aguardar", "Atrasado", "Em Aberto", "Pago"]


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
		inicio = b.get("inicio_do_pagamento")
		inicio_date = getdate(inicio) if inicio else None
		pagamentos = pagamentos_map.get(b["name"], [])
		status_geral = _calcular_status_geral(b, inicio_date, pagamentos, hoje)
		item = {
			"nome": b.get("nome_completo"),
			"id": b.get("name"),
			# manter como string para ser serializável em JSON no template
			"inicio_do_pagamento": inicio_date.isoformat() if inicio_date else None,
			"valor_contribuicao": b.get("valor_contribuicao"),
			"qt_contribuicoes_pagas": b.get("qt_contribuicoes_pagas") or 0,
			"qt_contribuicoes_atrasadas": b.get("qt_contribuicoes_atrasadas") or 0,
			"status_geral": status_geral,
			"pagamentos": pagamentos,
			"status_no_grupo": b.get("status_no_grupo"),
			"status_cobranca": b.get("status_cobranca"),
			"email_cobranca": b.get("email_cobranca"),
			"telefone_cobranca": b.get("telefone_cobranca"),
		}
		# Usa setdefault para evitar KeyError caso apareça status não listado
		agrupado.setdefault(status_geral, []).append(item)

	context.contribuicoes = agrupado
	context.titulo = "Contribuições Mensais"

	enrich_context(context, "/financeiro/contribuicoes")
	return context


def _get_beneficiarios():
	campos = [
		"name",
		"nome_completo",
		"inicio_do_pagamento",
		"valor_contribuicao",
		"qt_contribuicoes_pagas",
		"qt_contribuicoes_atrasadas",
		"status_no_grupo",
		"status_cobranca",
		"email_cobranca",
		"telefone_cobranca",
	]
	# Buscamos Beneficiário ativos e também os Inativos com cobrança ativa (para status 'Cancelar')
	beneficiarios_ativos = frappe.get_all(
		"Associado",
		filters={"status_no_grupo": "Ativo", "categoria": "Beneficiário"},
		fields=campos,
		order_by="nome_completo asc",
	)
	beneficiarios_cancelar = frappe.get_all(
		"Associado",
		filters={
			"status_no_grupo": "Inativo",
			"status_cobranca": "Ativo",
			"categoria": "Beneficiário",
		},
		fields=campos,
		order_by="nome_completo asc",
	)
	# Unimos listas (simples, nomes distintos por naming rule cpf)
	return beneficiarios_ativos + beneficiarios_cancelar


def _get_pagamentos_por_associado(associados):
	if not associados:
		return {}
	pagamentos = frappe.get_all(
		"Pagamento Contribuicao Mensal",
		filters={"associado": ["in", associados]},
		fields=["name", "associado", "mes_de_referencia", "status", "valor"],
		order_by="mes_de_referencia desc",
	)
	mapa = {}
	for p in pagamentos:
		lista = mapa.setdefault(p["associado"], [])
		lista.append(
			{
				"name": p.get("name"),
				# garantir serialização segura
				"mes_de_referencia": (
					p.get("mes_de_referencia").isoformat()
					if getattr(p.get("mes_de_referencia"), "isoformat", None)
					else p.get("mes_de_referencia")
				),
				"status": p.get("status"),
				"valor": (float(p.get("valor")) if p.get("valor") is not None else None),
			}
		)
	return mapa


def _calcular_status_geral(assoc_row, inicio, pagamentos, hoje):
	# Nova regra: Inativo + status_cobranca=Ativo => Cancelar
	if assoc_row.get("status_no_grupo") == "Inativo" and assoc_row.get("status_cobranca") == "Ativo":
		return "Cancelar"
	if (
		assoc_row.get("status_no_grupo") == "Ativo"
		and assoc_row.get("status_cobranca") == "Inativo"
		and inicio <= hoje
	):
		return "Cadastrar"
	qt_atrasadas = assoc_row.get("qt_contribuicoes_atrasadas") or 0
	if inicio and inicio > hoje:
		return "Aguardar"
	if qt_atrasadas > 0:
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
