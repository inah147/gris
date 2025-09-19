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
		frappe.local.flags.redirect_location = "/login?redirect_to=/associados/dashboard"
		raise frappe.Redirect
	# Logo e título
	uel_data = get_uel_cached()
	context.portal_logo = uel_data.get("logo") if uel_data else None
	context.active_link = "/associados/dashboard"
	enrich_context(context, "/associados/dashboard")
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

		# --- Gráfico 3: Série temporal de ativos (últimos 12 meses) ---
		# Usa doctype "Metrica Mensal de Associados" (campos mes_referencia, qt_ativos_uel)
		# Considera os últimos 12 meses incluindo o mês atual; se faltarem meses, completa com 0.

		monthly_labels = []
		monthly_values = []
		monthly_novos_values = []
		monthly_evasao_values = []
		monthly_evasao_rate_values = []
		try:
			# Recupera registros ordenados por mes_referencia asc dos últimos 12 meses
			rows_monthly = frappe.db.sql(
				"""
					SELECT mes_referencia, qt_ativos_uel, qt_novos, qt_evasao
					FROM `tabMetrica Mensal de Associados`
					WHERE mes_referencia >= DATE_SUB(DATE_FORMAT(CURDATE(), '%Y-%m-01'), INTERVAL 11 MONTH)
					ORDER BY mes_referencia ASC
				""",
				as_dict=True,
			)
			# Mapa por AAAA-MM
			# Monta sequência contínua de 12 meses
			today = frappe.utils.getdate()
			start_month = frappe.utils.add_months(frappe.utils.getdate(f"{today.year}-{today.month}-01"), -11)
			month_cursor = start_month
			rows_map_ativos = {}
			rows_map_novos = {}
			rows_map_evasao = {}
			for r in rows_monthly:
				if not r.mes_referencia:
					continue
				key = r.mes_referencia.strftime("%Y-%m")
				rows_map_ativos[key] = int(r.qt_ativos_uel or 0)
				rows_map_novos[key] = int(r.qt_novos or 0)
				rows_map_evasao[key] = int(r.qt_evasao or 0)
			PT_BR_MONTHS = [
				"jan",
				"fev",
				"mar",
				"abr",
				"mai",
				"jun",
				"jul",
				"ago",
				"set",
				"out",
				"nov",
				"dez",
			]
			for _i in range(12):
				key = month_cursor.strftime("%Y-%m")
				val_ativos = rows_map_ativos.get(key, 0)
				val_novos = rows_map_novos.get(key, 0)
				val_evasao = rows_map_evasao.get(key, 0)
				base = val_ativos + val_evasao
				rate = round((val_evasao / base) * 100, 2) if base else 0
				label = f"{PT_BR_MONTHS[month_cursor.month - 1]} {month_cursor.year}"
				monthly_labels.append(label)
				monthly_values.append(val_ativos)
				monthly_novos_values.append(val_novos)
				monthly_evasao_values.append(val_evasao)
				monthly_evasao_rate_values.append(rate)
				month_cursor = frappe.utils.add_months(month_cursor, 1)
		except Exception:
			# Em caso de erro (doctype inexistente, etc.), retorna vazio
			monthly_labels = []
			monthly_values = []
			monthly_novos_values = []
			monthly_evasao_values = []
			monthly_evasao_rate_values = []

		chart_ativos_mensal = None
		chart_novos_mensal = None
		chart_evasao_mensal = None
		if monthly_labels:
			chart_ativos_mensal = {
				"labels": monthly_labels,
				"datasets": [{"name": _("Ativos"), "chartType": "line", "values": monthly_values}],
			}
			chart_novos_mensal = {
				"labels": monthly_labels,
				"datasets": [{"name": _("Novos"), "chartType": "bar", "values": monthly_novos_values}],
			}
			chart_evasao_mensal = {
				"labels": monthly_labels,
				"datasets": [
					{"name": _("Evasão"), "chartType": "bar", "values": monthly_evasao_values},
					{"name": _("Taxa Evasão (%)"), "chartType": "line", "values": monthly_evasao_rate_values},
				],
			}

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
		"chart_ativos_mensal": chart_ativos_mensal,
		"chart_novos_mensal": locals().get("chart_novos_mensal"),
		"chart_evasao_mensal": locals().get("chart_evasao_mensal"),
	}
