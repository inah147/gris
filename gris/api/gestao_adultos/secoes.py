"""Sincronização das seções do Paxtu com as áreas do organograma.

Toda seção que aparece no cadastro vira uma `Unidade Organizacional`; cada uma
recebe o vínculo com as duas funções genéricas ("Chefe de Seção" e "Assistente de
Seção"), e todo escotista da seção recebe uma delas. O chefe vira responsável da
área.

As funções são genéricas porque o vínculo função↔área é M:N (`Unidade
Organizacional.funcoes`): a mesma "Chefe de Seção" serve para todas as seções.
Quem diz de qual seção a pessoa é não é o título da função, e sim a área da linha
em `Associado.funcoes_internas`.

A rotina só mexe no que ela mesma criou (`origem_automatica`) — área feita à mão
nunca é tocada, e função genérica numa área feita à mão também não. E nada é
apagado: área sai por `ativa = 0` e função de pessoa sai por `data_fim`, para o
histórico continuar de pé.

Dois caminhos de entrada, a mesma regra: `sincronizar_secoes()` reconcilia o grupo
inteiro (é o que a importação do Paxtu chama) e `sincronizar_secao_do_associado()`
reconcilia uma pessoa só, no `on_update` do `Associado` — é o que faz a regra valer
sempre, e não só no dia da importação.

Quem não tem `secao` preenchida fica de fora, por definição: sem seção não há área
para posicionar a pessoa. `escotistas_sem_secao()` é o que dá visibilidade a esse
buraco de cadastro, que é do Paxtu e não se resolve por inferência.
"""

from __future__ import annotations

import frappe
from frappe.utils import getdate, nowdate

from gris.utils.chefes import eh_funcao_chefe_de_secao, normalizar_texto

from . import identidade

CATEGORIA_ESCOTISTA = "Escotista"
PAPEL_CHEFE = "Chefe de Seção"
PAPEL_ASSISTENTE = "Assistente de Seção"


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
		return {
			"areas_criadas": 0,
			"funcoes_criadas": 0,
			"vinculos_criados": 0,
			"atribuicoes": 0,
			"encerradas": 0,
			"avisos": [],
		}

	area_mae = frappe.db.get_single_value("Configuracoes de Associados", "area_mae_das_secoes")
	if area_mae and not frappe.db.exists("Unidade Organizacional", area_mae):
		area_mae = None

	resumo = {
		"areas_criadas": 0,
		"funcoes_criadas": 0,
		"vinculos_criados": 0,
		"atribuicoes": 0,
		"encerradas": 0,
		"avisos": list(plano["avisos"]),
	}

	# Todo vínculo precisa existir antes das atribuições: o Associado recusa par
	# função+área que a Unidade Organizacional não lista.
	for secao in plano["secoes"]:
		resumo["areas_criadas"] += _garantir_area(secao, area_mae)
		for papel in (PAPEL_CHEFE, PAPEL_ASSISTENTE):
			resumo["funcoes_criadas"] += _garantir_funcao(papel)
			resumo["vinculos_criados"] += _garantir_vinculo(secao, papel)

	automaticas = set(frappe.get_all("Funcao Voluntario", filters={"origem_automatica": 1}, pluck="name"))
	areas_automaticas = set(
		frappe.get_all("Unidade Organizacional", filters={"origem_automatica": 1}, pluck="name")
	)
	for associado, papel_por_secao in plano["atribuicoes"].items():
		# Savepoint por pessoa: um cadastro torto não pode derrubar a sincronização
		# dos outros. A importação chama isto dentro de um `try/except` que só loga, e
		# num request a exceção capturada não desfaz o que já foi gravado.
		ponto = f"sync_secao_{frappe.generate_hash(length=8)}"
		frappe.db.savepoint(ponto)
		try:
			criadas, encerradas = _aplicar_atribuicoes(
				associado, papel_por_secao, automaticas, areas_automaticas
			)
		except Exception:
			frappe.db.rollback(save_point=ponto)
			resumo["avisos"].append(f"Não foi possível sincronizar as funções de {associado}.")
			continue
		resumo["atribuicoes"] += criadas
		resumo["encerradas"] += encerradas

	for secao, chefe in plano["responsaveis"].items():
		_definir_responsavel(secao, chefe)

	# Sem commit aqui: quem chama (a importação, num request; o seed, no fim do
	# script) é que fecha a transação.
	return resumo


