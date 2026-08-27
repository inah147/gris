import hashlib
import re

import frappe
from frappe import _
from frappe.utils import format_datetime, get_fullname, getdate, strip_html, today


@frappe.whitelist()
def update_novo_associado(name, responsavel_recepcao=None, status=None, ramo=None):
	"""Ajusta os campos do funil. O motivo da desistência é gravado por
	``processar_desistencia``, que é quem registra a desativação do registro."""
	doc = frappe.get_doc("Novo Associado", name)
	if responsavel_recepcao:
		doc.responsavel_recepcao = responsavel_recepcao
	if status:
		doc.status = status
	if ramo:
		doc.ramo = ramo
	doc.save()
	return doc.as_dict()


def nomes_desistentes(nomes: list[str] | None = None) -> set[str]:
	"""Nomes de Novo Associado desativados por desistência.

	Sem ``nomes``, devolve todos os desistentes; com ``nomes``, apenas os desse
	conjunto — usado para filtrar registros ligados ao funil (visitas, fila de
	espera, vínculos) que não têm o flag próprio.
	"""
	filtros: dict = {"desistiu": 1}
	if nomes is not None:
		if not nomes:
			return set()
		filtros["name"] = ["in", list(nomes)]

	return set(frappe.get_all("Novo Associado", filters=filtros, pluck="name"))


def filtrar_ativos(nomes: list[str]) -> list[str]:
	"""Remove da lista os Novo Associado que desistiram, preservando a ordem."""
	if not nomes:
		return []

	desistentes = nomes_desistentes(nomes)
	return [nome for nome in nomes if nome not in desistentes]


def _desligar_associado(novo_associado) -> None:
	"""Marca como inativo o Associado já efetivado, sem apagar nem anonimizar nada.

	O ``validate`` do Associado deriva ``status_no_grupo`` do histórico no grupo:
	fechar o último período com a data de desligamento é o que o torna inativo.
	"""
	if not (novo_associado.registro_provisorio_efetivado or novo_associado.registro_definitivo_efetivado):
		return

	if not novo_associado.cpf:
		return

	cpf_limpo = re.sub(r"\D", "", novo_associado.cpf)
	associado_name = hashlib.md5(cpf_limpo.encode("utf-8")).hexdigest()
	if not frappe.db.exists("Associado", associado_name):
		return

	assoc_doc = frappe.get_doc("Associado", associado_name)
	periodos = [linha for linha in (assoc_doc.historico_no_grupo or []) if linha.data_de_ingresso]

	if periodos:
		ultimo = sorted(periodos, key=lambda linha: getdate(linha.data_de_ingresso))[-1]
	else:
		# Sem período registrado o Associado continuaria "Ativo" no `validate`;
		# usa a criação do cadastro como ingresso para fechar o histórico.
		ultimo = assoc_doc.append("historico_no_grupo", {"data_de_ingresso": getdate(assoc_doc.creation)})

	if not ultimo.data_de_desligamento:
		ultimo.data_de_desligamento = today()

	assoc_doc.save(ignore_permissions=True)


def _responsavel_tem_beneficiario_ativo(responsavel_id: str, ignorar: str) -> bool:
	"""Diz se o responsável ainda acompanha alguém — no funil ou já associado."""
	vinculos = frappe.get_all(
		"Responsavel Vinculo",
		filters={"responsavel": responsavel_id},
		fields=["beneficiario_novo_associado", "beneficiario_associado"],
	)

	for vinculo in vinculos:
		associado = vinculo.get("beneficiario_associado")
		if associado and frappe.db.get_value("Associado", associado, "status_no_grupo") == "Ativo":
			return True

		novo_associado = vinculo.get("beneficiario_novo_associado")
		if (
			novo_associado
			and novo_associado != ignorar
			and not frappe.db.get_value("Novo Associado", novo_associado, "desistiu")
		):
			return True

	return False


def _desativar_acesso_responsaveis(novo_associado_name: str) -> None:
	"""Desativa o login dos responsáveis que ficaram sem beneficiário ativo.

	O cadastro (Responsavel, vínculos e User) é preservado: só o acesso ao portal
	é desligado, e apenas para quem não acompanha mais ninguém.
	"""
	vinculos = frappe.get_all(
		"Responsavel Vinculo",
		filters={"beneficiario_novo_associado": novo_associado_name},
		pluck="responsavel",
	)

	for responsavel_id in {vinculo for vinculo in vinculos if vinculo}:
		if _responsavel_tem_beneficiario_ativo(responsavel_id, ignorar=novo_associado_name):
			continue

		email = frappe.db.get_value("Responsavel", responsavel_id, "email")
		if email and frappe.db.exists("User", email):
			frappe.db.set_value("User", email, "enabled", 0)


@frappe.whitelist()
def processar_desistencia(novo_associado_name, motivo=None):
	"""Desativa o registro do fluxo de novo associado — sem apagar dados.

	Nada é excluído nem anonimizado: o Novo Associado é marcado com ``desistiu``
	e some das telas do fluxo (funil, fila de espera, agenda de visitas, portal
	do responsável), enquanto visitas, vínculos e cadastros continuam no banco
	para consulta e histórico. Quando o registro já havia sido efetivado, o
	Associado correspondente é desligado (inativo). O login do responsável só é
	desativado se ele não acompanhar mais nenhum beneficiário ativo.
	"""
	if not frappe.db.exists("Novo Associado", novo_associado_name):
		return

	doc = frappe.get_doc("Novo Associado", novo_associado_name)
	if not doc.has_permission("write"):
		frappe.throw(_("Você não tem permissão para registrar a desistência."), frappe.PermissionError)

	if doc.desistiu:
		return {"status": "success", "ja_registrada": True}

	doc.desistiu = 1
	doc.data_desistencia = today()
	if motivo:
		doc.motivo_desistencia = motivo
	doc.save()

	_desligar_associado(doc)
	_desativar_acesso_responsaveis(doc.name)

	return {"status": "success"}


