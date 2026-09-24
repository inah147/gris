"""Detalhes de um responsável legal que **não** tem cadastro de associado.

Chega-se aqui pela ficha do jovem, no botão de cada responsável. Quem também é associado é
mandado para `/associados/detalhe`: lá a mesma pessoa já tem registro, histórico, funções e
— desde a unificação — hobbies e habilidades. Duplicar isso aqui só criaria duas telas para
manter iguais.

Sobra, então, exatamente o que existe de um responsável puro: o perfil, os beneficiários
pelos quais ele responde e o lugar dele no organograma (o Conselho de Responsáveis). A
página é só leitura — o nó do conselho é automático e não há o que editar nele.
"""

from urllib.parse import quote

import frappe

from gris.api.gestao_adultos.atribuicoes import (
	listar_areas_com_funcoes,
	listar_funcoes_da_pessoa,
	pode_gerenciar_funcoes,
)
from gris.api.gestao_adultos.identidade import chave_do_responsavel
from gris.api.gestao_adultos.responsaveis import obter_detalhe_do_responsavel
from gris.api.pessoas import associado_do_responsavel
from gris.api.portal_access import enrich_context

no_cache = 1

#: Quem pode abrir a ficha do jovem no funil. Sem o papel, o card do beneficiário em
#: integração aparece sem link em vez de levar a um "acesso negado".
ROLES_DO_FUNIL = ("Recepcao", "System Manager")


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/associados/responsavel"
		raise frappe.Redirect

	name = frappe.form_dict.get("name")
	context.active_link = "/associados"  # mantém o grupo de Associados aberto na sidebar
	enrich_context(context, "/associados/responsavel")

	if context.access_denied:
		return context

	if not name:
		context.not_found = True
		context.missing_reason = "Parâmetro 'name' não informado."
		return context

	try:
		doc = frappe.get_doc("Responsavel", name)
	except frappe.DoesNotExistError:
		context.not_found = True
		context.missing_reason = "Responsável não encontrado."
		return context

	# A pessoa tem cadastro de associado: a ficha completa é a dela.
	associado = associado_do_responsavel(name)
	if associado:
		frappe.local.flags.redirect_location = f"/associados/detalhe?name={quote(associado)}"
		raise frappe.Redirect

	context.responsavel = doc
	context.head_nome = doc.nome_completo or doc.name

	context.hobbies_texto = (doc.o_que_gosta_de_fazer_no_dia_a_dia or "").strip()
	context.habilidades_list = [linha.habilidade for linha in (doc.habilidades or [])]

	context.beneficiarios = _beneficiarios(name, set(frappe.get_roles()))

	# O painel do organograma já sabe montar a função fixa do conselho e o contato atrás da
	# permissão de gestão; reaproveitar evita duas versões da mesma regra.
	detalhe = obter_detalhe_do_responsavel(name)
	context.iniciais = detalhe["iniciais"]
	context.whatsapp = detalhe["whatsapp"]
	context.funcoes = detalhe["funcoes"]

	# Alocar função é permissão própria, separada de abrir a página: quem administra o
	# organograma edita a grade; o resto vê a lista pronta. Mesma divisão da ficha do
	# associado.
	context.pode_gerenciar_funcoes = pode_gerenciar_funcoes()
	if context.pode_gerenciar_funcoes:
		context.areas_com_funcoes = listar_areas_com_funcoes()
		context.funcoes_internas_rows = listar_funcoes_da_pessoa(chave_do_responsavel(name))
	else:
		context.areas_com_funcoes = []
		context.funcoes_internas_rows = []

	return context


def _beneficiarios(responsavel_name: str, user_roles: set) -> list[dict]:
	"""Beneficiários do responsável, já registrados ou ainda em integração.

	O vínculo aponta para um dos dois cadastros: `Associado` para quem já terminou a
	recepção e `Novo Associado` para quem ainda está no funil. Os dois entram na lista —
	quem responde por um jovem responde por ele antes e depois do registro.
	"""
	vinculos = frappe.get_all(
		"Responsavel Vinculo",
		filters={"responsavel": responsavel_name},
		fields=[
			"beneficiario_associado",
			"beneficiario_novo_associado",
			"é_guardiao_legal",
			"sera_registrado",
			"primeiro_responsavel",
			"tipo_guarda",
		],
		order_by="primeiro_responsavel desc, creation asc",
	)

	pode_ver_funil = bool(user_roles.intersection(ROLES_DO_FUNIL))
	beneficiarios = []

	for vinculo in vinculos:
		if vinculo.beneficiario_associado:
			nome = frappe.db.get_value("Associado", vinculo.beneficiario_associado, "nome_completo")
			item = {
				"nome": nome or vinculo.beneficiario_associado,
				"situacao": "Associado",
				"url": f"/associados/detalhe?name={quote(vinculo.beneficiario_associado)}",
			}
		elif vinculo.beneficiario_novo_associado:
			nome = frappe.db.get_value("Novo Associado", vinculo.beneficiario_novo_associado, "nome_completo")
			item = {
				"nome": nome or vinculo.beneficiario_novo_associado,
				"situacao": "Em integração",
				"url": (
					f"/recepcao/ficha_registro?name={quote(vinculo.beneficiario_novo_associado)}"
					if pode_ver_funil
					else None
				),
			}
		else:
			# Vínculo órfão: o jovem saiu do funil sem virar associado.
			continue

		item["guardiao_legal"] = bool(vinculo.get("é_guardiao_legal"))
		item["primeiro"] = bool(vinculo.get("primeiro_responsavel"))
		item["sera_registrado"] = bool(vinculo.get("sera_registrado"))
		item["tipo_guarda"] = (vinculo.get("tipo_guarda") or "").strip().lstrip("-")
		beneficiarios.append(item)

	return beneficiarios
