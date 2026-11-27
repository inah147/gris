"""Prepara as assembleias: papel, catálogo de acessos e os padrões das configurações.

Só preenche o que está vazio. Textos, pautas e números já editados pela gestão ficam como
estão, então o patch pode rodar de novo sem desfazer nada.
"""

from __future__ import annotations

import frappe
from frappe.utils import cint

from gris.api.assembleias import constantes as c

ROLE = c.ROLE_GESTOR_ASSEMBLEIAS

NUMEROS_PADRAO = {
	"dias_limite_edital": 30,
	"idade_minima_voto_jovem": 16,
	"idade_minima_representacao_meses": 78,
	"vagas_comissao_fiscal": 3,
	"suplentes_comissao_fiscal": 3,
	"associados_por_delegado": 50,
	"prazo_diretoria_valor": 8,
	"prazo_comissao_fiscal_valor": 8,
	"prazo_delegado_valor": 1,
	"prazo_assuntos_gerais_valor": 2,
}

UNIDADES_PADRAO = {
	"prazo_mesa_unidade": c.PRAZO_SEM_LIMITE,
	"prazo_diretoria_unidade": c.PRAZO_DIAS,
	"prazo_comissao_fiscal_unidade": c.PRAZO_DIAS,
	"prazo_delegado_unidade": c.PRAZO_HORAS,
	"prazo_assuntos_gerais_unidade": c.PRAZO_HORAS,
}

# Só gravados quando o Single nunca foi salvo: depois disso, 0 é uma escolha da gestão.
CHECKS_PADRAO = {
	"voto_escotistas": 1,
	"voto_dirigentes": 1,
	"voto_demais_associados": 1,
	"exigir_registro_ativo": 1,
	"voto_jovens": 1,
	"voto_representado_por_responsavel": 1,
	"manter_aberto_sem_candidatos": 1,
	"edital_incluir_links": None,
}

TEXTOS_PADRAO = {
	"texto_topo_edital": c.TEXTO_TOPO_EDITAL,
	"texto_rodape_edital": c.TEXTO_RODAPE_EDITAL,
	"orientacoes_gerais": c.ORIENTACOES_GERAIS,
	"modelo_ata": c.MODELO_ATA,
}


def execute():
	_criar_papel()
	_semear_catalogo()
	if frappe.db.exists("DocType", c.DOCTYPE_CONFIGURACOES):
		preencher_configuracoes()


def _criar_papel() -> None:
	if frappe.db.exists("Role", ROLE):
		return
	frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 0}).insert(ignore_permissions=True)


def _semear_catalogo() -> None:
	"""Item do papel no portal de Acessos; o semeador só insere o que falta."""
	from gris.patches.semear_catalogo_de_acessos import _semear_papeis

	_semear_papeis()


def _local_padrao() -> str:
	uel = frappe.get_single("Definicao da UEL")
	if not uel.rua:
		return "nossa sede"
	endereco = ", ".join(parte for parte in (uel.rua, uel.numero) if parte)
	if uel.bairro:
		endereco = f"{endereco} - {uel.bairro}"
	return f"nossa sede, {endereco}"


def preencher_configuracoes() -> None:
	doc = frappe.get_single(c.DOCTYPE_CONFIGURACOES)
	nunca_salvo = not frappe.db.exists("Singles", {"doctype": c.DOCTYPE_CONFIGURACOES})

	for campo, valor in TEXTOS_PADRAO.items():
		if not (doc.get(campo) or "").strip():
			doc.set(campo, valor)
	for campo, valor in NUMEROS_PADRAO.items():
		if not cint(doc.get(campo)):
			doc.set(campo, valor)
	for campo, valor in UNIDADES_PADRAO.items():
		if not doc.get(campo):
			doc.set(campo, valor)
	if nunca_salvo:
		for campo, valor in CHECKS_PADRAO.items():
			if valor is not None and doc.meta.has_field(campo):
				doc.set(campo, valor)
	if not (doc.local_padrao or "").strip():
		doc.local_padrao = _local_padrao()
	if not (doc.cidade or "").strip():
		doc.cidade = "Santo André"

	if not doc.materiais:
		for item in c.MATERIAIS_PADRAO:
			doc.append("materiais", {"item": item})
	for tabela, itens in (
		("pauta_ordinaria", c.PAUTA_ORDINARIA),
		("pauta_extraordinaria", c.PAUTA_EXTRAORDINARIA),
	):
		if doc.get(tabela):
			continue
		for titulo, tem_votacao, finalidade in itens:
			doc.append(
				tabela,
				{
					"titulo": titulo,
					"tem_votacao": tem_votacao,
					"finalidade": finalidade,
					"orientacao_conducao": c.orientacao_da_finalidade(finalidade),
				},
			)

	# O drive fica de fora da validação: no site novo ele ainda não foi escolhido.
	doc.flags.ignore_permissions = True
	doc.save()
