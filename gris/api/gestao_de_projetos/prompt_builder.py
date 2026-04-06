from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime
from typing import Any

import frappe

PROMPT_SISTEMA_REVISAO_TAP = """
# Avaliador Técnico de Termo de Abertura de Projeto (TAP) Escoteiro

**Você é um avaliador técnico de Termo de Abertura de Projeto (TAP) para projetos de impacto social em um Grupo Escoteiro.**

Projetos escoteiros devem alinhar-se aos valores do escotismo: desenvolvimento integral dos jovens, cidadania ativa, sustentabilidade ambiental e impacto social positivo. O TAP, como primeira entrega, apresenta a ideia do projeto e busca autorização para início.

## Considerações importantes para a revisão

- **Sem lucro financeiro**: Projetos não visam ganho monetário. Arrecadação é permitida apenas para financiar objetivos escoteiros claros (ex.: atividade educativa, causa social/ambiental ou desenvolvimento de competências jovens). Evite projetos só para "levantar caixa" sem propósito alinhado.
- **Cronograma essencial**: Inclua tarefas como elaboração de orçamento e relatório final.

## Conteúdo esperado por seção

### Descrição e justificativa
Apresente a ideia do projeto, problema/oportunidade abordada e justificativa, com contexto relevante ao escotismo.

**Exemplo positivo**:  
"Projeto 'Horta Escoteira Sustentável': Criaremos uma horta orgânica na sede do grupo para ensinar 20 jovens sobre agricultura urbana, combatendo insegurança alimentar local (dados IBGE: 30% das famílias na comunidade sem acesso regular a vegetais). Justificativa: Fomenta autossuficiência e conexão com a natureza, alinhado ao Método Escoteiro."

**Exemplo negativo**:  
"Vamos fazer uma horta porque é legal. Tem gente passando fome por aí."

### Como o projeto se alinha com o escotismo
Mostre conexão clara com princípios escoteiros (ex.: Promessa Escoteira, Programa Educativo, gestão institucional).

**Exemplo positivo**:  
"Alinha-se ao Desenvolvimento Integral (área 'Cuidar da Natureza'): jovens aprendem jardinagem sustentável, promovendo cidadania ativa via doação de produção a famílias carentes e impacto ambiental (redução de resíduos plásticos em embalagens). Contribui para o Programa Educativo das Seções Escoteira e Pioneira."

**Exemplo negativo**:  
"É bom para o meio ambiente e ajuda as pessoas, tipo escotismo."

### Objetivos
Sejam claros, mensuráveis, com métricas de sucesso alinhadas à descrição.

**Exemplo positivo**:
- Plantar horta com 50 mudas orgânicas até mês 2 (**métrica**: 90% de sobrevivência).
- Capacitar 20 jovens em técnicas sustentáveis via 4 oficinas (**métrica**: 80% de aprovação em teste prático).
- Doar 100kg de vegetais a comunidade (**métrica**: registro fotográfico e pesagem).

**Exemplo negativo**:
- Fazer uma horta.
- Ensinar sobre plantas.
- Ajudar os pobres.

### ODS
Alinhe com pelo menos um ODS da ONU. A ODS deve ser relacionada com o problema/oportunidade e objetivos do projeto.

**Exemplo positivo**:
Se o projeto for sobre oficinas de hortaliças orgânicas para jovens, pode alinhar com o ODS 2

**Exemplo negativo**:  
Se o projeto for sobre oficinas de hortaliças orgânicas para jovens, não pode alinhar com o ODS 7 (Energia Limpa e Acessível)

### Cronograma
Liste tarefas principais com datas realistas, incluindo planejamento, execução, monitoramento, orçamento e relatório.

**Exemplo positivo**:
- Mês 1: Planejamento e levantamento de recursos (01/05-31/05).
- Mês 2: Oficinas e plantio (01/06-30/06).
- Mês 3: Monitoramento e colheita (01/07-15/07).
- Mês 4: Doação, relatório e avaliação (16/07-31/07), incluindo orçamento final.

**Exemplo negativo**:
"Começa em maio, acaba em agosto. Faz tudo rápido."

### Recursos
Detalhe recursos financeiros, humanos, materiais e tecnológicos, com quantidades e finalidades.

**Exemplo positivo**:
- **Financeiros**: R$500 (sementes/mudanças, via rifa alinhada).
- **Humanos**: 2 adultos formadores + 20 jovens.
- **Materiais**: 10 ferramentas de jardinagem; 50 sacos de terra.
- **Tecnológicos**: App gratuito para monitoramento de crescimento (ex.: Plantix).

**Exemplo negativo**:
"Dinheiro o que precisar, gente do grupo, coisas básicas."

### Riscos
Identifique riscos principais (natureza, probabilidade, impacto), com estratégias de mitigação.

**Exemplo positivo**:
- **Risco**: Chuvas excessivas danificam plantas (probabilidade média, impacto alto). **Mitigação**: Estufa improvisada com plásticos reciclados; plano B de cultivo indoor.
- **Risco**: Baixa adesão de jovens (probabilidade baixa, impacto médio). **Mitigação**: Gamificação com insígnias escoteiras e lembretes semanais.

**Exemplo negativo**:  
"Pode chover (sem mitigação). Jovens podem não vir (vamos ver)."

**Observação**: Se uma seção estiver perfeita, diga "Nenhum ponto de atenção identificado".

# Formato de resposta

[Avaliação geral do TAP: comentários gerais e recomendação de aprovação ou ajustes necessários, sem repetir pontos já mencionados nas seções específicas]
# **Descrição e justificativa**
[Pontos fortes, lacunas e recomendações específicas para esta seção]
# **Alinhamento com o escotismo**
[Pontos fortes, lacunas e recomendações específicas para esta seção]
# **Objetivos**
[Pontos fortes, lacunas e recomendações específicas para esta seção]
# **ODS**
[Pontos fortes, lacunas e recomendações específicas para esta seção]
# **Cronograma**
[Pontos fortes, lacunas e recomendações específicas para esta seção]
# **Recursos**
[Pontos fortes, lacunas e recomendações específicas para esta seção]
# **Riscos**
[Pontos fortes, lacunas e recomendações específicas para esta seção]

# Restrições obrigatórias:
- JAMAIS apresente diretamente um texto alterado para que a pessoa copie e cole. Apresente apenas análises, pontos de atenção e recomendações.
- NUNCA use linguagem pejorativa ou desmotivadora, mesmo que haja pontos de atenção. Mantenha tom profissional, direto e construtivo.
- NUNCA diga que o projeto é "ruim" ou "bom". Foque em análises objetivas e recomendações práticas de melhoria, sem julgamentos de valor.
- NUNCA recomende aprovação se houver pontos de atenção relevantes. Recomende ajustes necessários para alinhamento ao escotismo e melhoria do projeto, mesmo que o projeto tenha pontos fortes. A aprovação só deve ser recomendada se o TAP estiver muito bem elaborado, alinhado ao escotismo e sem pontos de atenção relevantes.

"""

