"""Gestão dos documentos do portal de transparência, pelo portal.

Antes só dava para cadastrar pelo Desk. Esta página cobre os tipos de `Transparencia`
— cadastrar, corrigir, publicar, despublicar e excluir — e só o `Gestor da UEL` mexe.

Os pareceres da comissão fiscal (anual e trimestral) ficam de fora: são geridos só em
/financeiro/pareceres. Não aparecem na lista, não estão entre os tipos e os endpoints
daqui recusam um parecer que chegue pelo `name`.

A checagem é do papel, e não só da permissão do DocType: `Editor de Parecer` e
`System Manager` também gravam em `Transparencia`, mas a página é da gestão. Depois do
papel, cada gravação passa pela permissão do DocType normalmente (sem
`ignore_permissions`), e por isso o `Gestor da UEL` tem create, write e delete lá.
"""

from __future__ import annotations

import json
from datetime import date

import frappe
from frappe import _
from frappe.utils import getdate

from gris.api.administracao.permissoes import ROLE_GESTOR_UEL

DOCTYPE = "Transparencia"

#: Geridos em /financeiro/pareceres, e só lá.
PARECERES = (
	"Parecer trimestral da comissão fiscal",
	"Parecer anual da comissão fiscal",
)

#: Os mesmos do `depends_on` de `registrado_em_cartorio` no DocType.
TIPOS_COM_CARTORIO = ("Estatuto", "Ata de eleição e posse da diretoria")


# ---------------------------------------------------------------------------
# Permissões
# ---------------------------------------------------------------------------


def pode_gerenciar_transparencia(user: str | None = None) -> bool:
	return ROLE_GESTOR_UEL in frappe.get_roles(user or frappe.session.user)


def garantir_gestor_transparencia() -> None:
	if not pode_gerenciar_transparencia():
		frappe.throw(
			_("Apenas o Gestor da UEL pode alterar os documentos de transparência."),
			frappe.PermissionError,
		)


def _garantir_que_nao_e_parecer(doc) -> None:
	if doc.tipo_arquivo in PARECERES:
		frappe.throw(
			_("Os pareceres da comissão fiscal são geridos na página Pareceres, do Financeiro."),
			frappe.PermissionError,
		)


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------


def tipos_de_documento() -> list[str]:
	"""As opções do Select `tipo_arquivo`, na ordem do DocType, sem os pareceres."""
	opcoes = frappe.get_meta(DOCTYPE).get_field("tipo_arquivo").options or ""
	return [tipo for tipo in opcoes.split("\n") if tipo.strip() and tipo not in PARECERES]


def listar_documentos_transparencia() -> list[dict]:
	# `get_list`: a página é só da gestão, e quem chega aqui tem read no DocType.
	linhas = frappe.get_list(
		DOCTYPE,
		filters={"tipo_arquivo": ["not in", list(PARECERES)]},
		fields=[
			"name",
			"tipo_arquivo",
			"area",
			"ano_referencia",
			"data_emissao",
			"data_validade",
			"registrado_em_cartorio",
			"publicado",
			"arquivo",
			"modified",
		],
		# O ano agrupa a página. (O `data_de_atualização` do DocType tem acento no nome
		# e o Frappe recusa ordenar por ele.)
		order_by="ano_referencia desc, tipo_arquivo asc, creation desc",
		limit_page_length=0,
	)
	return [_serializar(linha) for linha in linhas]


def _serializar(linha) -> dict:
	return {
		"name": linha.name,
		"tipo_arquivo": linha.tipo_arquivo,
		"area": linha.area,
		"ano_referencia": linha.ano_referencia,
		"data_emissao": str(linha.data_emissao) if linha.data_emissao else None,
		"data_validade": str(linha.data_validade) if linha.data_validade else None,
		"registrado_em_cartorio": bool(linha.registrado_em_cartorio),
		"publicado": bool(linha.publicado),
		"arquivo": linha.arquivo,
		"atualizado_em": str(linha.modified) if linha.modified else None,
	}


# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def salvar_documento_transparencia(payload: str) -> dict:
	"""Cadastra um documento novo, ou corrige um existente quando o payload traz `name`."""
	garantir_gestor_transparencia()
	dados = _carregar(payload)

	name = _texto(dados.get("name"))
	doc = frappe.get_doc(DOCTYPE, name) if name else frappe.new_doc(DOCTYPE)
	if name:
		_garantir_que_nao_e_parecer(doc)

	tipo = _texto(dados.get("tipo_arquivo"))
	if tipo not in tipos_de_documento():
		frappe.throw(_("Escolha o tipo do documento."))

	area = _texto(dados.get("area"))
	if area and not frappe.db.exists("Unidade Organizacional", area):
		frappe.throw(_("Área não encontrada."))

	data_emissao = _data(dados.get("data_emissao"), _("Data de emissão"))
	data_validade = _data(dados.get("data_validade"), _("Válido até"))
	if data_emissao and data_validade and data_validade < data_emissao:
		frappe.throw(_("A validade não pode ser anterior à emissão."))

	arquivo = _texto(dados.get("arquivo"))
	if not arquivo:
		frappe.throw(_("Envie o arquivo do documento."))
	# Manter o arquivo que o documento já tem não é um envio novo.
	if arquivo != doc.arquivo:
		_garantir_arquivo_do_usuario(arquivo)

	doc.tipo_arquivo = tipo
	doc.area = area or None
	# O ano não se digita mais: o portal público agrupa por ele e o DocType exige, então
	# sai da emissão. Sem emissão, o documento novo fica no ano do cadastro e o que já
	# existe mantém o seu.
	if data_emissao:
		doc.ano_referencia = data_emissao.year
	elif not name:
		doc.ano_referencia = getdate().year
	doc.data_emissao = data_emissao
	doc.data_validade = data_validade
	doc.registrado_em_cartorio = (
		1 if (tipo in TIPOS_COM_CARTORIO and _booleano(dados.get("registrado_em_cartorio"))) else 0
	)
	doc.publicado = 1 if _booleano(dados.get("publicado")) else 0
	doc.arquivo = arquivo
	if name:
		doc.save()
	else:
		doc.insert()

	return {"ok": True, "name": doc.name, "documentos": listar_documentos_transparencia()}


@frappe.whitelist(methods=["POST"])
def publicar_documento_transparencia(name: str, publicado: bool | int | str) -> dict:
	garantir_gestor_transparencia()
	doc = frappe.get_doc(DOCTYPE, name)
	_garantir_que_nao_e_parecer(doc)
	doc.publicado = 1 if _booleano(publicado) else 0
	doc.save()
	return {"ok": True, "documentos": listar_documentos_transparencia()}


@frappe.whitelist(methods=["POST"])
def excluir_documento_transparencia(name: str) -> dict:
	"""Exclui o documento; o Frappe apaga o anexo junto."""
	garantir_gestor_transparencia()
	_garantir_que_nao_e_parecer(frappe.get_doc(DOCTYPE, name))
	frappe.delete_doc(DOCTYPE, name)
	return {"ok": True, "documentos": listar_documentos_transparencia()}


# ---------------------------------------------------------------------------
# Apoio
# ---------------------------------------------------------------------------


def _garantir_arquivo_do_usuario(file_url: str) -> None:
	"""O link precisa ser de um arquivo que a própria pessoa acabou de enviar.

	Sem isso, qualquer `file_url` conhecido — inclusive de um anexo privado de outro
	documento — viraria anexo público da Transparência.
	"""
	arquivo = frappe.db.get_value(
		"File",
		{"file_url": file_url},
		["owner", "attached_to_name"],
		as_dict=True,
		order_by="creation desc",
	)
	if not arquivo:
		frappe.throw(_("Arquivo não encontrado. Envie o arquivo de novo."))
	if arquivo.owner != frappe.session.user or arquivo.attached_to_name:
		frappe.throw(_("Use um arquivo enviado agora por você."), frappe.PermissionError)


def _carregar(payload: str) -> dict:
	if isinstance(payload, dict):
		return payload
	try:
		dados = json.loads(payload or "{}")
	except (TypeError, ValueError):
		frappe.throw(_("Dados inválidos."))
	if not isinstance(dados, dict):
		frappe.throw(_("Dados inválidos."))
	return dados


def _texto(valor) -> str:
	return str(valor or "").strip()


def _booleano(valor) -> bool:
	if isinstance(valor, str):
		return valor.strip().lower() in ("1", "true", "sim", "on")
	return bool(valor)


def _data(valor, rotulo: str) -> date | None:
	"""Aceita ISO (o que o datepicker do dialog envia) ou `dd/mm/aaaa`."""
	texto = _texto(valor)
	if not texto:
		return None
	try:
		if "/" in texto:
			dia, mes, ano = (int(parte) for parte in texto.split("/"))
			return date(ano, mes, dia)
		return getdate(texto)
	except (TypeError, ValueError):
		frappe.throw(_("{0}: data inválida.").format(rotulo))
