"""Licenças de ferramentas quando o associado fica inativo (e quando volta)."""

from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.acessos import inatividade, notificacoes
from gris.api.acessos.constantes import (
	LICENCA_ATIVA,
	LICENCA_DOCTYPE,
	LICENCA_REVOGACAO_PENDENTE,
	MOTIVO_INATIVACAO,
	SETTINGS_DOCTYPE,
	SOLICITACAO_DOCTYPE,
	STATUS_CANCELADA,
	TIPO_FERRAMENTA,
)
from gris.install import garantir_role_gestor_de_acessos

DOMINIO = "escoteiros.org.br"


def _criar_associado(email: str) -> str:
	doc = frappe.get_doc(
		{
			"doctype": "Associado",
			"nome_completo": f"Teste Inatividade {email.split('@')[0].split('.')[-1]}",
			"cpf": frappe.generate_hash(length=32),
			"data_de_nascimento": "1990-01-01",
			"categoria": "Escotista",
			"historico_no_grupo": [{"data_de_ingresso": "2020-01-01"}],
		}
	).insert(ignore_permissions=True)
	frappe.db.set_value("Associado", doc.name, "id_escoteiros", email, update_modified=False)
	return doc.name


class TestInatividade(FrappeTestCase):
	def setUp(self):
		garantir_role_gestor_de_acessos()
		self.canva = frappe.get_doc(
			{
				"doctype": "Acesso",
				"titulo": "Teste Inatividade: Canva",
				"tipo": TIPO_FERRAMENTA,
				"descricao": "x",
			}
		).insert(ignore_permissions=True)
		self.office = frappe.get_doc(
			{
				"doctype": "Acesso",
				"titulo": "Teste Inatividade: Office",
				"tipo": TIPO_FERRAMENTA,
				"descricao": "x",
			}
		).insert(ignore_permissions=True)
		self.email = f"teste.inatividade.saiu@{DOMINIO}"
		self.associado = _criar_associado(self.email)
		self.licencas = [
			frappe.get_doc({"doctype": LICENCA_DOCTYPE, "acesso": acesso.name, "associado": self.associado})
			.insert(ignore_permissions=True)
			.name
			for acesso in (self.canva, self.office)
		]
		frappe.db.set_single_value(
			SETTINGS_DOCTYPE, {"habilitar_avisos_whatsapp": 1, "grupo_tecnologia_whatsapp": "grupo@g.us"}
		)

	def tearDown(self):
		frappe.db.after_commit.reset()
		frappe.db.rollback()

	def _status(self):
		return [frappe.db.get_value(LICENCA_DOCTYPE, nome, "status") for nome in self.licencas]

	def test_inativacao_deixa_as_licencas_pendentes_e_avisa_uma_vez(self):
		with patch("gris.api.acessos.notificacoes._enviar_para_grupo_de_tecnologia") as enviar:
			resultado = inatividade.processar_inativacoes([self.associado])
			frappe.db.after_commit.run()

		self.assertEqual(resultado["licencas"], 2)
		self.assertEqual(resultado["avisados"], 1)
		self.assertEqual(self._status(), [LICENCA_REVOGACAO_PENDENTE] * 2)
		enviar.assert_called_once()
		mensagem = enviar.call_args.args[0]
		self.assertIn(self.email, mensagem)
		self.assertIn("Teste Inatividade: Canva", mensagem)
		self.assertIn("Teste Inatividade: Office", mensagem)

		for nome in self.licencas:
			licenca = frappe.get_doc(LICENCA_DOCTYPE, nome)
			self.assertEqual(licenca.motivo_revogacao, MOTIVO_INATIVACAO)
			self.assertIsNotNone(licenca.aviso_tecnologia_enviado_em)

		# A rodada seguinte não repete o aviso.
		with patch("gris.api.acessos.notificacoes._enviar_para_grupo_de_tecnologia") as enviar:
			self.assertEqual(inatividade.avisar_pendentes(), 0)
			frappe.db.after_commit.run()
		enviar.assert_not_called()

	def test_sem_grupo_configurado_o_aviso_fica_para_depois(self):
		frappe.db.set_single_value(SETTINGS_DOCTYPE, "grupo_tecnologia_whatsapp", "")
		resultado = inatividade.processar_inativacoes([self.associado])
		self.assertEqual(resultado["avisados"], 0)
		for nome in self.licencas:
			self.assertIsNone(frappe.db.get_value(LICENCA_DOCTYPE, nome, "aviso_tecnologia_enviado_em"))

	def test_solicitacao_aberta_e_cancelada(self):
		outra = frappe.get_doc(
			{
				"doctype": "Acesso",
				"titulo": "Teste Inatividade: Outra",
				"tipo": TIPO_FERRAMENTA,
				"descricao": "x",
			}
		).insert(ignore_permissions=True)
		solicitacao = frappe.get_doc(
			{
				"doctype": SOLICITACAO_DOCTYPE,
				"acesso": outra.name,
				"solicitante": "Administrator",
				"associado": self.associado,
			}
		).insert(ignore_permissions=True)
		with patch.object(notificacoes, "avisar_tecnologia_inativos", return_value=False):
			resultado = inatividade.processar_inativacoes([self.associado])
		self.assertEqual(resultado["solicitacoes"], 1)
		self.assertEqual(
			frappe.db.get_value(SOLICITACAO_DOCTYPE, solicitacao.name, "status"), STATUS_CANCELADA
		)

	def test_reativacao_antes_da_revogacao_mantem_as_licencas(self):
		with patch.object(notificacoes, "avisar_tecnologia_inativos", return_value=False):
			inatividade.processar_inativacoes([self.associado])
		self.assertEqual(inatividade.processar_reativacoes([self.associado]), 2)
		self.assertEqual(self._status(), [LICENCA_ATIVA] * 2)

	def test_rodada_diaria_pega_quem_ficou_inativo_por_fora(self):
		frappe.db.set_value("Associado", self.associado, "status_no_grupo", "Inativo", update_modified=False)
		with patch.object(notificacoes, "avisar_tecnologia_inativos", return_value=True):
			inatividade.processar_inativos()
		self.assertEqual(self._status(), [LICENCA_REVOGACAO_PENDENTE] * 2)

		frappe.db.set_value("Associado", self.associado, "status_no_grupo", "Ativo", update_modified=False)
		inatividade.processar_inativos()
		self.assertEqual(self._status(), [LICENCA_ATIVA] * 2)

	def test_hook_so_reage_a_mudanca_de_status(self):
		def doc(antes, depois):
			return SimpleNamespace(
				name=self.associado,
				status_no_grupo=depois,
				get_doc_before_save=lambda: SimpleNamespace(status_no_grupo=antes),
			)

		with patch("frappe.enqueue") as enfileirar:
			inatividade.ao_atualizar_associado(doc("Ativo", "Ativo"))
			enfileirar.assert_not_called()

			inatividade.ao_atualizar_associado(doc("Ativo", "Inativo"))
			enfileirar.assert_called_once()
			self.assertEqual(
				enfileirar.call_args.args[0], "gris.api.acessos.inatividade.processar_inativacoes"
			)
			self.assertEqual(enfileirar.call_args.kwargs["associados"], [self.associado])
