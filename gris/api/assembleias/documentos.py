# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Conteúdo dos documentos da assembleia em markdown restrito (RF-06, RF-07, RF-11).

O markdown é a fonte única: vira HTML na pré-visualização do portal e requests da Docs
API no papel timbrado. Só usa o que o conversor entende: `#`/`##` (títulos), parágrafos,
`**negrito**`, `_itálico_`, listas `1.` e `-` e tabelas `|`.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint

from gris.api.assembleias import constantes as c
from gris.api.assembleias.formularios import CARGO_NO_EDITAL, formularios_da_assembleia
from gris.api.assembleias.padroes import configuracoes, valores_da_assembleia
from gris.api.assembleias.textos import substituir


def linhas_de_link(doc, config) -> list[str]:
	"""Uma frase por formulário previsto na pauta, com link e prazo (CA-06.3)."""
	linhas = []
	for formulario in formularios_da_assembleia(doc, config):
		if not formulario["previsto"]:
			continue
		modelo = (
			c.LINHA_LINK_ASSUNTOS
			if formulario["chave"] == c.FORMULARIO_ASSUNTOS_GERAIS
			else c.LINHA_LINK_CANDIDATURA
		)
		linhas.append(
			substituir(
				modelo,
				{
					"cargo": CARGO_NO_EDITAL.get(formulario["chave"], ""),
					"link": formulario["link"],
					"prazo": formulario["prazo"],
				},
			)
		)
	return linhas


def conteudo_do_edital(doc, config=None) -> str:
	config = config or configuracoes()
	valores = valores_da_assembleia(doc, config)
	partes = [
		f"# REUNIÃO {valores['tipo']} DA ASSEMBLEIA DE GRUPO",
		"## EDITAL DE CONVOCAÇÃO",
		substituir(doc.edital_texto_topo or "", valores),
		"\n".join(f"{i}. {item.titulo}" for i, item in enumerate(doc.pauta, start=1)),
	]
	if doc.edital_incluir_links:
		partes.extend(linhas_de_link(doc, config))
	partes.append(substituir(doc.edital_texto_rodape or "", valores))
	return "\n\n".join(parte.strip() for parte in partes if parte and parte.strip())


ROTULO_DA_COLUNA_REPRESENTANTE = {
	c.LINHA_JOVEM_REPRESENTADO: "Responsável: ______________________",
	c.LINHA_EQUIPE: "Representante: ____________________",
}


def _celula(texto: str) -> str:
	"""Texto seguro dentro de uma célula de tabela markdown."""
	return " ".join(str(texto or "").replace("|", "/").split())


def conteudo_da_lista(doc, config=None) -> str:
	"""Lista de presença em retrato: Nome | Representado por | Assinatura (CA-07.6)."""
	from gris.api.assembleias.votantes import totais

	config = config or configuracoes()
	valores = valores_da_assembleia(doc, config)
	linhas = [
		{"nome": v.nome, "tipo_linha": v.tipo_linha, "removido": v.removido}
		for v in doc.votantes
		if not v.removido
	]
	linhas.sort(key=lambda linha: (linha["nome"] or "").casefold())
	t = totais(linhas)
	tabela = ["| Nome | Representado por | Assinatura |", "| --- | --- | --- |"]
	for linha in linhas:
		nome = _celula(linha["nome"])
		if linha["tipo_linha"] == c.LINHA_JOVEM_REPRESENTADO:
			nome = f"{nome} (representado por seu responsável legal)"
		tabela.append(f"| {nome} | {ROTULO_DA_COLUNA_REPRESENTANTE.get(linha['tipo_linha'], '')} |  |")
	return "\n\n".join(
		[
			"# LISTA DE PRESENÇA",
			f"## REUNIÃO {valores['tipo']} DA ASSEMBLEIA DE GRUPO — {valores['data_curta']}",
			f"{t['total']} com direito a voto. Maioria absoluta para a primeira convocação: {t['maioria_absoluta']}.",
			"\n".join(tabela),
		]
	)


def conteudo_da_ata(doc, config=None) -> str:
	config = config or configuracoes()
	valores = valores_da_assembleia(doc, config)
	return "\n\n".join(
		[
			f"# ATA DA REUNIÃO {valores['tipo']} DA ASSEMBLEIA DE GRUPO",
			(doc.ata_texto or "").strip(),
		]
	)


# --------------------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------------------


def _responder_pdf(nome: str, conteudo: bytes) -> None:
	frappe.local.response.filename = f"{frappe.scrub(nome)}.pdf"
	frappe.local.response.filecontent = conteudo
	frappe.local.response.type = "pdf"


def gerar_edital_final(doc) -> bytes:
	from gris.api.google_workspace.assembleia_drive import gerar_documento

	return gerar_documento(doc.name, "edital", conteudo_do_edital(doc), final=True)


@frappe.whitelist(methods=["POST"])
def baixar_pdf(name: str, tipo: str) -> None:
	"""PDF no timbrado de edital, lista de presença ou ata (RF-11).

	Com o edital publicado, devolve sempre o PDF final; se ele ainda não existir (o Drive
	falhou na publicação), gera agora.
	"""
	from gris.api.assembleias.pagina import _assembleia
	from gris.api.google_workspace.assembleia_drive import baixar_pdf_existente, gerar_documento

	doc = _assembleia(name)
	if tipo == "edital":
		if cint(doc.edital_publicado):
			conteudo = (
				baixar_pdf_existente(doc.edital_pdf_link)
				if _edital_final_gerado(doc)
				else gerar_edital_final(doc)
			)
		else:
			conteudo = gerar_documento(doc.name, "edital", conteudo_do_edital(doc))
		_responder_pdf(f"edital-{doc.name}", conteudo)
		return
	if tipo == "lista":
		if not [v for v in doc.votantes if not v.removido]:
			frappe.throw(_("Gere a lista de presença antes de exportar."))
		_responder_pdf(
			f"lista-de-presenca-{doc.name}", gerar_documento(doc.name, "lista", conteudo_da_lista(doc))
		)
		return
	if tipo == "ata":
		if not (doc.ata_texto or "").strip():
			frappe.throw(_("Escreva ou gere o texto da ata antes de gerar o PDF."))
		_responder_pdf(f"ata-{doc.name}", gerar_documento(doc.name, "ata", conteudo_da_ata(doc)))
		return
	frappe.throw(_("Documento inválido."))


def _edital_final_gerado(doc) -> bool:
	"""O PDF final é gravado nos mesmos campos do rascunho, marcado por `edital_final_gerado`."""
	return bool(doc.edital_pdf_link and cint(doc.edital_final_gerado))


@frappe.whitelist(methods=["POST"])
def criar_pasta(name: str) -> dict:
	"""Botão "Criar pasta no Drive" da Visão Geral (CA-11.2)."""
	from googleapiclient.errors import HttpError

	from gris.api.assembleias.pagina import _assembleia
	from gris.api.google_workspace.assembleia_drive import criar_pasta_assembleia, mensagem_do_google

	doc = _assembleia(name)
	try:
		link = criar_pasta_assembleia(doc.name)
	except HttpError as erro:
		frappe.throw(mensagem_do_google(erro))
	erro = frappe.db.get_value(c.DOCTYPE_ASSEMBLEIA, doc.name, "pasta_drive_erro") or ""
	return {"link": link, "erro": "" if link else erro}
