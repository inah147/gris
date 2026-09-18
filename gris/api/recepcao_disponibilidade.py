# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Disponibilidade de datas para visita de novo associado.

A regra, num lugar só: a visita acontece em **sábado**, dentro dos próximos
``JANELA_EM_DIAS`` dias, e um sábado fica **bloqueado** quando existe atividade no
``Calendario`` cobrindo o dia cuja ``secao`` pertence ao ramo pretendido — a não ser que
a atividade libere a visitação (ver :func:`evento_libera_visita`).

Existia em quatro cópias (duas em ``www/recepcao/agenda_visitas.py``, duas em
``www/responsavel/beneficiarios.py``), que já tinham divergido entre si. Como a lista de
datas oferecida no portal e a validação do submit saíam de funções diferentes, qualquer
mudança de regra tinha de ser feita em quatro lugares — e esquecer um deles produzia o
pior sintoma possível: o select oferece a data e o submit recusa.

As páginas continuam expondo os mesmos nomes de função de antes, como invólucros finos:
é por lá que o MCP e os testes entram.
"""

from __future__ import annotations

from datetime import date

import frappe
from frappe.utils import add_days, cint, getdate, today

JANELA_EM_DIAS = 60
DIA_DA_VISITA = 5  # sábado, em date.weekday()

# Campos do Calendario que a regra precisa. Um flag novo de liberação entra aqui e em
# `evento_libera_visita`, e vale para todos os consumidores de uma vez.
CAMPOS_DO_EVENTO = (
	"inicio",
	"termino",
	"secao",
	"abertura_geral",
	"permite_visita_novos_associados",
)


def evento_libera_visita(evento) -> bool:
	"""A atividade cai no dia e na seção do ramo, mas ainda assim deixa receber visita.

	``abertura_geral`` libera o dia para todos os ramos; ``permite_visita_novos_associados``
	libera só o ramo da seção desta atividade — a decisão é por linha, não por dia.
	"""
	return bool(cint(evento.get("abertura_geral")) or cint(evento.get("permite_visita_novos_associados")))


def secoes_dos_ramos(ramos) -> set[str]:
	"""Seções do Calendario que dizem respeito aos ramos informados.

	``Calendario.secao`` e ``Associado.secao`` são texto livre com o nome real da seção
	("Alcateia", "Tropa", "Clã"), enquanto o novo associado tem ``ramo`` ("Lobinho",
	"Escoteiro"...). A ponte é feita pelos Associados já cadastrados; o próprio nome do
	ramo entra no conjunto porque parte do calendário é preenchida com ele.
	"""
	ramos_validos = {ramo for ramo in (ramos or []) if ramo}
	if not ramos_validos:
		return set()

	linhas = frappe.get_all(
		"Associado",
		filters={"ramo": ["in", list(ramos_validos)], "secao": ["is", "set"]},
		fields=["secao", "ramo"],
		distinct=True,
	)

	secoes = {linha.secao for linha in linhas if linha.secao}
	secoes.update(ramos_validos)
	return secoes


def janela_da_visita(inicio=None) -> tuple[date, date]:
	"""Primeiro e último dia em que se pode agendar, contados de hoje."""
	inicio = getdate(inicio or today())
	return inicio, add_days(inicio, JANELA_EM_DIAS)


def sabados_da_janela(inicio=None) -> list[date]:
	inicio, fim = janela_da_visita(inicio)

	sabados = []
	atual = inicio
	while atual <= fim:
		if atual.weekday() == DIA_DA_VISITA:
			sabados.append(atual)
		atual = add_days(atual, 1)
	return sabados


def eventos_da_janela(inicio, fim) -> list:
	"""Atividades que cobrem qualquer parte do intervalo, comparando por dia.

	Os limites viram início e fim do dia: ``inicio``/``termino`` do Calendario são Datetime,
	e filtrar por data crua compara contra a meia-noite — a atividade que começa às 08:00 do
	último dia do intervalo ficava de fora, e o dia passava por livre.
	"""
	return frappe.get_all(
		"Calendario",
		filters={
			"inicio": ["<=", f"{getdate(fim)} 23:59:59"],
			"termino": [">=", f"{getdate(inicio)} 00:00:00"],
		},
		fields=list(CAMPOS_DO_EVENTO),
	)


def datas_disponiveis_para_ramos(ramos) -> list[date]:
	"""Sábados livres para o conjunto de ramos informado.

	Um sábado bloqueado para **qualquer** um dos ramos sai da lista: quem agenda para
	vários beneficiários de uma vez grava um por um, e cada gravação é validada contra o
	ramo daquele beneficiário.
	"""
	inicio, fim = janela_da_visita()
	sabados = sabados_da_janela(inicio)
	if not sabados:
		return []

	secoes = secoes_dos_ramos(ramos)
	if not secoes:
		# Sem ramo conhecido não há seção que bloqueie — é o caso do beneficiário cujo
		# ramo ainda não foi derivado da data de nascimento.
		return sabados

	bloqueados = set()
	for evento in eventos_da_janela(inicio, fim):
		if evento_libera_visita(evento):
			continue

		if not evento.secao or evento.secao not in secoes:
			continue

		evento_inicio = getdate(evento.inicio)
		evento_fim = getdate(evento.termino)

		for sabado in sabados:
			if evento_inicio <= sabado <= evento_fim:
				bloqueados.add(sabado)

	return [sabado for sabado in sabados if sabado not in bloqueados]


def datas_disponiveis_para_ramo(ramo) -> list[date]:
	return datas_disponiveis_para_ramos({ramo} if ramo else set())


def data_disponivel_para_ramos(ramos, data) -> bool:
	"""Checa uma data só, sem montar a janela inteira."""
	if not data:
		return False

	inicio, fim = janela_da_visita()
	alvo = getdate(data)

	if alvo < inicio or alvo > fim or alvo.weekday() != DIA_DA_VISITA:
		return False

	secoes = secoes_dos_ramos(ramos)
	if not secoes:
		return True

	for evento in eventos_da_janela(alvo, alvo):
		if evento_libera_visita(evento):
			continue
		if evento.secao and evento.secao in secoes:
			return False

	return True


def data_disponivel_para_ramo(ramo, data) -> bool:
	if not ramo or not data:
		return False

	return data_disponivel_para_ramos({ramo}, data)
