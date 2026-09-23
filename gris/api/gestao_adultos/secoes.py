"""Sincronização das seções do Paxtu com as áreas do organograma.

Toda seção que aparece no cadastro vira uma `Unidade Organizacional`; cada uma
ganha duas `Funcao Voluntario` ("Chefe de Seção — X" e "Assistente de Seção — X"),
e todo escotista da seção recebe uma delas. O chefe vira responsável da área.

Precisa de duas funções por seção porque `Funcao Voluntario.area` é Link único:
não existe uma "Chefe de Seção" genérica que sirva para todas.

A rotina só mexe no que ela mesma criou (`origem_automatica`) — área feita à mão
nunca é tocada. E nada é apagado: área sai por `ativa = 0` e função de pessoa sai
por `data_fim`, para o histórico continuar de pé.
"""

from __future__ import annotations

import frappe
from frappe.utils import getdate, nowdate

from gris.utils.chefes import eh_funcao_chefe_de_secao, normalizar_texto

CATEGORIA_ESCOTISTA = "Escotista"
PAPEL_CHEFE = "Chefe de Seção"
PAPEL_ASSISTENTE = "Assistente de Seção"

#: Travessão que liga o papel ao nome da seção no título da função.
SEPARADOR = " " + chr(0x2014) + " "


def titulo_da_funcao(papel: str, secao: str) -> str:
	return f"{papel}{SEPARADOR}{secao}"


def sincronizar_secoes() -> dict:
	"""Reconcilia áreas, funções e atribuições a partir do campo `secao`.

	Devolve um resumo do que mudou, para o log da importação.
	"""
	associados = frappe.get_all(
		"Associado",
		filters={"status_no_grupo": "Ativo"},
		fields=["name", "nome_completo", "secao", "categoria", "funcao"],
	)
	plano = planejar_secoes(associados)
	if not plano["secoes"]:
		return {"areas_criadas": 0, "funcoes_criadas": 0, "atribuicoes": 0, "encerradas": 0, "avisos": []}

	area_mae = frappe.db.get_single_value("Configuracoes de Associados", "area_mae_das_secoes")
	if area_mae and not frappe.db.exists("Unidade Organizacional", area_mae):
		area_mae = None

	resumo = {
		"areas_criadas": 0,
		"funcoes_criadas": 0,
		"atribuicoes": 0,
		"encerradas": 0,
		"avisos": list(plano["avisos"]),
	}

	for secao in plano["secoes"]:
		resumo["areas_criadas"] += _garantir_area(secao, area_mae)
		for papel in (PAPEL_CHEFE, PAPEL_ASSISTENTE):
			resumo["funcoes_criadas"] += _garantir_funcao(papel, secao)

	automaticas = set(frappe.get_all("Funcao Voluntario", filters={"origem_automatica": 1}, pluck="name"))
	for associado, papel_por_secao in plano["atribuicoes"].items():
		criadas, encerradas = _aplicar_atribuicoes(associado, papel_por_secao, automaticas)
		resumo["atribuicoes"] += criadas
		resumo["encerradas"] += encerradas

	for secao, chefe in plano["responsaveis"].items():
		_definir_responsavel(secao, chefe)

	# Sem commit aqui: quem chama (a importação, num request; o seed, no fim do
	# script) é que fecha a transação.
	return resumo


# ---------------------------------------------------------------------------
# Planejamento (função pura — sem banco, para poder testar direto)
# ---------------------------------------------------------------------------


