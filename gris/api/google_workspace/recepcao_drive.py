"""Documentos da recepção no Google Drive.

Os documentos que o responsável envia pelo portal (identificação com foto, declaração de
idoneidade assinada) e a declaração que o sistema gera **não** viram ``File`` do Frappe:
vão direto para pastas do Drive compartilhado do grupo, e o que fica no banco é só o link.

A declaração de idoneidade é montada por cópia do modelo em Google Docs, substituição dos
marcadores pela própria API do Docs e export em PDF. É o Docs que faz a diagramação, então
o texto cai no corpo do papel timbrado sem risco de invadir cabeçalho ou rodapé — o que
aconteceria se o PDF fosse remontado por sobreposição.

A service account é a mesma de ``access_manager``: o escopo ``auth/drive`` que ela já usa é
aceito pela Docs API, então não há credencial nova a configurar.
"""

from __future__ import annotations

import re
from io import BytesIO
from urllib.parse import parse_qs, urlparse

import frappe
from frappe import _
from frappe.utils import cint, format_date, now_datetime
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload

from gris.api.google_workspace.access_manager import (
	_execute_with_retry,
	_get_google_drive_service,
	_motivos_do_erro,
	get_service_account_credentials,
)
from gris.utils.documento import formatar_cpf

SETTINGS_DOCTYPE = "Configuracoes de Recepcao"
RESPONSAVEL_DOCTYPE = "Responsavel"
GOOGLE_DOC_MIMETYPE = "application/vnd.google-apps.document"
PDF_MIMETYPE = "application/pdf"
# Teto do download servido pelo portal: o conteúdo passa inteiro pela memória do worker.
TAMANHO_MAXIMO_DOWNLOAD = 25 * 1024 * 1024

_DOC_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{10,}$")

MESES_PT_BR = (
	"janeiro",
	"fevereiro",
	"março",
	"abril",
	"maio",
	"junho",
	"julho",
	"agosto",
	"setembro",
	"outubro",
	"novembro",
	"dezembro",
)


def _logger():
	return frappe.logger("google_workspace_recepcao_drive", allow_site=True, file_count=10)


# --------------------------------------------------------------------------------------
# Configuração
# --------------------------------------------------------------------------------------


def get_reception_settings():
	return frappe.get_single(SETTINGS_DOCTYPE)


def is_feature_enabled(settings=None) -> bool:
	settings = settings or get_reception_settings()
	return bool(cint(settings.habilitar_documentos_drive))


def assert_feature_enabled(settings=None):
	"""Falha cedo e com mensagem de configuração, não com erro da API do Google."""
	settings = settings or get_reception_settings()

	if not is_feature_enabled(settings):
		frappe.throw(
			_(
				"O envio de documentos para o Google Drive está desabilitado. "
				"Habilite em Configurações de Recepção."
			)
		)

	if not (settings.drive_compartilhado_acesso_restrito or "").strip():
		frappe.throw(_("Drive compartilhado de acesso restrito não configurado."))

	return settings


def _get_drive_scope_params(settings) -> dict[str, str]:
	drive_id = (settings.drive_compartilhado_acesso_restrito or "").strip()
	if not drive_id:
		return {}
	return {"corpora": "drive", "driveId": drive_id}


def _get_docs_service():
	"""Cliente da Docs API sobre a mesma service account do Drive.

	O escopo ``auth/drive`` que ``DRIVE_SCOPES`` já pede é aceito pela Docs API, então não
	há credencial nem consentimento novo a configurar.
	"""
	return build("docs", "v1", credentials=get_service_account_credentials(), static_discovery=False)


# --------------------------------------------------------------------------------------
# Links
# --------------------------------------------------------------------------------------


