# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Página da assembleia, em quatro etapas: Edital, Inscrições, Sessão e Ata (RF-05 a RF-10).

Tudo exige quem gerencia. A tela grava tudo pelo salvamento automático (`salvar_campos`),
que devolve o `modified` novo: a tela manda o último que conhece e, se outra janela gravou
no meio, recebe `conflito` em vez de sobrescrever (CA-08.3).
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, get_time, getdate, now_datetime
from frappe.utils.data import md_to_html
from frappe.utils.html_utils import sanitize_html

from gris.api.assembleias import constantes as c
from gris.api.assembleias.documentos import conteudo_do_edital
from gris.api.assembleias.formularios import contar_inscricoes, formularios_da_assembleia
from gris.api.assembleias.padroes import aplicar_pauta_padrao, configuracoes, hora
from gris.api.assembleias.permissoes import garantir_gestor_assembleias
from gris.api.assembleias.pessoas import juntar_pessoa, nome_da_pessoa, separar_pessoa
from gris.api.assembleias.textos import validar_texto

TIPOS = (c.TIPO_ORDINARIA, c.TIPO_EXTRAORDINARIA)

MESES = (
	"janeiro",
	"fevereiro",
	"março",
	"abril",
	"maio",
	"junho",
	"julho",
	"agosto",
	"setembro",
	"outubro",
	"novembro",
	"dezembro",
)
DIAS_DA_SEMANA = (
	"segunda-feira",
	"terça-feira",
	"quarta-feira",
	"quinta-feira",
	"sexta-feira",
	"sábado",
	"domingo",
)

# As etapas da página, na ordem em que a assembleia acontece.
ETAPAS = (("edital", "Edital"), ("inscricoes", "Inscrições"), ("sessao", "Sessão"), ("ata", "Ata"))


def markdown_em_html(texto: str | None) -> str:
	"""Markdown escrito pela gestão, convertido e sanitizado para exibir no portal."""
	if not (texto or "").strip():
		return ""
	return sanitize_html(str(md_to_html(texto) or ""), always_sanitize=True)


def _carregar(payload) -> dict:
	if isinstance(payload, dict):
		return payload
	try:
		dados = json.loads(payload or "{}")
	except ValueError:
		frappe.throw(_("Dados inválidos."))
	if not isinstance(dados, dict):
		frappe.throw(_("Dados inválidos."))
	return dados


def _assembleia(name: str):
	garantir_gestor_assembleias()
	if not name or not frappe.db.exists(c.DOCTYPE_ASSEMBLEIA, name):
		frappe.throw(_("Assembleia não encontrada."), frappe.DoesNotExistError)
	return frappe.get_doc(c.DOCTYPE_ASSEMBLEIA, name)


def _hora(valor) -> str | None:
	if not valor:
		return None
	try:
		return get_time(valor).strftime("%H:%M:%S")
	except Exception:
		frappe.throw(_("Horário inválido: {0}.").format(valor))


# --------------------------------------------------------------------------------------
# Leitura
# --------------------------------------------------------------------------------------


def _data_br(valor) -> str:
	return getdate(valor).strftime("%d/%m/%Y") if valor else ""


def data_por_extenso(valor) -> str:
	""" "sábado, 5 de dezembro de 2026"."""
	data = getdate(valor)
	return f"{DIAS_DA_SEMANA[data.weekday()]}, {data.day} de {MESES[data.month - 1]} de {data.year}"


def _hora_curta(valor) -> str:
	"""14:30 vira "14h30"; hora cheia vira "14h"."""
	texto = hora(valor)
	if not texto:
		return ""
	horas, minutos = texto.split(":")
	return f"{int(horas)}h{minutos if minutos != '00' else ''}"


def _plural(n: int, singular: str, plural: str) -> str:
	return f"{n} {singular if n == 1 else plural}"


