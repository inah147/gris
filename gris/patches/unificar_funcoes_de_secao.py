"""Funde as funções de seção por área numa função genérica por papel.

Enquanto `Funcao Voluntario.area` era Link único, "Chefe de Seção" precisava existir
uma vez por seção — daí títulos como "Chefe de Seção — Alcateia". Com o vínculo M:N
do lado da área, uma única "Chefe de Seção" serve para todas: quem diz de qual seção
a pessoa é passou a ser a área da linha em `Associado.funcoes_internas`.

O histórico não se perde na fusão. A linha da pessoa vira `("Chefe de Seção",
"Alcateia")` com as datas intactas: a seção apenas migrou do título para a coluna.
"""

import frappe

# O wrapper `frappe.rename_doc` não expõe `ignore_permissions`, e `validate_rename`
# exige write nos dois documentos — durante o migrate não há usuário para tê-lo.
from frappe.model.rename_doc import rename_doc

from gris.utils.chefes import normalizar_texto

#: Cópias congeladas de `gris.api.gestao_adultos.secoes`. Patch é retrato do passado:
#: se aquele módulo mudar as constantes amanhã, esta migração continua falando do
#: dado que existia quando ela foi escrita.
SEPARADOR = " " + chr(0x2014) + " "
PAPEL_CHEFE = "Chefe de Seção"
PAPEL_ASSISTENTE = "Assistente de Seção"
PAPEIS = (PAPEL_CHEFE, PAPEL_ASSISTENTE)

CATEGORIA_ESCOTISTA = "Escotista"


def planejar_fusao(linhas: list[dict]) -> dict[str, tuple[str, str]]:
	"""Mapeia `titulo_antigo -> (papel_generico, secao)`.

	Critério deliberadamente restritivo: só entra o que a sincronização criou
	(`origem_automatica`) E cujo título casa exatamente com "<papel> — <seção>".
	Função batizada à mão nunca é fundida, mesmo que o nome se pareça.
	"""
	plano: dict[str, tuple[str, str]] = {}
	for linha in linhas:
		titulo = (linha.get("name") or "").strip()
		if not titulo or not linha.get("origem_automatica"):
			continue
		for papel in PAPEIS:
			prefixo = papel + SEPARADOR
			if titulo.startswith(prefixo):
				secao = titulo[len(prefixo) :].strip()
				if secao:
					plano[titulo] = (papel, secao)
				break
	return plano


def execute():
	if not frappe.db.table_exists("Funcao Voluntario"):
		return
	if not frappe.db.has_column("Funcao Voluntario", "area"):
		# A coluna só cai em `remover_area_da_funcao_voluntario`, o patch seguinte:
		# se ela já sumiu, esta fusão também já rodou.
		return

	linhas = frappe.db.sql(
		"SELECT `name`, `origem_automatica` FROM `tabFuncao Voluntario`",
		as_dict=True,
	)
	plano = planejar_fusao(linhas)
	if not plano:
		return

	for papel in sorted({papel for papel, _ in plano.values()}):
		_garantir_generica(papel)

	areas_afetadas = {secao for _, secao in plano.values()}

	for antigo in sorted(plano):
		generica, _ = plano[antigo]
		_mover_responsabilidades(antigo, generica)
		# `merge=True` reaponta todo Link para a função — inclusive os que vivem em
		# child tables (`Funcao do Associado.funcao`, `Funcao da Area.funcao`) — e
		# depois apaga o documento antigo.
		rename_doc(
			doctype="Funcao Voluntario",
			old=antigo,
			new=generica,
			merge=True,
			force=True,
			ignore_permissions=True,
			show_alert=False,
			rebuild_search=False,
		)

	_deduplicar_vinculos(areas_afetadas)
	_reconciliar_vinculos_faltantes()

	print(f"  → {len(plano)} função(ões) de seção fundidas em {len(PAPEIS)} genérica(s).")
	frappe.db.commit()