def extract_google_doc_id(value: str | None) -> str:
	"""ID do documento em uma URL do Google Docs, ou string vazia se não for uma."""
	text = (value or "").strip()
	if not text:
		return ""

	parsed = urlparse(text)
	if parsed.scheme != "https" or parsed.netloc.lower() != "docs.google.com":
		return ""

	path_parts = [part for part in (parsed.path or "").split("/") if part]
	if path_parts[:2] != ["document", "d"] or len(path_parts) < 3:
		return ""

	doc_id = path_parts[2].strip()
	return doc_id if _DOC_ID_PATTERN.fullmatch(doc_id) else ""


def build_drive_file_link(file_id: str) -> str:
	return f"https://drive.google.com/file/d/{file_id}/view"


def extract_drive_file_id(value: str | None) -> str:
	"""ID do arquivo em um link do Drive, nos formatos que a API devolve.

	Cobre ``/file/d/<id>/view`` (o que montamos) e ``?id=<id>`` (o que o ``webViewLink``
	usa para alguns tipos), além do próprio ID solto.
	"""
	text = (value or "").strip()
	if not text:
		return ""

	if _DOC_ID_PATTERN.fullmatch(text):
		return text

	parsed = urlparse(text)
	if parsed.netloc.lower() not in {"drive.google.com", "docs.google.com"}:
		return ""

	partes = [parte for parte in (parsed.path or "").split("/") if parte]
	if "d" in partes:
		indice = partes.index("d")
		if indice + 1 < len(partes):
			candidato = partes[indice + 1].strip()
			if _DOC_ID_PATTERN.fullmatch(candidato):
				return candidato

	candidato = (parse_qs(parsed.query or "").get("id") or [""])[0].strip()
	return candidato if _DOC_ID_PATTERN.fullmatch(candidato) else ""


def download_file(link: str | None) -> tuple[bytes, str, str]:
	"""Baixa um arquivo do Drive pela service account: conteúdo, nome e mimetype.

	É o que permite servir o documento pelo GRIS. O drive é de acesso restrito de
	propósito, então o responsável nunca vai conseguir abrir o link do Drive direto —
	quem tem a credencial é o servidor.
	"""
	file_id = extract_drive_file_id(link)
	if not file_id:
		frappe.throw(_("Arquivo não encontrado no Google Drive."))

	drive = _get_google_drive_service()
	metadata = _execute_with_retry(
		lambda: (
			drive.files()
			.get(fileId=file_id, fields="id,name,mimeType,size", supportsAllDrives=True)
			.execute()
		)
	)

	tamanho = cint((metadata or {}).get("size"))
	if tamanho > TAMANHO_MAXIMO_DOWNLOAD:
		frappe.throw(_("Arquivo grande demais para ser aberto pelo portal."))

	conteudo = _execute_with_retry(lambda: drive.files().get_media(fileId=file_id).execute())
	nome = (metadata or {}).get("name") or "documento"
	mimetype = (metadata or {}).get("mimeType") or "application/octet-stream"
	return conteudo, nome, mimetype


# --------------------------------------------------------------------------------------
# Upload
# --------------------------------------------------------------------------------------


def upload_bytes_to_folder(
	content: bytes,
	filename: str,
	mimetype: str,
	folder_id: str,
	settings=None,
	description: str = "",
) -> str:
	"""Sobe bytes para uma pasta do drive compartilhado e devolve o link de visualização."""
	if not content:
		frappe.throw(_("Arquivo vazio."))
	if not folder_id:
		frappe.throw(_("Pasta de destino não configurada no Google Drive."))

	settings = settings or get_reception_settings()
	drive = _get_google_drive_service()
	media = MediaIoBaseUpload(BytesIO(content), mimetype=mimetype, resumable=False)

	body = {"name": filename, "parents": [folder_id]}
	if description:
		body["description"] = description

	uploaded = _execute_with_retry(
		lambda: (
			drive.files()
			.create(
				body=body,
				media_body=media,
				fields="id,name,webViewLink",
				supportsAllDrives=True,
			)
			.execute()
		)
	)

	file_id = (uploaded or {}).get("id") or ""
	if not file_id:
		raise frappe.ValidationError("Não foi possível determinar o ID do arquivo enviado ao Drive.")

	return (uploaded or {}).get("webViewLink") or build_drive_file_link(file_id)