def etapas_da_assembleia(doc, config, formularios: list[dict], checklist: list[dict], hoje=None) -> dict:
	"""Onde a assembleia está: o estado de cada etapa, a etapa atual e o próximo passo.

	A etapa atual é a primeira com pendência pela data: o edital até ser publicado, as
	inscrições até a véspera, a sessão no dia e a ata depois. O próximo passo só aparece
	quando há algo a fazer, com o tom de quanto aquilo aperta.
	"""
	hoje = getdate(hoje) if hoje else getdate()
	data = getdate(doc.data)
	dias = (data - hoje).days
	dias_limite = cint(config.dias_limite_edital) or 30
	prazo = getdate(add_days(data, -dias_limite))
	publicado = cint(doc.edital_publicado)
	hora_inicio = _hora_curta(doc.hora_primeira_convocacao)

	# Edital
	if publicado:
		edital = ("feito", f"Publicado em {_data_br(doc.data_publicacao_edital or doc.edital_publicado_em)}")
	elif prazo < hoje:
		edital = ("alerta", f"Prazo venceu em {_data_br(prazo)}")
	else:
		edital = ("pendente", f"Publicar até {_data_br(prazo)}")

	# Inscrições
	contagens = contar_inscricoes(doc.name)
	inscricoes = sum(total for chave, total in contagens.items() if chave != "assuntos")
	rotulo_inscricoes = _plural(inscricoes, "inscrição", "inscrições")
	abertos = [f for f in formularios if f.get("aberto")]
	reabertos = [f for f in formularios if f.get("reaberto")]
	if dias < 0:
		inscricoes_estado = ("feito", f"Encerradas · {rotulo_inscricoes}")
	elif reabertos:
		inscricoes_estado = ("alerta", f"Faltam candidatos · {rotulo_inscricoes}")
	elif abertos:
		abertos_txt = _plural(len(abertos), "aberta", "abertas")
		inscricoes_estado = ("pendente", f"{abertos_txt} · {rotulo_inscricoes}")
	elif not any(f.get("previsto") for f in formularios):
		inscricoes_estado = ("pendente", "Nenhuma prevista na pauta")
	else:
		inscricoes_estado = ("pendente", f"Encerradas · {rotulo_inscricoes}")

	# Sessão
	if dias < 0:
		sessao = ("feito", f"Realizada em {_data_br(data)}")
	elif dias == 0:
		sessao = ("pendente", f"Hoje, às {hora_inicio}")
	elif dias == 1:
		sessao = ("pendente", f"Amanhã, às {hora_inicio}")
	else:
		sessao = ("pendente", f"Em {dias} dias")

	# Ata
	depois = [e for e in checklist if e["fase"] == "Depois"]
	feitas = sum(1 for e in depois if e["concluido"])
	if dias >= 0:
		ata = ("pendente", "Depois da sessão")
	elif depois and feitas == len(depois):
		ata = ("feito", "Tudo concluído")
	else:
		ata = ("pendente", f"{feitas} de {_plural(len(depois), 'tarefa', 'tarefas')}")

	estados = {"edital": edital, "inscricoes": inscricoes_estado, "sessao": sessao, "ata": ata}
	if not publicado:
		atual = "edital"
	elif dias > 0:
		atual = "inscricoes"
	elif dias == 0:
		atual = "sessao"
	else:
		atual = "ata"

	proximo = None
	if not publicado:
		if prazo < hoje:
			proximo = {
				"tom": "alerta",
				"titulo": "Publique o edital o quanto antes",
				"texto": f"O prazo de {dias_limite} dias de antecedência do estatuto venceu em "
				f"{_data_br(prazo)}. Ainda dá para publicar, confirmando o atraso.",
				"etapa": "edital",
				"alvo": "ed-acoes",
				"acao": "Revisar e publicar",
			}
		else:
			faltam = (prazo - hoje).days
			proximo = {
				"tom": "aviso" if faltam <= 7 else "info",
				"titulo": f"Publique o edital até {_data_br(prazo)}",
				"texto": "O prazo termina hoje."
				if not faltam
				else f"Faltam {_plural(faltam, 'dia', 'dias')} para cumprir os {dias_limite} dias de "
				"antecedência do estatuto.",
				"etapa": "edital",
				"alvo": "ed-acoes",
				"acao": "Revisar e publicar",
			}
	elif dias > 0:
		if reabertos:
			nomes = ", ".join(f["rotulo"] for f in reabertos)
			proximo = {
				"tom": "aviso",
				"titulo": "Faltam candidatos",
				"texto": f"As inscrições de {nomes} seguem abertas até o início da assembleia "
				"porque ainda faltam candidatos.",
				"etapa": "inscricoes",
				"alvo": "in-formularios",
				"acao": "Ver inscrições",
			}
		elif dias <= 7 and not doc.lista_gerada_em:
			proximo = {
				"tom": "info",
				"titulo": "Gere a lista de presença",
				"texto": f"A assembleia é em {_plural(dias, 'dia', 'dias')}. Gere a lista e imprima "
				"para o credenciamento.",
				"etapa": "sessao",
				"alvo": "lp-bloco",
				"acao": "Ir para a lista",
			}
	elif dias == 0:
		proximo = {
			"tom": "info",
			"titulo": f"A assembleia é hoje, às {hora_inicio}",
			"texto": "Registre a mesa, os horários e as anotações na etapa Sessão.",
			"etapa": "sessao",
			"alvo": "se-mesa",
			"acao": "Ir para a sessão",
		}
	elif not doc.ata_pdf_link:
		proximo = {
			"tom": "info",
			"titulo": "Finalize a ata",
			"texto": "Revise o texto e gere o PDF da versão final para as assinaturas.",
			"etapa": "ata",
			"alvo": "at-texto-bloco",
			"acao": "Ir para a ata",
		}
	elif feitas < len(depois):
		proximo = {
			"tom": "info",
			"titulo": f"Falta{'' if len(depois) - feitas == 1 else 'm'} "
			f"{_plural(len(depois) - feitas, 'tarefa', 'tarefas')} depois da assembleia",
			"texto": "Assinatura e registros que vêm depois da assembleia.",
			"etapa": "ata",
			"alvo": "at-tarefas",
			"acao": "Ver tarefas",
		}

	return {
		"atual": atual,
		"itens": [
			{"chave": chave, "rotulo": rotulo, "estado": estados[chave][0], "descricao": estados[chave][1]}
			for chave, rotulo in ETAPAS
		],
		"proximo": proximo,
	}


