import hashlib
import json
import os
import re
import unicodedata
import uuid

import frappe
import pandas as pd
import pdfplumber


def _extract_text_from_pdf(pdf_path: str) -> str:
	"""Extrai texto completo do PDF utilizando pdfplumber"""
	text = ""
	with pdfplumber.open(pdf_path) as pdf:
		for page in pdf.pages:
			page_text = page.extract_text()
			if page_text:
				text += page_text + "\n"
	return text


def _extract_scout_info(record: str) -> dict | None:
	"""Extrai informações de um registro do PDF"""
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

		patterns = {
			"Nome": r"Nome:\s*([^\n\t]+)",
			"Registro": r"Registro:\s*([^\n\t]+)",
			"Endereco_completo": r"Endereço completo:\s*([^\n\t]+)",
			"Unidade_escoteira_local": r"Unidade escoteira local:\s*([^\n\t]+)",
			"Categoria_1_Funcao": r"Categoria - 1º Função:\s*([^\n\t]+)",
			"Funcao_1_Funcao": r"Função - 1º Função:\s*([^\n\t]+)",
			"Ramo_1_Funcao": r"Ramo - 1º Função:\s*([^\n\t]+)",
			"Nivel_1_Funcao": r"Nível - 1º Função:\s*([^\n\t]+)",
			"Fone_Residencial": r"Fone Residencial:\s*([^\n\t]+)",
			"Celular": r"Celular:\s*([^\n\t]+)",
			"Email": r"E-mail:\s*([^\n\t]+)",
			"RG": r"RG:\s*([^\n\t]+)",
			"CPF": r"CPF:\s*([^\n\t]+)",
			"Data_Nascimento": r"Data Nascimento:\s*([^\n\t]+)",
			"Cidade": r"Cidade:\s*([^\n\t]+)",
			"Numero_da_UEL": r"Numero da UEL:\s*([^\n\t]+)",
			"Sexo": r"Sexo:\s*([^\n\t]+)",
			"Raca_ou_Cor": r"Raça ou Cor:\s*([^\n\t]+)",
			"Validade_Registro": r"Validade Registro:\s*([^\n\t]+)",
			"id_escoteiro": r"(?:id\s*@\s*escoteiros?|id\s+escoteiros?)\s*:\s*([^\s\n\t]+@escoteiros\.org\.br)",
			"Secao": r"Secao:\s*([^\n\t]+)",
		}

		for field, pattern in patterns.items():
			match = re.search(pattern, record, re.IGNORECASE)
			if match:
				value = match.group(1).strip()
				if value not in ["Não se aplica", "Não informado", ""]:
					data[field] = value

		responsible_section = re.search(r"Dados responsável\n(.*?)(?=\n\n|\nRetirado|$)", record, re.DOTALL)
		if responsible_section:
			responsible_text = responsible_section.group(1)
			responsible_patterns = {
				"Nome_responsavel": r"Nome:\s*([^\n\t]+)",
				"Profissao_responsavel": r"Profissão:\s*([^\n\t]+)",
				"Escolaridade_responsavel": r"Escolaridade:\s*([^\n\t]+)",
				"Telefone_Residencial_responsavel": r"Telefone Residencial:\s*([^\n\t]+)",
				"Celular_responsavel": r"Celular:\s*([^\n\t]+)",
				"Email_responsavel": r"E-mail:\s*([^\n\t]+)",
				"CPF_responsavel": r"CPF:\s*([^\n\t]+)",
			}
			for field, pattern in responsible_patterns.items():
				match = re.search(pattern, responsible_text, re.IGNORECASE)
				if match:
					value = match.group(1).strip()
					if value not in ["Não informado", ""]:
						data[field] = value

		if data["Nome"]:
			return data
		return None

	except Exception as e:
		print(f"Erro no processamento do registro: {e}")
		return None


