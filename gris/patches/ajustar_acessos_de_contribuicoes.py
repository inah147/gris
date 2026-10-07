"""Contribuições mensais no portal de acessos: por seção, só para associados e aprovadas
pela diretoria financeira.

* "Contribuições da seção" passa a ser concedido por seção: quem pede escolhe a seção e
  vê só os beneficiários dela (`gris.api.acessos.secoes`).
* Os três acessos de contribuição ficam só para associados: um responsável vê as
  contribuições dos filhos em /responsavel/contribuicoes e não pode pedir as dos outros.
* Quem aprova passa a ser o Gestor Contribuição Mensal (a diretoria financeira), que segue
  com o acesso total.

Respeita o que a gestão de acessos já mudou: textos e etapas só são trocados quando ainda
são os da semeadura original.
"""

import frappe

from gris.api.acessos.constantes import ACESSO_DOCTYPE, ROLE_GESTOR, TIPO_PAPEL

ROLE_GESTOR_CONTRIBUICAO = "Gestor Contribuição Mensal"
ROLE_VISUALIZADOR = "Visualizador Contribuição Mensal"
ROLE_VISUALIZADOR_SECAO = "Visualizador Contribuição Mensal da Seção"

ETAPA_FINANCEIRO = {"papel_aprovador": ROLE_GESTOR_CONTRIBUICAO, "descricao": "Diretoria financeira"}

# papel -> {campo: (texto antigo da semeadura, texto novo)}
TEXTOS = {
	ROLE_VISUALIZADOR: {
		"descricao": (
			"Consulta às contribuições mensais de todos os associados.",
			"Consulta às contribuições mensais de todas as seções do grupo.",
		),
		"o_que_muda": (
			"Libera /financeiro/contribuicoes para ver quem está em dia, em aberto ou em atraso, sem cobrar.",
			"Libera /financeiro/contribuicoes com todas as seções, para ver quem está em dia, em aberto ou em atraso, sem cobrar.",
		),
	},
	ROLE_VISUALIZADOR_SECAO: {
		"descricao": (
			"Consulta às contribuições dos associados da sua seção.",
			"Consulta às contribuições mensais dos beneficiários de uma seção.",
		),
		"o_que_muda": (
			"Libera /financeiro/contribuicoes mostrando só a seção que você chefia. Sem uma função de chefe de seção no cadastro, a lista fica vazia.",
			"Você escolhe a seção ao pedir e passa a ver em /financeiro/contribuicoes só os beneficiários dela, sem cobrar. Para ver outra seção, faça outro pedido. Quem é chefe de seção já vê a própria seção pelo perfil.",
		),
	},
}


def _so_etapa_padrao(doc) -> bool:
	etapas = doc.etapas_aprovacao or []
	return len(etapas) == 1 and etapas[0].papel_aprovador == ROLE_GESTOR


def execute():
	frappe.reload_doc("gris", "doctype", "acesso")
	frappe.reload_doc("gris", "doctype", "solicitacao_de_acesso")
	frappe.reload_doc("gris", "doctype", "acesso_por_secao")

	for papel in (ROLE_VISUALIZADOR, ROLE_VISUALIZADOR_SECAO, ROLE_GESTOR_CONTRIBUICAO):
		nome = frappe.db.get_value(ACESSO_DOCTYPE, {"tipo": TIPO_PAPEL, "papel": papel}, "name")
		if not nome:
			continue
		doc = frappe.get_doc(ACESSO_DOCTYPE, nome)
		doc.exige_associado = 1
		if papel == ROLE_VISUALIZADOR_SECAO:
			doc.por_secao = 1
		for campo, (antigo, novo) in TEXTOS.get(papel, {}).items():
			if (doc.get(campo) or "").strip() == antigo:
				doc.set(campo, novo)
		if _so_etapa_padrao(doc) and frappe.db.exists("Role", ROLE_GESTOR_CONTRIBUICAO):
			doc.set("etapas_aprovacao", [])
			doc.append("etapas_aprovacao", ETAPA_FINANCEIRO)
		doc.save(ignore_permissions=True)
