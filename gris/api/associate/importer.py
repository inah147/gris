import json
import os
import re
import unicodedata
import uuid

import frappe
import pandas as pd
import pdfplumber
from frappe.utils import get_datetime, get_fullname

from gris.api.users.roles import add_user_roles
from gris.utils.documento import id_por_cpf, ids_possiveis_por_cpf, localizar_associado_por_cpf


def _extract_text_from_pdf(pdf_path: str) -> str:
	"""Extrai texto completo do PDF utilizando pdfplumber"""
	text = ""
	with pdfplumber.open(pdf_path) as pdf:
		for page in pdf.pages:
			page_text = page.extract_text()
			if page_text:
				text += page_text + "\n"
	return text


# Valores que o relatório usa para campo vazio.
_VALORES_VAZIOS = {"não se aplica", "não informado", ""}

# Rótulos dos dados pessoais. Cada um casa só no início da linha: o valor de um campo nunca
# vira rótulo de outro. Onde o SIGUE já alternou entre a grafia com e sem acento, o padrão
# aceita as duas — "Secao:" sem acento nunca existiu no PDF e por isso a seção não entrava.
_ROTULOS_PESSOAIS = {
	"Nome": r"Nome",
	"Registro": r"Registro",
	"Endereco_completo": r"Endereço completo",
	"Unidade_escoteira_local": r"Unidade escoteira local",
	"Categoria_1_Funcao": r"Categoria - 1º Função",
	"Funcao_1_Funcao": r"Função - 1º Função",
	"Ramo_1_Funcao": r"Ramo - 1º Função",
	"Nivel_1_Funcao": r"Nível - 1º Função",
	"Fone_Residencial": r"Fone Residencial",
	"Celular": r"Celular",
	"Email": r"E-mail",
	"RG": r"RG",
	"CPF": r"CPF",
	"Data_Nascimento": r"Data Nascimento",
	"Cidade": r"Cidade",
	"Numero_da_UEL": r"N[úu]mero da UEL",
	"Sexo": r"Sexo",
	"Raca_ou_Cor": r"Ra[çc]a ou Cor",
	"Validade_Registro": r"Validade Registro",
	"Secao": r"Se[çc][ãa]o",
}

_ROTULOS_RESPONSAVEL = {
	"Nome_responsavel": r"Nome",
	"Profissao_responsavel": r"Profiss[ãa]o",
	"Escolaridade_responsavel": r"Escolaridade",
	"Telefone_Residencial_responsavel": r"Telefone Residencial",
	"Celular_responsavel": r"Celular",
	"Email_responsavel": r"E-mail",
	"CPF_responsavel": r"CPF",
}

_ID_ESCOTEIROS = re.compile(
	r"^(?:id\s*@\s*escoteiros?|id\s+escoteiros?)\s*:\s*(\S+@escoteiros\.org\.br)",
	re.IGNORECASE | re.MULTILINE,
)
_INICIO_RESPONSAVEL = re.compile(r"^Dados respons[áa]vel\s*$", re.IGNORECASE | re.MULTILINE)
_INICIO_REGISTRO = re.compile(r"^Dados pessoais\s*$", re.IGNORECASE | re.MULTILINE)
_LINHA_COM_ROTULO = re.compile(r"^[^:]{1,40}:")


def _valor_do_rotulo(bloco: str, rotulo: str) -> str:
	"""Valor do primeiro `Rótulo: valor` do bloco, ou "" quando ausente ou vazio."""
	match = re.search(rf"^{rotulo}:[ \t]*([^\n\t]*)", bloco, re.IGNORECASE | re.MULTILINE)
	if not match:
		return ""
	valor = match.group(1).strip()
	return "" if valor.lower() in _VALORES_VAZIOS else valor


def _nome_sem_rotulo(bloco_pessoal: str) -> str:
	"""Nome no layout novo: a primeira linha depois de "Dados pessoais", sem rótulo."""
	for linha in bloco_pessoal.splitlines():
		linha = linha.strip()
		if not linha or _INICIO_REGISTRO.match(linha):
			continue
		return "" if _LINHA_COM_ROTULO.match(linha) else linha
	return ""


