# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Endpoints da gestão de assembleias (portal). Todos exigem quem gerencia (RF-01)."""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, get_time, getdate

from gris.api.assembleias import constantes as c
from gris.api.assembleias.padroes import configuracoes, preencher_padroes
from gris.api.assembleias.permissoes import garantir_gestor_assembleias

TIPOS = (c.TIPO_ORDINARIA, c.TIPO_EXTRAORDINARIA)

# Campos das configurações que o portal edita. O drive fica só no Desk (CA-04.7).
CAMPOS_DE_CONFIGURACAO = (
	"dias_limite_edital",
	"local_padrao",
	"cidade",
	"grupo_diretoria_whatsapp",
	"texto_topo_edital",
	"texto_rodape_edital",
	"orientacoes_gerais",
	"voto_escotistas",
	"voto_dirigentes",
	"voto_demais_associados",
	"exigir_registro_ativo",
	"voto_jovens",
	"idade_minima_voto_jovem",
	"voto_representado_por_responsavel",
	"idade_minima_representacao_meses",
	"voto_por_matilha",
	"voto_por_patrulha_escoteiro",
	"voto_por_patrulha_senior",
	"prazo_mesa_unidade",
	"prazo_mesa_valor",
	"prazo_diretoria_unidade",
	"prazo_diretoria_valor",
	"prazo_comissao_fiscal_unidade",
	"prazo_comissao_fiscal_valor",
	"prazo_delegado_unidade",
	"prazo_delegado_valor",
	"prazo_assuntos_gerais_unidade",
	"prazo_assuntos_gerais_valor",
	"manter_aberto_sem_candidatos",
	"vagas_comissao_fiscal",
	"suplentes_comissao_fiscal",
	"associados_por_delegado",
	"modelo_ata",
)
CAMPOS_DE_ITEM_DE_PAUTA = ("titulo", "tem_votacao", "finalidade", "orientacao_conducao")


def _carregar(payload: str | dict) -> dict:
	if isinstance(payload, dict):
		return payload
	try:
		dados = json.loads(payload or "{}")
	except ValueError:
		frappe.throw(_("Dados inválidos."))
	if not isinstance(dados, dict):
		frappe.throw(_("Dados inválidos."))
	return dados


def _texto(valor) -> str:
	return str(valor or "").strip()


# --------------------------------------------------------------------------------------
# Lista
# --------------------------------------------------------------------------------------


def situacao_do_edital(publicado: int, prazo, hoje) -> str:
	if cint(publicado):
		return "publicado"
	return "vencido" if getdate(prazo) < getdate(hoje) else "rascunho"


def listar_assembleias() -> dict:
	"""Cards da lista, separados em próximas e já realizadas (RF-03)."""
	hoje = getdate()
	dias_limite = cint(configuracoes().dias_limite_edital) or 30
	assembleias = frappe.get_all(
		c.DOCTYPE_ASSEMBLEIA,
		fields=["name", "titulo", "data", "tipo", "local", "hora_primeira_convocacao", "edital_publicado"],
		order_by="data asc",
	)
	nomes = [a.name for a in assembleias]
	candidaturas = _contar_por_assembleia(c.DOCTYPE_CANDIDATURA, nomes)
	chapas = _contar_por_assembleia(c.DOCTYPE_CHAPA, nomes)
	assuntos = _contar_por_assembleia(c.DOCTYPE_ASSUNTO, nomes, so_ativas=False)

	proximas, realizadas = [], []
	for a in assembleias:
		prazo = add_days(a.data, -dias_limite)
		card = {
			"name": a.name,
			"titulo": a.titulo,
			"data": str(a.data),
			"tipo": a.tipo,
			"local": a.local or "",
			"hora": str(a.hora_primeira_convocacao or "")[:5],
			"prazo_edital": str(prazo),
			"edital": situacao_do_edital(a.edital_publicado, prazo, hoje),
			"etapa": etapa_pela_data(a.edital_publicado, a.data, hoje),
			"candidaturas": candidaturas.get(a.name, 0) + chapas.get(a.name, 0),
			"assuntos": assuntos.get(a.name, 0),
		}
		(proximas if getdate(a.data) >= hoje else realizadas).append(card)
	realizadas.reverse()
	return {"proximas": proximas, "realizadas": realizadas}


def etapa_pela_data(publicado, data, hoje) -> str:
	"""A etapa em que a assembleia está, a mesma regra da página (sem consultas)."""
	if not cint(publicado):
		return "Edital"
	dias = (getdate(data) - getdate(hoje)).days
	if dias > 0:
		return "Inscrições"
	return "Sessão hoje" if dias == 0 else "Ata"


def _contar_por_assembleia(doctype: str, nomes: list[str], so_ativas: bool = True) -> dict[str, int]:
	if not nomes:
		return {}
	filtros = {"assembleia": ["in", nomes]}
	if so_ativas:
		filtros["status"] = "Ativa"
	linhas = frappe.get_all(
		doctype,
		filters=filtros,
		fields=["assembleia", "count(name) as total"],
		group_by="assembleia",
	)
	return {linha.assembleia: cint(linha.total) for linha in linhas}


