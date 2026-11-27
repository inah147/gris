# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Modo sessão: registro item a item, acesso da mesa eleita e leitura ao vivo (RF-16).

Quem entra na sessão de uma assembleia:

- quem gerencia as assembleias, sempre, com edição;
- o secretário da mesa (a pessoa gravada em `secretario`), com edição do registro;
- o presidente da mesa, só para leitura.

A mesa entra pelo próprio login e perde o acesso quando "Finalizar a ata" é marcado. O
presidente acompanha por consulta leve (`ler_sessao` com o último `modified`), e o servidor
avisa pela sala do usuário dele quando o socket estiver disponível.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from gris.api.assembleias import constantes as c
from gris.api.assembleias.padroes import hora
from gris.api.assembleias.permissoes import pode_gerenciar_assembleias

PAPEL_GESTOR = "gestor"
PAPEL_SECRETARIO = "secretario"
PAPEL_PRESIDENTE = "presidente"
PAPEIS_QUE_EDITAM = frozenset({PAPEL_GESTOR, PAPEL_SECRETARIO})

RESULTADOS_DO_ITEM = ("Aprovado por aclamação", "Aprovado", "Reprovado", "Retirado de pauta")
RESULTADOS_DA_CANDIDATURA = ("Eleito", "Suplente", "Não eleito")
CAMPOS_DE_VOTOS = ("votos_favor", "votos_contra", "votos_abstencao")
# Da ata, o que a sessão grava. A mesa (presidente e secretário) só quem gerencia troca.
CAMPOS_DA_ATA_NA_SESSAO = ("ata_hora_inicio", "ata_hora_termino", "ata_presentes", "anotacoes_secretario")
CAMPOS_DA_MESA = ("presidente", "secretario")
CHECKLIST_FINALIZAR_ATA = "finalizar_ata"
LIMITE_DE_TEXTO = 100_000
EVENTO_DA_SESSAO = "gris_assembleia_sessao"


# --------------------------------------------------------------------------------------
# Quem entra
# --------------------------------------------------------------------------------------


def ata_finalizada(doc) -> bool:
	return any(e.chave == CHECKLIST_FINALIZAR_ATA and cint(e.concluido) for e in doc.checklist)


def _e_a_pessoa(tipo, name, pessoa) -> bool:
	return bool(name and pessoa) and (tipo, name) == (pessoa.tipo, pessoa.name)


def papel_na_assembleia(doc, user: str | None = None) -> str | None:
	"""Gestor, secretário, presidente ou ninguém. Quem é as duas coisas na mesa edita."""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return None
	if pode_gerenciar_assembleias(user):
		return PAPEL_GESTOR
	if ata_finalizada(doc):
		return None
	from gris.api.assembleias.formularios import pessoa_do_usuario

	pessoa = pessoa_do_usuario(user)
	if _e_a_pessoa(doc.secretario_tipo, doc.secretario, pessoa):
		return PAPEL_SECRETARIO
	if _e_a_pessoa(doc.presidente_tipo, doc.presidente, pessoa):
		return PAPEL_PRESIDENTE
	return None


def _sessao(name: str, editar: bool = False):
	if not name or not frappe.db.exists(c.DOCTYPE_ASSEMBLEIA, name):
		frappe.throw(_("Assembleia não encontrada."), frappe.DoesNotExistError)
	doc = frappe.get_doc(c.DOCTYPE_ASSEMBLEIA, name)
	papel = papel_na_assembleia(doc)
	if not papel:
		frappe.throw(
			_("Só a mesa da assembleia e quem gerencia as assembleias abrem a sessão."),
			frappe.PermissionError,
		)
	if editar and papel not in PAPEIS_QUE_EDITAM:
		frappe.throw(_("O presidente da mesa acompanha a sessão só para leitura."), frappe.PermissionError)
	return doc, papel


def usuarios_da_pessoa(tipo: str | None, name: str | None) -> list[str]:
	"""Logins de uma pessoa: o id@escoteiros do Associado e o e-mail do Responsável."""
	if not tipo or not name:
		return []
	candidatos = []
	if tipo == "Associado":
		candidatos.append(frappe.db.get_value("Associado", name, "id_escoteiros"))
	if frappe.db.exists("Responsavel", name):
		candidatos.append(frappe.db.get_value("Responsavel", name, "email"))
	return [u for u in candidatos if u and frappe.db.exists("User", u)]


# --------------------------------------------------------------------------------------
# Leitura
# --------------------------------------------------------------------------------------


def item_atual(itens: list[dict]) -> str | None:
	"""O item em andamento: iniciado e não concluído; senão o primeiro não concluído."""
	for item in itens:
		if item["iniciado_em"] and not item["concluido"]:
			return item["name"]
	for item in itens:
		if not item["concluido"]:
			return item["name"]
	return itens[-1]["name"] if itens else None