# --------------------------------------------------------------------------------------
# Declaração de idoneidade
# --------------------------------------------------------------------------------------


def data_por_extenso(data=None) -> str:
	data = data or now_datetime().date()
	return f"{data.day} de {MESES_PT_BR[data.month - 1]} de {data.year}"


def _marcadores_da_declaracao(resp_doc) -> dict[str, str]:
	"""Marcadores do modelo e o que entra no lugar de cada um.

	Os rótulos dizem "Associado" porque o formulário é o oficial da UEB; os dados são
	do responsável, que é quem assina.
	"""
	return {
		"<<Nome do Associado>>": resp_doc.nome_completo or "",
		"<<Data de nascimento do Associado>>": (
			format_date(resp_doc.data_de_nascimento, "dd/MM/yyyy") if resp_doc.data_de_nascimento else ""
		),
		"<<Cidade de Nascimento do Associado>>": resp_doc.cidade_de_nascimento or "",
		"<<UF de nascimento do Associado>>": resp_doc.uf_de_nascimento or "",
		"<<CPF do Associado>>": formatar_cpf(resp_doc.cpf),
		"<<RG do Associado>>": resp_doc.rg or "",
		"<<Data de Início>>": data_por_extenso(),
	}


def _assert_dados_para_declaracao(resp_doc):
	"""Sem estes campos a declaração sai com lacuna e não serve para assinar."""
	obrigatorios = (
		("nome_completo", "nome completo"),
		("data_de_nascimento", "data de nascimento"),
		("cidade_de_nascimento", "cidade de nascimento"),
		("uf_de_nascimento", "UF de nascimento"),
		("cpf", "CPF"),
		("rg", "RG"),
	)
	faltando = [rotulo for campo, rotulo in obrigatorios if not resp_doc.get(campo)]

	if faltando:
		frappe.throw(
			_("Complete os dados de {0} para gerar a declaração: {1}.").format(
				resp_doc.nome_completo or _("responsável"), ", ".join(faltando)
			)
		)


def _template_declaracao_id(settings=None) -> str:
	"""ID do Doc-modelo da declaração, configurado junto do resto do fluxo de recepção."""
	settings = settings or get_reception_settings()
	link = (settings.link_template_declaracao_idoneidade or "").strip()

	doc_id = extract_google_doc_id(link)
	if not doc_id:
		frappe.throw(
			_(
				"Modelo da declaração de idoneidade não configurado. "
				"Informe o link do Google Docs em Configurações de Recepção."
			)
		)
	return doc_id


def _mensagem_de_erro_do_google(exc: HttpError) -> str:
	"""Traduz a falha da API para algo que diga o que fazer a seguir.

	As três causas abaixo são de configuração no Google, não do dado do responsável, e cada
	uma tem um conserto diferente — mostrar "erro ao gerar" para as três deixaria quem
	administra sem pista de onde mexer.
	"""
	motivos = _motivos_do_erro(exc)
	status = getattr(getattr(exc, "resp", None), "status", None)

	if motivos & {"accessnotconfigured", "servicedisabled"}:
		return _(
			"A Google Docs API não está habilitada no projeto do Google Cloud da service account. "
			"Habilite a API e tente de novo em alguns minutos."
		)

	if status == 404:
		return _(
			"Modelo da declaração de idoneidade não encontrado no Google Drive. "
			"Confira o link em Configurações de Recepção."
		)

	if status == 403:
		return _(
			"A service account não tem acesso ao modelo da declaração ou à pasta de destino. "
			"Compartilhe os dois com o e-mail da service account e tente de novo."
		)

	return _("Não foi possível gerar a declaração de idoneidade. Tente novamente em alguns minutos.")


