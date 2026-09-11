"""Sincronizacao dos feriados do ano a partir de dados abertos.

Fonte: repositorio publico joaopbini/feriados-brasil, servido pelo GitHub em
arquivos JSON por ano e por abrangencia. Nao exige chave de acesso nem
assinatura — a integracao anterior dependia de uma API paga e parou de
responder quando a credencial deixou de valer.

Sao sincronizados os feriados nacionais, os estaduais da UF do municipio
configurado e os municipais do proprio municipio, identificado pelo codigo do
IBGE em "Configuracoes de Feriados".
"""

import re
import unicodedata
from datetime import datetime

import frappe
import requests
from frappe.utils import getdate

from gris.utils.job_logger import definir_resumo, metrica, obter_logger

URL_BASE = "https://raw.githubusercontent.com/joaopbini/feriados-brasil/master/dados/feriados"
TEMPO_LIMITE_SEGUNDOS = 60

# Os dois primeiros digitos do codigo do IBGE do municipio identificam a UF.
UF_POR_PREFIXO_IBGE = {
	"11": "RO",
	"12": "AC",
	"13": "AM",
	"14": "RR",
	"15": "PA",
	"16": "AP",
	"17": "TO",
	"21": "MA",
	"22": "PI",
	"23": "CE",
	"24": "RN",
	"25": "PB",
	"26": "PE",
	"27": "AL",
	"28": "SE",
	"29": "BA",
	"31": "MG",
	"32": "ES",
	"33": "RJ",
	"35": "SP",
	"41": "PR",
	"42": "SC",
	"43": "RS",
	"50": "MS",
	"51": "MT",
	"52": "GO",
	"53": "DF",
}

# A tela do calendario escolhe o badge pelo tipo (gris/www/calendario/visualizar.py),
# que usa esta grafia. A fonte entrega o tipo em caixa alta.
TIPO_POR_ABRANGENCIA = {
	"nacional": "Nacional",
	"estadual": "Estadual",
	"municipal": "Municipal",
}


def _sem_acento(texto: str | None) -> str:
	"""Normaliza para comparar nomes que so diferem em acento ou caixa."""
	decomposto = unicodedata.normalize("NFD", texto or "")
	return "".join(c for c in decomposto if unicodedata.category(c) != "Mn").strip().lower()


def _identificador(data_iso: str, nome: str) -> str:
	"""Identificador estavel do feriado, derivado da data e do nome.

	A fonte nao traz chave primaria, entao o mesmo feriado precisa gerar sempre
	o mesmo id para que a sincronizacao seja idempotente.
	"""
	base = re.sub(r"[^a-z0-9]+", "-", _sem_acento(nome)).strip("-")
	return f"{data_iso}-{base}"[:140]


def _baixar(abrangencia: str, ano: int, logger) -> list[dict]:
	"""Baixa o arquivo de uma abrangencia. Ano ainda nao publicado devolve lista vazia."""
	url = f"{URL_BASE}/{abrangencia}/json/{ano}.json"
	resposta = requests.get(url, timeout=TEMPO_LIMITE_SEGUNDOS)

	if resposta.status_code == 404:
		logger.warning(f"A fonte ainda nao publicou os feriados {abrangencia}s de {ano}.")
		return []

	resposta.raise_for_status()
	dados = resposta.json()

	if not isinstance(dados, list):
		raise ValueError(f"Formato inesperado em {url}: esperava uma lista.")

	return dados


def _converter(registro: dict, abrangencia: str) -> dict | None:
	"""Converte um registro da fonte no formato do DocType. Devolve None se a data for invalida."""
	try:
		data = datetime.strptime(registro.get("data") or "", "%d/%m/%Y").date()
	except ValueError:
		return None

	nome = (registro.get("nome") or "").strip()
	if not nome:
		return None

	data_iso = data.isoformat()
	return {
		"id": _identificador(data_iso, nome),
		"nome": nome,
		"data": data,
		"tipo": TIPO_POR_ABRANGENCIA[abrangencia],
		"descricao": (registro.get("descricao") or "").strip() or None,
	}


def _feriados_do_ano(ano: int, uf: str, codigo_ibge: str, logger) -> tuple[list[dict], int]:
	"""Junta as tres abrangencias, ja filtradas e sem repeticao de data.

	Um feriado nacional costuma aparecer de novo na lista municipal (a lei do
	municipio repete a data). Como o calendario mostra um item por feriado, a
	primeira abrangencia a declarar a data vence: nacional, depois estadual,
	depois municipal.
	"""
	filtros = {
		"nacional": lambda r: True,
		"estadual": lambda r: (r.get("uf") or "") == uf,
		"municipal": lambda r: str(r.get("codigo_ibge") or "") == codigo_ibge,
	}

	feriados: dict[tuple[str, str], dict] = {}
	ignorados = 0

	for abrangencia, filtro in filtros.items():
		registros = [r for r in _baixar(abrangencia, ano, logger) if filtro(r)]
		logger.info(f"A fonte devolveu {len(registros)} feriado(s) {abrangencia}(is) de {ano}.")

		for registro in registros:
			feriado = _converter(registro, abrangencia)
			if not feriado:
				logger.warning(f"Registro com data invalida, ignorado: {registro}.")
				ignorados += 1
				continue

			chave = (feriado["data"].isoformat(), _sem_acento(feriado["nome"]))
			feriados.setdefault(chave, feriado)

	return sorted(feriados.values(), key=lambda f: (f["data"], f["nome"])), ignorados


