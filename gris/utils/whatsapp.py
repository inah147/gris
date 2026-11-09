from __future__ import annotations

import random
import re
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import frappe
import requests
from frappe import _
from frappe.utils import get_datetime, now_datetime

from .whatsapp_errors import (
	WhatsAppConfigurationError,
	WhatsAppDesconectadoError,
	WhatsAppNumberNotFoundError,
	WhatsAppRequestError,
)

SETTINGS_DOCTYPE = "Configuracoes WhatsApp"

# Telas de configuração que têm um Select de grupo alimentado pela Evolution API.
# `listar_grupos_whatsapp_para_select` só aceita permissão vinda de uma delas.
DOCTYPES_COM_SELECT_DE_GRUPO: frozenset[str] = frozenset(
	{"Configuracoes de Recepcao", "Configuracoes de Desenvolvimento", "Configuracoes de Acessos"}
)

DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3
# 500 fica de fora: a Evolution responde 500 também depois de a mensagem ter saído, e
# repetir o POST mandaria a mesma mensagem duas vezes.
RETRYABLE_STATUS_CODES = {429, 502, 503, 504}

# ─── Cadência ─────────────────────────────────────────────────────────────────
# Todo envio do GRIS sai pelo mesmo número. Em 24/10/2026 uma rajada de ~150 PDFs em dois
# minutos (lembrete da festa) foi seguida da remoção do aparelho pelo WhatsApp, e nada mais
# saiu por 16 dias. Daí a fila única: um envio por vez, com um intervalo aleatório desde o
# último, valendo para os dois workers e para os envios síncronos.
INTERVALO_MIN = 4.0
INTERVALO_MAX = 6.0
LOCK_ENVIO = "gris_whatsapp_envio"
# Num job, esperar a vez é melhor do que falhar. Numa requisição web, quem clicou não pode
# ficar minutos parado: depois deste tempo a mensagem volta como falha.
LOCK_TIMEOUT_JOB = 240
LOCK_TIMEOUT_REQUISICAO = 25
# Os jobs de envio esperam a vez na fila antes do POST.
TIMEOUT_JOB_ENVIO = 300

ESTADO_CONECTADO = "open"


# ─── Infraestrutura interna ───────────────────────────────────────────────────


def _logger():
	return frappe.logger("whatsapp", allow_site=True, file_count=10)


def _get_config() -> dict:
	"""Lê e valida as configurações da Evolution API a partir do DocType Single."""
	settings = frappe.get_single(SETTINGS_DOCTYPE)

	if not settings.habilitar_integracao:
		raise WhatsAppConfigurationError(
			"Integração com WhatsApp está desabilitada. Habilite em Configuracoes WhatsApp."
		)

	url_api = (settings.get("url_api") or "").strip().rstrip("/")
	api_key = settings.get_password("api_key", raise_exception=False)
	nome_instancia = (settings.get("nome_instancia") or "").strip()

	if not url_api:
		raise WhatsAppConfigurationError("URL da API não configurada em Configuracoes WhatsApp.")
	if not api_key:
		raise WhatsAppConfigurationError("API Key não configurada em Configuracoes WhatsApp.")
	if not nome_instancia:
		raise WhatsAppConfigurationError("Nome da instância não configurado em Configuracoes WhatsApp.")

	return {"url_api": url_api, "api_key": api_key, "nome_instancia": nome_instancia}


def _build_headers(api_key: str) -> dict:
	return {"apikey": api_key, "Content-Type": "application/json"}


def _normalize_phone(number: str) -> str:
	"""Normaliza número de telefone para o formato da Evolution API: 55 + DDD + número.

	Aceita formatos como: +5511999999999, 5511999999999, 11999999999, (11) 99999-9999.
	Números de grupo (JID @g.us) são retornados sem modificação.
	"""
	if "@" in number:
		return number

	digits = re.sub(r"\D", "", number)

	if digits.startswith("55") and len(digits) >= 12:
		# Already has country code; check for duplicate DDD: 55 + DDD + DDD + number
		# e.g. 551111971872252 → 5511971872252
		if len(digits) >= 14 and digits[2:4] == digits[4:6]:
			digits = digits[:2] + digits[4:]
		return digits

	# No country code; check for duplicate DDD: DDD + DDD + number
	# e.g. 1111971872252 (13 digits) → 11971872252 (11 digits)
	if len(digits) > 11 and digits[:2] == digits[2:4]:
		digits = digits[2:]

	return f"55{digits}"


