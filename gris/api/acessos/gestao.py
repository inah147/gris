"""API da gestão de acessos (/acessos/gestao): só Gestor de Acessos e System Manager."""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.query_builder.functions import Count

from gris.api.acessos import drives
from gris.api.acessos.catalogo import ICONE_PADRAO, itens_do_catalogo, vagas_por_ferramenta
from gris.api.acessos.constantes import (
	ABA_POR_TIPO,
	ACESSO_DOCTYPE,
	LICENCA_ATIVA,
	LICENCA_DOCTYPE,
	LICENCA_REVOGACAO_PENDENTE,
	LICENCA_REVOGADA,
	LICENCAS_QUE_OCUPAM_VAGA,
	LIMITE_MASSA_SINCRONA,
	MOTIVO_GESTOR,
	ROLE_GESTOR,
	SOLICITACAO_DOCTYPE,
	STATUS_ABERTOS,
	TIPO_DRIVE,
	TIPO_FERRAMENTA,
	TIPO_PAPEL,
)
from gris.api.acessos.permissoes import eh_system_manager, garantir_gestor, papel_aprovador_padrao
from gris.api.acessos.provisionamento import (
	garantir_vaga,
	registrar_no_usuario,
	revogar_papel,
	sincronizar_hooks_de_papel,
)
from gris.api.users.roles import add_role_to_users, remove_role_from_users

ITENS_POR_PAGINA = 50
STATUS_DE_SOLICITACAO = (
	"Em aprovação",
	"Aguardando concessão",
	"Concedida",
	"Recusada",
	"Cancelada",
)


def _lista(valor) -> list[str]:
	"""Aceita lista ou JSON de lista vindo do cliente."""
	if not valor:
		return []
	if isinstance(valor, str):
		try:
			valor = json.loads(valor)
		except ValueError:
			valor = [parte for parte in valor.split(",")]
	return [str(item).strip() for item in valor if str(item).strip()]


def _item(acesso: str, tipo: str | None = None) -> frappe._dict:
	item = frappe.db.get_value(
		ACESSO_DOCTYPE,
		acesso,
		["name", "titulo", "tipo", "papel", "drive_id", "limite_licencas"],
		as_dict=True,
	)
	if not item:
		frappe.throw(_("Acesso não encontrado."))
	if tipo and item.tipo != tipo:
		frappe.throw(_("Esta ação não vale para acessos do tipo {0}.").format(item.tipo))
	return item


# ───────────────────────────── leitura ─────────────────────────────


def usuarios_elegiveis() -> list[frappe._dict]:
	"""Quem pode receber acessos: usuário habilitado com cadastro de Associado ativo.

	É o "todos" das ações em massa — sem os responsáveis (que não têm Associado) e sem
	contas de serviço.
	"""
	associado = frappe.qb.DocType("Associado")
	user = frappe.qb.DocType("User")
	linhas = (
		frappe.qb.from_(associado)
		.join(user)
		.on(user.name == associado.id_escoteiros)
		.select(
			user.name.as_("usuario"),
			associado.nome_completo.as_("nome"),
			associado.categoria,
			user.role_profile_name.as_("perfil"),
		)
		.where(associado.status_no_grupo == "Ativo")
		.where(user.enabled == 1)
		.where(user.name.notin(["Administrator", "Guest"]))
		.orderby(associado.nome_completo)
	).run(as_dict=True)
	return linhas


def _perfis_com_papel(papel: str) -> set[str]:
	return set(
		frappe.get_all(
			"Has Role",
			filters={"parenttype": "Role Profile", "role": papel},
			pluck="parent",
			limit_page_length=0,
		)
	)


def _titulares_de_papel(papel: str) -> list[dict]:
	has_role = frappe.qb.DocType("Has Role")
	user = frappe.qb.DocType("User")
	linhas = (
		frappe.qb.from_(has_role)
		.join(user)
		.on(user.name == has_role.parent)
		.select(user.name.as_("usuario"), user.full_name.as_("nome"), user.role_profile_name.as_("perfil"))
		.where(has_role.parenttype == "User")
		.where(has_role.role == papel)
		.where(user.enabled == 1)
		.where(user.name.notin(["Administrator", "Guest"]))
		.orderby(user.full_name)
	).run(as_dict=True)
	perfis = _perfis_com_papel(papel)
	return [
		{
			"usuario": linha.usuario,
			"nome": linha.nome or linha.usuario,
			"email": linha.usuario,
			"origem": f"Perfil {linha.perfil}" if linha.perfil in perfis else "Concessão direta",
			"via_perfil": linha.perfil in perfis,
		}
		for linha in linhas
	]