def dados_da_pagina(doc, config=None) -> dict:
	config = config or configuracoes()
	eletiva = doc.eletiva
	prazo_edital = add_days(doc.data, -(cint(config.dias_limite_edital) or 30))
	formularios = formularios_da_assembleia(doc, config)
	checklist = [
		{
			"chave": etapa.chave,
			"fase": etapa.fase,
			"titulo": etapa.titulo,
			"concluido": cint(etapa.concluido),
			"concluido_em": str(etapa.concluido_em or ""),
			"concluido_por": etapa.concluido_por or "",
			"automatico": etapa.chave == c.CHECKLIST_DIVULGAR_EDITAL,
		}
		for etapa in doc.checklist
		if eletiva or not cint(etapa.somente_eletiva)
	]
	return {
		"name": doc.name,
		"modified": str(doc.modified),
		"titulo": doc.titulo,
		"data": str(doc.data),
		"data_extenso": data_por_extenso(doc.data),
		"tipo": doc.tipo,
		"local": doc.local or "",
		"hora_primeira": hora(doc.hora_primeira_convocacao),
		"hora_segunda": hora(doc.hora_segunda_convocacao),
		"credenciamento": juntar_pessoa(doc.credenciamento_tipo, doc.credenciamento),
		"vagas_delegados": cint(doc.vagas_delegados),
		"presidente": nome_da_pessoa(doc.presidente_tipo, doc.presidente),
		"secretario": nome_da_pessoa(doc.secretario_tipo, doc.secretario),
		"pasta_drive_link": doc.pasta_drive_link or "",
		"pasta_drive_erro": doc.pasta_drive_erro or "",
		"eletiva": eletiva,
		"prazo_edital": str(prazo_edital),
		"prazo_vencido": not cint(doc.edital_publicado) and getdate(prazo_edital) < getdate(),
		"edital": {
			"publicado": cint(doc.edital_publicado),
			"publicado_em": str(doc.edital_publicado_em or ""),
			"data_publicacao": str(doc.data_publicacao_edital or ""),
			"incluir_links": cint(doc.edital_incluir_links),
			"texto_topo": doc.edital_texto_topo or "",
			"texto_rodape": doc.edital_texto_rodape or "",
			"doc_link": doc.edital_doc_link or "",
			"pdf_link": doc.edital_pdf_link or "",
		},
		"pauta": [
			{
				"name": item.name,
				"titulo": item.titulo,
				"tem_votacao": cint(item.tem_votacao),
				"finalidade": item.finalidade or "",
				"concluido": cint(item.concluido),
				"orientacao_conducao": item.orientacao_conducao or "",
				"orientacao_html": markdown_em_html(item.orientacao_conducao),
			}
			for item in doc.pauta
		],
		"checklist": checklist,
		"materiais": [m.item for m in config.materiais],
		"formularios": formularios,
		"orientacoes_gerais_html": markdown_em_html(config.orientacoes_gerais),
		"etapas": etapas_da_assembleia(doc, config, formularios, checklist),
	}