def _e_grupo(numero: str) -> bool:
	return (numero or "").endswith("@g.us")


def _post(
	endpoint: str,
	payload: dict,
	*,
	params: dict | None = None,
	config: dict | None = None,
) -> dict:
	"""Executa POST na Evolution API com retry automático para erros transitórios."""
	if config is None:
		config = _get_config()

	url = f"{config['url_api']}{endpoint}"
	headers = _build_headers(config["api_key"])
	logger = _logger()

	for attempt in range(1, MAX_RETRIES + 1):
		try:
			response = requests.post(
				url, headers=headers, params=params, json=payload, timeout=DEFAULT_TIMEOUT
			)
		except requests.ReadTimeout as exc:
			# O pedido chegou e a resposta não veio: repetir pode duplicar a mensagem.
			raise WhatsAppRequestError(
				f"A Evolution API não respondeu em {DEFAULT_TIMEOUT}s; a mensagem pode ter sido entregue."
			) from exc
		except requests.RequestException as exc:
			raise WhatsAppRequestError(f"Falha de conexão ao chamar Evolution API: {exc}") from exc

		if response.status_code < 400:
			try:
				return response.json()
			except ValueError:
				# A Evolution aceitou; um corpo ilegível não desfaz o envio.
				return {}

		if response.status_code not in RETRYABLE_STATUS_CODES or attempt == MAX_RETRIES:
			try:
				detail = response.json()
			except ValueError:
				detail = response.text or "Sem detalhes."
			# Evolution API returns 400 with exists:False when number is not on WhatsApp
			if response.status_code == 400 and isinstance(detail, dict):
				messages = (detail.get("response") or {}).get("message", [])
				if isinstance(messages, list) and any(
					isinstance(m, dict) and m.get("exists") is False for m in messages
				):
					number = messages[0].get("number", "") if messages else ""
					raise WhatsAppNumberNotFoundError(f"Número {number} não está registrado no WhatsApp.")
			raise WhatsAppRequestError(
				f"Evolution API retornou HTTP {response.status_code}: {detail}",
				status_code=response.status_code,
			)

		logger.warning(
			f"Evolution API HTTP {response.status_code} na tentativa {attempt}/{MAX_RETRIES}. Retentando..."
		)
		time.sleep(2 ** (attempt - 1))

	raise WhatsAppRequestError("Número máximo de tentativas atingido.")  # pragma: no cover


def _get(
	endpoint: str,
	*,
	params: dict | None = None,
	config: dict | None = None,
) -> dict | list:
	"""Executa GET na Evolution API com retry automático para erros transitórios."""
	if config is None:
		config = _get_config()

	url = f"{config['url_api']}{endpoint}"
	headers = _build_headers(config["api_key"])
	logger = _logger()

	for attempt in range(1, MAX_RETRIES + 1):
		try:
			response = requests.get(url, headers=headers, params=params, timeout=DEFAULT_TIMEOUT)
		except requests.RequestException as exc:
			raise WhatsAppRequestError(f"Falha de conexão ao chamar Evolution API: {exc}") from exc

		if response.status_code < 400:
			try:
				return response.json()
			except ValueError as exc:
				raise WhatsAppRequestError("Evolution API retornou resposta inválida.") from exc

		if response.status_code not in RETRYABLE_STATUS_CODES or attempt == MAX_RETRIES:
			try:
				detail = response.json()
			except ValueError:
				detail = response.text or "Sem detalhes."
			raise WhatsAppRequestError(
				f"Evolution API retornou HTTP {response.status_code}: {detail}",
				status_code=response.status_code,
			)

		logger.warning(
			f"Evolution API HTTP {response.status_code} na tentativa {attempt}/{MAX_RETRIES}. Retentando..."
		)
		time.sleep(2 ** (attempt - 1))

	raise WhatsAppRequestError("Número máximo de tentativas atingido.")  # pragma: no cover


# ─── Estado da conexão ────────────────────────────────────────────────────────


def estado_da_conexao(config: dict | None = None) -> str:
	"""Estado da sessão da instância com o WhatsApp, como a Evolution informa.

	``open`` é a única situação em que algo sai. ``close`` quer dizer que o aparelho foi
	desvinculado e alguém precisa ler o QR code de novo; ``connecting`` é a Evolution
	tentando reabrir a sessão.
	"""
	config = config or _get_config()
	resposta = _get(f"/instance/connectionState/{config['nome_instancia']}", config=config)
	instancia = resposta.get("instance") if isinstance(resposta, dict) else None
	return str((instancia or {}).get("state") or "desconhecido")


