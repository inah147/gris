"""Leitura da Captação de Recursos: kanban, projeto, histórico e documentos."""

from __future__ import annotations

import json

import frappe
from frappe.utils import cint, flt

from gris.api.administracao.documentos import DOCUMENTOS_PARA_CAPTACAO, listar_documentos
from gris.captacao_de_recursos.doctype.projeto_de_captacao.projeto_de_captacao import (
	CAMPOS_DAS_TABELAS,
	CAMPOS_DE_TEXTO_DO_DETALHAMENTO,
	ETAPA_APROVACAO_FINAL,
	ETAPA_APROVACAO_INICIAL,
	ETAPA_REVISAO_TECNICA,
	SECOES,
	STATUS_APROVACAO_FINAL,
	STATUS_CANCELAVEIS,
	STATUS_DE_CAPTACAO,
	STATUS_DETALHAVEIS,
	STATUS_ORDENADOS,
	STATUS_PRELIMINAR,
	STATUS_REVISAO_TECNICA,
)

from .permissoes import Perfil, eh_proponente

DOCTYPE = "Projeto de Captacao"
DOCTYPE_TIPO = "Tipo de Projeto de Captacao"

#: Campos de conteúdo que o `Version` registra. `status` e `decisoes` ficam de fora:
#: já aparecem, com motivo, na linha do tempo das decisões.
ROTULOS_DE_CAMPO = {
	**SECOES,
	"tipo_projeto": "Tipo de projeto",
}


def tipos_de_projeto() -> list[dict]:
	return frappe.get_all(
		DOCTYPE_TIPO,
		filters={"ativo": 1},
		fields=["name as value", "tipo as label", "descricao"],
		order_by="tipo asc",
	)


# ---------------------------------------------------------------------------
# Kanban
# ---------------------------------------------------------------------------


def listar_kanban(perfil: Perfil) -> dict:
	filtros: dict = {}
	if not perfil.ve_o_banco:
		filtros["proponente_user"] = perfil.user

	projetos = frappe.get_all(
		DOCTYPE,
		filters=filtros,
		fields=["name", "titulo", "status", "tipo_projeto", "proponente_nome", "valor_total", "modified"],
		order_by="modified desc",
		limit_page_length=1000,
	)
	pendencias = _pendencias_por_projeto([p.name for p in projetos])

	colunas = {status: [] for status in STATUS_ORDENADOS}
	for projeto in projetos:
		colunas.setdefault(projeto.status, []).append(
			{
				"name": projeto.name,
				"titulo": projeto.titulo,
				"tipo": projeto.tipo_projeto,
				"proponente": projeto.proponente_nome,
				"valor_total": flt(projeto.valor_total),
				"pendencias": pendencias.get(projeto.name, 0),
				"atualizado_em": str(projeto.modified),
			}
		)

	return {
		"colunas": [
			{
				"status": status,
				"cards": colunas.get(status, []),
				"aceita_arraste": status in STATUS_DE_CAPTACAO,
			}
			for status in STATUS_ORDENADOS
		],
		"pode_mover": perfil.move_cards,
		"ve_o_banco": perfil.ve_o_banco,
	}


def _pendencias_por_projeto(nomes: list[str]) -> dict[str, int]:
	if not nomes:
		return {}
	contagem: dict[str, int] = {}
	for linha in frappe.get_all(
		"Decisao de Projeto de Captacao",
		filters={
			"parenttype": DOCTYPE,
			"parent": ["in", nomes],
			"decisao": "Solicitar alteração",
			"resolvido": 0,
		},
		fields=["parent"],
	):
		contagem[linha.parent] = contagem.get(linha.parent, 0) + 1
	return contagem


# ---------------------------------------------------------------------------
# Projeto
# ---------------------------------------------------------------------------


def serializar_projeto(doc, perfil: Perfil) -> dict:
	return {
		"name": doc.name,
		"titulo": doc.titulo,
		"status": doc.status,
		"tipo_projeto": doc.tipo_projeto,
		"resumo": doc.resumo or "",
		"proponente": {
			"nome": doc.proponente_nome,
			"user": doc.proponente_user,
			"tipo": doc.proponente_tipo,
			"tipo_rotulo": {"Associado": "Associado", "Responsavel": "Responsável"}.get(
				doc.proponente_tipo or "", ""
			),
		},
		"criado_em": str(doc.creation) if doc.creation else None,
		"link_pasta_google_drive": doc.link_pasta_google_drive or "",
		"aprovado_inicialmente_em": str(doc.aprovado_inicialmente_em)
		if doc.aprovado_inicialmente_em
		else None,
		"aprovado_final_em": str(doc.aprovado_final_em) if doc.aprovado_final_em else None,
		"categoria_encerramento": doc.categoria_encerramento or "",
		"motivo_encerramento": doc.motivo_encerramento or "",
		"valor_total": flt(doc.valor_total),
		**{campo: doc.get(campo) or "" for campo in CAMPOS_DE_TEXTO_DO_DETALHAMENTO},
		**{
			tabela: [
				{coluna: _json(linha.get(coluna)) for coluna in colunas} for linha in doc.get(tabela) or []
			]
			for tabela, colunas in CAMPOS_DAS_TABELAS.items()
		},
		"recursos_totais": [flt(linha.valor_total) for linha in doc.recursos or []],
		"secoes": [{"campo": campo, "rotulo": rotulo} for campo, rotulo in SECOES.items()],
		"secoes_incompletas": doc.secoes_incompletas(),
		"pendencias": [_serializar_decisao(linha) for linha in doc.pendencias_abertas()],
		"decisoes": [_serializar_decisao(linha) for linha in reversed(doc.decisoes or [])],
		"acoes": acoes_disponiveis(doc, perfil),
	}


