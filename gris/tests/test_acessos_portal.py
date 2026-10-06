"""Portal de acessos: quem entra, o que cada um vê e o fluxo de solicitação.

Cobre o catálogo do ponto de vista da pessoa (papel direto, via perfil, licença), a
solicitação com etapas de aprovação, a concessão de papéis e de ferramentas e a regra de
que nenhum aviso sai antes do commit.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.acessos import catalogo, permissoes, provisionamento, solicitacoes
from gris.api.acessos.constantes import (
	LICENCA_ATIVA,
	LICENCA_DOCTYPE,
	ROLE_GESTOR,
	SETTINGS_DOCTYPE,
	SOLICITACAO_DOCTYPE,
	STATUS_AGUARDANDO_CONCESSAO,
	STATUS_CANCELADA,
	STATUS_CONCEDIDA,
	STATUS_EM_APROVACAO,
	STATUS_RECUSADA,
	TIPO_FERRAMENTA,
	TIPO_PAPEL,
)
from gris.install import garantir_role_gestor_de_acessos

PREFIXO = "teste.acessos"
DOMINIO = "escoteiros.org.br"

PAPEL_CONCEDIDO = "Teste Acessos Papel"
PAPEL_ETAPA_1 = "Teste Acessos Etapa Um"
PAPEL_ETAPA_2 = "Teste Acessos Etapa Dois"
PERFIL_COM_PAPEL = "Teste Acessos Perfil"


def _garantir_role(nome: str) -> None:
	if not frappe.db.exists("Role", nome):
		frappe.get_doc({"doctype": "Role", "role_name": nome, "desk_access": 0}).insert(
			ignore_permissions=True
		)


def _criar_user(email: str, roles: list[str] | None = None, perfil: str | None = None) -> str:
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
	frappe.db.delete("Has Role", {"parenttype": "User", "parent": email})
	if perfil:
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


def _criar_associado(email: str, categoria: str = "Dirigente") -> str:
	doc = frappe.get_doc(
		{
			"doctype": "Associado",
			"nome_completo": f"Teste Acessos {email.split('@')[0].split('.')[-1]}",
			"cpf": frappe.generate_hash(length=32),
			"data_de_nascimento": "1990-01-01",
			"categoria": categoria,
			"historico_no_grupo": [{"data_de_ingresso": "2020-01-01"}],
		}
	).insert(ignore_permissions=True)
	# Direto no banco: gravar `id_escoteiros` pelo documento dispararia a criação do usuário.
	frappe.db.set_value("Associado", doc.name, "id_escoteiros", email, update_modified=False)
	return doc.name


def _criar_acesso(titulo: str, tipo: str, etapas: list[str] | None = None, **campos) -> str:
	doc = frappe.get_doc(
		{
			"doctype": "Acesso",
			"titulo": titulo,
			"tipo": tipo,
			"descricao": f"Descrição de {titulo}",
			"ativo": 1,
			"solicitavel": 1,
			**campos,
		}
	)
	for papel in etapas or []:
		doc.append("etapas_aprovacao", {"papel_aprovador": papel, "descricao": f"Aprovação {papel}"})
	doc.insert(ignore_permissions=True)
	return doc.name


class _BaseAcessos(FrappeTestCase):
	def setUp(self):
		garantir_role_gestor_de_acessos()
		for papel in (PAPEL_CONCEDIDO, PAPEL_ETAPA_1, PAPEL_ETAPA_2):
			_garantir_role(papel)

		self.solicitante = _criar_user(f"{PREFIXO}.solicitante@{DOMINIO}")
		self.associado = _criar_associado(self.solicitante)
		self.aprovador_1 = _criar_user(f"{PREFIXO}.aprovador1@{DOMINIO}", [PAPEL_ETAPA_1])
		self.aprovador_2 = _criar_user(f"{PREFIXO}.aprovador2@{DOMINIO}", [PAPEL_ETAPA_2])
		_criar_associado(self.aprovador_1)
		_criar_associado(self.aprovador_2)
		self.gestor = _criar_user(f"{PREFIXO}.gestor@{DOMINIO}", [ROLE_GESTOR])
		self.responsavel = _criar_user(f"{PREFIXO}.responsavel@exemplo.com", ["Responsavel"])

		self.papel = _criar_acesso(
			"Teste Acessos: papel", TIPO_PAPEL, etapas=[PAPEL_ETAPA_1, PAPEL_ETAPA_2], papel=PAPEL_CONCEDIDO
		)
		self.ferramenta = _criar_acesso(
			"Teste Acessos: ferramenta", TIPO_FERRAMENTA, etapas=[PAPEL_ETAPA_1], limite_licencas=1
		)
		frappe.db.set_single_value(SETTINGS_DOCTYPE, "habilitar_avisos_whatsapp", 0)
		self._usuario_original = frappe.session.user

	def tearDown(self):
		frappe.set_user(self._usuario_original)
		frappe.db.after_commit.reset()
		# FrappeTestCase só faz rollback por classe: sem isto os documentos de um
		# teste vazam para o próximo.
		frappe.db.rollback()
		for user in (self.solicitante, self.aprovador_1, self.aprovador_2, self.gestor, self.responsavel):
			frappe.clear_cache(user=user)

	def _como(self, user: str):
		frappe.set_user(user)

	def _solicitar(self, acesso: str, user: str | None = None) -> str:
		self._como(user or self.solicitante)
		resultado = solicitacoes.solicitar(acesso, justificativa="Preciso para o meu trabalho.")
		return resultado["solicitacao"]["name"]

	def _decidir(self, solicitacao: str, user: str, decisao: str = "aprovar", observacao: str | None = None):
		self._como(user)
		return solicitacoes.decidir(solicitacao, decisao, observacao)


class TestQuemUsaOPortal(_BaseAcessos):
	def test_associado_usa_o_portal(self):
		self.assertTrue(permissoes.pode_usar_portal(self.solicitante))

	def test_responsavel_sem_associado_tambem_usa_o_portal(self):
		self.assertTrue(permissoes.pode_usar_portal(self.responsavel))
		self._como(self.responsavel)
		dados = catalogo.listar_meus_acessos()
		self.assertEqual(dados["email_institucional"], "")
		self.assertTrue(any(item["name"] == self.papel for item in dados["itens"]))

	def test_sem_id_escoteiros_pede_papel_mas_nao_ferramenta(self):
		nome = self._solicitar(self.papel, self.responsavel)
		doc = frappe.get_doc(SOLICITACAO_DOCTYPE, nome)
		self.assertIsNone(doc.associado)
		self.assertIsNone(doc.email_concessao)

		with self.assertRaises(frappe.ValidationError):
			self._solicitar(self.ferramenta, self.responsavel)

	def test_visitante_nao_usa_o_portal(self):
		self.assertFalse(permissoes.pode_usar_portal("Guest"))
		self._como("Guest")
		with self.assertRaises(frappe.PermissionError):
			catalogo.listar_meus_acessos()

	def test_so_gestor_e_system_manager_administram(self):
		self.assertTrue(permissoes.eh_gestor(self.gestor))
		self.assertFalse(permissoes.eh_gestor(self.solicitante))
		self.assertFalse(permissoes.eh_gestor(self.responsavel))


class TestCatalogoDaPessoa(_BaseAcessos):
	def _item(self, nome: str, user: str | None = None) -> dict:
		user = user or self.solicitante
		return catalogo.estado_do_item(user, permissoes.associado_do_usuario(user), nome)

	def test_papel_ausente_pode_ser_pedido(self):
		item = self._item(self.papel)
		self.assertEqual(item["estado"]["situacao"], catalogo.SITUACAO_NAO_TEM)
		self.assertTrue(item["pode_solicitar"])
		self.assertEqual(item["aba"], "gris")

	def test_papel_direto(self):
		_criar_user(self.solicitante, [PAPEL_CONCEDIDO])
		item = self._item(self.papel)
		self.assertEqual(item["estado"]["situacao"], catalogo.SITUACAO_TEM)
		self.assertFalse(item["pode_solicitar"])

	def test_papel_que_vem_do_perfil(self):
		if not frappe.db.exists("Role Profile", PERFIL_COM_PAPEL):
			frappe.get_doc(
				{
					"doctype": "Role Profile",
					"role_profile": PERFIL_COM_PAPEL,
					"roles": [{"role": PAPEL_CONCEDIDO}],
				}
			).insert(ignore_permissions=True)
		_criar_user(self.solicitante, [PAPEL_CONCEDIDO], perfil=PERFIL_COM_PAPEL)
		item = self._item(self.papel)
		self.assertEqual(item["estado"]["situacao"], catalogo.SITUACAO_VIA_PERFIL)
		self.assertEqual(item["estado"]["detalhe"], PERFIL_COM_PAPEL)

	def test_licenca_ativa_da_ferramenta(self):
		frappe.get_doc(
			{"doctype": LICENCA_DOCTYPE, "acesso": self.ferramenta, "associado": self.associado}
		).insert(ignore_permissions=True)
		item = self._item(self.ferramenta)
		self.assertEqual(item["estado"]["situacao"], catalogo.SITUACAO_TEM)
		self.assertEqual(item["estado"]["detalhe"], self.solicitante)
		self.assertEqual(item["vagas"], {"limite": 1, "usadas": 1, "aguardando": 0, "disponiveis": 0})

	def test_ferramenta_exige_id_escoteiros(self):
		item = catalogo.estado_do_item(self.responsavel, None, self.ferramenta)
		self.assertFalse(item["pode_solicitar"])
		self.assertIn("id@escoteiros", item["motivo_bloqueio"])

	def test_item_informativo_nao_pode_ser_pedido(self):
		frappe.db.set_value("Acesso", self.papel, "solicitavel", 0)
		item = self._item(self.papel)
		self.assertFalse(item["pode_solicitar"])
		self._como(self.solicitante)
		with self.assertRaises(frappe.ValidationError):
			solicitacoes.solicitar(self.papel)


class TestFluxoDeAprovacao(_BaseAcessos):
	def test_etapas_sao_copiadas_do_catalogo(self):
		nome = self._solicitar(self.papel)
		doc = frappe.get_doc(SOLICITACAO_DOCTYPE, nome)
		self.assertEqual([e.papel_aprovador for e in doc.etapas], [PAPEL_ETAPA_1, PAPEL_ETAPA_2])
		self.assertEqual(doc.status, STATUS_EM_APROVACAO)
		self.assertEqual(doc.etapa_atual, 1)
		self.assertEqual(doc.email_concessao, self.solicitante)

	def test_acesso_novo_nasce_aprovado_pela_gestao(self):
		sem_etapas = _criar_acesso("Teste Acessos: sem etapas", TIPO_PAPEL, papel=PAPEL_ETAPA_2)
		acesso = frappe.get_doc("Acesso", sem_etapas)
		self.assertEqual([e.papel_aprovador for e in acesso.etapas_aprovacao], [ROLE_GESTOR])

		nome = self._solicitar(sem_etapas)
		doc = frappe.get_doc(SOLICITACAO_DOCTYPE, nome)
		self.assertEqual([e.papel_aprovador for e in doc.etapas], [ROLE_GESTOR])

	def test_apagar_as_etapas_volta_ao_padrao(self):
		acesso = frappe.get_doc("Acesso", self.papel)
		acesso.set("etapas_aprovacao", [])
		acesso.save(ignore_permissions=True)
		self.assertEqual([e.papel_aprovador for e in acesso.etapas_aprovacao], [ROLE_GESTOR])

	def test_uma_solicitacao_aberta_por_acesso(self):
		self._solicitar(self.papel)
		with self.assertRaises(frappe.ValidationError):
			self._solicitar(self.papel)

	def test_duas_etapas_ate_conceder_o_papel(self):
		nome = self._solicitar(self.papel)

		# A etapa 2 ainda não é dela: quem tem o papel da etapa 2 não decide a etapa 1.
		self.assertNotIn(nome, [s["name"] for s in solicitacoes.pendentes_para(self.aprovador_2)])

		self._decidir(nome, self.aprovador_1)
		doc = frappe.get_doc(SOLICITACAO_DOCTYPE, nome)
		self.assertEqual(doc.etapa_atual, 2)
		self.assertEqual(doc.status, STATUS_EM_APROVACAO)

		with self.assertRaises(frappe.PermissionError):
			self._decidir(nome, self.aprovador_1)

		self._decidir(nome, self.aprovador_2)
		doc = frappe.get_doc(SOLICITACAO_DOCTYPE, nome)
		self.assertEqual(doc.status, STATUS_CONCEDIDA)
		self.assertIn(PAPEL_CONCEDIDO, frappe.get_roles(self.solicitante))
		self.assertTrue(
			frappe.db.exists(
				"Comment",
				{"reference_doctype": "User", "reference_name": self.solicitante, "comment_type": "Info"},
			)
		)

	def test_ninguem_aprova_o_proprio_pedido(self):
		_criar_user(self.solicitante, [PAPEL_ETAPA_1, ROLE_GESTOR])
		nome = self._solicitar(self.papel)
		with self.assertRaises(frappe.PermissionError):
			self._decidir(nome, self.solicitante)

	def test_gestor_aprova_por_padrao(self):
		padrao = _criar_acesso("Teste Acessos: padrão", TIPO_PAPEL, papel=PAPEL_ETAPA_2)
		nome = self._solicitar(padrao)
		self.assertIn(nome, [s["name"] for s in solicitacoes.pendentes_para(self.gestor)])
		self._decidir(nome, self.gestor)
		self.assertEqual(frappe.db.get_value(SOLICITACAO_DOCTYPE, nome, "status"), STATUS_CONCEDIDA)

	def test_etapa_trocada_tira_o_gestor(self):
		# O fluxo do item foi alterado para outros papéis: o gestor não decide mais.
		nome = self._solicitar(self.papel)
		self.assertNotIn(nome, [s["name"] for s in solicitacoes.pendentes_para(self.gestor)])
		with self.assertRaises(frappe.PermissionError):
			self._decidir(nome, self.gestor)

	def test_system_manager_destrava_qualquer_etapa(self):
		nome = self._solicitar(self.papel)
		self._decidir(nome, "Administrator")
		self._decidir(nome, "Administrator")
		self.assertEqual(frappe.db.get_value(SOLICITACAO_DOCTYPE, nome, "status"), STATUS_CONCEDIDA)

	def test_recusa_exige_motivo(self):
		nome = self._solicitar(self.papel)
		with self.assertRaises(frappe.ValidationError):
			self._decidir(nome, self.aprovador_1, "recusar")
		self._decidir(nome, self.aprovador_1, "recusar", "Fora do perfil da função.")
		doc = frappe.get_doc(SOLICITACAO_DOCTYPE, nome)
		self.assertEqual(doc.status, STATUS_RECUSADA)
		self.assertEqual(doc.motivo, "Fora do perfil da função.")
		self.assertNotIn(PAPEL_CONCEDIDO, frappe.get_roles(self.solicitante))

	def test_quem_pediu_cancela(self):
		nome = self._solicitar(self.papel)
		self._como(self.solicitante)
		solicitacoes.cancelar(nome)
		self.assertEqual(frappe.db.get_value(SOLICITACAO_DOCTYPE, nome, "status"), STATUS_CANCELADA)
		# Encerrada, libera um pedido novo.
		self._solicitar(self.papel)

	def test_outra_pessoa_nao_cancela(self):
		nome = self._solicitar(self.papel)
		with self.assertRaises(frappe.PermissionError):
			self._como(self.aprovador_1)
			solicitacoes.cancelar(nome)

	def test_papel_de_gestor_aprovado_pela_gestao_por_padrao(self):
		papel_gestor = frappe.db.get_value("Acesso", {"papel": ROLE_GESTOR}) or _criar_acesso(
			"Teste Acessos: gestor", TIPO_PAPEL, papel=ROLE_GESTOR
		)
		acesso = frappe.get_doc("Acesso", papel_gestor)
		acesso.ativo = 1
		acesso.solicitavel = 1
		acesso.set("etapas_aprovacao", [])
		acesso.save(ignore_permissions=True)

		nome = self._solicitar(papel_gestor)
		self._decidir(nome, self.gestor)
		self.assertIn(ROLE_GESTOR, frappe.get_roles(self.solicitante))


class TestConcessaoDeFerramenta(_BaseAcessos):
	def test_aprovacao_reserva_a_vaga_e_confirmacao_cria_a_licenca(self):
		nome = self._solicitar(self.ferramenta)
		self._decidir(nome, self.aprovador_1)
		doc = frappe.get_doc(SOLICITACAO_DOCTYPE, nome)
		self.assertEqual(doc.status, STATUS_AGUARDANDO_CONCESSAO)

		vagas = catalogo.vagas_por_ferramenta([self.ferramenta])
		self.assertEqual(vagas["aguardando"].get(self.ferramenta), 1)

		self._como(self.gestor)
		provisionamento.confirmar_concessao(nome)
		doc = frappe.get_doc(SOLICITACAO_DOCTYPE, nome)
		self.assertEqual(doc.status, STATUS_CONCEDIDA)
		licenca = frappe.get_doc(LICENCA_DOCTYPE, doc.licenca)
		self.assertEqual(licenca.status, LICENCA_ATIVA)
		self.assertEqual(licenca.email, self.solicitante)

	def test_sem_vaga_a_aprovacao_final_e_bloqueada(self):
		ocupante = _criar_associado(f"{PREFIXO}.ocupante@{DOMINIO}")
		frappe.get_doc({"doctype": LICENCA_DOCTYPE, "acesso": self.ferramenta, "associado": ocupante}).insert(
			ignore_permissions=True
		)
		nome = self._solicitar(self.ferramenta)
		with self.assertRaises(frappe.ValidationError):
			self._decidir(nome, self.aprovador_1)

	def test_so_a_gestao_confirma(self):
		nome = self._solicitar(self.ferramenta)
		self._decidir(nome, self.aprovador_1)
		self._como(self.aprovador_1)
		with self.assertRaises(frappe.PermissionError):
			provisionamento.confirmar_concessao(nome)


class TestAvisosSoDepoisDoCommit(_BaseAcessos):
	def test_aviso_aos_aprovadores_espera_o_commit(self):
		frappe.db.set_single_value(SETTINGS_DOCTYPE, "habilitar_avisos_whatsapp", 1)
		with patch("gris.api.acessos.notificacoes._avisar_aprovadores") as avisar:
			nome = self._solicitar(self.papel)
			avisar.assert_not_called()
			frappe.db.after_commit.run()
			avisar.assert_called_once_with(nome)

	def test_avisos_desligados_nao_agendam_nada(self):
		with patch("gris.api.acessos.notificacoes._avisar_aprovadores") as avisar:
			self._solicitar(self.papel)
			frappe.db.after_commit.run()
			avisar.assert_not_called()

	def test_mensagem_ao_aprovador_cita_a_etapa(self):
		from gris.api.acessos import notificacoes

		nome = self._solicitar(self.papel)
		doc = frappe.get_doc(SOLICITACAO_DOCTYPE, nome)
		texto = notificacoes._mensagem_aprovador(self.aprovador_1, doc)
		self.assertIn("Etapa 1 de 2", texto)
		self.assertIn(doc.acesso, texto)
		self.assertIn("/acessos", texto)
