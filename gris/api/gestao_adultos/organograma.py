"""Organograma da Gestão de Adultos.

Monta a árvore de voluntários a partir de duas coisas: a hierarquia de áreas
(`Unidade Organizacional.responde_para`) e a lotação de cada pessoa, que sai da
área escolhida em cada linha de `Associado.funcoes_internas`. Quem lidera uma
área responde ao líder da área-mãe; quem tem função numa área responde ao líder
dela. Funções em áreas diferentes colocam a mesma pessoa em mais de um ponto do
desenho.

A mesma função pode valer em várias áreas — o vínculo mora na child table
`Unidade Organizacional.funcoes`. Esse vínculo é catálogo de validação, e não
fonte do desenho: o organograma lê a área direto da linha da pessoa e nunca
precisa consultar a tabela de vínculos.
"""

from __future__ import annotations

import datetime
from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import getdate

from gris.utils.contato import format_phone

from . import identidade
from .atvs import acordos_por_linha_do_associado, classificar_validade, em_vigor
from .endpoints import _require_authenticated_user
from .responsaveis import (
	AREA_CONSELHO,
	LINHA_RESPONSAVEL,
	e_funcao_do_conselho,
	listar_membros_do_conselho,
	montar_no_conselho,
)
from .secoes import escotistas_sem_secao

#: Categoria que define o público assistido — não entra no organograma.
CATEGORIA_EXCLUIDA = "Beneficiário"

#: Meses abreviados em PT-BR. `toLocaleDateString` no JS devolveria "jan. de 2024",
#: então o período do painel é montado aqui.
MESES_ABREVIADOS = (
	"jan",
	"fev",
	"mar",
	"abr",
	"mai",
	"jun",
	"jul",
	"ago",
	"set",
	"out",
	"nov",
	"dez",
)

#: Travessão curto que separa os dois extremos do período de uma função. Vem de
#: chr() porque o ruff barra o caractere literal como ambíguo.
TRACO_DE_INTERVALO = chr(0x2013)

#: Só faz sentido mostrar ramo para quem atua numa seção.
CATEGORIA_COM_RAMO = "Escotista"
RAMO_VAZIO = "Não se aplica"

#: Sufixo da classe `badge-ramo-*` do design system, que pinta cada ramo com a
#: cor oficial dele. Sem acento nem maiúscula, como as classes CSS.
SLUG_POR_RAMO = {
	"Filhotes": "filhotes",
	"Lobinho": "lobinho",
	"Escoteiro": "escoteiro",
	"Sênior": "senior",
	"Pioneiro": "pioneiro",
}

#: Valor do filtro que isola quem está sem lotação.
FILTRO_SEM_AREA = "__sem_area__"

#: Espaço rígido: espaço comum colapsa no HTML e a indentação do filtro sumiria.
RECUO_DO_FILTRO = chr(0x00A0) * 2


@frappe.whitelist()
def obter_organograma(area: str | None = None) -> dict:
	"""Devolve a árvore do organograma, pronta para renderizar.

	`area` recorta o desenho naquela área e em tudo que responde para ela. O
	recorte é feito nas listas cruas, antes de montar a árvore: podar a árvore
	pronta perderia as outras ocorrências de quem aparece em mais de uma área.
	"""
	_require_authenticated_user()

	todas_areas = frappe.get_all(
		"Unidade Organizacional",
		filters={"ativa": 1},
		fields=[
			"name",
			"area",
			"responde_para",
			"responsavel",
			"tipo_responsavel",
			"descricao",
			"ordem",
		],
		order_by="ordem asc, area asc",
	)
	# O líder pode ser associado ou responsável; daqui para baixo tudo compara por chave.
	for unidade in todas_areas:
		unidade["responsavel"] = identidade.chave_do_lider(unidade)

	todas_pessoas = pessoas_do_organograma()
	lotacoes, funcoes_sem_area = lotacoes_atuais([p["name"] for p in todas_pessoas])

	area = (area or "").strip()
	areas, pessoas, lotacoes = _recortar_por_area(area, todas_areas, todas_pessoas, lotacoes)

	arvore = montar_arvore(areas, pessoas, lotacoes, _avatar_por_pessoa(pessoas))
	arvore["area_selecionada"] = area
	arvore["avisos"]["funcoes_sem_area"] = funcoes_sem_area
	arvore["avisos"]["escotistas_sem_secao"] = escotistas_sem_secao()
	_acrescentar_conselho(arvore, area)
	return arvore


