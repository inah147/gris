"""Acordos de Trabalho Voluntário (ATV) das funções internas.

Um ATV cobre uma alocação — a linha de `Associado.funcoes_internas` —, e cada alocação
pode ter zero ou mais acordos ao longo do tempo. O que vale hoje é o de **validade mais
recente**; os anteriores ficam como histórico da renovação.

A leitura é sempre agregada: a página lista o organograma inteiro de uma vez, então
nenhuma consulta pode rodar por pessoa.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from .atribuicoes import garantir_gestor_funcoes
from .responsaveis import e_funcao_do_conselho

#: Categoria que define o público assistido — não entra no organograma, logo não tem ATV.
CATEGORIA_EXCLUIDA = "Beneficiário"

SITUACAO_SEM_ATV = "sem_atv"
SITUACAO_VIGENTE = "vigente"
SITUACAO_VENCIDO = "vencido"


# ---------------------------------------------------------------------------
# Regra de validade (função pura — sem banco, para poder testar direto)
# ---------------------------------------------------------------------------


def classificar_validade(atvs: list[dict], hoje) -> dict:
	"""Resume, para uma alocação, o acordo que vale hoje.

	Vale o de maior `data_fim`; o desempate é pela `creation` mais nova, porque duas
	renovações podem terminar no mesmo dia e a última cadastrada é a que reflete a
	decisão atual.

	`assinado` é independente da situação: um acordo dentro do prazo mas sem assinatura
	continua sendo pendência, e a tela precisa saber das duas coisas separadamente.
	"""
	validos = [atv for atv in atvs if atv.get("data_fim")]
	if not validos:
		return {
			"situacao": SITUACAO_SEM_ATV,
			"acordo": None,
			"assinado": False,
			"data_inicio": None,
			"data_fim": None,
			"dias_para_vencer": None,
		}

	atual = max(validos, key=lambda atv: (getdate(atv["data_fim"]), atv.get("creation") or ""))
	fim = getdate(atual["data_fim"])
	dias = (fim - getdate(hoje)).days

	return {
		"situacao": SITUACAO_VENCIDO if dias < 0 else SITUACAO_VIGENTE,
		"acordo": atual.get("name"),
		"assinado": bool(atual.get("assinado")),
		"data_inicio": _iso(atual.get("data_inicio")),
		"data_fim": _iso(atual.get("data_fim")),
		"dias_para_vencer": dias,
	}


def em_vigor(linha: dict, hoje) -> bool:
	"""Mesmo corte de `lotacoes_atuais`: só está encerrada a linha cuja `data_fim` passou.

	Divergir disso colocaria na lista de ATVs gente que o organograma já não desenha —
	ou o contrário.
	"""
	fim = linha.get("data_fim")
	return not fim or getdate(fim) >= getdate(hoje)


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------


@frappe.whitelist()
def listar_atvs() -> list[dict]:
	"""Uma linha por função em vigor de cada pessoa do organograma, com a validade.

	Três consultas no total — pessoas, funções e acordos —, agregadas em Python. Uma
	consulta por pessoa deixaria a página na casa das centenas de idas ao banco.
	"""
	garantir_gestor_funcoes()

	pessoas = {
		p["name"]: p["nome_completo"] or p["name"]
		for p in frappe.get_all(
			"Associado",
			filters={"categoria": ["!=", CATEGORIA_EXCLUIDA], "status_no_grupo": "Ativo"},
			fields=["name", "nome_completo"],
			order_by="nome_completo asc",
		)
	}
	if not pessoas:
		return []

	hoje = getdate(nowdate())
	linhas = [
		linha
		for linha in frappe.get_all(
			"Funcao do Associado",
			filters={"parent": ["in", list(pessoas)], "parenttype": "Associado"},
			fields=["name", "parent", "funcao", "area", "principal", "data_inicio", "data_fim"],
			order_by="parent asc, principal desc, idx asc",
		)
		# A função do Conselho não é alocação do quadro: ela sai do vínculo com um
		# beneficiário e não tem acordo a assinar. Listá-la encheria a tela de cobrança
		# com uma pendência por responsável legal que ninguém consegue resolver.
		if em_vigor(linha, hoje) and not e_funcao_do_conselho(linha["funcao"], linha["area"])
	]
	if not linhas:
		return []

	por_linha = _acordos_por_linha([linha["name"] for linha in linhas])

	resultado = [
		{
			"associado": linha["parent"],
			"nome": pessoas[linha["parent"]],
			"linha": linha["name"],
			"funcao": linha["funcao"],
			"area": linha["area"],
			"principal": bool(linha["principal"]),
			"funcao_inicio": _iso(linha["data_inicio"]),
			"funcao_fim": _iso(linha["data_fim"]),
			**classificar_validade(por_linha.get(linha["name"], []), hoje),
		}
		for linha in linhas
	]
	# Pendência primeiro, depois o que vence mais cedo: a tela é de cobrança, e a
	# ordenação por coluna do design system continua disponível por cima desta.
	resultado.sort(key=_chave_de_urgencia)
	return resultado


@frappe.whitelist()
def listar_atvs_da_funcao(associado: str, linha: str) -> list[dict]:
	"""Histórico completo dos acordos daquela alocação, do mais recente ao mais antigo."""
	garantir_gestor_funcoes()
	_garantir_linha(associado, linha)

	return [
		{
			"name": atv["name"],
			"data_inicio": _iso(atv["data_inicio"]),
			"data_fim": _iso(atv["data_fim"]),
			"assinado": bool(atv["assinado"]),
		}
		for atv in frappe.get_all(
			"Acordo de Trabalho Voluntario",
			filters={"linha_funcao": linha, "associado": associado},
			fields=["name", "data_inicio", "data_fim", "assinado"],
			order_by="data_fim desc, creation desc",
		)
	]


# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def salvar_atv(payload: str) -> dict:
	"""Cria ou atualiza um acordo da alocação.

	`funcao` e `area` não vêm do payload: o controller as copia da linha, que é a única
	fonte confiável de qual função o acordo cobre.
	"""
	garantir_gestor_funcoes()
	dados = _carregar(payload)

	associado = _texto(dados.get("associado"))
	linha = _texto(dados.get("linha"))
	_garantir_linha(associado, linha, para_escrita=True)

	inicio = _texto(dados.get("data_inicio"))
	fim = _texto(dados.get("data_fim"))
	if not inicio or not fim:
		frappe.throw(_("Informe o início e o término do acordo."))

	nome = _texto(dados.get("name"))
	if nome:
		doc = frappe.get_doc("Acordo de Trabalho Voluntario", nome)
		if doc.linha_funcao != linha:
			frappe.throw(_("Este acordo é de outra função."))
	else:
		doc = frappe.new_doc("Acordo de Trabalho Voluntario")
		doc.associado = associado
		doc.linha_funcao = linha

	doc.data_inicio = getdate(inicio)
	doc.data_fim = getdate(fim)
	doc.assinado = 1 if _booleano(dados.get("assinado")) else 0
	doc.save()

	return {"ok": True, "name": doc.name, **_resposta_da_linha(associado, linha)}


@frappe.whitelist(methods=["POST"])
def apagar_atv(payload: str) -> dict:
	"""Apaga um acordo. O histórico da alocação não depende dele — a linha da função
	continua de pé, e o que muda é só qual acordo passa a valer."""
	garantir_gestor_funcoes()
	dados = _carregar(payload)

	nome = _texto(dados.get("name"))
	if not nome or not frappe.db.exists("Acordo de Trabalho Voluntario", nome):
		frappe.throw(_("Acordo não encontrado."), frappe.DoesNotExistError)

	doc = frappe.get_doc("Acordo de Trabalho Voluntario", nome)
	associado, linha = doc.associado, doc.linha_funcao
	doc.delete()

	return {"ok": True, **_resposta_da_linha(associado, linha)}


def _resposta_da_linha(associado: str, linha: str) -> dict:
	"""Histórico e validade da alocação, depois de uma gravação.

	A `validade` vai junto para a tabela de quem chamou trocar o selo da linha sem
	recarregar a página inteira — é ela que muda quando um acordo entra ou sai.
	"""
	atvs = listar_atvs_da_funcao(associado, linha)
	return {
		"atvs": atvs,
		"linha": linha,
		"validade": classificar_validade(_acordos_por_linha([linha]).get(linha, []), getdate(nowdate())),
	}


def apagar_atvs_da_linha(linha: str) -> int:
	"""Remove os acordos de uma alocação que deixou de existir.

	Chamado por `apagar_funcao`: sem isto, os acordos ficariam apontando para uma child
	row que não existe mais, e o controller do ATV recusaria qualquer edição futura
	deles — sem que houvesse tela nenhuma para chegar até lá e apagá-los.
	"""
	if not linha:
		return 0
	nomes = frappe.get_all("Acordo de Trabalho Voluntario", filters={"linha_funcao": linha}, pluck="name")
	for nome in nomes:
		frappe.delete_doc("Acordo de Trabalho Voluntario", nome, ignore_permissions=True)
	return len(nomes)


# ---------------------------------------------------------------------------
# Apoio
# ---------------------------------------------------------------------------


def acordos_por_linha_do_associado(associado: str) -> dict[str, list[dict]]:
	"""Todos os acordos de uma pessoa, agrupados por alocação.

	Uma consulta só, para o painel do organograma montar todas as funções da pessoa sem
	voltar ao banco por função.
	"""
	return _acordos_por_linha(
		frappe.get_all(
			"Funcao do Associado",
			filters={"parent": associado, "parenttype": "Associado"},
			pluck="name",
		)
	)


def _acordos_por_linha(linhas: list[str]) -> dict[str, list[dict]]:
	if not linhas:
		return {}
	por_linha: dict[str, list[dict]] = {}
	for atv in frappe.get_all(
		"Acordo de Trabalho Voluntario",
		filters={"linha_funcao": ["in", linhas]},
		fields=["name", "linha_funcao", "data_inicio", "data_fim", "assinado", "creation"],
	):
		por_linha.setdefault(atv["linha_funcao"], []).append(atv)
	return por_linha


def _chave_de_urgencia(item: dict) -> tuple:
	ordem_da_situacao = {SITUACAO_SEM_ATV: 0, SITUACAO_VENCIDO: 1, SITUACAO_VIGENTE: 2}
	return (
		ordem_da_situacao.get(item["situacao"], 3),
		0 if not item["assinado"] else 1,
		item["dias_para_vencer"] if item["dias_para_vencer"] is not None else 0,
		item["nome"],
	)


def _garantir_linha(associado: str, linha: str, para_escrita: bool = False) -> None:
	if not associado or not linha:
		frappe.throw(_("Escolha a função do acordo."))
	dono = frappe.db.get_value(
		"Funcao do Associado", linha, ["parent", "parenttype", "funcao", "area"], as_dict=True
	)
	if not dono or dono.parenttype != "Associado":
		frappe.throw(_("Função interna não encontrada."), frappe.DoesNotExistError)
	if dono.parent != associado:
		frappe.throw(_("Esta função não é da pessoa informada."), frappe.DoesNotExistError)
	# Ler o histórico de uma linha do Conselho continua valendo (dados antigos existem);
	# o que não pode é cadastrar acordo novo para uma função que não exige nenhum.
	if para_escrita and e_funcao_do_conselho(dono.funcao, dono.area):
		frappe.throw(
			_("{0} é mantida pelo vínculo com o beneficiário e não exige acordo de trabalho.").format(
				frappe.bold(dono.funcao)
			)
		)


def _carregar(payload: str) -> dict:
	try:
		dados = json.loads(payload or "{}")
	except ValueError:
		frappe.throw(_("Não foi possível ler os dados enviados."))
	if not isinstance(dados, dict):
		frappe.throw(_("Não foi possível ler os dados enviados."))
	return dados


def _texto(valor) -> str:
	return valor.strip() if isinstance(valor, str) else ""


def _booleano(valor) -> bool:
	if isinstance(valor, str):
		return valor.strip().lower() in {"1", "true", "sim", "on"}
	return bool(valor)


def _iso(valor) -> str | None:
	"""Texto ISO, não `date`: o contexto da página passa por `tojson` do Jinja, que não
	serializa data, e o front espera "aaaa-mm-dd"."""
	return getdate(valor).isoformat() if valor else None
