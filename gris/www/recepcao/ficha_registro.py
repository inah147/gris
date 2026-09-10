import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import add_days, cint, format_date, format_datetime, get_fullname, getdate, strip_html

from gris.api.portal_access import enrich_context
from gris.www.recepcao.ficha_campos import BLOCOS_DO_ASSOCIADO, BLOCOS_DO_RESPONSAVEL, montar_blocos

no_cache = 1

# Documentos do responsável hospedados no Drive, e o campo que guarda o link de cada um.
# A ficha serve os arquivos pelo GRIS: o drive é de acesso restrito e nem toda a equipe
# da recepção tem conta com acesso a ele.
DOCUMENTOS_DO_RESPONSAVEL = {
	"identificacao": ("link_documento_identificacao", "Documento de identificacao"),
	"declaracao": ("link_declaracao_idoneidade", "Declaracao de Idoneidade"),
	"declaracao_assinada": ("link_declaracao_idoneidade_assinada", "Declaracao de Idoneidade assinada"),
}


def get_context(context):
	# Ensure user is logged in (or handle permissions as needed)
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login"
		raise frappe.Redirect

	context.active_link = "/recepcao"
	enrich_context(context, "/recepcao/ficha_registro")

	name = frappe.form_dict.get("name")

	if not name:
		context.not_found = True
		context.missing_reason = "Parâmetro 'name' não informado."
		return context

	try:
		# Fetch Novo Associado
		doc = frappe.get_doc("Novo Associado", name)
	except frappe.DoesNotExistError:
		context.not_found = True
		context.missing_reason = "Novo Associado não encontrado."
		return context

	# Fetch configuration for intervals
	try:
		config = frappe.get_doc("Configuracoes de Recepcao").as_dict()
	except (frappe.DoesNotExistError, ImportError):
		config = {}

	# Map Novo Associado fields to Config fields
	field_interval_map = {
		"dados_para_registro_enviados": "dados_para_registro_enviados",
		"registro_criado_no_paxtu": "registro_criado_no_paxtu",
		"registro_provisorio_efetivado": "registro_provisorio_efetivado",
		"pesquisa_de_novos_associados_respondida": "pesquisa_de_novos_associados_respondida",
		"ficha_medica_preenchida": "ficha_medica_preenchida",
		"id_escoteiros_criado": "id_escoteiros_criado",
		"boleto_definitivo_gerado": "boleto_definitivo_gerado",
		"registro_definitivo_efetivado": "registro_definitivo_efetivado",
		"reuniao_de_acolhida_realizada": "reuniao_de_acolhida_realizada",
	}

	context.doc = doc
	context.title = doc.nome_completo
	# A ordem dos campos vive em ``ficha_campos`` — é a mesma do formulário do Paxtu, e é
	# conferida num lugar só em vez de campo a campo no template.
	context.blocos = montar_blocos(doc, BLOCOS_DO_ASSOCIADO)

	# Fetch Responsibles via Responsavel Vinculo
	vinculos = frappe.get_all(
		"Responsavel Vinculo", filters={"beneficiario_novo_associado": name}, fields=["*"]
	)

	responsaveis = []
	context.guarda_unilateral = cint(vinculos[0].guarda_unilateral) if vinculos else 0
	context.tipo_guarda = (vinculos[0].get("tipo_guarda") or "").strip() if vinculos else ""
	# Cadastros anteriores ao select de tipo de guarda só têm o booleano gravado.
	if context.tipo_guarda in ("", "-") and context.guarda_unilateral:
		context.tipo_guarda = "Unilateral"
	# Guarda alternada é o único caso em que os dois responsáveis são inscritos, cada um na
	# sua inscrição: a recepção precisa ver isso antes de abrir o registro no Paxtu.
	context.guarda_alternada = context.tipo_guarda == "Alternada"
	for v in vinculos:
		if v.responsavel:
			resp_doc = frappe.get_doc("Responsavel", v.responsavel)
			responsaveis.append(
				{
					"vinculo": v,
					"doc": resp_doc,
					"blocos": montar_blocos(resp_doc, BLOCOS_DO_RESPONSAVEL),
					"sera_registrado": cint(v.get("sera_registrado")),
					# Só se o documento existe: o link do Drive não vai para a página, porque
					# o download passa pelo GRIS (drive de acesso restrito).
					"documentos": {
						tipo: bool((resp_doc.get(campo) or "").strip())
						for tipo, (campo, _rotulo) in DOCUMENTOS_DO_RESPONSAVEL.items()
					},
				}
			)

	responsaveis.sort(key=lambda x: x["doc"].nome_completo or "")
	context.responsaveis = responsaveis
	# A seção de números de registro só lista quem de fato tira registro: o jovem
	# sempre, e os responsáveis marcados como ``sera_registrado`` no vínculo — o que
	# hoje só acontece no ramo Filhotes. É a mesma regra da pendência conferida em
	# ``gris.api.recepcao.numeros_de_registro_pendentes``.
	context.responsaveis_com_registro = [item for item in responsaveis if item["sera_registrado"]]
	# A seção de documentos só faz sentido no ramo que exige o registro do responsável.
	context.is_filhotes = (doc.ramo or "") == "Filhotes"

	# Flow steps for infographic
	flow_steps = [
		{"field": "visita_agendada", "label": "Visita Agendada"},
		{"field": "primeira_visita_realizada", "label": "Primeira Visita"},
		{"field": "dados_para_registro_enviados", "label": "Dados Enviados"},
		{"field": "registro_criado_no_paxtu", "label": "Registro Paxtu"},
		{"field": "registro_provisorio_efetivado", "label": "Prov. Efetivado"},
		{"field": "pesquisa_de_novos_associados_respondida", "label": "Pesquisa Respondida"},
		{"field": "ficha_medica_preenchida", "label": "Ficha Médica"},
		{"field": "id_escoteiros_criado", "label": "ID Criado"},
		{"field": "boleto_definitivo_gerado", "label": "Boleto Gerado"},
		{"field": "registro_definitivo_efetivado", "label": "Def. Efetivado"},
		{"field": "reuniao_de_acolhida_realizada", "label": "Acolhida"},
	]

	# Filter steps based on logic
	final_steps = []
	dados_enviados = bool(doc.get("dados_para_registro_enviados"))

	if not dados_enviados:
		final_steps = flow_steps[:4]
	elif doc.get("tipo_de_registro") == "Definitivo":
		final_steps = [s for s in flow_steps if s["field"] != "registro_provisorio_efetivado"]
	else:
		final_steps = flow_steps

	# Process steps state
	steps_data = []

	# Initial date calculation base
	# Try to find a visit date
	visit_date = None
	visit_rec = frappe.get_all(
		"Agenda de Visitas",
		filters={"jovem": doc.name},
		fields=["data_da_visita"],
		order_by="data_da_visita desc",
		limit=1,
	)
	if visit_rec:
		visit_date = visit_rec[0].data_da_visita

	current_calc_date = visit_date
	today = getdate()

	for step in final_steps:
		is_done = bool(doc.get(step["field"]))
		step_info = {"label": step["label"], "done": is_done, "field": step["field"]}

		# Calculate dates for pending steps
		if current_calc_date:
			config_field_name = field_interval_map.get(step["field"])
			if config_field_name:
				days_val = config.get(config_field_name) or 0
				try:
					days_int = int(days_val)
					current_calc_date = add_days(current_calc_date, days_int)
					# If not completed, show the estimated date
					if not is_done:
						step_info["estimated_date"] = format_date(current_calc_date)
						# Check if overdue
						if current_calc_date < today:
							step_info["is_overdue"] = True
				except (ValueError, TypeError):
					pass

		steps_data.append(step_info)

	context.flow_steps = steps_data

	# Comentários internos (usando Comment)
	comments = frappe.get_all(
		"Comment",
		filters={
			"reference_doctype": "Novo Associado",
			"reference_name": name,
			"comment_type": "Comment",
		},
		fields=["name", "content", "owner", "creation"],
		order_by="creation desc",
		limit=50,
	)

	context.comments = [
		{
			"name": c.name,
			"content_text": strip_html((c.content or "").replace("</p>", "\n").replace("<br>", "\n")),
			"owner": c.owner,
			"owner_fullname": get_fullname(c.owner),
			"creation": format_datetime(c.creation, "dd/MM/yyyy HH:mm"),
		}
		for c in comments
	]
	context.comments_count = len(comments)
	context.can_add_comments = doc.has_permission("write")
	# Mesma permissão do comentário, mas com nome próprio: quem só lê a ficha vê os
	# números de registro como texto, sem campo editável nem botão de salvar.
	context.pode_editar_registro = doc.has_permission("write")
	context.current_user = frappe.session.user

	return context


