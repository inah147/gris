import frappe

from gris.api.portal_access import enrich_context, user_has_access


def _get_responsavel_name(user):
	if not user or user == "Guest":
		return None

	responsavel_name = frappe.db.get_value("Responsavel", {"email": user}, "name")
	if responsavel_name:
		return responsavel_name

	associado_name = frappe.db.get_value("Associado", {"id_escoteiros": user}, "name")
	if not associado_name:
		return None

	associado_cpf_hash = frappe.db.get_value("Associado", associado_name, "cpf")
	if associado_cpf_hash and frappe.db.exists("Responsavel", associado_cpf_hash):
		return associado_cpf_hash

	return frappe.db.get_value(
		"Responsavel Vinculo", {"beneficiario_associado": associado_name}, "responsavel"
	)


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/responsavel/pesquisa_novos"
		raise frappe.Redirect

	if not user_has_access("/responsavel/pesquisa_novos"):
		frappe.local.flags.redirect_location = "/responsavel"
		raise frappe.Redirect

	user = frappe.session.user
	responsavel_name = _get_responsavel_name(user)

	if not responsavel_name:
		frappe.throw("Responsável não encontrado para este usuário.")

	# Check if survey already exists
	survey_name = frappe.db.exists("Pesqusa de Novos Associados", {"responsavel": responsavel_name})

	context.is_read_only = False
	context.survey = {}

	if survey_name:
		context.is_read_only = True
		context.survey = frappe.get_doc("Pesqusa de Novos Associados", survey_name).as_dict()

	context.sidebar_title = "Painel do Responsável"
	context.active_link = "/responsavel/pesquisa_novos"
	enrich_context(context, "/responsavel/pesquisa_novos")

	return context


@frappe.whitelist()
def submit_survey(data):
	if frappe.session.user == "Guest":
		frappe.throw("Não autorizado")

	if not user_has_access("/responsavel/pesquisa_novos"):
		frappe.throw(
			"Pesquisa disponível apenas para responsáveis com beneficiários em processo de integração.",
			frappe.PermissionError,
		)

	user = frappe.session.user
	responsavel_name = _get_responsavel_name(user)

	if not responsavel_name:
		frappe.throw("Responsável não encontrado.")

	# Check if already exists
	if frappe.db.exists("Pesqusa de Novos Associados", {"responsavel": responsavel_name}):
		frappe.throw("Pesquisa já respondida.")

	import json

	form_data = json.loads(data)

	doc = frappe.get_doc(
		{
			"doctype": "Pesqusa de Novos Associados",
			"responsavel": responsavel_name,
			"como_conheceu_movimento": form_data.get("como_conheceu_movimento"),
			"como_você_conheceu_o_nosso_grupo_escoteiro": form_data.get("como_voce_conheceu_grupo"),
			"visao_sobre_movimento": form_data.get("visao_sobre_movimento"),
			"espera_encontrar_movimento": form_data.get("espera_encontrar_movimento"),
			"chamou_atencao_uel": form_data.get("chamou_atencao_uel"),
			"nps_recepcao": form_data.get("nps_recepcao"),
			"pontos_fortes_recepcao": form_data.get("pontos_fortes_recepcao"),
			"melhoria_recepcao": form_data.get("melhoria_recepcao"),
			"data_resposta": frappe.utils.nowdate(),
		}
	)

	doc.insert(ignore_permissions=True)

	# Update Novo Associado flag if needed (optional, based on beneficiarios.py logic)
	# Find linked Novo Associado(s) and update 'pesquisa_de_novos_associados_respondida'
	vinculos = frappe.get_all(
		"Responsavel Vinculo",
		filters={"responsavel": responsavel_name},
		fields=["beneficiario_novo_associado"],
	)
	for v in vinculos:
		if v.beneficiario_novo_associado:
			frappe.db.set_value(
				"Novo Associado", v.beneficiario_novo_associado, "pesquisa_de_novos_associados_respondida", 1
			)

	return "Pesquisa enviada com sucesso!"
