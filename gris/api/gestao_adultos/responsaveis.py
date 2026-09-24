"""Conselho de Responsáveis no organograma.

Todo `Responsavel` do cadastro aparece no organograma, numa área própria que não responde
para nenhuma outra, com a função fixa de Responsável Legal.

Os nós são **derivados**, não gravados: nenhuma linha de `Funcao do Associado` é criada
para responsável, e o `Responsavel` não ganha tabela de funções. Um responsável não é
alocado nem encerrado — ele é responsável enquanto estiver no cadastro —, então gravar
1 linha por pessoa só criaria 114 registros para manter em sincronia com um fato que já
está no banco. O que existe de verdade é a estrutura (a área e a função), porque ela
precisa aparecer no catálogo das telas de administração e no filtro da página.

A árvore dos associados (`montar_arvore`) não é tocada: este módulo devolve um nó pronto
que `obter_organograma` pendura nas raízes.
"""

from __future__ import annotations

import frappe
from frappe import _

from .atribuicoes import pode_gerenciar_funcoes
from .endpoints import _require_authenticated_user

#: Área raiz do conselho. É `name` de `Unidade Organizacional` (autoname `field:area`).
AREA_CONSELHO = "Conselho de Responsáveis"

#: Função fixa de todo responsável legal.
FUNCAO_RESPONSAVEL_LEGAL = "Responsável Legal"

#: Categoria mostrada no selo do card, no lugar da `Associado.categoria`.
LINHA_RESPONSAVEL = "Responsável"

#: Prefixo que separa o espaço de nomes dos dois tipos de pessoa. `Responsavel.name` e
#: `Associado.name` são os dois md5 de CPF: sem prefixo, um clique num responsável
#: marcaria o card do associado homônimo.
PREFIXO_RESPONSAVEL = "responsavel:"
PREFIXO_ASSOCIADO = "associado:"

DESCRICAO_DA_AREA = (
	"Responsáveis legais dos beneficiários. Área mantida automaticamente: todo "
	"responsável do cadastro aparece aqui."
)
DESCRICAO_DA_FUNCAO = "Responsável legal de um ou mais beneficiários da UEL."

PERIODO_DO_RESPONSAVEL = "Enquanto houver vínculo com a UEL"


# ---------------------------------------------------------------------------
# Estrutura fixa
# ---------------------------------------------------------------------------


def garantir_estrutura_do_conselho() -> dict:
	"""Cria (uma vez) a área e a função do conselho, mais o vínculo entre elas.

	Idempotente de propósito: roda num patch e também pode ser chamada de novo sem
	efeito. Marca as duas com `origem_automatica`, que é o que impede a tela de
	administração de renomear ou desativar.
	"""
	criados = {"area": 0, "funcao": 0, "vinculo": 0}

	if not frappe.db.exists("Unidade Organizacional", AREA_CONSELHO):
		frappe.get_doc(
			{
				"doctype": "Unidade Organizacional",
				"area": AREA_CONSELHO,
				# Explícito: o conselho é raiz e não responde para ninguém.
				"responde_para": None,
				"ativa": 1,
				"origem_automatica": 1,
				"descricao": DESCRICAO_DA_AREA,
			}
		).insert(ignore_permissions=True)
		criados["area"] = 1

	if not frappe.db.exists("Funcao Voluntario", FUNCAO_RESPONSAVEL_LEGAL):
		frappe.get_doc(
			{
				"doctype": "Funcao Voluntario",
				"titulo": FUNCAO_RESPONSAVEL_LEGAL,
				"categoria": "Colaborador",
				"ativa": 1,
				"origem_automatica": 1,
				"descricao": DESCRICAO_DA_FUNCAO,
			}
		).insert(ignore_permissions=True)
		criados["funcao"] = 1

	if not frappe.db.exists(
		"Funcao da Area",
		{
			"parent": AREA_CONSELHO,
			"parenttype": "Unidade Organizacional",
			"funcao": FUNCAO_RESPONSAVEL_LEGAL,
		},
	):
		area = frappe.get_doc("Unidade Organizacional", AREA_CONSELHO)
		area.append("funcoes", {"funcao": FUNCAO_RESPONSAVEL_LEGAL})
		area.save(ignore_permissions=True)
		criados["vinculo"] = 1

	return criados


