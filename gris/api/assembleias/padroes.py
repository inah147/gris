# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""O que uma assembleia recebe ao nascer e os valores das variáveis dos textos (RF-02)."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta

import frappe
from frappe.utils import cint, get_time, getdate

from gris.api.assembleias import constantes as c
from gris.api.assembleias.pessoas import contar_associados_com_registro_ativo, ocupantes_da_funcao
from gris.api.assembleias.textos import substituir
from gris.utils.diretoria import funcao_do_presidente

MESES = (
	"janeiro",
	"fevereiro",
	"março",
	"abril",
	"maio",
	"junho",
	"julho",
	"agosto",
	"setembro",
	"outubro",
	"novembro",
	"dezembro",
)

MINUTOS_ATE_SEGUNDA_CONVOCACAO = 30


def configuracoes():
	return frappe.get_single(c.DOCTYPE_CONFIGURACOES)


def data_por_extenso(data) -> str:
	"""05 de dezembro de 2026 — com o dia em dois dígitos, como nos editais do grupo."""
	if not data:
		return ""
	data = getdate(data)
	return f"{data.day:02d} de {MESES[data.month - 1]} de {data.year}"


def data_curta(data) -> str:
	return getdate(data).strftime("%d/%m/%Y") if data else ""


def hora(valor) -> str:
	return get_time(valor).strftime("%H:%M") if valor else ""


def segunda_convocacao(primeira) -> str:
	"""Meia hora depois da primeira (estatuto: segunda convocação, qualquer número)."""
	if not primeira:
		return ""
	instante = datetime.combine(date(2000, 1, 1), get_time(primeira)) + timedelta(
		minutes=MINUTOS_ATE_SEGUNDA_CONVOCACAO
	)
	return instante.strftime("%H:%M:%S")


def vagas_de_delegado(referencia, por_vaga: int) -> int:
	"""Uma vaga para cada fração de `por_vaga` associados ativos com registro ativo."""
	por_vaga = cint(por_vaga) or 50
	return math.ceil(contar_associados_com_registro_ativo(referencia) / por_vaga)


def data_da_assembleia_anterior(data, ignorar: str | None = None) -> str:
	filtros = {"data": ["<", getdate(data)]}
	if ignorar:
		filtros["name"] = ["!=", ignorar]
	anterior = frappe.get_all(
		c.DOCTYPE_ASSEMBLEIA, filters=filtros, fields=["data"], order_by="data desc", limit_page_length=1
	)
	return data_curta(anterior[0].data) if anterior else "[data]"


def exercicio_do_balanco(data) -> int:
	"""Ano do balanço apreciado. O ano fiscal fecha em 31/12 e o balanço sai em até 60 dias
	(art. 40): assembleia do primeiro semestre aprecia o ano anterior; a do segundo, o
	próprio ano, como a de dezembro de 2026."""
	data = getdate(data)
	return data.year if data.month >= 7 else data.year - 1


def gestao_eleita(data) -> str:
	"""Biênio da diretoria eleita: o seguinte ao ano da assembleia, se ela for no segundo
	semestre (dezembro de 2026 elege 2027-2028); o próprio ano, se for no primeiro."""
	inicio = getdate(data).year + (1 if getdate(data).month >= 7 else 0)
	return f"{inicio}-{inicio + 1}"


def _dados_da_uel() -> dict:
	uel = frappe.get_single("Definicao da UEL")
	numeral = f"{uel.numeral}/{uel.regiao}" if uel.numeral and uel.regiao else str(uel.numeral or "")
	endereco = ", ".join(parte for parte in (uel.rua, uel.numero) if parte)
	if uel.bairro:
		endereco = f"{endereco} - {uel.bairro}" if endereco else uel.bairro
	return {
		"nome_uel": uel.nome_da_uel or "",
		"numeral": numeral,
		"cnpj": uel.cnpj or "",
		"endereco_sede": endereco,
	}


def valores_da_assembleia(doc, config=None) -> dict[str, str]:
	"""Valor de cada variável de `textos.VARIAVEIS` para esta assembleia."""
	config = config or configuracoes()
	data = getdate(doc.data) if doc.data else getdate()
	presidentes = ocupantes_da_funcao(funcao_do_presidente(), data)
	return {
		**_dados_da_uel(),
		"tipo": (doc.tipo or "").upper(),
		"tipo_minusculo": (doc.tipo or "").lower(),
		"data": data_por_extenso(doc.data),
		"data_curta": data_curta(doc.data),
		"hora_primeira": hora(doc.hora_primeira_convocacao),
		"hora_segunda": hora(doc.hora_segunda_convocacao),
		"local": doc.local or "",
		"cidade": config.cidade or "",
		"data_publicacao": data_por_extenso(doc.data_publicacao_edital) or "[data de publicação]",
		"diretor_presidente": " e ".join(presidentes) or "[diretor presidente]",
		"ano": str(data.year),
		"ano_anterior": str(data.year - 1),
		"gestao": gestao_eleita(data),
		"exercicio": str(exercicio_do_balanco(data)),
		"data_assembleia_anterior": data_da_assembleia_anterior(data, ignorar=doc.name),
	}


def itens_da_pauta_padrao(tipo: str, config=None) -> list[dict]:
	"""Os itens padrão do tipo, ainda com as variáveis nos títulos."""
	config = config or configuracoes()
	tabela = config.pauta_extraordinaria if tipo == c.TIPO_EXTRAORDINARIA else config.pauta_ordinaria
	return [
		{
			"titulo": item.titulo,
			"tem_votacao": cint(item.tem_votacao),
			"finalidade": item.finalidade or "",
			"orientacao_conducao": item.orientacao_conducao or c.orientacao_da_finalidade(item.finalidade),
		}
		for item in tabela
	]


def aplicar_pauta_padrao(doc, config=None) -> None:
	"""Troca a pauta pela padrão do tipo, com os títulos já resolvidos (CA-02.3)."""
	config = config or configuracoes()
	valores = valores_da_assembleia(doc, config)
	doc.set("pauta", [])
	for item in itens_da_pauta_padrao(doc.tipo, config):
		doc.append("pauta", {**item, "titulo": substituir(item["titulo"], valores)})


def preencher_padroes(doc, config=None) -> None:
	"""Tudo o que a assembleia copia das configurações ao ser criada."""
	config = config or configuracoes()
	# O Frappe põe a hora atual em todo campo Time de um doc novo: a segunda convocação
	# é sempre recalculada (os horários da ata são limpos no validate do doc novo).
	doc.hora_segunda_convocacao = segunda_convocacao(doc.hora_primeira_convocacao)
	doc.edital_texto_topo = config.texto_topo_edital or c.TEXTO_TOPO_EDITAL
	doc.edital_texto_rodape = config.texto_rodape_edital or c.TEXTO_RODAPE_EDITAL
	doc.edital_incluir_links = 1
	doc.vagas_delegados = vagas_de_delegado(doc.data, config.associados_por_delegado)
	aplicar_pauta_padrao(doc, config)
	doc.set("checklist", [])
	for chave, fase, titulo, somente_eletiva in c.CHECKLIST_PADRAO:
		doc.append(
			"checklist",
			{"chave": chave, "fase": fase, "titulo": titulo, "somente_eletiva": somente_eletiva},
		)
