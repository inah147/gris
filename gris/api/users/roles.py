"""Utilitários para concessão e troca de papéis (roles) de usuários.

Motivação: no Frappe, gravar `User.role_profile_name` faz o framework
**substituir toda a lista de papéis** do usuário pelos papéis do perfil —
`populate_role_profile_roles()` limpa `roles` antes de repopular. Consequência:
qualquer papel concedido manualmente (ex.: "Acesso ao Desk", "Responsavel",
"Portaria") é silenciosamente removido em qualquer `User.save()` disparado por
uma rotina automática, como a importação de associados.

As funções abaixo permitem:

* conceder papéis de forma **aditiva**, sem passar por `User.save()`
  (`add_user_roles`);
* trocar o Role Profile **preservando** os papéis que não vieram do perfil
  anterior, isto é, as concessões manuais (`apply_role_profile`).
"""

import json

import frappe
from frappe import _
from frappe.query_builder.functions import Max
from frappe.utils import add_days, cint, now, now_datetime

# Perfil sem nenhum papel associado. Usado como "sem mapeamento" na criação de
# usuários; nunca deve ser aplicado automaticamente sobre um usuário existente,
# pois zeraria todos os acessos.
PERFIL_SEM_ACESSO = "Guest"


def get_role_profile_roles(role_profile: str | None) -> set[str]:
	"""Retorna o conjunto de papéis de um Role Profile (vazio se não existir)."""
	if not role_profile or not frappe.db.exists("Role Profile", role_profile):
		return set()

	return set(
		frappe.get_all(
			"Has Role",
			filters={"parenttype": "Role Profile", "parent": role_profile},
			pluck="role",
			limit_page_length=0,
		)
	)


def get_user_roles(user: str) -> set[str]:
	"""Retorna o conjunto de papéis atualmente atribuídos ao usuário."""
	if not user:
		return set()

	return set(
		frappe.get_all(
			"Has Role",
			filters={"parenttype": "User", "parent": user},
			pluck="role",
			limit_page_length=0,
		)
	)


def add_user_roles(user: str, roles) -> list[str]:
	"""Concede papéis ao usuário sem disparar `User.save()`.

	As linhas de `Has Role` são gravadas diretamente para que o framework não
	recalcule a lista de papéis a partir do `role_profile_name` — o que
	removeria papéis concedidos manualmente.

	Retorna a lista de papéis efetivamente adicionados.
	"""
	if not user or not roles:
		return []

	# Remove duplicados e vazios preservando a ordem informada.
	roles = [role for role in dict.fromkeys(roles) if role]
	if not roles:
		return []

	existentes = get_user_roles(user)
	papeis_validos = set(
		frappe.get_all("Role", filters={"name": ("in", roles)}, pluck="name", limit_page_length=0)
	)

	ultima_linha = frappe.get_all(
		"Has Role",
		filters={"parenttype": "User", "parent": user},
		fields=["idx"],
		order_by="idx desc",
		limit=1,
	)
	proximo_idx = (ultima_linha[0].idx if ultima_linha else 0) or 0

	adicionados = []
	for role in roles:
		if role in existentes or role not in papeis_validos:
			continue

		proximo_idx += 1
		frappe.get_doc(
			{
				"doctype": "Has Role",
				"parent": user,
				"parenttype": "User",
				"parentfield": "roles",
				"idx": proximo_idx,
				"role": role,
			}
		).insert(ignore_permissions=True)
		adicionados.append(role)

	if adicionados:
		frappe.clear_cache(user=user)

	return adicionados


def remove_user_roles(user: str, roles) -> list[str]:
	"""Retira papéis do usuário sem disparar `User.save()`.

	Contraparte de `add_user_roles`. Atenção: um papel que vem do Role Profile do
	usuário volta no próximo `User.save()` — quem chama deve checar isso antes
	(`get_role_profile_roles`).

	Retorna a lista de papéis efetivamente removidos.
	"""
	if not user or not roles:
		return []

	removidos = sorted(get_user_roles(user) & {role for role in roles if role})
	if not removidos:
		return []

	frappe.db.delete("Has Role", {"parenttype": "User", "parent": user, "role": ["in", removidos]})
	frappe.clear_cache(user=user)
	return removidos


def add_role_to_users(role: str, users) -> list[str]:
	"""Concede um papel a vários usuários de uma vez, sem `User.save()`.

	Mesma gravação direta de `add_user_roles`, em lote: uma consulta para saber quem
	já tem o papel, uma para o próximo `idx` de cada usuário e um único insert.

	Retorna os usuários que receberam o papel.
	"""
	usuarios = [usuario for usuario in dict.fromkeys(users or []) if usuario]
	if not role or not usuarios or not frappe.db.exists("Role", role):
		return []

	ja_tem = set(
		frappe.get_all(
			"Has Role",
			filters={"parenttype": "User", "parent": ["in", usuarios], "role": role},
			pluck="parent",
			limit_page_length=0,
		)
	)
	existentes = set(
		frappe.get_all("User", filters={"name": ["in", usuarios]}, pluck="name", limit_page_length=0)
	)
	alvos = [usuario for usuario in usuarios if usuario in existentes and usuario not in ja_tem]
	if not alvos:
		return []

	has_role = frappe.qb.DocType("Has Role")
	ultimos = (
		frappe.qb.from_(has_role)
		.select(has_role.parent, Max(has_role.idx))
		.where(has_role.parenttype == "User")
		.where(has_role.parent.isin(alvos))
		.groupby(has_role.parent)
	).run()
	ultimo_idx = {parent: idx or 0 for parent, idx in ultimos}

	agora = now()
	quem = frappe.session.user
	campos = [
		"name",
		"creation",
		"modified",
		"owner",
		"modified_by",
		"parent",
		"parenttype",
		"parentfield",
		"idx",
		"role",
	]
	valores = [
		(
			frappe.generate_hash(length=10),
			agora,
			agora,
			quem,
			quem,
			usuario,
			"User",
			"roles",
			ultimo_idx.get(usuario, 0) + 1,
			role,
		)
		for usuario in alvos
	]
	frappe.db.bulk_insert("Has Role", campos, valores)

	for usuario in alvos:
		frappe.clear_cache(user=usuario)
	return alvos


