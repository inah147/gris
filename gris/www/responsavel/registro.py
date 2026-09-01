import json
import re

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, now_datetime

from gris.api.portal_access import enrich_context
from gris.api.recepcao_mensagens import notificar_dados_preenchidos_no_grupo_recepcao
from gris.api.responsavel_acesso import get_responsavel_do_usuario
from gris.gris.doctype.novo_associado.novo_associado import ramo_por_data_de_nascimento
from gris.utils.contato import format_phone
from gris.utils.documento import cpf_valido, id_por_cpf, limpar_cpf

# Campos do responsável editáveis pelo formulário, no nome usado pelo frontend.
CAMPOS_RESPONSAVEL = [
	"nome_completo",
	"cpf",
	"rg",
	"orgao_expedidor",
	"data_de_nascimento",
	"cidade_de_nascimento",
	"uf_de_nascimento",
	"sexo",
	"estado_civil",
	"escolaridade",
	"profissao",
	"local_de_trabalho",
	"cep",
	"endereco",
	"numero",
	"complemento",
	"bairro",
	"cidade",
	"estado",
	"email",
	"celular",
	"telefone_secundario",
]

# Alguns campos do DocType ``Responsavel`` têm acento no fieldname; o formulário usa a
# versão sem acento para não depender da codificação no HTML/JS.
MAPA_CAMPOS_RESPONSAVEL = {"endereco": "endereço", "numero": "número", "profissao": "profissão"}

RAMO_FILHOTES = "Filhotes"

# Extensões e tipos aceitos nos documentos enviados ao Drive. O responsável costuma
# fotografar o RG pelo celular, então imagem entra junto com PDF.
EXTENSOES_DOCUMENTO = (".pdf", ".jpg", ".jpeg", ".png")
MIMETYPES_DOCUMENTO = {
	".pdf": "application/pdf",
	".jpg": "image/jpeg",
	".jpeg": "image/jpeg",
	".png": "image/png",
}
TAMANHO_MAXIMO_DOCUMENTO = 10 * 1024 * 1024

# Nome dos arquivos no Drive: sempre "<rótulo> - <nome completo do responsável>".
ROTULO_DOCUMENTO_IDENTIDADE = "Documento de identidade"
ROTULO_DECLARACAO_ASSINADA = "Declaracao de Idoneidade assinada"


def _format_currency_brl(value):
	amount = float(value or 0)
	formatted = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
	return f"R$ {formatted}"


def _select_items(options):
	items = [{"label": "Selecione...", "value": ""}]
	for option in options or []:
		option = (option or "").strip()
		if option:
			items.append({"label": option, "value": option})
	return items


def _format_phone_for_ui(phone):
	return format_phone(phone) or ""


def _select_options_for(doctype):
	"""Monta os itens de cada campo Select do DocType, no formato esperado pela macro de select."""
	options = {}
	for field in frappe.get_meta(doctype).fields:
		if field.fieldtype == "Select" and field.options:
			options[field.fieldname] = _select_items(field.options.split("\n"))
	return options


def _responsavel_da_sessao():
	"""Responsável do usuário logado, pela mesma cadeia usada no resto da área ``/responsavel``."""
	responsavel = get_responsavel_do_usuario()
	if not responsavel:
		frappe.throw(_("Perfil de Responsável não encontrado para este usuário."))
	return responsavel


def _assert_pode_editar(responsavel, novo_associado_name):
	"""Só quem tem vínculo com o jovem mexe nos dados dele."""
	if not novo_associado_name:
		frappe.throw(_("Novo Associado não especificado."))

	tem_permissao = frappe.db.exists(
		"Responsavel Vinculo",
		{"responsavel": responsavel, "beneficiario_novo_associado": novo_associado_name},
	)
	if not tem_permissao:
		frappe.throw(_("Você não tem permissão para editar este associado."), frappe.PermissionError)


def _aplicar_campos_responsavel(doc, item, somente_vazios=False):
	"""Copia para o doc os campos do responsável enviados pelo formulário.

	``somente_vazios`` preenche apenas o que ainda está em branco no cadastro — usado
	quando o responsável veio da busca por CPF e não pertence à família de quem edita,
	para que ninguém sobrescreva o cadastro de terceiros.
	"""
	for campo in CAMPOS_RESPONSAVEL:
		if campo not in item:
			continue

		valor = item[campo]
		if campo in ("celular", "telefone_secundario"):
			valor = format_phone(valor)

		destino = MAPA_CAMPOS_RESPONSAVEL.get(campo, campo)
		if somente_vazios and doc.get(destino):
			continue

		doc.set(destino, valor)


def _dados_responsavel_para_form(resp_doc):
	"""Campos do responsável no formato que o formulário consome."""
	dados = {}
	for campo in CAMPOS_RESPONSAVEL:
		valor = resp_doc.get(MAPA_CAMPOS_RESPONSAVEL.get(campo, campo))

		if campo == "numero":
			valor = str(valor) if cint(valor) else ""
		elif campo in ("celular", "telefone_secundario"):
			valor = _format_phone_for_ui(valor)
		elif hasattr(valor, "isoformat"):
			valor = valor.isoformat()
		elif valor is None:
			valor = ""

		dados[campo] = valor

	return dados


