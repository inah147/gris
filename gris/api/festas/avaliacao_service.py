from __future__ import annotations

import frappe
from frappe.utils import cint

from gris.api.llm.client import gerar_resposta_modelo
from gris.api.llm.errors import LLMRequestError

FALLBACK_MODEL_ON_429 = "openai/gpt-4o-mini"


def _festa_titulo(doc) -> str:
	return frappe.db.get_value("Festa", doc.festa, "nome_festa") or doc.festa


def gerar_resumo_avaliacoes_individuais_festa(avaliacao_name: str) -> str:
	"""Gera o resumo das avaliações individuais da equipe via LLM."""
	doc = frappe.get_doc("Avaliacao Festa", avaliacao_name)

	linhas = ""
	total = 0
	for row in doc.avaliacoes_individuais or []:
		if not cint(row.avaliacao_concluida):
			continue
		total += 1
		linhas += (
			f"\nLinha {total} (avaliação individual): "
			f"resultado_festa={row.resultado_festa}; "
			f"satisfacao_colaboracao={row.satisfacao_colaboracao}; "
			f"muito_bom={row.muito_bom}; "
			f"pontos_melhoria={row.pontos_melhoria}"
		)

	if not total:
		return "Nenhuma avaliação individual concluída para gerar resumo."

	system_prompt = (
		"Você é um assistente de gestão de festas escoteiras. "
		"Analise as avaliações individuais da equipe e produza um resumo objetivo em "
		"português brasileiro. Destaque padrões, consensos e divergências. "
		"Seja conciso e construtivo."
	)
	user_prompt = (
		f"Festa: {_festa_titulo(doc)}\n"
		f"Total de avaliações individuais concluídas: {total}\n"
		"Cada linha abaixo representa uma avaliação individual, sem identificação do avaliador.\n"
		f"\n{linhas}\n"
		"Gere um resumo consolidado das avaliações individuais acima. "
		"Inclua: visão geral da satisfação, pontos fortes recorrentes e pontos de melhoria recorrentes."
	)
	return _call_llm(system_prompt, user_prompt)


def gerar_resumo_avaliacao_completa_festa(avaliacao_name: str) -> str:
	"""Gera o resumo completo da avaliação (equipe + geral + convidados) via LLM."""
	doc = frappe.get_doc("Avaliacao Festa", avaliacao_name)

	linhas = ""
	total = 0
	for row in doc.avaliacoes_individuais or []:
		if not cint(row.avaliacao_concluida):
			continue
		total += 1
		linhas += (
			f"\n- Linha {total} (avaliação individual): resultado={row.resultado_festa}, "
			f"satisfacao={row.satisfacao_colaboracao}, "
			f"muito_bom='{row.muito_bom}', melhoria='{row.pontos_melhoria}'"
		)

	# Convidados: anônimos, sem incluir o e-mail (dado pessoal) no prompt.
	convidados_linhas = ""
	total_convidados = 0
	for row in doc.avaliacoes_convidados or []:
		total_convidados += 1
		convidados_linhas += (
			f"\n- Convidado {total_convidados}: recomendacao={row.recomendacao}, "
			f"mais_gostou='{row.mais_gostou}', melhoria='{row.pode_melhorar}'"
		)

	system_prompt = (
		"Você é um assistente de gestão de festas escoteiras. "
		"Produza uma avaliação final consolidada da festa em português brasileiro, "
		"integrando a visão da equipe organizadora e a dos convidados. "
		"Seja construtivo, objetivo e destaque lições aprendidas."
	)
	user_prompt = (
		f"Festa: {_festa_titulo(doc)}\n\n"
		"Cada linha em Avaliações individuais representa uma avaliação individual da equipe, "
		"sem identificação do avaliador. Cada linha em Avaliações dos convidados é anônima.\n\n"
		f"## Avaliações individuais da equipe:{linhas or ' Nenhuma'}\n\n"
		f"## O que funcionou bem: {doc.o_que_funcionou_bem_na_dinamica_da_equipe or 'Não informado'}\n"
		f"## O que não funcionou: {doc.o_que_nao_funcionou_na_dinamica_da_equipe or 'Não informado'}\n"
		f"## Pontos positivos adicionais: {doc.pontos_positivos_adicionais or 'Não informado'}\n"
		f"## Pontos de melhoria adicionais: {doc.pontos_de_melhoria_adicionais or 'Não informado'}\n\n"
		"As notas dos convidados (recomendacao) vão de 0 a 10.\n"
		f"## Avaliações dos convidados:{convidados_linhas or ' Nenhuma'}\n\n"
		"Gere um resumo final da avaliação completa da festa, integrando a visão da equipe "
		"(dados individuais e gerais) e a dos convidados. Inclua: resultado geral, recomendação "
		"dos convidados, pontos fortes, pontos de melhoria, lições aprendidas e recomendações "
		"para festas futuras."
	)
	return _call_llm(system_prompt, user_prompt)


def gerar_resumo_avaliacoes_convidados_festa(avaliacao_name: str) -> str:
	"""Gera o resumo das avaliações dos convidados via LLM."""
	doc = frappe.get_doc("Avaliacao Festa", avaliacao_name)

	linhas = ""
	total = 0
	for row in doc.avaliacoes_convidados or []:
		total += 1
		linhas += (
			f"\nLinha {total} (avaliação de convidado): "
			f"recomendacao={row.recomendacao}; "
			f"mais_gostou={row.mais_gostou}; "
			f"pode_melhorar={row.pode_melhorar}"
		)

	if not total:
		return "Nenhuma avaliação de convidado registrada para gerar resumo."

	system_prompt = (
		"Você é um assistente de gestão de festas escoteiras. "
		"Analise as avaliações dos convidados e produza um resumo objetivo em português brasileiro. "
		"Destaque o nível de recomendação (NPS), o que mais agradou e o que pode melhorar. "
		"Seja conciso e construtivo."
	)
	user_prompt = (
		f"Festa: {_festa_titulo(doc)}\n"
		f"Total de avaliações de convidados: {total}\n"
		"Cada linha abaixo representa a avaliação anônima de um convidado. "
		"A recomendação vai de 0 a 10.\n"
		f"\n{linhas}\n"
		"Gere um resumo consolidado das avaliações dos convidados acima. "
		"Inclua: percepção geral de recomendação, pontos mais elogiados e principais sugestões de melhoria."
	)
	return _call_llm(system_prompt, user_prompt)


def _call_llm(system_prompt: str, user_prompt: str) -> str:
	"""Chama o LLM com fallback para modelo estável em caso de rate limit."""
	try:
		return gerar_resposta_modelo(system_prompt=system_prompt, user_prompt=user_prompt)
	except LLMRequestError as exc:
		if "HTTP 429" not in str(exc):
			raise
		return gerar_resposta_modelo(
			system_prompt=system_prompt, user_prompt=user_prompt, model=FALLBACK_MODEL_ON_429
		)
