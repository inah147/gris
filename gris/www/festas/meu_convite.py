"""Página pública /convite/<código> (rota em `hooks.website_route_rules`).

É o link da legenda do PDF que o convidado recebe pelo WhatsApp. Antes de mostrar o
QR, pede os 4 últimos dígitos do telefone que recebeu a mensagem; a conferência e o
QR vêm de `gris.api.festas.convite_publico.abrir_convite`.

O HTML desta página não traz nenhum dado pessoal: só a festa (nome, data e horário).
Código inexistente, pedido não pago, venda presencial e convidado sem telefone
devolvem a mesma página de "não encontrado" de qualquer rota inexistente.
"""

import frappe
from frappe import _

from gris.api.festas.convite_publico import carregar_convite
from gris.api.portal_cache_utils import get_uel_cached
from gris.www.festas.convite_confirmado import _formatar_data, _formatar_horario

no_cache = 1


def get_context(context):
	context.title = "Seu convite"
	context.show_sidebar = False
	context.no_header = True
	context.no_footer = True

	token = (frappe.form_dict.get("token") or "").strip()
	dados = carregar_convite(token)
	if not dados:
		frappe.throw(_("Página indisponível"), frappe.PageDoesNotExistError)

	uel_data = get_uel_cached() or {}
	context.token = token
	context.estado = "expirado" if dados.expirado else "verificar"
	context.festa = {
		"nome": dados.festa.nome_festa or dados.festa.name,
		"data": _formatar_data(dados.festa.data),
		"horario_inicio": _formatar_horario(dados.festa.horario_inicio),
		"horario_termino": _formatar_horario(dados.festa.horario_termino),
	}
	context.portal_logo = uel_data.get("logo")
	context.uel = {
		"tipo_uel": uel_data.get("tipo_uel") or "",
		"nome_da_uel": uel_data.get("nome_da_uel") or "",
		"numeral": uel_data.get("numeral") or "",
		"regiao": uel_data.get("regiao") or "",
	}
	# `noindex` e `no-referrer` também no HTML; os cabeçalhos saem do after_request.
	context.head_html = (
		'<meta name="robots" content="noindex, nofollow"><meta name="referrer" content="no-referrer">'
	)
	return context