def _parse_scout_data(text: str) -> list[dict]:
	"""Processa texto completo do PDF dividindo por registros e extraindo dados"""
	records = re.split(r"(?=Dados pessoais\nNome:)", text)
	records = [r.strip() for r in records if r.strip() and "Nome:" in r]
	scouts = []
	for rec in records:
		info = _extract_scout_info(rec)
		if info:
			scouts.append(info)
	return scouts


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
		("Celular Responsável", row.get("Celular_responsavel", "") or row.get("Telefone_Residencial_responsavel", "")),
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

	responsavel_name = hashlib.md5(cpf.encode("utf-8")).hexdigest()
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
		cpf_clean = re.sub(r"\D", "", cpf_raw)
		na_name = hashlib.md5(cpf_clean.encode("utf-8")).hexdigest()
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
		# Usuário já existe — garante que o papel Responsavel está atribuído, se aplicável.
		if responsavel_name:
			user_doc = frappe.get_doc("User", email)
			has_changes = False
			if user_doc.role_profile_name != "Responsavel":
				user_doc.role_profile_name = "Responsavel"
				has_changes = True
			existing_roles = {r.role for r in user_doc.roles}
			if "Responsavel" not in existing_roles:
				user_doc.append("roles", {"role": "Responsavel"})
				has_changes = True
			if has_changes:
				user_doc.save(ignore_permissions=True)

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
	df = pd.DataFrame(scouts)

	# CPF pode conter zeros à esquerda, manter string
	for cpf_col in ["CPF", "CPF_responsavel"]:
		if cpf_col in df.columns:
			df[cpf_col] = df[cpf_col].astype(str)

	# Estatísticas da importação
	results = {
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
		"usuario_skipped": 0
	}

	# Processar cada registro
	for idx, row in df.iterrows():
		cpf = None
		try:
			cpf = row.get("CPF", "").strip()
			if not cpf:
				results["errors"] += 1
				results["error_details"].append(f"Linha {idx + 1}: CPF não encontrado")
				continue

			# Calcular hash do CPF para busca (padrao do doctype Associado)
			cpf_hash = hashlib.md5(cpf.encode("utf-8")).hexdigest()

			# Verificar se o associado já existe (buscar pelo CPF como filtro)
			# Também deve buscar pelo nome, já que o ID é baseado no nome/hash
			filters = {"cpf": cpf_hash}
			existing_docs = frappe.get_all("Associado", filters=filters, limit=1)

			registro_ueb = row.get("Registro", "").strip()
			if not existing_docs and registro_ueb:
				# Tentar buscar pelo registro UEB se não achou por CPF
				existing_docs = frappe.get_all("Associado", filters={"registro": registro_ueb}, limit=1)

			existing = len(existing_docs) > 0

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
				doc = frappe.get_doc("Associado", existing_docs[0].name)
				has_changes = False

				for key, value in associate_data.items():
					if key != "doctype" and value:  # Apenas verificar campos com valor
						current_value = getattr(doc, key, None)

						# Special handling for CPF comparison (stored as hash vs input as raw)
						if key == "cpf":
							if current_value == cpf_hash:
								continue  # Hash matches raw input, no change

						# Special handling for CPF Responsavel comparison
						if key == "cpf_responsavel_1" and value:
							resp_hash = hashlib.md5(value.encode("utf-8")).hexdigest()
							if current_value == resp_hash:
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
									if current_value == cpf_hash:
										continue  # Hash matches raw input, no change

								# Special handling for CPF Responsavel comparison
								if key == "cpf_responsavel_1" and value:
									resp_hash = hashlib.md5(value.encode("utf-8")).hexdigest()
									if current_value == resp_hash:
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
							vinculo_action = _upsert_responsavel_vinculo(responsavel_name, associado_name, cpf)
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
						nome_for_user = responsavel_payload.get("nome_completo") or associate_data.get("nome_completo") or ""
						usuario_action = _upsert_portal_user(email_for_user, nome_for_user, doc, _resp_name_for_user)
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

	# Commit das alterações
	_registrar_log_importacao(path_pdf, results)
	frappe.db.commit()

	return results


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