def sincronizar_secao_do_associado(associado: str) -> bool:
	"""Reconcilia a área e a função automáticas de **uma** pessoa.

	Mesmas peças de `sincronizar_secoes`, com o plano montado a partir de um cadastro
	só. Devolve `True` quando alguma linha foi aberta, reaberta ou encerrada.
	"""
	pessoa = frappe.db.get_value(
		"Associado",
		associado,
		["name", "nome_completo", "secao", "categoria", "funcao", "status_no_grupo"],
		as_dict=True,
	)
	if not pessoa or pessoa.status_no_grupo != "Ativo":
		return False

	plano = planejar_secoes([pessoa])
	papel_por_secao = plano["atribuicoes"].get(associado)
	if not papel_por_secao:
		# Sem seção, sem categoria de escotista, ou seção sem chefe: nada a posicionar.
		# As linhas automáticas que a pessoa já tinha continuam onde estão — quem as
		# encerra é a reconciliação em lote, que enxerga o grupo inteiro.
		return False

	area_mae = frappe.db.get_single_value("Configuracoes de Associados", "area_mae_das_secoes")
	if area_mae and not frappe.db.exists("Unidade Organizacional", area_mae):
		area_mae = None

	for secao in plano["secoes"]:
		_garantir_area(secao, area_mae)
		for papel in (PAPEL_CHEFE, PAPEL_ASSISTENTE):
			_garantir_funcao(papel)
			_garantir_vinculo(secao, papel)

	automaticas = set(frappe.get_all("Funcao Voluntario", filters={"origem_automatica": 1}, pluck="name"))
	areas_automaticas = set(
		frappe.get_all("Unidade Organizacional", filters={"origem_automatica": 1}, pluck="name")
	)
	criadas, encerradas = _aplicar_atribuicoes(associado, papel_por_secao, automaticas, areas_automaticas)

	for secao, chefe in plano["responsaveis"].items():
		_definir_responsavel(secao, chefe)

	return bool(criadas or encerradas)


def on_associado_atualizado(doc, method=None) -> None:
	"""`doc_events` do Associado: mantém a lotação automática em dia a cada gravação.

	A sincronização grava no próprio `Associado`, então a reentrância é certa sem a
	trava de `frappe.flags` — mesmo padrão de `gris_sync_sugestao_tarefa`. E o savepoint
	existe porque um cadastro torto não pode derrubar o save de quem o editou: o erro
	vira log, não uma tela de erro no meio de outra tarefa.
	"""
	if frappe.flags.in_migrate or frappe.flags.in_patch or frappe.flags.in_install:
		return
	if frappe.flags.gris_sync_secoes:
		return
	if not any(doc.has_value_changed(campo) for campo in ("secao", "categoria", "funcao", "status_no_grupo")):
		return

	ponto = f"sync_secao_{frappe.generate_hash(length=8)}"
	frappe.db.savepoint(ponto)
	frappe.flags.gris_sync_secoes = True
	try:
		sincronizar_secao_do_associado(doc.name)
	except Exception:
		frappe.db.rollback(save_point=ponto)
		frappe.log_error(
			title="Sincronização de seção do associado",
			message=f"{doc.name}\n\n{frappe.get_traceback()}",
		)
	finally:
		frappe.flags.gris_sync_secoes = False


def escotistas_sem_secao() -> list[str]:
	"""Escotistas ativos sem `secao` no cadastro — os que ficam fora do organograma.

	A seção é o que posiciona o escotista; sem ela não há área, e a pessoa some do
	desenho sem nenhum sinal. Por decisão, a seção **não** é inferida do ramo: o dado
	tem que ser corrigido no Paxtu, e esta lista é o que mostra para quem.
	"""
	return [
		pessoa["nome_completo"] or pessoa["name"]
		for pessoa in frappe.get_all(
			"Associado",
			filters={
				"categoria": CATEGORIA_ESCOTISTA,
				"status_no_grupo": "Ativo",
				"secao": ["in", ["", None]],
			},
			fields=["name", "nome_completo"],
			order_by="nome_completo asc",
		)
	]


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


