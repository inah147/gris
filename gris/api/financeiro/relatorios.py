import io
import os
import re
import unicodedata
from datetime import datetime, timedelta

import frappe
from openpyxl import load_workbook
from openpyxl.styles import PatternFill
from openpyxl.utils.cell import column_index_from_string, coordinate_from_string


@frappe.whitelist()
def export_relatorio_contabil(data_inicio=None, data_fim=None):
	"""Exporta o relatório contábil preenchendo o template armazenado como File.

	Comportamento:
	- Procura o token literal <<START_CELL>> na planilha; se encontrado, usa essa célula como primeira
	  célula de dados (não sobrescreve o cabeçalho acima).
	- Substitui tokens de metadados: <<start_date>>, <<end_date>>, <<export_date>>, <<export_user>>.
	- Substitui tokens de saldo por instituição na forma <<saldo_<slug>>> onde <slug> é o nome da
	  instituição slugificada (acentos removidos, espaços -> underscore, lower-case).
	- Escreve as linhas dos lançamentos a partir da célula START_CELL.
	"""
	if frappe.session.user == "Guest":
		frappe.throw("Login necessário", frappe.PermissionError)

	# carregar instituições
	instituicoes = frappe.get_all("Instituicao Financeira", fields=["name", "nome"], order_by="nome asc")
	instituicoes_nomes = [i.get("nome") or i.get("name") for i in instituicoes]

	# montar filtros
	filters = []
	if data_inicio:
		filters.append(["Transacao Extrato Geral", "data_deposito", ">=", data_inicio])
	if data_fim:
		filters.append(["Transacao Extrato Geral", "data_deposito", "<=", data_fim])

	# obter transacoes
	transacoes = frappe.get_all(
		"Transacao Extrato Geral",
		fields=[
			"data_deposito",
			"instituicao",
			"carteira",
			"centro_de_custo",
			"valor_absoluto",
			"debito_credito",
			"descricao",
			"categoria",
			"nome_atividade",
			"observacoes",
		],
		filters=filters,
		order_by="data_deposito asc",
	)

	# garantir objetos simples
	rows = [dict(t) for t in transacoes]

	# calcular saldos iniciais (dia anterior a data_inicio)
	saldos_iniciais = {inst: 0.0 for inst in instituicoes_nomes}
	if data_inicio:
		try:
			dt = datetime.strptime(data_inicio, "%Y-%m-%d")
			dia_anterior = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
			for inst in instituicoes_nomes:
				saldo = 0.0
				anteriores = frappe.get_all(
					"Transacao Extrato Geral",
					fields=["valor_absoluto", "debito_credito"],
					filters={"instituicao": inst, "data_deposito": ["<=", dia_anterior]},
				)
				for t in anteriores:
					v = t.get("valor_absoluto") or 0.0
					if t.get("debito_credito") == "Crédito":
						saldo += v
					elif t.get("debito_credito") == "Débito":
						saldo -= v
				saldos_iniciais[inst] = saldo
		except Exception:
			# se parsing falhar, manter zeros
			pass

	# calcular saldos por linha
	saldos = saldos_iniciais.copy()
	for r in rows:
		inst = r.get("instituicao")
		valor = r.get("valor_absoluto") or 0.0
		if inst in saldos:
			if r.get("debito_credito") == "Crédito":
				saldos[inst] += valor
			elif r.get("debito_credito") == "Débito":
				saldos[inst] -= valor
			r[inst] = saldos[inst]
		else:
			# garantir chave mesmo se instituicao nao bater
			for i in instituicoes_nomes:
				if i not in r:
					r[i] = None

	# localizar o File com o template
	template_name = "template_relatorio_contabil.xlsx"
	files = frappe.get_all(
		"File",
		filters={"file_name": template_name},
		fields=["name", "file_url", "is_private"],
		limit_page_length=1,
	)
	if not files:
		frappe.throw(f"Template '{template_name}' não encontrado como File. Faça upload com este nome.")

	file_doc = frappe.get_doc("File", files[0].get("name"))
	file_url = file_doc.file_url

	# resolver path local
	site_path = frappe.get_site_path()
	template_path = None
	if file_url.startswith("/files/"):
		template_path = os.path.join(site_path, "public", file_url.lstrip("/"))
	elif file_url.startswith("/private/") or file_url.startswith("/private/files/"):
		template_path = os.path.join(site_path, file_url.lstrip("/"))
	else:
		# fallback: try file_doc.get_full_path()
		try:
			template_path = file_doc.get_full_path()
		except Exception:
			template_path = None

	if not template_path or not os.path.exists(template_path):
		frappe.throw(f"Arquivo de template não encontrado no filesystem: {template_path}")

	# abrir workbook
	wb = load_workbook(template_path)

	# helper slugify
	def slugify(text: str) -> str:
		if not text:
			return ""
		text = unicodedata.normalize("NFKD", text)
		text = text.encode("ascii", "ignore").decode("ascii")
		text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_")
		return text.lower()

	# localizar literal token <<START_CELL>> em todas as planilhas
	start_row = None
	start_col = None
	start_ws = None
	token_start = "<<START_CELL>>"

	for sheet_name in wb.sheetnames:
		ws_tmp = wb[sheet_name]
		max_r = ws_tmp.max_row or 100
		max_c = ws_tmp.max_column or 50
		for row in ws_tmp.iter_rows(min_row=1, max_row=max(1, max_r), min_col=1, max_col=max(1, max_c)):
			for cell in row:
				if isinstance(cell.value, str) and token_start in cell.value:
					start_row = cell.row
					start_col = cell.column
					start_ws = ws_tmp
					# remove the token from the cell so it doesn't remain
					new_val = cell.value.replace(token_start, "").strip()
					cell.value = new_val if new_val != "" else None
					break
			if start_row:
				break
		if start_row:
			break

	# fallback: try defined name START_CELL (if literal not found)
	if not start_row:
		try:
			dn = wb.defined_names
			for defined in dn.definedName:
				if defined.name == "START_CELL":
					dests = list(defined.destinations)
					if dests:
						sheet_name, coord = dests[0]
						if sheet_name in wb.sheetnames:
							col_letter, row_num = coordinate_from_string(coord)
							start_row = int(row_num)
							start_col = column_index_from_string(col_letter)
							start_ws = wb[sheet_name]
					break
		except Exception:
			pass

	# default if still not found
	if not start_row:
		start_row = 2
		start_col = 1
		start_ws = wb.active

	ws = start_ws

	# preencher tokens de metadados e saldos iniciais
	now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
	try:
		export_user = frappe.get_value("User", frappe.session.user, "full_name") or frappe.session.user
	except Exception:
		export_user = frappe.session.user

	# use '-' for missing textual metadata
	meta_replacements = {
		"<<start_date>>": data_inicio or "-",
		"<<end_date>>": data_fim or "-",
		"<<export_date>>": now_str or "-",
		"<<export_user>>": export_user or "-",
	}

	# iterate all sheets and replace tokens
	for sheet_name in wb.sheetnames:
		ws_tmp = wb[sheet_name]
		max_r = ws_tmp.max_row or 100
		max_c = ws_tmp.max_column or 50
		for row in ws_tmp.iter_rows(min_row=1, max_row=max(1, max_r), min_col=1, max_col=max(1, max_c)):
			for cell in row:
				if not isinstance(cell.value, str):
					continue
				v = cell.value
				replaced = False
				# replace metadata tokens
				for token, repl in meta_replacements.items():
					if token in v:
						v = v.replace(token, str(repl))
						replaced = True

				# replace saldo tokens per institution
				for inst in instituicoes_nomes:
					slug = slugify(inst)
					token = f"<<saldo_{slug}>>"
					if token in v:
						saldo_val = saldos_iniciais.get(inst)
						# if the cell contains only the token, write numeric value or '-' when None
						if v.strip() == token:
							if saldo_val is None:
								cell.value = "-"
							else:
								try:
									cell.value = float(saldo_val)
									# apply currency number format so Excel displays as number with two decimals
									try:
										cell.number_format = '#,##0.00'
									except Exception:
										pass
								except Exception:
									cell.value = saldo_val
							replaced = True
							break
						else:
							# embed formatted saldo, or '-' if None
							if saldo_val is None:
								v = v.replace(token, "-")
							else:
								v = v.replace(token, f"{saldo_val:,.2f}")
							replaced = True
				if replaced and isinstance(cell.value, str):
					cell.value = v

	# preencher dados (não sobrescreve o cabeçalho; começa em START_CELL)
	data_base_col = start_col
	dyn_base_col = data_base_col + 10
	# row fill for alternating colors
	light_fill = PatternFill(start_color="FFF7F7F7", end_color="FFF7F7F7", fill_type="solid")

	# prepare last known saldos per institution (start with saldos_iniciais)
	last_saldos = {inst: (saldos_iniciais.get(inst) if saldos_iniciais.get(inst) is not None else 0.0) for inst in instituicoes_nomes}
	for ri, r in enumerate(rows, start=start_row):
		# data_deposito pode estar em string
		dt = r.get("data_deposito")
		if isinstance(dt, str):
			try:
				dt_val = datetime.fromisoformat(dt)
			except Exception:
				dt_val = dt
		else:
			dt_val = dt

		ws.cell(row=ri, column=data_base_col + 0, value=dt_val)

		# textual fields: replace None/empty with '-'
		instituicao_val = r.get("instituicao") if r.get("instituicao") not in (None, "") else "-"
		carteira_val = r.get("carteira") if r.get("carteira") not in (None, "") else "-"
		centro_val = r.get("centro_de_custo") if r.get("centro_de_custo") not in (None, "") else "-"
		ws.cell(row=ri, column=data_base_col + 1, value=instituicao_val)
		ws.cell(row=ri, column=data_base_col + 2, value=carteira_val)
		ws.cell(row=ri, column=data_base_col + 3, value=centro_val)

		# valor (numérico)
		val_num = r.get("valor_absoluto") or 0
		cell_val = ws.cell(row=ri, column=data_base_col + 4, value=val_num)
		try:
			cell_val.number_format = '#,##0.00'
		except Exception:
			pass

		tipo_val = r.get("debito_credito") if r.get("debito_credito") not in (None, "") else "-"
		descricao_val = r.get("descricao") if r.get("descricao") not in (None, "") else "-"
		categoria_val = r.get("categoria") if r.get("categoria") not in (None, "") else "-"
		atividade_val = r.get("nome_atividade") if r.get("nome_atividade") not in (None, "") else "-"
		observacoes_val = r.get("observacoes") if r.get("observacoes") not in (None, "") else "-"
		ws.cell(row=ri, column=data_base_col + 5, value=tipo_val)
		ws.cell(row=ri, column=data_base_col + 6, value=descricao_val)
		ws.cell(row=ri, column=data_base_col + 7, value=categoria_val)
		ws.cell(row=ri, column=data_base_col + 8, value=atividade_val)
		ws.cell(row=ri, column=data_base_col + 9, value=observacoes_val)

		# colunas dinâmicas por instituição
		for j, inst in enumerate(instituicoes_nomes):
			col_idx = dyn_base_col + j
			# determine if this row changed this institution
			val = r.get(inst)
			if val in (None, ""):
				# no change on this row for this institution -> carry forward last known saldo
				carry = last_saldos.get(inst)
				if carry is None:
					# fallback to '-' if truly unknown
					ws.cell(row=ri, column=col_idx, value="-")
				else:
					cell_dyn = ws.cell(row=ri, column=col_idx, value=carry)
					try:
						cell_dyn.number_format = '#,##0.00'
					except Exception:
						pass
			else:
				# row changed this institution: write the provided saldo and update last_saldos
				try:
					num = float(val)
				except Exception:
					num = val
				cell_dyn = ws.cell(row=ri, column=col_idx, value=num)
				try:
					cell_dyn.number_format = '#,##0.00'
				except Exception:
					pass
				# update last known saldo if numeric
				try:
					if isinstance(num, (int, float)):
						last_saldos[inst] = num
				except Exception:
					pass

		# apply alternating fill
		# if offset is even -> light gray, else white (first row = even offset 0)
		offset = ri - start_row
		if offset % 2 == 0:
			for c in range(data_base_col, dyn_base_col + len(instituicoes_nomes)):
				cell = ws.cell(row=ri, column=c)
				cell.fill = light_fill

	# salvar em bytes
	out = io.BytesIO()
	wb.save(out)
	out.seek(0)

	filename = f"relatorio_contabil_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
	frappe.local.response.filename = filename
	frappe.local.response.filecontent = out.read()
	frappe.local.response.type = "download"
