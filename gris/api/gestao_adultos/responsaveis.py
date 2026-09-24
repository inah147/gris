"""Conselho de Responsáveis no organograma.

Todo responsável legal aparece no organograma, numa área própria que não responde para
nenhuma outra, com a função fixa de Responsável Legal. A área existe de verdade
(`garantir_estrutura_do_conselho`), porque precisa aparecer no catálogo das telas de
administração e no filtro da página.

**Os membros entram por dois regimes**, conforme a pessoa tenha ou não cadastro de
associado:

- Quem só é `Responsavel` rende um nó **derivado**: nada é gravado. Um responsável não é
  alocado nem encerrado — ele é responsável enquanto estiver no cadastro —, então gravar
  uma linha por pessoa só criaria registros para manter em sincronia com um fato que já
  está no banco. E o `Responsavel` não tem tabela de funções para receber a linha.
- Quem também é `Associado` recebe uma linha **gravada** em `funcoes_internas`
  (`garantir_funcao_do_conselho`), porque aí a função acumula com as outras da pessoa: ela
  aparece na ficha, nas telas de alocação e no organograma pelo caminho normal de
  `montar_arvore`. Quem grava é `gris.api.pessoas`, que é quem sabe que as duas pessoas são
  uma só.

Daí a mescla em `obter_organograma`: os derivados são pendurados no mesmo nó de grupo que a
árvore já montou para a área, e `listar_membros_do_conselho` exclui quem migrou — senão a
mesma pessoa apareceria duas vezes, uma de cada regime.
"""

from __future__ import annotations

from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from . import identidade
from .atribuicoes import pode_gerenciar_funcoes
from .endpoints import _require_authenticated_user

#: Área raiz do conselho. É `name` de `Unidade Organizacional` (autoname `field:area`).
AREA_CONSELHO = "Conselho de Responsáveis"

#: Função fixa de todo responsável legal.
FUNCAO_RESPONSAVEL_LEGAL = "Responsável Legal"

#: Categoria mostrada no selo do card, no lugar da `Associado.categoria`.
LINHA_RESPONSAVEL = "Responsável"

#: Reexportados de `identidade`, que é onde a chave com espaço de nomes mora agora que ela
#: também identifica a pessoa por dentro da montagem da árvore.
PREFIXO_RESPONSAVEL = identidade.PREFIXO_RESPONSAVEL
PREFIXO_ASSOCIADO = identidade.PREFIXO_ASSOCIADO

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
# Função gravada, para quem também é associado
# ---------------------------------------------------------------------------


def _linhas_do_conselho(doc) -> list:
	return [
		linha
		for linha in (doc.funcoes_internas or [])
		if linha.funcao == FUNCAO_RESPONSAVEL_LEGAL and linha.area == AREA_CONSELHO
	]


def _em_vigor(linha) -> bool:
	"""Mesmo corte do resto do organograma: só está encerrada a linha cuja data já passou."""
	return not linha.data_fim or getdate(linha.data_fim) >= getdate()


def garantir_funcao_do_conselho(doc) -> bool:
	"""Acrescenta ao `Associado` a função de Responsável Legal no conselho, se faltar.

	Recebe o **documento** e só o altera, sem gravar: quem chama junta esta mudança com a
	cópia do perfil e salva uma vez só. Devolve se mexeu em alguma linha.

	Nunca marca `principal` — a função do quadro de voluntários continua sendo a que o card
	do organograma mostra. E a duplicata é conferida aqui porque a gravação é direta: a
	trava de `atribuir_funcao` só vale para quem passa pelo endpoint.
	"""
	if any(_em_vigor(linha) for linha in _linhas_do_conselho(doc)):
		return False

	# Só depois de saber que a linha vai nascer: sem o vínculo `Funcao da Area` entre os
	# dois, o `validate` do Associado recusaria a gravação. Conferir antes custaria três
	# consultas por pessoa no backfill, para nada.
	garantir_estrutura_do_conselho()

	doc.append(
		"funcoes_internas",
		{
			"funcao": FUNCAO_RESPONSAVEL_LEGAL,
			"area": AREA_CONSELHO,
			"data_inicio": getdate(nowdate()),
		},
	)
	return True


def encerrar_funcao_do_conselho(doc) -> bool:
	"""Fecha a função do conselho quando a pessoa deixa de ter beneficiário.

	Encerra com `data_fim`, não apaga: o histórico de quem já foi responsável legal fica.
	"""
	hoje = getdate(nowdate())
	mudou = False
	for linha in _linhas_do_conselho(doc):
		if _em_vigor(linha):
			# `date`, não string: o `validate` do Associado compara as duas datas direto, e
			# uma string contra o `date` que veio do banco estoura com TypeError. E nunca
			# antes do início, que o mesmo `validate` recusa como período invertido.
			linha.data_fim = max(hoje, getdate(linha.data_inicio)) if linha.data_inicio else hoje
			linha.principal = 0
			mudou = True

	return mudou


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
	"""Quem entra no conselho pelo regime derivado, em ordem de nome.

	Quem migrou para o cadastro de associado fica de fora: essa pessoa já chega ao conselho
	pela linha gravada em `funcoes_internas`, e contá-la aqui também a faria aparecer duas
	vezes na mesma área, uma como card `responsavel:` e outra como card `associado:`.
	"""
	return frappe.get_all(
		"Responsavel",
		filters={"migrado_para_associado": 0},
		fields=["name", "nome_completo"],
		order_by="nome_completo asc",
	)


