# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Rascunho da ata por IA (CA-08.4 a CA-08.7).

O pedido grava "Gerando" e enfileira; a task chama o LLM e grava o texto ou um erro
amigável, sem apagar o texto que já existia. Vão para o modelo só nomes, cargos,
horários, a pauta e as anotações: CPF, telefone e e-mail não saem daqui.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint

from gris.api.assembleias import constantes as c
from gris.api.assembleias.ata import contar_marcadores, dados_da_ata
from gris.api.assembleias.padroes import configuracoes, data_por_extenso, hora, valores_da_assembleia
from gris.api.assembleias.pagina import _assembleia
from gris.api.assembleias.pessoas import nome_da_pessoa, ocupante_atual
from gris.api.assembleias.textos import substituir

STATUS_GERANDO = "Gerando"
STATUS_CONCLUIDA = "Concluída"
STATUS_FALHOU = "Falhou"

ERRO_GENERICO = (
	"Não foi possível gerar a ata por IA agora. Verifique a configuração do provedor em "
	"Configurações LLM e tente de novo. O texto que já existia foi mantido."
)
ERRO_LIMITE = "O serviço de IA atingiu o limite de uso. Tente de novo em alguns minutos."

PROMPT_DE_SISTEMA = """Você é o(a) secretário(a) de uma Assembleia de Grupo de um grupo escoteiro brasileiro e redige a ata oficial da reunião.

Regras:
1. Siga o MODELO DE ATA fornecido: mesma estrutura, mesmo tom formal e mesma redação dos trechos fixos.
2. Substitua cada marcador [ENTRE COLCHETES] pelos DADOS DA ASSEMBLEIA e pelas ANOTAÇÕES DO SECRETÁRIO.
3. Para cada item da pauta escreva um parágrafo que começa com "**Em atendimento ao item N do edital de convocação (TÍTULO DO ITEM)**", na ordem da pauta.
4. NUNCA invente votos, nomes, números, decisões ou horários. Se a informação não estiver nos dados nem nas anotações, escreva [A CONFIRMAR: o que falta].
5. Escreva horários e datas por extenso quando o modelo pedir.
6. Responda apenas com o texto da ata, em português, em markdown simples: parágrafos e **negrito**. Sem títulos, sem comentários, sem explicações antes ou depois."""


def _linhas_de_candidatos(name: str) -> list[str]:
	linhas = []
	for cargo in (
		c.CARGO_PRESIDENTE_MESA,
		c.CARGO_SECRETARIO_MESA,
		c.CARGO_DELEGADO,
		c.CARGO_COMISSAO_FISCAL,
	):
		nomes = frappe.get_all(
			c.DOCTYPE_CANDIDATURA,
			filters={"assembleia": name, "cargo": cargo, "status": "Ativa"},
			pluck="nome",
			order_by="creation asc",
		)
		if nomes:
			linhas.append(f"- Candidaturas prévias para {cargo}: {', '.join(nomes)}")
	for i, chapa in enumerate(
		frappe.get_all(
			c.DOCTYPE_CHAPA,
			filters={"assembleia": name, "status": "Ativa"},
			pluck="name",
			order_by="creation asc",
		),
		start=1,
	):
		membros = frappe.get_all(
			"Membro da Chapa", filters={"parent": chapa}, fields=["funcao", "nome"], order_by="idx asc"
		)
		descricao = "; ".join(f"{m.funcao}: {m.nome}" for m in membros)
		linhas.append(f"- Chapa {i} para a diretoria: {descricao}")
	return linhas