@frappe.whitelist()
@rate_limit(key="ficha-mensagens", limit=60, seconds=60)
def listar_mensagens_enviadas(novo_associado_name: str) -> list[dict]:
	"""Mensagens que o GRIS já tentou entregar a respeito deste jovem.

	Lê o ``Log de Mensagem``, gravado por ``gris.utils.whatsapp`` no ponto em que o resultado
	do provedor é conhecido. Só aparecem aqui os envios feitos depois que o log passou a
	existir: não havia registro nenhum antes dele, e o histórico anterior não é recuperável.

	Os avisos que falam de vários jovens de uma vez (as visitas do dia, por exemplo) ficam
	sem ``novo_associado`` e por isso não entram na ficha de ninguém.
	"""
	if not novo_associado_name:
		frappe.throw(_("Novo Associado não especificado."))

	if not frappe.has_permission("Novo Associado", "read", novo_associado_name):
		frappe.throw(_("Sem permissão para acessar este registro."), frappe.PermissionError)

	mensagens = frappe.get_all(
		"Log de Mensagem",
		filters={"novo_associado": novo_associado_name},
		fields=[
			"name",
			"enviada_em",
			"status",
			"assunto",
			"destinatario_tipo",
			"destinatario_nome",
			"destinatario_numero",
			"conteudo",
			"erro",
		],
		order_by="enviada_em desc",
		limit_page_length=200,
	)

	_resolver_nomes_de_grupo(mensagens)

	for mensagem in mensagens:
		mensagem["data"] = format_date(mensagem["enviada_em"], "dd/MM/yyyy")
		mensagem["hora"] = format_datetime(mensagem["enviada_em"], "HH:mm")

	return mensagens