def gerar_declaracao_idoneidade(responsavel_name: str) -> str:
	"""Gera o PDF da declaração no papel timbrado e devolve o link no Drive.

	Idempotente: se o responsável já tem uma declaração gerada, devolve o link guardado
	em vez de criar um segundo arquivo — o botão do portal pode ser clicado várias vezes.
	"""
	if not responsavel_name or not frappe.db.exists(RESPONSAVEL_DOCTYPE, responsavel_name):
		frappe.throw(_("Responsável não encontrado."))

	link_existente = (
		frappe.db.get_value(RESPONSAVEL_DOCTYPE, responsavel_name, "link_declaracao_idoneidade") or ""
	).strip()
	if link_existente:
		return link_existente

	settings = assert_feature_enabled()
	pasta_id = (settings.pasta_declaracoes_nao_assinadas_id or "").strip()
	if not pasta_id:
		frappe.throw(_("Pasta de declarações não assinadas não configurada."))

	resp_doc = frappe.get_doc(RESPONSAVEL_DOCTYPE, responsavel_name)
	_assert_dados_para_declaracao(resp_doc)

	template_id = _template_declaracao_id(settings)
	drive = _get_google_drive_service()
	copia_id = ""

	try:
		nome_arquivo = f"Declaracao de Idoneidade - {resp_doc.nome_completo}"

		copia = _execute_with_retry(
			lambda: (
				drive.files()
				.copy(
					fileId=template_id,
					body={"name": f"{nome_arquivo} (rascunho)", "parents": [pasta_id]},
					fields="id",
					supportsAllDrives=True,
				)
				.execute()
			)
		)
		copia_id = (copia or {}).get("id") or ""
		if not copia_id:
			raise frappe.ValidationError("Não foi possível copiar o modelo da declaração.")

		requests = [
			{
				"replaceAllText": {
					"containsText": {"text": marcador, "matchCase": True},
					"replaceText": valor,
				}
			}
			for marcador, valor in _marcadores_da_declaracao(resp_doc).items()
		]
		docs = _get_docs_service()
		_execute_with_retry(
			lambda: docs.documents().batchUpdate(documentId=copia_id, body={"requests": requests}).execute()
		)

		pdf_bytes = _execute_with_retry(
			lambda: drive.files().export(fileId=copia_id, mimeType=PDF_MIMETYPE).execute()
		)

		link = upload_bytes_to_folder(
			content=pdf_bytes,
			filename=f"{nome_arquivo}.pdf",
			mimetype=PDF_MIMETYPE,
			folder_id=pasta_id,
			settings=settings,
			description=f"Declaração de idoneidade de {resp_doc.nome_completo}",
		)
	except HttpError as exc:
		# Sem isto o portal recebe um 500 com traceback e o responsável não tem o que fazer
		# com a informação; o erro do Google fica no log, para quem administra.
		frappe.log_error(frappe.get_traceback(), f"gerar_declaracao_idoneidade:{responsavel_name}")
		frappe.throw(_mensagem_de_erro_do_google(exc))
	finally:
		# O .gdoc intermediário não interessa a ninguém: some mesmo que o export falhe,
		# senão a pasta de declarações acumula rascunho a cada tentativa.
		if copia_id:
			_descartar_copia(drive, copia_id)

	frappe.db.set_value(
		RESPONSAVEL_DOCTYPE, responsavel_name, "link_declaracao_idoneidade", link, update_modified=True
	)
	# Commit explícito: o PDF já existe no Drive. Perder o link aqui faria a próxima
	# chamada gerar um arquivo duplicado — mesmo cuidado de project_drive.
	frappe.db.commit()  # nosemgrep

	return link


def _descartar_copia(drive, file_id: str) -> None:
	try:
		_execute_with_retry(lambda: drive.files().delete(fileId=file_id, supportsAllDrives=True).execute())
	except HttpError as exc:
		if getattr(getattr(exc, "resp", None), "status", None) == 404:
			return
		_logger().warning("[RECEPCAO DRIVE] rascunho da declaração não removido file=%s", file_id)
	except Exception:
		_logger().warning("[RECEPCAO DRIVE] rascunho da declaração não removido file=%s", file_id)