def estado_da_sessao(doc, papel: str) -> dict:
	from gris.api.assembleias.formularios import listar_inscricoes
	from gris.api.assembleias.padroes import configuracoes
	from gris.api.assembleias.pagina import data_por_extenso, markdown_em_html
	from gris.api.assembleias.pessoas import juntar_pessoa, nome_da_pessoa
	from gris.api.assembleias.votantes import _linhas_do_doc, totais

	config = configuracoes()
	itens = [
		{
			"name": item.name,
			"titulo": item.titulo,
			"tem_votacao": cint(item.tem_votacao),
			"finalidade": item.finalidade or "",
			"orientacao_html": markdown_em_html(item.orientacao_conducao),
			"anotacoes": item.anotacoes or "",
			"resultado": item.resultado or "",
			"votos_favor": cint(item.votos_favor),
			"votos_contra": cint(item.votos_contra),
			"votos_abstencao": cint(item.votos_abstencao),
			"concluido": cint(item.concluido),
			"iniciado_em": str(item.iniciado_em or ""),
			"concluido_em": str(item.concluido_em or ""),
		}
		for item in doc.pauta
	]
	lista = totais(_linhas_do_doc(doc))
	return {
		"name": doc.name,
		"modified": str(doc.modified),
		"papel": papel,
		"pode_editar": papel in PAPEIS_QUE_EDITAM,
		"pode_trocar_mesa": papel == PAPEL_GESTOR,
		"tipo": doc.tipo,
		"data": str(doc.data),
		"data_extenso": data_por_extenso(doc.data),
		"aberta_em": str(doc.sessao_aberta_em or ""),
		"hora_inicio": hora(doc.ata_hora_inicio),
		"hora_termino": hora(doc.ata_hora_termino),
		"presentes": cint(doc.ata_presentes) or None,
		"votantes": lista["total"],
		"quorum": lista["maioria_absoluta"],
		"presidente": juntar_pessoa(doc.presidente_tipo, doc.presidente),
		"presidente_nome": nome_da_pessoa(doc.presidente_tipo, doc.presidente),
		"secretario": juntar_pessoa(doc.secretario_tipo, doc.secretario),
		"secretario_nome": nome_da_pessoa(doc.secretario_tipo, doc.secretario),
		"anotacoes_gerais": doc.anotacoes_secretario or "",
		"orientacoes_gerais_html": markdown_em_html(config.orientacoes_gerais),
		"itens": itens,
		"atual": item_atual(itens),
		"inscricoes": {
			**listar_inscricoes(doc.name, somente_ativas=True),
			"vagas_delegados": cint(doc.vagas_delegados),
			"titulares_cf": cint(config.vagas_comissao_fiscal),
			"suplentes_cf": cint(config.suplentes_comissao_fiscal),
		},
	}


# --------------------------------------------------------------------------------------
# Gravação
# --------------------------------------------------------------------------------------


def _texto(valor) -> str:
	texto = str(valor or "")
	if len(texto) > LIMITE_DE_TEXTO:
		frappe.throw(_("O texto passou do limite de {0} caracteres.").format(LIMITE_DE_TEXTO))
	return texto


def _aplicar_itens(doc, itens: dict) -> None:
	por_nome = {item.name: item for item in doc.pauta}
	agora = now_datetime()
	for nome, valores in (itens or {}).items():
		item = por_nome.get(nome)
		if not item or not isinstance(valores, dict):
			continue
		if "anotacoes" in valores:
			item.anotacoes = _texto(valores["anotacoes"])
		if "resultado" in valores:
			resultado = valores["resultado"] or ""
			if resultado and resultado not in RESULTADOS_DO_ITEM:
				frappe.throw(_("Resultado inválido: {0}.").format(resultado))
			item.resultado = resultado
		for campo in CAMPOS_DE_VOTOS:
			if campo in valores:
				item.set(campo, max(cint(valores[campo]), 0))
		if cint(valores.get("iniciar")) and not item.iniciado_em:
			item.iniciado_em = agora
		if "concluido" in valores:
			concluido = 1 if cint(valores["concluido"]) else 0
			if concluido and not cint(item.concluido):
				item.concluido_em = agora
				item.iniciado_em = item.iniciado_em or agora
			if not concluido:
				item.concluido_em = None
			item.concluido = concluido