def _resolver_nomes_de_grupo(mensagens: list[dict]) -> None:
	"""Troca o JID dos grupos pelo nome, para a ficha não mostrar "1203...@g.us".

	Só a Evolution API sabe o assunto de cada grupo. A consulta acontece aqui, uma vez por
	abertura do diálogo, e não a cada envio: no envio poria uma chamada de rede no caminho de
	toda mensagem. Se a API não responder, cada linha fica com o JID — que é o que já estava
	gravado — em vez de a ficha inteira falhar.
	"""
	jids = {
		mensagem["destinatario_numero"]
		for mensagem in mensagens
		if not mensagem.get("destinatario_nome")
		and (mensagem.get("destinatario_numero") or "").endswith("@g.us")
	}
	if not jids:
		return

	from gris.utils.whatsapp import listar_grupos_whatsapp

	try:
		nomes = {grupo["id"]: grupo.get("subject") or grupo["id"] for grupo in listar_grupos_whatsapp()}
	except Exception:
		frappe.logger("recepcao", allow_site=True).warning(
			"Nomes dos grupos não resolvidos na ficha de registro; as linhas ficam com o JID."
		)
		nomes = {}

	for mensagem in mensagens:
		numero = mensagem.get("destinatario_numero") or ""
		if not mensagem.get("destinatario_nome") and numero in jids:
			mensagem["destinatario_nome"] = nomes.get(numero, numero)


@frappe.whitelist()
@rate_limit(key="ficha-baixar-documento", limit=60, seconds=60)
def baixar_documento_do_responsavel(novo_associado_name: str, responsavel_name: str, tipo: str):
	"""Entrega pelo GRIS um documento do responsável hospedado no Drive.

	Os arquivos ficam num drive de **acesso restrito**, então o link do Google não abre
	para quem não é membro dele. Servir por aqui mantém o acesso preso à permissão de
	leitura do Novo Associado, que é onde a regra já vive.
	"""
	from gris.api.google_workspace import recepcao_drive

	campo_e_rotulo = DOCUMENTOS_DO_RESPONSAVEL.get(tipo)
	if not campo_e_rotulo:
		frappe.throw(_("Tipo de documento inválido."))
	campo, rotulo = campo_e_rotulo

	if not frappe.has_permission("Novo Associado", "read", novo_associado_name):
		frappe.throw(_("Sem permissão para acessar este registro."), frappe.PermissionError)

	if not frappe.db.exists(
		"Responsavel Vinculo",
		{"responsavel": responsavel_name, "beneficiario_novo_associado": novo_associado_name},
	):
		frappe.throw(_("Responsável não vinculado a este jovem."), frappe.PermissionError)

	link = (frappe.db.get_value("Responsavel", responsavel_name, campo) or "").strip()
	if not link:
		frappe.throw(_("Documento não enviado."))

	conteudo, _nome_no_drive, mimetype = recepcao_drive.download_file(link)
	nome_responsavel = frappe.db.get_value("Responsavel", responsavel_name, "nome_completo") or ""

	frappe.local.response.filename = f"{rotulo} - {nome_responsavel}".strip(" -")
	frappe.local.response.filecontent = conteudo
	frappe.local.response.type = "pdf" if mimetype == "application/pdf" else "download"
