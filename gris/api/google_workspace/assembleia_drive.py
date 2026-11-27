# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Pasta da assembleia no Drive e documentos no papel timbrado (spec RF-11).

A pasta segue o modelo das festas (`festa_drive`). O documento segue a declaração de
idoneidade (`recepcao_drive`): copia o Google Doc do timbrado para a pasta, escreve o
conteúdo pela Docs API, exporta o PDF e o guarda na mesma pasta. O Doc fica na pasta,
editável; o PDF é devolvido para download.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, formatdate, getdate
from googleapiclient.errors import HttpError

from gris.api.assembleias import constantes as c
from gris.api.google_workspace.access_manager import _execute_with_retry, _get_google_drive_service
from gris.api.google_workspace.festa_drive import (
	build_drive_folder_link,
	buscar_pasta,
	criar_pasta,
	extract_drive_folder_id,
	validar_pasta_raiz,
)
from gris.api.google_workspace.recepcao_drive import (
	PDF_MIMETYPE,
	_get_docs_service,
	download_file,
	extract_drive_file_id,
	extract_google_doc_id,
	upload_bytes_to_folder,
)
from gris.utils import docs_conteudo

DOCTYPE_COMUNICACAO = "Configuracoes de Comunicacao"

# tipo → (rótulo no nome do arquivo, campo do link do Doc, campo do link do PDF)
DOCUMENTOS = {
	"edital": ("Edital de convocação", "edital_doc_link", "edital_pdf_link"),
	"lista": ("Lista de presença", "lista_presenca_doc_link", "lista_presenca_pdf_link"),
	"ata": ("Ata", "ata_doc_link", "ata_pdf_link"),
}


def _logger():
	return frappe.logger("google_workspace_assembleia_drive", allow_site=True, file_count=10)


def nome_da_pasta(tipo: str, data) -> str:
	return f"Assembleia {tipo} - {formatdate(getdate(data), 'dd-MM-yyyy')}"


# --------------------------------------------------------------------------------------
# Pasta
# --------------------------------------------------------------------------------------


def _gravar_pasta(assembleia: str, link: str = "", erro: str = "") -> None:
	frappe.db.set_value(
		c.DOCTYPE_ASSEMBLEIA,
		assembleia,
		{"pasta_drive_link": link, "pasta_drive_erro": erro},
		update_modified=False,
	)


def criar_pasta_assembleia(assembleia: str) -> str:
	"""Cria (ou reaproveita) a pasta da assembleia e devolve o link. Erro vira mensagem."""
	doc = frappe.get_doc(c.DOCTYPE_ASSEMBLEIA, assembleia)
	if extract_drive_folder_id(doc.pasta_drive_link):
		return doc.pasta_drive_link

	config = frappe.get_single(c.DOCTYPE_CONFIGURACOES)
	if not cint(config.habilitar_pastas_drive):
		_gravar_pasta(
			assembleia, erro=_("As pastas no Drive estão desligadas em Configurações de Assembleias.")
		)
		return ""
	raiz = extract_drive_folder_id(config.pasta_assembleias_id) or (config.pasta_assembleias_id or "").strip()
	drive_id = (config.drive_compartilhado_assembleias or "").strip()
	if not raiz or not drive_id:
		_gravar_pasta(
			assembleia, erro=_("Escolha o drive e a pasta raiz em Configurações de Assembleias, no Desk.")
		)
		return ""

	drive = _get_google_drive_service()
	validar_pasta_raiz(drive, raiz, drive_id, rotulo="assembleias")
	nome = nome_da_pasta(doc.tipo, doc.data)
	pasta = buscar_pasta(drive, raiz, nome, {"corpora": "drive", "driveId": drive_id}) or criar_pasta(
		drive, raiz, nome, f"Documentos da {doc.titulo}"
	)
	pasta_id = (pasta or {}).get("id") or ""
	if not pasta_id:
		raise frappe.ValidationError(_("Não foi possível determinar o ID da pasta da assembleia."))
	link = build_drive_folder_link(pasta_id)
	_gravar_pasta(assembleia, link=link)
	# Commit explícito: a pasta já existe no Drive. Se algo falhar depois daqui, o link
	# não pode se perder — senão a próxima tentativa cria outra pasta (como em festa_drive).
	frappe.db.commit()  # nosemgrep
	return link


