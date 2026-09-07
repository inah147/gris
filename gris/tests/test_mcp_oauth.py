"""Testes de autenticação OAuth no transporte MCP sobre HTTP.

Cobrem a afirmação central do plano de migrar a integração MCP de API key para
OAuth: **um access token OAuth autentica a sessão do Frappe exatamente como a
API key**. Como ``gris.api.mcp.http.mcp`` é um whitelist comum que roda sob
``frappe.session.user``, o endpoint não precisa de mudança nenhuma — e as
checagens de papel do ``registry`` continuam valendo sob a identidade do token.

A camada de descoberta na frente dele (metadados RFC 9728 / RFC 8414 e o
header ``WWW-Authenticate`` no 401), implementada em ``gris.api.mcp.oauth``,
é coberta nas classes ``TestMetadadosDeDescoberta`` e
``TestAnuncioDoRecursoProtegidoNo401`` abaixo. Veja a seção de OAuth em
MCP_CLAUDE.md.

Estes testes exercitam o caminho real de `frappe.auth.validate_oauth` contra
registros de verdade — sem mock do que está sendo verificado.
"""

import base64
import hashlib
import json
from urllib.parse import parse_qs

import frappe
from frappe.auth import CookieManager, LoginManager, validate_oauth
from frappe.oauth import get_server_url
from frappe.tests.test_api import make_request
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, get_test_client, now_datetime, set_request
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request as RequisicaoWerkzeug
from werkzeug.wrappers import Response as RespostaWerkzeug

from gris.api.mcp import oauth as mcp_oauth
from gris.api.mcp import registry
from gris.api.sugestoes.constantes import ROLE_ACOMPANHAMENTO, ROLE_DESENVOLVEDOR

EMAIL = "mcp-oauth@teste.gris"
CLIENTE = "mcp-teste-oauth"
CAMINHO_MCP = "/api/method/gris.api.mcp.http.mcp"
ESCOPOS = "all openid"


def _garantir_papel(papel: str) -> None:
	if not frappe.db.exists("Role", papel):
		frappe.get_doc({"doctype": "Role", "role_name": papel}).insert(ignore_permissions=True)


def _criar_cenario() -> str:
	"""Usuário com os papéis do quadro de sugestões, e um OAuth Client para os tokens.

	Devolve o nome real do OAuth Client: o DocType não declara ``autoname``, então
	o nome final é decidido pelo Frappe e não pode ser presumido aqui.
	"""
	for papel in (ROLE_ACOMPANHAMENTO, ROLE_DESENVOLVEDOR):
		_garantir_papel(papel)

	if not frappe.db.exists("User", EMAIL):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": EMAIL,
				"first_name": "MCP OAuth",
				"send_welcome_email": 0,
				"user_type": "System User",
			}
		).insert(ignore_permissions=True)

	usuario = frappe.get_doc("User", EMAIL)
	atuais = {linha.role for linha in usuario.roles}
	for papel in (ROLE_ACOMPANHAMENTO, ROLE_DESENVOLVEDOR):
		if papel not in atuais:
			usuario.append("roles", {"role": papel})
	usuario.save(ignore_permissions=True)

	cliente = frappe.get_doc(
		{
			"doctype": "OAuth Client",
			"name": CLIENTE,
			"app_name": "MCP de teste",
			"user": "Administrator",
			"scopes": ESCOPOS,
			"redirect_uris": "https://exemplo.invalid/callback",
			"default_redirect_uri": "https://exemplo.invalid/callback",
			"grant_type": "Authorization Code",
			"response_type": "Code",
			"skip_authorization": 1,
		}
	).insert(ignore_permissions=True)
	return cliente.name


def _criar_token(
	access_token: str, cliente: str, *, status: str = "Active", horas: int = 1, escopos: str = ESCOPOS
) -> None:
	frappe.db.delete("OAuth Bearer Token", {"access_token": access_token})
	frappe.get_doc(
		{
			"doctype": "OAuth Bearer Token",
			"client": cliente,
			"user": EMAIL,
			"scopes": escopos,
			"access_token": access_token,
			"refresh_token": f"refresh-{access_token}",
			"expires_in": 3600,
			"expiration_time": add_to_date(now_datetime(), hours=horas),
			"status": status,
		}
	).insert(ignore_permissions=True)