def _extract_scout_info(record: str) -> dict | None:
	"""Extrai os dados de um registro ("Dados pessoais" até o próximo) do relatório.

	O registro tem dois blocos com rótulos repetidos (`Nome:`, `CPF:`, `Celular:`, `E-mail:`):
	o do associado e o do responsável. Cada padrão roda só no seu bloco — no layout novo o
	nome do associado vem sem rótulo, e procurar `Nome:` no registro inteiro devolvia o nome
	do responsável.
	"""
	try:
		data = {
			"Nome": "",
			"Registro": "",
			"Endereco_completo": "",
			"Unidade_escoteira_local": "",
			"Categoria_1_Funcao": "",
			"Funcao_1_Funcao": "",
			"Ramo_1_Funcao": "",
			"Nivel_1_Funcao": "",
			"Fone_Residencial": "",
			"Celular": "",
			"Email": "",
			"RG": "",
			"CPF": "",
			"Data_Nascimento": "",
			"Cidade": "",
			"Numero_da_UEL": "",
			"Sexo": "",
			"Raca_ou_Cor": "",
			"Validade_Registro": "",
			"Nome_responsavel": "",
			"Profissao_responsavel": "",
			"Escolaridade_responsavel": "",
			"Telefone_Residencial_responsavel": "",
			"Celular_responsavel": "",
			"Email_responsavel": "",
			"CPF_responsavel": "",
			"id_escoteiro": "",
			"Secao": "",
		}

		divisao = _INICIO_RESPONSAVEL.search(record)
		bloco_pessoal = record[: divisao.start()] if divisao else record
		bloco_responsavel = record[divisao.end() :] if divisao else ""

		for field, rotulo in _ROTULOS_PESSOAIS.items():
			data[field] = _valor_do_rotulo(bloco_pessoal, rotulo)

		# Layout antigo: "Nome: FULANO". Layout novo: o nome sozinho na linha seguinte.
		if not data["Nome"]:
			data["Nome"] = _nome_sem_rotulo(bloco_pessoal)

		id_escoteiro = _ID_ESCOTEIROS.search(bloco_pessoal)
		if id_escoteiro:
			data["id_escoteiro"] = id_escoteiro.group(1).strip()

		# O bloco do responsável vai até o fim do registro, mesmo atravessando a quebra de página.
		for field, rotulo in _ROTULOS_RESPONSAVEL.items():
			data[field] = _valor_do_rotulo(bloco_responsavel, rotulo)

		if data["Nome"] or data["Registro"]:
			return data
		return None

	except Exception:
		frappe.log_error("Erro ao extrair registro do relatório de associados", frappe.get_traceback())
		return None


def _parse_scout_data(text: str) -> list[dict]:
	"""Divide o texto do relatório em registros ("Dados pessoais") e extrai cada um.

	Pedaços sem `Registro:` são o cabeçalho da primeira página ("Retirado por…") e ficam fora.
	"""
	scouts = []
	for rec in re.split(r"(?=^Dados pessoais\s*$)", text, flags=re.IGNORECASE | re.MULTILINE):
		if not _INICIO_REGISTRO.match(rec) or not re.search(r"^Registro:", rec, re.MULTILINE):
			continue
		info = _extract_scout_info(rec)
		if info:
			scouts.append(info)
	return scouts


_CAMPOS_OBRIGATORIOS = {
	"Nome": "nome",
	"Registro": "registro",
	"Categoria_1_Funcao": "categoria da 1ª função",
}


def _identificar_registro(posicao: int, scout: dict) -> str:
	partes = [f"Registro {scout.get('Registro')}" if scout.get("Registro") else f"Associado nº {posicao}"]
	if scout.get("Nome"):
		partes.append(f"({scout['Nome']})")
	return " ".join(partes)