# --------------------------------------------------------------------------------------
# Dados da convocação, credenciamento e vagas
# --------------------------------------------------------------------------------------


def aplicar_dados(doc, dados: dict) -> bool:
	"""Põe no doc só os campos que vieram, sem gravar.

	Devolve se mudou algo que muda o resto da página (data, tipo, primeira convocação ou a
	pauta): a tela recarrega para refazer o título, os prazos e o roteiro. Data, tipo e
	horários travam com o edital publicado no controller (CA-06.7).
	"""
	recarregar = False
	if "tipo" in dados:
		tipo = dados.get("tipo") or doc.tipo
		if tipo not in TIPOS:
			frappe.throw(_("Tipo de assembleia inválido."))
		if tipo != doc.tipo:
			doc.tipo = tipo
			recarregar = True
			if dados.get("trocar_pauta"):
				aplicar_pauta_padrao(doc)
	if "data" in dados:
		if not dados.get("data"):
			frappe.throw(_("Informe a data da assembleia."))
		data = getdate(dados["data"])
		if data != getdate(doc.data):
			doc.data = data
			recarregar = True
	if "local" in dados:
		local = (dados.get("local") or "").strip()
		if not local:
			frappe.throw(_("Informe o local da assembleia."))
		doc.local = local
	if "hora_primeira" in dados:
		if not dados.get("hora_primeira"):
			frappe.throw(_("Informe o horário da primeira convocação."))
		primeira = _hora(dados["hora_primeira"])
		if hora(primeira) != hora(doc.hora_primeira_convocacao):
			recarregar = True
		doc.hora_primeira_convocacao = primeira
	if "hora_segunda" in dados:
		doc.hora_segunda_convocacao = _hora(dados.get("hora_segunda"))
	if "credenciamento" in dados:
		credenciamento_tipo, credenciamento = separar_pessoa(dados.get("credenciamento"))
		doc.credenciamento_tipo = credenciamento_tipo or None
		doc.credenciamento = credenciamento or None
	if "vagas_delegados" in dados:
		doc.vagas_delegados = max(cint(dados.get("vagas_delegados")), 0)
	return recarregar


@frappe.whitelist(methods=["POST"])
def salvar_visao_geral(name: str, payload: str) -> dict:
	"""Todos os dados de uma vez. A página usa o salvamento automático; fica para a API."""
	doc = _assembleia(name)
	dados = _carregar(payload)
	if str(doc.modified) != str(dados.get("modified") or doc.modified):
		frappe.throw(_("A assembleia foi alterada em outra janela. Recarregue a página para continuar."))
	aplicar_dados(
		doc,
		{
			"tipo": dados.get("tipo") or doc.tipo,
			"data": dados.get("data"),
			"local": dados.get("local"),
			"hora_primeira": dados.get("hora_primeira"),
			"hora_segunda": dados.get("hora_segunda"),
			"credenciamento": dados.get("credenciamento"),
			"vagas_delegados": dados.get("vagas_delegados"),
			"trocar_pauta": dados.get("trocar_pauta"),
		},
	)
	doc.save()
	return dados_da_pagina(doc)


# --------------------------------------------------------------------------------------
# Edital
# --------------------------------------------------------------------------------------


