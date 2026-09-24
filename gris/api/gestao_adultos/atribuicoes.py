"""Atribuição de funções internas a uma pessoa do organograma, pela ficha do portal.

A grade `funcoes_internas` vive em permlevel 2 no `Associado` e, até aqui, só existia no
Desk. Estes endpoints são o caminho do portal para ela — e valem para os dois tipos de
pessoa do organograma, porque o `Responsavel` ganhou a mesma grade (mesmo child DocType,
com `parenttype` diferente).

Por isso o parâmetro é `pessoa`, e não `associado`: os dois DocTypes têm `name` no mesmo
formato (md5 de CPF), então só a chave com espaço de nomes diz em qual grade gravar. Ver
`gris.api.gestao_adultos.identidade`. `associado` continua aceito para não quebrar o que já
chama estes métodos.

Cada linha é um par função + área: a área é o que posiciona a pessoa no
organograma, e o par precisa estar vinculado em `Unidade Organizacional.funcoes`
(o controller valida isso na gravação).

Tirar alguém de uma função é **encerrar** (`data_fim = hoje`), nunca apagar a
linha — é o mesmo que a sincronização de seções faz, e é o que mantém o histórico
do painel de detalhes de pé. `apagar_funcao` existe para o outro caso: desfazer um
lançamento que nunca deveria ter acontecido.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from . import identidade

#: Quem pode mexer nas funções internas pela ficha. `Gestor de Adultos` é o dono
#: histórico da grade; os outros dois ganharam write no permlevel 2 junto com esta
#: tela.
ROLES_GESTOR_FUNCOES = ("Gestor de Adultos", "Gestor da UEL", "Gestor de Associados")
ROLE_ADMIN = "System Manager"


def _roles(user: str | None = None) -> set[str]:
	return set(frappe.get_roles(user or frappe.session.user))


def pode_gerenciar_funcoes(user: str | None = None) -> bool:
	roles = _roles(user)
	return bool(roles & set(ROLES_GESTOR_FUNCOES)) or ROLE_ADMIN in roles


def garantir_gestor_funcoes(user: str | None = None) -> None:
	if not pode_gerenciar_funcoes(user):
		frappe.throw(
			_("Você não tem permissão para alterar as funções internas desta pessoa."),
			frappe.PermissionError,
		)


@frappe.whitelist()
def listar_areas_com_funcoes() -> list[dict]:
	"""Áreas ativas com as funções ativas de cada uma, para o seletor em cascata.

	Duas consultas no total, e não uma por área: a página monta a cascata inteira
	sem ida e volta ao servidor a cada troca de área.
	"""
	garantir_gestor_funcoes()

	areas = frappe.get_all(
		"Unidade Organizacional",
		filters={"ativa": 1},
		fields=["name", "area"],
		order_by="ordem asc, area asc",
	)
	if not areas:
		return []

	ativas = set(frappe.get_all("Funcao Voluntario", filters={"ativa": 1}, pluck="name"))
	funcoes_por_area: dict[str, list[str]] = {}
	for vinculo in frappe.get_all(
		"Funcao da Area",
		filters={"parenttype": "Unidade Organizacional", "parent": ["in", [a["name"] for a in areas]]},
		fields=["parent", "funcao"],
		order_by="parent asc, idx asc",
	):
		if vinculo.funcao in ativas:
			funcoes_por_area.setdefault(vinculo.parent, []).append(vinculo.funcao)

	return [
		{
			"value": area["name"],
			"label": area["area"],
			"funcoes": [{"value": f, "label": f} for f in funcoes_por_area.get(area["name"], [])],
		}
		for area in areas
	]


@frappe.whitelist()
def listar_funcoes_do_associado(associado: str) -> list[dict]:
	"""Atalho para quem já tem em mãos o `name` de um `Associado`."""
	return listar_funcoes_da_pessoa(identidade.chave_do_associado(associado))


@frappe.whitelist()
def listar_funcoes_da_pessoa(pessoa: str) -> list[dict]:
	"""As linhas de função da pessoa, em ordem de leitura: principal, depois em vigor."""
	garantir_gestor_funcoes()
	doctype, name = identidade.separar(pessoa)
	if not frappe.db.exists(doctype, name):
		frappe.throw(_("Pessoa não encontrada no organograma."), frappe.DoesNotExistError)

	hoje = getdate()
	linhas = frappe.get_all(
		"Funcao do Associado",
		filters={"parent": name, "parenttype": doctype},
		fields=["name", "funcao", "area", "principal", "data_inicio", "data_fim", "idx"],
		order_by="principal desc, idx asc",
	)

	# Importação tardia: `atvs` depende de `garantir_gestor_funcoes` deste módulo, e
	# `responsaveis` depende deste módulo inteiro.
	from .atvs import acordos_por_linha_do_associado, classificar_validade
	from .responsaveis import e_funcao_do_conselho

	# O acordo de trabalho voluntário é documento do quadro e só existe para associado.
	# Cobrar um de responsável criaria uma pendência que ninguém consegue resolver.
	tem_atv = doctype == identidade.DOCTYPE_ASSOCIADO
	acordos = acordos_por_linha_do_associado(name) if tem_atv else {}

	def _atv(linha):
		# A função do Conselho é a segunda exceção: ela não é alocação do quadro, e
		# ninguém assina acordo de trabalho para ser responsável legal do próprio filho.
		if not tem_atv or e_funcao_do_conselho(linha.funcao, linha.area):
			return None
		return classificar_validade(acordos.get(linha.name) or [], hoje)

	return [
		{
			"linha": linha.name,
			"funcao": linha.funcao,
			"area": linha.area,
			"principal": bool(linha.principal),
			# Texto ISO, não `date`: o contexto da página passa por `tojson` do Jinja,
			# que não serializa data, e o front espera "aaaa-mm-dd".
			"data_inicio": _iso(linha.data_inicio),
			"data_fim": _iso(linha.data_fim),
			"atual": not linha.data_fim or getdate(linha.data_fim) >= hoje,
			# Mantida pelo vínculo com o beneficiário, não pela tela: é o que faz o dialog
			# esconder "Encerrar hoje" e "Apagar função".
			"automatica": e_funcao_do_conselho(linha.funcao, linha.area),
			# O acordo de trabalho é por alocação: cada linha carrega o seu, e a tabela
			# mostra a pendência sem uma segunda ida ao servidor.
			"atv": _atv(linha),
		}
		for linha in linhas
	]


@frappe.whitelist(methods=["POST"])
def atribuir_funcao(payload: str) -> dict:
	"""Abre uma função para a pessoa numa área.

	Recusa par repetido em vigor: duas linhas iguais abertas disputariam a mesma
	vaga no organograma, que fica com uma e descarta a outra em silêncio.
	"""
	garantir_gestor_funcoes()
	dados = _carregar(payload)

	pessoa = _pessoa_do_payload(dados)
	funcao = _texto(dados.get("funcao"))
	area = _texto(dados.get("area"))
	if not funcao or not area:
		frappe.throw(_("Escolha a área e a função."))

	doc = identidade.carregar(pessoa)
	hoje = getdate(nowdate())
	for linha in doc.funcoes_internas:
		if linha.funcao != funcao or linha.area != area:
			continue
		if not linha.data_fim or getdate(linha.data_fim) >= hoje:
			frappe.throw(
				_("{0} já exerce {1} em {2}.").format(
					frappe.bold(doc.nome_completo or doc.name), frappe.bold(funcao), frappe.bold(area)
				)
			)

	principal = bool(dados.get("principal"))
	if principal:
		for linha in doc.funcoes_internas:
			linha.principal = 0

	doc.append(
		"funcoes_internas",
		{
			"funcao": funcao,
			"area": area,
			"principal": 1 if principal else 0,
			"data_inicio": _data(dados.get("data_inicio")) or hoje,
		},
	)
	doc.save()
	return {"ok": True, "funcoes": listar_funcoes_da_pessoa(pessoa)}


@frappe.whitelist(methods=["POST"])
def encerrar_funcao(payload: str) -> dict:
	"""Encerra a linha em `data_fim`, mantendo o histórico.

	Apagar a linha tiraria a pessoa do organograma e também do histórico do painel
	— e não é isso que "tirar a função de alguém" quer dizer.
	"""
	garantir_gestor_funcoes()
	dados = _carregar(payload)

	pessoa = _pessoa_do_payload(dados)
	doc = identidade.carregar(pessoa)
	linha = _localizar_linha(doc, _texto(dados.get("linha")))

	_garantir_que_a_linha_pode_sair(doc, linha)

	hoje = getdate(nowdate())
	if linha.data_fim and getdate(linha.data_fim) < hoje:
		frappe.throw(_("Esta função já está encerrada."))

	# A data de início pode ser posterior a hoje em cadastro planejado; nesse caso
	# encerrar em "hoje" criaria um período invertido, que o Associado recusa.
	linha.data_fim = max(hoje, getdate(linha.data_inicio)) if linha.data_inicio else hoje
	linha.principal = 0
	doc.save()
	return {"ok": True, "funcoes": listar_funcoes_da_pessoa(pessoa)}


@frappe.whitelist(methods=["POST"])
def editar_funcao(payload: str) -> dict:
	"""Corrige as datas de uma linha já existente.

	`data_fim` em branco devolve a linha para "atual". A coerência do período é do
	`Associado` (`_validar_funcoes_internas`), não daqui: duplicar a regra faria as duas
	divergirem no primeiro ajuste.

	Mexer só nas datas não reabre a validação de vínculo função+área — ela compara o par
	`(funcao, area)` com o do documento anterior —, e é assim que linha antiga sem área
	continua editável.
	"""
	garantir_gestor_funcoes()
	dados = _carregar(payload)

	pessoa = _pessoa_do_payload(dados)
	doc = identidade.carregar(pessoa)
	linha = _localizar_linha(doc, _texto(dados.get("linha")))

	inicio = _data(dados.get("data_inicio"))
	fim = _data(dados.get("data_fim"))
	if not inicio:
		frappe.throw(_("Informe a data de início da função."))

	linha.data_inicio = inicio
	linha.data_fim = fim
	# Função encerrada no passado não pode seguir sendo a principal — é a mesma regra
	# que `definir_principal` aplica na outra ponta.
	if fim and fim < getdate(nowdate()):
		linha.principal = 0

	doc.save()
	return {"ok": True, "funcoes": listar_funcoes_da_pessoa(pessoa)}


@frappe.whitelist(methods=["POST"])
def apagar_funcao(payload: str) -> dict:
	"""Remove a linha de vez, com os acordos de trabalho que dependiam dela.

	É para desfazer um lançamento errado. Para tirar alguém de uma função que ele de
	fato exerceu, o caminho continua sendo `encerrar_funcao`, que preserva o histórico.
	"""
	garantir_gestor_funcoes()
	dados = _carregar(payload)

	pessoa = _pessoa_do_payload(dados)
	doc = identidade.carregar(pessoa)
	linha = _localizar_linha(doc, _texto(dados.get("linha")))

	_garantir_que_a_linha_pode_sair(doc, linha)

	# Importação tardia: `atvs` depende de `garantir_gestor_funcoes` deste módulo.
	from .atvs import apagar_atvs_da_linha

	apagar_atvs_da_linha(linha.name)
	doc.funcoes_internas.remove(linha)
	doc.save()
	return {"ok": True, "funcoes": listar_funcoes_da_pessoa(pessoa)}


@frappe.whitelist(methods=["POST"])
def definir_principal(payload: str) -> dict:
	"""Marca qual função aparece no card do organograma. Só uma por pessoa."""
	garantir_gestor_funcoes()
	dados = _carregar(payload)

	pessoa = _pessoa_do_payload(dados)
	doc = identidade.carregar(pessoa)
	alvo = _localizar_linha(doc, _texto(dados.get("linha")))

	hoje = getdate(nowdate())
	if alvo.data_fim and getdate(alvo.data_fim) < hoje:
		frappe.throw(_("Uma função encerrada não pode ser a principal."))

	for linha in doc.funcoes_internas:
		linha.principal = 1 if linha.name == alvo.name else 0
	doc.save()
	return {"ok": True, "funcoes": listar_funcoes_da_pessoa(pessoa)}


# ---------------------------------------------------------------------------
# Apoio
# ---------------------------------------------------------------------------


def _carregar(payload: str) -> dict:
	try:
		dados = json.loads(payload or "{}")
	except ValueError:
		frappe.throw(_("Não foi possível ler os dados enviados."))
	if not isinstance(dados, dict):
		frappe.throw(_("Não foi possível ler os dados enviados."))
	return dados


def _texto(valor) -> str:
	return (valor or "").strip() if isinstance(valor, str) else ""


def _data(valor):
	return getdate(valor) if valor else None


def _iso(valor) -> str | None:
	return getdate(valor).isoformat() if valor else None


def _pessoa_do_payload(dados: dict) -> str:
	"""Chave da pessoa a alterar, aceitando o formato antigo.

	`pessoa` é o caminho novo, com espaço de nomes. `associado` continua aceito porque é o
	que a ficha do associado manda, e lá o tipo nunca foi ambíguo.
	"""
	pessoa = _texto(dados.get("pessoa"))
	if pessoa:
		return pessoa

	associado = _texto(dados.get("associado"))
	if not associado:
		frappe.throw(_("Pessoa não informada."), frappe.DoesNotExistError)
	return identidade.chave_do_associado(associado)


def _garantir_que_a_linha_pode_sair(doc, linha) -> None:
	"""Barra encerrar ou apagar a função que o cadastro mantém sozinho.

	A gravação do documento barraria de novo (`gris.utils.funcoes_internas`), mas só depois
	de `apagar_funcao` já ter varrido os acordos da linha. Aqui a recusa chega antes de
	qualquer efeito colateral.
	"""
	from .responsaveis import e_funcao_do_conselho, garantir_permanencia_no_conselho

	if e_funcao_do_conselho(linha.funcao, linha.area):
		garantir_permanencia_no_conselho(doc)


def _localizar_linha(doc, nome_da_linha: str):
	for linha in doc.funcoes_internas:
		if linha.name == nome_da_linha:
			return linha
	frappe.throw(_("Função não encontrada na ficha desta pessoa."), frappe.DoesNotExistError)