def _indexar_existentes(ano: int) -> tuple[dict, dict]:
	"""Indexa os feriados ja gravados no ano, por id e por data + nome.

	O indice por data + nome reaproveita o registro criado pela integracao
	anterior, cujo id vinha da API antiga: sem ele, a troca de fonte
	duplicaria cada feriado do ano corrente no calendario.
	"""
	existentes = frappe.get_all(
		"Feriados",
		filters={"data": ["between", [f"{ano}-01-01", f"{ano}-12-31"]]},
		fields=["name", "data", "nome"],
	)

	por_id = {e.name: e.name for e in existentes}
	por_data_e_nome = {(getdate(e.data).isoformat(), _sem_acento(e.nome)): e.name for e in existentes}
	return por_id, por_data_e_nome


def _gravar(feriado: dict, por_id: dict, por_data_e_nome: dict, logger) -> str:
	"""Cria ou atualiza um feriado. Devolve 'criado', 'atualizado' ou 'sem_alteracao'."""
	chave = (feriado["data"].isoformat(), _sem_acento(feriado["nome"]))
	name = por_id.get(feriado["id"]) or por_data_e_nome.get(chave)

	if not name:
		doc = frappe.get_doc({"doctype": "Feriados", **feriado})
		doc.insert()
		logger.info(f"Feriado criado: {doc.nome} ({doc.data}).")
		return "criado"

	doc = frappe.get_doc("Feriados", name)
	alterou = False

	for campo in ("nome", "data", "tipo", "descricao"):
		atual = getdate(doc.data) if campo == "data" else (doc.get(campo) or None)
		if atual != feriado[campo]:
			doc.set(campo, feriado[campo])
			alterou = True

	if not alterou:
		return "sem_alteracao"

	doc.save()
	logger.info(f"Feriado atualizado: {doc.nome} ({doc.data}).")
	return "atualizado"


def sync_feriados():
	"""Job diario: sincroniza os feriados do municipio configurado com a fonte aberta."""
	logger = obter_logger("sync_feriados")

	settings = frappe.get_single("Configuracoes de Feriados")
	codigo_ibge = (settings.codigo_municipio_ibge or "").strip()

	if not codigo_ibge:
		logger.warning(
			"Sincronizacao de feriados ignorada: falta o codigo do municipio em Configuracoes de Feriados."
		)
		definir_resumo("Integração de feriados não configurada — nada foi sincronizado.")
		return

	uf = UF_POR_PREFIXO_IBGE.get(codigo_ibge[:2])
	if not uf:
		logger.warning(
			f"Sincronizacao de feriados ignorada: o codigo {codigo_ibge} nao corresponde "
			"a nenhuma UF. Confira o codigo do municipio no IBGE."
		)
		definir_resumo(f"Código de município inválido ({codigo_ibge}) — nada foi sincronizado.")
		return

	ano = datetime.now().year

	criados = 0
	atualizados = 0
	sem_alteracao = 0
	ignorados = 0

	try:
		logger.info(f"Consultando feriados de {ano} para o municipio {codigo_ibge} ({uf}).")
		feriados, ignorados = _feriados_do_ano(ano, uf, codigo_ibge, logger)

		if not feriados:
			definir_resumo(f"A fonte não tem feriados de {ano} — nada foi sincronizado.")
			return

		por_id, por_data_e_nome = _indexar_existentes(ano)

		for feriado in feriados:
			resultado = _gravar(feriado, por_id, por_data_e_nome, logger)
			if resultado == "criado":
				criados += 1
			elif resultado == "atualizado":
				atualizados += 1
			else:
				sem_alteracao += 1

		frappe.db.commit()

		metrica("criados", criados, incrementar=False)
		metrica("atualizados", atualizados, incrementar=False)
		metrica("sem_alteracao", sem_alteracao, incrementar=False)
		metrica("ignorados", ignorados, incrementar=False)
		definir_resumo(
			f"{criados} feriado(s) criado(s), {atualizados} atualizado(s) e "
			f"{sem_alteracao} sem alteração para {ano}."
		)

	except Exception as e:
		logger.exception(f"Falha ao sincronizar os feriados de {ano}: {e!s}")
		definir_resumo(f"A sincronização de feriados de {ano} falhou.")
		frappe.log_error(title="Feriados Sync Error", message=f"{e!s}\n\n{frappe.get_traceback()}")
