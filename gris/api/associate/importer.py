import os
import re

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
	results = {"total": len(df), "created": 0, "updated": 0, "skipped": 0, "errors": 0, "error_details": []}

	# Processar cada registro
	for idx, row in df.iterrows():
		cpf = None
		try:
			cpf = row.get("CPF", "").strip()
			if not cpf:
				results["errors"] += 1
				results["error_details"].append(f"Linha {idx + 1}: CPF não encontrado")
				continue

			# Verificar se o associado já existe (buscar pelo CPF como filtro)
			existing_docs = frappe.get_all("Associado", filters={"cpf": cpf}, limit=1)
			existing = len(existing_docs) > 0

			# Mapear campos do PDF para o doctype Associado
			associate_data = {
				"doctype": "Associado",
				"cpf": cpf,
				"nome_completo": row.get("Nome", "").strip(),
				"registro": row.get("Registro", "").strip(),
				"email": row.get("Email", "").strip(),
				"telefone": row.get("Celular", "").strip() or row.get("Fone_Residencial", "").strip(),
				"data_de_nascimento": _parse_date(row.get("Data_Nascimento", "")),
				"sexo": _parse_sexo(row.get("Sexo", "")),
				"etnia": _parse_etnia(row.get("Raca_ou_Cor", "")),
				"validade_registro": _parse_date(row.get("Validade_Registro", "")),
				"categoria": row.get("Categoria_1_Funcao", "").strip(),
				"funcao": row.get("Funcao_1_Funcao", "").strip(),
				"ramo": _parse_ramo(row.get("Ramo_1_Funcao", "")),
			}

			# Adicionar dados do responsável se existirem
			if row.get("Nome_responsavel"):
				associate_data.update(
					{
						"nome_responsavel_1": row.get("Nome_responsavel", "").strip(),
						"telefone_responsavel_1": row.get("Celular_responsavel", "").strip()
						or row.get("Telefone_Residencial_responsavel", "").strip(),
						"email_responsavel_1": row.get("Email_responsavel", "").strip(),
						"cpf_responsavel_1": row.get("CPF_responsavel", "").strip(),
					}
				)

			if existing:
				# Atualizar registro existente apenas se houver diferenças
				doc = frappe.get_doc("Associado", existing_docs[0].name)
				has_changes = False

				for key, value in associate_data.items():
					if key != "doctype" and value:  # Apenas verificar campos com valor
						current_value = getattr(doc, key, None)
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
			else:
				# Criar novo registro
				doc = frappe.get_doc(associate_data)
				doc.insert()
				results["created"] += 1

		except frappe.DuplicateEntryError:
			# Duplicata detectada - verificar se realmente não tem alterações
			results["skipped"] += 1
		except Exception as e:
			results["errors"] += 1
			error_msg = f"CPF {cpf or 'desconhecido'}: {type(e).__name__}"
			results["error_details"].append(f"Linha {idx + 1} - {error_msg}")
			# Log de erro mais curto para não exceder o limite
			frappe.log_error(
				title=f"Import Error: {error_msg[:100]}", message=f"Linha {idx + 1}\nCPF: {cpf}\nErro: {e!s}"
			)

	# Commit das alterações
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
