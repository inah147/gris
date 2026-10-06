"""Drives no portal de acessos: o que a tela mostra e como a concessão manual é gravada.

O mecanismo de ``access_manager`` não muda; estes testes travam duas coisas do portal:

* o estado calculado do banco bate com as regras dos jobs (drive para todos por
  categoria, concessão manual ativa/expirada/em provisionamento);
* a concessão manual entra pelo Single, de modo que a gravação atrasada do job diário
  falhe com ``TimestampMismatchError`` em vez de apagar a linha nova.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime, today

from gris.api.acessos import drives, provisionamento, solicitacoes
from gris.api.acessos.constantes import (
	SETTINGS_DOCTYPE,
	SOLICITACAO_DOCTYPE,
	STATUS_AGUARDANDO_CONCESSAO,
	STATUS_CONCEDIDA,
	TIPO_DRIVE,
)
from gris.install import garantir_role_gestor_de_acessos

WORKSPACE = drives.WORKSPACE_DOCTYPE
DOMINIO = "escoteiros.org.br"
DRIVE_GLOBAL = "TESTE-ACESSOS-GLOBAL"
DRIVE_RESTRITO = "TESTE-ACESSOS-RESTRITO"


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


def _criar_associado(email: str, categoria: str) -> frappe._dict:
	doc = frappe.get_doc(
		{
			"doctype": "Associado",
			"nome_completo": f"Teste Drives {categoria}",
			"cpf": frappe.generate_hash(length=32),
			"data_de_nascimento": "1990-01-01",
			"categoria": categoria,
			"historico_no_grupo": [{"data_de_ingresso": "2020-01-01"}],
		}
	).insert(ignore_permissions=True)
	frappe.db.set_value("Associado", doc.name, "id_escoteiros", email, update_modified=False)
	return frappe.db.get_value(
		"Associado", doc.name, ["name", "id_escoteiros", "status_no_grupo", "categoria"], as_dict=True
	)


class TestDrivesDoPortal(FrappeTestCase):
	def setUp(self):
		garantir_role_gestor_de_acessos()
		settings = frappe.get_doc(WORKSPACE)
		settings.habilitar_integracao = 0
		settings.dominio_institucional = DOMINIO
		settings.dias_expiracao_acesso_restrito = 90
		settings.set(
			"drives_compartilhados",
			[
				{
					"nome_drive": "Teste Global",
					"drive_id": DRIVE_GLOBAL,
					"conceder_a_todos": 1,
					"permissao_padrao_beneficiario": "reader",
					"permissao_padrao_adulto_voluntario": "fileOrganizer",
					"ativo": 1,
				},
				{
					"nome_drive": "Teste Restrito",
					"drive_id": DRIVE_RESTRITO,
					"conceder_a_todos": 0,
					"ativo": 1,
				},
			],
		)
		settings.set("concessoes_manuais", [])
		settings.save(ignore_permissions=True)
		frappe.db.set_single_value(SETTINGS_DOCTYPE, "habilitar_avisos_whatsapp", 0)

		self.jovem = _criar_associado(f"teste.drives.jovem@{DOMINIO}", "Beneficiário")
		self.voluntario = _criar_associado(f"teste.drives.voluntario@{DOMINIO}", "Escotista")
		self.contribuinte = _criar_associado(f"teste.drives.contribuinte@{DOMINIO}", "Contribuinte")
		self._usuario_original = frappe.session.user

	def tearDown(self):
		frappe.set_user(self._usuario_original)
		frappe.db.after_commit.reset()
		frappe.db.rollback()

	def _conceder(self, associado, **campos) -> str:
		settings = frappe.get_doc(WORKSPACE)
		linha = settings.append(
			"concessoes_manuais",
			{
				"associado": associado.name,
				"email_institucional": associado.id_escoteiros,
				"drive": "Teste Restrito",
				"drive_id": DRIVE_RESTRITO,
				"tipo_acesso": "writer",
				"ativo": 1,
				**campos,
			},
		)
		settings.save(ignore_permissions=True)
		return linha.name

	# ─── estado calculado ──────────────────────────────────────────────────

	def test_drive_para_todos_segue_a_categoria(self):
		jovem = drives.estado_dos_drives(self.jovem)[DRIVE_GLOBAL]
		voluntario = drives.estado_dos_drives(self.voluntario)[DRIVE_GLOBAL]
		contribuinte = drives.estado_dos_drives(self.contribuinte)[DRIVE_GLOBAL]
		self.assertTrue(jovem["tem_acesso"])
		self.assertEqual(jovem["permissao"], "reader")
		self.assertEqual(voluntario["permissao"], "fileOrganizer")
		self.assertEqual(voluntario["permissao_rotulo"], "Administrador de conteúdo")
		self.assertFalse(contribuinte["tem_acesso"])

	def test_inativo_nao_tem_o_drive_para_todos(self):
		self.voluntario.status_no_grupo = "Inativo"
		self.assertFalse(drives.estado_dos_drives(self.voluntario)[DRIVE_GLOBAL]["tem_acesso"])

	def test_concessao_manual_ativa_em_provisionamento(self):
		self._conceder(self.voluntario)
		estado = drives.estado_dos_drives(self.voluntario)[DRIVE_RESTRITO]
		self.assertTrue(estado["tem_acesso"])
		self.assertTrue(estado["em_provisionamento"])
		self.assertEqual(estado["permissao"], "writer")
		self.assertFalse(drives.estado_dos_drives(self.jovem)[DRIVE_RESTRITO]["tem_acesso"])

	def test_concessao_manual_aplicada_mostra_a_validade(self):
		self._conceder(self.voluntario, concedido_em=now_datetime())
		estado = drives.estado_dos_drives(self.voluntario)[DRIVE_RESTRITO]
		self.assertFalse(estado["em_provisionamento"])
		self.assertEqual(str(estado["expira_em"]), add_days(today(), 90))

	def test_concessao_expirada_some(self):
		self._conceder(self.voluntario, concedido_em=now_datetime(), expira_em=add_days(today(), -1))
		self.assertFalse(drives.estado_dos_drives(self.voluntario)[DRIVE_RESTRITO]["tem_acesso"])

	def test_titulares_do_drive_restrito_sao_as_concessoes(self):
		self._conceder(self.voluntario)
		titulares = drives.titulares_do_drive(DRIVE_RESTRITO)
		self.assertFalse(titulares["global"])
		self.assertEqual([t["associado"] for t in titulares["titulares"]], [self.voluntario.name])

	# ─── gravação segura ───────────────────────────────────────────────────

	def test_gravacao_atrasada_do_job_nao_apaga_a_concessao(self):
		# O job diário carrega o Single, demora no Google e grava tudo no fim.
		copia_do_job = frappe.get_doc(WORKSPACE)

		linha = drives.registrar_concessao_manual(
			associado=self.voluntario.name,
			email=self.voluntario.id_escoteiros,
			drive_id=DRIVE_RESTRITO,
			tipo_acesso="writer",
			observacao="teste",
		)

		with self.assertRaises(frappe.TimestampMismatchError):
			copia_do_job.save(ignore_permissions=True)
		frappe.clear_messages()
		self.assertTrue(frappe.db.exists(drives.CONCESSAO_DOCTYPE, linha))

	def test_encerrar_concessao_deixa_o_job_revogar(self):
		linha = self._conceder(self.voluntario, concedido_em=now_datetime())
		alvo = drives.encerrar_concessao_manual(linha, "teste")
		self.assertEqual(alvo, {"email": self.voluntario.id_escoteiros, "drive_id": DRIVE_RESTRITO})
		ativo, expira_em = frappe.db.get_value(drives.CONCESSAO_DOCTYPE, linha, ["ativo", "expira_em"])
		self.assertEqual(ativo, 1)
		self.assertEqual(str(expira_em), add_days(today(), -1))
		self.assertFalse(drives.estado_dos_drives(self.voluntario)[DRIVE_RESTRITO]["tem_acesso"])

	# ─── do pedido à concessão ─────────────────────────────────────────────

	def test_pedido_de_drive_vira_concessao_manual(self):
		acesso = frappe.get_doc(
			{
				"doctype": "Acesso",
				"titulo": "Teste Acessos: drive restrito",
				"tipo": TIPO_DRIVE,
				"drive_id": DRIVE_RESTRITO,
				"permissao_drive": "writer",
				"descricao": "Drive de teste",
				"solicitavel": 1,
				"ativo": 1,
			}
		).insert(ignore_permissions=True)
		self.assertEqual(acesso.nome_drive, "Teste Restrito")

		solicitante = _criar_user(self.voluntario.id_escoteiros)
		frappe.set_user(solicitante)
		nome = solicitacoes.solicitar(acesso.name)["solicitacao"]["name"]

		frappe.set_user("Administrator")
		with patch("gris.api.acessos.drives.enfileirar_concessao") as enfileirar:
			solicitacoes.decidir(nome, "aprovar")
		doc = frappe.get_doc(SOLICITACAO_DOCTYPE, nome)
		self.assertEqual(doc.status, STATUS_AGUARDANDO_CONCESSAO)
		enfileirar.assert_called_once_with(nome, doc.concessao_drive)

		linha = frappe.db.get_value(
			drives.CONCESSAO_DOCTYPE,
			doc.concessao_drive,
			["associado", "drive_id", "tipo_acesso", "ativo", "concedido_em"],
			as_dict=True,
		)
		self.assertEqual(linha.associado, self.voluntario.name)
		self.assertEqual(linha.tipo_acesso, "writer")
		self.assertIsNone(linha.concedido_em)

		# A rodada diária do Workspace aplica a concessão; a reconciliação fecha o pedido.
		frappe.db.set_value(drives.CONCESSAO_DOCTYPE, doc.concessao_drive, "concedido_em", now_datetime())
		provisionamento.reconciliar_concessoes_drive()
		self.assertEqual(frappe.db.get_value(SOLICITACAO_DOCTYPE, nome, "status"), STATUS_CONCEDIDA)

	def test_drive_nao_configurado_nao_entra_no_catalogo(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Acesso",
					"titulo": "Teste Acessos: drive fantasma",
					"tipo": TIPO_DRIVE,
					"drive_id": "NAO-EXISTE",
					"descricao": "x",
				}
			).insert(ignore_permissions=True)
