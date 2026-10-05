"""Busca global do Portal: a paleta que abre pela barra de busca da topbar.

A busca tem duas metades, com custos diferentes:

- **páginas e ações** são poucas e o shell já as conhece. O índice sai da sidebar que
  ``enrich_context`` monta em toda página, vai embutido no HTML e o navegador filtra a cada
  tecla, sem ida ao servidor (:func:`paginas_da_busca`);
- **registros** (pessoas, projetos, festas, documentos) exigem banco e permissão, e vêm de
  :func:`buscar`, chamado com debounce pelo ``portal_busca.js``.

O que a busca mostra nunca passa do que a pessoa abriria: cada fonte só é consultada se o
usuário acessa a página de destino e lê o DocType. Nada aqui leva ao Desk.
Especificação em ``docs/specs/busca-global/spec.md``.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from urllib.parse import quote, urlencode

import frappe
from frappe.utils import formatdate

from gris.api.portal_access import PAGE_ROLES, SIDEBAR_ICON_MAP, _get_user_roles, user_has_access

MIN_CARACTERES = 2
MAX_CARACTERES = 80
MAX_PALAVRAS = 5
LIMITE_POR_GRUPO = 5
# Cada fonte traz mais candidatos do que mostra, para o ranking escolher os melhores.
CANDIDATOS_POR_FONTE = 20

ICONE_PADRAO = "arrow-right"

# Páginas do portal que não estão no menu lateral. Só entra rota mapeada em PAGE_ROLES:
# `user_has_access` libera rota não mapeada (fail-open), e o índice a mostraria para todos.
PAGINAS_FORA_DO_MENU: list[dict[str, str]] = [
	{
		"label": "Importar calendário",
		"path": "/calendario/importar",
		"grupo": "Calendário",
		"icone": "upload",
	},
	{
		"label": "Simulação do calendário",
		"path": "/calendario/simulacao_calendario",
		"grupo": "Calendário",
		"icone": "calendar-cog",
	},
]

# Sinônimos: o nome que a pessoa procura nem sempre é o rótulo do menu.
PALAVRAS_CHAVE: dict[str, str] = {
	"/inicio": "home painel começo",
	"/associados": "pessoas usuários membros escoteiros jovens adultos",
	"/associados/lista": "pessoas usuários membros cadastro",
	"/associados/dashboard": "indicadores métricas gráficos",
	"/associados/importar": "planilha paxtu upload",
	"/recepcao": "integração funil",
	"/recepcao/novos_associados": "integração funil interessados",
	"/recepcao/agenda_visitas": "visitas agendamento",
	"/recepcao/fila_espera": "lista de espera vagas",
	"/financeiro": "dinheiro finanças tesouraria",
	"/financeiro/contribuicoes": "mensalidade pagamentos cobrança",
	"/financeiro/contas": "bancos carteiras saldo",
	"/financeiro/extrato": "transações lançamentos movimentações",
	"/financeiro/conciliacao": "importar extrato banco",
	"/financeiro/despesas": "contas a pagar gastos",
	"/financeiro/previsao_orcamentaria": "orçamento planejamento",
	"/financeiro/relatorios": "balanço demonstrativo",
	"/financeiro/pareceres": "comissão fiscal",
	"/calendario": "agenda eventos atividades",
	"/calendario/visualizar": "agenda eventos atividades",
	"/gestao_adultos/organograma": "estrutura equipes áreas hierarquia",
	"/gestao_adultos/atvs": "voluntários termo de adesão",
	"/gestao_adultos/entrevista_competencias": "competências avaliação",
	"/compras": "pedido aquisição material",
	"/compras/solicitar": "comprar nova solicitação insígnias distintivos manutenção sede reparo material de construção ferramentas administrativo escritório papelaria impressão",
	"/compras/minhas_solicitacoes": "meus pedidos",
	"/compras/fila": "lista de compras pedidos pendentes",
	"/compras/catalogo": "itens produtos insígnias distintivos",
	"/projetos/cadastrar_novo_projeto": "criar",
	"/captacao": "recursos patrocínio editais",
	"/captacao/nova_ideia": "proposta recursos",
	"/captacao/documentos": "certidões documentos do grupo",
	"/gestao_tarefas/tarefas": "afazeres pendências",
	"/festas/portaria": "entrada ingressos qr code convites",
	"/festas/nova_festa": "criar evento",
	"/responsavel/meus_dados": "perfil cadastro conta",
	"/responsavel/beneficiarios": "filhos jovens",
	"/administracao": "configurações ajustes",
	"/administracao/unidades_organizacionais": "configurações áreas estrutura organograma",
	"/administracao/funcoes": "configurações cargos responsabilidades",
	"/administracao/transparencia": "configurações publicar documentos",
	"/sugestoes/nova": "bug problema erro reportar",
	"/sugestoes/acompanhamento": "bugs problemas chamados",
	"/portal_transparencia": "documentos prestação de contas balanço estatuto",
}


# ---------------------------------------------------------------------------
# Índice de páginas (filtrado no navegador)
# ---------------------------------------------------------------------------


def paginas_da_busca(
	sidebar_items: list[dict[str, object]], roles: Iterable[str] | None = None
) -> list[dict[str, object]]:
	"""Páginas que o usuário pode abrir, no formato que o ``portal_busca.js`` filtra.

	``sidebar_items`` é a saída de ``build_sidebar()``, já filtrada por papel. O índice de
	cada módulo é checado à parte porque ``_filter_items`` mantém o pai quando algum filho
	é acessível, mesmo que o próprio índice não seja.
	"""
	roles = list(roles) if roles is not None else _get_user_roles()
	paginas: dict[str, dict[str, object]] = {}

	def incluir(titulo: str, url: str, grupo: str | None, icone: str | None, modulo: bool) -> None:
		if url in paginas:
			# A mesma rota com dois rótulos (o índice de Gestão de Tarefas é também "Quadros"):
			# os dois nomes acham a página.
			paginas[url]["termos"] = f"{paginas[url]['termos']} {titulo}".strip()
			return
		paginas[url] = {
			"titulo": titulo,
			"grupo": grupo,
			"url": url,
			"icone": SIDEBAR_ICON_MAP.get(url) or icone or ICONE_PADRAO,
			"termos": PALAVRAS_CHAVE.get(url, ""),
			"modulo": modulo,
		}

	for item in sidebar_items:
		titulo = str(item.get("label") or "").strip()
		path = str(item.get("path") or "")
		filhos = item.get("children") or []
		if not titulo or not path:
			continue
		icone_do_modulo = SIDEBAR_ICON_MAP.get(path)
		if not filhos or user_has_access(path, roles=roles):
			incluir(titulo, path, None, icone_do_modulo, modulo=True)
		for filho in filhos:
			titulo_filho = str(filho.get("label") or "").strip()
			path_filho = str(filho.get("path") or "")
			if titulo_filho and path_filho:
				incluir(titulo_filho, path_filho, titulo, icone_do_modulo, modulo=False)

	for extra in PAGINAS_FORA_DO_MENU:
		if extra["path"] in PAGE_ROLES and user_has_access(extra["path"], roles=roles):
			incluir(extra["label"], extra["path"], extra["grupo"], extra["icone"], modulo=False)

	return list(paginas.values())


# ---------------------------------------------------------------------------
# Fontes de registros (consultadas no servidor)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Fonte:
	chave: str
	rotulo: str
	icone: str
	# Página de destino dos resultados: a fonte só é consultada se o usuário a abre.
	rota: str
	consultar: Callable[[list[str]], list[dict[str, str]]]
	# DocType lido com permissão. `None` quando a fonte tem regra de visibilidade própria.
	doctype: str | None = None


def _escapar_like(palavra: str) -> str:
	return palavra.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _condicoes(
	campo_titulo: str, palavras: list[str], campos_secundarios: tuple[str, ...] = ()
) -> tuple[list[list[str]], list[list[str]] | None]:
	"""Filtros de nome: cada palavra precisa aparecer, em qualquer ordem e posição.

	Vale o radical da palavra; acento e caixa o banco já ignora (`utf8mb4_unicode_ci`).
	Com uma palavra só, os campos secundários (ex.: número de registro) também valem.
	"""
	like = [f"%{_escapar_like(_radical(p))}%" for p in palavras]
	if len(like) == 1 and campos_secundarios:
		return [], [[campo, "like", like[0]] for campo in (campo_titulo, *campos_secundarios)]
	return [[campo_titulo, "like", valor] for valor in like], None


def _juntar(*partes: object) -> str:
	return " · ".join(str(p) for p in partes if p)


def _url(rota: str, **parametros: object) -> str:
	return f"{rota}?{urlencode(parametros, quote_via=quote)}"


def _associados(palavras: list[str]) -> list[dict[str, str]]:
	filtros, ou = _condicoes("nome_completo", palavras, ("registro",))
	linhas = frappe.get_list(
		"Associado",
		fields=["name", "nome_completo", "registro", "status", "ramo", "categoria"],
		filters=filtros,
		or_filters=ou,
		order_by="nome_completo asc",
		limit_page_length=CANDIDATOS_POR_FONTE,
	)
	return [
		{
			"titulo": linha.nome_completo or linha.name,
			# Adulto tem ramo "Não se aplica"; para ele a categoria (Dirigente…) diz mais.
			"subtitulo": _juntar(
				linha.ramo if linha.ramo and linha.ramo != "Não se aplica" else linha.categoria,
				linha.status,
				linha.registro and f"Registro {linha.registro}",
			),
			"url": _url("/associados/detalhe", name=linha.name),
		}
		for linha in linhas
	]


def _responsaveis(palavras: list[str]) -> list[dict[str, str]]:
	filtros, _ = _condicoes("nome_completo", palavras)
	linhas = frappe.get_list(
		"Responsavel",
		fields=["name", "nome_completo", "associado"],
		filters=filtros,
		order_by="nome_completo asc",
		limit_page_length=CANDIDATOS_POR_FONTE,
	)
	# Quem também é associado aparece só como associado: é a mesma pessoa, e a página do
	# responsável redireciona para a do associado. Sem a ponte gravada, vale o `name` igual
	# (as duas chaves derivam do mesmo CPF) — a mesma regra de `associado_do_responsavel`.
	sem_ponte = [linha.name for linha in linhas if not linha.associado]
	tambem_associados = (
		set(frappe.get_all("Associado", filters={"name": ["in", sem_ponte]}, pluck="name"))
		if sem_ponte
		else set()
	)
	return [
		{
			"titulo": linha.nome_completo or linha.name,
			"subtitulo": "Responsável legal",
			"url": _url("/associados/responsavel", name=linha.name),
		}
		for linha in linhas
		if not linha.associado and linha.name not in tambem_associados
	]


def _novos_associados(palavras: list[str]) -> list[dict[str, str]]:
	filtros, ou = _condicoes("nome_completo", palavras, ("apelido_ou_nome_social",))
	linhas = frappe.get_list(
		"Novo Associado",
		fields=["name", "nome_completo", "ramo", "status"],
		filters=filtros,
		or_filters=ou,
		order_by="nome_completo asc",
		limit_page_length=CANDIDATOS_POR_FONTE,
	)
	return [
		{
			"titulo": linha.nome_completo or linha.name,
			"subtitulo": _juntar(linha.ramo, linha.status),
			"url": _url("/recepcao/ficha_registro", name=linha.name),
		}
		for linha in linhas
	]


def _projetos(palavras: list[str]) -> list[dict[str, str]]:
	filtros, ou = _condicoes("nome_do_projeto", palavras, ("name",))
	linhas = frappe.get_list(
		"Projeto",
		fields=["name", "nome_do_projeto", "status"],
		filters=filtros,
		or_filters=ou,
		order_by="modified desc",
		limit_page_length=CANDIDATOS_POR_FONTE,
	)
	return [
		{
			"titulo": linha.nome_do_projeto or linha.name,
			"subtitulo": _juntar(linha.status, linha.name),
			"url": _url("/projetos/projeto", projeto=linha.name),
		}
		for linha in linhas
	]


def _captacao(palavras: list[str]) -> list[dict[str, str]]:
	from gris.api.captacao.consultas import DOCTYPE
	from gris.api.captacao.permissoes import perfil_do_usuario

	# A Captação não usa a permissão do DocType: quem não "vê o banco" enxerga só o que
	# propôs. Mesma regra do kanban (`listar_kanban`) e da página do projeto (`pode_ver`).
	perfil = perfil_do_usuario()
	filtros, _ = _condicoes("titulo", palavras)
	if not perfil.ve_o_banco:
		filtros.append(["proponente_user", "=", perfil.user])
	linhas = frappe.get_all(
		DOCTYPE,
		fields=["name", "titulo", "status", "proponente_nome"],
		filters=filtros,
		order_by="modified desc",
		limit_page_length=CANDIDATOS_POR_FONTE,
	)
	return [
		{
			"titulo": linha.titulo or linha.name,
			"subtitulo": _juntar(linha.status, linha.proponente_nome),
			"url": _url("/captacao/projeto", name=linha.name),
		}
		for linha in linhas
	]


def _festas(palavras: list[str]) -> list[dict[str, str]]:
	filtros, _ = _condicoes("nome_festa", palavras)
	linhas = frappe.get_list(
		"Festa",
		fields=["name", "nome_festa", "data", "status"],
		filters=filtros,
		order_by="data desc",
		limit_page_length=CANDIDATOS_POR_FONTE,
	)
	return [
		{
			"titulo": linha.nome_festa or linha.name,
			"subtitulo": _juntar(linha.data and formatdate(linha.data, "dd/MM/yyyy"), linha.status),
			"url": _url("/festas/festa", name=linha.name),
		}
		for linha in linhas
	]


def _transparencia(palavras: list[str]) -> list[dict[str, str]]:
	filtros, _ = _condicoes("title", palavras)
	# Só o que já está publicado: é o conteúdo da página pública de transparência, aberta
	# até para visitante — por isso a leitura dispensa a permissão do DocType.
	filtros.append(["publicado", "=", 1])
	linhas = frappe.get_all(
		"Transparencia",
		fields=["name", "title", "ano_referencia", "area", "tipo_arquivo", "trimestre_referencia"],
		filters=filtros,
		# `data_de_atualização` tem acento e o `order_by` do Frappe a recusa.
		order_by="ano_referencia desc, creation desc",
		limit_page_length=CANDIDATOS_POR_FONTE,
	)
	itens = []
	for linha in linhas:
		titulo = linha.title or linha.name
		# Mesmo rótulo da página pública, onde há um parecer por trimestre.
		if linha.tipo_arquivo == "Parecer trimestral da comissão fiscal" and linha.trimestre_referencia:
			titulo = f"{titulo} - {linha.trimestre_referencia}º Trimestre"
		itens.append(
			{
				"titulo": titulo,
				"subtitulo": _juntar(linha.ano_referencia, linha.area or "Documentos institucionais"),
				"url": _url("/portal_transparencia", ano_referencia=linha.ano_referencia)
				if linha.ano_referencia
				else "/portal_transparencia",
			}
		)
	return itens


FONTES: tuple[Fonte, ...] = (
	Fonte("associados", "Associados", "users", "/associados/detalhe", _associados, "Associado"),
	Fonte(
		"responsaveis",
		"Responsáveis",
		"shield-user",
		"/associados/responsavel",
		_responsaveis,
		"Responsavel",
	),
	Fonte(
		"novos_associados",
		"Novos associados",
		"user-plus",
		"/recepcao/ficha_registro",
		_novos_associados,
		"Novo Associado",
	),
	Fonte("projetos", "Projetos", "folder-kanban", "/projetos/projeto", _projetos, "Projeto"),
	Fonte("captacao", "Captação de recursos", "hand-coins", "/captacao/projeto", _captacao),
	Fonte("festas", "Festas", "party-popper", "/festas/festa", _festas, "Festa"),
	Fonte("transparencia", "Transparência", "file-text", "/portal_transparencia", _transparencia),
)


# ---------------------------------------------------------------------------
# Termo e ranking
# ---------------------------------------------------------------------------


def _normalizar(texto: object) -> str:
	decomposto = unicodedata.normalize("NFKD", str(texto or ""))
	return "".join(c for c in decomposto if not unicodedata.combining(c)).casefold().strip()


# Terminações de singular/plural do português, da mais longa para a mais curta. Busca por
# substring não liga "contribuicao" a "Contribuições" (nem "mensal" a "mensais"); cortar a
# terminação dá o radical comum. O `portal_busca.js` aplica as mesmas regras às páginas.
_TERMINACOES = (
	("oes", ""),
	("aes", ""),
	("ao", ""),
	("ais", "a"),
	("al", "a"),
	("eis", "e"),
	("el", "e"),
	("s", ""),
)
_MIN_PALAVRA_PARA_RADICAL = 5
_MIN_RADICAL = 4


def _radical(palavra: str) -> str:
	"""Palavra normalizada sem a terminação de número. É sempre prefixo da palavra, então
	casar pelo radical só amplia o resultado, nunca perde o que casava antes."""
	normalizada = _normalizar(palavra)
	if len(normalizada) < _MIN_PALAVRA_PARA_RADICAL:
		return normalizada
	for terminacao, troca in _TERMINACOES:
		if normalizada.endswith(terminacao):
			radical = normalizada[: -len(terminacao)] + troca
			return radical if len(radical) >= _MIN_RADICAL else normalizada
	return normalizada


def _palavras(termo: object) -> list[str]:
	texto = str(termo or "")[:MAX_CARACTERES]
	return texto.split()[:MAX_PALAVRAS]


def _pontuacao(titulo: str, termo: str, primeira_palavra: str) -> int:
	"""Menor é melhor: título igual, começa com o termo, alguma palavra começa, contém."""
	normalizado = _normalizar(titulo)
	if normalizado == termo:
		return 0
	if normalizado.startswith(termo):
		return 1
	if any(parte.startswith(primeira_palavra) for parte in normalizado.split()):
		return 2
	return 3


def _ranquear(itens: list[dict[str, str]], palavras: list[str]) -> list[dict[str, str]]:
	termo = _normalizar(" ".join(palavras))
	primeira = _radical(palavras[0]) if palavras else ""
	ordenados = sorted(
		itens, key=lambda item: (_pontuacao(item["titulo"], termo, primeira), _normalizar(item["titulo"]))
	)
	return ordenados[:LIMITE_POR_GRUPO]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@frappe.whitelist(methods=["GET"])
def buscar(termo: str | None = None) -> dict:
	"""Registros que casam com ``termo``, agrupados por fonte.

	Sem ``allow_guest``: visitante recebe 403 do próprio whitelist. Termo com menos de
	``MIN_CARACTERES`` devolve a lista vazia sem tocar no banco.
	"""
	palavras = _palavras(termo)
	resposta: dict[str, object] = {"termo": " ".join(palavras), "grupos": []}
	if len(resposta["termo"]) < MIN_CARACTERES:
		return {"ok": True, "data": resposta}

	roles = _get_user_roles()
	grupos = []
	for fonte in FONTES:
		if not user_has_access(fonte.rota, roles=roles):
			continue
		# Papel sem leitura do DocType não tem resultados daquele tipo: o grupo some, sem
		# erro. Checar antes evita a PermissionError (e o msgprint) do `get_list`.
		if fonte.doctype and not frappe.has_permission(fonte.doctype, "read"):
			continue
		itens = _ranquear(fonte.consultar(palavras), palavras)
		if itens:
			grupos.append(
				{"chave": fonte.chave, "rotulo": fonte.rotulo, "icone": fonte.icone, "itens": itens}
			)

	resposta["grupos"] = grupos
	return {"ok": True, "data": resposta}