def _aplicar_edital(doc, dados: dict) -> None:
	"""Põe no doc o que veio da etapa Edital, sem gravar.

	Item que já existia é reconhecido pelo `name` e é a mesma linha, atualizada: mantém o
	`name`, o "concluído" e a orientação (editada na Sessão, que o Edital não mostra). Assim
	o salvamento automático não troca as linhas a cada gravação. Item novo recebe a
	orientação da finalidade.
	"""
	existentes = {item.name: item for item in doc.pauta}
	linhas = []
	for item in dados.get("pauta") or []:
		titulo = " ".join(str(item.get("titulo") or "").split())
		if not titulo:
			continue
		finalidade = (item.get("finalidade") or "").strip()
		if finalidade and finalidade not in c.FINALIDADES:
			frappe.throw(_("Finalidade inválida: {0}.").format(finalidade))
		validar_texto(titulo, _("Item da pauta"))
		anterior = existentes.pop(item.get("name") or "", None)
		if "orientacao_conducao" in item:
			orientacao = str(item.get("orientacao_conducao") or "").strip()
		else:
			orientacao = anterior.orientacao_conducao if anterior else ""
		valores = {
			"titulo": titulo,
			"tem_votacao": 1 if item.get("tem_votacao") else 0,
			"finalidade": finalidade,
			"orientacao_conducao": orientacao or c.orientacao_da_finalidade(finalidade),
		}
		if anterior:
			anterior.update(valores)
			linhas.append(anterior)
		else:
			linhas.append({**valores, "concluido": 0})
	if not linhas:
		frappe.throw(_("A pauta precisa de pelo menos um item."))

	# O `idx` vem explícito: uma linha existente guarda o antigo, e a ordem é a da tela.
	doc.set("pauta", [])
	for idx, linha in enumerate(linhas, start=1):
		if isinstance(linha, dict):
			linha["idx"] = idx
		else:
			linha.idx = idx
		doc.append("pauta", linha)

	topo = (dados.get("texto_topo") or "").strip()
	rodape = (dados.get("texto_rodape") or "").strip()
	validar_texto(topo, _("Texto antes da pauta"))
	validar_texto(rodape, _("Texto depois da pauta"))
	doc.edital_texto_topo = topo
	doc.edital_texto_rodape = rodape
	doc.edital_incluir_links = 1 if dados.get("incluir_links") else 0
	doc.data_publicacao_edital = getdate(dados["data_publicacao"]) if dados.get("data_publicacao") else None


@frappe.whitelist(methods=["POST"])
def salvar_edital(name: str, payload: str) -> dict:
	doc = _assembleia(name)
	if cint(doc.edital_publicado):
		frappe.throw(_("O edital já foi publicado e não pode mais ser alterado."))
	dados = _carregar(payload)
	if str(doc.modified) != str(dados.get("modified") or doc.modified):
		frappe.throw(_("A assembleia foi alterada em outra janela. Recarregue a página para continuar."))
	_aplicar_edital(doc, dados)
	doc.save()
	return dados_da_pagina(doc)


@frappe.whitelist(methods=["POST"])
def previa_edital(name: str, payload: str | None = None) -> dict:
	"""O edital como vai sair, com o que está na tela, sem gravar nada."""
	doc = _assembleia(name)
	if payload and not cint(doc.edital_publicado):
		_aplicar_edital(doc, _carregar(payload))
	return {"html": markdown_em_html(conteudo_do_edital(doc))}


@frappe.whitelist(methods=["POST"])
def restaurar_pauta_padrao(name: str) -> dict:
	doc = _assembleia(name)
	if cint(doc.edital_publicado):
		frappe.throw(_("O edital já foi publicado e não pode mais ser alterado."))
	aplicar_pauta_padrao(doc)
	doc.save()
	return dados_da_pagina(doc)


@frappe.whitelist(methods=["POST"])
def restaurar_textos_padrao(name: str) -> dict:
	"""Textos antes e depois da pauta voltam aos das configurações."""
	doc = _assembleia(name)
	if cint(doc.edital_publicado):
		frappe.throw(_("O edital já foi publicado e não pode mais ser alterado."))
	config = configuracoes()
	doc.edital_texto_topo = config.texto_topo_edital or c.TEXTO_TOPO_EDITAL
	doc.edital_texto_rodape = config.texto_rodape_edital or c.TEXTO_RODAPE_EDITAL
	doc.save()
	return dados_da_pagina(doc)


