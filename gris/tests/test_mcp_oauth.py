"""Testes de autenticação OAuth no transporte MCP sobre HTTP.

Cobrem a afirmação central do plano de migrar a integração MCP de API key para
OAuth: **um access token OAuth autentica a sessão do Frappe exatamente como a
API key**. Como ``gris.api.mcp.http.mcp`` é um whitelist comum que roda sob
``frappe.session.user``, o endpoint não precisa de mudança nenhuma — e as
checagens de papel do ``registry`` continuam valendo sob a identidade do token.

O que falta para o fluxo OAuth completo não é o endpoint, e sim a camada de
descoberta na frente dele (metadados RFC 9728 / RFC 8414 e o header
``WWW-Authenticate`` no 401). Veja a seção de OAuth em MCP_CLAUDE.md.

Estes testes exercitam o caminho real de `frappe.auth.validate_oauth` contra
registros de verdade — sem mock do que está sendo verificado.
"""

import frappe
from frappe.auth import validate_oauth
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request as RequisicaoWerkzeug

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


def _criar_token(access_token: str, cliente: str, *, status: str = "Active", horas: int = 1) -> None:
	frappe.db.delete("OAuth Bearer Token", {"access_token": access_token})
	frappe.get_doc(
		{
			"doctype": "OAuth Bearer Token",
			"client": cliente,
			"user": EMAIL,
			"scopes": ESCOPOS,
			"access_token": access_token,
			"refresh_token": f"refresh-{access_token}",
			"expires_in": 3600,
			"expiration_time": add_to_date(now_datetime(), hours=horas),
			"status": status,
		}
	).insert(ignore_permissions=True)


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
		catalogo_inteiro = {
			ferramenta["nome"] for ferramenta in registry.listar(incluir_indisponiveis=True)
		}

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
