import frappe
from frappe import _
from frappe.utils import format_datetime, get_fullname, getdate, strip_html


def formatar_idade(data_nascimento) -> str | None:
	"""Idade completa em anos e meses, por extenso (ex.: "6 anos e 1 mês").

	Sempre calculada a partir da data de hoje — nunca persistir o resultado,
	para que as telas mostrem a idade atualizada a cada carregamento.
	Retorna None quando a data é ausente, inválida ou está no futuro.
	"""
	if not data_nascimento:
		return None

	try:
		nascimento = getdate(data_nascimento)
	except Exception:
		return None

	hoje = getdate()
	if not nascimento or nascimento > hoje:
		return None

	anos = hoje.year - nascimento.year
	meses = hoje.month - nascimento.month
	if hoje.day < nascimento.day:
		meses -= 1
	if meses < 0:
		anos -= 1
		meses += 12

	if not anos and not meses:
		return "Menos de 1 mês"

	partes = []
	if anos:
		partes.append(f"{anos} ano" if anos == 1 else f"{anos} anos")
	if meses:
		partes.append(f"{meses} mês" if meses == 1 else f"{meses} meses")

	return " e ".join(partes)


@frappe.whitelist()
def update_novo_associado(
	name: str,
	responsavel_recepcao: str | None = None,
	status: str | None = None,
	motivo_desistencia: str | None = None,
):
	"""Campos do Novo Associado que a recepção edita à mão.

	``ramo`` não entra aqui de propósito: ele é derivado da idade em ``before_insert`` e
	recalculado todo dia por ``atualizar_ramos_por_idade``, então qualquer escrita manual
	era desfeita no ciclo seguinte. Para corrigir o ramo, corrija a data de nascimento.
	"""
	doc = frappe.get_doc("Novo Associado", name)
	if responsavel_recepcao:
		doc.responsavel_recepcao = responsavel_recepcao
	if status:
		doc.status = status
	if motivo_desistencia:
		doc.motivo_desistencia = motivo_desistencia
	doc.save()
	return doc.as_dict()


def _anonimizar_user(user_email):
	"""Anonimiza o login do responsável que desistiu (LGPD).

	Não é possível excluir o User: ele tem um Board pessoal criado pelo hook
	`after_insert` (gris.gestao_de_tarefas.user_board.criar_board_pessoal) cujo
	Dynamic Link dispara LinkExistsError. Então removemos o Board pessoal — que
	também guarda o nome no título — e anonimizamos o User, inclusive renomeando
	o email/login para um identificador anônimo.
	"""
	# Remove o Board pessoal (Dynamic Link bloqueador + título com o nome) e suas tarefas
	boards = frappe.get_all(
		"Board",
		filters={"referencia_doctype": "User", "referencia_nome": user_email},
		pluck="name",
	)
	for board in boards:
		frappe.db.delete("Gestao de Tarefas", {"board": board})
		frappe.delete_doc("Board", board, ignore_permissions=True)

	# Renomeia o login para um identificador anônimo (atualiza os links que apontam
	# ao User). Usa o rename_doc interno: o wrapper público `frappe.rename_doc` não
	# expõe `ignore_permissions`, necessário aqui porque a recepção não tem permissão
	# de escrita em User.
	from frappe.model.rename_doc import rename_doc

	anon_email = f"desativado-{frappe.generate_hash(length=10)}@anonimizado.invalid"
	rename_doc("User", user_email, anon_email, force=True, ignore_permissions=True)

	# Limpa os dados pessoais remanescentes e desativa o acesso
	frappe.db.set_value(
		"User",
		anon_email,
		{
			"enabled": 0,
			"email": anon_email,
			# username e mobile_no são UNIQUE em tabUser. Gravar "" (literal, via set_value,
			# que não passa pela conversão da ORM) colide com outros Users já anonimizados
			# ("Duplicate entry '' for key '<campo>'"). NULL é permitido em múltiplas linhas
			# no índice UNIQUE. (api_key também é UNIQUE, mas não é tocado aqui.)
			"username": None,
			"first_name": "ANONIMIZADO",
			"last_name": "",
			"full_name": "ANONIMIZADO",
			"mobile_no": None,
			"phone": "",
			"birth_date": None,
			"location": "",
			"bio": "",
		},
	)


