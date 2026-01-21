import frappe
from frappe import _

from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	# Bloqueio para usuários não autenticados
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/financeiro/extrato"
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

	context.active_link = "/financeiro/extrato"
	enrich_context(context, "/financeiro/extrato")
	context.show_sidebar = True
	context.no_cache = 1
	context.title = _("Detalhe de transação")

	# Adiciona opções de dropdown
	def get_distinct(doctype, field):
		return [
			r[field]
			for r in frappe.get_all(doctype, fields=[field], distinct=True, order_by=field)
			if r[field]
		]

	context.opcoes_categoria = get_distinct("Categoria de Transacao", "name")
	context.opcoes_centro_de_custo = get_distinct("Centro de Custo", "name")
	context.opcoes_conta_fixa = get_distinct("Conta Fixa", "name")

	# Beneficiários: apenas associados com categoria Beneficiário
	context.opcoes_beneficiario = [
		{"name": r["name"], "nome_completo": r.get("nome_completo", r["name"])}
		for r in frappe.get_all(
			"Associado",
			fields=["name", "nome_completo", "categoria"],
			filters={"categoria": "Beneficiário"},
			order_by="nome_completo",
		)
	]

	context.opcoes_fixo_variavel = ["Fixo", "Variável"]
	context.opcoes_ordinaria_extraordinaria = ["Ordinária", "Extraordinária"]

	name = frappe.form_dict.get("name")
	if not name:
		context.not_found = True
		context.missing_reason = "Parâmetro 'name' não informado."
		return context

	try:
		doc = frappe.get_doc("Transacao Extrato Geral", name)
	except frappe.DoesNotExistError:
		context.not_found = True
		context.missing_reason = "Transação não encontrada."
		return context
	except Exception as e:
		context.not_found = True
		context.missing_reason = f"Erro ao carregar transação: {e}"
		return context

	context.doc = doc

	# Filtrar contas fixas já pagas no mês
	if doc.data_transacao:
		from frappe.utils import getdate

		data_t = getdate(doc.data_transacao)
		mes_ref = data_t.replace(day=1)

		# 1. Encontrar pagamentos que já foram realizados (Pago) neste mês
		# ou estão vinculados a outras transações (independente se o pagamento estivesse 'Em Aberto',
		# se já tem transação vinculada, não deve aparecer de novo)

		# Vamos pela abordagem de transações já existentes no mês:
		# Encontrar todas as transações deste mês que têm conta_fixa preenchido
		primeiro_dia = mes_ref
		import calendar
		ultimo_dia = mes_ref.replace(day=calendar.monthrange(mes_ref.year, mes_ref.month)[1])

		used_accounts = frappe.get_all(
			"Transacao Extrato Geral",
			filters={
				"data_transacao": ["between", [primeiro_dia, ultimo_dia]],
				"conta_fixa": ["is", "set"],
				"name": ["!=", doc.name]  # Excluir a própria transação
			},
			pluck="conta_fixa"
		)

		# Remover das opções
		if used_accounts:
			# context.opcoes_conta_fixa é uma lista de strings (names)
			context.opcoes_conta_fixa = [
				op for op in context.opcoes_conta_fixa if op not in used_accounts
			]

	return context