def _contagem_por_papel(papeis: list[str]) -> dict[str, int]:
	if not papeis:
		return {}
	has_role = frappe.qb.DocType("Has Role")
	user = frappe.qb.DocType("User")
	return dict(
		(
			frappe.qb.from_(has_role)
			.join(user)
			.on(user.name == has_role.parent)
			.select(has_role.role, Count(has_role.parent).distinct())
			.where(has_role.parenttype == "User")
			.where(has_role.role.isin(papeis))
			.where(user.enabled == 1)
			.where(user.name.notin(["Administrator", "Guest"]))
			.groupby(has_role.role)
		).run()
	)


def _etapas_por_acesso(nomes: list[str]) -> dict[str, list[dict]]:
	etapas: dict[str, list[dict]] = {}
	if not nomes:
		return etapas
	for etapa in frappe.get_all(
		"Etapa de Aprovacao de Acesso",
		filters={"parenttype": ACESSO_DOCTYPE, "parent": ["in", nomes]},
		fields=["parent", "papel_aprovador", "descricao"],
		order_by="idx asc",
	):
		etapas.setdefault(etapa.parent, []).append(
			{"papel_aprovador": etapa.papel_aprovador, "descricao": etapa.descricao}
		)
	return etapas


@frappe.whitelist(methods=["GET"])
def resumo() -> dict:
	"""Um card por acesso: titulares, vagas, pedidos em andamento e o que é editável."""
	garantir_gestor()
	itens = itens_do_catalogo(incluir_inativos=True)
	etapas = _etapas_por_acesso([item.name for item in itens])

	papeis = [item.papel for item in itens if item.tipo == TIPO_PAPEL and item.papel]
	por_papel = _contagem_por_papel(papeis)
	vagas = vagas_por_ferramenta([item.name for item in itens if item.tipo == TIPO_FERRAMENTA])
	abertos = {
		linha.acesso: linha.total
		for linha in frappe.get_all(
			SOLICITACAO_DOCTYPE,
			filters={"status": ["in", STATUS_ABERTOS]},
			fields=["acesso", "count(name) as total"],
			group_by="acesso",
		)
	}

	cards = []
	for item in itens:
		card = {
			"name": item.name,
			"titulo": item.titulo,
			"tipo": item.tipo,
			"aba": ABA_POR_TIPO.get(item.tipo),
			"icone": item.icone or ICONE_PADRAO.get(item.tipo),
			"papel": item.papel,
			"nome_drive": item.nome_drive,
			"ativo": bool(item.ativo),
			"solicitavel": bool(item.solicitavel),
			"descricao": item.descricao,
			"o_que_muda": item.o_que_muda,
			"instrucoes_concessao": item.instrucoes_concessao,
			"link_externo": item.link_externo,
			"limite_licencas": int(item.limite_licencas or 0),
			"permissao_drive": item.permissao_drive,
			"ordem": int(item.ordem or 0),
			"etapas": etapas.get(item.name, []),
			"abertos": int(abertos.get(item.name) or 0),
			"titulares": 0,
			"vagas": None,
			"global": False,
		}
		if item.tipo == TIPO_PAPEL:
			card["titulares"] = int(por_papel.get(item.papel) or 0)
		elif item.tipo == TIPO_DRIVE:
			titulares = drives.titulares_do_drive(item.drive_id)
			card["titulares"] = len(titulares["titulares"])
			card["global"] = titulares["global"]
		elif item.tipo == TIPO_FERRAMENTA:
			usadas = int(vagas["ocupadas"].get(item.name) or 0)
			aguardando = int(vagas["aguardando"].get(item.name) or 0)
			limite = int(item.limite_licencas or 0)
			card["titulares"] = usadas
			card["vagas"] = {
				"limite": limite,
				"usadas": usadas,
				"aguardando": aguardando,
				"disponiveis": max(limite - usadas - aguardando, 0) if limite else None,
			}
		cards.append(card)
	return {"cards": cards, "papel_padrao": papel_aprovador_padrao()}