def montar_prompt(doc, config=None) -> str:
	"""O pedido ao modelo: modelo de ata, dados e anotações."""
	config = config or configuracoes()
	valores = valores_da_assembleia(doc, config)
	modelo = substituir(config.modelo_ata or c.MODELO_ATA, valores)

	diretoria = []
	for funcao in frappe.get_all(
		"Funcao Voluntario", filters={"diretoria": "Eleita", "ativa": 1}, pluck="name", order_by="name asc"
	):
		ocupante = ocupante_atual(funcao, doc.data)
		if ocupante:
			diretoria.append(f"- {funcao}: {ocupante}")

	pauta = "\n".join(
		f"{i}. {item.titulo}{' (concluído)' if cint(item.concluido) else ''}"
		for i, item in enumerate(doc.pauta, start=1)
	)
	assuntos = frappe.get_all(
		c.DOCTYPE_ASSUNTO, filters={"assembleia": doc.name}, pluck="conteudo", order_by="creation asc"
	)

	dados = [
		f"- Data: {valores['data']}",
		f"- Tipo: reunião {valores['tipo_minusculo']}",
		f"- Local: {doc.local or ''}",
		f"- Horário marcado: {valores['hora_primeira']} (primeira convocação) e {valores['hora_segunda']} (segunda)",
		f"- Início da reunião: {hora(doc.ata_hora_inicio) or '[não informado]'}",
		f"- Término da reunião: {hora(doc.ata_hora_termino) or '[não informado]'}",
		f"- Edital publicado em: {data_por_extenso(doc.data_publicacao_edital) or '[não informado]'}",
		f"- Presentes pela lista de presença: {cint(doc.ata_presentes) or '[não informado]'}",
		f"- Presidente da mesa: {nome_da_pessoa(doc.presidente_tipo, doc.presidente) or '[não informado]'}",
		f"- Secretário(a) da mesa: {nome_da_pessoa(doc.secretario_tipo, doc.secretario) or '[não informado]'}",
		f"- Vagas de delegado: {cint(doc.vagas_delegados)}",
		*diretoria,
		*_linhas_de_candidatos(doc.name),
		f"- Assuntos gerais enviados pelo formulário: {len(assuntos)}",
		*(f"  - {conteudo}" for conteudo in assuntos),
	]

	return "\n\n".join(
		[
			"MODELO DE ATA:\n" + modelo,
			"DADOS DA ASSEMBLEIA:\n" + "\n".join(dados),
			"PAUTA DO EDITAL:\n" + pauta,
			"ANOTAÇÕES DO SECRETÁRIO:\n" + ((doc.anotacoes_secretario or "").strip() or "[sem anotações]"),
		]
	)


@frappe.whitelist(methods=["POST"])
def solicitar_ata_ia(name: str, substituir_texto: int | str = 0) -> dict:
	doc = _assembleia(name)
	if doc.ata_status_geracao == STATUS_GERANDO:
		return {**dados_da_ata(doc), "pendente": True}
	if (doc.ata_texto or "").strip() and not cint(substituir_texto):
		# Como dado: a tela pergunta antes de trocar o texto existente (CA-08.6).
		return {"precisa_confirmar": True}
	if not (doc.anotacoes_secretario or "").strip():
		frappe.throw(_("Escreva as anotações do secretário antes de gerar a ata."))

	doc.ata_status_geracao = STATUS_GERANDO
	doc.ata_erro_geracao = ""
	doc.save()
	frappe.enqueue(
		"gris.api.assembleias.ata_ia.gerar_ata",
		queue="long",
		timeout=600,
		enqueue_after_commit=True,
		assembleia=doc.name,
	)
	return {**dados_da_ata(doc), "pendente": True}


@frappe.whitelist()
def status_ata_ia(name: str) -> dict:
	return dados_da_ata(_assembleia(name))


def gerar_ata(assembleia: str) -> None:
	"""Task da fila `long`. Grava só os campos da geração, sem passar pelo save.

	Sem commit manual: o worker do Frappe confirma a transação quando o job termina.
	"""
	from gris.api.llm import gerar_resposta_modelo
	from gris.api.llm.errors import LLMConfigurationError, LLMRequestError

	if not frappe.db.exists(c.DOCTYPE_ASSEMBLEIA, assembleia):
		return
	doc = frappe.get_doc(c.DOCTYPE_ASSEMBLEIA, assembleia)
	try:
		texto = gerar_resposta_modelo(
			system_prompt=PROMPT_DE_SISTEMA, user_prompt=montar_prompt(doc), temperature=0.2
		)
	except (LLMConfigurationError, LLMRequestError) as erro:
		frappe.log_error(frappe.get_traceback(), f"Ata por IA: {assembleia}")
		mensagem = ERRO_LIMITE if "429" in str(erro) else ERRO_GENERICO
		frappe.db.set_value(
			c.DOCTYPE_ASSEMBLEIA,
			assembleia,
			{"ata_status_geracao": STATUS_FALHOU, "ata_erro_geracao": mensagem},
			update_modified=False,
		)
		return
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Ata por IA: {assembleia}")
		frappe.db.set_value(
			c.DOCTYPE_ASSEMBLEIA,
			assembleia,
			{"ata_status_geracao": STATUS_FALHOU, "ata_erro_geracao": ERRO_GENERICO},
			update_modified=False,
		)
		return

	frappe.db.set_value(
		c.DOCTYPE_ASSEMBLEIA,
		assembleia,
		{"ata_texto": texto.strip(), "ata_status_geracao": STATUS_CONCLUIDA, "ata_erro_geracao": ""},
		# Sem mexer no `modified`: a tela aberta continua gravando sem acusar conflito.
		update_modified=False,
	)


__all__ = ["contar_marcadores", "gerar_ata", "montar_prompt", "solicitar_ata_ia", "status_ata_ia"]