def _explicar_falha(erro: Exception, config: dict | None, numero: str) -> Exception:
	"""Troca o erro cru da Evolution por um que diga o que fazer.

	Só olha as respostas HTTP de erro: são elas que a Evolution devolve quando a sessão caiu,
	e de um jeito que não diz isso. Com a instância desconectada, o envio a um número falha
	com 500 ``Cannot read properties of undefined (reading 'onWhatsApp')`` e o envio a um
	grupo com 400 ``['[object Object]']`` (o "grupo não encontrado" dela, serializado errado).
	"""
	if not isinstance(erro, WhatsAppRequestError) or erro.status_code is None or not config:
		return erro

	try:
		estado = estado_da_conexao(config)
	except Exception:
		estado = None

	if estado and estado != ESTADO_CONECTADO:
		return WhatsAppDesconectadoError(
			f"WhatsApp desconectado (estado na Evolution: {estado}). Nenhuma mensagem sai até "
			f"alguém reconectar a instância {config['nome_instancia']} no Evolution Manager, lendo o "
			f"QR code com o celular do grupo. Resposta da Evolution: {erro}",
			status_code=erro.status_code,
		)

	detalhe = str(erro)
	if "onWhatsApp" in detalhe:
		explicacao = "A Evolution não conseguiu consultar o número: a sessão com o WhatsApp não está ativa."
	elif "[object Object]" in detalhe and _e_grupo(numero):
		explicacao = (
			"A Evolution não encontrou o grupo: o número do GRIS saiu do grupo ou a sessão com o "
			"WhatsApp não está ativa."
		)
	else:
		return erro

	return WhatsAppRequestError(
		f"{explicacao} Resposta da Evolution: {detalhe}", status_code=erro.status_code
	)


# ─── Fila única de envio ──────────────────────────────────────────────────────


def _lock_timeout() -> int:
	return LOCK_TIMEOUT_REQUISICAO if getattr(frappe.local, "request", None) else LOCK_TIMEOUT_JOB


def _ultimo_envio_em():
	"""Quando saiu o último envio bem-sucedido, por qualquer worker.

	O commit antes da leitura é o que a faz enxergar o envio que o outro worker acabou de
	gravar: sem ele, a leitura devolveria o snapshot do início da transação, tirado antes de
	esperar a vez. Ele não muda nada para quem chamou, porque todo envio já termina em commit
	(``_registrar_sucesso`` ou ``_registrar_erro``). Um ``FOR UPDATE`` resolveria o mesmo
	problema, mas ficaria preso atrás de qualquer transação longa que tocasse a configuração.
	"""
	frappe.db.commit()  # nosemgrep
	linha = frappe.db.sql(
		"SELECT `value` FROM `tabSingles` WHERE `doctype` = %s AND `field` = 'ultimo_envio_em'",
		(SETTINGS_DOCTYPE,),
	)
	return get_datetime(linha[0][0]) if linha and linha[0][0] else None


def _aguardar_intervalo() -> None:
	"""Dorme o que falta para o intervalo mínimo desde o último envio bem-sucedido."""
	ultimo = _ultimo_envio_em()
	if not ultimo:
		return

	decorrido = (now_datetime() - ultimo).total_seconds()
	espera = random.uniform(INTERVALO_MIN, INTERVALO_MAX) - decorrido
	if espera > 0:
		time.sleep(espera)


@contextmanager
def _vez_de_enviar() -> Iterator[None]:
	"""Um envio por vez em todo o site, e nunca dois colados.

	O lock nomeado do MariaDB é da conexão, não da transação: vale entre os workers, não
	some com o commit que o envio faz e é solto no ``finally`` mesmo quando o POST falha.
	"""
	timeout = _lock_timeout()
	obtido = frappe.db.sql("SELECT GET_LOCK(%s, %s)", (LOCK_ENVIO, timeout))
	if not obtido or obtido[0][0] != 1:
		raise WhatsAppRequestError(
			f"A fila de envio do WhatsApp ficou ocupada por mais de {timeout}s; a mensagem não foi enviada."
		)
	try:
		_aguardar_intervalo()
		yield
	finally:
		frappe.db.sql("SELECT RELEASE_LOCK(%s)", (LOCK_ENVIO,))


