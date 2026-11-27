from urllib.parse import quote

import frappe

from gris.api.assembleias import constantes as c
from gris.api.assembleias.formularios import (
	ROTULO_DO_FORMULARIO,
	elegibilidade,
	funcoes_eleitas,
	pessoa_do_usuario,
	situacao_agora,
)
from gris.api.assembleias.pessoas import opcoes_de_pessoas
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1

ROTA = "/assembleias/candidatura"
FORMULARIOS = (c.FORMULARIO_MESA, c.FORMULARIO_DELEGADO, c.FORMULARIO_COMISSAO_FISCAL, c.FORMULARIO_DIRETORIA)


def get_context(context):
	assembleia = frappe.form_dict.get("assembleia") or ""
	cargo = frappe.form_dict.get("cargo") or ""
	if frappe.session.user == "Guest":
		volta = quote(f"{ROTA}?assembleia={assembleia}&cargo={cargo}", safe="")
		frappe.local.flags.redirect_location = f"/login?redirect-to={volta}"
		raise frappe.Redirect

	enrich_context(context, ROTA)
	uel_data = get_uel_cached()
	context.portal_logo = uel_data.get("logo") if uel_data else None

	context.encontrada = bool(assembleia and frappe.db.exists(c.DOCTYPE_ASSEMBLEIA, assembleia)) and (
		cargo in FORMULARIOS
	)
	if not context.encontrada:
		return context

	doc = frappe.get_doc(c.DOCTYPE_ASSEMBLEIA, assembleia)
	pessoa = pessoa_do_usuario()
	situacao = situacao_agora(doc, cargo)
	context.assembleia = doc
	context.chave = cargo
	context.rotulo = ROTULO_DO_FORMULARIO[cargo]
	context.situacao = situacao
	context.fecha_em = frappe.utils.get_datetime(situacao["fecha_em"])
	context.pessoa = pessoa
	context.regra = elegibilidade(cargo, pessoa, doc.data)

	ja_inscrito = set()
	if pessoa:
		ja_inscrito = set(
			frappe.get_all(
				c.DOCTYPE_CANDIDATURA,
				filters={
					"assembleia": doc.name,
					"candidato_tipo": pessoa.tipo,
					"candidato": pessoa.name,
					"status": "Ativa",
				},
				pluck="cargo",
			)
		)
	context.ja_inscrito = sorted(ja_inscrito)
	context.cargos_mesa = [
		{"cargo": cargo_mesa, "inscrito": cargo_mesa in ja_inscrito}
		for cargo_mesa in c.CARGOS_DO_FORMULARIO[c.FORMULARIO_MESA]
	]
	context.cargo_unico = (c.CARGOS_DO_FORMULARIO.get(cargo) or ("",))[0]
	if cargo == c.FORMULARIO_DIRETORIA:
		context.funcoes = funcoes_eleitas()
		context.pessoas_18 = opcoes_de_pessoas(18, doc.data)
	return context