@frappe.whitelist()
def enviar_para_fila_espera(novo_associado_name):
	if not frappe.db.exists("Novo Associado", novo_associado_name):
		frappe.throw("Novo Associado não encontrado")

	doc = frappe.get_doc("Novo Associado", novo_associado_name)

	# Update status
	doc.status = "Fila de espera"
	doc.save()

	# Create Fila de Espera entry
	fila = frappe.get_doc(
		{
			"doctype": "Fila de Espera",
			"associado": novo_associado_name,
			"ramo": doc.ramo,
			"dt_inclusao_fila": frappe.utils.now(),
		}
	)
	fila.insert()

	return {"status": "success"}


@frappe.whitelist()
def confirmar_visita(novo_associado_name):
	# Find the latest visit for this associate
	visits = frappe.get_all(
		"Agenda de Visitas",
		filters={"jovem": novo_associado_name},
		order_by="data_da_visita desc",
		limit=1,
	)

	if not visits:
		frappe.throw("Nenhuma visita agendada encontrada para este associado.")

	visit_name = visits[0].name
	frappe.db.set_value("Agenda de Visitas", visit_name, "visita_confirmada", 1)

	return {"status": "success"}


@frappe.whitelist()
def remover_confirmacao_visita(novo_associado_name):
	# Find the latest visit for this associate
	visits = frappe.get_all(
		"Agenda de Visitas",
		filters={"jovem": novo_associado_name},
		order_by="data_da_visita desc",
		limit=1,
	)

	if not visits:
		frappe.throw("Nenhuma visita agendada encontrada para este associado.")

	visit_name = visits[0].name
	frappe.db.set_value("Agenda de Visitas", visit_name, "visita_confirmada", 0)

	return {"status": "success"}


@frappe.whitelist()
def registrar_recepcao_realizada(novo_associado_name):
	if not frappe.db.exists("Novo Associado", novo_associado_name):
		frappe.throw("Novo Associado não encontrado")

	doc = frappe.get_doc("Novo Associado", novo_associado_name)
	doc.status = "Aguardar Dados"
	doc.primeira_visita_realizada = 1
	doc.save()

	return {"status": "success"}


@frappe.whitelist()
def adicionar_comentario(novo_associado_name: str, content: str):
	"""Cria um Comment vinculado ao Novo Associado para uso interno da recepção."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Você precisa estar autenticado."), frappe.PermissionError)

	if not novo_associado_name:
		frappe.throw(_("Informe o registro do associado."))

	content = (content or "").strip()
	if not content:
		frappe.throw(_("O comentário não pode estar vazio."))

	# Verifica se o registro existe e se o usuário tem permissão de escrita
	doc = frappe.get_doc("Novo Associado", novo_associado_name)
	if not doc.has_permission("write"):
		frappe.throw(_("Você não tem permissão para comentar."), frappe.PermissionError)

	comment = frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Comment",
			"reference_doctype": "Novo Associado",
			"reference_name": novo_associado_name,
			"content": content,
		}
	)
	comment.insert()

	clean_text = strip_html((content or "").replace("</p>", "\n").replace("<br>", "\n"))

	return {
		"name": comment.name,
		"content": comment.content,
		"content_text": clean_text,
		"owner": comment.owner,
		"owner_fullname": get_fullname(comment.owner),
		"creation": format_datetime(comment.creation, "dd/MM/yyyy HH:mm"),
	}


@frappe.whitelist()
def editar_comentario(comment_name: str, content: str):
	"""Edita um comentário existente se o usuário for dono ou tiver permissão de escrita no registro."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Você precisa estar autenticado."), frappe.PermissionError)

	content = (content or "").strip()
	if not content:
		frappe.throw(_("O comentário não pode estar vazio."))

	if not comment_name:
		frappe.throw(_("Comentário inválido."))

	comment = frappe.get_doc("Comment", comment_name)
	if comment.reference_doctype != "Novo Associado":
		frappe.throw(_("Edição não permitida."), frappe.PermissionError)

	ref_name = comment.reference_name
	if not ref_name or not frappe.db.exists("Novo Associado", ref_name):
		frappe.throw(_("Registro relacionado não encontrado."))

	ref_doc = frappe.get_doc("Novo Associado", ref_name)

	# Pode editar se for dono ou tiver permissão de escrita no Doc
	if comment.owner != frappe.session.user and not ref_doc.has_permission("write"):
		frappe.throw(_("Você não tem permissão para editar este comentário."), frappe.PermissionError)

	comment.content = content
	comment.save()

	clean_text = strip_html((content or "").replace("</p>", "\n").replace("<br>", "\n"))

	return {
		"name": comment.name,
		"content": comment.content,
		"content_text": clean_text,
		"owner": comment.owner,
		"owner_fullname": get_fullname(comment.owner),
		"creation": format_datetime(comment.creation, "dd/MM/yyyy HH:mm"),
	}