def _validar_extracao(text: str, scouts: list[dict]) -> list[str]:
	"""Problemas que impedem a importação; lista vazia quando o relatório foi lido por inteiro.

	A importação é tudo ou nada: se algum registro sair incompleto, o mais provável é que o
	layout do relatório tenha mudado, e gravar o que deu para ler apagaria dados bons com
	dados errados (já aconteceu de o nome do responsável entrar como nome do associado).
	"""
	if not (text or "").strip():
		return ["O PDF não tem texto selecionável (parece imagem ou documento escaneado)."]
	if not scouts:
		sem_registros = (
			"Nenhum associado encontrado: o layout do relatório não foi reconhecido. "
			"Confira se o arquivo é o Relatório Customizável do SIGUE."
		)
		return [sem_registros]

	problemas = []
	for posicao, scout in enumerate(scouts, start=1):
		faltando = [rotulo for campo, rotulo in _CAMPOS_OBRIGATORIOS.items() if not scout.get(campo)]
		cpf = _clean_digits(scout.get("CPF", ""))
		if not cpf:
			faltando.append("CPF")
		elif len(cpf) != 11:
			faltando.append(f"CPF válido (veio “{scout.get('CPF')}”)")

		identificacao = _identificar_registro(posicao, scout)
		if faltando:
			problemas.append(f"{identificacao}: falta {', '.join(faltando)}.")

		nome_responsavel = scout.get("Nome_responsavel")
		if (
			scout.get("Nome")
			and nome_responsavel
			and _normalize_text(scout["Nome"]) == _normalize_text(nome_responsavel)
		):
			problemas.append(
				f"{identificacao}: o nome do associado saiu igual ao do responsável — "
				"o layout do relatório não foi reconhecido."
			)
	return problemas


_FIELD_LABELS = {
	"telefone": "Telefone",
	"telefone_responsavel_1": "Telefone do Responsável 1",
	"telefone_responsavel_2": "Telefone do Responsável 2",
	"celular": "Celular",
	"email": "E-mail",
	"cpf": "CPF",
	"cpf_responsavel_1": "CPF do Responsável 1",
	"nome_completo": "Nome completo",
}


def _format_error_pt(error_str: str) -> str:
	"""Strip HTML tags and translate known Frappe validation messages to Portuguese."""
	clean = re.sub(r"<[^>]+>", "", str(error_str)).strip()

	m = re.match(
		r"Phone Number\s+(\S+)\s+set in field\s+(\S+)\s+is not valid\.",
		clean,
		re.IGNORECASE,
	)
	if m:
		phone = m.group(1).rstrip(".")
		fieldname = m.group(2).rstrip(".")
		label = _FIELD_LABELS.get(fieldname, fieldname)
		return f"Telefone inválido: {phone} (campo: {label})"

	return clean


def _values_differ(current_value, new_value) -> bool:
	"""
	Compara dois valores considerando None e string vazia como equivalentes.
	Retorna True se os valores são diferentes.
	"""
	# Normalizar valores vazios
	current = current_value if current_value not in [None, ""] else ""
	new = new_value if new_value not in [None, ""] else ""

	# Converter ambos para string para comparação consistente
	return str(current).strip() != str(new).strip()


def _normalize_phone(phone: str) -> str:
	"""Normaliza telefone para formato +55"""
	if not phone:
		return ""
	num = re.sub(r"\D", "", phone)
	if not num:
		return ""
	return f"+55{num}" if not num.startswith("55") else f"+{num}"


def _clean_digits(value: str) -> str:
	if not value:
		return ""
	return re.sub(r"\D", "", str(value))


def _normalize_text(value: str) -> str:
	if not value:
		return ""
	normalized = unicodedata.normalize("NFKD", str(value))
	ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
	return ascii_text.strip().lower()


def _is_beneficiario_category(category: str) -> bool:
	return _normalize_text(category) == "beneficiario"


def _format_row_summary(row) -> str:
	"""Formata os dados do registro para exibição em mensagens de erro."""
	fields = [
		("Nome", row.get("Nome", "")),
		("CPF", row.get("CPF", "")),
		("Registro", row.get("Registro", "")),
		("Categoria", row.get("Categoria_1_Funcao", "")),
		("Função", row.get("Funcao_1_Funcao", "")),
		("Seção", row.get("Secao", "")),
		("Celular", row.get("Celular", "")),
		("Email", row.get("Email", "")),
		("Nome Responsável", row.get("Nome_responsavel", "")),
		("CPF Responsável", row.get("CPF_responsavel", "")),
		(
			"Celular Responsável",
			row.get("Celular_responsavel", "") or row.get("Telefone_Residencial_responsavel", ""),
		),
	]
	parts = [f"{label}: {str(value).strip()}" for label, value in fields if value and str(value).strip()]
	return " | ".join(parts) if parts else "sem dados"


