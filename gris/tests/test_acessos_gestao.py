"""Gestão de acessos: papéis em lote, ação em massa, licenças e edição do catálogo."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.acessos import gestao
from gris.api.acessos.constantes import (
	LICENCA_ATIVA,
	LICENCA_DOCTYPE,
	LICENCA_REVOGACAO_PENDENTE,
	LICENCA_REVOGADA,
	ROLE_GESTOR,
	TIPO_FERRAMENTA,
	TIPO_PAPEL,
)
from gris.api.users.roles import add_role_to_users, get_user_roles, remove_role_from_users, remove_user_roles
from gris.install import garantir_role_gestor_de_acessos

DOMINIO = "escoteiros.org.br"
PAPEL = "Teste Gestao Acessos Papel"
PERFIL = "Teste Gestao Acessos Perfil"


def _criar_user(email: str, roles: list[str] | None = None, perfil: str | None = None) -> str:
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	frappe.db.delete("Has Role", {"parenttype": "User", "parent": email})
	frappe.db.set_value("User", email, "role_profile_name", perfil, update_modified=False)
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


def _criar_associado(email: str) -> str:
	doc = frappe.get_doc(
		{
			"doctype": "Associado",
			"nome_completo": f"Teste Gestao {email.split('@')[0].split('.')[-1]}",
			"cpf": frappe.generate_hash(length=32),
			"data_de_nascimento": "1990-01-01",
			"categoria": "Escotista",
			"historico_no_grupo": [{"data_de_ingresso": "2020-01-01"}],
		}
	).insert(ignore_permissions=True)
	frappe.db.set_value("Associado", doc.name, "id_escoteiros", email, update_modified=False)
	return doc.name


class TestGestaoDeAcessos(FrappeTestCase):
	def setUp(self):
		garantir_role_gestor_de_acessos()
		if not frappe.db.exists("Role", PAPEL):
			frappe.get_doc({"doctype": "Role", "role_name": PAPEL, "desk_access": 0}).insert(
				ignore_permissions=True
			)
		if not frappe.db.exists("Role Profile", PERFIL):
			frappe.get_doc(
				{"doctype": "Role Profile", "role_profile": PERFIL, "roles": [{"role": PAPEL}]}
			).insert(ignore_permissions=True)

		self.gestor = _criar_user(f"teste.gestao.gestor@{DOMINIO}", [ROLE_GESTOR])
		self.ana = _criar_user(f"teste.gestao.ana@{DOMINIO}")
		self.bia = _criar_user(f"teste.gestao.bia@{DOMINIO}", [PAPEL])
		self.caio = _criar_user(f"teste.gestao.caio@{DOMINIO}", [PAPEL], perfil=PERFIL)
		self.associados = {email: _criar_associado(email) for email in (self.ana, self.bia, self.caio)}

		self.acesso_papel = frappe.get_doc(
			{
				"doctype": "Acesso",
				"titulo": "Teste Gestao: papel",
				"tipo": TIPO_PAPEL,
				"papel": PAPEL,
				"descricao": "Papel de teste",
			}
		).insert(ignore_permissions=True)
		self.ferramenta = frappe.get_doc(
			{
				"doctype": "Acesso",
				"titulo": "Teste Gestao: ferramenta",
				"tipo": TIPO_FERRAMENTA,
				"descricao": "Ferramenta de teste",
				"limite_licencas": 1,
			}
		).insert(ignore_permissions=True)
		self._usuario_original = frappe.session.user
		frappe.set_user(self.gestor)

	def tearDown(self):
		frappe.set_user(self._usuario_original)
		frappe.db.after_commit.reset()
		frappe.db.rollback()
		for user in (self.gestor, self.ana, self.bia, self.caio):
			frappe.clear_cache(user=user)

	# ─── helpers de papéis ─────────────────────────────────────────────────

	def test_concessao_em_lote_ignora_quem_ja_tem(self):
		alterados = add_role_to_users(PAPEL, [self.ana, self.bia, "nao.existe@teste.gris"])
		self.assertEqual(alterados, [self.ana])
		self.assertIn(PAPEL, get_user_roles(self.ana))

	def test_revogacao_em_lote_e_individual(self):
		self.assertEqual(remove_role_from_users(PAPEL, [self.ana, self.bia]), [self.bia])
		self.assertNotIn(PAPEL, get_user_roles(self.bia))
		self.assertEqual(remove_user_roles(self.caio, [PAPEL, "Inexistente"]), [PAPEL])

	# ─── ação em massa ─────────────────────────────────────────────────────

	def test_conceder_para_selecionados(self):
		resultado = gestao.conceder_papel_em_massa(self.acesso_papel.name, usuarios=f'["{self.ana}"]')
		self.assertEqual(resultado["alterados"], 1)
		self.assertFalse(resultado["enfileirado"])
		self.assertIn(PAPEL, get_user_roles(self.ana))

	def test_revogar_ignora_papel_que_vem_do_perfil(self):
		resultado = gestao.revogar_papel_em_massa(
			self.acesso_papel.name, usuarios=f'["{self.bia}", "{self.caio}"]'
		)
		self.assertEqual(resultado["alterados"], 1)
		self.assertEqual([i["usuario"] for i in resultado["ignorados_via_perfil"]], [self.caio])
		self.assertNotIn(PAPEL, get_user_roles(self.bia))
		self.assertIn(PAPEL, get_user_roles(self.caio))

	def test_todos_sao_os_associados_ativos(self):
		elegiveis = {linha.usuario for linha in gestao.usuarios_elegiveis()}
		self.assertTrue({self.ana, self.bia, self.caio} <= elegiveis)
		# O gestor não tem cadastro de associado: fica fora do "todos".
		self.assertNotIn(self.gestor, elegiveis)

	def test_muitos_usuarios_vao_para_a_fila(self):
		with patch.object(gestao, "LIMITE_MASSA_SINCRONA", 1), patch("frappe.enqueue") as enfileirar:
			resultado = gestao.conceder_papel_em_massa(
				self.acesso_papel.name, usuarios=f'["{self.ana}", "{self.bia}", "{self.caio}"]'
			)
		self.assertTrue(resultado["enfileirado"])
		enfileirar.assert_called_once()
		self.assertNotIn(PAPEL, get_user_roles(self.ana))

	def test_so_a_gestao_faz_acao_em_massa(self):
		frappe.set_user(self.ana)
		with self.assertRaises(frappe.PermissionError):
			gestao.conceder_papel_em_massa(self.acesso_papel.name, todos=1)

	def test_papel_de_gestor_em_massa_so_com_system_manager(self):
		acesso_gestor = frappe.db.get_value("Acesso", {"papel": ROLE_GESTOR})
		if not acesso_gestor:
			acesso_gestor = (
				frappe.get_doc(
					{
						"doctype": "Acesso",
						"titulo": "Teste Gestao: gestor",
						"tipo": TIPO_PAPEL,
						"papel": ROLE_GESTOR,
						"descricao": "x",
					}
				)
				.insert(ignore_permissions=True)
				.name
			)
		with self.assertRaises(frappe.ValidationError):
			gestao.conceder_papel_em_massa(acesso_gestor, usuarios=f'["{self.ana}"]')

	def test_revogar_papel_do_perfil_individualmente_e_recusado(self):
		with self.assertRaises(frappe.ValidationError):
			gestao.revogar_papel_de_usuario(self.acesso_papel.name, self.caio)
		gestao.revogar_papel_de_usuario(self.acesso_papel.name, self.bia)
		self.assertNotIn(PAPEL, get_user_roles(self.bia))

	# ─── licenças ──────────────────────────────────────────────────────────

	def test_licenca_existente_respeita_o_limite_e_libera_a_vaga(self):
		licenca = gestao.registrar_licenca(self.ferramenta.name, self.associados[self.ana])["licenca"]
		self.assertEqual(frappe.db.get_value(LICENCA_DOCTYPE, licenca, "email"), self.ana)

		with self.assertRaises(frappe.ValidationError):
			gestao.registrar_licenca(self.ferramenta.name, self.associados[self.bia])

		gestao.marcar_revogacao(licenca)
		self.assertEqual(frappe.db.get_value(LICENCA_DOCTYPE, licenca, "status"), LICENCA_REVOGACAO_PENDENTE)
		# Pendente ainda ocupa a vaga: a conta existe na ferramenta até ser removida.
		with self.assertRaises(frappe.ValidationError):
			gestao.registrar_licenca(self.ferramenta.name, self.associados[self.bia])

		gestao.confirmar_revogacao(licenca)
		self.assertEqual(frappe.db.get_value(LICENCA_DOCTYPE, licenca, "status"), LICENCA_REVOGADA)
		gestao.registrar_licenca(self.ferramenta.name, self.associados[self.bia])

	def test_desfazer_revogacao_volta_a_ativa(self):
		licenca = gestao.registrar_licenca(self.ferramenta.name, self.associados[self.ana])["licenca"]
		gestao.marcar_revogacao(licenca)
		gestao.desfazer_revogacao(licenca)
		doc = frappe.get_doc(LICENCA_DOCTYPE, licenca)
		self.assertEqual(doc.status, LICENCA_ATIVA)
		self.assertIsNone(doc.revogacao_pendente_desde)

	def test_licenca_revogada_nao_volta(self):
		licenca = gestao.registrar_licenca(self.ferramenta.name, self.associados[self.ana])["licenca"]
		gestao.confirmar_revogacao(licenca)
		doc = frappe.get_doc(LICENCA_DOCTYPE, licenca)
		doc.status = LICENCA_ATIVA
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_resumo_conta_vagas_e_titulares(self):
		gestao.registrar_licenca(self.ferramenta.name, self.associados[self.ana])
		cards = {c["name"]: c for c in gestao.resumo()["cards"]}
		self.assertEqual(cards[self.ferramenta.name]["vagas"]["disponiveis"], 0)
		self.assertEqual(cards[self.acesso_papel.name]["titulares"], 2)
		titulares = gestao.listar_titulares(self.acesso_papel.name)["titulares"]
		self.assertEqual(
			{t["usuario"]: t["via_perfil"] for t in titulares}, {self.bia: False, self.caio: True}
		)

	# ─── catálogo ──────────────────────────────────────────────────────────

	def test_salvar_acesso_muda_limite_e_etapas(self):
		gestao.salvar_acesso(
			self.ferramenta.name,
			{
				"limite_licencas": "5",
				"descricao": "  Nova descrição  ",
				"etapas": [{"papel_aprovador": ROLE_GESTOR, "descricao": "Gestão"}],
			},
		)
		doc = frappe.get_doc("Acesso", self.ferramenta.name)
		self.assertEqual(doc.limite_licencas, 5)
		self.assertEqual(doc.descricao, "Nova descrição")
		self.assertEqual([e.papel_aprovador for e in doc.etapas_aprovacao], [ROLE_GESTOR])

	def test_etapa_com_papel_fora_da_lista_e_recusada(self):
		with self.assertRaises(frappe.ValidationError):
			gestao.salvar_acesso(self.ferramenta.name, {"etapas": [{"papel_aprovador": "Guest"}]})


class TestSementeDoCatalogo(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_semente_e_idempotente_e_preserva_edicoes(self):
		from gris.patches import semear_catalogo_de_acessos

		# Catálogo vazio, como num site novo; o rollback do tearDown devolve o que havia.
		frappe.db.delete("Etapa de Aprovacao de Acesso", {"parenttype": "Acesso"})
		frappe.db.delete("Acesso")

		semear_catalogo_de_acessos.execute()
		total = frappe.db.count("Acesso")
		frappe.db.set_value("Acesso", "Canva", "limite_licencas", 42)

		semear_catalogo_de_acessos.execute()
		self.assertEqual(frappe.db.count("Acesso"), total)
		self.assertEqual(frappe.db.get_value("Acesso", "Canva", "limite_licencas"), 42)
		self.assertFalse(frappe.db.exists("Acesso", {"papel": "Responsavel"}))
		# Todo item nasce com uma etapa da gestão de acessos, inclusive o do próprio gestor —
		# menos as contribuições, que a diretoria financeira aprova.
		etapas = frappe.get_all(
			"Etapa de Aprovacao de Acesso",
			filters={"parenttype": "Acesso"},
			fields=["parent", "papel_aprovador"],
		)
		self.assertEqual({e.parent for e in etapas}, set(frappe.get_all("Acesso", pluck="name")))
		contribuicoes = set(
			frappe.get_all("Acesso", filters={"papel": ["like", "%Contribuição Mensal%"]}, pluck="name")
		)
		self.assertEqual({e.papel_aprovador for e in etapas if e.parent not in contribuicoes}, {ROLE_GESTOR})
		self.assertEqual(
			{e.papel_aprovador for e in etapas if e.parent in contribuicoes}, {"Gestor Contribuição Mensal"}
		)


class TestAjusteDasContribuicoes(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_patch_marca_por_secao_e_preserva_edicoes(self):
		from gris.patches import ajustar_acessos_de_contribuicoes as patch_
		from gris.patches import semear_catalogo_de_acessos

		frappe.db.delete("Etapa de Aprovacao de Acesso", {"parenttype": "Acesso"})
		frappe.db.delete("Acesso")
		semear_catalogo_de_acessos.execute()

		secao = frappe.db.get_value("Acesso", {"papel": patch_.ROLE_VISUALIZADOR_SECAO}, "name")
		total = frappe.db.get_value("Acesso", {"papel": patch_.ROLE_VISUALIZADOR}, "name")
		# Como num site semeado antes: etapa padrão e texto antigo, mais uma edição da gestão.
		for nome in (secao, total):
			doc = frappe.get_doc("Acesso", nome)
			doc.set("etapas_aprovacao", [{"papel_aprovador": ROLE_GESTOR, "descricao": "Gestão de acessos"}])
			doc.save(ignore_permissions=True)
		antigo = patch_.TEXTOS[patch_.ROLE_VISUALIZADOR_SECAO]["o_que_muda"][0]
		frappe.db.set_value("Acesso", secao, "o_que_muda", antigo)
		frappe.db.set_value("Acesso", total, "descricao", "Texto escrito pela gestão.")

		patch_.execute()

		item = frappe.get_doc("Acesso", secao)
		self.assertTrue(item.por_secao)
		self.assertTrue(item.exige_associado)
		self.assertEqual(item.o_que_muda, patch_.TEXTOS[patch_.ROLE_VISUALIZADOR_SECAO]["o_que_muda"][1])
		self.assertEqual(
			[e.papel_aprovador for e in item.etapas_aprovacao], [patch_.ROLE_GESTOR_CONTRIBUICAO]
		)
		self.assertEqual(frappe.db.get_value("Acesso", total, "descricao"), "Texto escrito pela gestão.")
		self.assertFalse(frappe.db.get_value("Acesso", total, "por_secao"))
