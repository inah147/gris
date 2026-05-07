"""Helpers de inserção segura — protegem contra recriar DocTypes carregados via fixtures."""

import frappe

# DocTypes carregados via fixtures (ver hooks.py:269-326).
# Seed NUNCA deve recriar esses — apenas usá-los como Link target.
FIXTURE_DOCTYPES = {
	"Role",
	"Role Profile",
	"Carteira",
	"Instituicao Financeira",
	"Centro de Custo",
	"Categoria de Transacao",
	"Unidade Organizacional",
	"Email Template",
	"Mapeamento de perguntas e respostas da entrevista",
	"ODS Projeto",
}


class FixtureCollisionError(Exception):
	"""Erro lançado se o seed tentar criar um DocType que é fixture."""


def _check_not_fixture(doctype: str):
	if doctype in FIXTURE_DOCTYPES:
		raise FixtureCollisionError(
			f"❌ '{doctype}' é carregado via fixtures (apps/gris/gris/fixtures/). "
			f"O seed não deve recriá-lo. Rode `bench --site <site> migrate` antes."
		)


def safe_insert(doc_dict: dict, *, ignore_permissions: bool = True) -> "frappe.model.document.Document":
	"""
	Insere um documento, pulando se duplicado.

	Bloqueia DocTypes de fixture explicitamente.
	Retorna o doc inserido OU o existente (carregado de novo).
	"""
	doctype = doc_dict.get("doctype")
	if not doctype:
		raise ValueError("doc_dict precisa ter 'doctype'")
	_check_not_fixture(doctype)

	doc = frappe.get_doc(doc_dict)
	try:
		doc.insert(ignore_permissions=ignore_permissions, ignore_if_duplicate=True)
	except frappe.DuplicateEntryError:
		# DuplicateEntryError pode escapar do ignore_if_duplicate em alguns contextos
		return frappe.get_doc(doctype, doc.name)
	return doc


def safe_get_or_create(
	doctype: str,
	filters: dict,
	defaults: dict,
	*,
	ignore_permissions: bool = True,
) -> "frappe.model.document.Document":
	"""
	Retorna o doc se existe (matched por `filters`), senão cria com `filters + defaults`.

	Útil quando o nome é autogerado (hash, format:..., random) — nesses casos
	procuramos por uma chave de negócio antes de inserir.
	"""
	_check_not_fixture(doctype)
	existing = frappe.db.exists(doctype, filters)
	if existing:
		return frappe.get_doc(doctype, existing)

	payload = {"doctype": doctype, **filters, **defaults}
	doc = frappe.get_doc(payload)
	doc.insert(ignore_permissions=ignore_permissions)
	return doc


def set_single(doctype: str, values: dict, *, ignore_permissions: bool = True):
	"""
	Atualiza um Single doctype com os campos passados.

	Usa get_doc + save para garantir que campos Password sejam encriptados.
	Pula valores None / "".
	"""
	cleaned = {k: v for k, v in values.items() if v not in (None, "")}
	if not cleaned:
		return None
	doc = frappe.get_single(doctype)
	for k, v in cleaned.items():
		doc.set(k, v)
	doc.save(ignore_permissions=ignore_permissions)
	return doc


def has_records(doctype: str) -> bool:
	"""True se já há ao menos 1 registro do DocType (usado para idempotência)."""
	return frappe.db.count(doctype) > 0


def first_name(doctype: str, filters: dict | None = None) -> str | None:
	"""Retorna o `name` do primeiro doc encontrado, ou None."""
	rows = frappe.get_all(doctype, filters=filters or {}, limit=1, pluck="name")
	return rows[0] if rows else None


def all_names(doctype: str, filters: dict | None = None, limit: int = 0) -> list[str]:
	"""Retorna lista de `name` de todos os docs (ou limitado)."""
	kwargs = {"filters": filters or {}, "pluck": "name"}
	if limit:
		kwargs["limit"] = limit
	return frappe.get_all(doctype, **kwargs)