SECTION_CANONICAL_HEADINGS: list[tuple[str, str]] = [
	("descricao_justificativa", "# **Descrição e justificativa**"),
	("alinhamento_escotismo", "# **Alinhamento com o escotismo**"),
	("objetivos", "# **Objetivos**"),
	("ods", "# **ODS**"),
	("cronograma", "# **Cronograma**"),
	("recursos", "# **Recursos**"),
	("riscos", "# **Riscos**"),
]


def _serialize_rows(rows: list[dict[str, Any]] | None, allowed_fields: list[str]) -> list[dict[str, Any]]:
	output: list[dict[str, Any]] = []
	for row in rows or []:
		payload = {fieldname: _to_json_safe_value(row.get(fieldname)) for fieldname in allowed_fields}
		if any(payload.get(fieldname) not in (None, "", []) for fieldname in allowed_fields):
			output.append(payload)
	return output


def _to_json_safe_value(value: Any) -> Any:
	if isinstance(value, (date, datetime)):
		return value.isoformat()
	return value


def _montar_equipe_para_prompt(rows: list[dict[str, Any]] | None) -> list[dict[str, str]]:
	equipe: list[dict[str, str]] = []
	pessoa_idx = 1

	for row in rows or []:
		has_any_data = any(
			(row.get(fieldname) or "").strip()
			for fieldname in [
				"tipo_pessoa",
				"associado",
				"responsavel",
				"nome",
				"email",
				"telefone",
				"funcao",
			]
		)
		if not has_any_data:
			continue

		funcao = (row.get("funcao") or "").strip() or "Não informado"
		equipe.append(
			{
				"pessoa": f"Pessoa {pessoa_idx}",
				"funcao": funcao,
			}
		)
		pessoa_idx += 1

	return equipe


def _mapear_ods_com_descricao(rows_ods: list[dict[str, Any]] | None) -> list[dict[str, str]]:
	selecionadas = [
		(row.get("ods") or "").strip() for row in rows_ods or [] if (row.get("ods") or "").strip()
	]
	if not selecionadas:
		return []

	ods_docs = frappe.get_all(
		"ODS Projeto",
		filters={"name": ["in", selecionadas]},
		fields=["name", "codigo", "titulo", "descricao"],
		limit_page_length=max(len(selecionadas), 20),
	)
	ods_por_name = {doc.get("name"): doc for doc in ods_docs}

	output: list[dict[str, str]] = []
	for ods_name in selecionadas:
		ods_doc = ods_por_name.get(ods_name) or {}
		output.append(
			{
				"ods": ods_name,
				"titulo": ods_doc.get("titulo") or ods_name,
				"descricao": ods_doc.get("descricao") or "",
			}
		)
	return output


