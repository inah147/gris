"""Testes da preservação de papéis (roles) durante a importação de associados.

Cenários cobertos:
1. Papel concedido manualmente sobrevive a `User.save()` automático
2. Concessão do papel Responsavel na importação não zera papéis existentes
3. Troca automática de perfil preserva papéis concedidos manualmente
4. Perfil definido manualmente não é rebaixado pela automação
5. Categoria/função sem mapeamento não altera o perfil do usuário
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.associate.importer import _upsert_portal_user
from gris.api.users.roles import (
	add_user_roles,
	apply_role_profile,
	get_user_roles,
	save_user_preserving_roles,
)
from gris.api.users.user_manager import _define_role_profile_por_funcao, _sync_role_profile

EMAIL_TESTE = "teste.papeis.import@example.com"
PAPEL_MANUAL = "Visualizador Calendario"
PAPEL_EXTRA = "Responsavel"


class _AssociadoFake:
	"""Stub mínimo com os campos usados pela sincronização de papéis."""

	def __init__(self, name, categoria=None, funcao=None):
		self.name = name
		self.categoria = categoria
		self.funcao = funcao


def _criar_usuario(role_profile=None) -> "frappe.Document":
	if frappe.db.exists("User", EMAIL_TESTE):
		frappe.delete_doc("User", EMAIL_TESTE, ignore_permissions=True, force=True)

	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": EMAIL_TESTE,
			"first_name": "Teste",
			"last_name": "Papeis",
			"send_welcome_email": 0,
			"enabled": 1,
			"role_profile_name": role_profile,
		}
	)
	user.insert(ignore_permissions=True)
	return user


class TestPapeisImportacaoAssociados(FrappeTestCase):
	def setUp(self):
		self._cleanup()

	def tearDown(self):
		self._cleanup()

	def _cleanup(self):
		if frappe.db.exists("User", EMAIL_TESTE):
			frappe.delete_doc("User", EMAIL_TESTE, ignore_permissions=True, force=True)
		frappe.db.commit()

	def test_01_save_preserva_papel_concedido_manualmente(self):
		"""Gravar o usuário não pode remover papéis fora do Role Profile."""
		user = _criar_usuario(role_profile="Beneficiário")
		add_user_roles(EMAIL_TESTE, [PAPEL_MANUAL, PAPEL_EXTRA])
		self.assertIn(PAPEL_EXTRA, get_user_roles(EMAIL_TESTE))

		user = frappe.get_doc("User", EMAIL_TESTE)
		user.enabled = 0
		save_user_preserving_roles(user)

		papeis = get_user_roles(EMAIL_TESTE)
		self.assertIn(PAPEL_EXTRA, papeis)
		self.assertIn(PAPEL_MANUAL, papeis)

	def test_02_importacao_nao_zera_papeis_de_usuario_existente(self):
		"""Conceder Responsavel na importação mantém os demais papéis."""
		_criar_usuario(role_profile="Dirigente")
		papeis_antes = get_user_roles(EMAIL_TESTE)
		self.assertTrue(papeis_antes, "perfil Dirigente deveria conceder papéis")

		acao = _upsert_portal_user(
			EMAIL_TESTE,
			"Teste Papeis",
			_AssociadoFake("ASSOC-TESTE"),
			responsavel_name="responsavel-inexistente-teste",
		)
		self.assertEqual(acao, "skipped")

		papeis_depois = get_user_roles(EMAIL_TESTE)
		self.assertIn(PAPEL_EXTRA, papeis_depois, "papel Responsavel deveria ser concedido")
		self.assertTrue(
			papeis_antes.issubset(papeis_depois),
			"papéis do perfil existente não podem ser removidos pela importação",
		)
		self.assertEqual(
			frappe.db.get_value("User", EMAIL_TESTE, "role_profile_name"),
			"Dirigente",
			"a importação não deve trocar o perfil de um usuário existente",
		)

	def test_03_troca_de_perfil_preserva_papeis_manuais(self):
		"""Ao trocar o perfil, papéis fora do perfil anterior são reaplicados."""
		_criar_usuario(role_profile="Beneficiário")
		add_user_roles(EMAIL_TESTE, [PAPEL_EXTRA])

		resultado = apply_role_profile(frappe.get_doc("User", EMAIL_TESTE), "Dirigente")

		papeis = get_user_roles(EMAIL_TESTE)
		self.assertEqual(resultado["perfil_novo"], "Dirigente")
		self.assertIn(PAPEL_EXTRA, papeis)
		self.assertIn("Visualizador Associados", papeis)

	def test_04_perfil_manual_nao_e_rebaixado(self):
		"""Perfil definido manualmente não é substituído pelo derivado."""
		_criar_usuario(role_profile="Diretoria Eleita")
		papeis_antes = get_user_roles(EMAIL_TESTE)

		associado = _AssociadoFake("ASSOC-TESTE", categoria="Dirigente", funcao="Diretor Administrativo")
		_sync_role_profile(
			frappe.get_doc("User", EMAIL_TESTE),
			associado,
			old_categoria="Dirigente",
			old_funcao="Diretor Presidente",
		)

		self.assertEqual(frappe.db.get_value("User", EMAIL_TESTE, "role_profile_name"), "Diretoria Eleita")
		self.assertEqual(get_user_roles(EMAIL_TESTE), papeis_antes)

	def test_05_categoria_sem_mapeamento_mantem_perfil(self):
		"""Categoria sem mapeamento não pode rebaixar o usuário para Guest."""
		self.assertIsNone(_define_role_profile_por_funcao("Colaboradores", ""))
		self.assertIsNone(_define_role_profile_por_funcao("Escotista", "Diretor de Métodos"))
		self.assertEqual(_define_role_profile_por_funcao("Dirigente", "Comissão Fiscal"), "Comissão Fiscal")
		self.assertEqual(_define_role_profile_por_funcao("Escotista", "Chefe de Seção"), "Chefe de Seção")

		_criar_usuario(role_profile="Chefe de Seção")
		papeis_antes = get_user_roles(EMAIL_TESTE)

		associado = _AssociadoFake("ASSOC-TESTE", categoria="Colaboradores", funcao="Apoio")
		_sync_role_profile(
			frappe.get_doc("User", EMAIL_TESTE),
			associado,
			old_categoria="Escotista",
			old_funcao="Chefe de Seção",
		)

		self.assertEqual(frappe.db.get_value("User", EMAIL_TESTE, "role_profile_name"), "Chefe de Seção")
		self.assertEqual(get_user_roles(EMAIL_TESTE), papeis_antes)

	def test_06_perfil_gerenciado_pela_automacao_e_atualizado(self):
		"""Quando o perfil atual é o derivado da função anterior, a troca ocorre."""
		_criar_usuario(role_profile="Assistente")
		add_user_roles(EMAIL_TESTE, [PAPEL_EXTRA])

		associado = _AssociadoFake("ASSOC-TESTE", categoria="Escotista", funcao="Chefe de Seção")
		_sync_role_profile(
			frappe.get_doc("User", EMAIL_TESTE),
			associado,
			old_categoria="Escotista",
			old_funcao="Assistente",
		)

		papeis = get_user_roles(EMAIL_TESTE)
		self.assertEqual(frappe.db.get_value("User", EMAIL_TESTE, "role_profile_name"), "Chefe de Seção")
		self.assertIn("Gestor de Associados", papeis)
		self.assertIn(PAPEL_EXTRA, papeis, "papel manual deve sobreviver à troca de perfil")