def _extract_responsavel_payload(row) -> dict:
	nome = (row.get("Nome_responsavel", "") or "").strip()
	if nome:
		nome = nome.title()

	email = (row.get("Email_responsavel", "") or "").strip()
	telefone = (row.get("Celular_responsavel", "") or "").strip() or (
		row.get("Telefone_Residencial_responsavel", "") or ""
	).strip()
	telefone = _normalize_phone(telefone)
	cpf_clean = _clean_digits((row.get("CPF_responsavel", "") or "").strip())

	return {
		"nome_completo": nome,
		"email": email,
		"celular": telefone,
		"cpf": cpf_clean,
		"profissao": (row.get("Profissao_responsavel", "") or "").strip(),
		"escolaridade": (row.get("Escolaridade_responsavel", "") or "").strip(),
	}


def _has_responsavel_data(payload: dict) -> bool:
	return bool(
		payload.get("cpf") or payload.get("nome_completo") or payload.get("email") or payload.get("celular")
	)


def _upsert_responsavel(payload: dict) -> tuple[str | None, str]:
	"""Retorna (responsavel_name, action), action em {created, updated, skipped}."""
	cpf = payload.get("cpf")
	if not cpf:
		return None, "skipped"

	responsavel_name = id_por_cpf(cpf)
	if frappe.db.exists("Responsavel", responsavel_name):
		resp_doc = frappe.get_doc("Responsavel", responsavel_name)
		has_changes = False
		for fieldname in ["nome_completo", "email", "celular", "cpf", "profissão", "escolaridade"]:
			payload_key = "profissao" if fieldname == "profissão" else fieldname
			new_value = payload.get(payload_key)
			if not new_value:
				continue
			current_value = resp_doc.get(fieldname)
			if _values_differ(current_value, new_value):
				resp_doc.set(fieldname, new_value)
				has_changes = True

		if has_changes:
			resp_doc.save()
			return resp_doc.name, "updated"
		return resp_doc.name, "skipped"

	new_resp = frappe.new_doc("Responsavel")
	new_resp.nome_completo = payload.get("nome_completo")
	new_resp.email = payload.get("email")
	new_resp.celular = payload.get("celular")
	new_resp.cpf = cpf
	if payload.get("profissao"):
		new_resp.set("profissão", payload.get("profissao"))
	if payload.get("escolaridade"):
		new_resp.escolaridade = payload.get("escolaridade")
	new_resp.insert()
	return new_resp.name, "created"


def _upsert_responsavel_vinculo(responsavel_name: str, associado_name: str, cpf_raw: str = "") -> str:
	"""Retorna action em {created, updated, skipped}.

	Se já existir um vínculo entre o responsável e o Novo Associado correspondente
	(criado na recepção), atualiza o vínculo existente adicionando o Associado.
	"""
	# 1. Buscar vínculo já ligado ao Associado
	existing_link_name = frappe.db.get_value(
		"Responsavel Vinculo",
		{"responsavel": responsavel_name, "beneficiario_associado": associado_name},
		"name",
	)
	if existing_link_name:
		current_guardiao = frappe.db.get_value("Responsavel Vinculo", existing_link_name, "é_guardiao_legal")
		if int(current_guardiao or 0) != 1:
			frappe.db.set_value("Responsavel Vinculo", existing_link_name, "é_guardiao_legal", 1)
			return "updated"
		return "skipped"

	# 2. Buscar vínculo existente via Novo Associado (criado na recepção)
	if cpf_raw:
		na_name = id_por_cpf(cpf_raw)
		na_link_name = frappe.db.get_value(
			"Responsavel Vinculo",
			{"responsavel": responsavel_name, "beneficiario_novo_associado": na_name},
			"name",
		)
		if na_link_name:
			frappe.db.set_value(
				"Responsavel Vinculo",
				na_link_name,
				{"beneficiario_associado": associado_name, "é_guardiao_legal": 1},
			)
			return "updated"

	# 3. Criar novo vínculo
	new_link = frappe.new_doc("Responsavel Vinculo")
	new_link.responsavel = responsavel_name
	new_link.beneficiario_associado = associado_name
	new_link.é_guardiao_legal = 1
	new_link.insert()
	return "created"


