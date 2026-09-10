# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

from typing import Any

import frappe
from frappe import _


def format_phone(phone):
	"""Normaliza número de telefone para armazenamento no formato +55DDNÚMERO.

	Corrige DDD duplicado (e.g. +1111971872252 → +5511971872252).
	Aceita formatos como: +5511999999999, 5511999999999, 11999999999, (11) 99999-9999.
	"""
	if not phone:
		return phone

	digits = "".join(c for c in str(phone) if c.isdigit())

	if not digits:
		return ""

	# Fix duplicate DDD with country code: e.g. 551111971872252 (15 digits) → 5511971872252
	if digits.startswith("55") and len(digits) >= 14 and digits[2:4] == digits[4:6]:
		digits = digits[:2] + digits[4:]

	# Fix duplicate DDD without country code: e.g. 1111971872252 (13 digits) → 11971872252
	if not digits.startswith("55") and len(digits) > 11 and digits[:2] == digits[2:4]:
		digits = digits[2:]

	# Brazil numbers are usually 10 or 11 digits (DDD + 8 or 9 digit number)
	if len(digits) in [10, 11]:
		return f"+55{digits}"

	# Already has country code (12 or 13 digits)
	if len(digits) in [12, 13] and digits.startswith("55"):
		return f"+{digits}"

	return phone


def partes_telefone(telefone: str | None) -> dict[str, str]:
	"""Separa um telefone gravado em E.164 nas partes que cada sistema usa.

	O GRIS guarda ``+5511912345678``; o Paxtu pede o número sem o código do país, e quem
	transcreve precisa copiar só do DDD em diante. Um campo único com tudo junto obriga a
	selecionar o pedaço com o mouse, que é lento e erra — daí a ficha da recepção exibir DDI e
	número em campos separados, cada um copiável por inteiro.

	Devolve ``ddi`` (com o ``+``), ``ddd``, ``numero`` e ``nacional_formatado``. Fora do Brasil
	não se tenta adivinhar DDD: o número inteiro vai em ``numero``, porque cada país divide o
	seu de um jeito e fatiar errado é pior do que não fatiar.
	"""
	vazio = {"ddi": "", "ddd": "", "numero": "", "nacional_formatado": ""}
	if not telefone:
		return vazio

	bruto = str(telefone).strip()
	digitos = "".join(c for c in bruto if c.isdigit())
	if not digitos:
		return vazio

	if bruto.startswith("+"):
		# Mesma resolução do componente phone-input: vence o DDI de prefixo mais longo.
		dial = _maior_ddi(digitos)
		if not dial:
			return {"ddi": "", "ddd": "", "numero": digitos, "nacional_formatado": digitos}
		resto = digitos[len(dial) :]
		if dial != "55":
			return {"ddi": f"+{dial}", "ddd": "", "numero": resto, "nacional_formatado": resto}
	elif digitos.startswith("55") and len(digitos) in (12, 13):
		resto = digitos[2:]
	elif len(digitos) in (10, 11):
		# Sem código de país e no tamanho brasileiro: o DDI implícito é o +55.
		resto = digitos
	else:
		return {"ddi": "", "ddd": "", "numero": digitos, "nacional_formatado": digitos}

	ddd, numero = resto[:2], resto[2:]

	if len(numero) == 9:
		formatado = f"({ddd}) {numero[0]} {numero[1:5]}-{numero[5:]}"
	elif len(numero) == 8:
		formatado = f"({ddd}) {numero[:4]}-{numero[4:]}"
	else:
		formatado = f"({ddd}) {numero}".strip()

	return {"ddi": "+55", "ddd": ddd, "numero": numero, "nacional_formatado": formatado}


def _maior_ddi(digitos: str) -> str:
	"""DDI de prefixo mais longo que casa com ``digitos``, ou string vazia."""
	from gris.utils.phone_countries import get_phone_countries

	candidatos = {pais["dial"] for pais in get_phone_countries()}
	for tamanho in (4, 3, 2, 1):
		prefixo = digitos[:tamanho]
		if prefixo in candidatos:
			return prefixo

	return ""


def telefone_do_usuario(user: str | None) -> str:
	"""Telefone de um User, na ordem em que o GRIS costuma encontrá-lo.

	1. ``User.mobile_no`` — o campo padrão do Frappe, raramente preenchido aqui.
	2. ``Associado.telefone`` casado por ``id_escoteiros``: o login do associado é
	   o id@escoteiros, não o e-mail comum (mesma resolução de
	   ``gris.utils.gestores`` e de ``recepcao_mensagens``).
	3. ``Responsavel.celular`` casado por ``email``: os responsáveis são Website
	   Users e não têm registro de Associado nenhum.

	Retorna string vazia quando a pessoa não tem telefone em lugar nenhum — quem
	chama decide se isso é um erro ou apenas motivo para não enviar nada.
	"""
	user = (user or "").strip()
	if not user or user == "Guest":
		return ""

	mobile_no = frappe.db.get_value("User", user, "mobile_no")
	if (mobile_no or "").strip():
		return str(mobile_no).strip()

	telefone = frappe.db.get_value("Associado", {"id_escoteiros": user}, "telefone")
	if (telefone or "").strip():
		return str(telefone).strip()

	responsavel = frappe.db.get_value(
		"Responsavel", {"email": user}, ["celular", "telefone_secundario"], as_dict=True
	)
	if responsavel:
		telefone = (responsavel.get("celular") or "").strip() or (
			responsavel.get("telefone_secundario") or ""
		).strip()
		if telefone:
			return telefone

	return ""


@frappe.whitelist()
def get_contato_pessoa(doctype_name: str, docname: str) -> dict[str, Any]:
	if doctype_name not in {"Associado", "Responsavel"}:
		frappe.throw(_("Tipo de pessoa invalido."))

	if doctype_name == "Associado":
		return _get_associado_payload(docname)

	return _get_responsavel_payload(docname)


def _get_associado_payload(name: str) -> dict[str, Any]:
	data = frappe.db.get_value(
		"Associado",
		name,
		["nome_completo", "data_de_nascimento", "id_escoteiros", "email", "telefone"],
		as_dict=True,
	)
	if not data:
		frappe.throw(_("Associado nao encontrado."))

	email = data.get("id_escoteiros") or data.get("email")
	if not email or not data.get("telefone"):
		frappe.throw(_("Associado selecionado nao possui email ou telefone preenchido."))

	return {
		"nome": data.get("nome_completo") or name,
		"email": email,
		"telefone": data.get("telefone"),
		"data_de_nascimento": data.get("data_de_nascimento"),
	}


def _get_responsavel_payload(name: str) -> dict[str, Any]:
	data = frappe.db.get_value(
		"Responsavel",
		name,
		["nome_completo", "data_de_nascimento", "email", "celular", "telefone_secundario"],
		as_dict=True,
	)
	if not data:
		frappe.throw(_("Responsavel nao encontrado."))

	telefone = data.get("celular") or data.get("telefone_secundario")
	if not data.get("email") or not telefone:
		frappe.throw(_("Responsavel selecionado nao possui email ou telefone preenchido."))

	return {
		"nome": data.get("nome_completo") or name,
		"email": data.get("email"),
		"telefone": telefone,
		"data_de_nascimento": data.get("data_de_nascimento"),
	}
