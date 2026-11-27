# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Conteúdo dos documentos da assembleia em markdown restrito (RF-06, RF-07, RF-11).

O markdown é a fonte única: vira HTML na pré-visualização do portal e requests da Docs
API no papel timbrado. Só usa o que o conversor entende: `#`/`##` (títulos), parágrafos,
`**negrito**`, `_itálico_`, listas `1.` e `-` e tabelas `|`.
"""

from __future__ import annotations

from gris.api.assembleias import constantes as c
from gris.api.assembleias.formularios import CARGO_NO_EDITAL, formularios_da_assembleia
from gris.api.assembleias.padroes import configuracoes, valores_da_assembleia
from gris.api.assembleias.textos import substituir


def linhas_de_link(doc, config) -> list[str]:
	"""Uma frase por formulário previsto na pauta, com link e prazo (CA-06.3)."""
	linhas = []
	for formulario in formularios_da_assembleia(doc, config):
		if not formulario["previsto"]:
			continue
		modelo = (
			c.LINHA_LINK_ASSUNTOS
			if formulario["chave"] == c.FORMULARIO_ASSUNTOS_GERAIS
			else c.LINHA_LINK_CANDIDATURA
		)
		linhas.append(
			substituir(
				modelo,
				{
					"cargo": CARGO_NO_EDITAL.get(formulario["chave"], ""),
					"link": formulario["link"],
					"prazo": formulario["prazo"],
				},
			)
		)
	return linhas


def conteudo_do_edital(doc, config=None) -> str:
	config = config or configuracoes()
	valores = valores_da_assembleia(doc, config)
	partes = [
		f"# REUNIÃO {valores['tipo']} DA ASSEMBLEIA DE GRUPO",
		"## EDITAL DE CONVOCAÇÃO",
		substituir(doc.edital_texto_topo or "", valores),
		"\n".join(f"{i}. {item.titulo}" for i, item in enumerate(doc.pauta, start=1)),
	]
	if doc.edital_incluir_links:
		partes.extend(linhas_de_link(doc, config))
	partes.append(substituir(doc.edital_texto_rodape or "", valores))
	return "\n\n".join(parte.strip() for parte in partes if parte and parte.strip())
