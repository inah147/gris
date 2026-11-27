import frappe

from gris.api.assembleias import constantes as c
from gris.api.assembleias.endpoints import dados_das_configuracoes
from gris.api.assembleias.permissoes import pode_gerenciar_assembleias
from gris.api.assembleias.textos import VARIAVEIS
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1

ROTA = "/administracao/assembleias/configuracoes"

PRAZOS = (
	("mesa", "Mesa (presidente e secretário)"),
	("diretoria", "Chapas da diretoria"),
	("comissao_fiscal", "Comissão fiscal"),
	("delegado", "Delegados para a Assembleia Regional"),
	("assuntos_gerais", "Assuntos gerais"),
)


def _grupos_do_whatsapp(atual: str) -> tuple[list[dict], str]:
	"""Opções do grupo da Diretoria. Com o WhatsApp fora do ar, a página abre mesmo assim."""
	from gris.gris.doctype.configuracoes_de_assembleias.configuracoes_de_assembleias import (
		grupos_para_select,
	)

	resposta = grupos_para_select()
	itens = [{"label": "Nenhum grupo", "value": ""}]
	valores = set()
	for grupo in resposta.get("grupos") or []:
		if grupo.get("value") and grupo["value"] not in valores:
			valores.add(grupo["value"])
			itens.append({"label": grupo.get("label") or grupo["value"], "value": grupo["value"]})
	if atual and atual not in valores:
		itens.append({"label": f"{atual} (selecionado anteriormente)", "value": atual})
	erro = ""
	if resposta.get("grupos") is None:
		erro = "Não foi possível carregar os grupos do WhatsApp" + (
			f": {resposta.get('erro')}" if resposta.get("erro") else "."
		)
	return itens, erro


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = f"/login?redirect-to={ROTA}"
		raise frappe.Redirect

	enrich_context(context, ROTA)
	if context.access_denied or not pode_gerenciar_assembleias():
		frappe.local.flags.redirect_location = "/403"
		raise frappe.Redirect

	uel_data = get_uel_cached()
	context.portal_logo = uel_data.get("logo") if uel_data else None
	context.active_link = "/administracao/assembleias"

	dados = dados_das_configuracoes()
	context.config = frappe._dict(dados)
	context.config_json = {
		"pauta_ordinaria": dados["pauta_ordinaria"],
		"pauta_extraordinaria": dados["pauta_extraordinaria"],
		"materiais": dados["materiais"],
		"orientacoes": c.ORIENTACAO_POR_FINALIDADE,
		"orientacao_simples": c.ORIENTACAO_APROVACAO_SIMPLES,
		"finalidades": [
			{"label": "Sem finalidade", "value": ""},
			*({"label": f, "value": f} for f in c.FINALIDADES),
		],
	}
	context.unidade_items = [
		{"label": unidade, "value": unidade} for unidade in (c.PRAZO_SEM_LIMITE, c.PRAZO_DIAS, c.PRAZO_HORAS)
	]
	context.prazos = PRAZOS
	context.variaveis = sorted(VARIAVEIS)
	context.grupo_items, context.grupo_erro = _grupos_do_whatsapp(dados.get("grupo_diretoria_whatsapp") or "")
	context.idade_representacao_anos = (dados.get("idade_minima_representacao_meses") or 0) / 12
	return context