def _upsert_portal_user(
	email: str,
	nome_completo: str,
	associate_doc,
	responsavel_name: str | None = None,
) -> str:
	"""Cria um usuário Frappe para o email informado se ainda não existir e garante
	que Responsavel.email aponte para esse email (vínculo exigido pelo portal).

	Retorna action em {created, skipped}.
	"""
	if not email:
		return "skipped"

	action = "skipped"
	if not frappe.db.exists("User", email):
		name_parts = (nome_completo or "").strip().split(" ")
		first_name = name_parts[0] if name_parts else email
		last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

		registro = (getattr(associate_doc, "registro", "") or "").split("-")[0]
		role_profile_name = "Responsavel" if responsavel_name else "Beneficiário"

		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": first_name,
				"last_name": last_name,
				"new_password": f"gepim{registro}" if registro else None,
				"send_welcome_email": 1,
				"role_profile_name": role_profile_name,
				"reset_password_key": str(uuid.uuid4()),
				"enabled": 1,
			}
		)
		if responsavel_name:
			user.append("roles", {"role": "Responsavel"})
		user.insert()
		action = "created"
	else:
		# Usuário já existe — apenas concede (de forma aditiva) o papel
		# Responsavel. NÃO alteramos role_profile_name (Função) nem usamos
		# User.save(): ambos fazem o Frappe repopular a lista de papéis a partir
		# do perfil, removendo acessos concedidos manualmente ao usuário.
		if responsavel_name:
			add_user_roles(email, ["Responsavel"])

	# Garante que Responsavel.email aponte para este usuário (exigido pelo portal).
	if responsavel_name and frappe.db.exists("Responsavel", responsavel_name):
		current_email = frappe.db.get_value("Responsavel", responsavel_name, "email")
		if current_email != email:
			frappe.db.set_value("Responsavel", responsavel_name, "email", email)

	return action


def _registrar_log_importacao(path_pdf: str, results: dict) -> None:
	"""Persiste uma linha de log com o resultado da importação de associados."""
	resumo = {
		"total": results.get("total", 0),
		"created": results.get("created", 0),
		"updated": results.get("updated", 0),
		"skipped": results.get("skipped", 0),
		"errors": results.get("errors", 0),
		"error_details": results.get("error_details", []),
		"responsavel_created": results.get("responsavel_created", 0),
		"responsavel_updated": results.get("responsavel_updated", 0),
		"responsavel_skipped": results.get("responsavel_skipped", 0),
		"vinculo_created": results.get("vinculo_created", 0),
		"vinculo_updated": results.get("vinculo_updated", 0),
		"vinculo_skipped": results.get("vinculo_skipped", 0),
		"usuario_created": results.get("usuario_created", 0),
		"usuario_skipped": results.get("usuario_skipped", 0),
	}

	log_doc = frappe.get_doc(
		{
			"doctype": "Log Importacao de Associados",
			"arquivo_origem": path_pdf,
			"sucesso": 1 if int(results.get("errors", 0) or 0) == 0 else 0,
			"total_registros": int(results.get("total", 0) or 0),
			"registros_criados": int(results.get("created", 0) or 0),
			"registros_atualizados": int(results.get("updated", 0) or 0),
			"registros_sem_alteracao": int(results.get("skipped", 0) or 0),
			"total_erros": int(results.get("errors", 0) or 0),
			"detalhes_resultado": json.dumps(resumo, ensure_ascii=False),
		}
	)
	log_doc.insert()


def ultima_importacao_associados() -> dict | None:
	"""Quando e por quem os associados foram atualizados pela última vez (importação do PDF).

	Lê pelo `frappe.db` de propósito: quem consulta a lista não tem permissão no Log, e o que
	sai daqui é só a data e o nome de quem importou.
	"""
	log = frappe.db.get_value(
		"Log Importacao de Associados",
		{},
		["data_importacao", "owner"],
		order_by="data_importacao desc",
		as_dict=True,
	)
	if not log or not log.data_importacao:
		return None

	quando = get_datetime(log.data_importacao)
	return {
		"quando": quando.strftime("%d/%m/%Y às %H:%M"),
		"por": get_fullname(log.owner) if log.owner else "",
	}


