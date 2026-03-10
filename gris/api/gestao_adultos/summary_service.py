from __future__ import annotations

import json

import frappe

from gris.api.gestao_adultos.prompt_builder import (
	PROMPT_SISTEMA_AVALIACAO_ENTREVISTA,
	montar_user_prompt_entrevista,
)
from gris.api.llm.client import gerar_resposta_modelo
from gris.gestão_de_adultos.doctype.entrevista_por_competencias.entrevista_por_competencias import (
	QUESTION_FIELDS,
	get_question_by_fieldname,
)

INTERVIEW_DTYPE = "Entrevista por Competencias"


def montar_contexto_entrevista(entrevista_name: str) -> dict:
	doc = frappe.get_doc(INTERVIEW_DTYPE, entrevista_name)
	questions_by_fieldname = get_question_by_fieldname()
	question_fields = [item["fieldname"] for item in QUESTION_FIELDS]

	respostas = []
	for fieldname in question_fields:
		resposta = doc.get(fieldname)
		observacao = doc.get(f"obs_{fieldname}")
		if not resposta and not observacao:
			continue
		respostas.append(
			{
				"fieldname": fieldname,
				"pergunta": questions_by_fieldname.get(fieldname),
				"resposta": resposta,
				"observacao": observacao,
			}
		)

	alertas = [
		{
			"pergunta": row.pergunta,
			"resposta": row.resposta,
			"motivo_do_alerta": row.motivo_do_alerta,
		}
		for row in doc.get("alertas")
	]

	return {
		"funcao_atual": doc.funcao_atual,
		"profissao": doc.profissao,
		"formacao": doc.formacao,
		"hobbies_e_interesses": doc.hobbies_e_interesses,
		"motivo_da_entrevista": doc.motivo_da_entrevista,
		"pontuacoes": {
			"pontuacao_dirigente_administrativo_financeiro": doc.pontuacao_dirigente_administrativo_financeiro,
			"pontuacao_dirigente_gestao_institucional": doc.pontuacao_dirigente_gestao_institucional,
			"pontuacao_dirigente_metodos_educativos": doc.pontuacao_dirigente_metodos_educativos,
			"pontuacao_ramo_lobinho": doc.pontuacao_ramo_lobinho,
			"pontuacao_ramo_escoteiro": doc.pontuacao_ramo_escoteiro,
			"pontuacao_ramo_senior": doc.pontuacao_ramo_senior,
			"pontuacao_ramo_pioneiro": doc.pontuacao_ramo_pioneiro,
		},
		"alertas": alertas,
		"respostas": respostas,
	}


def gerar_resumo_entrevista(entrevista_name: str) -> str:
	contexto = montar_contexto_entrevista(entrevista_name)
	contexto_serializado = json.dumps(contexto, ensure_ascii=False, indent=2)
	user_prompt = montar_user_prompt_entrevista(contexto_serializado)
	return gerar_resposta_modelo(
		system_prompt=PROMPT_SISTEMA_AVALIACAO_ENTREVISTA,
		user_prompt=user_prompt,
	)