def _acrescentar_conselho(arvore: dict, area: str) -> None:
	"""Pendura no Conselho de Responsáveis os membros que não têm lotação gravada.

	Entra por fora de `montar_arvore` de propósito: quem só é `Responsavel` não tem linha
	em `Funcao do Associado`, e obrigar a montagem da árvore a conhecer um segundo tipo de
	pessoa complicaria a parte que desenha o quadro de voluntários inteiro.

	Quem também é associado chega ao conselho pelo caminho normal, pela linha gravada — e
	nesse caso `montar_arvore` já criou o nó de grupo da área. Os derivados então **entram
	nesse mesmo nó**: dois nós com o mesmo `id` deixariam a interface marcando o card
	errado, e a área apareceria duas vezes na tela.
	"""
	if area and area != AREA_CONSELHO:
		return

	derivados = montar_no_conselho(listar_membros_do_conselho())
	grupo = next(
		(no for no in arvore["raizes"] if no.get("id") == f"area:{AREA_CONSELHO}"),
		None,
	)

	if grupo is None:
		if not derivados:
			return
		arvore["raizes"].append(derivados)
		arvore["raizes"].sort(key=_chave_ordenacao)
		arvore["total_pessoas"] += derivados["membros"]
		return

	# São mais de uma centena de cards: abrir todos de saída empurraria o resto do
	# organograma para fora da tela.
	grupo["recolhido"] = True
	if not derivados:
		return

	# Um responsável alocado no próprio Conselho já tem nó gravado aqui; o derivado dele
	# repetiria o mesmo `id` e a interface passaria a marcar dois cards de uma vez.
	ja_no_grupo = {filho["id"] for filho in grupo["children"]}
	novos = [filho for filho in derivados["children"] if filho["id"] not in ja_no_grupo]
	if not novos:
		return

	grupo["children"].extend(novos)
	grupo["children"].sort(key=_chave_ordenacao)
	# Somado à mão porque `_contar` já rodou sobre a árvore, antes destes nós existirem.
	grupo["membros"] = grupo.get("membros", 0) + len(novos)
	arvore["total_pessoas"] += len(novos)


def pessoas_do_organograma() -> list[dict]:
	"""Quem pode aparecer no desenho, já com a chave que identifica cada um.

	São dois tipos: o quadro de associados ativos, e os responsáveis **que têm função
	alocada ou lideram uma área**. O recorte do segundo grupo é o que impede o organograma
	de encher com a centena de responsáveis do cadastro — quem não exerce função nem lidera
	nada aparece só no Conselho, por derivação (ver `gris.api.gestao_adultos.responsaveis`).
	"""
	pessoas = [
		dict(
			pessoa,
			name=identidade.chave_do_associado(pessoa["name"]),
			pessoa_id=pessoa["name"],
			tipo_pessoa="associado",
		)
		for pessoa in frappe.get_all(
			"Associado",
			filters={"categoria": ["!=", CATEGORIA_EXCLUIDA], "status_no_grupo": "Ativo"},
			fields=["name", "nome_completo", "categoria", "ramo", "secao", "id_escoteiros"],
			order_by="nome_completo asc",
		)
	]

	alocados = set(
		frappe.get_all(
			"Funcao do Associado",
			filters={"parenttype": "Responsavel"},
			pluck="parent",
			distinct=True,
		)
	)
	# Liderar uma área basta para entrar no desenho: sem isto a área ficaria sem cabeça
	# só porque o líder não tem função alocada — o mesmo que `montar_arvore` já faz com o
	# associado que só lidera.
	alocados |= set(
		frappe.get_all(
			"Unidade Organizacional",
			filters={"ativa": 1, "tipo_responsavel": identidade.DOCTYPE_RESPONSAVEL},
			pluck="responsavel",
		)
	)
	alocados = {nome for nome in alocados if nome}
	if alocados:
		pessoas += [
			dict(
				pessoa,
				name=identidade.chave_do_responsavel(pessoa["name"]),
				pessoa_id=pessoa["name"],
				tipo_pessoa="responsavel",
				# O responsável não tem categoria, ramo nem seção: o selo do card dele é o
				# mesmo do Conselho.
				categoria=LINHA_RESPONSAVEL,
			)
			for pessoa in frappe.get_all(
				"Responsavel",
				filters={"name": ["in", sorted(alocados)]},
				fields=["name", "nome_completo"],
				order_by="nome_completo asc",
			)
		]

	return pessoas