@frappe.whitelist()
def parse_associates_report(path_pdf: str) -> dict:
	"""
	Parse PDF report and insert/update Associado records.
	Returns a summary of the import operation.
	"""
	# Converter o file_url para o caminho físico do arquivo
	site_path = frappe.get_site_path()
	file_path = None

	if path_pdf.startswith("/files/"):
		file_path = os.path.join(site_path, "public", path_pdf.lstrip("/"))
	elif path_pdf.startswith("/private/") or path_pdf.startswith("/private/files/"):
		file_path = os.path.join(site_path, path_pdf.lstrip("/"))
	else:
		# Assume que já é um caminho completo
		file_path = path_pdf

	if not os.path.exists(file_path):
		frappe.throw(f"Arquivo não encontrado: {path_pdf}")

	text = _extract_text_from_pdf(file_path)
	scouts = _parse_scout_data(text)

	# Tudo ou nada: com qualquer problema de leitura nada é gravado — nem o Log, que marca a
	# data da última atualização (carimbo da lista e lembrete de WhatsApp).
	problemas = _validar_extracao(text, scouts)
	if problemas:
		return {"status": "invalido", "total": len(scouts), "validation_errors": problemas}

	df = pd.DataFrame(scouts)

	# CPF pode conter zeros à esquerda, manter string
	for cpf_col in ["CPF", "CPF_responsavel"]:
		if cpf_col in df.columns:
			df[cpf_col] = df[cpf_col].astype(str)

	# Estatísticas da importação
	results = {
		"status": "ok",
		"total": len(df),
		"created": 0,
		"updated": 0,
		"skipped": 0,
		"errors": 0,
		"error_details": [],
		"responsavel_created": 0,
		"responsavel_updated": 0,
		"responsavel_skipped": 0,
		"vinculo_created": 0,
		"vinculo_updated": 0,
		"vinculo_skipped": 0,
		"usuario_created": 0,
		"usuario_skipped": 0,
	}

	# A reconciliação por pessoa (`on_associado_atualizado`) fica desligada durante o
	# laço: são centenas de gravações, e a rotina em lote no fim faz o mesmo trabalho
	# enxergando o grupo inteiro — inclusive encerrando quem saiu da seção, que o
	# caminho por pessoa não tem como saber.
	frappe.flags.gris_sync_secoes = True
	try:
		_importar_linhas(df, results)
	finally:
		frappe.flags.gris_sync_secoes = False

	# A importação é o único momento em que `secao` e `funcao` mudam em lote; é
	# aqui que as seções viram áreas do organograma.
	results["secoes"] = _sincronizar_secoes_do_organograma()

	_registrar_log_importacao(path_pdf, results)

	return results