def criar_pasta_assembleia_async(assembleia: str) -> None:
	"""Job enfileirado na criação da assembleia (CA-02.3). Falha vira motivo na Visão Geral."""
	if not frappe.db.exists(c.DOCTYPE_ASSEMBLEIA, assembleia):
		return
	try:
		criar_pasta_assembleia(assembleia)
	except frappe.ValidationError as erro:
		_gravar_pasta(assembleia, erro=str(erro))
	except HttpError as erro:
		frappe.log_error(frappe.get_traceback(), f"Pasta da assembleia {assembleia}")
		_gravar_pasta(assembleia, erro=mensagem_do_google(erro))
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Pasta da assembleia {assembleia}")
		_gravar_pasta(
			assembleia, erro=_("Não foi possível criar a pasta no Drive. Tente de novo pela Visão Geral.")
		)


def enfileirar_pasta(assembleia: str) -> None:
	frappe.enqueue(
		"gris.api.google_workspace.assembleia_drive.criar_pasta_assembleia_async",
		queue="long",
		timeout=300,
		enqueue_after_commit=True,
		assembleia=assembleia,
	)


# --------------------------------------------------------------------------------------
# Documentos
# --------------------------------------------------------------------------------------


def mensagem_do_google(erro: HttpError) -> str:
	status = getattr(getattr(erro, "resp", None), "status", None)
	if status == 404:
		return _(
			"O papel timbrado ou a pasta da assembleia não foram encontrados no Drive. "
			"Confira o link do timbrado em Configurações de Comunicação."
		)
	if status == 403:
		return _(
			"A service account não tem acesso ao papel timbrado ou à pasta da assembleia. "
			"Compartilhe os dois com o e-mail da service account."
		)
	return _("O Google não respondeu como esperado. Tente de novo em alguns minutos.")


def _timbrado_id() -> str:
	link = frappe.db.get_single_value(DOCTYPE_COMUNICACAO, "link_papel_timbrado") or ""
	timbrado = extract_google_doc_id(link)
	if not timbrado:
		frappe.throw(_("Cadastre o link do papel timbrado (Google Docs) em Configurações de Comunicação."))
	return timbrado


def _pasta_id(doc) -> str:
	pasta = extract_drive_folder_id(doc.pasta_drive_link)
	if pasta:
		return pasta
	link = criar_pasta_assembleia(doc.name)
	pasta = extract_drive_folder_id(link)
	if not pasta:
		frappe.throw(
			frappe.db.get_value(c.DOCTYPE_ASSEMBLEIA, doc.name, "pasta_drive_erro")
			or _("A assembleia ainda não tem pasta no Drive.")
		)
	return pasta


def escrever_conteudo(docs, documento_id: str, markdown: str) -> None:
	"""Escreve o markdown no fim do corpo do Doc: texto em uma request por bloco,
	tabelas criadas e depois preenchidas com os índices reais."""
	for bloco in docs_conteudo.blocos(markdown):
		atual = _execute_with_retry(lambda: docs.documents().get(documentId=documento_id).execute())
		if bloco["tipo"] == "texto":
			requests, _comprimento = docs_conteudo.requests_de_texto(
				bloco["paragrafos"], docs_conteudo.fim_do_corpo(atual)
			)
		else:
			_execute_with_retry(
				lambda b=bloco: (
					docs.documents()
					.batchUpdate(
						documentId=documento_id,
						body={"requests": [docs_conteudo.requests_de_tabela(b["linhas"])]},
					)
					.execute()
				)
			)
			atual = _execute_with_retry(lambda: docs.documents().get(documentId=documento_id).execute())
			tabela = docs_conteudo.ultima_tabela(atual) or {}
			requests = docs_conteudo.requests_de_preenchimento(tabela, bloco["linhas"])
		if requests:
			_execute_with_retry(
				lambda r=requests: (
					docs.documents().batchUpdate(documentId=documento_id, body={"requests": r}).execute()
				)
			)


