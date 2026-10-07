"""Acessos concedidos por seção.

Um item do catálogo marcado como "Concedido por seção" é um papel do Gris que abre uma
página e só mostra o que é das seções concedidas — hoje, as contribuições mensais
(`gris.api.financeiro.pagamentos_contribuicao.associados_visiveis`). O papel continua sendo
a porta: sem ele a página não abre e nenhuma seção vale. Cada ``Acesso por Secao`` diz o
que aparece lá dentro.

A seção é o texto livre de ``Associado.secao`` (vem de importação de planilha). Quem pede
escolhe entre as seções que existem no cadastro dos beneficiários ativos, e toda
comparação ignora acentos e caixa (`gris.utils.chefes.normalizar_texto`).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now_datetime

from gris.api.acessos.constantes import SECAO_DOCTYPE
from gris.api.users.roles import get_role_profile_roles
from gris.utils.chefes import normalizar_texto

# Jovens cujas seções podem ser pedidas. Mesma categoria que paga a contribuição mensal.
CATEGORIAS_COM_SECAO = ("Beneficiário",)


def secoes_existentes() -> list[str]:
	"""Seções dos beneficiários ativos, sem repetir grafias do mesmo nome."""
	linhas = frappe.get_all(
		"Associado",
		filters={
			"status_no_grupo": "Ativo",
			"categoria": ["in", list(CATEGORIAS_COM_SECAO)],
			"secao": ["is", "set"],
		},
		pluck="secao",
		distinct=True,
		limit_page_length=0,
	)
	por_chave: dict[str, str] = {}
	for secao in linhas:
		texto = " ".join((secao or "").split())
		chave = normalizar_texto(texto)
		if chave and chave not in por_chave:
			por_chave[chave] = texto
	return sorted(por_chave.values(), key=normalizar_texto)


def secao_entre(secao: str | None, opcoes: list[str]) -> str | None:
	"""A grafia de ``secao`` que está em ``opcoes``, ou None quando não está."""
	alvo = normalizar_texto(secao)
	if not alvo:
		return None
	return next((opcao for opcao in opcoes if normalizar_texto(opcao) == alvo), None)


def concessoes_do_usuario(user: str) -> dict[str, list[frappe._dict]]:
	"""Seções concedidas a ``user``, agrupadas pelo papel — uma consulta para o catálogo todo."""
	por_papel: dict[str, list[frappe._dict]] = {}
	for linha in frappe.get_all(
		SECAO_DOCTYPE,
		filters={"usuario": user},
		fields=["name", "papel", "secao", "concedido_em"],
		order_by="secao asc",
		limit_page_length=0,
	):
		por_papel.setdefault(linha.papel, []).append(linha)
	return por_papel


def papel_vem_do_perfil(user: str, papel: str) -> bool:
	perfil = frappe.db.get_value("User", user, "role_profile_name")
	return bool(perfil) and papel in get_role_profile_roles(perfil)


def conceder_secao(user: str, papel: str, secao: str, origem: str, solicitacao: str | None = None) -> str:
	"""Dá a seção e, se faltar, o papel que abre a página."""
	from gris.api.acessos.provisionamento import conceder_papel, registrar_no_usuario

	secao = secao_entre(secao, secoes_existentes())
	if not secao:
		frappe.throw(_("Seção não encontrada no cadastro dos associados."))

	doc = frappe.get_doc(
		{
			"doctype": SECAO_DOCTYPE,
			"usuario": user,
			"papel": papel,
			"secao": secao,
			"solicitacao": solicitacao,
			"concedido_em": now_datetime(),
			"concedido_por": frappe.session.user,
		}
	).insert(ignore_permissions=True)

	conceder_papel(user, papel, origem)
	registrar_no_usuario(
		user,
		_("Seção {0} do papel {1} concedida pelo portal de acessos ({2}) por {3}.").format(
			secao, papel, origem, frappe.session.user
		),
	)
	return doc.name


def revogar_secao(nome: str, origem: str) -> dict:
	"""Tira uma seção. Sem nenhuma seção restante, sai também o papel — exceto o do perfil.

	O papel sozinho não mostraria nada a quem não chefia seção, e deixá-lo ficaria como
	acesso "fantasma" no catálogo. O que vem do Role Profile (o chefe de seção) fica: ele
	volta no próximo ``User.save()`` de qualquer jeito e mostra a seção que a pessoa chefia.
	"""
	from gris.api.acessos.provisionamento import registrar_no_usuario, revogar_papel

	linha = frappe.db.get_value(SECAO_DOCTYPE, nome, ["name", "usuario", "papel", "secao"], as_dict=True)
	if not linha:
		frappe.throw(_("Concessão de seção não encontrada."))

	frappe.delete_doc(SECAO_DOCTYPE, linha.name, ignore_permissions=True, force=True)
	registrar_no_usuario(
		linha.usuario,
		_("Seção {0} do papel {1} revogada pelo portal de acessos ({2}) por {3}.").format(
			linha.secao, linha.papel, origem, frappe.session.user
		),
	)

	papel_revogado = False
	restantes = frappe.db.exists(SECAO_DOCTYPE, {"usuario": linha.usuario, "papel": linha.papel})
	if not restantes and not papel_vem_do_perfil(linha.usuario, linha.papel):
		papel_revogado = revogar_papel(linha.usuario, linha.papel, origem)
	return {"usuario": linha.usuario, "secao": linha.secao, "papel_revogado": papel_revogado}


def apagar_secoes(user: str, papel: str) -> int:
	"""Some com as seções de quem perdeu o papel, para um papel novo não ressuscitá-las."""
	nomes = frappe.get_all(SECAO_DOCTYPE, filters={"usuario": user, "papel": papel}, pluck="name")
	for nome in nomes:
		frappe.delete_doc(SECAO_DOCTYPE, nome, ignore_permissions=True, force=True)
	return len(nomes)


def titulares_por_secao(papel: str) -> dict[str, list[dict]]:
	"""Seções concedidas por usuário, para a lista de titulares da gestão."""
	por_usuario: dict[str, list[dict]] = {}
	for linha in frappe.get_all(
		SECAO_DOCTYPE,
		filters={"papel": papel},
		fields=["name", "usuario", "secao", "concedido_em"],
		order_by="secao asc",
		limit_page_length=0,
	):
		por_usuario.setdefault(linha.usuario, []).append(
			{
				"concessao": linha.name,
				"secao": linha.secao,
				"concedido_em": str(linha.concedido_em) if linha.concedido_em else None,
			}
		)
	return por_usuario