def _card_responsavel(resp_doc, vinculo=None, origem="vinculo"):
	return {
		"vinculo": vinculo or {},
		"doc": resp_doc,
		"phone": {
			"celular": _format_phone_for_ui(resp_doc.celular),
			"telefone_secundario": _format_phone_for_ui(resp_doc.telefone_secundario),
		},
		"origem": origem,
	}


def _card_vazio():
	"""Card em branco, para o responsável que ainda não existe no sistema."""
	return {
		"vinculo": {},
		"doc": {},
		"phone": {"celular": "", "telefone_secundario": ""},
		"origem": "novo",
		"is_placeholder": True,
	}


def _beneficiarios_do_responsavel(responsavel):
	"""Beneficiários (em integração e já registrados) vinculados ao responsável."""
	rows = frappe.get_all(
		"Responsavel Vinculo",
		filters={"responsavel": responsavel},
		fields=["beneficiario_novo_associado", "beneficiario_associado"],
	)

	novos = {r.beneficiario_novo_associado for r in rows if r.beneficiario_novo_associado}
	associados = {r.beneficiario_associado for r in rows if r.beneficiario_associado}
	return novos, associados


def _responsaveis_da_familia(responsavel, excluir=None):
	"""Outros responsáveis já vinculados aos beneficiários deste responsável.

	É o que permite recuperar o segundo responsável no cadastro de um irmão: os dados
	já existem no sistema, vinculados ao jovem que foi registrado antes.
	"""
	excluir = set(excluir or [])
	novos, associados = _beneficiarios_do_responsavel(responsavel)

	filtros = []
	if novos:
		filtros.append({"beneficiario_novo_associado": ["in", list(novos)]})
	if associados:
		filtros.append({"beneficiario_associado": ["in", list(associados)]})

	encontrados = {}
	for filtro in filtros:
		vinculos = frappe.get_all(
			"Responsavel Vinculo",
			filters=filtro,
			fields=["responsavel", "guarda_unilateral", "é_guardiao_legal"],
			order_by="modified desc",
		)
		for v in vinculos:
			if not v.responsavel or v.responsavel in excluir or v.responsavel in encontrados:
				continue
			encontrados[v.responsavel] = v

	return list(encontrados.items())


def _assert_cpf_confere(resp_id, cpf_informado):
	"""Vincular alguém de fora da família exige o CPF, o mesmo que a busca por CPF pede.

	Sem isso, bastaria enviar um identificador qualquer para trazer os dados de um
	terceiro para dentro do formulário.
	"""
	digitos = limpar_cpf(cpf_informado)
	if digitos and (
		id_por_cpf(digitos) == resp_id
		or digitos == limpar_cpf(frappe.db.get_value("Responsavel", resp_id, "cpf"))
	):
		return

	frappe.throw(_("Informe o CPF do responsável para vinculá-lo a este jovem."))


def _e_filhotes(data_de_nascimento) -> bool:
	"""O ramo é decidido pela data de nascimento, não pelo campo ``ramo`` gravado.

	``Novo Associado.ramo`` é escrito no ``before_insert`` e recalculado por um job diário,
	mas este formulário deixa editar a data de nascimento: ler o campo persistido deixaria
	escapar das regras do ramo Filhotes quem corrigiu a data agora.
	"""
	if not data_de_nascimento:
		return False

	return ramo_por_data_de_nascimento(data_de_nascimento) == RAMO_FILHOTES


def _resolver_responsavel_do_item(resp_item):
	"""``name`` do ``Responsavel`` que o card representa, se já existir na base."""
	resp_id = (resp_item.get("name") or "").strip()
	if resp_id and frappe.db.exists("Responsavel", resp_id):
		return resp_id

	candidato = id_por_cpf(resp_item.get("cpf"))
	return candidato if candidato and frappe.db.exists("Responsavel", candidato) else ""


def _valor_efetivo(resp_item, campo):
	"""Valor do campo considerando o que já está gravado no cadastro.

	O formulário só envia o que renderiza. Um responsável recuperado da família pode já ter
	cidade de nascimento ou documento no cadastro sem que o card tenha mandado o valor —
	exigir o reenvio seria pedir de novo o que o sistema já sabe.
	"""
	valor = (resp_item.get(campo) or "").strip()
	if valor:
		return valor

	resp_id = _resolver_responsavel_do_item(resp_item)
	if not resp_id:
		return ""

	return (frappe.db.get_value("Responsavel", resp_id, campo) or "").strip()