def _importar_linhas(df, results: dict) -> None:
	"""Cria ou atualiza um `Associado` por linha do relatório."""
	for idx, row in df.iterrows():
		cpf = None
		try:
			cpf = row.get("CPF", "").strip()
			if not cpf:
				results["errors"] += 1
				results["error_details"].append(f"Linha {idx + 1}: CPF não encontrado")
				continue

			registro_ueb = row.get("Registro", "").strip()

			# Verificar se o associado já existe. O identificador sai do CPF (md5 dos
			# dígitos), mas cadastros antigos foram nomeados pelo CPF pontuado e o registro
			# na UEB é o último recurso — as três tentativas moram em
			# ``localizar_associado_por_cpf``.
			existing_name = localizar_associado_por_cpf(cpf, registro_ueb)
			existing = bool(existing_name)

			# Mapear campos do PDF para o doctype Associado
			# Mantemos CPF cru no associate_data para que o save() do doctype gere o hash corretamente
			nome_completo = row.get("Nome", "").strip()
			if nome_completo:
				nome_completo = nome_completo.title()

			telefone = row.get("Celular", "").strip() or row.get("Fone_Residencial", "").strip()
			telefone = _normalize_phone(telefone)

			associate_data = {
				"doctype": "Associado",
				"cpf": cpf,
				"nome_completo": nome_completo,
				"registro": row.get("Registro", "").strip(),
				"email": row.get("Email", "").strip(),
				"telefone": telefone,
				"data_de_nascimento": _parse_date(row.get("Data_Nascimento", "")),
				"sexo": _parse_sexo(row.get("Sexo", "")),
				"etnia": _parse_etnia(row.get("Raca_ou_Cor", "")),
				"validade_registro": _parse_date(row.get("Validade_Registro", "")),
				"categoria": row.get("Categoria_1_Funcao", "").strip(),
				"funcao": row.get("Funcao_1_Funcao", "").strip(),
				"secao": row.get("Secao", "").strip(),
				"ramo": _parse_ramo(row.get("Ramo_1_Funcao", "")),
				"id_escoteiros": row.get("id_escoteiro", "").strip(),
			}

			# Adicionar dados do responsável se existirem
			if row.get("Nome_responsavel"):
				nome_resp = row.get("Nome_responsavel", "").strip()
				if nome_resp:
					nome_resp = nome_resp.title()

				tel_resp = (
					row.get("Celular_responsavel", "").strip()
					or row.get("Telefone_Residencial_responsavel", "").strip()
				)
				tel_resp = _normalize_phone(tel_resp)

				# Para escotistas (não-beneficiários), telefone inválido fica em branco
				# sem gerar erro — o PDF pode conter números sem DDD ou incompletos
				if tel_resp and not _is_beneficiario_category(row.get("Categoria_1_Funcao", "")):
					num_digits = re.sub(r"\D", "", tel_resp)
					if len(num_digits) not in (12, 13):
						tel_resp = ""

				associate_data.update(
					{
						"nome_responsavel_1": nome_resp,
						"telefone_responsavel_1": tel_resp,
						"email_responsavel_1": row.get("Email_responsavel", "").strip(),
						"cpf_responsavel_1": row.get("CPF_responsavel", "").strip(),
					}
				)

			associado_name = None

			if existing:
				# Atualizar registro existente apenas se houver diferenças
				doc = frappe.get_doc("Associado", existing_name)
				has_changes = False

				for key, value in associate_data.items():
					if key != "doctype" and value:  # Apenas verificar campos com valor
						current_value = getattr(doc, key, None)

						# Special handling for CPF comparison (stored as hash vs input as raw).
						# Aceita as convenções antigas de hash para não marcar alteração em
						# cadastro que só tem o nome no formato velho.
						if key == "cpf":
							if current_value in ids_possiveis_por_cpf(cpf):
								continue  # Hash matches raw input, no change

						# Special handling for CPF Responsavel comparison
						if key == "cpf_responsavel_1" and value:
							if current_value in ids_possiveis_por_cpf(value):
								continue

						# Comparar valores, considerando None e string vazia como equivalentes
						if _values_differ(current_value, value):
							setattr(doc, key, value)
							has_changes = True

				if has_changes:
					doc.save()
					results["updated"] += 1
				else:
					# Registro já existe e não tem alterações
					results["skipped"] += 1
				associado_name = doc.name
			else:
				try:
					# Criar novo registro
					doc = frappe.get_doc(associate_data)
					doc.insert()
					results["created"] += 1
					associado_name = doc.name
				except frappe.DuplicateEntryError:
					# Se falhar por nome duplicado mas não achou por CPF/Registro, tenta recuperar e atualizar
					# O nome é autogerado? Se sim, pode ser colisão. Se for manual, usuário mandou.
					# Vamos tentar encontrar o doc que causou conflito
					frappe.clear_messages()

					# Se realmente for duplicata de nome e não achamos antes,
					# pode ser que o CPF estava diferente ou em branco no banco
					# Vamos tentar achar pelo nome completo se possível, ou apenas logar
					dup_candidates = frappe.get_all(
						"Associado", filters={"nome_completo": associate_data.get("nome_completo")}, limit=1
					)

					if dup_candidates:
						doc = frappe.get_doc("Associado", dup_candidates[0].name)
						# Repetir lógica de update
						has_changes = False
						for key, value in associate_data.items():
							if key != "doctype" and value:
								current_value = getattr(doc, key, None)

								# Special handling for CPF comparison (stored as hash vs input as raw)
								if key == "cpf":
									if current_value in ids_possiveis_por_cpf(cpf):
										continue  # Hash matches raw input, no change

								# Special handling for CPF Responsavel comparison
								if key == "cpf_responsavel_1" and value:
									if current_value in ids_possiveis_por_cpf(value):
										continue

								if _values_differ(current_value, value):
									setattr(doc, key, value)
									has_changes = True

						if has_changes:
							doc.save()
							results["updated"] += 1
						else:
							results["skipped"] += 1
						associado_name = doc.name
					else:
						# Se não achou candidato, então é um erro real de chave
						raise

			# Para beneficiários, sincronizar Responsavel e Responsavel Vinculo
			if associado_name and _is_beneficiario_category(associate_data.get("categoria")):
				responsavel_payload = _extract_responsavel_payload(row)
				if _has_responsavel_data(responsavel_payload):
					_resp_name_for_user = None
					try:
						responsavel_name, responsavel_action = _upsert_responsavel(responsavel_payload)
						_resp_name_for_user = responsavel_name
						results[f"responsavel_{responsavel_action}"] += 1

						if responsavel_name:
							vinculo_action = _upsert_responsavel_vinculo(
								responsavel_name, associado_name, cpf
							)
							results[f"vinculo_{vinculo_action}"] += 1
						else:
							results["vinculo_skipped"] += 1
					except Exception as e:
						frappe.clear_messages()
						results["errors"] += 1
						error_msg = (
							f"CPF {cpf or 'desconhecido'}: erro ao sincronizar responsável/vínculo"
							f" - {_format_error_pt(str(e))}"
							f"\n  Dados do registro: {_format_row_summary(row)}"
						)
						results["error_details"].append(f"Linha {idx + 1} - {error_msg}")
						frappe.log_error(f"Erro sync responsavel linha {idx + 1}", str(e))

					# Criar usuário: usa email do responsável ou, na ausência, email do associado
					try:
						email_for_user = responsavel_payload.get("email") or associate_data.get("email") or ""
						nome_for_user = (
							responsavel_payload.get("nome_completo")
							or associate_data.get("nome_completo")
							or ""
						)
						usuario_action = _upsert_portal_user(
							email_for_user, nome_for_user, doc, _resp_name_for_user
						)
						results[f"usuario_{usuario_action}"] += 1
					except Exception as e:
						frappe.clear_messages()
						results["errors"] += 1
						error_msg = (
							f"CPF {cpf or 'desconhecido'}: erro ao criar usuário"
							f" - {_format_error_pt(str(e))}"
							f"\n  Dados do registro: {_format_row_summary(row)}"
						)
						results["error_details"].append(f"Linha {idx + 1} - {error_msg}")
						frappe.log_error(f"Erro criação usuário linha {idx + 1}", str(e))

		except Exception as e:
			frappe.clear_messages()
			frappe.log_error(f"Erro importação linha {idx + 1}", str(e))
			results["errors"] += 1
			error_msg = (
				f"CPF {cpf or 'desconhecido'}: {_format_error_pt(str(e))}"
				f"\n  Dados do registro: {_format_row_summary(row)}"
			)
			results["error_details"].append(f"Linha {idx + 1} - {error_msg}")


