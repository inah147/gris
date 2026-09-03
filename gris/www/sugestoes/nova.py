import frappe
from frappe import _

from gris.api.portal_access import enrich_context, user_has_access
from gris.api.portal_cache_utils import get_uel_cached
from gris.api.sugestoes.constantes import (
	MODULO_NOVO,
	MODULOS,
	TIPO_FUNCIONALIDADE,
	TIPO_PROBLEMA,
)
from gris.utils.contato import telefone_do_usuario

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/sugestoes/nova"
		raise frappe.Redirect

	if not user_has_access("/sugestoes/nova"):
		frappe.throw(_("Você não tem permissão para acessar esta página."), frappe.PermissionError)

	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		if uel_data.get("nome_da_uel"):
			context.sidebar_title = f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
		else:
			context.sidebar_title = "Portal"
	else:
		context.sidebar_title = "Portal"

	context.active_link = "/sugestoes/nova"

	# O aviso de conclusão só pode ser prometido a quem tem telefone no cadastro.
	# Resolver aqui, no servidor, evita um endpoint só para o formulário saber se
	# deve mostrar a opção marcada ou o alerta de cadastro incompleto.
	context.telefone_aviso = telefone_do_usuario(frappe.session.user)
	context.tem_telefone = bool(context.telefone_aviso)

	# A opção vazia à frente evita que o formulário abra com um tipo já
	# escolhido — o macro `select` pré-seleciona o primeiro item sem ela.
	context.tipo_items = [
		{"label": "Selecione", "value": "", "type": "item"},
		{"label": "Relatar um problema", "value": TIPO_PROBLEMA, "type": "item"},
		{"label": "Solicitar uma nova funcionalidade", "value": TIPO_FUNCIONALIDADE, "type": "item"},
	]

	# O JS esconde "Novo módulo" enquanto o tipo for "Problema"; o atributo
	# marca quais opções são exclusivas de funcionalidade.
	context.modulo_items = [
		{"label": "Selecione", "value": "", "type": "item"},
		*[
			{
				"label": modulo,
				"value": modulo,
				"type": "item",
				"attrs": {"data-so-funcionalidade": "1"} if modulo == MODULO_NOVO else {},
			}
			for modulo in MODULOS
		],
	]

	enrich_context(context, "/sugestoes/nova")
	return context