def lotacoes_atuais(chaves: list[str]) -> tuple[list[dict], int]:
	"""Onde cada pessoa está, derivado das funções internas em vigor.

	A área é escolhida na própria linha de função interna — a mesma função pode
	valer em várias áreas, então só a linha sabe onde a pessoa exerce. Quem tem
	linhas em áreas diferentes gera uma lotação para cada uma, e aparece em mais de
	um lugar no organograma.

	Recebe e devolve **chaves** (`associado:…` / `responsavel:…`), porque os dois tipos de
	pessoa têm `name` no mesmo formato e a grade é a mesma tabela. Uma consulta por
	`parenttype`, não uma por pessoa.
	"""
	if not chaves:
		return [], 0

	nomes_por_doctype: dict[str, list[str]] = {}
	for chave in chaves:
		doctype, name = identidade.separar(chave)
		nomes_por_doctype.setdefault(doctype, []).append(name)

	linhas = []
	for doctype, nomes in nomes_por_doctype.items():
		for linha in frappe.get_all(
			"Funcao do Associado",
			filters={"parent": ["in", nomes], "parenttype": doctype},
			fields=["parent", "funcao", "area", "principal", "idx", "data_fim"],
			order_by="parent asc, principal desc, idx asc",
		):
			linha["pessoa"] = identidade.chave(doctype, linha["parent"])
			linhas.append(linha)

	hoje = getdate()
	por_chave: dict[tuple[str, str], str] = {}
	sem_area = 0
	for linha in linhas:
		if linha.get("data_fim") and getdate(linha["data_fim"]) < hoje:
			continue
		area = linha.get("area")
		if not area:
			sem_area += 1
			continue
		# `order_by` já pôs a principal na frente: a primeira ganha a vaga da área.
		por_chave.setdefault((linha["pessoa"], area), linha["funcao"])

	lotacoes = [
		{"pessoa": pessoa, "area": area, "funcao": funcao} for (pessoa, area), funcao in por_chave.items()
	]
	return lotacoes, sem_area