def montar_payload_revisao_tap(projeto_name: str) -> dict[str, Any]:
	doc = frappe.get_doc("Projeto", projeto_name)

	return {
		"titulo": doc.get("nome_do_projeto") or "",
		"descricao_e_justificativa": doc.get("justificativa") or "",
		"alinhamento_com_escotismo": doc.get("alinhamento_com_escotismo") or "",
		"equipe_de_interesse": _montar_equipe_para_prompt(doc.get("equipe_de_interesse")),
		"objetivos": _serialize_rows(doc.get("objetivos"), ["objetivo", "metrica_de_sucesso"]),
		"ods": _mapear_ods_com_descricao(doc.get("ods")),
		"cronograma": _serialize_rows(doc.get("cronograma"), ["data_inicio", "data_termino", "tarefa"]),
		"recursos": _serialize_rows(doc.get("recursos"), ["recurso"]),
		"riscos": _serialize_rows(doc.get("riscos"), ["risco", "mitigacao"]),
		"contexto_adicional_observacoes_e_comentarios": doc.get("observacoes_e_comentarios") or "",
	}


def construir_prompts_revisao_tap(projeto_name: str) -> tuple[str, str]:
	payload = montar_payload_revisao_tap(projeto_name)
	template = [
		"[Avaliação geral do TAP: comentários gerais e recomendação de aprovação ou ajustes necessários, sem repetir pontos já mencionados nas seções específicas]",
	]
	template.extend(heading for _, heading in SECTION_CANONICAL_HEADINGS)
	user_prompt = (
		"Revise o termo de abertura de projeto usando os dados enviados.\n"
		"A resposta final deve ser em Markdown puro (sem bloco de código envolvendo todo o texto).\n"
		"Siga EXATAMENTE o template abaixo, na mesma ordem e com os mesmos títulos de seção.\n"
		+ "\n".join(template)
		+ "\n"
		f"TAP para revisão (JSON):\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
	)
	return PROMPT_SISTEMA_REVISAO_TAP, user_prompt


def normalizar_formato_revisao_tap(markdown_text: str) -> str:
	text = _strip_global_code_fence(markdown_text or "")
	lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

	sections: dict[str, list[str]] = {key: [] for key, _ in SECTION_CANONICAL_HEADINGS}
	general_lines: list[str] = []
	current_section: str | None = None

	for line in lines:
		section_key = _match_section_key(line)
		if section_key:
			current_section = section_key
			continue

		if current_section is None:
			general_lines.append(line)
		else:
			sections[current_section].append(line)

	general_text = _compact_block("\n".join(general_lines).strip())
	if not general_text:
		general_text = "Sem observações gerais adicionais."

	output_parts = [general_text]
	for key, heading in SECTION_CANONICAL_HEADINGS:
		output_parts.append(heading)
		section_text = _compact_block("\n".join(sections.get(key, [])).strip())
		output_parts.append(section_text or "Nenhum ponto de atenção identificado.")

	return "\n\n".join(part.strip() for part in output_parts if part is not None).strip()


def _normalize_heading_label(value: str) -> str:
	decomposed = unicodedata.normalize("NFKD", value or "")
	no_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
	return re.sub(r"[^a-z0-9]", "", no_accents.lower())


def _match_section_key(line: str) -> str | None:
	stripped = (line or "").strip()
	if not stripped.startswith("#"):
		return None

	label = stripped.lstrip("#").strip().strip("*").strip()
	label_norm = _normalize_heading_label(label)

	if "descricao" in label_norm and "justificativa" in label_norm:
		return "descricao_justificativa"
	if "alinhamento" in label_norm and "escotismo" in label_norm:
		return "alinhamento_escotismo"
	if label_norm.startswith("objetivos"):
		return "objetivos"
	if label_norm == "ods" or ("objetivos" in label_norm and "sustentavel" in label_norm):
		return "ods"
	if "cronograma" in label_norm:
		return "cronograma"
	if "recursos" in label_norm:
		return "recursos"
	if "riscos" in label_norm:
		return "riscos"

	return None


def _strip_global_code_fence(text: str) -> str:
	stripped = (text or "").strip()
	if stripped.startswith("```") and stripped.endswith("```"):
		content = stripped[3:-3]
		if "\n" in content:
			content = content.split("\n", 1)[1]
		return content.strip()
	return stripped


def _compact_block(text: str) -> str:
	if not text:
		return ""
	lines = [line.rstrip() for line in text.split("\n")]
	cleaned: list[str] = []
	blank_count = 0
	for line in lines:
		if not line.strip():
			blank_count += 1
			if blank_count <= 1:
				cleaned.append("")
			continue
		blank_count = 0
		cleaned.append(line)
	return "\n".join(cleaned).strip()
