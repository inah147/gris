# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Normalização e validação de documentos (CPF).

O CPF é a chave de identidade das pessoas no Gris: ``Responsavel``, ``Novo Associado``
e ``Associado`` são nomeados pelo md5 dos dígitos do CPF (ver ``autoname`` de cada
DocType). Concentrar a limpeza, a validação e o cálculo desse identificador aqui evita
que cada tela reimplemente a regra — e é justamente a divergência entre implementações
que gera registro duplicado ou busca que não encontra o que existe.

Foi exatamente o que aconteceu com ``Associado``: até a correção deste módulo, o hash
saía do CPF *como digitado*, então o cadastro do jovem nascia com um ``name`` que a
recepção (que usa os dígitos) nunca encontrava, e o botão "Finalizar Recepção" não
achava ninguém. O CPF cru desses cadastros não existe mais — só o hash ficou —, então
quem procura um ``Associado`` por CPF precisa aceitar as duas convenções:
``ids_possiveis_por_cpf`` e as funções de busca abaixo fazem isso num lugar só.
"""

from __future__ import annotations

import hashlib
import re

import frappe

# Identificador derivado do CPF: md5 em hexadecimal.
_PADRAO_HASH = re.compile(r"^[0-9a-f]{32}$")


def limpar_cpf(cpf: str | None) -> str:
	"""Só os dígitos do CPF, sem pontuação."""
	return re.sub(r"\D", "", cpf or "")


def formatar_cpf(cpf: str | None) -> str:
	"""CPF pontuado (``000.000.000-00``), para exibição em tela e em documento gerado.

	Devolve o valor original quando não há 11 dígitos: cadastros antigos guardam o CPF
	nos dois formatos, e mascarar um valor incompleto esconderia o problema.
	"""
	digitos = limpar_cpf(cpf)
	if len(digitos) != 11:
		return (cpf or "").strip()

	return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"


def cpf_valido(cpf: str | None) -> bool:
	"""Valida os dígitos verificadores do CPF (espelho de ``validateCPF`` no registro.js)."""
	digitos = limpar_cpf(cpf)
	if len(digitos) != 11 or digitos == digitos[0] * 11:
		return False

	for posicao in (9, 10):
		soma = sum(int(digitos[i]) * (posicao + 1 - i) for i in range(posicao))
		resto = 11 - (soma % 11)
		esperado = 0 if resto >= 10 else resto
		if esperado != int(digitos[posicao]):
			return False

	return True


def id_por_cpf(cpf: str | None) -> str:
	"""Identificador (``name``) que os DocTypes de pessoa derivam do CPF.

	Retorna string vazia quando não há CPF, para o chamador decidir o que fazer.
	"""
	digitos = limpar_cpf(cpf)
	if not digitos:
		return ""

	return _md5(digitos)


def _md5(valor: str) -> str:
	return hashlib.md5(valor.encode("utf-8")).hexdigest()  # nosec B324 - identificador, não segredo


def e_hash_de_cpf(valor: str | None) -> bool:
	"""Diz se o valor já é o identificador hasheado, em vez de um CPF.

	Os campos que guardam CPF gravam o hash, não o número. Sem esta checagem, um hook que
	hasheia no save re-hasheia o que já era hash e o campo deixa de bater com o ``name``
	do próprio documento.
	"""
	return bool(valor and _PADRAO_HASH.match(str(valor)))


def ids_possiveis_por_cpf(cpf: str | None) -> tuple[str, ...]:
	"""Identificadores que um cadastro daquele CPF pode ter, do canônico ao legado.

	O primeiro é sempre o canônico (``id_por_cpf``). Depois vêm as convenções antigas do
	``Associado``, que hasheava o CPF com a pontuação que o operador digitou ou que veio
	do relatório do Paxtu. Quem recebe um valor que já é hash devolve só ele.
	"""
	if not cpf:
		return ()

	if e_hash_de_cpf(cpf):
		return (str(cpf),)

	candidatos: list[str] = []
	for candidato in (id_por_cpf(cpf), _md5(str(cpf).strip()), _md5(formatar_cpf(cpf))):
		if candidato and candidato not in candidatos:
			candidatos.append(candidato)

	return tuple(candidatos)


def localizar_associado_por_cpf(cpf: str | None, registro: str | None = None) -> str | None:
	"""``name`` do ``Associado`` daquele CPF, nas duas convenções de hash.

	``registro`` (o número de registro na UEB) é o último recurso: é a mesma chave humana
	que o importador do Paxtu usa quando o CPF não encontra o cadastro.
	"""
	for candidato in ids_possiveis_por_cpf(cpf):
		if frappe.db.exists("Associado", candidato):
			return candidato

	registro = (registro or "").replace(" ", "")
	if registro:
		return frappe.db.get_value("Associado", {"registro": registro}, "name")

	return None


def localizar_associados_em_lote(pessoas: list[dict]) -> dict[str, str]:
	"""``chave`` -> ``name`` do ``Associado``, para uma lista inteira, em duas consultas.

	Versão em lote de ``localizar_associado_por_cpf``, para telas que resolvem o cadastro
	de muita gente (o kanban da recepção) sem uma consulta por linha. Cada item precisa
	de ``chave`` e ``cpf``; ``registro`` é opcional. Chaves sem cadastro ficam fora do
	resultado.
	"""
	candidatos_por_chave: dict[str, tuple[str, ...]] = {}
	registro_por_chave: dict[str, str] = {}
	todos_os_candidatos: set[str] = set()

	for pessoa in pessoas:
		chave = pessoa.get("chave")
		if not chave:
			continue

		candidatos = ids_possiveis_por_cpf(pessoa.get("cpf"))
		candidatos_por_chave[chave] = candidatos
		todos_os_candidatos.update(candidatos)

		registro = (pessoa.get("registro") or "").replace(" ", "")
		if registro:
			registro_por_chave[chave] = registro

	existentes: set[str] = set()
	if todos_os_candidatos:
		existentes = {
			linha.name
			for linha in frappe.get_all(
				"Associado", filters={"name": ["in", list(todos_os_candidatos)]}, fields=["name"]
			)
		}

	encontrados: dict[str, str] = {}
	chave_por_registro: dict[str, str] = {}

	for chave, candidatos in candidatos_por_chave.items():
		achado = next((candidato for candidato in candidatos if candidato in existentes), None)
		if achado:
			encontrados[chave] = achado
		elif chave in registro_por_chave:
			chave_por_registro[registro_por_chave[chave]] = chave

	if chave_por_registro:
		for linha in frappe.get_all(
			"Associado",
			filters={"registro": ["in", list(chave_por_registro)]},
			fields=["name", "registro"],
		):
			chave = chave_por_registro.get(linha.registro)
			if chave and chave not in encontrados:
				encontrados[chave] = linha.name

	return encontrados


def localizar_novo_associado(associado_name: str | None, cpf: str | None = None) -> str | None:
	"""``name`` do ``Novo Associado`` que corresponde àquele ``Associado``, se ainda há um.

	O caminho normal é direto: os dois DocTypes derivam o ``name`` do mesmo CPF. Quando o
	``Associado`` é de antes da correção da convenção, o CPF cru dele já não existe (o
	campo guarda o hash), então a volta é pelo CPF que o funil ainda tem em claro. O funil
	é uma tabela de passagem — quem termina a recepção sai dela —, então a comparação
	cabe numa consulta só.
	"""
	alvos = {valor for valor in (associado_name, cpf) if valor}
	if not alvos:
		return None

	if associado_name and frappe.db.exists("Novo Associado", associado_name):
		return associado_name

	for linha in frappe.get_all("Novo Associado", fields=["name", "cpf"]):
		if alvos.intersection(ids_possiveis_por_cpf(linha.cpf)):
			return linha.name

	return None