def _apagar(drive, link: str | None) -> None:
	arquivo = extract_drive_file_id(link) or extract_google_doc_id(link)
	if not arquivo:
		return
	try:
		_execute_with_retry(lambda: drive.files().delete(fileId=arquivo, supportsAllDrives=True).execute())
	except HttpError as erro:
		if getattr(getattr(erro, "resp", None), "status", None) != 404:
			_logger().warning("[ASSEMBLEIA DRIVE] não apagou %s: %s", arquivo, erro)


def link_do_doc(documento_id: str) -> str:
	return f"https://docs.google.com/document/d/{documento_id}/edit"


def gerar_documento(assembleia: str, tipo: str, markdown: str, final: bool = False) -> bytes:
	"""Gera o Doc e o PDF na pasta e devolve os bytes do PDF (CA-11.3 e CA-11.4).

	Um rascunho substitui o rascunho anterior do mesmo tipo. O edital final ganha
	"(publicado)" no nome e nunca é substituído.
	"""
	rotulo, campo_doc, campo_pdf = DOCUMENTOS[tipo]
	doc = frappe.get_doc(c.DOCTYPE_ASSEMBLEIA, assembleia)
	timbrado = _timbrado_id()
	pasta = _pasta_id(doc)
	nome = f"{rotulo} - {doc.titulo}{' (publicado)' if final else ''}"

	drive = _get_google_drive_service()
	docs = _get_docs_service()
	try:
		copia = _execute_with_retry(
			lambda: (
				drive.files()
				.copy(
					fileId=timbrado,
					body={"name": nome, "parents": [pasta]},
					fields="id",
					supportsAllDrives=True,
				)
				.execute()
			)
		)
		documento_id = (copia or {}).get("id") or ""
		if not documento_id:
			raise frappe.ValidationError(_("Não foi possível copiar o papel timbrado."))
		escrever_conteudo(docs, documento_id, markdown)
		pdf = _execute_with_retry(
			lambda: drive.files().export(fileId=documento_id, mimeType=PDF_MIMETYPE).execute()
		)
		link_pdf = upload_bytes_to_folder(
			content=pdf,
			filename=f"{nome}.pdf",
			mimetype=PDF_MIMETYPE,
			folder_id=pasta,
			description=f"{rotulo} gerado pelo GRIS",
		)
	except HttpError as erro:
		frappe.log_error(frappe.get_traceback(), f"Documento da assembleia {assembleia} ({tipo})")
		frappe.throw(mensagem_do_google(erro))

	# Rascunho anterior sai da pasta; o publicado nunca é apagado.
	if not (tipo == "edital" and cint(doc.edital_publicado) and not final):
		_apagar(drive, doc.get(campo_doc))
		_apagar(drive, doc.get(campo_pdf))
	valores = {campo_doc: link_do_doc(documento_id), campo_pdf: link_pdf}
	if tipo == "edital":
		valores["edital_final_gerado"] = 1 if final else 0
	frappe.db.set_value(c.DOCTYPE_ASSEMBLEIA, assembleia, valores, update_modified=False)
	# Commit explícito: os arquivos já existem no Drive; perder os links faria a próxima
	# geração deixar órfãos na pasta.
	frappe.db.commit()  # nosemgrep
	return pdf


def baixar_pdf_existente(link: str) -> bytes:
	conteudo, _nome, _tipo = download_file(link)
	return conteudo
