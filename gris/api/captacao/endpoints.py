"""Endpoints da Captação de Recursos, chamados pelas páginas de `/captacao`.

Toda mutação segue a mesma ordem: `perfil_do_usuario()` → checagem de quem pode
(`permissoes`) → transição no documento (que confere se a ação cabe no status) →
`_gravar()`. Ler com `for_update` serializa duas decisões simultâneas sobre o mesmo
projeto: a segunda vê o status já mudado e é recusada.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import flt

from gris.api.google_workspace.captacao_drive import enfileirar_criacao_da_pasta
from gris.captacao_de_recursos.doctype.projeto_de_captacao.projeto_de_captacao import (
	CAMPOS_DE_TEXTO_DO_DETALHAMENTO,
	CATEGORIAS_DE_RECURSO,
	DECISAO_APROVAR,
	DECISAO_ENVIAR_DETALHAMENTO,
	DECISOES_DA_APROVACAO_FINAL,
	ETAPA_APROVACAO_FINAL,
	ETAPA_REVISAO_TECNICA,
	STATUS_APROVADO_INICIALMENTE,
	STATUS_DETALHAVEIS,
	STATUS_PRELIMINAR,
	definir_tabela,
	fotografar,
)
from gris.utils import comentarios

from . import consultas
from .permissoes import (
	Perfil,
	garantir_diretoria,
	garantir_proponente,
	garantir_que_ve,
	garantir_quem_cancela,
	garantir_quem_move,
	garantir_revisor,
	perfil_do_usuario,
)

DOCTYPE = consultas.DOCTYPE
LIMITE_DO_TITULO = 140
LIMITE_DE_TEXTO = 20000
LIMITE_DE_LINHAS = 200


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------


@frappe.whitelist()
def listar_kanban() -> dict:
	return {"ok": True, **consultas.listar_kanban(perfil_do_usuario())}


@frappe.whitelist()
def obter_projeto(name: str) -> dict:
	perfil = perfil_do_usuario()
	doc = _carregar_projeto(name)
	garantir_que_ve(perfil, doc)
	return _resposta(doc, perfil)


# ---------------------------------------------------------------------------
# Ideia e aprovação inicial
# ---------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def submeter_ideia(payload: str) -> dict:
	"""Cria a ideia ou, com `name`, reenvia a que a Diretoria pediu para alterar."""
	perfil = perfil_do_usuario()
	dados = _carregar_json(payload, dict)

	name = _texto(dados.get("name"))
	if name:
		doc = _carregar_projeto(name, para_alterar=True)
		garantir_proponente(perfil, doc)
		_aplicar_ideia(doc, dados)
		doc.reenviar_ideia(perfil.user)
	else:
		# O proponente é preenchido pelo `before_insert` com quem está logado.
		doc = frappe.new_doc(DOCTYPE)
		doc.status = STATUS_PRELIMINAR
		_aplicar_ideia(doc, dados)
		doc.registrar_ideia(perfil.user)

	_gravar(doc)
	return _resposta(doc, perfil)


@frappe.whitelist(methods=["POST"])
def decidir_preliminar(name: str, decisao: str, comentario: str | None = None) -> dict:
	perfil = perfil_do_usuario()
	garantir_diretoria(perfil)
	doc = _carregar_projeto(name, para_alterar=True)

	doc.decidir_preliminar(decisao, comentario or "", perfil.user)
	_gravar(doc)
	if decisao == DECISAO_ENVIAR_DETALHAMENTO:
		enfileirar_criacao_da_pasta(doc.name)
	return _resposta(doc, perfil)


# ---------------------------------------------------------------------------
# Detalhamento
# ---------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def salvar_detalhamento(name: str, payload: str) -> dict:
	perfil = perfil_do_usuario()
	doc = _carregar_projeto(name, para_alterar=True)
	garantir_proponente(perfil, doc)
	_salvar_detalhamento(doc, payload)
	_gravar(doc)
	return _resposta(doc, perfil)


@frappe.whitelist(methods=["POST"])
def enviar_para_revisao(name: str, payload: str | None = None) -> dict:
	"""Salva o que veio do formulário (se veio) e manda para a Relações Institucionais."""
	perfil = perfil_do_usuario()
	doc = _carregar_projeto(name, para_alterar=True)
	garantir_proponente(perfil, doc)
	if payload:
		_salvar_detalhamento(doc, payload)
	doc.enviar_para_revisao(perfil.user)
	_gravar(doc)
	return _resposta(doc, perfil)


@frappe.whitelist(methods=["POST"])
def resolver_pendencia(name: str, decisao: str) -> dict:
	perfil = perfil_do_usuario()
	doc = _carregar_projeto(name, para_alterar=True)
	garantir_proponente(perfil, doc)
	doc.resolver_pendencia(decisao, perfil.user)
	_gravar(doc)
	return _resposta(doc, perfil)


# ---------------------------------------------------------------------------
# Revisão técnica
# ---------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def solicitar_alteracoes(name: str, pedidos: str) -> dict:
	perfil = perfil_do_usuario()
	garantir_revisor(perfil)
	doc = _carregar_projeto(name, para_alterar=True)
	doc.solicitar_alteracoes(ETAPA_REVISAO_TECNICA, _pedidos(pedidos), perfil.user)
	_gravar(doc)
	return _resposta(doc, perfil)


@frappe.whitelist(methods=["POST"])
def alterar_manualmente(name: str, payload: str, motivo: str) -> dict:
	perfil = perfil_do_usuario()
	garantir_revisor(perfil)
	doc = _carregar_projeto(name, para_alterar=True)

	antes = fotografar(doc)
	dados = _carregar_json(payload, dict)
	_aplicar_ideia(doc, dados, parcial=True)
	_aplicar_detalhamento(doc, dados)
	doc.registrar_alteracao_manual(antes, motivo, perfil.user)
	_gravar(doc)
	return _resposta(doc, perfil)


@frappe.whitelist(methods=["POST"])
def aprovar_revisao(name: str, comentario: str | None = None) -> dict:
	perfil = perfil_do_usuario()
	garantir_revisor(perfil)
	doc = _carregar_projeto(name, para_alterar=True)
	doc.aprovar_revisao(comentario or "", perfil.user)
	_gravar(doc)
	return _resposta(doc, perfil)


# ---------------------------------------------------------------------------
# Aprovação final e banco
# ---------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def decidir_aprovacao_final(
	name: str, decisao: str, comentario: str | None = None, pedidos: str | None = None
) -> dict:
	perfil = perfil_do_usuario()
	garantir_diretoria(perfil)
	if decisao not in DECISOES_DA_APROVACAO_FINAL:
		frappe.throw(_("Na aprovação final, a Diretoria aprova ou pede alterações."))
	doc = _carregar_projeto(name, para_alterar=True)

	if decisao == DECISAO_APROVAR:
		doc.aprovar_final(comentario or "", perfil.user)
	else:
		lista = _pedidos(pedidos) if pedidos else [{"secao": "", "comentario": comentario or ""}]
		doc.solicitar_alteracoes(ETAPA_APROVACAO_FINAL, lista, perfil.user)
	_gravar(doc)
	return _resposta(doc, perfil)


@frappe.whitelist(methods=["POST"])
def cancelar(name: str, motivo: str) -> dict:
	perfil = perfil_do_usuario()
	doc = _carregar_projeto(name, para_alterar=True)
	garantir_quem_cancela(perfil, doc)
	doc.cancelar(motivo, perfil.user)
	_gravar(doc)
	return _resposta(doc, perfil)


@frappe.whitelist(methods=["POST"])
def mover_card(name: str, status: str) -> dict:
	perfil = perfil_do_usuario()
	garantir_quem_move(perfil)
	doc = _carregar_projeto(name, para_alterar=True)
	if doc.mover_para(status, perfil.user):
		_gravar(doc)
	return {"ok": True, "name": doc.name, "status": doc.status}


# ---------------------------------------------------------------------------
# Comentários livres
# ---------------------------------------------------------------------------


@frappe.whitelist()
def listar_comentarios(name: str) -> dict:
	perfil = perfil_do_usuario()
	garantir_que_ve(perfil, _carregar_projeto(name))
	return {"ok": True, "comentarios": comentarios.listar(DOCTYPE, name, perfil.user)}


@frappe.whitelist(methods=["POST"])
def comentar(name: str, texto: str) -> dict:
	perfil = perfil_do_usuario()
	garantir_que_ve(perfil, _carregar_projeto(name))
	comentarios.adicionar(DOCTYPE, name, texto)
	return {"ok": True, "comentarios": comentarios.listar(DOCTYPE, name, perfil.user)}


@frappe.whitelist(methods=["POST"])
def editar_comentario(name: str, comentario: str, texto: str) -> dict:
	perfil = perfil_do_usuario()
	garantir_que_ve(perfil, _carregar_projeto(name))
	comentarios.editar(DOCTYPE, name, comentario, texto)
	return {"ok": True, "comentarios": comentarios.listar(DOCTYPE, name, perfil.user)}


@frappe.whitelist(methods=["POST"])
def apagar_comentario(name: str, comentario: str) -> dict:
	perfil = perfil_do_usuario()
	garantir_que_ve(perfil, _carregar_projeto(name))
	comentarios.apagar(DOCTYPE, name, comentario)
	return {"ok": True, "comentarios": comentarios.listar(DOCTYPE, name, perfil.user)}


# ---------------------------------------------------------------------------
# Apoio
# ---------------------------------------------------------------------------


def _carregar_projeto(name: str, para_alterar: bool = False):
	name = _texto(name)
	if not name or not frappe.db.exists(DOCTYPE, name):
		frappe.throw(_("Projeto de captação não encontrado."), frappe.DoesNotExistError)
	return frappe.get_doc(DOCTYPE, name, for_update=para_alterar)


def _gravar(doc) -> None:
	# `ignore_permissions`: quem pode agir já foi decidido pela lotação em
	# `permissoes`; o DocType só dá permissão ao System Manager de propósito.
	doc.save(ignore_permissions=True)


def _resposta(doc, perfil: Perfil) -> dict:
	return {
		"ok": True,
		"projeto": consultas.serializar_projeto(doc, perfil),
		"versoes": consultas.historico_de_versoes(doc.name) if not doc.is_new() else [],
	}


def _aplicar_ideia(doc, dados: dict, parcial: bool = False) -> None:
	"""Título, resumo, tipo e objetivos. `parcial`: só o que veio no payload."""
	if not parcial or "titulo" in dados:
		titulo = _texto(dados.get("titulo"))
		if not titulo:
			frappe.throw(_("Informe o título do projeto."))
		if len(titulo) > LIMITE_DO_TITULO:
			frappe.throw(_("O título passou de {0} caracteres.").format(LIMITE_DO_TITULO))
		doc.titulo = titulo

	if not parcial or "resumo" in dados:
		resumo = _texto_longo(dados.get("resumo"), _("Resumo"))
		if not resumo:
			frappe.throw(_("Escreva o resumo do projeto."))
		doc.resumo = resumo

	if not parcial or "tipo_projeto" in dados:
		tipo = _texto(dados.get("tipo_projeto"))
		if not tipo or not frappe.db.get_value(consultas.DOCTYPE_TIPO, {"name": tipo, "ativo": 1}):
			frappe.throw(_("Escolha o tipo de projeto."))
		doc.tipo_projeto = tipo

	if not parcial or "objetivos" in dados:
		objetivos = []
		for linha in _linhas(dados.get("objetivos")):
			objetivo = _texto_longo(linha.get("objetivo"), _("Objetivo"))
			if objetivo:
				objetivos.append(
					{
						"objetivo": objetivo,
						"metrica_de_sucesso": _texto_longo(linha.get("metrica_de_sucesso"), _("Métrica")),
					}
				)
		if not objetivos:
			frappe.throw(_("Liste ao menos um objetivo."))
		definir_tabela(doc, "objetivos", objetivos)


def _salvar_detalhamento(doc, payload: str) -> None:
	if doc.status not in STATUS_DETALHAVEIS:
		frappe.throw(_("O detalhamento só pode ser editado depois que a ideia é aprovada."))
	dados = _carregar_json(payload, dict)
	# No detalhamento o proponente revisa os objetivos da ideia; o resto da ideia fica.
	if "objetivos" in dados:
		_aplicar_ideia(doc, {"objetivos": dados["objetivos"]}, parcial=True)
	_aplicar_detalhamento(doc, dados)
	if doc.status == STATUS_APROVADO_INICIALMENTE:
		doc.iniciar_detalhamento()


def _aplicar_detalhamento(doc, dados: dict) -> None:
	"""Só o que veio no payload: rascunho parcial é permitido; a completude é do envio."""
	for campo in CAMPOS_DE_TEXTO_DO_DETALHAMENTO:
		if campo in dados:
			doc.set(campo, _texto_longo(dados.get(campo), campo))

	if "equipe" in dados:
		definir_tabela(
			doc,
			"equipe",
			[
				{
					"nome": _texto(linha.get("nome"))[:140],
					"papel": _texto(linha.get("papel"))[:140],
					"apresentacao": _texto_longo(linha.get("apresentacao"), _("Apresentação")),
				}
				for linha in _linhas(dados.get("equipe"))
				if _texto(linha.get("nome")) or _texto(linha.get("apresentacao"))
			],
		)

	if "atividades" in dados:
		definir_tabela(
			doc,
			"atividades",
			[
				{
					"atividade": _texto(linha.get("atividade"))[:140],
					"dia_inicio": _dia(linha.get("dia_inicio"), _("Dia de início")),
					"dia_termino": _dia(linha.get("dia_termino"), _("Dia de término")),
					"descricao": _texto_longo(linha.get("descricao"), _("Descrição da atividade")),
				}
				for linha in _linhas(dados.get("atividades"))
				if _texto(linha.get("atividade")) or _texto(linha.get("descricao"))
			],
		)

	if "recursos" in dados:
		recursos = []
		for linha in _linhas(dados.get("recursos")):
			descricao = _texto(linha.get("descricao"))[:140]
			if not descricao:
				continue
			categoria = _texto(linha.get("categoria"))
			if categoria and categoria not in CATEGORIAS_DE_RECURSO:
				frappe.throw(_("Categoria de recurso inválida: {0}.").format(categoria))
			recursos.append(
				{
					"categoria": categoria or None,
					"descricao": descricao,
					"quantidade": flt(
						linha.get("quantidade") if linha.get("quantidade") not in (None, "") else 1
					),
					"valor_unitario": flt(linha.get("valor_unitario")),
				}
			)
		definir_tabela(doc, "recursos", recursos)


def _pedidos(pedidos: str | list) -> list[dict]:
	return [
		{
			"secao": _texto(pedido.get("secao")),
			"comentario": _texto_longo(pedido.get("comentario"), _("Pedido")),
		}
		for pedido in _linhas(_carregar_json(pedidos, list))
	]


def _carregar_json(valor, tipo):
	if isinstance(valor, tipo):
		return valor
	try:
		dados = json.loads(valor or ("{}" if tipo is dict else "[]"))
	except (TypeError, ValueError):
		frappe.throw(_("Dados inválidos."))
	if not isinstance(dados, tipo):
		frappe.throw(_("Dados inválidos."))
	return dados


def _linhas(valor) -> list[dict]:
	if not isinstance(valor, list):
		return []
	if len(valor) > LIMITE_DE_LINHAS:
		frappe.throw(_("Linhas demais numa só tabela."))
	return [linha for linha in valor if isinstance(linha, dict)]


def _texto(valor) -> str:
	return str(valor or "").strip()


def _texto_longo(valor, rotulo: str) -> str:
	texto = _texto(valor)
	if len(texto) > LIMITE_DE_TEXTO:
		frappe.throw(_("{0}: texto longo demais.").format(rotulo))
	return texto


def _dia(valor, rotulo: str) -> int:
	"""Dia do cronograma: inteiro a partir de 0. Vazio vira 0 (o campo não guarda vazio)."""
	texto = _texto(valor)
	if not texto:
		return 0
	try:
		dia = int(texto)
	except (TypeError, ValueError):
		frappe.throw(_("{0}: informe um número inteiro de dias.").format(rotulo))
	if dia < 0:
		frappe.throw(_("{0}: o cronograma começa no dia 0.").format(rotulo))
	return dia