@frappe.whitelist()
def obter_detalhe_do_adulto(associado: str) -> dict:
	"""Dados do painel lateral: contato, badges e o histórico de funções.

	Endpoint à parte, e não campos a mais na árvore: carregar funções, descrições e
	responsabilidades de todo mundo para mostrar uma pessoa por vez inflaria o
	organograma inteiro à toa.
	"""
	_require_authenticated_user()

	pessoa = frappe.db.get_value(
		"Associado",
		associado,
		[
			"name",
			"nome_completo",
			"categoria",
			"ramo",
			"secao",
			"telefone",
			"id_escoteiros",
			"status_no_grupo",
		],
		as_dict=True,
	)

	# A página é aberta a qualquer pessoa logada, então esta trava é o que impede o
	# endpoint de virar um leitor genérico de Associado.
	if (
		not pessoa
		or pessoa.get("categoria") == CATEGORIA_EXCLUIDA
		or pessoa.get("status_no_grupo") != "Ativo"
	):
		frappe.throw(_("Esta pessoa não faz parte do organograma."), frappe.DoesNotExistError)

	funcoes = frappe.get_all(
		"Funcao do Associado",
		filters={"parent": associado, "parenttype": "Associado"},
		# `name` é a identidade da alocação: é por ele que o acordo de trabalho é ligado.
		fields=["name", "funcao", "area", "principal", "data_inicio", "data_fim", "idx"],
		order_by="principal desc, idx asc",
	)

	titulos = [linha["funcao"] for linha in funcoes if linha.get("funcao")]
	definicoes = {
		linha["name"]: linha
		for linha in frappe.get_all(
			"Funcao Voluntario",
			filters={"name": ["in", titulos]},
			fields=["name", "descricao"],
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

	lideradas = areas_lideradas(identidade.chave_do_associado(associado))
	avatares = _avatar_por_pessoa([pessoa])
	# Uma consulta de acordos para todas as funções da pessoa, antes do loop: o painel
	# abre por clique, e uma consulta por função seria N+1 a cada abertura.
	acordos = acordos_por_linha_do_associado(associado)
	return montar_detalhe(
		pessoa,
		funcoes,
		definicoes,
		responsabilidades,
		avatares.get(associado),
		lideradas,
		acordos,
	)


# ---------------------------------------------------------------------------
# Montagem do detalhe (função pura — sem banco, para poder testar direto)
# ---------------------------------------------------------------------------


def montar_detalhe(
	pessoa: dict,
	funcoes: list[dict],
	definicoes: dict[str, dict],
	responsabilidades: dict[str, list[dict]],
	avatar_url: str | None,
	areas_lideradas: list[str] | None = None,
	acordos: dict[str, list[dict]] | None = None,
) -> dict:
	categoria = pessoa.get("categoria")
	ramo = pessoa.get("ramo")
	if categoria != CATEGORIA_COM_RAMO or ramo == RAMO_VAZIO:
		ramo = None

	hoje = getdate()
	nome = pessoa.get("nome_completo") or pessoa.get("name")
	lista = [
		_funcao_do_painel(linha, definicoes, responsabilidades, acordos or {}, hoje) for linha in funcoes
	]

	# A área não vem mais do cadastro da pessoa: sai das funções em vigor, mais as
	# áreas que ela lidera.
	areas = {f["area"] for f in lista if f["area"] and f["atual"]}
	areas |= set(areas_lideradas or [])

	return {
		"id": pessoa.get("name"),
		"nome": nome,
		"avatar_url": avatar_url,
		"iniciais": _iniciais(nome),
		"funcao_principal": lista[0]["titulo"] if lista else None,
		"areas": sorted(areas),
		"areas_lideradas": sorted(areas_lideradas or []),
		"linha": categoria,
		"ramo": ramo,
		"ramo_slug": SLUG_POR_RAMO.get(ramo or ""),
		# Seção só faz sentido junto do ramo, pelo mesmo motivo.
		"secao": (pessoa.get("secao") or "").strip() or None if ramo else None,
		"whatsapp": _numero_do_whatsapp(pessoa.get("telefone")),
		"ficha_url": "/associados/detalhe?name=" + quote(str(pessoa.get("name") or "")),
		"permite_ficha": True,
		"somente_leitura": False,
		"funcoes": lista,
	}


def _funcao_do_painel(
	linha: dict,
	definicoes: dict[str, dict],
	responsabilidades: dict[str, list[dict]],
	acordos: dict[str, list[dict]],
	hoje,
) -> dict:
	titulo = linha.get("funcao")
	definicao = definicoes.get(titulo) or {}
	return {
		"linha": linha.get("name"),
		"titulo": titulo,
		# A área é da linha, não da definição: a mesma função pode valer em
		# várias áreas.
		"area": linha.get("area"),
		"principal": bool(linha.get("principal")),
		# Mesmo corte de `lotacoes_atuais`: só está encerrada a linha cuja `data_fim` já
		# passou. Com término marcado para o ano que vem a função continua em vigor — e
		# é dela que o acordo de trabalho ainda é cobrado.
		"atual": em_vigor(linha, hoje),
		"periodo": _periodo(linha.get("data_inicio"), linha.get("data_fim")),
		"descricao": (definicao.get("descricao") or "").strip() or None,
		# O acordo de trabalho é por alocação, não por pessoa: cada linha tem o seu. A
		# função do Conselho é a exceção: ela não é alocação do quadro, e cobrar um acordo
		# dela criaria uma pendência que ninguém pode resolver.
		"atv": None
		if e_funcao_do_conselho(linha.get("funcao"), linha.get("area"))
		else classificar_validade(acordos.get(linha.get("name")) or [], hoje),
		"responsabilidades": [
			{
				"responsabilidade": item.get("responsabilidade"),
				"detalhe": (item.get("detalhe") or "").strip() or None,
			}
			for item in responsabilidades.get(titulo, [])
		],
	}


def _periodo(inicio, fim) -> str:
	de = _mes_ano(inicio)
	ate = _mes_ano(fim)

	if de and ate:
		return f"{de} {TRACO_DE_INTERVALO} {ate}"
	if de:
		return f"Atual · desde {de}"
	if ate:
		return f"até {ate}"
	return "Sem período informado"


def _mes_ano(valor) -> str | None:
	"""Devolve "jan/2024" a partir de date, datetime ou string ISO."""
	if not valor:
		return None
	if isinstance(valor, datetime.datetime):
		valor = valor.date()
	if not isinstance(valor, datetime.date):
		try:
			valor = datetime.date.fromisoformat(str(valor)[:10])
		except ValueError:
			return None
	return f"{MESES_ABREVIADOS[valor.month - 1]}/{valor.year}"


def _numero_do_whatsapp(telefone) -> str | None:
	"""Só os dígitos, para o link wa.me.

	`format_phone` devolve a entrada crua quando não consegue normalizar; o prefixo
	`+` é o sinal de que deu certo.
	"""
	normalizado = format_phone(telefone) or ""
	if not str(normalizado).startswith("+"):
		return None
	digitos = "".join(c for c in str(normalizado) if c.isdigit())
	return digitos or None


def _recortar_por_area(
	area: str,
	todas_areas: list[dict],
	pessoas: list[dict],
	lotacoes: list[dict],
) -> tuple[list, list, list]:
	"""Restringe áreas, pessoas e lotações ao ramo escolhido no filtro."""
	if not area:
		return todas_areas, pessoas, lotacoes

	nomes_validos = {a["name"] for a in todas_areas}
	if area == FILTRO_SEM_AREA:
		lotados = {linha["pessoa"] for linha in lotacoes if linha["area"] in nomes_validos}
		return [], [p for p in pessoas if p["name"] not in lotados], []

	selecionadas = _area_com_descendentes(area, todas_areas)
	if not selecionadas:
		return [], [], []

	areas = [a for a in todas_areas if a["name"] in selecionadas]
	recortadas = [linha for linha in lotacoes if linha["area"] in selecionadas]
	# Quem lidera uma área selecionada entra mesmo sem função mapeada para ela.
	dentro = {linha["pessoa"] for linha in recortadas}
	dentro |= {a["responsavel"] for a in areas if a.get("responsavel")}
	return areas, [p for p in pessoas if p["name"] in dentro], recortadas


def _area_com_descendentes(area: str, todas_areas: list[dict]) -> set[str]:
	if not any(a["name"] == area for a in todas_areas):
		return set()

	filhas: dict[str, list[str]] = {}
	for a in todas_areas:
		filhas.setdefault(a.get("responde_para"), []).append(a["name"])

	selecionadas = {area}
	fila = [area]
	while fila:
		atual = fila.pop()
		for filha in filhas.get(atual, []):
			if filha not in selecionadas:
				selecionadas.add(filha)
				fila.append(filha)
	return selecionadas


def listar_areas_para_filtro() -> list[dict]:
	"""Áreas ativas em ordem de hierarquia, para montar o seletor da página."""
	areas = frappe.get_all(
		"Unidade Organizacional",
		filters={"ativa": 1},
		fields=["name", "area", "responde_para", "ordem"],
		order_by="ordem asc, area asc",
	)
	if not areas:
		return []

	conhecidas = {a["name"] for a in areas}
	filhas: dict[str, list[dict]] = {}
	for a in areas:
		filhas.setdefault(a.get("responde_para"), []).append(a)

	ordenadas: list[dict] = []
	visitadas: set[str] = set()

	def _descer(no: dict, nivel: int):
		if no["name"] in visitadas:
			return
		visitadas.add(no["name"])
		ordenadas.append(
			{
				"value": no["name"],
				"label": (RECUO_DO_FILTRO * nivel) + (no["area"] or no["name"]),
			}
		)
		for filha in filhas.get(no["name"], []):
			_descer(filha, nivel + 1)

	# Área cuja mãe está inativa vira raiz, senão sumiria do filtro.
	for a in areas:
		if not a.get("responde_para") or a["responde_para"] not in conhecidas:
			_descer(a, 0)

	# Sobra só se houver ciclo; entra no fim para não desaparecer da lista.
	for a in areas:
		if a["name"] not in visitadas:
			ordenadas.append({"value": a["name"], "label": a["area"] or a["name"]})

	return ordenadas


def existe_associado_sem_area() -> bool:
	"""Se ninguém está sem lotação, a opção "Sem área" não precisa existir.

	Só olha para associados: o responsável entra no desenho justamente por ter função
	alocada, então nunca está sem área.
	"""
	chaves = [
		identidade.chave_do_associado(nome)
		for nome in frappe.get_all(
			"Associado",
			filters={"categoria": ["!=", CATEGORIA_EXCLUIDA], "status_no_grupo": "Ativo"},
			pluck="name",
		)
	]
	if not chaves:
		return False

	lotacoes, _sem_area = lotacoes_atuais(chaves)
	areas_ativas = set(frappe.get_all("Unidade Organizacional", filters={"ativa": 1}, pluck="name"))
	lotados = {linha["pessoa"] for linha in lotacoes if linha["area"] in areas_ativas}
	lotados |= {
		identidade.chave_do_lider(r)
		for r in frappe.get_all(
			"Unidade Organizacional",
			filters={"ativa": 1, "responsavel": ["is", "set"]},
			fields=["responsavel", "tipo_responsavel"],
		)
	}
	return any(chave not in lotados for chave in chaves)


def areas_lideradas(pessoa: str) -> list[str]:
	"""Áreas ativas que a pessoa lidera, seja ela associado ou responsável.

	Pelo par (tipo, nome), nunca só pelo nome: o homônimo do outro cadastro devolveria
	as áreas de outra pessoa.
	"""
	return frappe.get_all(
		"Unidade Organizacional",
		filters={**identidade.filtros_do_lider(pessoa), "ativa": 1},
		pluck="name",
		order_by="ordem asc, area asc",
	)


def _avatar_por_pessoa(pessoas: list[dict]) -> dict[str, str]:
	"""O login do associado é o `id_escoteiros`, não o e-mail comum."""
	ids = [p["id_escoteiros"] for p in pessoas if p.get("id_escoteiros")]
	if not ids:
		return {}

	imagens = {
		u["name"]: u["user_image"]
		for u in frappe.get_all("User", filters={"name": ["in", ids]}, fields=["name", "user_image"])
		if u.get("user_image")
	}

	return {
		p["name"]: imagens[p["id_escoteiros"]]
		for p in pessoas
		if p.get("id_escoteiros") and p["id_escoteiros"] in imagens
	}


# ---------------------------------------------------------------------------
# Montagem da árvore (função pura — sem banco, para poder testar direto)
# ---------------------------------------------------------------------------


def montar_arvore(
	areas: list[dict],
	pessoas: list[dict],
	lotacoes: list[dict],
	avatar_por_pessoa: dict[str, str],
) -> dict:
	"""Monta a árvore a partir das lotações derivadas das funções.

	Uma pessoa com funções em áreas diferentes rende um nó em cada uma — o mesmo
	rosto aparece em mais de um lugar. Por isso a chave do nó é o par
	(pessoa, área), e as contagens de liderados somam pessoas distintas, não nós.
	"""
	areas_por_nome = {a["name"]: a for a in areas}
	pessoas_por_nome = {p["name"]: p for p in pessoas}

	ciclos = _detectar_ciclos(areas_por_nome)
	# Uma área em ciclo não tem cadeia confiável para subir; tratamos como topo.
	em_ciclo = set(ciclos)

	# O responsável só vale se ele próprio entrou no organograma (um responsável
	# desligado ou beneficiário deixa a área efetivamente sem líder).
	lider_da_area = {
		a["name"]: a["responsavel"]
		for a in areas
		if a.get("responsavel") and a["responsavel"] in pessoas_por_nome
	}

	funcao_por_chave = {
		(linha["pessoa"], linha["area"]): linha.get("funcao")
		for linha in lotacoes
		if linha["pessoa"] in pessoas_por_nome and linha["area"] in areas_por_nome
	}
	# Liderar a área também posiciona: sem isso, área com membros ficaria sem
	# cabeça só porque faltou cadastrar a função do responsável.
	for nome_area, lider in lider_da_area.items():
		funcao_por_chave.setdefault((lider, nome_area), None)

	areas_por_pessoa: dict[str, list[str]] = {}
	for pessoa, nome_area in funcao_por_chave:
		areas_por_pessoa.setdefault(pessoa, []).append(nome_area)

	nos: dict[tuple[str, str], dict] = {}
	for (pessoa, nome_area), funcao in funcao_por_chave.items():
		outras = sorted(a for a in areas_por_pessoa[pessoa] if a != nome_area)
		nos[(pessoa, nome_area)] = _no_pessoa(
			pessoas_por_nome[pessoa],
			nome_area,
			funcao,
			avatar_por_pessoa.get(pessoa),
			lidera=lider_da_area.get(nome_area) == pessoa,
			outras_areas=outras,
		)

	nos_grupo: dict[str, dict] = {}
	raizes: list[dict] = []
	sem_area_filhos: list[dict] = []

	def _area_ancestral_com_lider(nome_area: str | None, ignorar: str) -> str | None:
		"""Área mais próxima acima de `nome_area` que tenha líder diferente de `ignorar`."""
		visitados: set[str] = set()
		atual = (areas_por_nome.get(nome_area) or {}).get("responde_para")
		while atual and atual not in visitados and atual not in em_ciclo:
			visitados.add(atual)
			candidato = lider_da_area.get(atual)
			if candidato and candidato != ignorar:
				return atual
			atual = (areas_por_nome.get(atual) or {}).get("responde_para")
		return None

	def _grupo_da_area(nome_area: str) -> dict:
		if nome_area not in nos_grupo:
			area = areas_por_nome.get(nome_area) or {}
			nos_grupo[nome_area] = {
				"tipo": "grupo",
				"id": f"area:{nome_area}",
				"nome": area.get("area") or nome_area,
				"ordem": area.get("ordem") or 0,
				"membros": 0,
				"children": [],
			}
		return nos_grupo[nome_area]

	for (pessoa, nome_area), no in nos.items():
		if lider_da_area.get(nome_area) == pessoa:
			acima = _area_ancestral_com_lider(nome_area, ignorar=pessoa)
			if acima:
				nos[(lider_da_area[acima], acima)]["children"].append(no)
			else:
				raizes.append(no)
			continue

		lider = lider_da_area.get(nome_area)
		if lider:
			nos[(lider, nome_area)]["children"].append(no)
		else:
			_grupo_da_area(nome_area)["children"].append(no)

	# Quem não tem nenhuma lotação não está em área nenhuma.
	for nome, pessoa in pessoas_por_nome.items():
		if nome not in areas_por_pessoa:
			sem_area_filhos.append(
				_no_pessoa(pessoa, None, None, avatar_por_pessoa.get(nome), lidera=False, outras_areas=[])
			)

	# Grupos (áreas sem líder) penduram no primeiro líder acima; sem nenhum, viram raiz.
	for nome_area, grupo in nos_grupo.items():
		acima = _area_ancestral_com_lider(nome_area, ignorar="")
		if acima:
			nos[(lider_da_area[acima], acima)]["children"].append(grupo)
		else:
			raizes.append(grupo)

	for no in list(nos.values()) + list(nos_grupo.values()):
		no["children"].sort(key=_chave_ordenacao)
	raizes.sort(key=_chave_ordenacao)
	sem_area_filhos.sort(key=_chave_ordenacao)

	for raiz in raizes:
		_contar(raiz)
	for no in sem_area_filhos:
		_contar(no)

	sem_area = None
	if sem_area_filhos:
		sem_area = {
			"tipo": "grupo",
			"id": "sem-area",
			"nome": "Sem área definida",
			"ordem": 0,
			"membros": len(sem_area_filhos),
			"children": sem_area_filhos,
		}

	# O conselho não tem líder por definição — cobrar um dele seria um aviso que ninguém
	# pode resolver.
	areas_sem_responsavel = sorted(
		areas_por_nome[n]["area"] for n in nos_grupo if n in areas_por_nome and n != AREA_CONSELHO
	)

	return {
		"raizes": raizes,
		"sem_area": sem_area,
		"avisos": {
			"pessoas_sem_area": len(sem_area_filhos),
			"areas_sem_responsavel": areas_sem_responsavel,
			"ciclos": sorted(ciclos),
		},
		"total_pessoas": len(pessoas_por_nome),
	}


def _no_pessoa(
	pessoa: dict,
	nome_area: str | None,
	funcao: str | None,
	avatar_url: str | None,
	lidera: bool,
	outras_areas: list[str],
) -> dict:
	# `name` aqui é a **chave** pela qual a árvore indexa a pessoa. `pessoa_id` é o docname,
	# e `tipo_pessoa` diz de qual DocType. Os dois têm default para o caso em que a chave já
	# é o próprio docname de um associado.
	chave = pessoa["name"]
	tipo_pessoa = pessoa.get("tipo_pessoa") or "associado"
	docname = pessoa.get("pessoa_id") or chave

	ramo = pessoa.get("ramo")
	if pessoa.get("categoria") != CATEGORIA_COM_RAMO or ramo == RAMO_VAZIO:
		ramo = None
	return {
		"tipo": "pessoa",
		# A mesma pessoa pode ter vários nós; o id é do nó, `pessoa` é de quem.
		"id": f"{chave}@@{nome_area or ''}",
		# O organograma tem dois tipos de gente (associado e responsável) e os dois têm
		# `name` no mesmo formato — md5 de CPF. `pessoa` é a chave com espaço de nomes,
		# e é por ela que a interface marca o card e pede o painel.
		"tipo_pessoa": tipo_pessoa,
		"pessoa": identidade.chave(
			identidade.DOCTYPE_RESPONSAVEL if tipo_pessoa == "responsavel" else identidade.DOCTYPE_ASSOCIADO,
			docname,
		),
		"associado": docname if tipo_pessoa == "associado" else None,
		"responsavel": docname if tipo_pessoa == "responsavel" else None,
		"nome": pessoa.get("nome_completo") or docname,
		"area": nome_area,
		"outras_areas": outras_areas,
		"funcao_interna": funcao,
		"linha": pessoa.get("categoria"),
		"ramo": ramo,
		"ramo_slug": SLUG_POR_RAMO.get(ramo or ""),
		"secao": (pessoa.get("secao") or "").strip() or None,
		"avatar_url": avatar_url,
		"iniciais": _iniciais(pessoa.get("nome_completo") or docname),
		"lidera_area": nome_area if lidera else None,
		"diretos": 0,
		"indiretos": 0,
		"children": [],
	}


def _detectar_ciclos(areas_por_nome: dict[str, dict]) -> set[str]:
	"""Áreas cuja cadeia de `responde_para` volta para elas mesmas.

	O DocType barra ciclos na gravação, mas dados legados (ou importados) podem
	trazer um; sem esta guarda a montagem entraria em recursão infinita.
	"""
	ciclos: set[str] = set()
	for inicio in areas_por_nome:
		visitados = {inicio}
		atual = areas_por_nome[inicio].get("responde_para")
		while atual and atual in areas_por_nome:
			if atual in visitados:
				ciclos.add(inicio)
				break
			visitados.add(atual)
			atual = areas_por_nome[atual].get("responde_para")
	return ciclos


def _chave_ordenacao(no: dict) -> tuple:
	"""Líderes e áreas primeiro (na ordem definida), depois o time por nome."""
	if no["tipo"] == "grupo":
		return (0, no.get("ordem") or 0, no["nome"])
	if no.get("lidera_area"):
		return (0, 0, no["nome"])
	return (1, 0, no["nome"])


def _pessoas_diretas(no: dict) -> set[str]:
	"""Quem está um nível abaixo, atravessando nós de grupo.

	Um grupo é uma área sem líder: quem está dentro dele responde, na prática,
	ao líder que está acima do grupo. Devolve nomes de associado — a mesma pessoa
	pode ter dois nós ali embaixo e não pode ser contada duas vezes.
	"""
	diretas: set[str] = set()
	for filho in no["children"]:
		if filho["tipo"] == "grupo":
			diretas |= _pessoas_diretas(filho)
		else:
			diretas.add(filho["pessoa"])
	return diretas


def _contar(no: dict) -> set[str]:
	"""Preenche diretos/indiretos em pós-ordem; devolve as pessoas distintas abaixo."""
	abaixo: set[str] = set()
	for filho in no["children"]:
		abaixo |= _contar(filho)
		if filho["tipo"] == "pessoa":
			abaixo.add(filho["pessoa"])

	if no["tipo"] == "pessoa":
		# Quem lidera uma área e tem função numa sub-área sem líder acaba dentro da
		# própria subárvore; ninguém é liderado de si mesmo.
		proprio = {no["pessoa"]}
		diretas = _pessoas_diretas(no) - proprio
		abaixo = abaixo - proprio
		no["diretos"] = len(diretas)
		no["indiretos"] = len(abaixo) - len(diretas)
	else:
		no["membros"] = len(abaixo)

	return abaixo


def _iniciais(nome: str) -> str:
	partes = [p for p in (nome or "").split() if p]
	if not partes:
		return "?"
	if len(partes) == 1:
		return partes[0][:2].upper()
	return (partes[0][0] + partes[-1][0]).upper()
