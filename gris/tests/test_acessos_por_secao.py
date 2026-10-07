"""Contribuições mensais no portal de acessos: pedido por seção, acesso total e responsável.

* Quem pede "Contribuições da seção" escolhe a seção; aprovado, ganha o papel e passa a ver
  só os beneficiários daquela seção.
* A última seção revogada leva o papel junto; uma seção sem o papel não mostra nada.
* O gestor (diretoria financeira) e o visualizador do grupo seguem vendo tudo.
* O responsável não pede acessos de contribuição e só vê os filhos.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.acessos import catalogo, gestao, permissoes, secoes, solicitacoes
from gris.api.acessos.constantes import (
	ACESSO_DOCTYPE,
	SECAO_DOCTYPE,
	SETTINGS_DOCTYPE,
	SOLICITACAO_DOCTYPE,
	STATUS_CONCEDIDA,
	TIPO_PAPEL,
)
from gris.api.financeiro import pagamentos_contribuicao as servico
from gris.api.responsavel_acesso import get_responsavel_do_usuario
from gris.install import garantir_role_gestor_de_acessos

DOMINIO = "escoteiros.org.br"
SECAO_A = "Alcateia Teste Por Secao"
SECAO_B = "Tropa Teste Por Secao"


def _criar_user(email: str, roles: list[str] | None = None) -> str:
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	frappe.db.delete("Has Role", {"parenttype": "User", "parent": email})
	for indice, role in enumerate(roles or [], start=1):
		frappe.get_doc(
			{
				"doctype": "Has Role",
				"parent": email,
				"parenttype": "User",
				"parentfield": "roles",
				"idx": indice,
				"role": role,
			}
		).insert(ignore_permissions=True)
	frappe.clear_cache(user=email)
	return email


def _criar_associado(nome: str, categoria: str = "Beneficiário", email: str | None = None, **campos) -> str:
	doc = frappe.get_doc(
		{
			"doctype": "Associado",
			"nome_completo": f"Teste Por Secao {nome}",
			"cpf": frappe.generate_hash(length=32),
			"data_de_nascimento": "2014-01-01" if categoria == "Beneficiário" else "1990-01-01",
			"categoria": categoria,
			"status_no_grupo": "Ativo",
			"historico_no_grupo": [{"data_de_ingresso": "2020-01-01"}],
			**campos,
		}
	).insert(ignore_permissions=True)
	if email:
		# Direto no banco: gravar `id_escoteiros` pelo documento dispararia a criação do usuário.
		frappe.db.set_value("Associado", doc.name, "id_escoteiros", email, update_modified=False)
	return doc.name


def _acesso_da_secao() -> str:
	"""O item "Contribuições da seção", criado ou ajustado como o patch deixa."""
	nome = frappe.db.get_value(
		ACESSO_DOCTYPE, {"tipo": TIPO_PAPEL, "papel": servico.ROLE_VISUALIZADOR_SECAO}, "name"
	)
	if not nome:
		nome = (
			frappe.get_doc(
				{
					"doctype": ACESSO_DOCTYPE,
					"titulo": "Teste Contribuições da seção",
					"tipo": TIPO_PAPEL,
					"papel": servico.ROLE_VISUALIZADOR_SECAO,
					"descricao": "Contribuições de uma seção.",
					"ativo": 1,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
	frappe.db.set_value(
		ACESSO_DOCTYPE, nome, {"ativo": 1, "solicitavel": 1, "por_secao": 1, "exige_associado": 1}
	)
	return nome


class _Base(FrappeTestCase):
	def setUp(self):
		garantir_role_gestor_de_acessos()
		frappe.db.set_single_value(SETTINGS_DOCTYPE, "habilitar_avisos_whatsapp", 0)
		self._usuario_original = frappe.session.user

		self.jovem_a = _criar_associado("Jovem A", secao=SECAO_A)
		self.jovem_b = _criar_associado("Jovem B", secao=SECAO_B)
		self.pessoa = _criar_user(f"teste.porsecao.pessoa@{DOMINIO}")
		_criar_associado("Pessoa", categoria="Dirigente", email=self.pessoa)
		self.responsavel = _criar_user("teste.porsecao.responsavel@exemplo.com", ["Responsavel"])
		self.acesso = _acesso_da_secao()

	def tearDown(self):
		frappe.set_user(self._usuario_original)
		frappe.db.after_commit.reset()
		frappe.db.rollback()
		for user in (self.pessoa, self.responsavel):
			frappe.clear_cache(user=user)

	def _pedir(self, secao: str | None, user: str | None = None) -> str:
		frappe.set_user(user or self.pessoa)
		return solicitacoes.solicitar(self.acesso, justificativa="Sou da seção.", secao=secao)["solicitacao"][
			"name"
		]

	def _aprovar_tudo(self, solicitacao: str) -> None:
		# O System Manager decide qualquer etapa, seja qual for o fluxo do item no site.
		frappe.set_user("Administrator")
		while frappe.db.get_value(SOLICITACAO_DOCTYPE, solicitacao, "status") == "Em aprovação":
			solicitacoes.decidir(solicitacao, "aprovar")

	def _item(self, user: str | None = None) -> dict:
		user = user or self.pessoa
		return catalogo.estado_do_item(user, permissoes.associado_do_usuario(user), self.acesso)


class TestPedidoPorSecao(_Base):
	def test_catalogo_oferece_as_secoes_dos_beneficiarios(self):
		item = self._item()
		self.assertTrue(item["por_secao"])
		self.assertTrue(item["pode_solicitar"])
		self.assertIn(SECAO_A, item["recorte"]["disponiveis"])
		self.assertIn(SECAO_B, item["recorte"]["disponiveis"])

	def test_pedido_exige_uma_secao_existente(self):
		with self.assertRaises(frappe.ValidationError):
			self._pedir(None)
		with self.assertRaises(frappe.ValidationError):
			self._pedir("Seção que não existe")

	def test_um_pedido_aberto_por_secao(self):
		nome = self._pedir(SECAO_A.upper())
		self.assertEqual(frappe.db.get_value(SOLICITACAO_DOCTYPE, nome, "secao"), SECAO_A)
		with self.assertRaises(frappe.ValidationError):
			self._pedir(SECAO_A)
		# Outra seção pode ser pedida enquanto a primeira está em aprovação.
		self.assertTrue(self._pedir(SECAO_B))
		item = self._item()
		self.assertEqual({p["secao"] for p in item["recorte"]["pedidas"]}, {SECAO_A, SECAO_B})
		self.assertFalse({SECAO_A, SECAO_B} & set(item["recorte"]["disponiveis"]))

	def test_aprovado_ve_so_a_secao_pedida(self):
		self._aprovar_tudo(self._pedir(SECAO_A))
		self.assertIn(servico.ROLE_VISUALIZADOR_SECAO, frappe.get_roles(self.pessoa))
		self.assertTrue(frappe.db.exists(SECAO_DOCTYPE, {"usuario": self.pessoa, "secao": SECAO_A}))

		frappe.set_user(self.pessoa)
		visiveis = servico.associados_visiveis()
		self.assertIn(self.jovem_a, visiveis)
		self.assertNotIn(self.jovem_b, visiveis)
		with self.assertRaises(frappe.PermissionError):
			servico.assert_associado_visivel(self.jovem_b)

		item = self._item()
		self.assertEqual(item["recorte"]["concedidas"], [SECAO_A])
		self.assertNotIn(SECAO_A, item["recorte"]["disponiveis"])
		# Já ter o papel não impede pedir outra seção.
		self.assertTrue(item["pode_solicitar"])

	def test_duas_secoes_somam(self):
		self._aprovar_tudo(self._pedir(SECAO_A))
		self._aprovar_tudo(self._pedir(SECAO_B))
		frappe.set_user(self.pessoa)
		self.assertTrue({self.jovem_a, self.jovem_b} <= servico.associados_visiveis())
		self.assertEqual(
			frappe.db.get_value(
				SOLICITACAO_DOCTYPE, {"solicitante": self.pessoa, "secao": SECAO_B}, "status"
			),
			STATUS_CONCEDIDA,
		)

	def test_secao_sem_o_papel_nao_mostra_nada(self):
		self._aprovar_tudo(self._pedir(SECAO_A))
		_criar_user(self.pessoa, [])
		frappe.set_user(self.pessoa)
		self.assertEqual(servico.associados_visiveis(), set())


class TestRevogacaoPorSecao(_Base):
	def _concessao(self, secao: str) -> str:
		return frappe.db.get_value(SECAO_DOCTYPE, {"usuario": self.pessoa, "secao": secao}, "name")

	def test_ultima_secao_leva_o_papel(self):
		self._aprovar_tudo(self._pedir(SECAO_A))
		self._aprovar_tudo(self._pedir(SECAO_B))

		frappe.set_user("Administrator")
		self.assertFalse(gestao.revogar_secao(self._concessao(SECAO_A))["papel_revogado"])
		self.assertIn(servico.ROLE_VISUALIZADOR_SECAO, frappe.get_roles(self.pessoa))

		self.assertTrue(gestao.revogar_secao(self._concessao(SECAO_B))["papel_revogado"])
		self.assertNotIn(servico.ROLE_VISUALIZADOR_SECAO, frappe.get_roles(self.pessoa))

	def test_revogar_o_papel_apaga_as_secoes(self):
		self._aprovar_tudo(self._pedir(SECAO_A))
		frappe.set_user("Administrator")
		gestao.revogar_papel_de_usuario(self.acesso, self.pessoa)
		self.assertFalse(frappe.db.exists(SECAO_DOCTYPE, {"usuario": self.pessoa}))

	def test_gestao_concede_secao_sem_pedido(self):
		frappe.set_user("Administrator")
		gestao.conceder_secao(self.acesso, self.pessoa, SECAO_B)
		frappe.set_user(self.pessoa)
		self.assertIn(self.jovem_b, servico.associados_visiveis())
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.ValidationError):
			gestao.conceder_secao(self.acesso, self.pessoa, SECAO_B)

	def test_acesso_por_secao_fica_fora_das_acoes_em_massa(self):
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.ValidationError):
			gestao.conceder_papel_em_massa(self.acesso, usuarios=f'["{self.pessoa}"]')


class TestAcessoTotalEResponsavel(_Base):
	def test_diretoria_financeira_e_visualizador_veem_tudo(self):
		for papel in (servico.ROLE_GESTOR, servico.ROLE_VISUALIZADOR):
			_criar_user(self.pessoa, [papel, servico.ROLE_VISUALIZADOR_SECAO])
			secoes.conceder_secao(self.pessoa, servico.ROLE_VISUALIZADOR_SECAO, SECAO_A, "teste")
			frappe.set_user(self.pessoa)
			self.assertIsNone(servico.associados_visiveis())
			frappe.set_user("Administrator")
			secoes.apagar_secoes(self.pessoa, servico.ROLE_VISUALIZADOR_SECAO)

	def test_responsavel_nao_pede_contribuicoes(self):
		item = self._item(self.responsavel)
		self.assertFalse(item["pode_solicitar"])
		with self.assertRaises(frappe.ValidationError):
			self._pedir(SECAO_A, self.responsavel)

	def test_beneficiario_logado_nao_vira_responsavel_dos_irmaos(self):
		email = f"teste.porsecao.filho@{DOMINIO}"
		_criar_user(email, ["Responsavel"])
		filho = _criar_associado("Filho", email=email, secao=SECAO_A)
		irmao = _criar_associado("Irmão", secao=SECAO_A)
		responsavel = frappe.get_doc(
			{
				"doctype": "Responsavel",
				"nome_completo": "Teste Por Secao Mãe",
				"cpf": frappe.generate_hash(length=11),
				"email": "teste.porsecao.mae@exemplo.com",
			}
		).insert(ignore_permissions=True)
		for beneficiario in (filho, irmao):
			frappe.get_doc(
				{
					"doctype": "Responsavel Vinculo",
					"responsavel": responsavel.name,
					"beneficiario_associado": beneficiario,
				}
			).insert(ignore_permissions=True)

		# O caminho genérico ainda acha a mãe; a página de contribuições, não.
		self.assertEqual(get_responsavel_do_usuario(email), responsavel.name)
		self.assertIsNone(get_responsavel_do_usuario(email, incluir_vinculo_do_beneficiario=False))
		self.assertEqual(
			get_responsavel_do_usuario(
				"teste.porsecao.mae@exemplo.com", incluir_vinculo_do_beneficiario=False
			),
			responsavel.name,
		)