# --------------------------------------------------------------------------------------
# Criar e excluir
# --------------------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def criar_assembleia(payload: str) -> dict:
	"""Cria a assembleia já com pauta, textos, checklist e vagas (RF-02)."""
	garantir_gestor_assembleias()
	dados = _carregar(payload)

	data = _texto(dados.get("data"))
	tipo = _texto(dados.get("tipo"))
	hora = _texto(dados.get("hora_primeira_convocacao"))
	local = _texto(dados.get("local"))
	if not (data and tipo and hora and local):
		frappe.throw(_("Preencha data, tipo, horário da primeira convocação e local."))
	if tipo not in TIPOS:
		frappe.throw(_("Tipo de assembleia inválido."))
	try:
		data = getdate(data)
		hora = get_time(hora).strftime("%H:%M:%S")
	except Exception:
		frappe.throw(_("Data ou horário inválido."))
	if data < getdate():
		frappe.throw(_("A data da assembleia não pode estar no passado."))

	doc = frappe.new_doc(c.DOCTYPE_ASSEMBLEIA)
	doc.update({"data": data, "tipo": tipo, "hora_primeira_convocacao": hora, "local": local})
	preencher_padroes(doc)
	doc.insert()
	_pedir_pasta(doc)
	return {"name": doc.name, "url": f"/administracao/assembleias/assembleia?name={doc.name}"}


def _pedir_pasta(doc) -> None:
	"""Pasta no Drive em segundo plano (CA-02.3); desligada, só registra o motivo."""
	from gris.api.google_workspace.assembleia_drive import enfileirar_pasta

	if cint(configuracoes().habilitar_pastas_drive):
		enfileirar_pasta(doc.name)
	else:
		doc.db_set(
			"pasta_drive_erro",
			_("As pastas no Drive estão desligadas em Configurações de Assembleias."),
			update_modified=False,
		)


@frappe.whitelist(methods=["POST"])
def excluir_assembleia(name: str) -> dict:
	"""Apaga a assembleia e as inscrições dela; recusa com o edital publicado (CA-02.6)."""
	garantir_gestor_assembleias()
	if not name or not frappe.db.exists(c.DOCTYPE_ASSEMBLEIA, name):
		frappe.throw(_("Assembleia não encontrada."), frappe.DoesNotExistError)
	if cint(frappe.db.get_value(c.DOCTYPE_ASSEMBLEIA, name, "edital_publicado")):
		frappe.throw(
			_("O edital já foi publicado. Para excluir, fale com o administrador do sistema."),
			frappe.PermissionError,
		)
	# O on_trash apaga as inscrições; tudo na mesma transação do request.
	frappe.delete_doc(c.DOCTYPE_ASSEMBLEIA, name)
	return {"ok": True}


def contagem_de_inscricoes(name: str) -> dict[str, int]:
	"""O que a confirmação de exclusão lista (CA-02.5)."""
	return {
		"candidaturas": frappe.db.count(c.DOCTYPE_CANDIDATURA, {"assembleia": name}),
		"chapas": frappe.db.count(c.DOCTYPE_CHAPA, {"assembleia": name}),
		"assuntos": frappe.db.count(c.DOCTYPE_ASSUNTO, {"assembleia": name}),
	}


# --------------------------------------------------------------------------------------
# Configurações
# --------------------------------------------------------------------------------------


def dados_das_configuracoes() -> dict:
	config = configuracoes()
	dados = {campo: config.get(campo) for campo in CAMPOS_DE_CONFIGURACAO}
	for tabela in ("pauta_ordinaria", "pauta_extraordinaria"):
		dados[tabela] = [
			{campo: item.get(campo) for campo in CAMPOS_DE_ITEM_DE_PAUTA} for item in config.get(tabela)
		]
	dados["materiais"] = [item.item for item in config.materiais]
	return dados


@frappe.whitelist(methods=["POST"])
def salvar_configuracoes(payload: str) -> dict:
	"""Grava as configurações do portal; o `validate` do Single confere o conteúdo."""
	garantir_gestor_assembleias()
	dados = _carregar(payload)
	config = configuracoes()
	for campo in CAMPOS_DE_CONFIGURACAO:
		if campo in dados:
			config.set(campo, dados[campo])

	for tabela in ("pauta_ordinaria", "pauta_extraordinaria"):
		if tabela not in dados:
			continue
		itens = [item for item in (dados.get(tabela) or []) if _texto(item.get("titulo"))]
		if not itens:
			frappe.throw(_("A pauta padrão precisa de pelo menos um item."))
		config.set(tabela, [])
		for item in itens:
			finalidade = _texto(item.get("finalidade"))
			if finalidade and finalidade not in c.FINALIDADES:
				frappe.throw(_("Finalidade inválida: {0}.").format(finalidade))
			config.append(
				tabela,
				{
					"titulo": _texto(item.get("titulo")),
					"tem_votacao": 1 if item.get("tem_votacao") else 0,
					"finalidade": finalidade,
					"orientacao_conducao": _texto(item.get("orientacao_conducao")),
				},
			)

	if "materiais" in dados:
		config.set("materiais", [])
		for item in dados.get("materiais") or []:
			if _texto(item):
				config.append("materiais", {"item": _texto(item)})

	config.save()
	return dados_das_configuracoes()


@frappe.whitelist()
def pauta_padrao_com_orientacao(finalidade: str | None = None) -> str:
	"""Orientação sugerida para um item novo, pela finalidade escolhida."""
	garantir_gestor_assembleias()
	return c.orientacao_da_finalidade(finalidade)
