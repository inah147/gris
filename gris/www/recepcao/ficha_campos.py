# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Ordem e formato dos campos da ficha de registro, na sequência do Paxtu.

A ficha existe para ser transcrita: a recepção lê daqui e digita no Paxtu, campo a campo.
Quando a ordem das duas telas não bate, quem transcreve fica saltando de bloco em bloco — o
primeiro pedido do documento de ajustes é exatamente esse ("Colocar na ordem!!").

Manter a lista aqui, e não espalhada em ``<div class="field">`` no template, é o que permite
conferir a ordem contra o Paxtu num lugar só, e o que faz o bloco do jovem e o de cada
responsável seguirem a mesma sequência sem precisar lembrar de mudar os dois.
"""

from __future__ import annotations

from typing import Any

from frappe.utils import format_date

from gris.utils.contato import partes_telefone

TEXTO = "texto"
DATA = "data"
TELEFONE = "telefone"
SIM_NAO = "sim_nao"

BLOCOS_DO_ASSOCIADO: list[dict[str, Any]] = [
	{
		"titulo": "Dados do Associado",
		"descricao": "Informações pessoais",
		"campos": [
			("apelido_ou_nome_social", "Apelido ou nome social", TEXTO),
			("data_de_nascimento", "Data de Nascimento", DATA),
			("etnia", "Etnia", TEXTO),
			("sexo", "Sexo", TEXTO),
			("estrangeiro", "É estrangeiro?", SIM_NAO),
			("pais_nascimento", "País de Nascimento", TEXTO),
			("uf_de_nascimento", "UF de Nascimento", TEXTO),
			("cidade_de_nascimento", "Cidade de Nascimento", TEXTO),
			("rg", "RG", TEXTO),
			("orgao_expedidor", "Órgão Expedidor", TEXTO),
			("cpf", "CPF", TEXTO),
			("estado_civil", "Estado Civil", TEXTO),
			("religiao", "Religião", TEXTO),
			("denominacao", "Denominação", TEXTO),
		],
	},
	{
		"titulo": "Informações Profissionais e Acadêmicas",
		"descricao": None,
		"campos": [
			("escolaridade", "Escolaridade", TEXTO),
			("profissao", "Profissão", TEXTO),
			("local_de_trabalho", "Área de Atuação", TEXTO),
		],
	},
	{
		"titulo": "Endereço e Dados de Contato",
		"descricao": None,
		"campos": [
			("cep", "CEP do endereço residencial", TEXTO),
			("endereco", "Endereço", TEXTO),
			("numero", "Número", TEXTO),
			("complemento", "Complemento", TEXTO),
			("estado", "Estado", TEXTO),
			("cidade", "Cidade", TEXTO),
			("bairro", "Bairro", TEXTO),
			("email", "E-mail", TEXTO),
			("email_escoteiros", "E-mail Escoteiros do Brasil", TEXTO),
			("celular", "Celular", TELEFONE),
			("telefone_secundario", "Telefone secundário", TELEFONE),
		],
	},
	{
		"titulo": "Dados de Cobrança",
		"descricao": None,
		"campos": [
			("email_cobranca", "E-mail de Cobrança", TEXTO),
			("telefone_cobranca", "Telefone de Cobrança", TELEFONE),
		],
	},
]

# O ``Responsavel`` não guarda etnia, religião nem nacionalidade — só o associado tem. A ordem
# dos que existem é a mesma do bloco acima, para a transcrição seguir o mesmo caminho.
BLOCOS_DO_RESPONSAVEL: list[dict[str, Any]] = [
	{
		"titulo": "Dados Pessoais",
		"descricao": None,
		"campos": [
			("data_de_nascimento", "Data de Nascimento", DATA),
			("sexo", "Sexo", TEXTO),
			("uf_de_nascimento", "UF de Nascimento", TEXTO),
			("cidade_de_nascimento", "Cidade de Nascimento", TEXTO),
			("rg", "RG", TEXTO),
			("orgao_expedidor", "Órgão Expedidor", TEXTO),
			("cpf", "CPF", TEXTO),
			("estado_civil", "Estado Civil", TEXTO),
		],
	},
	{
		"titulo": "Informações Profissionais e Acadêmicas",
		"descricao": None,
		"campos": [
			("escolaridade", "Escolaridade", TEXTO),
			("profissão", "Profissão", TEXTO),
			("local_de_trabalho", "Área de Atuação", TEXTO),
		],
	},
	{
		"titulo": "Endereço e Dados de Contato",
		"descricao": None,
		"campos": [
			("cep", "CEP do endereço residencial", TEXTO),
			("endereço", "Endereço", TEXTO),
			("número", "Número", TEXTO),
			("complemento", "Complemento", TEXTO),
			("estado", "Estado", TEXTO),
			("cidade", "Cidade", TEXTO),
			("bairro", "Bairro", TEXTO),
			("email", "E-mail", TEXTO),
			("celular", "Celular", TELEFONE),
			("telefone_secundario", "Telefone secundário", TELEFONE),
		],
	},
]


def montar_blocos(doc, blocos: list[dict[str, Any]]) -> list[dict[str, Any]]:
	"""Transforma a definição de blocos nos campos prontos para o template.

	Cada campo vira ``{"label", "valor", "vazio"}``; telefone vira dois campos, DDI e número.
	"""
	montados = []

	for bloco in blocos:
		campos: list[dict[str, Any]] = []
		for fieldname, label, tipo in bloco["campos"]:
			campos.extend(_montar_campo(doc, fieldname, label, tipo))

		montados.append({"titulo": bloco["titulo"], "descricao": bloco.get("descricao"), "campos": campos})

	return montados


def _montar_campo(doc, fieldname: str, label: str, tipo: str) -> list[dict[str, Any]]:
	valor = doc.get(fieldname)

	if tipo == TELEFONE:
		return _campos_de_telefone(valor, label)

	if tipo == DATA:
		# ``format_date`` de ``frappe.utils``: o ``frappe.format_date`` que o template Jinja
		# enxerga é do namespace do Jinja, e não existe no módulo importado aqui.
		texto = format_date(valor, "dd/MM/yyyy") if valor else ""
	elif tipo == SIM_NAO:
		texto = "Sim" if valor else "Não"
	else:
		texto = str(valor).strip() if valor not in (None, "") else ""

	return [_campo(label, texto)]


def _campos_de_telefone(valor, label: str) -> list[dict[str, Any]]:
	"""Um telefone vira DDI e número, em campos separados.

	O Paxtu não usa o ``+55`` que o GRIS grava junto do número, e um campo único obriga a
	selecionar o pedaço com o mouse antes de copiar. Separado, cada parte é copiável inteira.
	"""
	partes = partes_telefone(valor)
	if not partes["numero"]:
		return [_campo(f"{label} (DDI)", ""), _campo(label, "")]

	return [
		_campo(f"{label} (DDI)", partes["ddi"]),
		_campo(label, partes["nacional_formatado"] or partes["numero"]),
	]


def _campo(label: str, texto: str) -> dict[str, Any]:
	return {"label": label, "valor": texto or "-", "vazio": not texto}
