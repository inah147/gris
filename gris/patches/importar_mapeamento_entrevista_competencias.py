from __future__ import annotations

import csv
from pathlib import Path

import frappe

DTYPE = "Mapeamento de perguntas e respostas da entrevista"


def _as_int(value):
	try:
		return int(value)
	except Exception:
		return 0


def execute():
	csv_path = (
		Path(__file__).resolve().parents[1]
		/ "gestão_de_adultos"
		/ "data"
		/ "mapeamento_entrevista_competencias.csv"
	)

	with csv_path.open("r", encoding="utf-8", newline="") as file:
		reader = csv.DictReader(file)
		for row in reader:
			row_id = _as_int(row.get("ID"))
			if not row_id:
				continue

			existing = frappe.db.exists(DTYPE, {"id_origem": row_id})
			data = {
				"doctype": DTYPE,
				"id_origem": row_id,
				"pergunta": (row.get("Pergunta") or "").strip(),
				"resposta": (row.get("Resposta") or "").strip(),
				"alerta": 1 if str(row.get("Alerta") or "").strip().upper() == "TRUE" else 0,
				"motivo_do_alerta": (row.get("Motivo do alerta") or "").strip(),
				"pontuacao_dirigente_administrativo_financeiro": _as_int(
					row.get("Pontuação Dirigente Administrativo Financeiro")
				),
				"pontuacao_dirigente_gestao_institucional": _as_int(
					row.get("Pontuação Dirigente Gestão Institucional")
				),
				"pontuacao_dirigente_metodos_educativos": _as_int(
					row.get("Pontuação Dirigente Métodos Educativos")
				),
				"pontuacao_ramo_lobinho": _as_int(row.get("Pontuação Ramo Lobinho")),
				"pontuacao_ramo_escoteiro": _as_int(row.get("Pontuação Ramo Escoteiro")),
				"pontuacao_ramo_senior": _as_int(row.get("Pontuação Ramo Sênior")),
				"pontuacao_ramo_pioneiro": _as_int(row.get("Pontuação Ramo Pioneiro")),
			}

			if existing:
				doc = frappe.get_doc(DTYPE, existing)
				for key, value in data.items():
					if key == "doctype":
						continue
					doc.set(key, value)
				doc.save(ignore_permissions=True)
			else:
				frappe.get_doc(data).insert(ignore_permissions=True)