def _validar_regras_filhotes(data, responsaveis_data):
	"""Regras que só valem para o ramo Filhotes, aplicadas antes de qualquer gravação.

	No ramo Filhotes só o adulto registrado pode acompanhar a criança, então pelo menos um
	responsável precisa ser registrado junto — e quem for registrado precisa dos dados que
	a declaração de idoneidade exige, além do documento com foto.
	"""
	if not cint(data.get("ciente_registro_responsavel_filhotes")) or not cint(
		data.get("ciente_acompanhamento_filhotes")
	):
		frappe.throw(
			_("Para o ramo Filhotes é necessário confirmar as duas ciências sobre o registro do responsável.")
		)

	preenchidos = [
		item
		for item in responsaveis_data or []
		if (item.get("nome_completo") or "").strip() or (item.get("cpf") or "").strip()
	]
	if not preenchidos:
		frappe.throw(_("Informe ao menos um responsável para o registro."))

	# Com um único responsável não há escolha a fazer: ele é quem será registrado.
	if len(preenchidos) == 1:
		preenchidos[0]["sera_registrado"] = 1

	marcados = [item for item in preenchidos if cint(item.get("sera_registrado"))]
	if not marcados:
		frappe.throw(
			_("Selecione ao menos um responsável que será registrado junto com o jovem do ramo Filhotes.")
		)

	# Naturalidade é obrigatória para todo responsável do ramo, não só para quem será
	# registrado: é o dado que a declaração de idoneidade exige, e o segundo responsável
	# pode passar a ser o registrado depois.
	naturalidade = (
		("cidade_de_nascimento", "cidade de nascimento"),
		("uf_de_nascimento", "UF de nascimento"),
	)

	for item in preenchidos:
		nome = (item.get("nome_completo") or "").strip() or _("Responsável")
		faltando = [rotulo for campo, rotulo in naturalidade if not _valor_efetivo(item, campo)]
		if faltando:
			frappe.throw(
				_("Informe {1} de {0}.").format(nome, " e ".join(faltando)),
			)

	for item in marcados:
		nome = (item.get("nome_completo") or "").strip() or _("Responsável")

		if not _valor_efetivo(item, "rg"):
			frappe.throw(_("Para registrar {0} é necessário informar o RG.").format(nome))

		if not _valor_efetivo(item, "link_documento_identificacao"):
			frappe.throw(
				_("Envie o documento de identificação com foto de {0} para concluir o registro.").format(nome)
			)


def _encontrar_responsavel_por_cpf(cpf):
	"""Nome do ``Responsavel`` com este CPF, se existir."""
	digitos = limpar_cpf(cpf)
	if not digitos:
		return None

	candidato = id_por_cpf(digitos)
	if candidato and frappe.db.exists("Responsavel", candidato):
		return candidato

	# Cadastros antigos podem não seguir a regra de nome derivada do CPF e a base guarda
	# o CPF nos dois formatos (só dígitos e pontuado).
	formatado = f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
	return frappe.db.get_value("Responsavel", {"cpf": ["in", [digitos, formatado]]}, "name")


def _enriquecer_contexto_filhotes(context, novo_associado, responsaveis):
	"""Contexto do fluxo exclusivo do ramo Filhotes.

	``idade_transicao_filhotes`` vai para a página porque o formulário deixa editar a data
	de nascimento: o JS refaz a conta a cada mudança e liga a UI do ramo sem recarregar.
	"""
	vagas = frappe.get_single("Vagas")
	context.idade_transicao_filhotes = float(vagas.get("idade_transicao_filhotes") or 0)
	context.is_filhotes = _e_filhotes(novo_associado.data_de_nascimento)

	config = frappe.get_single("Configuracoes de Recepcao")
	context.curso_protecao_url = (config.get("link_curso_protecao_infanto_juvenil") or "").strip()

	# Quem será registrado e ainda não mandou a declaração assinada: alimenta o banner do
	# topo e o dialog que abre sozinho quando o responsável volta à página.
	pendentes = []
	for item in responsaveis:
		doc = item.get("doc") or {}
		if not getattr(doc, "name", None):
			continue
		if not cint((item.get("vinculo") or {}).get("sera_registrado")):
			continue
		if (doc.get("link_declaracao_idoneidade_assinada") or "").strip():
			continue
		pendentes.append({"name": doc.name, "nome_completo": doc.nome_completo or _("Responsável")})

	context.responsaveis_pendentes_declaracao = pendentes
	context.declaracao_pendente = bool(
		context.is_filhotes and cint(novo_associado.dados_para_registro_enviados) and pendentes
	)


