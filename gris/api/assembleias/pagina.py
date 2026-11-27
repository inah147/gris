# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Página da assembleia: Visão Geral, Edital e Auxílio para condução (RF-05, RF-06, RF-10).

Tudo exige quem gerencia. As gravações devolvem os dados da página já atualizados, e as
de salvamento automático devolvem o `modified` novo: a tela manda o último que conhece e,
se outra janela gravou no meio, recebe `conflito` em vez de sobrescrever (CA-08.3).
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, get_time, getdate, now_datetime
from frappe.utils.data import md_to_html
from frappe.utils.html_utils import sanitize_html

from gris.api.assembleias import constantes as c
from gris.api.assembleias.documentos import conteudo_do_edital
from gris.api.assembleias.formularios import formularios_da_assembleia
from gris.api.assembleias.padroes import aplicar_pauta_padrao, configuracoes, hora
from gris.api.assembleias.permissoes import garantir_gestor_assembleias
from gris.api.assembleias.pessoas import juntar_pessoa, nome_da_pessoa, separar_pessoa
from gris.api.assembleias.textos import validar_texto

TIPOS = (c.TIPO_ORDINARIA, c.TIPO_EXTRAORDINARIA)


def markdown_em_html(texto: str | None) -> str:
	"""Markdown escrito pela gestão, convertido e sanitizado para exibir no portal."""
	if not (texto or "").strip():
		return ""
	return sanitize_html(str(md_to_html(texto) or ""), always_sanitize=True)


def _carregar(payload) -> dict:
	if isinstance(payload, dict):
		return payload
	try:
		dados = json.loads(payload or "{}")
	except ValueError:
		frappe.throw(_("Dados inválidos."))
	if not isinstance(dados, dict):
		frappe.throw(_("Dados inválidos."))
	return dados


def _assembleia(name: str):
	garantir_gestor_assembleias()
	if not name or not frappe.db.exists(c.DOCTYPE_ASSEMBLEIA, name):
		frappe.throw(_("Assembleia não encontrada."), frappe.DoesNotExistError)
	return frappe.get_doc(c.DOCTYPE_ASSEMBLEIA, name)


def _hora(valor) -> str | None:
	if not valor:
		return None
	try:
		return get_time(valor).strftime("%H:%M:%S")
	except Exception:
		frappe.throw(_("Horário inválido: {0}.").format(valor))


# --------------------------------------------------------------------------------------
# Leitura
# --------------------------------------------------------------------------------------


def dados_da_pagina(doc, config=None) -> dict:
	config = config or configuracoes()
	eletiva = doc.eletiva
	prazo_edital = add_days(doc.data, -(cint(config.dias_limite_edital) or 30))
	return {
		"name": doc.name,
		"modified": str(doc.modified),
		"titulo": doc.titulo,
		"data": str(doc.data),
		"tipo": doc.tipo,
		"local": doc.local or "",
		"hora_primeira": hora(doc.hora_primeira_convocacao),
		"hora_segunda": hora(doc.hora_segunda_convocacao),
		"credenciamento": juntar_pessoa(doc.credenciamento_tipo, doc.credenciamento),
		"vagas_delegados": cint(doc.vagas_delegados),
		"presidente": nome_da_pessoa(doc.presidente_tipo, doc.presidente),
		"secretario": nome_da_pessoa(doc.secretario_tipo, doc.secretario),
		"pasta_drive_link": doc.pasta_drive_link or "",
		"pasta_drive_erro": doc.pasta_drive_erro or "",
		"eletiva": eletiva,
		"prazo_edital": str(prazo_edital),
		"prazo_vencido": not cint(doc.edital_publicado) and getdate(prazo_edital) < getdate(),
		"edital": {
			"publicado": cint(doc.edital_publicado),
			"publicado_em": str(doc.edital_publicado_em or ""),
			"data_publicacao": str(doc.data_publicacao_edital or ""),
			"incluir_links": cint(doc.edital_incluir_links),
			"texto_topo": doc.edital_texto_topo or "",
			"texto_rodape": doc.edital_texto_rodape or "",
			"doc_link": doc.edital_doc_link or "",
			"pdf_link": doc.edital_pdf_link or "",
		},
		"pauta": [
			{
				"name": item.name,
				"titulo": item.titulo,
				"tem_votacao": cint(item.tem_votacao),
				"finalidade": item.finalidade or "",
				"concluido": cint(item.concluido),
				"orientacao_conducao": item.orientacao_conducao or "",
				"orientacao_html": markdown_em_html(item.orientacao_conducao),
			}
			for item in doc.pauta
		],
		"checklist": [
			{
				"chave": etapa.chave,
				"fase": etapa.fase,
				"titulo": etapa.titulo,
				"concluido": cint(etapa.concluido),
				"concluido_em": str(etapa.concluido_em or ""),
				"concluido_por": etapa.concluido_por or "",
				"automatico": etapa.chave == c.CHECKLIST_DIVULGAR_EDITAL,
			}
			for etapa in doc.checklist
			if eletiva or not cint(etapa.somente_eletiva)
		],
		"materiais": [m.item for m in config.materiais],
		"formularios": formularios_da_assembleia(doc, config),
		"orientacoes_gerais_html": markdown_em_html(config.orientacoes_gerais),
	}


