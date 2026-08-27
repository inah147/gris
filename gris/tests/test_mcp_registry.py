"""Testes do registro de ferramentas MCP (autorização e validação de argumentos)."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from gris.api.mcp import registry


def _ferramenta(nome="ferramenta_teste", handler=None, **kwargs):
	return registry.Ferramenta(
		nome=nome,
		titulo="Ferramenta de teste",
		descricao="Usada nos testes.",
		handler=handler or (lambda **kw: kw),
		**kwargs,
	)


def _com_sessao(user="gestor@example.com", papeis=("Gestor de Associados",)):
	return (
		patch.object(registry.frappe, "session", SimpleNamespace(user=user), create=True),
		patch.object(registry.frappe, "get_roles", return_value=list(papeis)),
	)


class TestValidacaoDeArgumentos(TestCase):
	def test_aplica_default_e_ignora_vazios(self):
		ferramenta = _ferramenta(
			parametros={
				"limite": {"type": "integer", "default": 25},
				"busca": {"type": "string"},
			}
		)
		self.assertEqual(registry.validar_argumentos(ferramenta, {"busca": ""}), {"limite": 25})

	def test_recusa_parametro_desconhecido(self):
		ferramenta = _ferramenta(parametros={"busca": {"type": "string"}})
		with self.assertRaises(registry.ErroDeFerramenta) as ctx:
			registry.validar_argumentos(ferramenta, {"buscar": "ana"})
		self.assertEqual(ctx.exception.codigo, "ARGUMENTO_INVALIDO")
		self.assertIn("buscar", ctx.exception.mensagem)

	def test_exige_obrigatorios(self):
		ferramenta = _ferramenta(parametros={"cpf": {"type": "string"}}, obrigatorios=("cpf",))
		with self.assertRaises(registry.ErroDeFerramenta) as ctx:
			registry.validar_argumentos(ferramenta, {})
		self.assertIn("cpf", ctx.exception.mensagem)

	def test_valida_enum(self):
		ferramenta = _ferramenta(parametros={"ramo": {"type": "string", "enum": ["Lobinho", "Escoteiro"]}})
		with self.assertRaises(registry.ErroDeFerramenta) as ctx:
			registry.validar_argumentos(ferramenta, {"ramo": "Pioneiro"})
		self.assertEqual(ctx.exception.detalhes["opcoes"], ["Lobinho", "Escoteiro"])

	def test_limita_inteiro_ao_intervalo(self):
		ferramenta = _ferramenta(parametros={"limite": {"type": "integer", "minimum": 1, "maximum": 100}})
		self.assertEqual(registry.validar_argumentos(ferramenta, {"limite": "500"}), {"limite": 100})
		self.assertEqual(registry.validar_argumentos(ferramenta, {"limite": -3}), {"limite": 1})

	def test_inteiro_invalido(self):
		ferramenta = _ferramenta(parametros={"limite": {"type": "integer"}})
		with self.assertRaises(registry.ErroDeFerramenta):
			registry.validar_argumentos(ferramenta, {"limite": "muitos"})

	def test_booleano_aceita_texto(self):
		ferramenta = _ferramenta(parametros={"revisada": {"type": "boolean"}})
		self.assertEqual(registry.validar_argumentos(ferramenta, {"revisada": "sim"}), {"revisada": True})
		self.assertEqual(registry.validar_argumentos(ferramenta, {"revisada": "0"}), {"revisada": False})

	def test_lista_aceita_csv_e_respeita_limite(self):
		ferramenta = _ferramenta(parametros={"ids": {"type": "array", "maxItems": 2}})
		self.assertEqual(registry.validar_argumentos(ferramenta, {"ids": "T1, T2"}), {"ids": ["T1", "T2"]})
		with self.assertRaises(registry.ErroDeFerramenta):
			registry.validar_argumentos(ferramenta, {"ids": ["T1", "T2", "T3"]})

	def test_objeto_precisa_ser_dict(self):
		ferramenta = _ferramenta(parametros={"campos": {"type": "object"}})
		with self.assertRaises(registry.ErroDeFerramenta):
			registry.validar_argumentos(ferramenta, {"campos": "telefone=1"})


class TestAutorizacao(TestCase):
	def test_system_manager_acessa_tudo(self):
		ferramenta = _ferramenta(roles=("Gestor Financeiro",))
		self.assertTrue(registry.usuario_autorizado(ferramenta, {"System Manager"}))

	def test_sem_roles_declaradas_libera_autenticado(self):
		self.assertTrue(registry.usuario_autorizado(_ferramenta(), {"Responsavel"}))

	def test_exige_uma_das_roles(self):
		ferramenta = _ferramenta(roles=("Gestor Financeiro", "Visualizador Financeiro"))
		self.assertTrue(registry.usuario_autorizado(ferramenta, {"Visualizador Financeiro"}))
		self.assertFalse(registry.usuario_autorizado(ferramenta, {"Responsavel"}))


class TestExecucao(TestCase):
	def test_recusa_guest(self):
		with patch.object(registry.frappe, "session", SimpleNamespace(user="Guest"), create=True):
			with self.assertRaises(registry.ErroDeFerramenta) as ctx:
				registry.executar("listar_associados", {})
		self.assertEqual(ctx.exception.codigo, "NAO_AUTENTICADO")

	def test_ferramenta_inexistente_lista_disponiveis(self):
		sessao, papeis = _com_sessao()
		with (
			sessao,
			papeis,
			patch.object(registry, "carregar_ferramentas", return_value={"listar_associados": _ferramenta()}),
		):
			with self.assertRaises(registry.ErroDeFerramenta) as ctx:
				registry.executar("listar_tudo", {})
		self.assertEqual(ctx.exception.codigo, "FERRAMENTA_DESCONHECIDA")
		self.assertEqual(ctx.exception.detalhes["disponiveis"], ["listar_associados"])

	def test_permissao_negada(self):
		ferramenta = _ferramenta(nome="categorizar", roles=("Gestor Financeiro",))
		sessao, papeis = _com_sessao(papeis=("Responsavel",))
		with (
			sessao,
			papeis,
			patch.object(registry, "carregar_ferramentas", return_value={"categorizar": ferramenta}),
		):
			with self.assertRaises(registry.ErroDeFerramenta) as ctx:
				registry.executar("categorizar", {})
		self.assertEqual(ctx.exception.codigo, "PERMISSAO_NEGADA")
		self.assertEqual(ctx.exception.detalhes["roles_necessarias"], ["Gestor Financeiro"])

	def test_execucao_valida_argumentos_e_devolve_envelope(self):
		handler = MagicMock(return_value={"associados": []})
		ferramenta = _ferramenta(
			nome="listar_associados",
			handler=handler,
			parametros={"limite": {"type": "integer", "default": 25}},
		)
		sessao, papeis = _com_sessao()
		with (
			sessao,
			papeis,
			patch.object(registry, "carregar_ferramentas", return_value={"listar_associados": ferramenta}),
		):
			resposta = registry.executar("listar_associados", {})

		handler.assert_called_once_with(limite=25)
		self.assertEqual(resposta, {"ok": True, "data": {"associados": []}})

	def test_mutacao_gera_log_de_auditoria(self):
		ferramenta = _ferramenta(
			nome="atualizar",
			handler=lambda **kw: {"atualizado": True},
			roles=("Gestor de Associados",),
			somente_leitura=False,
		)
		logger = MagicMock()
		sessao, papeis = _com_sessao()
		with (
			sessao,
			papeis,
			patch.object(registry, "carregar_ferramentas", return_value={"atualizar": ferramenta}),
			patch.object(registry.frappe, "logger", return_value=logger),
		):
			registry.executar("atualizar", {})

		logger.info.assert_called_once()
		evento = logger.info.call_args[0][0]
		self.assertEqual(evento["ferramenta"], "atualizar")
		self.assertEqual(evento["usuario"], "gestor@example.com")


class TestCatalogo(TestCase):
	def test_listar_esconde_ferramentas_sem_permissao(self):
		catalogo = {
			"listar_associados": _ferramenta(nome="listar_associados", roles=("Gestor de Associados",)),
			"categorizar": _ferramenta(nome="categorizar", roles=("Gestor Financeiro",)),
		}
		sessao, papeis = _com_sessao()
		with sessao, papeis, patch.object(registry, "carregar_ferramentas", return_value=catalogo):
			visiveis = registry.listar()
			todas = registry.listar(incluir_indisponiveis=True)

		self.assertEqual([f["nome"] for f in visiveis], ["listar_associados"])
		self.assertEqual([f["nome"] for f in todas], ["categorizar", "listar_associados"])
		self.assertFalse(next(f for f in todas if f["nome"] == "categorizar")["autorizada"])

	def test_input_schema_expoe_obrigatorios(self):
		ferramenta = _ferramenta(parametros={"cpf": {"type": "string"}}, obrigatorios=("cpf",))
		schema = ferramenta.input_schema()
		self.assertEqual(schema["required"], ["cpf"])
		self.assertFalse(schema["additionalProperties"])

	def test_registrar_recusa_nome_duplicado(self):
		catalogo_original = dict(registry._REGISTRO)
		try:
			registry._REGISTRO.clear()
			registry.registrar(_ferramenta(nome="unica"))
			with self.assertRaises(ValueError):
				registry.registrar(_ferramenta(nome="unica"))
		finally:
			registry._REGISTRO.clear()
			registry._REGISTRO.update(catalogo_original)


class TestSimulacao(TestCase):
	def test_ferramenta_de_escrita_ganha_parametro_simular(self):
		ferramenta = _ferramenta(parametros={"cpf": {"type": "string"}}, somente_leitura=False)
		propriedades = ferramenta.input_schema()["properties"]
		self.assertIn("simular", propriedades)
		self.assertFalse(propriedades["simular"]["default"])

	def test_ferramenta_de_leitura_nao_ganha_simular(self):
		ferramenta = _ferramenta(parametros={"cpf": {"type": "string"}})
		self.assertNotIn("simular", ferramenta.input_schema()["properties"])
		with self.assertRaises(registry.ErroDeFerramenta):
			registry.validar_argumentos(ferramenta, {"simular": True})

	def test_handler_de_escrita_recebe_simular_false_por_padrao(self):
		handler = MagicMock(return_value={"atualizado": True})
		ferramenta = _ferramenta(nome="gravar", handler=handler, somente_leitura=False)
		sessao, papeis = _com_sessao()
		with (
			sessao,
			papeis,
			patch.object(registry, "carregar_ferramentas", return_value={"gravar": ferramenta}),
		):
			registry.executar("gravar", {})

		handler.assert_called_once_with(simular=False)

	def test_simulacao_nao_entra_no_log_de_auditoria(self):
		ferramenta = _ferramenta(
			nome="gravar", handler=lambda **kw: {"simulacao": True}, somente_leitura=False
		)
		logger = MagicMock()
		sessao, papeis = _com_sessao()
		with (
			sessao,
			papeis,
			patch.object(registry, "carregar_ferramentas", return_value={"gravar": ferramenta}),
			patch.object(registry.frappe, "logger", return_value=logger),
		):
			registry.executar("gravar", {"simular": True})

		logger.info.assert_not_called()