def get_context(context):
	# Get current user
	user = frappe.session.user
	if user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/responsavel/beneficiarios"
		raise frappe.Redirect

	# Get Novo Associado ID from request
	novo_associado_name = frappe.form_dict.get("novo_associado")

	responsavel = _responsavel_da_sessao()
	_assert_pode_editar(responsavel, novo_associado_name)

	# Fetch Novo Associado data
	novo_associado = frappe.get_doc("Novo Associado", novo_associado_name)

	context.novo_associado = novo_associado
	context.novo_associado_phone = {
		"celular": _format_phone_for_ui(novo_associado.celular),
		"telefone_secundario": _format_phone_for_ui(novo_associado.telefone_secundario),
		"telefone_cobranca": _format_phone_for_ui(novo_associado.telefone_cobranca),
	}

	# Fetch Responsibles via Responsavel Vinculo
	vinculos = frappe.get_all(
		"Responsavel Vinculo", filters={"beneficiario_novo_associado": novo_associado_name}, fields=["*"]
	)
	vinculo_por_responsavel = {v.responsavel: v for v in vinculos if v.responsavel}

	# A ordem dos cards é fixa: quem está preenchendo vem primeiro, sempre com os dados já
	# salvos no cadastro dele. Ordenar por nome embaralharia os cards de um filho para o outro.
	responsaveis = [
		_card_responsavel(
			frappe.get_doc("Responsavel", responsavel),
			vinculo_por_responsavel.get(responsavel),
			origem="sessao",
		)
	]
	ja_listados = {responsavel}

	for v in vinculos:
		if not v.responsavel or v.responsavel in ja_listados:
			continue
		responsaveis.append(_card_responsavel(frappe.get_doc("Responsavel", v.responsavel), v))
		ja_listados.add(v.responsavel)

	# Sem um segundo responsável neste jovem, recupera o que a família já cadastrou em
	# outro beneficiário (o irmão registrado antes), editável e pronto para ser vinculado.
	da_familia = []
	if len(responsaveis) < 2:
		da_familia = _responsaveis_da_familia(responsavel, excluir=ja_listados)
		for resp_name, vinculo_irmao in da_familia:
			responsaveis.append(
				_card_responsavel(frappe.get_doc("Responsavel", resp_name), vinculo_irmao, origem="familia")
			)
			ja_listados.add(resp_name)
			if len(responsaveis) >= 2:
				break

	# O formulário sempre mostra dois cards: o segundo em branco é onde entra o outro
	# responsável, seja digitado ou trazido pela busca por CPF.
	while len(responsaveis) < 2:
		responsaveis.append(_card_vazio())

	guarda_unilateral = cint(
		(vinculo_por_responsavel.get(responsavel) or (vinculos[0] if vinculos else {})).get(
			"guarda_unilateral"
		)
	)
	# Jovem recém-adicionado nasce com o vínculo zerado: herda a informação da família
	# enquanto os dados de registro não foram enviados.
	if not guarda_unilateral and not cint(novo_associado.dados_para_registro_enviados) and da_familia:
		guarda_unilateral = cint(da_familia[0][1].get("guarda_unilateral"))

	context.responsaveis = responsaveis
	context.family_info = {"guarda_unilateral": guarda_unilateral}

	# Fetch options for Select fields.
	# Cada escopo do formulário lê o metadado do DocType em que os dados serão gravados:
	# o bloco do associado grava em ``Novo Associado`` e o bloco dos responsáveis grava em
	# ``Responsavel``. Montar as duas listas separadamente evita que uma divergência entre os
	# dois schemas (ex.: uma opção com typo em apenas um deles) derrube o save.
	context.options = _select_options_for("Novo Associado")
	context.options_responsavel = _select_options_for("Responsavel")

	try:
		config = frappe.get_doc("Configuracoes de Recepcao")
		context.valor_registro_provisorio = config.get("valor_registro_provisorio")
		context.valor_registro_definitivo = config.get("valor_registro_definitivo")
	except frappe.DoesNotExistError:
		context.valor_registro_provisorio = 0
		context.valor_registro_definitivo = 0

	context.valor_registro_provisorio_fmt = _format_currency_brl(context.valor_registro_provisorio)
	context.valor_registro_definitivo_fmt = _format_currency_brl(context.valor_registro_definitivo)

	_enriquecer_contexto_filhotes(context, novo_associado, responsaveis)

	# Sidebar context
	context.sidebar_title = "Painel do Responsável"
	context.active_link = "/responsavel/beneficiarios"
	enrich_context(context, "/responsavel/beneficiarios")


def _notificar_dados_preenchidos(novo_associado_name: str) -> None:
	"""Avisa o grupo da recepção, com menção geral, que os dados de registro chegaram.

	Antes o aviso ia individualmente para cada usuário com o papel de gestor de associados;
	agora vai para o grupo configurado em Configurações de Recepção, onde toda a equipe vê.
	"""
	notificar_dados_preenchidos_no_grupo_recepcao(novo_associado_name)


def _sincronizar_vinculo(novo_associado_name, resp_id, guarda_unilateral, resp_item):
	"""Garante o vínculo do responsável com o jovem e atualiza os dados do vínculo.

	O card pode trazer um responsável que ainda não tem vínculo com este jovem (o outro
	responsável da família, ou um cadastro achado pela busca por CPF): nesse caso o vínculo
	é criado, em vez de descartar os dados em silêncio.
	"""
	link_name = frappe.db.get_value(
		"Responsavel Vinculo",
		{"responsavel": resp_id, "beneficiario_novo_associado": novo_associado_name},
		"name",
	)

	guardiao = resp_item.get("é_guardiao_legal")
	sera_registrado = resp_item.get("sera_registrado")

	if link_name:
		valores = {"guarda_unilateral": guarda_unilateral}
		if guardiao is not None:
			valores["é_guardiao_legal"] = cint(guardiao)
		if sera_registrado is not None:
			valores["sera_registrado"] = cint(sera_registrado)
		frappe.db.set_value("Responsavel Vinculo", link_name, valores)
		return link_name

	novo_link = frappe.new_doc("Responsavel Vinculo")
	novo_link.responsavel = resp_id
	novo_link.beneficiario_novo_associado = novo_associado_name
	novo_link.guarda_unilateral = guarda_unilateral
	if guardiao is not None:
		novo_link.set("é_guardiao_legal", cint(guardiao))
	if sera_registrado is not None:
		novo_link.sera_registrado = cint(sera_registrado)
	novo_link.save(ignore_permissions=True)
	return novo_link.name


def _aplicar_documento_identificacao(resp_doc, resp_item):
	"""Grava o link do documento no Drive, quando o card trouxe um envio novo.

	Fora de ``CAMPOS_RESPONSAVEL`` de propósito: aquele laço grava o que vier, inclusive
	vazio, e um card renderizado sem o campo (qualquer ramo que não seja Filhotes) apagaria
	o link de um documento já enviado.
	"""
	link = (resp_item.get("link_documento_identificacao") or "").strip()
	if not link or link == (resp_doc.get("link_documento_identificacao") or "").strip():
		return

	resp_doc.link_documento_identificacao = link
	resp_doc.documento_identificacao_enviado_em = now_datetime()


