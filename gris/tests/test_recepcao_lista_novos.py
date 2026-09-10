"""Lista de novos associados em tabela (`/recepcao/novos_associados`).

Cenários cobertos:
1. A listagem devolve todo mundo do funil, em qualquer status
2. Filtros de status, ramo e dados enviados recortam a lista
3. Filtro com valor fora das opções é ignorado em vez de virar consulta vazia
4. O responsável legal da linha é o primeiro vínculo do jovem
5. Paginação: página além do fim volta para a primeira
6. Só quem tem o papel Recepcao abre a página e chama a listagem
"""

from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.utils.documento import id_por_cpf
from gris.www.recepcao import novos_associados


def _gerar_cpf(base9: str) -> str:
	"""CPF fictício com dígitos verificadores corretos, a partir de 9 dígitos."""
	digitos = [int(d) for d in base9]
	for posicao in (9, 10):
		soma = sum(d * (posicao + 1 - i) for i, d in enumerate(digitos))
		resto = 11 - (soma % 11)
		digitos.append(0 if resto >= 10 else resto)
	return "".join(str(d) for d in digitos)


# CPFs exclusivos deste módulo, para não colidir com os dos outros testes de recepção.
CPF_LOBINHO = _gerar_cpf("723456785")
CPF_FILHOTE = _gerar_cpf("823456786")
CPF_MAE = _gerar_cpf("923456787")

# Prefixo que isola as asserções dos registros que outros testes deixam na mesma base.
PREFIXO = "Zz Lista Teste"

EMAIL_RECEPCAO = "equipe.lista.novos@example.com"
EMAIL_SEM_PAPEL = "estranho.lista.novos@example.com"


def _garantir_papel(nome: str) -> None:
	if not frappe.db.exists("Role", nome):
		frappe.get_doc({"doctype": "Role", "role_name": nome, "desk_access": 0}).insert(
			ignore_permissions=True
		)


def _garantir_usuario(email: str, nome: str, papeis: tuple[str, ...] = ()) -> None:
	if frappe.db.exists("User", email):
		return

	user = frappe.new_doc("User")
	user.email = email
	user.first_name = nome
	user.send_welcome_email = 0
	for papel in papeis:
		_garantir_papel(papel)
		user.append("roles", {"role": papel})
	user.insert(ignore_permissions=True)


def _criar_novo_associado(cpf: str, nome: str, **campos) -> str:
	name = id_por_cpf(cpf)
	if frappe.db.exists("Novo Associado", name):
		return name

	doc = frappe.get_doc({"doctype": "Novo Associado", "cpf": cpf, "nome_completo": nome, **campos})
	doc.insert(ignore_permissions=True)
	return doc.name