def _garantir_generica(papel: str) -> None:
	if frappe.db.exists("Funcao Voluntario", papel):
		# Pode já existir, criada à mão antes do patch — inclusive desativada.
		# `origem_automatica` devolve a função ao alcance da sincronização; `ativa`
		# é obrigatório porque as funções que vão ser fundidas aqui estavam ativas:
		# herdar um destino desligado tiraria todos os chefes de seção da lista de
		# funções atribuíveis, sem nenhum aviso.
		atual = frappe.db.get_value("Funcao Voluntario", papel, ["ativa", "origem_automatica"], as_dict=True)
		if not atual.get("origem_automatica"):
			frappe.db.set_value("Funcao Voluntario", papel, "origem_automatica", 1)
		if not atual.get("ativa"):
			frappe.db.set_value("Funcao Voluntario", papel, "ativa", 1)
		return

	frappe.get_doc(
		{
			"doctype": "Funcao Voluntario",
			"titulo": papel,
			"categoria": CATEGORIA_ESCOTISTA,
			"ativa": 1,
			"origem_automatica": 1,
			"descricao": f"{papel}. A seção vem da área em que a função é exercida.",
		}
	).insert(ignore_permissions=True)


def _mover_responsabilidades(antigo: str, generica: str) -> None:
	"""Copia as responsabilidades do doc antigo antes do merge.

	`rename_doc(merge=True)` não move filhos: ele apaga o documento de origem, e as
	responsabilidades iriam junto. Na prática a sincronização nunca as preenche, mas
	alguém pode ter editado pelo Desk.
	"""
	origem = frappe.get_all(
		"Responsabilidade da Funcao",
		filters={"parent": antigo, "parenttype": "Funcao Voluntario"},
		fields=["responsabilidade", "detalhe"],
		order_by="idx asc",
	)
	if not origem:
		return

	destino = frappe.get_doc("Funcao Voluntario", generica)
	ja_tem = {normalizar_texto(linha.responsabilidade) for linha in destino.responsabilidades}
	novas = 0
	for linha in origem:
		chave = normalizar_texto(linha.get("responsabilidade"))
		if not chave or chave in ja_tem:
			continue
		destino.append(
			"responsabilidades",
			{"responsabilidade": linha.get("responsabilidade"), "detalhe": linha.get("detalhe")},
		)
		ja_tem.add(chave)
		novas += 1

	if novas:
		destino.save(ignore_permissions=True)


def _deduplicar_vinculos(areas: set[str]) -> None:
	"""Tira funções repetidas de `Unidade Organizacional.funcoes`.

	A fusão quase garante duplicata: se a área tinha "Chefe de Seção — Alcateia" e já
	tinha a genérica, as duas viram a mesma linha. Duplicata ali trava para sempre o
	save daquela área na validação de vínculo.
	"""
	for parent in sorted(areas):
		linhas = frappe.get_all(
			"Funcao da Area",
			filters={"parent": parent, "parenttype": "Unidade Organizacional"},
			fields=["name", "funcao", "idx"],
			order_by="idx asc, creation asc",
		)
		vistos: set[str] = set()
		idx = 0
		for linha in linhas:
			if linha["funcao"] in vistos:
				frappe.db.delete("Funcao da Area", {"name": linha["name"]})
				continue
			vistos.add(linha["funcao"])
			idx += 1
			if linha["idx"] != idx:
				frappe.db.set_value("Funcao da Area", linha["name"], "idx", idx, update_modified=False)


def _reconciliar_vinculos_faltantes() -> None:
	"""Cria o vínculo de todo par (genérica, área) que alguém já exerce.

	Função de seção com `area` vazia não gerou vínculo no patch anterior; sem isto, o
	par ficaria órfão e o primeiro save daquele associado esbarraria na validação.
	"""
	pares = frappe.get_all(
		"Funcao do Associado",
		filters={"parenttype": "Associado", "funcao": ["in", list(PAPEIS)]},
		fields=["funcao", "area"],
		distinct=True,
	)
	existentes = {
		(v["parent"], v["funcao"])
		for v in frappe.get_all(
			"Funcao da Area",
			filters={"parenttype": "Unidade Organizacional", "funcao": ["in", list(PAPEIS)]},
			fields=["parent", "funcao"],
		)
	}

	proximo_idx: dict[str, int] = {}
	for par in pares:
		area = (par.get("area") or "").strip()
		funcao = par["funcao"]
		if not area or (area, funcao) in existentes:
			continue
		if not frappe.db.exists("Unidade Organizacional", area):
			continue

		if area not in proximo_idx:
			proximo_idx[area] = (
				frappe.db.count("Funcao da Area", {"parent": area, "parenttype": "Unidade Organizacional"})
				or 0
			)
		proximo_idx[area] += 1

		frappe.get_doc(
			{
				"doctype": "Funcao da Area",
				"parent": area,
				"parenttype": "Unidade Organizacional",
				"parentfield": "funcoes",
				"funcao": funcao,
				"idx": proximo_idx[area],
			}
		).insert(ignore_permissions=True)
		existentes.add((area, funcao))
