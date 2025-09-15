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

	# --- Filtros dinâmicos ---
	# Buscar valores distintos presentes na base (apenas associados ativos para coerência)
	# Nota: campos funcao e secao são Data (texto livre); removemos vazios e ordenamos alfabeticamente.
	# Para Select (categoria, ramo) usamos valores distintos existentes para refletir a realidade.
	rows = frappe.db.sql(
		"""
		SELECT DISTINCT
			NULLIF(ramo,'') AS ramo,
			NULLIF(categoria,'') AS categoria,
			NULLIF(secao,'') AS secao,
			NULLIF(funcao,'') AS funcao
		FROM `tabAssociado`
		WHERE status_no_grupo='Ativo'
		""",
		as_dict=True,
	)

	def collect(key):
		vals = sorted({r.get(key) for r in rows if r.get(key)})
		return vals

	context.filter_ramos = [r for r in RAMOS_ORDER if r != "Não se aplica" and r in collect("ramo")] + (
		["Não se aplica"] if "Não se aplica" in collect("ramo") else []
	)
	context.filter_categorias = collect("categoria")
	context.filter_secoes = collect("secao")
	context.filter_funcoes = collect("funcao")

	return context


@frappe.whitelist()
def get_associados_dashboard(categoria=None, ramo=None, secao=None, funcao=None):
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

	filters = ["status_no_grupo='Ativo'"]
	params = {}
	if categoria:
		filters.append("categoria=%(categoria)s")
		params["categoria"] = categoria
	if ramo:
		filters.append("ramo=%(ramo)s")
		params["ramo"] = ramo
	if secao:
		filters.append("secao=%(secao)s")
		params["secao"] = secao
	if funcao:
		filters.append("funcao=%(funcao)s")
		params["funcao"] = funcao
	where_clause = " AND ".join(filters)

	stats_card = frappe.db.sql(
		f"""
		SELECT
			SUM(CASE WHEN status_no_grupo='Ativo' THEN 1 ELSE 0 END) AS ativos_total,
			SUM(CASE WHEN status_no_grupo='Ativo' AND categoria='Beneficiário' THEN 1 ELSE 0 END) AS ativos_beneficiarios,
			SUM(CASE WHEN status_no_grupo='Ativo' AND categoria IN ('Escotista','Dirigente') THEN 1 ELSE 0 END) AS ativos_adultos,
			SUM(CASE WHEN status_no_grupo='Ativo' AND status='Válido' THEN 1 ELSE 0 END) AS registro_valido,
			SUM(CASE WHEN status_no_grupo='Ativo' AND status='Vencido' THEN 1 ELSE 0 END) AS registro_vencido,
			SUM(CASE WHEN status_no_grupo='Ativo' AND IFNULL(registro_isento,'Não')='Sim' THEN 1 ELSE 0 END) AS registro_isento,
			SUM(CASE WHEN status_no_grupo='Ativo' AND tipo_registro='Provisório' THEN 1 ELSE 0 END) AS registro_provisorio
		FROM `tabAssociado`
		WHERE {where_clause}
		""",
		params,
		as_dict=True,
	)[0]

	ativos_total = int(stats_card.ativos_total or 0)
	ativos_benef = int(stats_card.ativos_beneficiarios or 0)
	ativos_adultos = int(stats_card.ativos_adultos or 0)
	registro_valido = int(stats_card.registro_valido or 0)
	registro_vencido = int(stats_card.registro_vencido or 0)
	registro_isento = int(stats_card.registro_isento or 0)
	registro_provisorio = int(stats_card.registro_provisorio or 0)
	ativos_outros = max(0, ativos_total - (ativos_benef + ativos_adultos))

	def pct(v):
		return round((v / ativos_total) * 100, 1) if ativos_total else 0

	rows = frappe.db.sql(
		f"""
		SELECT ramo, categoria, COUNT(*) AS total
		FROM `tabAssociado`
		WHERE {where_clause}
		GROUP BY ramo, categoria
		""",
		params,
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

	# --- Gráfico 2: Vencimentos próximos (próximos 6 meses incluindo mês atual) ---

	# Gerar lista de meses (AAAAMM) e labels (MMM/YY) usando SQL NOW() para consistência
	months_info = frappe.db.sql(
		"""
		SELECT
			DATE_FORMAT(DATE_ADD(DATE_FORMAT(NOW(), '%Y-%m-01'), INTERVAL seq MONTH), '%Y-%m-01') AS first_day,
			DATE_FORMAT(DATE_ADD(DATE_FORMAT(NOW(), '%Y-%m-01'), INTERVAL seq MONTH), '%Y%m') AS yyyymm,
			DATE_FORMAT(DATE_ADD(DATE_FORMAT(NOW(), '%Y-%m-01'), INTERVAL seq MONTH), '%m/%y') AS label
		FROM (
			SELECT 0 AS seq UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5
		) AS m
	""",
		as_dict=True,
	)

	month_order = [m.yyyymm for m in months_info]
	month_labels = [m.label for m in months_info]

	# Construir lista literal (seguro porque gerado internamente) 'YYYYMM'
	months_in = ", ".join([f"'{m}'" for m in month_order])
	venc_rows = frappe.db.sql(
		f"""
		SELECT DATE_FORMAT(validade_registro,'%%Y%%m') AS yyyymm, tipo_registro, COUNT(*) AS total
		FROM `tabAssociado`
		WHERE {where_clause}
			AND validade_registro IS NOT NULL
			AND DATE_FORMAT(validade_registro,'%%Y%%m') IN ({months_in})
		GROUP BY yyyymm, tipo_registro
		""",
		params,
		as_dict=True,
	)

	# Agrupar por tipo_registro
	tipos = sorted({r.tipo_registro for r in venc_rows if r.tipo_registro})
	if not tipos:
		# garantir ao menos um dataset vazio consistente
		venc_datasets = []
	else:
		venc_map = {t: [0] * len(month_order) for t in tipos}
		index_month = {m: i for i, m in enumerate(month_order)}
		for r in venc_rows:
			if r.tipo_registro in venc_map and r.yyyymm in index_month:
				venc_map[r.tipo_registro][index_month[r.yyyymm]] = r.total
		venc_datasets = [{"name": t, "chartType": "bar", "values": venc_map[t]} for t in tipos]

	return {
		"cards": {
			"ativos": {
				"total": ativos_total,
				"beneficiarios": ativos_benef,
				"adultos": ativos_adultos,
				"outros": ativos_outros,
			},
			"registro_valido": {"total": registro_valido, "pct": pct(registro_valido)},
			"registro_vencido": {"total": registro_vencido, "pct": pct(registro_vencido)},
			"registro_isento": {"total": registro_isento, "pct": pct(registro_isento)},
			"registro_provisorio": {"total": registro_provisorio, "pct": pct(registro_provisorio)},
		},
		"chart": {"labels": RAMOS_ORDER, "datasets": datasets},
		"chart_vencimentos": {"labels": month_labels, "datasets": venc_datasets},
	}