# ─── Log de mensagens ─────────────────────────────────────────────────────────

LOG_DOCTYPE = "Log de Mensagem"

TIPO_NAO_IDENTIFICADO = "Não identificado"

STATUS_ENVIADA = "Enviada"
STATUS_FALHOU = "Falhou"

ENTREGA_AGUARDANDO = "Aguardando confirmação"
ENTREGA_GRUPO = "Não rastreável (grupo)"


def _registrar_log(
	contexto: dict | None,
	*,
	numero: str,
	conteudo: str,
	status: str,
	erro: str = "",
	id_mensagem: str | None = None,
	jid_destino: str | None = None,
	entrega: str | None = None,
) -> None:
	"""Grava a linha do ``Log de Mensagem``.

	``contexto`` é o que o chamador sabe e o transporte não: de qual jovem a mensagem fala,
	que mensagem é essa e quem é o destinatário. Vem opcional porque nem todo envio do GRIS
	nasce no funil de recepção — sem ele a linha ainda registra número, texto e status.

	``id_mensagem`` e ``jid_destino`` são o ``key`` que a Evolution devolve. "Enviada" quer
	dizer só que a Evolution aceitou; é por esse id que
	``gris.utils.whatsapp_entrega.conciliar_entregas`` descobre depois se a mensagem chegou.

	Grupos ficam sem nome aqui de propósito: só a Evolution API sabe o assunto do grupo, e
	buscá-lo no envio poria uma chamada de rede no caminho de cada mensagem. Quem resolve o
	nome é a leitura (``gris.www.recepcao.ficha_registro.listar_mensagens_enviadas``), uma vez
	por consulta.

	Nunca deixa uma falha do log derrubar o envio: a mensagem já foi (ou não foi) entregue, e
	perder o registro é menos grave do que transformar isso em erro para o chamador.
	"""
	contexto = contexto or {}
	try:
		frappe.get_doc(
			{
				"doctype": LOG_DOCTYPE,
				"enviada_em": now_datetime(),
				"status": status,
				"novo_associado": contexto.get("novo_associado"),
				"assunto": contexto.get("assunto"),
				"destinatario_tipo": contexto.get("destinatario_tipo") or TIPO_NAO_IDENTIFICADO,
				"destinatario_nome": contexto.get("destinatario_nome") or "",
				"destinatario_numero": numero,
				"conteudo": conteudo,
				"erro": erro[:2000] if erro else "",
				"id_mensagem": id_mensagem or "",
				"jid_destino": jid_destino or "",
				"entrega": entrega or "",
			}
		).insert(ignore_permissions=True)
	except Exception:
		_logger().exception(f"Falha ao registrar o log da mensagem para {numero}.")


def _registrar_sucesso() -> None:
	frappe.db.set_single_value(SETTINGS_DOCTYPE, {"ultimo_envio_em": now_datetime(), "ultimo_erro": ""})
	# Commit explícito: a mensagem já foi entregue pelo provedor. O marcador de
	# último envio não pode ser desfeito por um rollback do chamador.
	frappe.db.commit()  # nosemgrep


def _registrar_erro(contexto: str) -> None:
	tb = frappe.get_traceback()
	frappe.log_error(tb, f"WhatsApp:{contexto}")
	frappe.db.set_single_value(SETTINGS_DOCTYPE, {"ultimo_erro": tb[-5000:]})
	# Commit explícito: o chamador propaga a exceção logo em seguida e o rollback
	# apagaria justamente o registro do erro que se quer diagnosticar.
	frappe.db.commit()  # nosemgrep


# ─── Funções síncronas (chamadas diretamente ou via enqueue) ──────────────────


