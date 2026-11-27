# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Formulários de candidatura e de assuntos gerais: quando cada um está aberto (RF-12).

`situacao_do_formulario` é pura: recebe a assembleia, as regras, o instante e as
contagens, e devolve o estado. Os endpoints de envio ficam neste módulo também.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import frappe
from frappe.utils import cint, get_datetime, get_time, get_url, getdate

from gris.api.assembleias import constantes as c

ORDEM_DOS_FORMULARIOS = (
	c.FORMULARIO_MESA,
	c.FORMULARIO_DELEGADO,
	c.FORMULARIO_COMISSAO_FISCAL,
	c.FORMULARIO_DIRETORIA,
	c.FORMULARIO_ASSUNTOS_GERAIS,
)

ROTULO_DO_FORMULARIO = {
	c.FORMULARIO_MESA: "Mesa diretora (presidente e secretário)",
	c.FORMULARIO_DELEGADO: "Delegados para a Assembleia Regional",
	c.FORMULARIO_COMISSAO_FISCAL: "Comissão fiscal",
	c.FORMULARIO_DIRETORIA: "Chapas para a diretoria",
	c.FORMULARIO_ASSUNTOS_GERAIS: "Assuntos gerais",
}

# Como o cargo aparece na frase do edital: "Candidaturas para ... devem ser encaminhadas".
CARGO_NO_EDITAL = {
	c.FORMULARIO_MESA: "a mesa diretora (presidente e secretário)",
	c.FORMULARIO_DELEGADO: "delegados para a Assembleia Regional",
	c.FORMULARIO_COMISSAO_FISCAL: "a Comissão Fiscal",
	c.FORMULARIO_DIRETORIA: "as chapas da diretoria",
}

NUMEROS_POR_EXTENSO = {1: "uma", 2: "duas", 3: "três", 4: "quatro", 5: "cinco", 6: "seis"}


def inicio_da_assembleia(data, hora) -> datetime:
	return datetime.combine(getdate(data), get_time(hora or "00:00:00"))


def regras_de_prazo(config) -> dict:
	"""Unidade e valor de cada prazo, mais as vagas e o "manter aberto"."""
	return {
		"prazos": {
			chave: (
				config.get(f"prazo_{chave}_unidade") or c.PRAZO_SEM_LIMITE,
				cint(config.get(f"prazo_{chave}_valor")),
			)
			for chave in ORDEM_DOS_FORMULARIOS
		},
		"manter_aberto": cint(config.manter_aberto_sem_candidatos),
		"vagas_comissao_fiscal": cint(config.vagas_comissao_fiscal) + cint(config.suplentes_comissao_fiscal),
	}


def limite_de_inscricao(chave: str, inicio: datetime, regras: dict) -> datetime:
	unidade, valor = regras["prazos"].get(chave, (c.PRAZO_SEM_LIMITE, 0))
	if unidade == c.PRAZO_DIAS:
		return inicio - timedelta(days=valor)
	if unidade == c.PRAZO_HORAS:
		return inicio - timedelta(hours=valor)
	return inicio


def falta_candidato(chave: str, contagens: dict, regras: dict, vagas_delegados: int) -> bool:
	"""Art. 9, § 5º: sem inscrições suficientes, aceitam-se novas até a eleição."""
	if chave == c.FORMULARIO_MESA:
		return not contagens.get(c.CARGO_PRESIDENTE_MESA) or not contagens.get(c.CARGO_SECRETARIO_MESA)
	if chave == c.FORMULARIO_COMISSAO_FISCAL:
		return cint(contagens.get(c.CARGO_COMISSAO_FISCAL)) < regras["vagas_comissao_fiscal"]
	if chave == c.FORMULARIO_DELEGADO:
		return cint(contagens.get(c.CARGO_DELEGADO)) < max(cint(vagas_delegados), 1)
	if chave == c.FORMULARIO_DIRETORIA:
		return not contagens.get("chapas")
	return False