def _validar_cpfs_distintos(data, responsaveis_data):
	all_cpfs = []
	associado_cpf = limpar_cpf(data.get("cpf"))
	if associado_cpf:
		all_cpfs.append((associado_cpf, "Novo Associado"))

	for resp_item in responsaveis_data:
		if not resp_item.get("nome_completo") and not resp_item.get("cpf"):
			continue
		resp_cpf = limpar_cpf(resp_item.get("cpf"))
		if resp_cpf:
			resp_label = resp_item.get("nome_completo") or "Responsável"
			all_cpfs.append((resp_cpf, resp_label))

	seen_cpfs = {}
	duplicates = []
	for cpf_digits, label in all_cpfs:
		if cpf_digits in seen_cpfs:
			duplicates.append(label)
			if seen_cpfs[cpf_digits] not in duplicates:
				duplicates.append(seen_cpfs[cpf_digits])
		else:
			seen_cpfs[cpf_digits] = label

	if duplicates:
		nomes = ", ".join(dict.fromkeys(duplicates))
		frappe.throw(_("Os CPFs devem ser distintos. CPFs repetidos encontrados em: {0}.").format(nomes))


@frappe.whitelist()
def update_novo_associado(
	novo_associado_name: str, data: str | dict, responsaveis_data: str | list | None = None
):
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Você precisa estar logado."), frappe.PermissionError)

	responsavel = _responsavel_da_sessao()
	_assert_pode_editar(responsavel, novo_associado_name)

	# Update Novo Associado
	doc = frappe.get_doc("Novo Associado", novo_associado_name)

	# Parse data if it's a string
	if isinstance(data, str):
		data = json.loads(data)

	if isinstance(responsaveis_data, str):
		responsaveis_data = json.loads(responsaveis_data)

	guarda_unilateral = cint(data.get("guarda_unilateral", 0))
	data["guarda_unilateral"] = guarda_unilateral

	# O ramo vem da data de nascimento enviada agora, não do campo gravado: é essa a
	# decisão que vale, e ela precisa acontecer antes de qualquer gravação.
	is_filhotes = _e_filhotes(data.get("data_de_nascimento"))
	if is_filhotes:
		data["tipo_de_registro"] = "Definitivo"
		_validar_regras_filhotes(data, responsaveis_data)

	email_cobranca = (data.get("email_cobranca") or "").strip()
	telefone_cobranca = data.get("telefone_cobranca") or ""

	if not email_cobranca:
		frappe.throw(_("Email de cobrança é obrigatório."))

	if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email_cobranca):
		frappe.throw(_("Email de cobrança inválido."))

	telefone_cobranca_fmt = format_phone(telefone_cobranca)
	phone_digits = "".join(c for c in str(telefone_cobranca_fmt or telefone_cobranca) if c.isdigit())
	if len(phone_digits) not in (12, 13):
		frappe.throw(_("Telefone de cobrança inválido. Informe DDD + número (ex: 11 91234-5678)."))

	data["email_cobranca"] = email_cobranca

	# Allowed fields to update
	allowed_fields = [
		"tipo_de_registro",
		"nome_completo",
		"data_de_nascimento",
		"etnia",
		"sexo",
		"estrangeiro",
		"pais_nascimento",
		"uf_de_nascimento",
		"cidade_de_nascimento",
		"rg",
		"orgao_expedidor",
		"cpf",
		"estado_civil",
		"religiao",
		"escolaridade",
		"profissao",
		"local_de_trabalho",
		"cep",
		"endereco",
		"numero",
		"complemento",
		"estado",
		"cidade",
		"bairro",
		"email",
		"celular",
		"telefone_secundario",
		"email_cobranca",
		"telefone_cobranca",
	]

	for field in allowed_fields:
		if field in data:
			val = data[field]
			if field in ["celular", "telefone_secundario", "telefone_cobranca"]:
				val = format_phone(val)
			doc.set(field, val)

	# Update status and flag indicating data submission
	doc.status = "Fazer Registro"
	doc.dados_para_registro_enviados = 1

	# O job diário recalcula o ramo, mas a ficha da recepção não pode mostrar um ramo
	# incoerente com as regras que acabaram de ser aplicadas neste save.
	ramo = ramo_por_data_de_nascimento(data.get("data_de_nascimento"))
	if ramo:
		doc.ramo = ramo

	if is_filhotes:
		doc.ciente_registro_responsavel_filhotes = 1
		doc.ciente_acompanhamento_filhotes = 1
		doc.data_ciencia_filhotes = now_datetime()

	doc.save(ignore_permissions=True)

	# Update Family Info on ALL Links (Responsavel Vinculo)
	vinculos = frappe.get_all(
		"Responsavel Vinculo",
		filters={"beneficiario_novo_associado": novo_associado_name},
		fields=["name"],
	)
	for v in vinculos:
		frappe.db.set_value("Responsavel Vinculo", v.name, "guarda_unilateral", guarda_unilateral)

	# Update Responsibles
	if responsaveis_data:
		# Validate duplicate CPFs across associado and responsáveis
		_validar_cpfs_distintos(data, responsaveis_data)

		# Responsáveis que já pertencem à família de quem está editando podem ser atualizados
		# por completo; os demais (trazidos pela busca por CPF) só têm campos vazios preenchidos.
		da_familia = {resp_name for resp_name, _vinculo in _responsaveis_da_familia(responsavel)}
		da_familia.add(responsavel)

		for resp_item in responsaveis_data:
			resp_id = (resp_item.get("name") or "").strip()

			# Card sem identificação (placeholder ou limpo pelo usuário): nada a gravar nem a vincular.
			if not resp_item.get("nome_completo") and not resp_item.get("cpf"):
				continue

			if not resp_id:
				# ``Responsavel`` é nomeado por md5(CPF): inserir de novo o CPF de alguém que
				# já existe estouraria DuplicateEntryError e derrubaria o save inteiro.
				candidato = id_por_cpf(resp_item.get("cpf"))
				if candidato and frappe.db.exists("Responsavel", candidato):
					resp_id = candidato

			if resp_id:
				if not frappe.db.exists("Responsavel", resp_id):
					frappe.throw(_("Responsável não encontrado."))

				de_fora = resp_id not in da_familia
				if de_fora:
					_assert_cpf_confere(resp_id, resp_item.get("cpf"))

				resp_doc = frappe.get_doc("Responsavel", resp_id)
				_aplicar_campos_responsavel(resp_doc, resp_item, somente_vazios=de_fora)
			else:
				resp_doc = frappe.new_doc("Responsavel")
				_aplicar_campos_responsavel(resp_doc, resp_item)

			_aplicar_documento_identificacao(resp_doc, resp_item)
			resp_doc.save(ignore_permissions=True)
			_sincronizar_vinculo(novo_associado_name, resp_doc.name, guarda_unilateral, resp_item)
			da_familia.add(resp_doc.name)

	all_vinculos = frappe.get_all(
		"Responsavel Vinculo",
		filters={"beneficiario_novo_associado": novo_associado_name},
		fields=["name", "é_guardiao_legal"],
	)

	if guarda_unilateral:
		guardioes = [v for v in all_vinculos if cint(v.get("é_guardiao_legal")) == 1]
		if len(guardioes) != 1:
			frappe.throw(
				_("Com guarda unilateral, exatamente um responsável deve ser marcado como guardião legal.")
			)
	else:
		for v in all_vinculos:
			if cint(v.get("é_guardiao_legal")) != 1:
				frappe.db.set_value("Responsavel Vinculo", v.name, "é_guardiao_legal", 1)

	_notificar_dados_preenchidos(str(novo_associado_name))

	# A página foi renderizada antes deste save, então quem será registrado só é conhecido
	# agora: o dialog dos próximos passos monta a lista com o que volta daqui.
	return {
		"status": "success",
		"is_filhotes": 1 if is_filhotes else 0,
		"responsaveis_para_registro": _responsaveis_para_registro(novo_associado_name) if is_filhotes else [],
	}