def planejar_secoes(associados: list[dict]) -> dict:
	"""Decide quais seções existem, quem chefia cada uma e quem entra nelas.

	`secao` é texto livre vindo de planilha, então a comparação é feita sem acento
	nem caixa; o nome que vale é a primeira grafia encontrada.
	"""
	canonico: dict[str, str] = {}
	escotistas_por_secao: dict[str, list[dict]] = {}

	for pessoa in associados:
		secao = (pessoa.get("secao") or "").strip()
		if not secao:
			continue
		chave = normalizar_texto(secao)
		canonico.setdefault(chave, secao)
		if pessoa.get("categoria") == CATEGORIA_ESCOTISTA:
			escotistas_por_secao.setdefault(chave, []).append(pessoa)

	secoes = [canonico[chave] for chave in sorted(canonico)]

	atribuicoes: dict[str, dict[str, str]] = {}
	responsaveis: dict[str, str] = {}
	avisos: list[str] = []

	for chave, nome in canonico.items():
		escotistas = escotistas_por_secao.get(chave, [])
		if not escotistas:
			avisos.append(f"A seção {nome} não tem nenhum escotista ativo.")
			continue

		chefes = [e for e in escotistas if eh_funcao_chefe_de_secao(e.get("funcao"))]
		nomes_dos_chefes = {c["name"] for c in chefes}
		for pessoa in escotistas:
			papel = PAPEL_CHEFE if pessoa["name"] in nomes_dos_chefes else PAPEL_ASSISTENTE
			atribuicoes.setdefault(pessoa["name"], {})[nome] = papel

		if len(chefes) == 1:
			responsaveis[nome] = chefes[0]["name"]
		elif len(chefes) > 1:
			# Responsável é Link único: com dois chefes não dá para escolher sem
			# inventar critério. A área fica sem cabeça e o aviso mostra por quê.
			nomes = ", ".join(sorted(c.get("nome_completo") or c["name"] for c in chefes))
			avisos.append(f"A seção {nome} tem mais de um chefe cadastrado: {nomes}.")
		else:
			avisos.append(f"A seção {nome} não tem chefe cadastrado.")

	return {
		"secoes": secoes,
		"atribuicoes": atribuicoes,
		"responsaveis": responsaveis,
		"avisos": avisos,
	}


# ---------------------------------------------------------------------------
# Aplicação
# ---------------------------------------------------------------------------


def _garantir_area(secao: str, area_mae: str | None) -> int:
	if frappe.db.exists("Unidade Organizacional", secao):
		return 0
	frappe.get_doc(
		{
			"doctype": "Unidade Organizacional",
			"area": secao,
			"responde_para": area_mae,
			"ativa": 1,
			"origem_automatica": 1,
			"descricao": "Seção criada pela sincronização do Paxtu.",
		}
	).insert(ignore_permissions=True)
	return 1


def _garantir_funcao(papel: str, secao: str) -> int:
	titulo = titulo_da_funcao(papel, secao)
	if frappe.db.exists("Funcao Voluntario", titulo):
		return 0
	frappe.get_doc(
		{
			"doctype": "Funcao Voluntario",
			"titulo": titulo,
			"categoria": CATEGORIA_ESCOTISTA,
			"area": secao,
			"ativa": 1,
			"origem_automatica": 1,
			"descricao": f"{papel} da seção {secao}.",
		}
	).insert(ignore_permissions=True)
	return 1


def _aplicar_atribuicoes(
	associado: str, papel_por_secao: dict[str, str], automaticas: set[str]
) -> tuple[int, int]:
	"""Abre a função certa e encerra as automáticas que não valem mais."""
	desejadas = {titulo_da_funcao(papel, secao) for secao, papel in papel_por_secao.items()}

	doc = frappe.get_doc("Associado", associado)
	hoje = getdate(nowdate())
	criadas = 0
	encerradas = 0
	abertas = set()

	for linha in doc.funcoes_internas:
		if linha.funcao not in automaticas:
			continue
		encerrada = linha.data_fim and getdate(linha.data_fim) < hoje
		if linha.funcao in desejadas:
			if encerrada:
				# Voltou para a seção: reabre em vez de criar linha duplicada.
				linha.data_fim = None
				criadas += 1
			abertas.add(linha.funcao)
		elif not encerrada:
			linha.data_fim = hoje
			encerradas += 1

	for titulo in sorted(desejadas - abertas):
		doc.append("funcoes_internas", {"funcao": titulo, "data_inicio": hoje})
		criadas += 1

	if criadas or encerradas:
		doc.save(ignore_permissions=True)
	return criadas, encerradas


def _definir_responsavel(secao: str, chefe: str) -> None:
	area = frappe.db.get_value(
		"Unidade Organizacional", secao, ["responsavel", "origem_automatica"], as_dict=True
	)
	if not area:
		return
	# Área feita à mão tem dono humano; a rotina não passa por cima.
	if not area.get("origem_automatica"):
		return
	if area.get("responsavel") == chefe:
		return
	frappe.db.set_value("Unidade Organizacional", secao, "responsavel", chefe)