def _enviar(
	rota: str,
	montar_payload: Callable[[], dict],
	*,
	numero: str,
	conteudo: str,
	contexto: dict | None,
	rotulo: str,
) -> dict:
	"""Caminho único de toda mensagem: monta, espera a vez, envia e registra.

	Tudo o que pode falhar fica dentro do ``try`` — configuração, montagem do payload, a fila
	e o POST —, para que nenhuma mensagem se perca sem deixar a linha "Falhou" no log.
	"""
	config: dict | None = None
	enviado = False
	try:
		config = _get_config()
		payload = montar_payload()
		with _vez_de_enviar():
			result = _post(f"{rota}/{config['nome_instancia']}", payload, config=config)
			enviado = True
			# Ainda com a vez: o próximo da fila lê `ultimo_envio_em` para saber quanto esperar,
			# e só enxerga este envio depois do commit de `_registrar_sucesso`.
			_registrar_enviada(result, numero=numero, conteudo=conteudo, contexto=contexto)
			_registrar_sucesso()
	except Exception as erro:
		if enviado:
			# A mensagem saiu; o que falhou foi só o registro. Não é um "Falhou".
			raise
		explicado = _explicar_falha(erro, config, numero)
		_registrar_log(contexto, numero=numero, conteudo=conteudo, status=STATUS_FALHOU, erro=str(explicado))
		_registrar_erro(rotulo)
		if explicado is erro:
			raise
		raise explicado from erro

	return result


def _registrar_enviada(result, *, numero: str, conteudo: str, contexto: dict | None) -> None:
	chave = (result.get("key") if isinstance(result, dict) else None) or {}
	id_mensagem = chave.get("id")
	if _e_grupo(numero):
		entrega = ENTREGA_GRUPO
	else:
		entrega = ENTREGA_AGUARDANDO if id_mensagem else ""
	_registrar_log(
		contexto,
		numero=numero,
		conteudo=conteudo,
		status=STATUS_ENVIADA,
		id_mensagem=id_mensagem,
		jid_destino=chave.get("remoteJid"),
		entrega=entrega,
	)


def _enviar_texto_sync(numero: str, mensagem: str, contexto: dict | None = None) -> dict:
	result = _enviar(
		"/message/sendText",
		lambda: {"number": _normalize_phone(numero), "text": mensagem},
		numero=numero,
		conteudo=mensagem,
		contexto=contexto,
		rotulo=f"enviar_texto:{numero}",
	)
	_logger().info(f"Mensagem de texto enviada para {numero}.")
	return result


_TIPOS_DE_MIDIA = {"image", "document", "audio", "video"}


def _enviar_midia_sync(
	numero: str,
	tipo: str,
	url_ou_base64: str,
	caption: str = "",
	*,
	nome_arquivo: str = "",
	mimetype: str = "",
	contexto: dict | None = None,
) -> dict:
	def montar() -> dict:
		if tipo not in _TIPOS_DE_MIDIA:
			raise WhatsAppRequestError(
				f"Tipo de mídia inválido: '{tipo}'. Use: {', '.join(sorted(_TIPOS_DE_MIDIA))}."
			)
		payload: dict = {
			"number": _normalize_phone(numero),
			"mediatype": tipo,
			"media": url_ou_base64,
		}
		if caption:
			payload["caption"] = caption
		# Sem nome e tipo, o documento chega sem extensão e o celular não sabe abri-lo.
		if nome_arquivo:
			payload["fileName"] = nome_arquivo
		if mimetype:
			payload["mimetype"] = mimetype
		return payload

	# O log guarda a legenda e o nome do arquivo, nunca o conteúdo em base64.
	conteudo_log = "\n".join(parte for parte in (caption, f"[anexo: {nome_arquivo or tipo}]") if parte)
	result = _enviar(
		"/message/sendMedia",
		montar,
		numero=numero,
		conteudo=conteudo_log,
		contexto=contexto,
		rotulo=f"enviar_midia:{numero}:{tipo}",
	)
	_logger().info(f"Mídia ({tipo}) enviada para {numero}.")
	return result


def _enviar_para_grupo_sync(
	grupo_jid: str,
	mensagem: str,
	*,
	mencionar_todos: bool = False,
	mencionar: list[str] | None = None,
	contexto: dict | None = None,
) -> dict:
	def montar() -> dict:
		payload: dict = {"number": grupo_jid, "text": mensagem}
		# `mentionsEveryOne` só entra no payload quando verdadeiro: a Evolution menciona todo
		# mundo mesmo quando a chave chega com `false`.
		if mencionar_todos:
			payload["mentionsEveryOne"] = True
		if mencionar:
			numeros = [_normalize_phone(numero) for numero in mencionar if (numero or "").strip()]
			if numeros:
				payload["mentioned"] = list(dict.fromkeys(numeros))
		return payload

	result = _enviar(
		"/message/sendText",
		montar,
		numero=grupo_jid,
		conteudo=mensagem,
		contexto=contexto,
		rotulo=f"enviar_para_grupo:{grupo_jid}",
	)
	_logger().info(f"Mensagem enviada para grupo {grupo_jid}.")
	return result