def _desvincular_referencias(doctype, name):
	"""Limpa todas as referências Link a ``name`` antes de excluí-lo.

	- child table (meta.istable): apaga as linhas que referenciam o registro;
	- single doctype: zera o campo no Single;
	- doc normal: seta o campo para NULL em todas as linhas que apontam ao registro.

	Usa ``get_link_fields`` (o mesmo mapa que ``check_if_doc_is_linked`` usa para
	detectar os bloqueios de exclusão) para não depender de uma lista fixa de
	DocTypes — qualquer DocType futuro que aponte para ``doctype`` é tratado
	automaticamente. Dynamic Links remanescentes (Comment, ToDo, File…) já estão
	em ``ignore_links_on_delete`` do Frappe e não bloqueiam a exclusão.
	"""
	from frappe.model.rename_doc import get_link_fields

	for lf in get_link_fields(doctype):
		link_dt, link_field, issingle = lf["parent"], lf["fieldname"], lf["issingle"]
		if link_dt == doctype:  # auto-referência: ignora
			continue
		if issingle:
			if frappe.db.get_single_value(link_dt, link_field) == name:
				frappe.db.set_single_value(link_dt, link_field, None)
			continue
		if frappe.get_meta(link_dt).istable:
			frappe.db.delete(link_dt, {link_field: name})
			continue
		frappe.db.set_value(link_dt, {link_field: name}, link_field, None, update_modified=False)


@frappe.whitelist()
def processar_desistencia(novo_associado_name: str, motivo: str | None = None):
	# 1. Get Novo Associado
	if not frappe.db.exists("Novo Associado", novo_associado_name):
		return

	novo_associado = frappe.get_doc("Novo Associado", novo_associado_name)
	cpf = novo_associado.cpf

	# 2. Delete scheduled visits
	frappe.db.delete("Agenda de Visitas", {"jovem": novo_associado_name})

	# 3. Handle Associado (Anonimizar + Desligamento context)
	# Check if effective
	is_effective = (
		novo_associado.registro_provisorio_efetivado or novo_associado.registro_definitivo_efetivado
	)

	if is_effective and cpf:
		# Try to find Associado by Name (CPF)
		associado_name = cpf
		if frappe.db.exists("Associado", associado_name):
			assoc_doc = frappe.get_doc("Associado", associado_name)

			# Anonimize fields
			fields_to_anonymize = [
				"nome_completo",
				"email",
				"telefone",
				"cep_residencia",
				"numero_residencia",
				"nome_responsavel_1",
				"cpf_responsavel_1",
				"email_responsavel_1",
				"telefone_responsavel_1",
				"nome_responsavel_2",
				"cpf_responsavel_2",
				"email_responsavel_2",
				"telefone_responsavel_2",
				"religiao",
				"etnia",
			]

			for field in fields_to_anonymize:
				if assoc_doc.meta.has_field(field):
					assoc_doc.set(field, "ANONIMIZADO")

			# Historico de Desligamento
			if assoc_doc.historico_no_grupo:
				for row in assoc_doc.historico_no_grupo:
					if not row.data_de_desligamento:
						row.data_de_desligamento = frappe.utils.today()
						break

			assoc_doc.save(ignore_permissions=True)

	# 4. Find and Clean Responsavel Vinculo
	vinculos = frappe.get_all(
		"Responsavel Vinculo",
		filters={"beneficiario_novo_associado": novo_associado_name},
		fields=["name", "responsavel"],
	)

	for vinculo in vinculos:
		responsavel_id = vinculo.responsavel

		# Delete the link
		frappe.delete_doc("Responsavel Vinculo", vinculo.name, ignore_permissions=True)

		# Check if Responsavel has other links (Vinculo)
		other_links_count = frappe.db.count("Responsavel Vinculo", {"responsavel": responsavel_id})

		if other_links_count == 0:
			# Check if Responsavel has Survey Answer
			# Note: Doctype has a typo 'Pesqusa' which is correct in the system
			if frappe.db.exists("Pesqusa de Novos Associados", {"responsavel": responsavel_id}):
				# Unlink Responsavel from Survey to keep the survey data but allow user deletion
				frappe.db.set_value(
					"Pesqusa de Novos Associados", {"responsavel": responsavel_id}, "responsavel", None
				)

			# No other links, delete Responsavel and User
			if frappe.db.exists("Responsavel", responsavel_id):
				responsavel_doc = frappe.get_doc("Responsavel", responsavel_id)
				user_email = responsavel_doc.email

				# O Responsavel pode estar vinculado a outros contextos além do associado
				# (ex.: coordenador geral de Festa, padrinho de Projeto, membro de equipe).
				# Nesses casos o delete dispara LinkExistsError. Política: não preservar —
				# desvinculamos todas as referências e excluímos o cadastro de fato.
				try:
					frappe.delete_doc("Responsavel", responsavel_id, ignore_permissions=True)
				except frappe.LinkExistsError:
					_desvincular_referencias("Responsavel", responsavel_id)
					frappe.delete_doc("Responsavel", responsavel_id, ignore_permissions=True)

				if user_email and frappe.db.exists("User", user_email):
					_anonimizar_user(user_email)

	# 5. Cleanup Fila de Espera (if any)
	frappe.db.delete("Fila de Espera", {"associado": novo_associado_name})

	# 6. Delete Novo Associado
	frappe.delete_doc("Novo Associado", novo_associado_name, ignore_permissions=True)

	return {"status": "success"}