@frappe.whitelist(methods=["GET"])
def listar_solicitacoes(status: str | None = None, aba: str | None = None, pagina: int = 1) -> dict:
	garantir_gestor()
	from gris.api.acessos.solicitacoes import resumo as resumo_da_solicitacao

	filtros: dict = {}
	if status:
		if status == "abertas":
			filtros["status"] = ["in", STATUS_ABERTOS]
		elif status in STATUS_DE_SOLICITACAO:
			filtros["status"] = status
	if aba:
		tipos = [tipo for tipo, a in ABA_POR_TIPO.items() if a == aba]
		if tipos:
			filtros["tipo"] = ["in", tipos]

	pagina = max(int(pagina or 1), 1)
	total = frappe.db.count(SOLICITACAO_DOCTYPE, filtros)
	nomes = frappe.get_all(
		SOLICITACAO_DOCTYPE,
		filters=filtros,
		pluck="name",
		order_by="creation desc",
		limit_start=(pagina - 1) * ITENS_POR_PAGINA,
		limit_page_length=ITENS_POR_PAGINA,
	)
	return {
		"total": total,
		"pagina": pagina,
		"por_pagina": ITENS_POR_PAGINA,
		"solicitacoes": [resumo_da_solicitacao(frappe.get_doc(SOLICITACAO_DOCTYPE, nome)) for nome in nomes],
	}


@frappe.whitelist(methods=["GET"])
def listar_titulares(acesso: str) -> dict:
	garantir_gestor()
	item = _item(acesso)

	if item.tipo == TIPO_PAPEL:
		return {"tipo": item.tipo, "titulares": _titulares_de_papel(item.papel)}

	if item.tipo == TIPO_DRIVE:
		resultado = drives.titulares_do_drive(item.drive_id)
		return {"tipo": item.tipo, "global": resultado["global"], "titulares": resultado["titulares"]}

	licencas = frappe.get_all(
		LICENCA_DOCTYPE,
		filters={"acesso": item.name, "status": ["in", LICENCAS_QUE_OCUPAM_VAGA]},
		fields=[
			"name",
			"associado",
			"nome",
			"email",
			"status",
			"concedida_em",
			"motivo_revogacao",
			"revogacao_pendente_desde",
		],
		order_by="status asc, nome asc",
	)
	return {
		"tipo": item.tipo,
		"titulares": [
			{
				"licenca": licenca.name,
				"associado": licenca.associado,
				"nome": licenca.nome,
				"email": licenca.email,
				"status": licenca.status,
				"origem": licenca.motivo_revogacao if licenca.status == LICENCA_REVOGACAO_PENDENTE else None,
				"concedida_em": str(licenca.concedida_em) if licenca.concedida_em else None,
				"revogacao_pendente_desde": str(licenca.revogacao_pendente_desde)
				if licenca.revogacao_pendente_desde
				else None,
			}
			for licenca in licencas
		],
	}


# ───────────────────────────── catálogo ─────────────────────────────

CAMPOS_EDITAVEIS = {
	"descricao": str,
	"o_que_muda": str,
	"instrucoes_concessao": str,
	"link_externo": str,
	"permissao_drive": str,
	"solicitavel": int,
	"ativo": int,
	"limite_licencas": int,
	"ordem": int,
}


def opcoes_de_papel_aprovador() -> list[dict]:
	"""Papéis que podem aprovar uma etapa: os do catálogo, o gestor e o System Manager."""
	papeis = set(
		frappe.get_all(ACESSO_DOCTYPE, filters={"tipo": TIPO_PAPEL}, pluck="papel", limit_page_length=0)
	)
	papeis |= {ROLE_GESTOR, "System Manager"}
	existentes = frappe.get_all(
		"Role", filters={"name": ["in", sorted(p for p in papeis if p)], "disabled": 0}, pluck="name"
	)
	return [{"value": papel, "label": papel} for papel in sorted(existentes, key=str.casefold)]


@frappe.whitelist(methods=["POST"])
def salvar_acesso(acesso: str, dados: str | dict) -> dict:
	"""Edita descrição, limite de licenças, fluxo de aprovação e visibilidade de um item."""
	garantir_gestor()
	if isinstance(dados, str):
		dados = json.loads(dados or "{}")
	if not isinstance(dados, dict):
		frappe.throw(_("Dados inválidos."))

	doc = frappe.get_doc(ACESSO_DOCTYPE, acesso)
	if doc.tipo == TIPO_PAPEL and doc.papel == ROLE_GESTOR and not eh_system_manager():
		frappe.throw(_("Só um System Manager altera o acesso de {0}.").format(ROLE_GESTOR))

	for campo, tipo in CAMPOS_EDITAVEIS.items():
		if campo not in dados:
			continue
		valor = dados[campo]
		if tipo is int:
			valor = frappe.utils.cint(valor)
		else:
			valor = (str(valor) if valor is not None else "").strip() or None
		doc.set(campo, valor)

	if "etapas" in dados:
		permitidos = {opcao["value"] for opcao in opcoes_de_papel_aprovador()}
		doc.set("etapas_aprovacao", [])
		for etapa in dados.get("etapas") or []:
			papel = (etapa.get("papel_aprovador") or "").strip()
			if papel not in permitidos:
				frappe.throw(_("O papel {0} não pode aprovar etapas.").format(papel or "vazio"))
			doc.append(
				"etapas_aprovacao",
				{"papel_aprovador": papel, "descricao": (etapa.get("descricao") or "").strip() or None},
			)

	doc.save(ignore_permissions=True)
	return {"ok": True}