def situacao_do_formulario(
	chave: str,
	*,
	finalidades: set[str],
	inicio: datetime,
	regras: dict,
	agora: datetime,
	contagens: dict,
	vagas_delegados: int = 0,
) -> dict:
	"""Estado de um formulário: previsto, aberto, até quando e se foi reaberto."""
	limite = limite_de_inscricao(chave, inicio, regras)
	previsto = c.FINALIDADE_DO_FORMULARIO[chave] in finalidades
	estado = {"chave": chave, "previsto": previsto, "aberto": False, "reaberto": False, "fecha_em": limite}
	if not previsto or agora >= inicio:
		return estado
	if agora < limite:
		estado["aberto"] = True
		return estado
	if regras["manter_aberto"] and falta_candidato(chave, contagens, regras, vagas_delegados):
		estado.update({"aberto": True, "reaberto": True, "fecha_em": inicio})
	return estado


def contar_inscricoes(assembleia: str) -> dict:
	"""Candidaturas ativas por cargo, chapas ativas e assuntos, em três consultas."""
	contagens: dict = {}
	for linha in frappe.get_all(
		c.DOCTYPE_CANDIDATURA,
		filters={"assembleia": assembleia, "status": "Ativa"},
		fields=["cargo", "count(name) as total"],
		group_by="cargo",
	):
		contagens[linha.cargo] = cint(linha.total)
	contagens["chapas"] = frappe.db.count(c.DOCTYPE_CHAPA, {"assembleia": assembleia, "status": "Ativa"})
	contagens["assuntos"] = frappe.db.count(c.DOCTYPE_ASSUNTO, {"assembleia": assembleia})
	return contagens


def link_do_formulario(assembleia: str, chave: str) -> str:
	if chave == c.FORMULARIO_ASSUNTOS_GERAIS:
		return get_url(f"/assembleias/assunto_geral?assembleia={assembleia}")
	return get_url(f"/assembleias/candidatura?assembleia={assembleia}&cargo={chave}")


def prazo_por_extenso(chave: str, regras: dict, inicio: datetime) -> str:
	"""Como o edital diz o prazo: data por extenso, ou horas antes da convocação."""
	from gris.api.assembleias.padroes import data_por_extenso

	unidade, valor = regras["prazos"].get(chave, (c.PRAZO_SEM_LIMITE, 0))
	if unidade == c.PRAZO_DIAS:
		return data_por_extenso(limite_de_inscricao(chave, inicio, regras).date())
	if unidade == c.PRAZO_HORAS:
		quantidade = NUMEROS_POR_EXTENSO.get(valor, str(valor))
		return f"{quantidade} hora{'s' if valor != 1 else ''} antes da primeira convocação"
	return "o início da assembleia"


def formularios_da_assembleia(doc, config, agora=None) -> list[dict]:
	"""Os cinco formulários com estado, link e prazo, na ordem da Visão Geral."""
	agora = get_datetime(agora) if agora else get_datetime()
	regras = regras_de_prazo(config)
	inicio = inicio_da_assembleia(doc.data, doc.hora_primeira_convocacao)
	finalidades = {item.finalidade for item in doc.pauta if item.finalidade}
	contagens = contar_inscricoes(doc.name) if doc.name else {}
	formularios = []
	for chave in ORDEM_DOS_FORMULARIOS:
		estado = situacao_do_formulario(
			chave,
			finalidades=finalidades,
			inicio=inicio,
			regras=regras,
			agora=agora,
			contagens=contagens,
			vagas_delegados=cint(doc.vagas_delegados),
		)
		formularios.append(
			{
				**estado,
				"rotulo": ROTULO_DO_FORMULARIO[chave],
				"link": link_do_formulario(doc.name, chave),
				"prazo": prazo_por_extenso(chave, regras, inicio),
				"fecha_em": str(estado["fecha_em"]),
			}
		)
	return formularios