def _criar_cliente_com_escopo(
	nome_cliente: str, escopos: str, *, redirect_uri: str = "https://exemplo.invalid/callback"
) -> str:
	"""Um segundo ``OAuth Client``, com escopo próprio — para provar que o
	escopo de um cliente não vaza pro token de outro (Fase 2 do plano)."""
	frappe.db.delete("OAuth Client", {"name": nome_cliente})
	cliente = frappe.get_doc(
		{
			"doctype": "OAuth Client",
			"name": nome_cliente,
			"app_name": "MCP de teste — escopo dedicado",
			"user": "Administrator",
			"scopes": escopos,
			"redirect_uris": redirect_uri,
			"default_redirect_uri": redirect_uri,
			"grant_type": "Authorization Code",
			"response_type": "Code",
			"skip_authorization": 1,
		}
	).insert(ignore_permissions=True)
	return cliente.name


def _requisicao_mcp(token: str) -> RequisicaoWerkzeug:
	"""Requisição equivalente à que um cliente MCP remoto faria."""
	construtor = EnvironBuilder(
		path=CAMINHO_MCP,
		method="POST",
		base_url="http://test.localhost",
		json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
		headers={"Authorization": f"Bearer {token}"},
	)
	return RequisicaoWerkzeug(construtor.get_environ())