# ---------------------------------------------------------------------------
# Montagem do nó (função pura — sem banco, para poder testar direto)
# ---------------------------------------------------------------------------


def montar_no_conselho(responsaveis: list[dict]) -> dict | None:
	"""Devolve o nó de grupo do conselho, ou `None` quando não há responsável nenhum.

	Nasce recolhido (`recolhido: True`): são mais de uma centena de cards, e abrir todos
	de saída empurraria o resto do organograma para fora da tela.
	"""
	filhos = [_no_responsavel(pessoa) for pessoa in responsaveis if pessoa.get("name")]
	if not filhos:
		return None

	filhos.sort(key=lambda no: no["nome"])
	return {
		"tipo": "grupo",
		"id": f"area:{AREA_CONSELHO}",
		"nome": AREA_CONSELHO,
		"ordem": 0,
		"membros": len(filhos),
		"recolhido": True,
		"children": filhos,
	}


def _no_responsavel(pessoa: dict) -> dict:
	from .organograma import _iniciais

	nome = pessoa.get("nome_completo") or pessoa.get("name")
	return {
		"tipo": "pessoa",
		"tipo_pessoa": "responsavel",
		"id": f"{PREFIXO_RESPONSAVEL}{pessoa['name']}@@{AREA_CONSELHO}",
		"pessoa": f"{PREFIXO_RESPONSAVEL}{pessoa['name']}",
		"responsavel": pessoa["name"],
		"associado": None,
		"nome": nome,
		"area": AREA_CONSELHO,
		"outras_areas": [],
		"funcao_interna": FUNCAO_RESPONSAVEL_LEGAL,
		"linha": LINHA_RESPONSAVEL,
		"ramo": None,
		"ramo_slug": None,
		"secao": None,
		"avatar_url": None,
		"iniciais": _iniciais(nome),
		"lidera_area": None,
		"diretos": 0,
		"indiretos": 0,
		"children": [],
	}


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------


def listar_membros_do_conselho() -> list[dict]:
	"""Todo mundo do cadastro de `Responsavel`, em ordem de nome."""
	return frappe.get_all(
		"Responsavel",
		fields=["name", "nome_completo"],
		order_by="nome_completo asc",
	)


@frappe.whitelist()
def obter_detalhe_do_responsavel(responsavel: str) -> dict:
	"""Painel lateral de um responsável. Só leitura — o nó é automático.

	O contato sai apenas para quem tem papel de gestão. A página é aberta a qualquer
	pessoa logada, e o telefone das famílias não é informação do mesmo nível que a dos
	voluntários do quadro.
	"""
	_require_authenticated_user()

	pessoa = frappe.db.get_value(
		"Responsavel", responsavel, ["name", "nome_completo", "celular", "email"], as_dict=True
	)
	if not pessoa:
		frappe.throw(_("Esta pessoa não faz parte do organograma."), frappe.DoesNotExistError)

	from .organograma import _iniciais, _numero_do_whatsapp

	nome = pessoa.get("nome_completo") or pessoa["name"]
	mostra_contato = pode_gerenciar_funcoes()

	return {
		"id": f"{PREFIXO_RESPONSAVEL}{pessoa['name']}",
		"nome": nome,
		"avatar_url": None,
		"iniciais": _iniciais(nome),
		"funcao_principal": FUNCAO_RESPONSAVEL_LEGAL,
		"areas": [AREA_CONSELHO],
		"areas_lideradas": [],
		"linha": LINHA_RESPONSAVEL,
		"ramo": None,
		"ramo_slug": None,
		"secao": None,
		"whatsapp": _numero_do_whatsapp(pessoa.get("celular")) if mostra_contato else None,
		# O nó é automático: não há ficha do organograma para abrir, nem ação de escrita.
		"permite_ficha": False,
		"somente_leitura": True,
		"funcoes": [
			{
				"titulo": FUNCAO_RESPONSAVEL_LEGAL,
				"area": AREA_CONSELHO,
				"principal": True,
				"atual": True,
				"periodo": PERIODO_DO_RESPONSAVEL,
				"descricao": DESCRICAO_DA_FUNCAO,
				"responsabilidades": [],
				"atv": None,
			}
		],
	}