# ───────────────────────────── papéis em massa ─────────────────────────────


def _papel_do_acesso(acesso: str) -> str:
	item = _item(acesso, TIPO_PAPEL)
	if item.papel == ROLE_GESTOR and not eh_system_manager():
		frappe.throw(_("Só um System Manager concede ou revoga o papel {0}.").format(ROLE_GESTOR))
	return item.papel


def _alvos(usuarios, todos) -> list[frappe._dict]:
	elegiveis = usuarios_elegiveis()
	if frappe.utils.cint(todos):
		return elegiveis
	escolhidos = set(_lista(usuarios))
	if not escolhidos:
		frappe.throw(_("Selecione ao menos uma pessoa."))
	return [linha for linha in elegiveis if linha.usuario in escolhidos]


def aplicar_papel_em_massa(acao: str, papel: str, usuarios: list[str], origem: str) -> dict:
	"""Concede ou revoga ``papel`` para ``usuarios`` (já filtrados). Usado também na fila."""
	if acao == "conceder":
		alterados = add_role_to_users(papel, usuarios)
		verbo = "concedido"
	else:
		alterados = remove_role_from_users(papel, usuarios)
		verbo = "revogado"

	if alterados:
		sincronizar_hooks_de_papel([papel])
		for usuario in alterados:
			registrar_no_usuario(
				usuario,
				_("Papel {0} {1} em massa pelo portal de acessos ({2}) por {3}.").format(
					papel, verbo, origem, frappe.session.user
				),
			)
	return {"alterados": len(alterados), "usuarios": alterados}


def _papel_em_massa(acao: str, acesso: str, usuarios, todos) -> dict:
	garantir_gestor()
	papel = _papel_do_acesso(acesso)
	alvos = _alvos(usuarios, todos)

	ignorados = []
	if acao == "revogar":
		# Papel que vem do Role Profile volta no próximo User.save(): revogar aqui seria
		# uma promessa falsa. Fica de fora e a tela diz por quê.
		perfis = _perfis_com_papel(papel)
		ignorados = [linha for linha in alvos if linha.perfil in perfis]
		alvos = [linha for linha in alvos if linha.perfil not in perfis]

	usuarios_alvo = [linha.usuario for linha in alvos]
	resultado = {
		"total": len(usuarios_alvo),
		"ignorados_via_perfil": [
			{"usuario": i.usuario, "nome": i.nome, "perfil": i.perfil} for i in ignorados
		],
		"enfileirado": False,
		"alterados": 0,
	}
	if not usuarios_alvo:
		return resultado

	origem = _("todos os associados") if frappe.utils.cint(todos) else _("seleção")
	if len(usuarios_alvo) > LIMITE_MASSA_SINCRONA:
		frappe.enqueue(
			"gris.api.acessos.gestao.aplicar_papel_em_massa",
			queue="long",
			timeout=1800,
			enqueue_after_commit=True,
			acao=acao,
			papel=papel,
			usuarios=usuarios_alvo,
			origem=origem,
		)
		resultado["enfileirado"] = True
		return resultado

	resultado["alterados"] = aplicar_papel_em_massa(acao, papel, usuarios_alvo, origem)["alterados"]
	return resultado


@frappe.whitelist(methods=["GET"])
def listar_usuarios_elegiveis(acesso: str | None = None) -> dict:
	"""Pessoas para a ação em massa, com a marca de quem já tem o papel."""
	garantir_gestor()
	tem = set()
	via_perfil = set()
	if acesso:
		papel = _item(acesso, TIPO_PAPEL).papel
		tem = set(
			frappe.get_all(
				"Has Role",
				filters={"parenttype": "User", "role": papel},
				pluck="parent",
				limit_page_length=0,
			)
		)
		via_perfil = _perfis_com_papel(papel)
	return {
		"usuarios": [
			{
				"usuario": linha.usuario,
				"nome": linha.nome,
				"categoria": linha.categoria,
				"tem": linha.usuario in tem,
				"via_perfil": linha.usuario in tem and linha.perfil in via_perfil,
			}
			for linha in usuarios_elegiveis()
		]
	}


@frappe.whitelist(methods=["POST"])
def conceder_papel_em_massa(acesso: str, usuarios: str | None = None, todos: int = 0) -> dict:
	return _papel_em_massa("conceder", acesso, usuarios, todos)


