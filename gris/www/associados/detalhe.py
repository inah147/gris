import frappe

from gris.api.portal_access import enrich_context

no_cache = 1


def get_context(context):
	# Permissões iguais à lista de associados (rota '/associados/detalhe')
	if frappe.session.user == "Guest":
		# Sanitiza redirect_to para evitar open redirect
		redirect_path = "/associados/detalhe"
		frappe.local.flags.redirect_location = f"/login?redirect_to={redirect_path}"
		raise frappe.Redirect

	name = frappe.form_dict.get("name")
	context.active_link = "/associados"  # mantém grupo aberto
	enrich_context(context, "/associados/detalhe")

	if not name:
		context.not_found = True
		context.missing_reason = "Parâmetro 'name' não informado."
		return context

	try:
		doc = frappe.get_doc("Associado", name)
	except frappe.DoesNotExistError:
		context.not_found = True
		context.missing_reason = "Associado não encontrado."
		return context
	except Exception as e:  # pragma: no cover
		context.not_found = True
		context.missing_reason = f"Erro ao carregar associado: {e}"
		return context

	# Cabeçalho / Seção 1
	context.head_nome = doc.nome_completo or doc.name
	context.head_registro = doc.registro or "—"
	context.head_tipo_registro = doc.tipo_registro or "—"
	context.head_status = doc.status or "—"
	context.head_validade = (
		frappe.format_value(doc.validade_registro, {"fieldtype": "Date"}) if doc.validade_registro else "—"
	)
	context.head_status_class = _status_badge_class(context.head_status)
	context.head_tipo_registro_class = _tipo_registro_badge_class(context.head_tipo_registro)

	# Configuração de exibição
	meta = frappe.get_meta("Associado")
	df_map = {d.fieldname: d for d in meta.fields}

	# Campos a excluir totalmente
	exclude = {"cpf", "cpf_responsavel_1", "cpf_responsavel_2", "status_no_grupo", "route"}
	# Campos mostrados no cabeçalho
	section1 = {"nome_completo", "tipo_registro", "status", "validade_registro", "registro"}

	is_beneficiario = (doc.categoria or "").strip().lower().startswith("benef")  # cobre Beneficiário
	context.is_beneficiario = is_beneficiario

	# Listas de campos por agrupamento
	personal_fields = ["etnia", "sexo", "data_de_nascimento", "religiao", "estado_civil"]
	contact_fields = ["email", "telefone", "cep_residencia", "numero_residencia", "id_escoteiros"]
	responsaveis_fields = [
		"nome_responsavel_1",
		"telefone_responsavel_1",
		"email_responsavel_1",
		"estado_civil_responsavel_1",
		"nome_responsavel_2",
		"telefone_responsavel_2",
		"email_responsavel_2",
		"estado_civil_responsavel_2",
		"pais_divorciados",
		"tipo_guarda",
		"guardiao_legal_responsavel_1",
		"guardiao_legal_responsavel_2",
	]
	registro_fields = [
		"categoria",
		"ramo",
		"secao",
		"funcao",
		"area",
		"registro",
		"validade_registro",
		"registro_isento",
		"anos_afastamento",
		"eleito",
		"tipo_registro",
		"status",
	]

	# Conjunto de edição permitida
	editable = {
		"guardiao_legal_responsavel_1",
		"guardiao_legal_responsavel_2",
		"anos_afastamento",
		"eleito",
		"tipo_guarda",
		"area",
		"pais_divorciados",
	}

	def build_field(fieldname):
		df = df_map.get(fieldname)
		if not df:
			return None
		if df.fieldtype in {"Section Break", "Column Break", "Tab Break", "Fold"}:
			return None
		if fieldname in exclude or fieldname in section1:
			return None
		value = doc.get(fieldname)
		# Mostrar mesmo nulo
		disp = frappe.format_value(value, df.as_dict()) if value not in (None, "") else ""
		opts = (df.options or "").split("\n") if df.fieldtype == "Select" and df.options else []
		return {
			"fieldname": fieldname,
			"label": df.label or fieldname,
			"value": value if value not in (None,) else "",
			"display": disp,
			"fieldtype": df.fieldtype,
			"options": opts,
			"editable": fieldname in editable,
		}

	def build_group(fnames):
		out = []
		for f in fnames:
			item = build_field(f)
			if item:
				out.append(item)
		return out

	context.group_personal = build_group(personal_fields)
	context.group_contact = build_group(contact_fields)
	context.group_responsaveis = build_group(responsaveis_fields) if is_beneficiario else []
	context.group_registro = build_group(registro_fields)

	# Lógica de guarda / exibição dos toggles de guardião
	pais_div = (doc.pais_divorciados or "").strip() == "Sim"
	tipo_guarda = (doc.tipo_guarda or "").strip()
	context.show_guard_block = is_beneficiario
	# Mostrar campos de guardião somente se pais divorciados E tipo de guarda for exatamente 'Unilateral'
	context.show_guardian_toggles = bool(pais_div and tipo_guarda and tipo_guarda.lower() == "unilateral")

	# Histórico
	historico_rows = []
	has_open_historico = False
	for row in doc.historico_no_grupo or []:
		if not row.data_de_desligamento:
			has_open_historico = True
		historico_rows.append(
			{
				"ingresso": row.data_de_ingresso,
				"desligamento": row.data_de_desligamento,
			}
		)
	context.historico_no_grupo_rows = historico_rows
	context.has_open_historico = has_open_historico
	# Permissão de edição passada ao template sem usar frappe.has_role (não disponível neste contexto)
	try:
		user_roles = set(frappe.get_roles())
	except Exception:
		user_roles = set()
	context.can_edit_member = "Gestor de Associados" in user_roles

	context.associado = doc
	return context


def _status_badge_class(status):
	status = (status or "").lower()
	if status in {"válido", "valido"}:
		return "g-badge--success"
	if status == "vencido":
		return "g-badge--warning"
	return "g-badge--secondary"


def _tipo_registro_badge_class(tipo):
	tipo = (tipo or "").lower()
	if tipo == "definitivo":
		return "g-badge--primary"
	if tipo in {"provisório", "provisorio"}:
		return "g-badge--info"
	return "g-badge--secondary"