def _aplicar_resultados(doc, candidaturas: dict, chapas: dict) -> None:
	"""Eleitos marcados na sessão. Só candidaturas e chapas ativas desta assembleia."""
	for nome, resultado in (candidaturas or {}).items():
		resultado = resultado or ""
		if resultado and resultado not in RESULTADOS_DA_CANDIDATURA:
			frappe.throw(_("Resultado inválido: {0}.").format(resultado))
		dono = frappe.db.get_value(c.DOCTYPE_CANDIDATURA, nome, ["assembleia", "status"], as_dict=True)
		if not dono or dono.assembleia != doc.name or dono.status != "Ativa":
			frappe.throw(_("Candidatura não encontrada nesta assembleia."))
		frappe.db.set_value(c.DOCTYPE_CANDIDATURA, nome, "resultado", resultado)
	for nome, eleita in (chapas or {}).items():
		dono = frappe.db.get_value(c.DOCTYPE_CHAPA, nome, ["assembleia", "status"], as_dict=True)
		if not dono or dono.assembleia != doc.name or dono.status != "Ativa":
			frappe.throw(_("Chapa não encontrada nesta assembleia."))
		if cint(eleita):
			# Uma chapa eleita por assembleia.
			for outra in frappe.get_all(
				c.DOCTYPE_CHAPA,
				filters={"assembleia": doc.name, "eleita": 1, "name": ["!=", nome]},
				pluck="name",
			):
				frappe.db.set_value(c.DOCTYPE_CHAPA, outra, "eleita", 0)
		frappe.db.set_value(c.DOCTYPE_CHAPA, nome, "eleita", 1 if cint(eleita) else 0)


def aplicar_sessao(doc, campos: dict, papel: str) -> None:
	"""Põe no doc o que veio do modo sessão, conforme o papel. Não grava o doc."""
	from gris.api.assembleias.ata import aplicar_campos

	agora = now_datetime()
	if cint(campos.get("abrir")):
		doc.sessao_aberta_em = doc.sessao_aberta_em or agora
		doc.ata_hora_inicio = doc.ata_hora_inicio or agora.strftime("%H:%M:00")
	if cint(campos.get("encerrar")):
		doc.ata_hora_termino = agora.strftime("%H:%M:00")
	ata = campos.get("ata") or {}
	permitidos = CAMPOS_DA_ATA_NA_SESSAO + (CAMPOS_DA_MESA if papel == PAPEL_GESTOR else ())
	if any(campo in ata for campo in CAMPOS_DA_MESA) and papel != PAPEL_GESTOR:
		frappe.throw(_("Só quem gerencia as assembleias troca a mesa."), frappe.PermissionError)
	aplicar_campos(doc, {campo: valor for campo, valor in ata.items() if campo in permitidos})
	_aplicar_itens(doc, campos.get("itens") or {})
	_aplicar_resultados(doc, campos.get("candidaturas") or {}, campos.get("chapas") or {})


def _avisar_quem_acompanha(doc) -> None:
	"""Avisa o presidente (e quem mais for da mesa) que a sessão mudou."""
	usuarios = set(usuarios_da_pessoa(doc.presidente_tipo, doc.presidente))
	usuarios |= set(usuarios_da_pessoa(doc.secretario_tipo, doc.secretario))
	usuarios.discard(frappe.session.user)
	for usuario in usuarios:
		frappe.publish_realtime(
			EVENTO_DA_SESSAO,
			{"name": doc.name, "modified": str(doc.modified)},
			user=usuario,
			after_commit=True,
		)


def _carregar(campos) -> dict:
	if isinstance(campos, dict):
		return campos
	try:
		dados = json.loads(campos or "{}")
	except ValueError:
		frappe.throw(_("Dados inválidos."))
	if not isinstance(dados, dict):
		frappe.throw(_("Dados inválidos."))
	return dados


@frappe.whitelist(methods=["POST"])
def salvar_sessao(name: str, campos: str, modified: str) -> dict:
	"""Gravação automática do modo sessão. Recusa com `conflito` se outra janela gravou."""
	doc, papel = _sessao(name, editar=True)
	if str(doc.modified) != str(modified):
		return {"conflito": True}
	aplicar_sessao(doc, _carregar(campos), papel)
	# O secretário não tem permissão no DocType: o acesso foi conferido em `_sessao`, e só os
	# campos da sessão passam por `aplicar_sessao`.
	doc.save(ignore_permissions=True)
	_avisar_quem_acompanha(doc)
	return {
		"modified": str(doc.modified),
		"salvo_em": now_datetime().strftime("%H:%M"),
		"sessao": estado_da_sessao(doc, papel),
	}


@frappe.whitelist(methods=["GET", "POST"])
def ler_sessao(name: str, desde: str | None = None) -> dict:
	"""Estado da sessão. Com `desde` igual ao `modified` atual, responde só que nada mudou."""
	doc, papel = _sessao(name)
	if desde and str(doc.modified) == str(desde):
		return {"mudou": False}
	return {"mudou": True, **estado_da_sessao(doc, papel)}