# --------------------------------------------------------------------------------------
# Visão Geral
# --------------------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def salvar_visao_geral(name: str, payload: str) -> dict:
	doc = _assembleia(name)
	dados = _carregar(payload)
	if str(doc.modified) != str(dados.get("modified") or doc.modified):
		frappe.throw(_("A assembleia foi alterada em outra janela. Recarregue a página para continuar."))

	tipo = dados.get("tipo") or doc.tipo
	if tipo not in TIPOS:
		frappe.throw(_("Tipo de assembleia inválido."))
	local = (dados.get("local") or "").strip()
	if not local:
		frappe.throw(_("Informe o local da assembleia."))
	if not dados.get("data") or not dados.get("hora_primeira"):
		frappe.throw(_("Informe a data e o horário da primeira convocação."))

	trocou_tipo = tipo != doc.tipo
	credenciamento_tipo, credenciamento = separar_pessoa(dados.get("credenciamento"))
	doc.update(
		{
			"data": getdate(dados["data"]),
			"tipo": tipo,
			"local": local,
			"hora_primeira_convocacao": _hora(dados.get("hora_primeira")),
			"hora_segunda_convocacao": _hora(dados.get("hora_segunda")),
			"credenciamento_tipo": credenciamento_tipo or None,
			"credenciamento": credenciamento or None,
			"vagas_delegados": max(cint(dados.get("vagas_delegados")), 0),
		}
	)
	if trocou_tipo and dados.get("trocar_pauta"):
		aplicar_pauta_padrao(doc)
	doc.save()
	return dados_da_pagina(doc)


# --------------------------------------------------------------------------------------
# Edital
# --------------------------------------------------------------------------------------


def _aplicar_edital(doc, dados: dict) -> None:
	"""Põe no doc o que veio da aba Edital, sem gravar.

	Item que já existia é reconhecido pelo `name` e mantém o "concluído" e a orientação
	(editada na aba Condução, que a aba Edital não mostra). Item novo recebe a orientação
	da finalidade.
	"""
	existentes = {item.name: item for item in doc.pauta}
	itens = []
	for item in dados.get("pauta") or []:
		titulo = " ".join(str(item.get("titulo") or "").split())
		if not titulo:
			continue
		finalidade = (item.get("finalidade") or "").strip()
		if finalidade and finalidade not in c.FINALIDADES:
			frappe.throw(_("Finalidade inválida: {0}.").format(finalidade))
		validar_texto(titulo, _("Item da pauta"))
		anterior = existentes.get(item.get("name") or "")
		if "orientacao_conducao" in item:
			orientacao = str(item.get("orientacao_conducao") or "").strip()
		else:
			orientacao = anterior.orientacao_conducao if anterior else ""
		itens.append(
			{
				"titulo": titulo,
				"tem_votacao": 1 if item.get("tem_votacao") else 0,
				"finalidade": finalidade,
				"orientacao_conducao": orientacao or c.orientacao_da_finalidade(finalidade),
				"concluido": cint(anterior.concluido) if anterior else 0,
			}
		)
	if not itens:
		frappe.throw(_("A pauta precisa de pelo menos um item."))

	doc.set("pauta", [])
	for item in itens:
		doc.append("pauta", item)

	topo = (dados.get("texto_topo") or "").strip()
	rodape = (dados.get("texto_rodape") or "").strip()
	validar_texto(topo, _("Texto antes da pauta"))
	validar_texto(rodape, _("Texto depois da pauta"))
	doc.edital_texto_topo = topo
	doc.edital_texto_rodape = rodape
	doc.edital_incluir_links = 1 if dados.get("incluir_links") else 0
	doc.data_publicacao_edital = getdate(dados["data_publicacao"]) if dados.get("data_publicacao") else None


@frappe.whitelist(methods=["POST"])
def salvar_edital(name: str, payload: str) -> dict:
	doc = _assembleia(name)
	if cint(doc.edital_publicado):
		frappe.throw(_("O edital já foi publicado e não pode mais ser alterado."))
	dados = _carregar(payload)
	if str(doc.modified) != str(dados.get("modified") or doc.modified):
		frappe.throw(_("A assembleia foi alterada em outra janela. Recarregue a página para continuar."))
	_aplicar_edital(doc, dados)
	doc.save()
	return dados_da_pagina(doc)