class TestOAuthNoTransporteMCP(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.cliente = _criar_cenario()

	def setUp(self):
		self.request_anterior = getattr(frappe.local, "request", None)
		self.form_dict_anterior = getattr(frappe.local, "form_dict", None)

	def tearDown(self):
		frappe.local.request = self.request_anterior
		frappe.local.form_dict = self.form_dict_anterior
		frappe.set_user("Administrator")

	def _autenticar(self, token: str) -> str:
		"""Roda o caminho real de autenticação e devolve o usuário da sessão."""
		frappe.local.request = _requisicao_mcp(token)
		frappe.local.form_dict = frappe._dict()
		frappe.set_user("Guest")
		validate_oauth(["Bearer", token])
		return frappe.session.user

	def test_bearer_token_define_o_usuario_da_sessao(self):
		"""O núcleo: um token OAuth válido autentica como a API key autenticaria."""
		_criar_token("token-mcp-valido", self.cliente)
		self.assertEqual(self._autenticar("token-mcp-valido"), EMAIL)

	def test_catalogo_respeita_os_papeis_do_token(self):
		"""Sob a identidade do token, o registry aplica os papéis do usuário."""
		_criar_token("token-mcp-papeis", self.cliente)
		self.assertEqual(self._autenticar("token-mcp-papeis"), EMAIL)

		nomes = {ferramenta["nome"] for ferramenta in registry.listar()}
		catalogo_inteiro = {ferramenta["nome"] for ferramenta in registry.listar(incluir_indisponiveis=True)}

		# Guarda contra asserção vazia: a ferramenta do financeiro existe no
		# catálogo, então ficar de fora acima é filtro de papel, não ausência.
		self.assertIn("listar_transacoes", catalogo_inteiro)

		# Tem os papéis do quadro de sugestões...
		self.assertIn("listar_sugestoes", nomes)
		# ...e não tem os do financeiro, então essas ferramentas não aparecem.
		self.assertNotIn("listar_transacoes", nomes)

	def test_token_revogado_nao_autentica(self):
		_criar_token("token-mcp-revogado", self.cliente, status="Revoked")
		self.assertEqual(self._autenticar("token-mcp-revogado"), "Guest")

	def test_token_expirado_nao_autentica(self):
		_criar_token("token-mcp-expirado", self.cliente, horas=-1)
		self.assertEqual(self._autenticar("token-mcp-expirado"), "Guest")

	def test_token_inexistente_nao_autentica(self):
		self.assertEqual(self._autenticar("token-que-nunca-existiu"), "Guest")


class TestEscopoDedicadoRestringeOToken(FrappeTestCase):
	"""Fase 2 do plano: um escopo próprio (``gris.mcp``) de fato limita o
	token — não é só documentação, ``validate_bearer_token`` confere o escopo
	do token contra o do ``OAuth Client`` (``frappe/oauth.py``)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_criar_cenario()  # garante o usuário EMAIL, usado pelo token abaixo
		cls.cliente = _criar_cliente_com_escopo("mcp-teste-escopo-dedicado", mcp_oauth.ESCOPO_MCP)

	def setUp(self):
		self.request_anterior = getattr(frappe.local, "request", None)
		self.form_dict_anterior = getattr(frappe.local, "form_dict", None)

	def tearDown(self):
		frappe.local.request = self.request_anterior
		frappe.local.form_dict = self.form_dict_anterior
		frappe.set_user("Administrator")

	def _autenticar(self, token: str) -> str:
		frappe.local.request = _requisicao_mcp(token)
		frappe.local.form_dict = frappe._dict()
		frappe.set_user("Guest")
		validate_oauth(["Bearer", token])
		return frappe.session.user

	def test_token_com_o_escopo_do_cliente_autentica(self):
		_criar_token("token-escopo-valido", self.cliente, escopos=mcp_oauth.ESCOPO_MCP)
		self.assertEqual(self._autenticar("token-escopo-valido"), EMAIL)

	def test_token_com_escopo_fora_do_cliente_nao_autentica(self):
		"""O token carrega um escopo (``all``) que o cliente nunca declarou —
		mesmo com o resto do token válido, a checagem de escopo barra."""
		_criar_token("token-escopo-alheio", self.cliente, escopos="all")
		self.assertEqual(self._autenticar("token-escopo-alheio"), "Guest")

	def test_token_com_escopo_parcialmente_fora_do_cliente_nao_autentica(self):
		_criar_token("token-escopo-misto", self.cliente, escopos=f"{mcp_oauth.ESCOPO_MCP} all")
		self.assertEqual(self._autenticar("token-escopo-misto"), "Guest")


def _requisicao(caminho: str) -> RequisicaoWerkzeug:
	construtor = EnvironBuilder(path=caminho, method="GET", base_url="http://test.localhost")
	return RequisicaoWerkzeug(construtor.get_environ())


class TestMetadadosDeDescoberta(FrappeTestCase):
	"""RFC 9728 e RFC 8414 — os documentos que fazem o cliente MCP descobrir o
	authorization server sozinho, a partir de um 401 no endpoint."""

	def setUp(self):
		self.request_anterior = getattr(frappe.local, "request", None)
		self.form_dict_anterior = getattr(frappe.local, "form_dict", None)
		frappe.local.request = _requisicao_mcp("irrelevante-para-descoberta")
		frappe.local.form_dict = frappe._dict()

	def tearDown(self):
		frappe.local.request = self.request_anterior
		frappe.local.form_dict = self.form_dict_anterior

	def test_recurso_protegido_aponta_para_o_endpoint_mcp(self):
		mcp_oauth.oauth_protected_resource()
		resposta = frappe.local.response
		servidor = get_server_url()

		self.assertEqual(resposta["resource"], f"{servidor}{CAMINHO_MCP}")
		self.assertEqual(resposta["authorization_servers"], [servidor])
		self.assertIn(mcp_oauth.ESCOPO_MCP, resposta["scopes_supported"])
		self.assertEqual(resposta["bearer_methods_supported"], ["header"])

	def test_authorization_server_espelha_o_openid_configuration(self):
		mcp_oauth.oauth_authorization_server()
		resposta = frappe.local.response

		# Espelhado do frappe.integrations.oauth2.openid_configuration.
		self.assertIn("authorization_endpoint", resposta)
		self.assertIn("token_endpoint", resposta)

	def test_authorization_server_anuncia_o_que_o_openid_configuration_nao_anuncia(self):
		mcp_oauth.oauth_authorization_server()
		resposta = frappe.local.response

		self.assertEqual(set(resposta["code_challenge_methods_supported"]), {"S256", "plain"})
		self.assertIn("authorization_code", resposta["grant_types_supported"])
		self.assertEqual(resposta["token_endpoint_auth_methods_supported"], ["none"])
		self.assertIn(mcp_oauth.ESCOPO_MCP, resposta["scopes_supported"])


class TestAnuncioDoRecursoProtegidoNo401(FrappeTestCase):
	"""``WWW-Authenticate`` só na chamada sem token válido ao endpoint MCP."""

	def setUp(self):
		self.request_anterior = getattr(frappe.local, "request", None)

	def tearDown(self):
		frappe.local.request = self.request_anterior

	def _header_esperado(self) -> str:
		return f'Bearer resource_metadata="{get_server_url()}/.well-known/oauth-protected-resource"'

	def test_401_no_mcp_ganha_o_header(self):
		frappe.local.request = _requisicao_mcp("irrelevante")
		resposta = RespostaWerkzeug(status=401)

		mcp_oauth.anunciar_recurso_protegido(resposta, frappe.local.request)

		self.assertEqual(resposta.status_code, 401)
		self.assertEqual(resposta.headers["WWW-Authenticate"], self._header_esperado())

	def test_403_no_mcp_vira_401_com_o_header(self):
		"""403 é o que ``is_whitelisted`` devolve pra Guest sem Authorization —
		mesma falta de credencial que o 401, então ganha o mesmo tratamento."""
		frappe.local.request = _requisicao_mcp("irrelevante")
		resposta = RespostaWerkzeug(status=403)

		mcp_oauth.anunciar_recurso_protegido(resposta, frappe.local.request)

		self.assertEqual(resposta.status_code, 401)
		self.assertEqual(resposta.headers["WWW-Authenticate"], self._header_esperado())

	def test_outro_caminho_nao_ganha_o_header(self):
		frappe.local.request = _requisicao("/api/method/frappe.auth.get_logged_user")
		resposta = RespostaWerkzeug(status=401)

		mcp_oauth.anunciar_recurso_protegido(resposta, frappe.local.request)

		self.assertNotIn("WWW-Authenticate", resposta.headers)
		self.assertEqual(resposta.status_code, 401)

	def test_200_no_mcp_nao_ganha_o_header(self):
		frappe.local.request = _requisicao_mcp("irrelevante")
		resposta = RespostaWerkzeug(status=200)

		mcp_oauth.anunciar_recurso_protegido(resposta, frappe.local.request)

		self.assertNotIn("WWW-Authenticate", resposta.headers)

	def test_sem_resposta_nao_quebra(self):
		frappe.local.request = _requisicao_mcp("irrelevante")
		mcp_oauth.anunciar_recurso_protegido(None, frappe.local.request)


FORM_HEADER = {"content-type": "application/x-www-form-urlencoded"}


class TestDescobertaAtravesDoAppReal(FrappeTestCase):
	"""As mesmas checagens de ``TestMetadadosDeDescoberta`` e
	``TestAnuncioDoRecursoProtegidoNo401``, mas através do app WSGI de
	verdade (``frappe.app.application``) em vez de chamar as funções em
	isolamento — prova que o roteamento (``website_redirects``) e o hook
	(``after_request``) cadastrados em ``gris/hooks.py`` estão de fato
	ligados. Não grava nada no banco, então não precisa de commit/limpeza.
	"""

	site = frappe.local.site

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.TEST_CLIENT = get_test_client()

	def _get(self, path, **kwargs):
		return make_request(target=self.TEST_CLIENT.get, args=(path,), kwargs=kwargs, site=self.site)

	def _post(self, path, data=None, **kwargs):
		return make_request(
			target=self.TEST_CLIENT.post, args=(path,), kwargs={"data": data, **kwargs}, site=self.site
		)

	def test_mcp_sem_token_devolve_401_com_www_authenticate(self):
		resposta = self._post(
			CAMINHO_MCP,
			data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
			headers={"Content-Type": "application/json"},
		)
		self.assertEqual(resposta.status_code, 401)
		self.assertIn("oauth-protected-resource", resposta.headers.get("WWW-Authenticate", ""))

	def test_recurso_protegido_redireciona_e_responde(self):
		resposta = self._get("/.well-known/oauth-protected-resource", follow_redirects=True)
		self.assertEqual(resposta.status_code, 200)
		self.assertTrue(resposta.json["resource"].endswith(CAMINHO_MCP))

	def test_authorization_server_redireciona_e_responde(self):
		resposta = self._get("/.well-known/oauth-authorization-server", follow_redirects=True)
		self.assertEqual(resposta.status_code, 200)
		self.assertIn("S256", resposta.json["code_challenge_methods_supported"])


class TestFluxoOAuthPontaAPonta(FrappeTestCase):
	"""Fase 3 do plano: o Authorization Code + PKCE completo contra o site de
	teste, do ``authorize`` até uma chamada ``tools/list`` autenticada por
	Bearer — a mesma sequência que um cliente MCP de verdade percorre.

	A requisição HTTP roda numa thread à parte (``make_request``), com sua
	própria conexão de banco — por isso os fixtures são gravados com
	``frappe.db.commit()`` e desfeitos manualmente no ``tearDown``: o
	rollback automático do ``FrappeTestCase`` não alcança o que já foi
	commitado (mesmo padrão de ``frappe/tests/test_oauth20.py``).
	"""

	site = frappe.local.site

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.TEST_CLIENT = get_test_client()

	REDIRECT_URI = "http://localhost/callback"

	def setUp(self):
		_criar_cenario()
		self.cliente = _criar_cliente_com_escopo(
			"mcp-teste-fluxo-completo", mcp_oauth.ESCOPO_MCP, redirect_uri=self.REDIRECT_URI
		)

		set_request(path="/")
		frappe.local.cookie_manager = CookieManager()
		frappe.local.login_manager = LoginManager()
		frappe.local.login_manager.login_as(EMAIL)
		self.sid = frappe.session.sid

		frappe.db.commit()  # nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("OAuth Bearer Token", {"client": self.cliente})
		frappe.db.delete("OAuth Authorization Code", {"client": self.cliente})
		frappe.delete_doc("OAuth Client", self.cliente, force=True, ignore_permissions=True)
		frappe.db.commit()  # nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit

	def _get(self, path, params=None, **kwargs):
		return make_request(
			target=self.TEST_CLIENT.get, args=(path,), kwargs={"data": params, **kwargs}, site=self.site
		)

	def _post(self, path, data=None, **kwargs):
		return make_request(
			target=self.TEST_CLIENT.post, args=(path,), kwargs={"data": data, **kwargs}, site=self.site
		)

	def test_fluxo_completo_authorization_code_com_pkce(self):
		redirect_uri = self.REDIRECT_URI
		verificador = "verificador-de-teste-para-pkce-bem-longo-o-suficiente"
		desafio = (
			base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
		)

		# 1. authorize — client de teste tem skip_authorization=1, então o
		#    redirecionamento com o `code` acontece sem tela de consentimento.
		self.TEST_CLIENT.set_cookie(key="sid", value=self.sid)
		resposta_autorizacao = self._get(
			"/api/method/frappe.integrations.oauth2.authorize",
			{
				"client_id": self.cliente,
				"scope": mcp_oauth.ESCOPO_MCP,
				"response_type": "code",
				"redirect_uri": redirect_uri,
				"code_challenge_method": "S256",
				"code_challenge": desafio,
			},
			follow_redirects=True,
		)
		codigo = parse_qs(resposta_autorizacao.request.environ["QUERY_STRING"])["code"][0]

		# 2. get_token — troca o code (+ o verifier do PKCE) por um access token.
		resposta_token = self._post(
			"/api/method/frappe.integrations.oauth2.get_token",
			headers=FORM_HEADER,
			data={
				"grant_type": "authorization_code",
				"code": codigo,
				"redirect_uri": redirect_uri,
				"client_id": self.cliente,
				"scope": mcp_oauth.ESCOPO_MCP,
				"code_verifier": verificador,
			},
		)
		token = resposta_token.json
		self.assertTrue(token.get("access_token"), token)

		# 3. tools/list no endpoint MCP, autenticado só pelo access token.
		resposta_mcp = self._post(
			CAMINHO_MCP,
			data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
			headers={"Authorization": f"Bearer {token['access_token']}", "Content-Type": "application/json"},
		)
		self.assertEqual(resposta_mcp.status_code, 200)
		self.assertIn("tools", resposta_mcp.json.get("result", {}))
