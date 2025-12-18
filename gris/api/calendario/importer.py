import os
import re

import frappe
import pandas as pd
import pdfplumber


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


def processar_datas(mes_ano_str, dias_str):
	"""
	Processa as datas do evento e retorna (data_inicio, data_fim) em formato YYYY-MM-DD
	"""
	partes = mes_ano_str.split("/")
	mes_nome = partes[0]
	ano = partes[1]

	mes_num = converter_mes_para_numero(mes_nome)

	if " e " in dias_str:
		dias = dias_str.split(" e ")
		dia_inicio = dias[0].strip().zfill(2)
		dia_fim = dias[1].strip().zfill(2)
	else:
		dia_inicio = dias_str.strip().zfill(2)
		dia_fim = dia_inicio

	# Formatar as datas em YYYY-MM-DD para o Frappe
	data_inicio = f"{ano}-{mes_num}-{dia_inicio}"
	data_fim = f"{ano}-{mes_num}-{dia_fim}"

	return data_inicio, data_fim


def extract_events_from_pdf_file(pdf_path):
	"""
	Extrai eventos de um relatório PAXTU em PDF e retorna um DataFrame.
	"""
	pdf_text = ""
	with pdfplumber.open(pdf_path) as pdf:
		for page in pdf.pages:
			pdf_text += page.extract_text() + "\n"

	return extract_events_from_text(pdf_text)


def extract_events_from_text(content):
	"""
	Extrai eventos do conteúdo em texto e retorna um DataFrame.
	"""
	lines = content.split("\n")

	eventos = []
	secao_atual = None
	mes_ano_atual = None
	dias_evento = None
	atividade_atual = None
	local_atual = None

	# Palavras-chave que indicam cabeçalhos a ignorar
	headers_ignore = [
		"Escoteiros do Brasil",
		"PAXTU - Sistema de Informações e Gerenciamento de Unidades Escoteiras",
		"CALENDÁRIO DE ATIVIDADES POR SEÇÃO",
		"Retirado por",
		"registro",
	]

	for line in lines:
		line_stripped = line.strip()

		# Pula linhas vazias
		if not line_stripped:
			continue

		# Pula cabeçalhos genéricos
		if any(header in line_stripped for header in headers_ignore):
			continue

		# Verifica se é um cabeçalho de seção
		if ":" not in line_stripped:
			if not re.match(r"\w+/\d{4}", line_stripped) and not re.match(
				r"^\d+(\s+e\s+\d+)?$", line_stripped
			):
				if not any(word in line_stripped for word in ["Atividade", "Local", "Grupo Escoteiro"]):
					secao_atual = line_stripped
					continue

		# Verifica se é mês/ano (formato: Mês/Ano)
		if re.match(r"^\w+/\d{4}", line_stripped):
			mes_ano_atual = line_stripped
			continue

		# Verifica se são dias do evento
		if re.match(r"^\d+(\s+e\s+\d+)?$", line_stripped):
			dias_evento = line_stripped
			continue

		# Extrai atividade
		if line_stripped.startswith("Atividade:"):
			atividade_atual = line_stripped.replace("Atividade:", "").strip()
			continue

		# Extrai local
		if line_stripped.startswith("Local:"):
			local_atual = line_stripped.replace("Local:", "").strip()
			continue

		# Se encontramos grupo escoteiro, finalizamos um evento
		if line_stripped.startswith("Grupo Escoteiro:"):
			if secao_atual and mes_ano_atual and dias_evento and atividade_atual:
				# Processar as datas
				data_inicio, data_fim = processar_datas(mes_ano_atual, dias_evento)

				eventos.append(
					{
						"secao": secao_atual,
						"inicio": data_inicio,
						"termino": data_fim,
						"atividade": atividade_atual,
						"local": local_atual if local_atual else "Não especificado",
					}
				)
			# Reset para próximo evento
			dias_evento = None
			atividade_atual = None
			local_atual = None

	return pd.DataFrame(eventos)


@frappe.whitelist()
def parse_calendario_report(path_pdf: str) -> dict:
	"""
	Parse PDF report and insert/update Calendario records.
	Returns a summary of the import operation.
	"""
	site_path = frappe.get_site_path()
	file_path = None

	if path_pdf.startswith("/files/"):
		file_path = os.path.join(site_path, "public", path_pdf.lstrip("/"))
	elif path_pdf.startswith("/private/") or path_pdf.startswith("/private/files/"):
		file_path = os.path.join(site_path, path_pdf.lstrip("/"))
	else:
		file_path = path_pdf

	if not os.path.exists(file_path):
		frappe.throw(f"Arquivo não encontrado: {path_pdf}")

	eventos_df = extract_events_from_pdf_file(file_path)

	results = {
		"total": len(eventos_df),
		"created": 0,
		"updated": 0,
		"skipped": 0,
		"errors": 0,
		"error_details": [],
	}

	for _, evento in eventos_df.iterrows():
		# Chave: {atividade}{inicio}{termino}{secao}
		chave = f"{evento['atividade']}{evento['inicio']}{evento['termino']}{evento['secao']}"

		try:
			# Verificar se o evento já existe pela chave
			# Assumindo que existe um campo 'chave' no DocType para armazenar esse identificador único
			# Se não existir, teremos que filtrar pelos campos individuais

			# Tentativa 1: Filtrar por campo 'chave' se existir
			# existing_docs = frappe.get_all("Calendario", filters={"chave": chave}, limit=1)

			# Tentativa 2: Filtrar pelos campos compostos (mais seguro se 'chave' não existir)
			filters = {
				"atividade": evento["atividade"],
				"inicio": evento["inicio"],
				"termino": evento["termino"],
				"secao": evento["secao"],
			}
			existing_docs = frappe.get_all("Calendario", filters=filters, limit=1)

			doc_data = {
				"doctype": "Calendario",
				"atividade": evento["atividade"],
				"inicio": evento["inicio"],
				"termino": evento["termino"],
				"secao": evento["secao"],
				"local": evento["local"],
				"chave": chave,  # Tentamos salvar a chave também
			}

			if existing_docs:
				doc = frappe.get_doc("Calendario", existing_docs[0].name)
				doc.update(doc_data)
				doc.save()
				results["updated"] += 1
			else:
				doc = frappe.get_doc(doc_data)
				doc.insert()
				results["created"] += 1

		except Exception as e:
			results["errors"] += 1
			results["error_details"].append(f"Erro ao importar evento '{evento.get('atividade')}': {e!s}")
			frappe.log_error(f"Erro importação calendário: {e!s}")

	frappe.db.commit()
	return results
