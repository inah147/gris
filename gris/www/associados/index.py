import frappe
from frappe import _

from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1

RAMOS_ORDER = [
	"Filhotes",
	"Lobinho",
	"Escoteiro",
	"Sênior",
	"Pioneiro",
	"Não se aplica",
]


def get_context(context):
	# Bloqueio para usuários não autenticados
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect_to=/associados"
		raise frappe.Redirect
	# Logo e título
	uel_data = get_uel_cached()
	context.portal_logo = uel_data.get("logo") if uel_data else None
	context.active_link = "/associados"
	enrich_context(context, "/associados")
	context.ramos_order = RAMOS_ORDER
	return context


@frappe.whitelist()
def get_associados_dashboard():
	"""Retorna estatísticas para cards + dados de gráfico (ativos por ramo e categoria).

	Novas métricas:
	- ativos_total: total de associados com status_no_grupo='Ativo'
	- ativos_beneficiarios: categoria = 'Beneficiário' e ativo
	- ativos_adultos: categorias Escotista + Dirigente (ativos)
	- ativos_outros: ativos - (beneficiarios + adultos)
	- registro_valido: status = 'Válido'
	- registro_vencido: status = 'Vencido'
	- registro_isento: registro_isento = 'Sim'
	Percentuais sempre relativos a ativos_total (evitar divisão por zero).
	"""

	stats_card = frappe.db.sql(
		"""
		SELECT
			SUM(CASE WHEN status_no_grupo='Ativo' THEN 1 ELSE 0 END) AS ativos_total,
			SUM(CASE WHEN status_no_grupo='Ativo' AND categoria='Beneficiário' THEN 1 ELSE 0 END) AS ativos_beneficiarios,
			SUM(CASE WHEN status_no_grupo='Ativo' AND categoria IN ('Escotista','Dirigente') THEN 1 ELSE 0 END) AS ativos_adultos,
			SUM(CASE WHEN status_no_grupo='Ativo' AND status='Válido' THEN 1 ELSE 0 END) AS registro_valido,
			SUM(CASE WHEN status_no_grupo='Ativo' AND status='Vencido' THEN 1 ELSE 0 END) AS registro_vencido,
			SUM(CASE WHEN status_no_grupo='Ativo' AND IFNULL(registro_isento,'Não')='Sim' THEN 1 ELSE 0 END) AS registro_isento
		FROM `tabAssociado`
		""",
		as_dict=True,
	)[0]

	ativos_total = int(stats_card.ativos_total or 0)
	ativos_benef = int(stats_card.ativos_beneficiarios or 0)
	ativos_adultos = int(stats_card.ativos_adultos or 0)
	registro_valido = int(stats_card.registro_valido or 0)
	registro_vencido = int(stats_card.registro_vencido or 0)
	registro_isento = int(stats_card.registro_isento or 0)
	ativos_outros = max(0, ativos_total - (ativos_benef + ativos_adultos))

	def pct(v):
		return round((v / ativos_total) * 100, 1) if ativos_total else 0

	rows = frappe.db.sql(
		"""
		SELECT ramo, categoria, COUNT(*) AS total
		FROM `tabAssociado`
		WHERE status_no_grupo='Ativo'
		GROUP BY ramo, categoria
		""",
		as_dict=True,
	)

	categorias = sorted({r.categoria for r in rows if r.categoria})
	pivot = {cat: [0] * len(RAMOS_ORDER) for cat in categorias}
	index_map = {ramo: i for i, ramo in enumerate(RAMOS_ORDER)}

	for r in rows:
		ramo = r.ramo or "Não se aplica"
		if ramo not in index_map:
			continue
		cat = r.categoria or "(Sem Categoria)"
		if cat not in pivot:
			pivot[cat] = [0] * len(RAMOS_ORDER)
		pivot[cat][index_map[ramo]] = r.total

	datasets = [{"name": cat, "chartType": "bar", "values": pivot[cat]} for cat in pivot]

	return {
		"cards": {
			"ativos": {
				"total": ativos_total,
				"beneficiarios": ativos_benef,
				"adultos": ativos_adultos,
				"outros": ativos_outros,
			},
			"registro_valido": {
				"total": registro_valido,
				"pct": pct(registro_valido),
			},
			"registro_vencido": {
				"total": registro_vencido,
				"pct": pct(registro_vencido),
			},
			"registro_isento": {
				"total": registro_isento,
				"pct": pct(registro_isento),
			},
		},
		"chart": {"labels": RAMOS_ORDER, "datasets": datasets},
	}
