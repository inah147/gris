# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Busca global do Portal (spec: docs/specs/busca-global/spec.md).

Cobre o que dá para provar sem navegador: o termo, o radical de singular/plural, o
ranking, o índice de páginas por papel e, principalmente, que a busca nunca mostra o que a
pessoa não abriria. O comportamento da paleta na tela fica no E2E
(`gris/tests/e2e/test_busca_global.py`).
"""

from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api import busca_global
from gris.api.busca_global import (
	FONTES,
	LIMITE_POR_GRUPO,
	PAGINAS_FORA_DO_MENU,
	_condicoes,
	_palavras,
	_radical,
	_ranquear,
	buscar,
	paginas_da_busca,
)
from gris.api.portal_access import PAGE_ROLES, build_sidebar

#: Palavra que não existe em nenhum cadastro real: isola os registros deste teste.
MARCA = "Zqbuscaglobal"
ANO_TESTE = 1987

USUARIO_SEM_PAPEL = "busca.sem.papel@example.com"
USUARIO_GESTOR = "busca.gestor.associados@example.com"
USUARIO_CONTRIBUICAO = "busca.contribuicao@example.com"


class TestBuscaGlobal(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")
		# O rollback do FrappeTestCase é por classe: sem este, o cadastro de um teste
		# derruba o seguinte com DuplicateEntryError.
		frappe.db.rollback()

	# ------------------------------------------------------------------
	# Termo
	# ------------------------------------------------------------------

	def test_radical_liga_singular_e_plural(self):
		self.assertEqual(_radical("contribuição"), _radical("Contribuições"))
		self.assertEqual(_radical("mensal"), _radical("mensais"))
		self.assertEqual(_radical("projetos"), "projeto")
		self.assertEqual(_radical("Gonçalves"), "goncalve")

	def test_radical_preserva_palavra_curta(self):
		# Cortar "visão" daria "vis", curto demais para valer como radical.
		self.assertEqual(_radical("visão"), "visao")
		self.assertEqual(_radical("ana"), "ana")
		self.assertEqual(_radical("12345"), "12345")

	def test_radical_e_sempre_prefixo_da_palavra(self):
		for palavra in ("contribuicoes", "mensais", "papeis", "festas", "relatorio", "geral"):
			self.assertTrue(palavra.startswith(_radical(palavra)), palavra)

	def test_termo_cortado_em_80_caracteres_e_5_palavras(self):
		self.assertEqual(len(_palavras("a b c d e f g h")), 5)
		self.assertLessEqual(len(" ".join(_palavras("x" * 200))), 80)
		self.assertEqual(_palavras(None), [])

	def test_termo_curto_devolve_vazio_sem_consultar(self):
		with patch.object(busca_global, "FONTES", tuple(_fonte_espia(f) for f in FONTES)) as fontes:
			for termo in (None, "", " ", "a", " b "):
				resposta = buscar(termo)
				self.assertTrue(resposta["ok"])
				self.assertEqual(resposta["data"]["grupos"], [])
			for fonte in fontes:
				fonte.consultar.assert_not_called()

	def test_curinga_do_like_e_literal(self):
		filtros, _ = _condicoes("nome_completo", ["50%_"])
		self.assertEqual(filtros, [["nome_completo", "like", "%50\\%\\_%"]])
		# Sem o escape, "%%" casaria com qualquer nome.
		_criar_associado("39100000001", f"{MARCA} Curinga")
		self.assertNotIn("associados", _chaves(buscar("%%")))

	# ------------------------------------------------------------------
	# Casamento e ranking
	# ------------------------------------------------------------------

	def test_palavras_em_qualquer_ordem(self):
		_criar_associado("39100000002", f"{MARCA} Maria Silva")
		titulos = _titulos(buscar(f"silva {MARCA.lower()} maria"), "associados")
		self.assertIn(f"{MARCA} Maria Silva", titulos)

	def test_ignora_acento_caixa_e_plural(self):
		_criar_associado("39100000003", f"{MARCA} João Conceição")
		self.assertIn(f"{MARCA} João Conceição", _titulos(buscar(f"{MARCA} JOAO conceicoes"), "associados"))

	def test_busca_associado_pelo_registro(self):
		nome = _criar_associado("39100000004", f"{MARCA} Registro")
		frappe.db.set_value("Associado", nome, "registro", "7766554", update_modified=False)
		itens = _itens(buscar("7766554"), "associados")
		self.assertEqual([item["titulo"] for item in itens], [f"{MARCA} Registro"])
		self.assertIn("Registro 7766554", itens[0]["subtitulo"])

	def test_ranking_prefixo_antes_de_meio(self):
		itens = [{"titulo": titulo} for titulo in ("Mariana Souza", "Souza Ana", "Ana Souza", "Ana")]
		self.assertEqual(
			[item["titulo"] for item in _ranquear(itens, ["ana"])],
			["Ana", "Ana Souza", "Souza Ana", "Mariana Souza"],
		)

	def test_limite_por_grupo(self):
		for indice in range(LIMITE_POR_GRUPO + 2):
			_criar_associado(f"3910000010{indice}", f"{MARCA} Limite {indice}")
		self.assertEqual(len(_itens(buscar(f"{MARCA} limite"), "associados")), LIMITE_POR_GRUPO)

	def test_url_do_registro_e_codificada(self):
		nome = _criar_associado("39100000005", f"{MARCA} Url")
		itens = _itens(buscar(f"{MARCA} url"), "associados")
		self.assertEqual(itens[0]["url"], f"/associados/detalhe?name={nome}")

	# ------------------------------------------------------------------
	# Pessoas: responsável x associado
	# ------------------------------------------------------------------

	def test_responsavel_que_e_associado_aparece_so_como_associado(self):
		# Mesmo CPF, mesma chave: é a mesma pessoa.
		_criar_associado("39100000006", f"{MARCA} Dupla")
		_criar_responsavel("39100000006", f"{MARCA} Dupla")
		so_responsavel = _criar_responsavel("39100000007", f"{MARCA} Sozinha")

		resposta = buscar(MARCA)
		self.assertIn(f"{MARCA} Dupla", _titulos(resposta, "associados"))
		responsaveis = _itens(resposta, "responsaveis")
		self.assertEqual([item["titulo"] for item in responsaveis], [f"{MARCA} Sozinha"])
		self.assertEqual(responsaveis[0]["url"], f"/associados/responsavel?name={so_responsavel}")

	def test_subtitulo_sem_dado_sensivel(self):
		nome = _criar_associado("39100000008", f"{MARCA} Sensivel")
		frappe.db.set_value(
			"Associado",
			nome,
			{"email": "sensivel@example.com", "telefone": "11988887777"},
			update_modified=False,
		)
		_criar_responsavel("39100000009", f"{MARCA} Sensivel Resp")

		for grupo in buscar(f"{MARCA} sensivel")["data"]["grupos"]:
			for item in grupo["itens"]:
				for proibido in (
					"39100000008",
					"39100000009",
					"sensivel@example.com",
					"11988887777",
					"11999990000",
				):
					self.assertNotIn(proibido, item["subtitulo"])
					self.assertNotIn(proibido, item["titulo"])

	# ------------------------------------------------------------------
	# Autorização
	# ------------------------------------------------------------------

	def test_usuario_sem_papel_nao_ve_pessoas(self):
		_criar_associado("39100000010", f"{MARCA} Restrito")
		_criar_responsavel("39100000011", f"{MARCA} Restrito Resp")
		_criar_usuario(USUARIO_SEM_PAPEL)

		frappe.set_user(USUARIO_SEM_PAPEL)
		chaves = _chaves(buscar(MARCA))
		self.assertFalse({"associados", "responsaveis", "novos_associados", "projetos", "festas"} & chaves)

	def test_gestor_de_associados_ve_associados(self):
		_criar_associado("39100000012", f"{MARCA} Visivel")
		_criar_usuario(USUARIO_GESTOR, ["Gestor de Associados"])

		frappe.set_user(USUARIO_GESTOR)
		self.assertIn(f"{MARCA} Visivel", _titulos(buscar(MARCA), "associados"))

	def test_papel_com_leitura_mas_sem_a_pagina_nao_ve(self):
		"""Gestor Contribuição Mensal lê o DocType Associado, mas não abre a ficha."""
		_criar_associado("39100000013", f"{MARCA} Ficha")
		_criar_usuario(USUARIO_CONTRIBUICAO, ["Gestor Contribuição Mensal"])

		frappe.set_user(USUARIO_CONTRIBUICAO)
		self.assertNotIn("associados", _chaves(buscar(MARCA)))

	def test_visitante_nao_busca(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			frappe.is_whitelisted(buscar)

	def test_endpoint_so_aceita_get(self):
		self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[buscar], ["GET"])

	def test_gates_e_paginas_extras_estao_mapeados(self):
		"""`user_has_access` libera rota não mapeada: tudo aqui precisa estar em PAGE_ROLES."""
		for pagina in PAGINAS_FORA_DO_MENU:
			self.assertIn(pagina["path"], PAGE_ROLES)
		for fonte in FONTES:
			self.assertIn(fonte.rota, PAGE_ROLES)

	def test_captacao_sem_ver_o_banco_filtra_pelo_proponente(self):
		perfil = SimpleNamespace(ve_o_banco=False, user="proponente@example.com")
		with (
			patch("gris.api.captacao.permissoes.perfil_do_usuario", return_value=perfil),
			patch.object(busca_global.frappe, "get_all", return_value=[]) as get_all,
		):
			busca_global._captacao(["ideia"])
		self.assertIn(["proponente_user", "=", "proponente@example.com"], get_all.call_args.kwargs["filters"])

	def test_transparencia_so_publicado(self):
		_criar_transparencia("Parecer anual da comissão fiscal", publicado=1)
		_criar_transparencia("Cartão CNPJ", publicado=0)

		itens = _itens(buscar(str(ANO_TESTE)), "transparencia")
		self.assertEqual(len(itens), 1)
		self.assertIn("Parecer anual", itens[0]["titulo"])
		self.assertEqual(itens[0]["url"], f"/portal_transparencia?ano_referencia={ANO_TESTE}")

	# ------------------------------------------------------------------
	# Índice de páginas
	# ------------------------------------------------------------------

	def test_indice_de_quem_nao_tem_papel(self):
		_criar_usuario(USUARIO_SEM_PAPEL)
		frappe.set_user(USUARIO_SEM_PAPEL)
		urls = {pagina["url"] for pagina in paginas_da_busca(build_sidebar())}
		self.assertIn("/inicio", urls)
		self.assertIn("/portal_transparencia", urls)
		self.assertNotIn("/financeiro", urls)
		self.assertNotIn("/associados/lista", urls)
		self.assertNotIn("/calendario/importar", urls)
		self.assertFalse(any(url.startswith("/app") for url in urls))

	def test_indice_do_modulo_so_com_acesso_ao_indice(self):
		"""A sidebar mantém "Financeiro" por causa do filho; o índice do módulo não abre."""
		_criar_usuario(USUARIO_CONTRIBUICAO, ["Gestor Contribuição Mensal"])
		frappe.set_user(USUARIO_CONTRIBUICAO)
		paginas = {pagina["url"]: pagina for pagina in paginas_da_busca(build_sidebar())}
		self.assertIn("/financeiro/contribuicoes", paginas)
		self.assertEqual(paginas["/financeiro/contribuicoes"]["grupo"], "Financeiro")
		self.assertNotIn("/financeiro", paginas)

	def test_indice_sem_url_repetida(self):
		paginas = paginas_da_busca(build_sidebar())
		urls = [pagina["url"] for pagina in paginas]
		self.assertEqual(len(urls), len(set(urls)))
		quadros = next(pagina for pagina in paginas if pagina["url"] == "/gestao_tarefas")
		self.assertIn("Quadros", quadros["termos"])

	def test_indice_marca_modulos_e_traz_sinonimos(self):
		paginas = {pagina["url"]: pagina for pagina in paginas_da_busca(build_sidebar())}
		self.assertTrue(paginas["/administracao"]["modulo"])
		self.assertFalse(paginas["/administracao/funcoes"]["modulo"])
		self.assertIn("configurações", paginas["/administracao"]["termos"])
		self.assertIn("/calendario/importar", paginas)


# ----------------------------------------------------------------------
# Auxiliares
# ----------------------------------------------------------------------


def _fonte_espia(fonte):
	from unittest.mock import MagicMock

	return SimpleNamespace(**{**fonte.__dict__, "consultar": MagicMock(return_value=[])})


def _chaves(resposta) -> set[str]:
	return {grupo["chave"] for grupo in resposta["data"]["grupos"]}


def _itens(resposta, chave) -> list[dict]:
	for grupo in resposta["data"]["grupos"]:
		if grupo["chave"] == chave:
			return grupo["itens"]
	return []


def _titulos(resposta, chave) -> list[str]:
	return [item["titulo"] for item in _itens(resposta, chave)]


def _criar_associado(cpf: str, nome: str) -> str:
	doc = frappe.get_doc(
		{
			"doctype": "Associado",
			"nome_completo": nome,
			"cpf": cpf,
			"data_de_nascimento": "1985-01-01",
			"categoria": "Dirigente",
			"status_no_grupo": "Ativo",
			"historico_no_grupo": [{"data_de_ingresso": "2020-01-01"}],
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _criar_responsavel(cpf: str, nome: str) -> str:
	doc = frappe.get_doc(
		{"doctype": "Responsavel", "nome_completo": nome, "cpf": cpf, "celular": "11999990000"}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _criar_usuario(email: str, roles: list[str] | None = None) -> None:
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	if roles:
		frappe.get_doc("User", email).add_roles(*roles)


def _criar_transparencia(tipo: str, publicado: int) -> str:
	codigo = frappe.generate_hash(length=8)
	arquivo = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"{codigo}.txt",
			# Conteúdo único: o File deduplica pelo hash e devolveria a URL de outro dono.
			"content": f"documento de teste {codigo}".encode(),
			"is_private": 0,
		}
	).insert(ignore_permissions=True)
	return (
		frappe.get_doc(
			{
				"doctype": "Transparencia",
				"tipo_arquivo": tipo,
				"ano_referencia": ANO_TESTE,
				"arquivo": arquivo.file_url,
				"publicado": publicado,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)