@frappe.whitelist(methods=["POST"])
def previa_edital(name: str, payload: str | None = None) -> dict:
	"""O edital como vai sair, com o que está na tela, sem gravar nada."""
	doc = _assembleia(name)
	if payload and not cint(doc.edital_publicado):
		_aplicar_edital(doc, _carregar(payload))
	return {"html": markdown_em_html(conteudo_do_edital(doc))}


@frappe.whitelist(methods=["POST"])
def restaurar_pauta_padrao(name: str) -> dict:
	doc = _assembleia(name)
	if cint(doc.edital_publicado):
		frappe.throw(_("O edital já foi publicado e não pode mais ser alterado."))
	aplicar_pauta_padrao(doc)
	doc.save()
	return dados_da_pagina(doc)


@frappe.whitelist(methods=["POST"])
def marcar_edital_publicado(name: str, fora_do_prazo: int | str = 0) -> dict:
	"""Publica e trava o edital (CA-06.5). Depois do prazo, pede uma segunda confirmação."""
	doc = _assembleia(name)
	if cint(doc.edital_publicado):
		return dados_da_pagina(doc)
	config = configuracoes()
	prazo = add_days(doc.data, -(cint(config.dias_limite_edital) or 30))
	if getdate() > getdate(prazo) and not cint(fora_do_prazo):
		# Como dado, e não como erro: a tela abre a confirmação em vez do toast vermelho.
		return {"precisa_confirmar": True, "prazo": str(prazo), "dias": cint(config.dias_limite_edital)}

	doc.edital_publicado = 1
	doc.edital_publicado_em = now_datetime()
	if not doc.data_publicacao_edital:
		doc.data_publicacao_edital = getdate()
	doc.save()

	# O PDF final no timbrado. Se o Drive falhar, o edital continua publicado e o PDF
	# final é gerado no primeiro "Baixar PDF".
	aviso = ""
	try:
		from gris.api.assembleias.documentos import gerar_edital_final

		gerar_edital_final(doc)
	except Exception as erro:
		frappe.clear_messages()
		if not isinstance(erro, frappe.ValidationError):
			frappe.log_error(frappe.get_traceback(), f"Edital final da assembleia {doc.name}")
		aviso = _(
			"O edital foi publicado, mas o PDF final não pôde ser gerado agora ({0}). "
			'Use "Baixar PDF" para tentar de novo.'
		).format(str(erro) or _("erro no Drive"))
	doc.reload()
	return {**dados_da_pagina(doc), "aviso": aviso}


# --------------------------------------------------------------------------------------
# Salvamento automático: checklist e condução (a ata usa o mesmo caminho em ata.py)
# --------------------------------------------------------------------------------------


def aplicar_checklist(doc, marcacoes: dict) -> None:
	for etapa in doc.checklist:
		if etapa.chave not in marcacoes or etapa.chave == c.CHECKLIST_DIVULGAR_EDITAL:
			continue
		marcado = 1 if marcacoes[etapa.chave] else 0
		if marcado == cint(etapa.concluido):
			continue
		etapa.concluido = marcado
		etapa.concluido_em = now_datetime() if marcado else None
		etapa.concluido_por = frappe.session.user if marcado else None


def aplicar_conducao(doc, itens: dict) -> None:
	por_nome = {item.name: item for item in doc.pauta}
	for nome, valores in (itens or {}).items():
		item = por_nome.get(nome)
		if not item or not isinstance(valores, dict):
			continue
		if "concluido" in valores:
			item.concluido = 1 if valores["concluido"] else 0
		if "orientacao_conducao" in valores:
			item.orientacao_conducao = str(valores["orientacao_conducao"] or "").strip()


@frappe.whitelist(methods=["POST"])
def salvar_campos(name: str, campos: str, modified: str) -> dict:
	"""Gravação automática da página: checklist, condução (pauta) e ata."""
	doc = _assembleia(name)
	if str(doc.modified) != str(modified):
		return {"conflito": True}
	dados = _carregar(campos)
	if "checklist" in dados:
		aplicar_checklist(doc, dados["checklist"] or {})
	if "pauta" in dados:
		aplicar_conducao(doc, dados["pauta"] or {})
	if "ata" in dados:
		from gris.api.assembleias.ata import aplicar_campos

		aplicar_campos(doc, dados["ata"] or {})
	doc.save()

	from gris.api.assembleias.ata import contar_marcadores

	return {
		"modified": str(doc.modified),
		"salvo_em": now_datetime().strftime("%H:%M"),
		"pauta": {item.name: markdown_em_html(item.orientacao_conducao) for item in doc.pauta},
		"marcadores": contar_marcadores(doc.ata_texto),
		"presidente_nome": nome_da_pessoa(doc.presidente_tipo, doc.presidente),
		"secretario_nome": nome_da_pessoa(doc.secretario_tipo, doc.secretario),
	}