@frappe.whitelist(methods=["POST"])
def marcar_edital_publicado(name: str, fora_do_prazo: int | str = 0) -> dict:
	"""Publica e trava o edital (CA-06.5). Depois do prazo, pede uma segunda confirmação."""
	doc = _assembleia(name)
	if cint(doc.edital_publicado):
		return dados_da_pagina(doc)
	config = configuracoes()
	prazo = add_days(doc.data, -(cint(config.dias_limite_edital) or 30))
	if getdate() > getdate(prazo) and not cint(fora_do_prazo):
		# Como dado, e não como erro: a tela abre a confirmação em vez do toast vermelho.
		return {"precisa_confirmar": True, "prazo": str(prazo), "dias": cint(config.dias_limite_edital)}

	doc.edital_publicado = 1
	doc.edital_publicado_em = now_datetime()
	if not doc.data_publicacao_edital:
		doc.data_publicacao_edital = getdate()
	doc.save()

	# O PDF final no timbrado. Se o Drive falhar, o edital continua publicado e o PDF
	# final é gerado no primeiro "Baixar PDF".
	aviso = ""
	try:
		from gris.api.assembleias.documentos import gerar_edital_final

		gerar_edital_final(doc)
	except Exception as erro:
		frappe.clear_messages()
		if not isinstance(erro, frappe.ValidationError):
			frappe.log_error(frappe.get_traceback(), f"Edital final da assembleia {doc.name}")
		aviso = _(
			"O edital foi publicado, mas o PDF final não pôde ser gerado agora ({0}). "
			'Use "Baixar PDF" para tentar de novo.'
		).format(str(erro) or _("erro no Drive"))
	doc.reload()
	return {**dados_da_pagina(doc), "aviso": aviso}


# --------------------------------------------------------------------------------------
# Salvamento automático: checklist e condução (a ata usa o mesmo caminho em ata.py)
# --------------------------------------------------------------------------------------


def aplicar_checklist(doc, marcacoes: dict) -> None:
	for etapa in doc.checklist:
		if etapa.chave not in marcacoes or etapa.chave == c.CHECKLIST_DIVULGAR_EDITAL:
			continue
		marcado = 1 if marcacoes[etapa.chave] else 0
		if marcado == cint(etapa.concluido):
			continue
		etapa.concluido = marcado
		etapa.concluido_em = now_datetime() if marcado else None
		etapa.concluido_por = frappe.session.user if marcado else None


def aplicar_conducao(doc, itens: dict) -> None:
	por_nome = {item.name: item for item in doc.pauta}
	for nome, valores in (itens or {}).items():
		item = por_nome.get(nome)
		if not item or not isinstance(valores, dict):
			continue
		if "concluido" in valores:
			item.concluido = 1 if valores["concluido"] else 0
		if "orientacao_conducao" in valores:
			item.orientacao_conducao = str(valores["orientacao_conducao"] or "").strip()


@frappe.whitelist(methods=["POST"])
def salvar_campos(name: str, campos: str, modified: str) -> dict:
	"""Gravação automática da página inteira.

	Chaves aceitas: `dados` (convocação, credenciamento e vagas, parciais), `edital` (a
	etapa Edital inteira), `checklist`, `pauta` (concluído e orientação da condução) e
	`ata`. Com `dados` ou `edital`, a resposta traz a página atualizada e diz se a tela
	precisa recarregar.
	"""
	doc = _assembleia(name)
	if str(doc.modified) != str(modified):
		return {"conflito": True}
	dados = _carregar(campos)
	recarregar = False
	if "dados" in dados:
		recarregar = aplicar_dados(doc, dados["dados"] or {})
	if "edital" in dados:
		if cint(doc.edital_publicado):
			frappe.throw(_("O edital já foi publicado e não pode mais ser alterado."))
		_aplicar_edital(doc, dados["edital"] or {})
	if "checklist" in dados:
		aplicar_checklist(doc, dados["checklist"] or {})
	if "pauta" in dados:
		aplicar_conducao(doc, dados["pauta"] or {})
	if "ata" in dados:
		from gris.api.assembleias.ata import aplicar_campos

		aplicar_campos(doc, dados["ata"] or {})
	doc.save()

	from gris.api.assembleias.ata import contar_marcadores

	resposta = {
		"modified": str(doc.modified),
		"salvo_em": now_datetime().strftime("%H:%M"),
		"pauta": {item.name: markdown_em_html(item.orientacao_conducao) for item in doc.pauta},
		"marcadores": contar_marcadores(doc.ata_texto),
		"presidente_nome": nome_da_pessoa(doc.presidente_tipo, doc.presidente),
		"secretario_nome": nome_da_pessoa(doc.secretario_tipo, doc.secretario),
	}
	if "dados" in dados or "edital" in dados:
		resposta["pagina"] = dados_da_pagina(doc)
		resposta["recarregar"] = recarregar
	return resposta
