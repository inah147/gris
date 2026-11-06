"""Fila de espera da recepção: ordem, entrada, saída e histórico de passagens.

A regra morava espalhada entre ``gris.api.recepcao`` (entrar), a página
``/recepcao/fila_espera`` (chamar) e as ferramentas MCP (listar e chamar). Aqui fica o
que todos eles precisam concordar:

- **Ordem.** A posição de cada jovem dentro do ramo é gravada em ``Fila de Espera.posicao``:
  quem entra vai para o fim, e a recepção pode reordenar arrastando o card. A data de
  inclusão só desempata.
- **Volta ao status de origem.** Sair da fila devolve o jovem ao status em que ele estava ao
  entrar, com as etapas já concluídas intactas. O status de origem é gravado na passagem
  aberta (``Novo Associado.historico_fila_de_espera``) pelo controller do Novo Associado.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.functions import Max
from frappe.utils import format_datetime

from gris.api.recepcao_funil import (
	COLUNA_ACOMPANHAMENTO_DEFINITIVO,
	COLUNA_ACOMPANHAMENTO_FINAL,
	ETAPAS_QUE_MOVEM_O_FUNIL,
	RAMOS,
	STATUS_ACOMPANHAMENTO,
	coluna_de_acompanhamento,
	status_por_etapas_concluidas,
)

DOCTYPE_FILA = "Fila de Espera"
DOCTYPE_PASSAGEM = "Passagem pela Fila de Espera"
CAMPO_HISTORICO = "historico_fila_de_espera"

STATUS_FILA = "Fila de espera"

# Ordem canônica da fila de um ramo. Toda leitura da fila usa esta mesma ordem — a página,
# a previsão de chamada e o MCP —, senão a posição exibida não seria a posição de fato.
ORDEM_DA_FILA = "posicao asc, dt_inclusao_fila asc"

# Quem entra na fila: qualquer etapa do funil, menos as listas de acompanhamento que vêm
# depois da efetivação do registro. Daí em diante o jovem já ocupa a vaga no ramo.
STATUS_SEM_FILA: tuple[str, ...] = ("Concluído",)
COLUNAS_SEM_FILA: tuple[str, ...] = (COLUNA_ACOMPANHAMENTO_DEFINITIVO, COLUNA_ACOMPANHAMENTO_FINAL)

# O que ``motivo_para_nao_entrar_na_fila`` precisa ler do Novo Associado.
CAMPOS_PARA_ENTRAR_NA_FILA: tuple[str, ...] = (
	"status",
	"tipo_de_registro",
	"registro_provisorio_efetivado",
	"registro_definitivo_efetivado",
)

ROTULO_NA_FILA = "Na fila"
ROTULO_NAO_REGISTRADO = "Não registrado"


def motivo_para_nao_entrar_na_fila(dados) -> str | None:
	"""Por que o jovem não pode ir para a fila agora, ou ``None`` se pode.

	``dados`` é o Novo Associado (documento ou dicionário com ``CAMPOS_PARA_ENTRAR_NA_FILA``).
	A divisão do "Acompanhamento" em listas vem das etapas, não do ``status`` — por isso a
	mesma ``coluna_de_acompanhamento`` do kanban decide aqui.
	"""
	status = dados.get("status")
	if status == STATUS_FILA:
		return _("Este associado já está na fila de espera.")
	if status in STATUS_SEM_FILA:
		return _("Quem já concluiu a recepção não vai para a fila de espera.")
	if status == STATUS_ACOMPANHAMENTO:
		coluna = coluna_de_acompanhamento(dados)
		if coluna in COLUNAS_SEM_FILA:
			return _("Quem está em {0} não vai para a fila de espera.").format(coluna)
	return None


def proxima_posicao(ramo: str | None) -> int:
	"""Posição de quem entra agora no fim da fila do ramo."""
	fila = frappe.qb.DocType(DOCTYPE_FILA)
	resultado = frappe.qb.from_(fila).select(Max(fila.posicao)).where(fila.ramo == ramo).run()
	maior = resultado[0][0] if resultado else None
	return (maior or 0) + 1


def passagem_aberta(doc):
	"""Passagem pela fila ainda sem saída — a mais recente, se houver mais de uma."""
	for linha in reversed(doc.get(CAMPO_HISTORICO) or []):
		if not linha.saida_em:
			return linha
	return None


def _retorno(status_anterior: str | None, dados) -> str:
	origem = (status_anterior or "").strip()
	if origem and origem != STATUS_FILA:
		return origem
	return status_por_etapas_concluidas(dados)


def status_de_retorno(doc) -> str:
	"""Status para onde o jovem volta ao sair da fila.

	É o status em que ele estava ao entrar. Quem entrou na fila antes de o status de origem
	passar a ser gravado não tem esse dado: volta para a coluna que as etapas já concluídas
	indicam (a mesma regra que reposiciona o card ao desmarcar uma etapa).
	"""
	linha = passagem_aberta(doc)
	return _retorno(linha.status_anterior if linha else None, doc)


def status_de_retorno_por_associado(nomes: list[str]) -> dict[str, str]:
	"""``status_de_retorno`` de vários jovens da fila, em duas consultas."""
	if not nomes:
		return {}

	abertas = frappe.get_all(
		DOCTYPE_PASSAGEM,
		filters={
			"parenttype": "Novo Associado",
			"parentfield": CAMPO_HISTORICO,
			"parent": ["in", nomes],
			"saida_em": ["is", "not set"],
		},
		fields=["parent", "status_anterior"],
		order_by="entrada_em asc",
	)
	# A mais recente vence, como em ``passagem_aberta``.
	origem = {linha.parent: linha.status_anterior for linha in abertas}

	campos = ["name", *(campo for campo, _status in ETAPAS_QUE_MOVEM_O_FUNIL)]
	etapas = frappe.get_all("Novo Associado", filters={"name": ["in", nomes]}, fields=campos)

	return {dados.name: _retorno(origem.get(dados.name), dados) for dados in etapas}


def chamar(fila_id: str) -> str:
	"""Tira o jovem da fila e o devolve ao status de origem. Retorna o status de destino.

	As etapas não são tocadas: só o ``status`` muda. Fechar a passagem e apagar a entrada da
	fila fica com o controller do Novo Associado, que roda em qualquer caminho de saída.
	"""
	if not fila_id:
		frappe.throw(_("ID da fila não fornecido"))

	associado = frappe.db.get_value(DOCTYPE_FILA, fila_id, "associado")
	if not associado:
		frappe.throw(_("Associado não encontrado na fila"))

	doc = frappe.get_doc("Novo Associado", associado)
	doc.check_permission("write")

	destino = status_de_retorno(doc)
	doc.status = destino
	doc.save()

	# Entrada de fila apontando para alguém que não estava com status "Fila de espera" não
	# passa pelo controller como saída da fila: apaga aqui para o card não ficar preso.
	if frappe.db.exists(DOCTYPE_FILA, fila_id):
		frappe.delete_doc(DOCTYPE_FILA, fila_id)

	return destino


def reordenar(ramo: str, ordem: list[str]) -> list[dict[str, Any]]:
	"""Grava a ordem da fila de um ramo exatamente como a recepção arrumou.

	``ordem`` é a lista completa das entradas do ramo, na ordem nova. Uma lista que não
	bate com a fila atual (alguém entrou, saiu ou mudou de ramo enquanto a página estava
	aberta) é recusada: gravar só parte dela deixaria posições repetidas.
	"""
	frappe.has_permission(DOCTYPE_FILA, "write", throw=True)

	if ramo not in RAMOS:
		frappe.throw(_("Ramo inválido."))

	if not isinstance(ordem, list) or not all(isinstance(item, str) for item in ordem):
		frappe.throw(_("Ordem da fila inválida."))

	atuais = frappe.get_all(DOCTYPE_FILA, filters={"ramo": ramo}, pluck="name")
	if len(ordem) != len(set(ordem)) or set(ordem) != set(atuais):
		frappe.throw(_("A fila mudou desde que a página foi aberta. Recarregue e tente de novo."))

	if not ordem:
		return []

	fila = frappe.qb.DocType(DOCTYPE_FILA)
	posicao = Case()
	for indice, nome in enumerate(ordem, start=1):
		posicao = posicao.when(fila.name == nome, indice)

	frappe.qb.update(fila).set(fila.posicao, posicao).where(fila.name.isin(ordem)).run()

	return [{"name": nome, "posicao": indice} for indice, nome in enumerate(ordem, start=1)]


def _formatar(valor) -> str:
	return format_datetime(valor, "dd/MM/yyyy HH:mm") if valor else ""


def historico_formatado(linhas) -> list[dict[str, Any]]:
	"""Passagens pela fila prontas para exibir, da mais recente para a mais antiga."""
	ordenadas = sorted(
		linhas or [],
		key=lambda linha: str(linha.get("entrada_em") or ""),
		reverse=True,
	)
	resultado = []
	for linha in ordenadas:
		aberta = not linha.get("saida_em")
		resultado.append(
			{
				"entrada_em": _formatar(linha.get("entrada_em")) or ROTULO_NAO_REGISTRADO,
				"status_anterior": (linha.get("status_anterior") or "").strip() or ROTULO_NAO_REGISTRADO,
				"saida_em": ROTULO_NA_FILA if aberta else _formatar(linha.get("saida_em")),
				"status_posterior": "" if aberta else (linha.get("status_posterior") or ""),
				"aberta": aberta,
			}
		)
	return resultado


def historico_por_associado(nomes: list[str]) -> dict[str, list[dict[str, Any]]]:
	"""Histórico de cada Novo Associado da lista, numa consulta só."""
	if not nomes:
		return {}

	linhas = frappe.get_all(
		DOCTYPE_PASSAGEM,
		filters={
			"parenttype": "Novo Associado",
			"parentfield": CAMPO_HISTORICO,
			"parent": ["in", nomes],
		},
		fields=["parent", "entrada_em", "status_anterior", "saida_em", "status_posterior"],
		order_by="entrada_em desc",
	)

	por_associado: dict[str, list] = {}
	for linha in linhas:
		por_associado.setdefault(linha.parent, []).append(linha)

	return {nome: historico_formatado(itens) for nome, itens in por_associado.items()}