def _adicionar_participantes_no_grupo_sync(grupo_jid: str, numeros: list[str]) -> dict:
	config = _get_config()
	participantes = [_normalize_phone(numero) for numero in numeros if (numero or "").strip()]
	participantes = list(dict.fromkeys(participantes))
	if not participantes:
		raise WhatsAppRequestError("Nenhum número válido para adicionar ao grupo.")

	enviado = False
	try:
		with _vez_de_enviar():
			result = _post(
				f"/group/updateParticipant/{config['nome_instancia']}",
				{"action": "add", "participants": participantes},
				params={"groupJid": grupo_jid},
				config=config,
			)
			enviado = True
			_registrar_sucesso()
	except Exception:
		if not enviado:
			_registrar_erro(f"adicionar_participantes_no_grupo:{grupo_jid}")
		raise

	_logger().info(f"{len(participantes)} participante(s) adicionado(s) ao grupo {grupo_jid}.")
	return result


def _enviar_mensagem_formatada_sync(
	numero: str,
	titulo: str,
	descricao: str,
	botoes: list[dict] | None = None,
	contexto: dict | None = None,
) -> dict:
	def montar() -> dict:
		payload: dict = {
			"number": _normalize_phone(numero),
			"title": titulo,
			"description": descricao,
		}
		if botoes:
			payload["buttons"] = botoes
		return payload

	conteudo = f"*{titulo}*\n{descricao}" if titulo else descricao
	result = _enviar(
		"/message/sendButtons",
		montar,
		numero=numero,
		conteudo=conteudo,
		contexto=contexto,
		rotulo=f"enviar_mensagem_formatada:{numero}",
	)
	_logger().info(f"Mensagem formatada enviada para {numero}.")
	return result


# ─── API Pública ──────────────────────────────────────────────────────────────


def listar_grupos_whatsapp(*, get_participants: bool = False) -> list[dict[str, str]]:
	"""Lista os grupos da instância WhatsApp conectada na Evolution API.

	Args:
		get_participants: Quando True, solicita também os participantes no endpoint da Evolution.

	Returns:
		Lista de grupos no formato [{"id": "...@g.us", "subject": "Nome do grupo"}].

	Raises:
		WhatsAppConfigurationError: Integração desabilitada ou configuração incompleta.
		WhatsAppRequestError: Falha de rede, HTTP ou payload inválido ao chamar a Evolution API.
	"""
	config = _get_config()
	params = {"getParticipants": str(bool(get_participants)).lower()}
	result = _get(
		f"/group/fetchAllGroups/{config['nome_instancia']}",
		params=params,
		config=config,
	)

	if not isinstance(result, list):
		raise WhatsAppRequestError("Formato inválido na resposta de listagem de grupos.")

	grupos: list[dict[str, str]] = []
	for item in result:
		if not isinstance(item, dict):
			continue

		grupo_id = str(item.get("id") or "").strip()
		if not grupo_id:
			continue

		subject = str(item.get("subject") or "").strip()
		grupos.append({"id": grupo_id, "subject": subject or grupo_id})

	return sorted(grupos, key=lambda grupo: grupo["subject"].casefold())


@frappe.whitelist()
def listar_grupos_whatsapp_para_select(
	doctype: str = "Configuracoes de Recepcao",
) -> list[dict[str, str]]:
	"""Retorna opções de grupos WhatsApp para uso em campos Select no Desk.

	`doctype` diz de qual tela de configuração veio a chamada, para a permissão
	ser checada no documento que a pessoa está de fato editando. A allowlist
	existe porque o parâmetro vem do cliente: sem ela, qualquer DocType em que o
	usuário tenha `write` liberaria a listagem dos grupos da instância.
	"""
	if doctype not in DOCTYPES_COM_SELECT_DE_GRUPO:
		frappe.throw(_("DocType inválido para seleção de grupo: {0}.").format(doctype or "vazio"))

	if not frappe.has_permission(doctype, ptype="write"):
		frappe.throw(
			_("Sem permissão para editar {0}.").format(_(doctype)),
			frappe.PermissionError,
		)

	grupos = listar_grupos_whatsapp()
	return [
		{
			"label": f"{grupo['subject']} ({grupo['id']})",
			"value": grupo["id"],
		}
		for grupo in grupos
	]