def _responsaveis_para_registro(novo_associado_name: str) -> list[dict]:
	"""Responsáveis marcados para registro neste jovem, para o dialog dos próximos passos."""
	vinculos = frappe.get_all(
		"Responsavel Vinculo",
		filters={"beneficiario_novo_associado": novo_associado_name, "sera_registrado": 1},
		fields=["responsavel"],
	)

	responsaveis = []
	for vinculo in vinculos:
		if not vinculo.responsavel:
			continue
		nome = frappe.db.get_value("Responsavel", vinculo.responsavel, "nome_completo")
		responsaveis.append({"name": vinculo.responsavel, "nome_completo": nome or _("Responsável")})

	return responsaveis


@frappe.whitelist()
@rate_limit(key="registro-busca-responsavel", limit=20, seconds=60)
def buscar_responsavel_por_cpf(novo_associado_name: str, cpf: str):
	"""Dados de um responsável já cadastrado, para reaproveitar no registro de outro jovem.

	Exige CPF completo e válido (sem busca parcial ou por nome) e devolve apenas os campos
	do formulário. Quem vincula o responsável não pode sobrescrever o cadastro dele: essa
	regra é aplicada no save, em ``update_novo_associado``.

	Desfechos previstos da busca (CPF inválido, CPF do próprio jovem, responsável que já
	está no formulário) voltam em ``motivo``, não como exceção: no portal a exceção vira
	uma mensagem solta na página e prende a tela no estado de carregando.
	"""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Você precisa estar logado."), frappe.PermissionError)

	responsavel = _responsavel_da_sessao()
	_assert_pode_editar(responsavel, novo_associado_name)

	if not cpf_valido(cpf):
		return {"encontrado": False, "motivo": "cpf_invalido"}

	digitos = limpar_cpf(cpf)

	cpf_do_jovem = limpar_cpf(frappe.db.get_value("Novo Associado", novo_associado_name, "cpf"))
	if digitos and digitos == cpf_do_jovem:
		return {"encontrado": False, "motivo": "cpf_do_jovem"}

	resp_name = _encontrar_responsavel_por_cpf(digitos)
	if not resp_name:
		return {"encontrado": False, "motivo": "nao_encontrado"}

	ja_vinculado = frappe.db.exists(
		"Responsavel Vinculo",
		{"responsavel": resp_name, "beneficiario_novo_associado": novo_associado_name},
	)
	if ja_vinculado:
		return {
			"encontrado": False,
			"motivo": "ja_vinculado",
			"nome": frappe.db.get_value("Responsavel", resp_name, "nome_completo") or "",
		}

	resp_doc = frappe.get_doc("Responsavel", resp_name)
	dados = _dados_responsavel_para_form(resp_doc)

	return {
		"encontrado": True,
		"motivo": None,
		"name": resp_name,
		# Cadastro anonimizado ao fim da recepção guarda só o nome: a tela avisa e o
		# responsável preenche o restante à mão.
		"vazio": not any(valor for campo, valor in dados.items() if campo != "nome_completo"),
		"dados": dados,
	}


