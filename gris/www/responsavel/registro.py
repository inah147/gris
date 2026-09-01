import json
import re

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint

from gris.api.portal_access import enrich_context
from gris.api.recepcao_mensagens import notificar_dados_preenchidos_no_grupo_recepcao
from gris.api.responsavel_acesso import get_responsavel_do_usuario
from gris.utils.contato import format_phone
from gris.utils.documento import cpf_valido, id_por_cpf, limpar_cpf

# Campos do responsável editáveis pelo formulário, no nome usado pelo frontend.
CAMPOS_RESPONSAVEL = [
	"nome_completo",
	"cpf",
	"rg",
	"orgao_expedidor",
	"data_de_nascimento",
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

	if link_name:
		valores = {"guarda_unilateral": guarda_unilateral}
		if guardiao is not None:
			valores["é_guardiao_legal"] = cint(guardiao)
		frappe.db.set_value("Responsavel Vinculo", link_name, valores)
		return link_name

	novo_link = frappe.new_doc("Responsavel Vinculo")
	novo_link.responsavel = resp_id
	novo_link.beneficiario_novo_associado = novo_associado_name
	novo_link.guarda_unilateral = guarda_unilateral
	if guardiao is not None:
		novo_link.set("é_guardiao_legal", cint(guardiao))
	novo_link.save(ignore_permissions=True)
	return novo_link.name


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

	guarda_unilateral = cint(data.get("guarda_unilateral", 0))
	data["guarda_unilateral"] = guarda_unilateral

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
		if isinstance(responsaveis_data, str):
			responsaveis_data = json.loads(responsaveis_data)

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
	return {"status": "success"}


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