def funcao_derivada_do_conselho() -> dict:
	"""A linha fixa do Conselho, no formato que o painel e a ficha esperam.

	Sem `linha`: não existe registro por trás dela, e é justamente isso que faz as telas
	tratarem-na como automática — nada de encerrar, editar ou apagar.
	"""
	return {
		"linha": None,
		"titulo": FUNCAO_RESPONSAVEL_LEGAL,
		"area": AREA_CONSELHO,
		"principal": False,
		"atual": True,
		"automatica": True,
		"periodo": PERIODO_DO_RESPONSAVEL,
		"descricao": DESCRICAO_DA_FUNCAO,
		"responsabilidades": [],
		# Acordo de trabalho é por alocação do quadro; o Conselho não é alocação.
		"atv": None,
	}


def funcoes_do_responsavel(responsavel: str, incluir_conselho: bool = True) -> list[dict]:
	"""Funções da pessoa: a derivada do Conselho mais as que foram alocadas a ela.

	As alocadas vêm da mesma grade do associado (`Funcao do Associado`, com
	`parenttype = "Responsavel"`), então a montagem do painel é a mesma — só o acordo de
	trabalho fica de fora, que é documento do quadro de voluntários.
	"""
	from .organograma import _funcao_do_painel

	linhas = frappe.get_all(
		"Funcao do Associado",
		filters={"parent": responsavel, "parenttype": "Responsavel"},
		fields=["name", "funcao", "area", "principal", "data_inicio", "data_fim", "idx"],
		order_by="principal desc, idx asc",
	)

	titulos = [linha["funcao"] for linha in linhas if linha.get("funcao")]
	definicoes = {
		linha["name"]: linha
		for linha in frappe.get_all(
			"Funcao Voluntario", filters={"name": ["in", titulos]}, fields=["name", "descricao"]
		)
	}
	responsabilidades: dict[str, list[dict]] = {}
	if titulos:
		for linha in frappe.get_all(
			"Responsabilidade da Funcao",
			filters={"parent": ["in", titulos], "parenttype": "Funcao Voluntario"},
			fields=["parent", "responsabilidade", "detalhe"],
			order_by="parent asc, idx asc",
		):
			responsabilidades.setdefault(linha["parent"], []).append(linha)

	hoje = getdate()
	alocadas = []
	for linha in linhas:
		funcao = _funcao_do_painel(linha, definicoes, responsabilidades, {}, hoje)
		funcao["automatica"] = False
		# Sem acordo de trabalho para responsável: `atvHtml` não desenha nada com `null`,
		# e uma pendência que ninguém pode resolver seria pior que nenhuma informação.
		funcao["atv"] = None
		alocadas.append(funcao)

	conselho = [funcao_derivada_do_conselho()] if incluir_conselho else []
	return conselho + alocadas


@frappe.whitelist()
def obter_detalhe_do_responsavel(responsavel: str) -> dict:
	"""Painel lateral de um responsável.

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
	pode_gerenciar = pode_gerenciar_funcoes()

	funcoes = funcoes_do_responsavel(pessoa["name"])
	areas = sorted({funcao["area"] for funcao in funcoes if funcao["area"] and funcao["atual"]})
	# A principal é a primeira alocada de verdade; o Conselho é pano de fundo de todo
	# responsável e não descreve o que a pessoa faz no quadro.
	alocadas = [funcao for funcao in funcoes if not funcao["automatica"]]

	return {
		"id": identidade.chave_do_responsavel(pessoa["name"]),
		"nome": nome,
		"avatar_url": None,
		"iniciais": _iniciais(nome),
		"funcao_principal": alocadas[0]["titulo"] if alocadas else FUNCAO_RESPONSAVEL_LEGAL,
		"areas": areas,
		"areas_lideradas": [],
		"linha": LINHA_RESPONSAVEL,
		"ramo": None,
		"ramo_slug": None,
		"secao": None,
		"whatsapp": _numero_do_whatsapp(pessoa.get("celular")) if pode_gerenciar else None,
		"ficha_url": "/associados/responsavel?name=" + quote(str(pessoa["name"])),
		"permite_ficha": True,
		"somente_leitura": not pode_gerenciar,
		"funcoes": funcoes,
	}