def acoes_disponiveis(doc, perfil: Perfil) -> dict[str, bool]:
	"""O que a tela oferece. O endpoint confere de novo; isto só evita botão morto."""
	proponente = perfil.admin or eh_proponente(perfil, doc)
	return {
		"editar_ideia": proponente and doc.status == STATUS_PRELIMINAR,
		"decidir_preliminar": perfil.decide_pela_diretoria and doc.status == STATUS_PRELIMINAR,
		"detalhar": proponente and doc.status in STATUS_DETALHAVEIS,
		"enviar_para_revisao": proponente and doc.status in STATUS_DETALHAVEIS,
		"resolver_pendencias": proponente and doc.status in STATUS_DETALHAVEIS,
		"revisar": perfil.revisa and doc.status == STATUS_REVISAO_TECNICA,
		"aprovacao_final": perfil.decide_pela_diretoria and doc.status == STATUS_APROVACAO_FINAL,
		"cancelar": (perfil.move_cards or eh_proponente(perfil, doc)) and doc.status in STATUS_CANCELAVEIS,
		"mover": perfil.move_cards and doc.status in STATUS_DE_CAPTACAO,
		"comentar": True,
	}


def _serializar_decisao(linha) -> dict:
	return {
		"name": linha.name,
		"data": str(linha.data) if linha.data else None,
		"etapa": linha.etapa,
		"decisao": linha.decisao,
		"secao": linha.secao or "",
		"secao_rotulo": SECOES.get(linha.secao or "", ""),
		"status_anterior": linha.status_anterior or "",
		"status_novo": linha.status_novo or "",
		"comentario": linha.comentario or "",
		"resumo_alteracoes": linha.resumo_alteracoes or "",
		"autor": linha.autor_nome or linha.autor_user or "",
		"resolvido": bool(cint(linha.resolvido)),
		"de_quem": {
			ETAPA_APROVACAO_INICIAL: "Diretoria",
			ETAPA_REVISAO_TECNICA: "Relações Institucionais",
			ETAPA_APROVACAO_FINAL: "Diretoria",
		}.get(linha.etapa, ""),
	}


def historico_de_versoes(name: str) -> list[dict]:
	"""Quem mudou quais partes do projeto, e quando — lido do `Version` (track_changes)."""
	versoes = frappe.get_all(
		"Version",
		filters={"ref_doctype": DOCTYPE, "docname": name},
		fields=["name", "owner", "creation", "data"],
		order_by="creation desc",
		limit_page_length=200,
	)
	nomes = {v.owner for v in versoes}
	nomes_completos = {
		u.name: u.full_name
		for u in frappe.get_all("User", filters={"name": ["in", list(nomes)]}, fields=["name", "full_name"])
	}

	historico = []
	for versao in versoes:
		campos = _campos_alterados(versao.data)
		if not campos:
			continue
		historico.append(
			{
				"data": str(versao.creation),
				"autor": nomes_completos.get(versao.owner) or versao.owner,
				"campos": campos,
			}
		)
	return historico


def _campos_alterados(dados: str | None) -> list[str]:
	try:
		diff = json.loads(dados or "{}")
	except ValueError:
		return []
	campos: list[str] = []
	for alteracao in diff.get("changed") or []:
		campos.append(alteracao[0])
	for chave in ("added", "removed", "row_changed"):
		for alteracao in diff.get(chave) or []:
			campos.append(alteracao[0])
	rotulos = []
	for campo in campos:
		rotulo = ROTULOS_DE_CAMPO.get(campo)
		if rotulo and rotulo not in rotulos:
			rotulos.append(rotulo)
	return rotulos


def documentos_para_captacao() -> list[dict]:
	return listar_documentos(DOCUMENTOS_PARA_CAPTACAO)


def _json(valor):
	if valor is None:
		return ""
	if isinstance(valor, float | int):
		return valor
	return str(valor)