@frappe.whitelist()
def enviar_para_fila_espera(novo_associado_name: str):
	if not frappe.db.exists("Novo Associado", novo_associado_name):
		frappe.throw(_("Novo Associado não encontrado"))

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
def confirmar_visita(novo_associado_name: str):
	# Find the latest visit for this associate
	visits = frappe.get_all(
		"Agenda de Visitas",
		filters={"jovem": novo_associado_name},
		order_by="data_da_visita desc",
		limit=1,
	)

	if not visits:
		frappe.throw(_("Nenhuma visita agendada encontrada para este associado."))

	visit_name = visits[0].name
	frappe.db.set_value("Agenda de Visitas", visit_name, "visita_confirmada", 1)

	return {"status": "success"}


@frappe.whitelist()
def remover_confirmacao_visita(novo_associado_name: str):
	# Find the latest visit for this associate
	visits = frappe.get_all(
		"Agenda de Visitas",
		filters={"jovem": novo_associado_name},
		order_by="data_da_visita desc",
		limit=1,
	)

	if not visits:
		frappe.throw(_("Nenhuma visita agendada encontrada para este associado."))

	visit_name = visits[0].name
	frappe.db.set_value("Agenda de Visitas", visit_name, "visita_confirmada", 0)

	return {"status": "success"}


@frappe.whitelist()
def registrar_recepcao_realizada(novo_associado_name: str):
	if not frappe.db.exists("Novo Associado", novo_associado_name):
		frappe.throw(_("Novo Associado não encontrado"))

	doc = frappe.get_doc("Novo Associado", novo_associado_name)
	doc.status = "Aguardar Dados"
	doc.primeira_visita_realizada = 1
	doc.save()

	return {"status": "success"}


# Teto da listagem de observações. O mesmo valor da ficha (ficha_registro.py): a caixa
# é de acompanhamento, não de histórico completo.
LIMITE_DE_COMENTARIOS = 50


def _texto_do_comentario(content: str | None) -> str:
	"""Conteúdo do Comment em texto puro, preservando as quebras de linha do editor."""
	return strip_html((content or "").replace("</p>", "\n").replace("<br>", "\n"))


@frappe.whitelist()
def listar_comentarios(novo_associado_name: str):
	"""Observações internas de um Novo Associado, da mais recente para a mais antiga.

	Mesmo formato devolvido por ``adicionar_comentario``/``editar_comentario``, para que a
	visão geral renderize item carregado e item recém-criado com um único caminho.
	"""
	if not novo_associado_name:
		frappe.throw(_("Informe o registro do associado."))

	if not frappe.has_permission("Novo Associado", "read", novo_associado_name):
		frappe.throw(_("Sem permissão para acessar este registro."), frappe.PermissionError)

	filtros = {
		"reference_doctype": "Novo Associado",
		"reference_name": novo_associado_name,
		"comment_type": "Comment",
	}

	comentarios = frappe.get_all(
		"Comment",
		filters=filtros,
		fields=["name", "content", "owner", "creation"],
		order_by="creation desc",
		limit=LIMITE_DE_COMENTARIOS,
	)

	return {
		"pode_comentar": bool(frappe.has_permission("Novo Associado", "write", novo_associado_name)),
		"usuario_atual": frappe.session.user,
		# `total` é a contagem real: a lista vem truncada e o balão do card mostra o total.
		"total": frappe.db.count("Comment", filtros),
		"comentarios": [
			{
				"name": c.name,
				"content": c.content,
				"content_text": _texto_do_comentario(c.content),
				"owner": c.owner,
				"owner_fullname": get_fullname(c.owner),
				"creation": format_datetime(c.creation, "dd/MM/yyyy HH:mm"),
			}
			for c in comentarios
		],
	}


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
	comment.insert(ignore_permissions=True)

	clean_text = _texto_do_comentario(content)

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
	comment.save(ignore_permissions=True)

	clean_text = _texto_do_comentario(content)

	return {
		"name": comment.name,
		"content": comment.content,
		"content_text": clean_text,
		"owner": comment.owner,
		"owner_fullname": get_fullname(comment.owner),
		"creation": format_datetime(comment.creation, "dd/MM/yyyy HH:mm"),
	}