# --------------------------------------------------------------------------------------
# Documentos do ramo Filhotes (Google Drive)
#
# Os arquivos não viram ``File`` do Frappe: o componente de upload do design system posta
# em ``/api/method/upload_file`` com ``method`` apontando para os handlers abaixo, e o
# Frappe então delega a gravação por inteiro (ver ``frappe/handler.py``), expondo o
# conteúdo em ``frappe.local.uploaded_file``. O que fica no banco é só o link do Drive.
# --------------------------------------------------------------------------------------


def _nome_de_arquivo_seguro(texto: str) -> str:
	"""Nome de arquivo sem separador de caminho nem caractere de controle."""
	limpo = re.sub(r"[^\w\s.\-]", "", texto or "", flags=re.UNICODE).strip()
	limpo = re.sub(r"\s+", " ", limpo)
	return limpo[:120] or "documento"


def _ler_upload():
	"""Conteúdo e extensão do arquivo que o Frappe recebeu, já validados."""
	content = frappe.local.uploaded_file
	filename = frappe.local.uploaded_filename or ""

	if not content:
		frappe.throw(_("Nenhum arquivo recebido."))

	if len(content) > TAMANHO_MAXIMO_DOCUMENTO:
		frappe.throw(_("O arquivo deve ter no máximo 10 MB."))

	extensao = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
	if extensao not in EXTENSOES_DOCUMENTO:
		frappe.throw(_("Envie um arquivo PDF, JPG ou PNG."))

	return content, extensao


def _responsavel_registrado_do_jovem(novo_associado_name: str, responsavel_name: str) -> str:
	"""Valida que o responsável indicado é um dos que serão registrados neste jovem.

	Quem preenche pode enviar a declaração do outro responsável: o segundo adulto muitas
	vezes não tem login no portal, e quem preenche já edita os dados dele nesta mesma tela.
	"""
	responsavel_name = (responsavel_name or "").strip()
	if not responsavel_name:
		frappe.throw(_("Responsável não informado."))

	vinculo = frappe.db.get_value(
		"Responsavel Vinculo",
		{"responsavel": responsavel_name, "beneficiario_novo_associado": novo_associado_name},
		["name", "sera_registrado"],
		as_dict=True,
	)
	if not vinculo:
		frappe.throw(_("Responsável não vinculado a este jovem."), frappe.PermissionError)

	if not cint(vinculo.sera_registrado):
		frappe.throw(_("Este responsável não foi marcado para registro."))

	return responsavel_name


@frappe.whitelist()
@rate_limit(key="registro-upload-documento", limit=10, seconds=60)
def upload_documento_identificacao():
	"""Sobe o documento de identificação com foto para o Drive e devolve o link.

	Acontece antes do save do formulário — o card pode ser um responsável que ainda não
	existe na base — então o link volta para a tela e só é amarrado ao ``Responsavel`` em
	``update_novo_associado``. Abandonar o formulário deixa o arquivo órfão no Drive; o
	nome carrega o jovem e o card de origem para a recepção conseguir rastrear.
	"""
	from gris.api.google_workspace.recepcao_drive import (
		assert_feature_enabled,
		upload_bytes_to_folder,
	)

	if frappe.session.user == "Guest":
		frappe.throw(_("Você precisa estar logado."), frappe.PermissionError)

	novo_associado_name = (frappe.form_dict.get("novo_associado") or "").strip()
	responsavel = _responsavel_da_sessao()
	_assert_pode_editar(responsavel, novo_associado_name)

	content, extensao = _ler_upload()
	settings = assert_feature_enabled()
	pasta_id = (settings.pasta_documentos_identificacao_id or "").strip()
	if not pasta_id:
		frappe.throw(_("Pasta de documentos de identificação não configurada."))

	nome_jovem = frappe.db.get_value("Novo Associado", novo_associado_name, "nome_completo") or ""
	# O nome vem do card, porque o upload acontece antes do save e o responsável pode ainda
	# não existir. `_nome_de_arquivo_seguro` é o que impede um nome digitado de virar caminho.
	nome_enviado = (frappe.form_dict.get("responsavel_nome") or "").strip()
	if nome_enviado:
		nome_responsavel = _nome_de_arquivo_seguro(nome_enviado)
	else:
		# Card ainda sem nome preenchido: o jovem e a posição do card mantêm o rastro.
		slot = cint(frappe.form_dict.get("responsavel_slot")) or 1
		nome_responsavel = f"{_nome_de_arquivo_seguro(nome_jovem)} - responsavel {slot}"

	base = _nome_de_arquivo_seguro(f"{ROTULO_DOCUMENTO_IDENTIDADE} - {nome_responsavel}")

	link = upload_bytes_to_folder(
		content=content,
		filename=f"{base}{extensao}",
		mimetype=MIMETYPES_DOCUMENTO[extensao],
		folder_id=pasta_id,
		settings=settings,
		description=f"Documento de identificação enviado no registro de {nome_jovem}",
	)

	return {"file_url": link, "file_name": f"{base}{extensao}"}