def enviar_texto(
	numero: str, mensagem: str, *, enqueue: bool = True, contexto: dict | None = None
) -> dict | None:
	"""Envia mensagem de texto para um número WhatsApp.

	Args:
		numero: Número no formato internacional (ex.: "5511999999999", "+55 11 99999-9999").
		mensagem: Texto a enviar.
		enqueue: Se True (padrão), processa em background. Se False, executa de forma síncrona.
		contexto: O que o transporte não sabe e a ficha de registro precisa: de qual jovem
			a mensagem fala (``novo_associado``), que mensagem é essa (``assunto``) e quem
			recebe (``destinatario_tipo``, ``destinatario_nome``). Ver ``_registrar_log``.

	Returns:
		Resposta da Evolution API (dict) no modo síncrono, ou None quando enfileirado.

	Raises:
		WhatsAppConfigurationError: Integração desabilitada ou configuração incompleta.
		WhatsAppRequestError: Falha de rede ou HTTP ao chamar a Evolution API (modo síncrono).
	"""
	if enqueue:
		frappe.enqueue(
			"gris.utils.whatsapp._enviar_texto_sync",
			queue="short",
			timeout=TIMEOUT_JOB_ENVIO,
			enqueue_after_commit=True,
			numero=numero,
			mensagem=mensagem,
			contexto=contexto,
		)
		return None
	return _enviar_texto_sync(numero, mensagem, contexto=contexto)


def enviar_midia(
	numero: str,
	tipo: str,
	url_ou_base64: str,
	*,
	caption: str = "",
	nome_arquivo: str = "",
	mimetype: str = "",
	enqueue: bool = True,
	contexto: dict | None = None,
) -> dict | None:
	"""Envia mídia (imagem, documento, áudio ou vídeo) para um número WhatsApp.

	Args:
		numero: Número no formato internacional.
		tipo: Tipo de mídia. Um de: "image", "document", "audio", "video".
		url_ou_base64: URL pública da mídia ou string base64 do arquivo.
		caption: Legenda opcional (suportada para imagem, documento e vídeo).
		nome_arquivo: Nome com que o documento aparece na conversa (ex.: "convite.pdf").
		mimetype: Tipo do arquivo (ex.: "application/pdf"). Junto com ``nome_arquivo``,
			é o que faz o celular reconhecer e abrir o documento.
		enqueue: Se True (padrão), processa em background. Para arquivos em base64, prefira
			False dentro de um job, para não levar o arquivo inteiro para a fila.
		contexto: Mesmo papel que em ``enviar_texto``. Ver ``_registrar_log``.

	Returns:
		Resposta da Evolution API (dict) no modo síncrono, ou None quando enfileirado.

	Raises:
		WhatsAppConfigurationError: Integração desabilitada ou configuração incompleta.
		WhatsAppRequestError: Tipo inválido, falha de rede ou HTTP (modo síncrono).
	"""
	if enqueue:
		frappe.enqueue(
			"gris.utils.whatsapp._enviar_midia_sync",
			queue="short",
			timeout=TIMEOUT_JOB_ENVIO,
			enqueue_after_commit=True,
			numero=numero,
			tipo=tipo,
			url_ou_base64=url_ou_base64,
			caption=caption,
			nome_arquivo=nome_arquivo,
			mimetype=mimetype,
			contexto=contexto,
		)
		return None
	return _enviar_midia_sync(
		numero,
		tipo,
		url_ou_base64,
		caption,
		nome_arquivo=nome_arquivo,
		mimetype=mimetype,
		contexto=contexto,
	)