class TestListaDeNovosAssociados(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

		_garantir_usuario(EMAIL_RECEPCAO, "Equipe Lista", ("Recepcao",))
		_garantir_usuario(EMAIL_SEM_PAPEL, "Sem Papel Lista")

		# O ramo é escrito no before_insert a partir da data de nascimento; os status são
		# gravados depois para não depender das regras de transição do controller.
		self.lobinho = _criar_novo_associado(CPF_LOBINHO, f"{PREFIXO} Lobinho")
		self.filhote = _criar_novo_associado(CPF_FILHOTE, f"{PREFIXO} Filhote")
		frappe.db.set_value(
			"Novo Associado",
			self.lobinho,
			{"status": "Visita Agendada", "ramo": "Lobinho", "dados_para_registro_enviados": 0},
		)
		frappe.db.set_value(
			"Novo Associado",
			self.filhote,
			{"status": "Fazer Registro", "ramo": "Filhotes", "dados_para_registro_enviados": 1},
		)

		self.mae = frappe.get_doc(
			{"doctype": "Responsavel", "cpf": CPF_MAE, "nome_completo": f"{PREFIXO} Mãe"}
		)
		self.mae.insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Responsavel Vinculo",
				"responsavel": self.mae.name,
				"beneficiario_novo_associado": self.filhote,
				"primeiro_responsavel": 1,
			}
		).insert(ignore_permissions=True)

		frappe.set_user(EMAIL_RECEPCAO)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _listar(self, **filtros):
		return novos_associados.listar(busca=PREFIXO, **filtros)

	def _nomes(self, resposta) -> set[str]:
		return {linha["name"] for linha in resposta["linhas"]}

	# ----------------------------------------------------------------- listagem

	def test_lista_traz_o_funil_inteiro_independente_do_status(self):
		resposta = self._listar()

		self.assertEqual(self._nomes(resposta), {self.lobinho, self.filhote})
		self.assertEqual(resposta["total"], 2)
		self.assertEqual(resposta["pagina"], 1)

	def test_filtro_de_status_recorta_a_lista(self):
		resposta = self._listar(status="Fazer Registro")

		self.assertEqual(self._nomes(resposta), {self.filhote})

	def test_filtro_de_ramo_recorta_a_lista(self):
		resposta = self._listar(ramo="Lobinho")

		self.assertEqual(self._nomes(resposta), {self.lobinho})

	def test_filtro_de_dados_enviados_separa_enviados_de_pendentes(self):
		self.assertEqual(self._nomes(self._listar(dados_enviados="sim")), {self.filhote})
		self.assertEqual(self._nomes(self._listar(dados_enviados="nao")), {self.lobinho})

	def test_valor_fora_das_opcoes_e_ignorado(self):
		# Um status inventado na query string não pode virar filtro: a tela apareceria
		# vazia sem explicação.
		resposta = self._listar(status="Status Inventado", ramo="Ramo Inventado")

		self.assertEqual(self._nomes(resposta), {self.lobinho, self.filhote})

	def test_linha_mostra_o_primeiro_responsavel_do_jovem(self):
		resposta = self._listar(status="Fazer Registro")

		linha = resposta["linhas"][0]
		self.assertEqual(linha["responsavel_legal"], f"{PREFIXO} Mãe")
		self.assertEqual(linha["dados_enviados"], 1)
		self.assertEqual(linha["ramo_variante"], "ramo-filhotes")

	def test_pagina_alem_do_fim_volta_para_a_primeira(self):
		resposta = self._listar(pagina=99)

		self.assertEqual(resposta["pagina"], 1)
		self.assertEqual(self._nomes(resposta), {self.lobinho, self.filhote})

	# ----------------------------------------------------------------- permissão

	def test_usuario_sem_papel_de_recepcao_nao_lista(self):
		frappe.set_user(EMAIL_SEM_PAPEL)

		with self.assertRaises(frappe.PermissionError):
			novos_associados.listar()

	def test_guest_nao_lista(self):
		frappe.set_user("Guest")

		with self.assertRaises(frappe.PermissionError):
			novos_associados.listar()

	def test_pagina_renderiza_com_os_filtros_e_a_tabela(self):
		from frappe.website.serve import get_response

		frappe.form_dict.clear()
		pagina = get_response(novos_associados.CAMINHO, 200).get_data(as_text=True)

		self.assertIn("Lista de Novos Associados", pagina)
		self.assertIn('id="novos-filtros"', pagina)
		self.assertIn('id="novosAssociadosTable"', pagina)
		self.assertIn("/recepcao/novos_associados.js", pagina)

	def test_pagina_abre_para_recepcao_e_nega_para_os_demais(self):
		context = frappe._dict()
		with mock.patch.object(novos_associados, "enrich_context"):
			novos_associados.get_context(context)
		self.assertEqual(context.active_link, "/recepcao/novos_associados")
		self.assertTrue(context.itens_status)

		frappe.set_user(EMAIL_SEM_PAPEL)
		with self.assertRaises(frappe.PermissionError), mock.patch.object(novos_associados, "enrich_context"):
			novos_associados.get_context(frappe._dict())