@frappe.whitelist()
@rate_limit(key="registro-upload-declaracao", limit=10, seconds=60)
def upload_declaracao_assinada():
	"""Sobe a declaração de idoneidade assinada e grava o link no ``Responsavel``.

	Roda depois do save, então o responsável já existe e o link é gravado na hora.
	"""
	from gris.api.google_workspace.recepcao_drive import (
		assert_feature_enabled,
		upload_bytes_to_folder,
	)

	if frappe.session.user == "Guest":
		frappe.throw(_("Você precisa estar logado."), frappe.PermissionError)

	novo_associado_name = (frappe.form_dict.get("novo_associado") or "").strip()
	responsavel = _responsavel_da_sessao()
	_assert_pode_editar(responsavel, novo_associado_name)

	alvo = _responsavel_registrado_do_jovem(novo_associado_name, frappe.form_dict.get("responsavel"))

	content, extensao = _ler_upload()
	if extensao != ".pdf":
		frappe.throw(_("A declaração assinada deve ser enviada em PDF."))

	settings = assert_feature_enabled()
	pasta_id = (settings.pasta_declaracoes_assinadas_id or "").strip()
	if not pasta_id:
		frappe.throw(_("Pasta de declarações assinadas não configurada."))

	nome_responsavel = frappe.db.get_value("Responsavel", alvo, "nome_completo") or ""
	base = _nome_de_arquivo_seguro(f"{ROTULO_DECLARACAO_ASSINADA} - {nome_responsavel}")

	link = upload_bytes_to_folder(
		content=content,
		filename=f"{base}.pdf",
		mimetype="application/pdf",
		folder_id=pasta_id,
		settings=settings,
		description=f"Declaração de idoneidade assinada de {nome_responsavel}",
	)

	frappe.db.set_value(
		"Responsavel",
		alvo,
		{
			"link_declaracao_idoneidade_assinada": link,
			"declaracao_idoneidade_assinada_em": now_datetime(),
		},
		update_modified=True,
	)

	return {"file_url": link, "file_name": f"{base}.pdf"}


@frappe.whitelist()
@rate_limit(key="registro-gerar-declaracao", limit=10, seconds=60)
def baixar_declaracao_idoneidade(novo_associado_name: str, responsavel_name: str):
	"""Entrega o PDF da declaração pelo próprio GRIS, gerando-a se ainda não existir.

	O arquivo mora num drive de **acesso restrito**: o responsável é usuário de portal e
	nunca vai conseguir abrir o link do Drive: quem tem a credencial é o servidor. Por isso
	o portal baixa por aqui em vez de redirecionar para o Google.

	Síncrono de propósito: o responsável clica em "Baixar declaração" e espera o arquivo.
	Uma fila exigiria polling e um estado intermediário na tela, sem ganho para quem usa.
	"""
	from gris.api.google_workspace import recepcao_drive

	if frappe.session.user == "Guest":
		frappe.throw(_("Você precisa estar logado."), frappe.PermissionError)

	responsavel = _responsavel_da_sessao()
	_assert_pode_editar(responsavel, novo_associado_name)

	alvo = _responsavel_registrado_do_jovem(novo_associado_name, responsavel_name)
	link = recepcao_drive.gerar_declaracao_idoneidade(alvo)
	conteudo, _nome, _mimetype = recepcao_drive.download_file(link)

	nome_responsavel = frappe.db.get_value("Responsavel", alvo, "nome_completo") or ""
	frappe.local.response.filename = (
		_nome_de_arquivo_seguro(f"Declaracao de Idoneidade - {nome_responsavel}") + ".pdf"
	)
	frappe.local.response.filecontent = conteudo
	frappe.local.response.type = "pdf"


@frappe.whitelist()
@rate_limit(key="registro-baixar-documento", limit=30, seconds=60)
def baixar_documento_identificacao(novo_associado_name: str, responsavel_name: str):
	"""Entrega pelo GRIS o documento de identificação que o responsável enviou.

	Mesmo motivo do download da declaração: o drive é de acesso restrito e o link do
	Google não abre para quem preencheu o formulário.
	"""
	from gris.api.google_workspace import recepcao_drive

	if frappe.session.user == "Guest":
		frappe.throw(_("Você precisa estar logado."), frappe.PermissionError)

	responsavel = _responsavel_da_sessao()
	_assert_pode_editar(responsavel, novo_associado_name)

	alvo = (responsavel_name or "").strip()
	if not frappe.db.exists(
		"Responsavel Vinculo",
		{"responsavel": alvo, "beneficiario_novo_associado": novo_associado_name},
	):
		frappe.throw(_("Responsável não vinculado a este jovem."), frappe.PermissionError)

	link = (frappe.db.get_value("Responsavel", alvo, "link_documento_identificacao") or "").strip()
	if not link:
		frappe.throw(_("Nenhum documento de identificação enviado para este responsável."))

	conteudo, nome, mimetype = recepcao_drive.download_file(link)

	frappe.local.response.filename = _nome_de_arquivo_seguro(nome) or "documento"
	frappe.local.response.filecontent = conteudo
	frappe.local.response.type = "pdf" if mimetype == "application/pdf" else "download"