def _sincronizar_secoes_do_organograma() -> dict:
	"""Reconcilia seções e áreas; uma falha aqui não invalida a importação."""
	from gris.api.gestao_adultos.secoes import sincronizar_secoes

	try:
		return sincronizar_secoes()
	except Exception as e:  # pragma: no cover - depende do estado do cadastro
		frappe.log_error("Erro ao sincronizar seções do organograma", str(e))
		return {"erro": str(e)}


def _parse_date(date_str: str) -> str:
	"""Converte string de data do formato DD/MM/YYYY para YYYY-MM-DD"""
	if not date_str or date_str.strip() == "":
		return ""
	try:
		date_str = date_str.strip()
		if "/" in date_str:
			parts = date_str.split("/")
			if len(parts) == 3:
				return f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
		return date_str
	except Exception:
		return ""


def _parse_sexo(sexo_str: str) -> str:
	"""Normaliza o valor de sexo para o formato do doctype"""
	sexo = sexo_str.strip().lower()
	if "masculino" in sexo or sexo == "m":
		return "Masculino"
	elif "feminino" in sexo or sexo == "f":
		return "Feminino"
	return ""


def _parse_etnia(etnia_str: str) -> str:
	"""Normaliza o valor de etnia para o formato do doctype"""
	etnia = etnia_str.strip().lower()
	mapping = {
		"amarela": "Amarela",
		"branca": "Branca",
		"indígena": "Indígena",
		"indigena": "Indígena",
		"parda": "Parda",
		"preta": "Preta",
	}
	return mapping.get(etnia, "")


def _parse_ramo(ramo_str: str) -> str:
	"""Normaliza o valor de ramo para o formato do doctype"""
	ramo = ramo_str.strip().lower()
	mapping = {
		"filhotes": "Filhotes",
		"lobinho": "Lobinho",
		"escoteiro": "Escoteiro",
		"sênior": "Sênior",
		"senior": "Sênior",
		"pioneiro": "Pioneiro",
	}
	return mapping.get(ramo, "Não se aplica")


def converter_mes_para_numero(mes_nome):
	"""Converte nome do mês para número"""
	meses = {
		"janeiro": "01",
		"fevereiro": "02",
		"março": "03",
		"abril": "04",
		"maio": "05",
		"junho": "06",
		"julho": "07",
		"agosto": "08",
		"setembro": "09",
		"outubro": "10",
		"novembro": "11",
		"dezembro": "12",
	}
	return meses.get(mes_nome.lower(), "")