def _garantir_funcao(papel: str) -> int:
	"""Cria a função genérica do papel, uma só para todas as seções."""
	if frappe.db.exists("Funcao Voluntario", papel):
		return 0
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
	return 1


def _garantir_vinculo(secao: str, papel: str) -> int:
	"""Liga a função genérica à área da seção."""
	if frappe.db.exists(
		"Funcao da Area",
		{"parent": secao, "parenttype": "Unidade Organizacional", "funcao": papel},
	):
		return 0
	if not frappe.db.exists("Unidade Organizacional", secao):
		return 0

	area = frappe.get_doc("Unidade Organizacional", secao)
	area.append("funcoes", {"funcao": papel})
	area.save(ignore_permissions=True)
	return 1


def planejar_linhas(
	linhas_atuais: list[dict],
	desejados: set[tuple[str, str]],
	automaticas: set[str],
	areas_automaticas: set[str],
	hoje,
) -> dict:
	"""Decide o que fazer com cada linha de função interna (função pura).

	O título da função não carrega mais a seção, então o que identifica uma lotação
	é o par `(funcao, area)`. E o escopo da rotina é o cruzamento das duas marcas de
	`origem_automatica`: função automática **numa área automática**. Função genérica
	vinculada a uma área feita à mão é decisão humana e não se mexe — sem esse
	segundo filtro a sincronização fecharia linhas que nunca foram dela.

	Devolve `{"encerrar": [idx…], "reabrir": [idx…], "abrir": [(funcao, area)…]}`,
	com `idx` sendo a posição na lista recebida.
	"""
	encerrar: list[int] = []
	reabrir: list[int] = []
	abertos: set[tuple[str, str]] = set()

	for posicao, linha in enumerate(linhas_atuais):
		funcao = linha.get("funcao")
		area = linha.get("area")
		if funcao not in automaticas or not area or area not in areas_automaticas:
			continue

		encerrada = linha.get("data_fim") and getdate(linha["data_fim"]) < hoje
		chave = (funcao, area)
		if chave in desejados:
			if encerrada:
				# Voltou para a seção: reabre em vez de criar linha duplicada.
				reabrir.append(posicao)
			abertos.add(chave)
		elif not encerrada:
			encerrar.append(posicao)

	return {
		"encerrar": encerrar,
		"reabrir": reabrir,
		"abrir": sorted(desejados - abertos),
	}


def _aplicar_atribuicoes(
	associado: str,
	papel_por_secao: dict[str, str],
	automaticas: set[str],
	areas_automaticas: set[str],
) -> tuple[int, int]:
	"""Abre o par (função, área) certo e encerra os pares automáticos que não valem mais."""
	desejados = {(papel, secao) for secao, papel in papel_por_secao.items()}

	doc = frappe.get_doc("Associado", associado)
	hoje = getdate(nowdate())
	linhas = [
		{"funcao": linha.funcao, "area": linha.area, "data_fim": linha.data_fim}
		for linha in doc.funcoes_internas
	]
	plano = planejar_linhas(linhas, desejados, automaticas, areas_automaticas, hoje)

	for posicao in plano["reabrir"]:
		doc.funcoes_internas[posicao].data_fim = None
	for posicao in plano["encerrar"]:
		doc.funcoes_internas[posicao].data_fim = hoje
	for funcao, area in plano["abrir"]:
		doc.append("funcoes_internas", {"funcao": funcao, "area": area, "data_inicio": hoje})

	criadas = len(plano["reabrir"]) + len(plano["abrir"])
	encerradas = len(plano["encerrar"])
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
	# O par (tipo, nome) vai junto: `responsavel` é Dynamic Link, e a área ficaria
	# insalvável se o tipo não acompanhasse. Chefe de seção é sempre associado.
	frappe.db.set_value(
		"Unidade Organizacional",
		secao,
		{"responsavel": chefe, "tipo_responsavel": identidade.DOCTYPE_ASSOCIADO},
	)