def remove_role_from_users(role: str, users) -> list[str]:
	"""Retira um papel de vários usuários de uma vez, sem `User.save()`.

	Retorna os usuários que perderam o papel.
	"""
	usuarios = [usuario for usuario in dict.fromkeys(users or []) if usuario]
	if not role or not usuarios:
		return []

	alvos = sorted(
		set(
			frappe.get_all(
				"Has Role",
				filters={"parenttype": "User", "parent": ["in", usuarios], "role": role},
				pluck="parent",
				limit_page_length=0,
			)
		)
	)
	if not alvos:
		return []

	frappe.db.delete("Has Role", {"parenttype": "User", "parent": ["in", alvos], "role": role})
	for usuario in alvos:
		frappe.clear_cache(user=usuario)
	return alvos


def save_user_preserving_roles(user_doc, ignore_permissions: bool = True) -> list[str]:
	"""Grava o usuário reaplicando os papéis descartados pelo recálculo do perfil.

	Qualquer `User.save()` faz o Frappe repopular `roles` a partir de
	`role_profile_name`, descartando papéis concedidos manualmente — mesmo
	quando a gravação nada tem a ver com papéis (ex.: ativar/desativar o
	usuário). Esta função restaura esses papéis logo após a gravação.

	Retorna a lista de papéis que precisaram ser restaurados.
	"""
	papeis_antes = set() if user_doc.get("__islocal") else get_user_roles(user_doc.name)

	user_doc.save(ignore_permissions=ignore_permissions)

	return add_user_roles(user_doc.name, sorted(papeis_antes - get_user_roles(user_doc.name)))


def apply_role_profile(user_doc, novo_perfil: str) -> dict:
	"""Troca o Role Profile do usuário preservando os papéis concedidos manualmente.

	Papéis que o usuário possui e que **não** fazem parte do perfil anterior são
	tratados como concessão manual e reaplicados após a troca, já que o Frappe
	zera a lista de papéis ao gravar `role_profile_name`.

	Retorna um resumo com o perfil anterior, o novo e os papéis preservados.
	"""
	perfil_anterior = user_doc.role_profile_name
	papeis_manuais = get_user_roles(user_doc.name) - get_role_profile_roles(perfil_anterior)

	user_doc.role_profile_name = novo_perfil
	user_doc.save(ignore_permissions=True)

	preservados = add_user_roles(user_doc.name, sorted(papeis_manuais))

	return {
		"perfil_anterior": perfil_anterior,
		"perfil_novo": novo_perfil,
		"papeis_preservados": preservados,
	}


@frappe.whitelist()
def diagnosticar_papeis_removidos(email: str | None = None, dias: int = 90, aplicar: int = 0) -> dict:
	"""Lista (e opcionalmente restaura) papéis removidos automaticamente de usuários.

	Usa o histórico de versões (`Version`) do DocType User para identificar
	papéis que foram retirados — tipicamente pelo recálculo do Role Profile em
	rotinas automáticas, como a importação de associados — e que o usuário ainda
	não possui.

	Por padrão roda em modo simulação (`aplicar=0`), para que a restauração seja
	conferida antes de ser aplicada.
	"""
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw(_("Sem permissão para diagnosticar papéis de usuários."), frappe.PermissionError)

	aplicar = cint(aplicar)
	dias = cint(dias) or 90

	filtros = {
		"ref_doctype": "User",
		"creation": (">=", add_days(now_datetime(), -dias)),
	}
	if email:
		filtros["docname"] = email

	versoes = frappe.get_all(
		"Version",
		filters=filtros,
		fields=["docname", "data"],
		order_by="creation asc",
		limit_page_length=0,
	)

	removidos: dict[str, set[str]] = {}
	for versao in versoes:
		try:
			dados = json.loads(versao.data or "{}")
		except ValueError:
			continue

		for parentfield, linha in dados.get("removed") or []:
			if parentfield != "roles":
				continue
			papel = (linha or {}).get("role")
			if papel:
				removidos.setdefault(versao.docname, set()).add(papel)

	resultado = {"usuarios": [], "aplicado": bool(aplicar)}
	for usuario, papeis in sorted(removidos.items()):
		pendentes = sorted(papeis - get_user_roles(usuario))
		if not pendentes:
			continue

		restaurados = add_user_roles(usuario, pendentes) if aplicar else []
		resultado["usuarios"].append(
			{"usuario": usuario, "papeis_removidos": pendentes, "papeis_restaurados": restaurados}
		)

	return resultado
