from __future__ import annotations

import frappe
from frappe.utils import cint

from gris.api.llm.client import gerar_resposta_modelo
from gris.api.llm.errors import LLMRequestError

FALLBACK_MODEL_ON_429 = "openai/gpt-4o-mini"


def gerar_resumo_avaliacoes_individuais(avaliacao_name: str) -> str:
	"""Gera resumo das avaliações individuais via LLM."""
	doc = frappe.get_doc("Avaliacao de Projeto", avaliacao_name)
	projeto_titulo = frappe.db.get_value("Projeto", doc.projeto, "nome_do_projeto") or doc.projeto

	avaliacoes = []
	for row in doc.avaliacoes_individuais or []:
		if not cint(row.avaliacao_concluida):
			continue
		avaliacoes.append(
			{
				"resultado_projeto": row.resultado_projeto,
				"satisfacao_colaboracao": row.satisfacao_colaboracao,
				"objetivos_atingidos": row.objetivos_atingidos,
				"muito_bom": row.muito_bom,
				"pontos_melhoria": row.pontos_melhoria,
			}
		)

	if not avaliacoes:
		return "Nenhuma avaliação individual concluída para gerar resumo."

	system_prompt = (
		"Você é um assistente de gestão de projetos escoteiros. "
		"Analise as avaliações individuais e produza um resumo objetivo em português brasileiro. "
		"Destaque padrões, consensos e divergências. Seja conciso e construtivo."
	)

	avaliacoes_text = ""
	for i, av in enumerate(avaliacoes, 1):
		avaliacoes_text += (
			f"\nLinha {i} (avaliação individual): "
			f"resultado_projeto={av['resultado_projeto']}; "
			f"satisfacao_colaboracao={av['satisfacao_colaboracao']}; "
			f"objetivos_atingidos={av['objetivos_atingidos']}; "
			f"muito_bom={av['muito_bom']}; "
			f"pontos_melhoria={av['pontos_melhoria']}"
		)

	user_prompt = (
		f"Projeto: {projeto_titulo}\n"
		f"Total de avaliações individuais concluídas: {len(avaliacoes)}\n"
		"Cada linha abaixo representa uma avaliação individual, sem identificação do avaliador.\n"
		f"\n{avaliacoes_text}\n"
		"Gere um resumo consolidado das avaliações individuais acima. "
		"Inclua: visão geral da satisfação, pontos fortes recorrentes, "
		"pontos de melhoria recorrentes e análise dos objetivos."
	)

	return _call_llm(system_prompt, user_prompt)


def gerar_resumo_avaliacao_completa(avaliacao_name: str) -> str:
	"""Gera resumo completo da avaliação (individuais + geral) via LLM."""
	doc = frappe.get_doc("Avaliacao de Projeto", avaliacao_name)
	projeto_titulo = frappe.db.get_value("Projeto", doc.projeto, "nome_do_projeto") or doc.projeto

	avaliacoes_text = ""
	linha = 1
	for row in doc.avaliacoes_individuais or []:
		if not cint(row.avaliacao_concluida):
			continue
		avaliacoes_text += (
			f"\n- Linha {linha} (avaliação individual): resultado={row.resultado_projeto}, "
			f"satisfacao={row.satisfacao_colaboracao}, "
			f"objetivos_atingidos={row.objetivos_atingidos}, "
			f"muito_bom='{row.muito_bom}', melhoria='{row.pontos_melhoria}'"
		)
		linha += 1

	objetivos_text = ""
	for row in doc.objetivos_atingidos or []:
		atingido = row.objetivo_atingido or "Não informado"
		motivo = f" ({row.porque_nao_foi_atingido})" if row.porque_nao_foi_atingido else ""
		objetivos_text += f"\n- {row.objetivo}: {atingido}{motivo}"

	system_prompt = (
		"Você é um assistente de gestão de projetos escoteiros. "
		"Produza uma avaliação final consolidada do projeto em português brasileiro. "
		"Seja construtivo, objetivo e destaque lições aprendidas."
	)

	user_prompt = (
		f"Projeto: {projeto_titulo}\n\n"
		"Cada linha em Avaliações individuais representa uma avaliação individual, sem identificação do avaliador.\n\n"
		f"## Avaliações individuais:{avaliacoes_text or ' Nenhuma'}\n\n"
		f"## Objetivos:{objetivos_text or ' Nenhum'}\n\n"
		f"## O que funcionou bem: {doc.o_que_funcionou_bem_na_dinamica_da_equipe or 'Não informado'}\n"
		f"## O que não funcionou: {doc.o_que_nao_funcionou_na_dinamica_da_equipe or 'Não informado'}\n"
		f"## Maior aprendizado: {doc.maior_aprendizado_gerado or 'Não informado'}\n"
		f"## Impacto na comunidade: {doc.impacto_gerado_para_comunidade or 'Não informado'}\n"
		f"## Pontos positivos adicionais: {doc.pontos_positivos_adicionais or 'Não informado'}\n"
		f"## Pontos de melhoria adicionais: {doc.pontos_de_melhoria_adicionais or 'Não informado'}\n\n"
		"Gere um resumo final da avaliação completa do projeto, integrando dados "
		"individuais e gerais. Inclua: resultado geral, pontos fortes, pontos de "
		"melhoria, lições aprendidas e recomendações para projetos futuros."
	)

	return _call_llm(system_prompt, user_prompt)


def _call_llm(system_prompt: str, user_prompt: str) -> str:
	"""Chama LLM com fallback para modelo estável em caso de rate limit."""
	try:
		return gerar_resposta_modelo(
			system_prompt=system_prompt,
			user_prompt=user_prompt,
		)
	except LLMRequestError as exc:
		if "HTTP 429" not in str(exc):
			raise

		return gerar_resposta_modelo(
			system_prompt=system_prompt,
			user_prompt=user_prompt,
			model=FALLBACK_MODEL_ON_429,
		)