def enviar_para_grupo(
	grupo_jid: str,
	mensagem: str,
	*,
	mencionar_todos: bool = False,
	mencionar: list[str] | None = None,
	enqueue: bool = True,
	contexto: dict | None = None,
) -> dict | None:
	"""Envia mensagem de texto para um grupo WhatsApp.

	Args:
		grupo_jid: JID do grupo no formato Evolution API (ex.: "5511999999999-1234567890@g.us").
		mensagem: Texto a enviar.
		mencionar_todos: Quando True, envia com menção geral para todos os participantes do grupo.
		mencionar: Números a mencionar individualmente. O corpo da mensagem precisa conter
			``@<números>`` para o WhatsApp desenhar a menção.
		enqueue: Se True (padrão), processa em background.
		contexto: O que o transporte não sabe e a ficha de registro precisa: de qual jovem
			a mensagem fala (``novo_associado``), que mensagem é essa (``assunto``) e quem
			recebe (``destinatario_tipo``, ``destinatario_nome``). Ver ``_registrar_log``.

	Returns:
		Resposta da Evolution API (dict) no modo síncrono, ou None quando enfileirado.

	Raises:
		WhatsAppConfigurationError: Integração desabilitada ou configuração incompleta.
		WhatsAppRequestError: Falha de rede ou HTTP ao chamar a Evolution API (modo síncrono).
	"""
	if enqueue:
		frappe.enqueue(
			"gris.utils.whatsapp._enviar_para_grupo_sync",
			queue="short",
			timeout=TIMEOUT_JOB_ENVIO,
			enqueue_after_commit=True,
			grupo_jid=grupo_jid,
			mensagem=mensagem,
			mencionar_todos=mencionar_todos,
			mencionar=mencionar,
			contexto=contexto,
		)
		return None
	return _enviar_para_grupo_sync(
		grupo_jid,
		mensagem,
		mencionar_todos=mencionar_todos,
		mencionar=mencionar,
		contexto=contexto,
	)


def adicionar_participantes_no_grupo(
	grupo_jid: str,
	numeros: list[str],
	*,
	enqueue: bool = True,
) -> dict | None:
	"""Adiciona participantes a um grupo WhatsApp.

	A adição pode ser recusada pela configuração de privacidade de quem seria adicionado —
	nesse caso a Evolution responde com o status por participante, sem erro de HTTP. Quem
	chama deve tratar a falha como não fatal.

	Args:
		grupo_jid: JID do grupo no formato Evolution API (ex.: "1203630000000000@g.us").
		numeros: Telefones a adicionar, em qualquer formato aceito por ``_normalize_phone``.
		enqueue: Se True (padrão), processa em background.

	Returns:
		Resposta da Evolution API (dict) no modo síncrono, ou None quando enfileirado.

	Raises:
		WhatsAppConfigurationError: Integração desabilitada ou configuração incompleta.
		WhatsAppRequestError: Nenhum número válido, falha de rede ou HTTP (modo síncrono).
	"""
	if enqueue:
		frappe.enqueue(
			"gris.utils.whatsapp._adicionar_participantes_no_grupo_sync",
			queue="short",
			timeout=TIMEOUT_JOB_ENVIO,
			enqueue_after_commit=True,
			grupo_jid=grupo_jid,
			numeros=numeros,
		)
		return None
	return _adicionar_participantes_no_grupo_sync(grupo_jid, numeros)


def enviar_mensagem_formatada(
	numero: str,
	titulo: str,
	descricao: str,
	botoes: list[dict] | None = None,
	*,
	enqueue: bool = True,
	contexto: dict | None = None,
) -> dict | None:
	"""Envia mensagem com título, descrição e botões interativos.

	Evite: fora da API oficial do WhatsApp os botões não aparecem de forma confiável. No
	histórico da Evolution, um terço dos lembretes de visita enviados assim nunca teve
	confirmação de entrega. Prefira ``enviar_texto``.

	Args:
		numero: Número no formato internacional.
		titulo: Título da mensagem.
		descricao: Descrição/corpo da mensagem.
		botoes: Lista de botões conforme Evolution API v2.
		        Exemplo: [{"buttonId": "1", "buttonText": {"displayText": "Confirmar"}, "type": "reply"}]
		enqueue: Se True (padrão), processa em background.
		contexto: O que o transporte não sabe e a ficha de registro precisa: de qual jovem
			a mensagem fala (``novo_associado``), que mensagem é essa (``assunto``) e quem
			recebe (``destinatario_tipo``, ``destinatario_nome``). Ver ``_registrar_log``.

	Returns:
		Resposta da Evolution API (dict) no modo síncrono, ou None quando enfileirado.

	Raises:
		WhatsAppConfigurationError: Integração desabilitada ou configuração incompleta.
		WhatsAppRequestError: Falha de rede ou HTTP ao chamar a Evolution API (modo síncrono).
	"""
	if enqueue:
		frappe.enqueue(
			"gris.utils.whatsapp._enviar_mensagem_formatada_sync",
			queue="short",
			timeout=TIMEOUT_JOB_ENVIO,
			enqueue_after_commit=True,
			numero=numero,
			titulo=titulo,
			descricao=descricao,
			botoes=botoes,
			contexto=contexto,
		)
		return None
	return _enviar_mensagem_formatada_sync(numero, titulo, descricao, botoes, contexto=contexto)