@frappe.whitelist(methods=["POST"])
def revogar_papel_em_massa(acesso: str, usuarios: str | None = None, todos: int = 0) -> dict:
	return _papel_em_massa("revogar", acesso, usuarios, todos)


@frappe.whitelist(methods=["POST"])
def revogar_papel_de_usuario(acesso: str, usuario: str) -> dict:
	garantir_gestor()
	papel = _papel_do_acesso(acesso)
	perfil = frappe.db.get_value("User", usuario, "role_profile_name")
	if perfil and perfil in _perfis_com_papel(papel):
		frappe.throw(
			_("{0} recebe este papel pelo perfil {1}: mude o perfil no cadastro do usuário.").format(
				usuario, perfil
			)
		)
	if not revogar_papel(usuario, papel, _("gestão de acessos")):
		frappe.throw(_("Esta pessoa já não tem o papel."))
	return {"ok": True}


# ───────────────────────────── drives ─────────────────────────────


@frappe.whitelist(methods=["POST"])
def revogar_concessao_drive(concessao: str) -> dict:
	garantir_gestor()
	alvo = drives.encerrar_concessao_manual(
		concessao, _("Revogada pela gestão de acessos ({0}).").format(frappe.session.user)
	)
	if not alvo:
		frappe.throw(_("Concessão não encontrada."))
	drives.enfileirar_revogacao(alvo["email"], alvo["drive_id"])
	return {"ok": True}


# ───────────────────────────── licenças de ferramentas ─────────────────────────────


@frappe.whitelist(methods=["GET"])
def opcoes_de_associados() -> list[dict]:
	"""Associados ativos com id@escoteiros, para registrar licenças que já existem."""
	garantir_gestor()
	return [
		{"value": linha.name, "label": f"{linha.nome_completo} ({linha.id_escoteiros})"}
		for linha in frappe.get_all(
			"Associado",
			filters={"status_no_grupo": "Ativo", "id_escoteiros": ["is", "set"]},
			fields=["name", "nome_completo", "id_escoteiros"],
			order_by="nome_completo asc",
		)
	]


@frappe.whitelist(methods=["POST"])
def registrar_licenca(acesso: str, associado: str, observacao: str | None = None) -> dict:
	"""Carga inicial: quem já usa a ferramenta passa a ocupar uma vaga no controle."""
	garantir_gestor()
	_item(acesso, TIPO_FERRAMENTA)
	garantir_vaga(acesso)
	licenca = frappe.get_doc(
		{
			"doctype": LICENCA_DOCTYPE,
			"acesso": acesso,
			"associado": associado,
			"status": LICENCA_ATIVA,
			"observacao": (observacao or "").strip() or None,
		}
	).insert(ignore_permissions=True)
	return {"ok": True, "licenca": licenca.name}


def _licenca(nome: str):
	if not frappe.db.exists(LICENCA_DOCTYPE, nome):
		frappe.throw(_("Licença não encontrada."))
	return frappe.get_doc(LICENCA_DOCTYPE, nome, for_update=True)


@frappe.whitelist(methods=["POST"])
def marcar_revogacao(licenca: str, observacao: str | None = None) -> dict:
	garantir_gestor()
	doc = _licenca(licenca)
	if doc.status != LICENCA_ATIVA:
		frappe.throw(_("Só licenças ativas podem ser marcadas para revogação."))
	doc.status = LICENCA_REVOGACAO_PENDENTE
	doc.motivo_revogacao = MOTIVO_GESTOR
	if (observacao or "").strip():
		doc.observacao = observacao.strip()
	doc.save(ignore_permissions=True)
	return {"ok": True}


@frappe.whitelist(methods=["POST"])
def desfazer_revogacao(licenca: str) -> dict:
	garantir_gestor()
	doc = _licenca(licenca)
	if doc.status != LICENCA_REVOGACAO_PENDENTE:
		frappe.throw(_("Esta licença não está aguardando revogação."))
	doc.status = LICENCA_ATIVA
	doc.save(ignore_permissions=True)
	return {"ok": True}


@frappe.whitelist(methods=["POST"])
def confirmar_revogacao(licenca: str) -> dict:
	"""A conta foi removida da ferramenta: a vaga volta a ficar livre."""
	garantir_gestor()
	doc = _licenca(licenca)
	if doc.status == LICENCA_REVOGADA:
		frappe.throw(_("Esta licença já foi revogada."))
	if not doc.motivo_revogacao:
		doc.motivo_revogacao = MOTIVO_GESTOR
	doc.status = LICENCA_REVOGADA
	doc.save(ignore_permissions=True)
	return {"ok": True}
