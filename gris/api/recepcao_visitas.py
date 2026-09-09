# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""A visita do jovem no funil de recepção.

Regra central: cada ``Novo Associado`` tem **no máximo uma** ``Agenda de Visitas``. Remarcar
é alterar a data dessa linha, nunca criar outra.

Antes, "Reagendar Visita" na visão geral chamava o mesmo serviço de agendar, que inseria um
registro novo e deixava o antigo parado na data velha. Como ``notificar_visitas_do_dia``
seleciona só por ``data_da_visita``, o registro órfão reaparecia como visita fantasma na
mensagem de sábado no grupo de chefes de seção.

Concentra também a resposta a "qual é a visita dele?", que estava reimplementada em vários
pontos com critérios diferentes (a mais recente aqui, a próxima futura ali).
"""

from __future__ import annotations

import frappe
from frappe.utils import getdate

DOCTYPE = "Agenda de Visitas"

# A visita canônica do jovem é a de data mais alta: com uma remarcação pendente de limpeza no
# legado, a linha nova (futura) vence a antiga. ``creation`` desempata registros do mesmo dia.
ORDEM_CANONICA = "data_da_visita desc, creation desc"

CAMPOS = ["name", "jovem", "data_da_visita", "visita_confirmada", "ramo"]


def _visitas_do_jovem(novo_associado_name: str) -> list[frappe._dict]:
	if not novo_associado_name:
		return []

	return frappe.get_all(
		DOCTYPE,
		filters={"jovem": novo_associado_name},
		fields=CAMPOS,
		order_by=ORDEM_CANONICA,
	)


def visita_do_jovem(novo_associado_name: str) -> frappe._dict | None:
	"""A visita do jovem, ou ``None`` se ele não tem nenhuma.

	Leitura pura: registros duplicados de legado não são apagados aqui, só ignorados — quem
	consolida é ``agendar_ou_remarcar_visita``.
	"""
	visitas = _visitas_do_jovem(novo_associado_name)
	return visitas[0] if visitas else None


def agendar_ou_remarcar_visita(
	novo_associado_name: str,
	data,
	ramo: str | None = None,
	*,
	ignore_permissions: bool = False,
) -> str:
	"""Agenda a visita do jovem, ou remarca a que já existe. Devolve o nome do registro.

	Sem visita: insere (o ``after_insert`` do controller avisa o responsável).
	Com visita: altera a data da existente. A confirmação é zerada porque valia para a data
	antiga, e o responsável recebe o aviso da data nova — remarcar por ``db.set_value`` não
	passava pelo ``after_insert`` e ficava silencioso.

	Duplicatas de legado encontradas no caminho são consolidadas: sobra a canônica.
	"""
	if not novo_associado_name:
		frappe.throw(frappe._("Novo Associado não especificado."))

	data = getdate(data)
	visitas = _visitas_do_jovem(novo_associado_name)

	if not visitas:
		visita = frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"jovem": novo_associado_name,
				"data_da_visita": data,
				"ramo": ramo,
				"visita_confirmada": 0,
			}
		)
		visita.insert(ignore_permissions=ignore_permissions)
		return visita.name

	canonica, *duplicadas = visitas
	for extra in duplicadas:
		frappe.delete_doc(DOCTYPE, extra.name, ignore_permissions=True)

	visita = frappe.get_doc(DOCTYPE, canonica.name)
	mudou_de_data = getdate(visita.data_da_visita) != data

	visita.data_da_visita = data
	if ramo:
		visita.ramo = ramo
	if mudou_de_data:
		visita.visita_confirmada = 0
	visita.save(ignore_permissions=ignore_permissions)

	if mudou_de_data:
		_avisar_remarcacao(novo_associado_name, visita)

	return visita.name


def _avisar_remarcacao(novo_associado_name: str, visita) -> None:
	"""Aviso da data nova, no mesmo espírito do ``after_insert`` do controller.

	Falha silenciosa com log: a remarcação já está gravada e não pode ser desfeita porque o
	WhatsApp caiu.
	"""
	try:
		from gris.api.recepcao_notificacoes import notificar_visita_agendada

		notificar_visita_agendada(novo_associado_name, str(visita.data_da_visita), remarcada=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Aviso de visita remarcada: {visita.name}")


def remover_visita_do_jovem(novo_associado_name: str) -> int:
	"""Apaga a(s) visita(s) do jovem. Devolve quantas saíram.

	Usado quando a etapa "Visita Agendada" é desmarcada no funil: manter o registro deixaria
	o jovem na lista de visitas do dia sem ter visita marcada de verdade.
	"""
	visitas = _visitas_do_jovem(novo_associado_name)
	for visita in visitas:
		frappe.delete_doc(DOCTYPE, visita.name, ignore_permissions=True)

	return len(visitas)
