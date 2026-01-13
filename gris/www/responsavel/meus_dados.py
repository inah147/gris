import json

import frappe

from gris.api.portal_access import enrich_context, user_has_access


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/responsavel/meus_dados"
		raise frappe.Redirect

	if not user_has_access("/responsavel/meus_dados"):
		frappe.throw("Você não tem permissão para acessar esta página.", frappe.PermissionError)

	user = frappe.session.user
	responsavel_name = frappe.db.get_value("Responsavel", {"email": user}, "name")

	if not responsavel_name:
		context.responsavel = None
		frappe.msgprint("Cadastro de responsável não encontrado para este usuário.")
		return context

	responsavel = frappe.get_doc("Responsavel", responsavel_name)
	context.responsavel = responsavel

	roles = frappe.get_roles(user)
	context.is_nova_familia = "Nova Familia" in roles

	if context.is_nova_familia:
		fields_of_interest = [
			{"fieldname": "nome_completo", "label": "Nome Completo"},
			{"fieldname": "email", "label": "E-mail"},
			{"fieldname": "cpf", "label": "CPF"},
			{"fieldname": "celular", "label": "Celular"},
		]

		fields_to_show = []
		for item in fields_of_interest:
			val = responsavel.get(item["fieldname"])
			if val:
				fields_to_show.append({"label": item["label"], "value": val, "fieldtype": "Data"})
		context.fields_to_show = fields_to_show
	else:
		context.nome_completo = responsavel.nome_completo
		context.email = responsavel.email
		context.o_que_gosta = responsavel.o_que_gosta_de_fazer_no_dia_a_dia
		context.habilidades_list = [h.habilidade for h in responsavel.habilidades]

	context.sidebar_title = "Painel do Responsável"
	context.active_link = "/responsavel/meus_dados"
	enrich_context(context, "/responsavel/meus_dados")

	return context


@frappe.whitelist()
def update_meus_dados(o_que_gosta_de_fazer_no_dia_a_dia, habilidades):
	user = frappe.session.user
	responsavel_name = frappe.db.get_value("Responsavel", {"email": user}, "name")
	if not responsavel_name:
		frappe.throw("Responsável não encontrado.")

	doc = frappe.get_doc("Responsavel", responsavel_name)
	doc.o_que_gosta_de_fazer_no_dia_a_dia = o_que_gosta_de_fazer_no_dia_a_dia

	if isinstance(habilidades, str):
		habilidades_list = json.loads(habilidades)
	else:
		habilidades_list = habilidades

	doc.set("habilidades", [])
	for hab in habilidades_list:
		doc.append("habilidades", {"habilidade": hab})

	doc.save()
	return "Dados atualizados com sucesso."
