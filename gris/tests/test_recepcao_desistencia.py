"""Testes da desistência no fluxo de novo associado.

Regra coberta: desistir **não apaga nada**. O registro é apenas desativado
(``desistiu``) e some das telas do fluxo; visitas, fila de espera, vínculos e
cadastros continuam no banco.
"""

import hashlib
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from gris.api.recepcao import filtrar_ativos, nomes_desistentes, processar_desistencia
from gris.www.recepcao.agenda_visitas import get_associates_for_scheduling
from gris.www.responsavel import beneficiarios

CPF_JOVEM = "00000000010"
CPF_JOVEM2 = "00000000011"
CPF_RESP = "00000000012"
EMAIL_RESP = "responsavel.desistencia@example.com"


def _md5(valor: str) -> str:
	return hashlib.md5(valor.encode("utf-8")).hexdigest()


class TestDesistenciaNovoAssociado(FrappeTestCase):
	def setUp(self):
		self._limpar()

	def tearDown(self):
		self._limpar()

	def _limpar(self):
		for cpf in (CPF_JOVEM, CPF_JOVEM2, CPF_RESP):
			md5 = _md5(cpf)
			for vinculo in frappe.get_all(
				"Responsavel Vinculo",
				or_filters={
					"responsavel": md5,
					"beneficiario_novo_associado": md5,
					"beneficiario_associado": md5,
				},
				pluck="name",
			):
				frappe.delete_doc("Responsavel Vinculo", vinculo, ignore_permissions=True, force=True)

			frappe.db.delete("Agenda de Visitas", {"jovem": md5})
			frappe.db.delete("Fila de Espera", {"associado": md5})

			for doctype in ("Associado", "Novo Associado", "Responsavel"):
				if frappe.db.exists(doctype, md5):
					frappe.delete_doc(doctype, md5, ignore_permissions=True, force=True)

		if frappe.db.exists("User", EMAIL_RESP):
			frappe.delete_doc("User", EMAIL_RESP, ignore_permissions=True, force=True)

		frappe.db.commit()

	def _criar_novo_associado(self, cpf=CPF_JOVEM, **campos) -> "frappe.model.document.Document":
		doc = frappe.get_doc(
			{
				"doctype": "Novo Associado",
				"nome_completo": f"Jovem {cpf}",
				"cpf": cpf,
				"data_de_nascimento": "2015-04-14",
				"status": "Aguardar Dados",
				"ramo": "Lobinho",
				**campos,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def _criar_responsavel_com_user(self) -> str:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": EMAIL_RESP,
				"first_name": "Responsável de Teste",
				"send_welcome_email": 0,
				"enabled": 1,
			}
		)
		user.insert(ignore_permissions=True)

		responsavel = frappe.get_doc(
			{
				"doctype": "Responsavel",
				"cpf": CPF_RESP,
				"nome_completo": "Responsável de Teste",
				"email": EMAIL_RESP,
			}
		)
		responsavel.insert(ignore_permissions=True)
		return responsavel.name

	def _vincular(self, responsavel_name: str, novo_associado_name: str) -> str:
		doc = frappe.get_doc(
			{
				"doctype": "Responsavel Vinculo",
				"responsavel": responsavel_name,
				"beneficiario_novo_associado": novo_associado_name,
				"é_guardiao_legal": 1,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def test_desistencia_desativa_sem_apagar_nada(self):
		na = self._criar_novo_associado()
		responsavel_name = self._criar_responsavel_com_user()
		vinculo_name = self._vincular(responsavel_name, na.name)

		visita = frappe.get_doc(
			{
				"doctype": "Agenda de Visitas",
				"jovem": na.name,
				"data_da_visita": today(),
				"ramo": "Lobinho",
			}
		)
		visita.insert(ignore_permissions=True)

		fila = frappe.get_doc({"doctype": "Fila de Espera", "associado": na.name, "ramo": "Lobinho"})
		fila.insert(ignore_permissions=True)
		frappe.db.commit()

		processar_desistencia(na.name, motivo="Mudou de cidade")

		na.reload()
		self.assertTrue(na.desistiu)
		self.assertEqual(str(na.data_desistencia), today())
		self.assertEqual(na.motivo_desistencia, "Mudou de cidade")
		self.assertEqual(na.nome_completo, f"Jovem {CPF_JOVEM}")

		# Nada foi excluído
		self.assertTrue(frappe.db.exists("Agenda de Visitas", visita.name))
		self.assertTrue(frappe.db.exists("Fila de Espera", fila.name))
		self.assertTrue(frappe.db.exists("Responsavel Vinculo", vinculo_name))
		self.assertTrue(frappe.db.exists("Responsavel", responsavel_name))
		self.assertTrue(frappe.db.exists("User", EMAIL_RESP))

		# O responsável ficou sem beneficiário ativo: só o acesso é desativado
		self.assertEqual(frappe.db.get_value("User", EMAIL_RESP, "enabled"), 0)
		self.assertEqual(
			frappe.db.get_value("Responsavel", responsavel_name, "nome_completo"),
			"Responsável de Teste",
		)

	def test_registro_desistente_sai_das_listagens(self):
		na = self._criar_novo_associado()
		frappe.db.commit()

		self.assertIn(na.name, [item.name for item in get_associates_for_scheduling()])

		processar_desistencia(na.name)

		self.assertNotIn(na.name, [item.name for item in get_associates_for_scheduling()])
		self.assertIn(na.name, nomes_desistentes([na.name]))
		self.assertEqual(filtrar_ativos([na.name]), [])

	def test_acesso_do_responsavel_e_mantido_com_outro_beneficiario_ativo(self):
		na = self._criar_novo_associado()
		outro = self._criar_novo_associado(cpf=CPF_JOVEM2)
		responsavel_name = self._criar_responsavel_com_user()
		self._vincular(responsavel_name, na.name)
		self._vincular(responsavel_name, outro.name)
		frappe.db.commit()

		processar_desistencia(na.name)

		self.assertEqual(frappe.db.get_value("User", EMAIL_RESP, "enabled"), 1)

	def test_associado_efetivado_e_desligado_sem_anonimizar(self):
		na = self._criar_novo_associado(registro_provisorio_efetivado=1)
		associado = frappe.get_doc(
			{
				"doctype": "Associado",
				"cpf": CPF_JOVEM,
				"nome_completo": "Jovem Efetivado",
				"data_de_nascimento": "2015-04-14",
				"historico_no_grupo": [{"data_de_ingresso": "2026-01-10"}],
			}
		)
		associado.insert(ignore_permissions=True)
		frappe.db.commit()

		processar_desistencia(na.name)

		associado.reload()
		self.assertEqual(associado.nome_completo, "Jovem Efetivado")
		self.assertEqual(associado.status_no_grupo, "Inativo")
		self.assertEqual(str(associado.historico_no_grupo[-1].data_de_desligamento), today())

	def test_segunda_chamada_nao_altera_a_desistencia_registrada(self):
		na = self._criar_novo_associado()
		frappe.db.commit()

		processar_desistencia(na.name, motivo="Primeiro motivo")
		resultado = processar_desistencia(na.name, motivo="Segundo motivo")

		na.reload()
		self.assertTrue(resultado.get("ja_registrada"))
		self.assertEqual(na.motivo_desistencia, "Primeiro motivo")

	def test_desmarcar_desistiu_limpa_data_e_motivo(self):
		na = self._criar_novo_associado()
		frappe.db.commit()

		processar_desistencia(na.name, motivo="Mudou de cidade")

		na.reload()
		na.desistiu = 0
		na.save(ignore_permissions=True)

		self.assertIsNone(na.data_desistencia)
		self.assertIsNone(na.motivo_desistencia)
		self.assertIn(na.name, [item.name for item in get_associates_for_scheduling()])

	def test_retorno_da_familia_reativa_o_mesmo_registro(self):
		na = self._criar_novo_associado(status="Fila de espera")
		responsavel_name = self._criar_responsavel_com_user()
		self._vincular(responsavel_name, na.name)
		frappe.db.commit()

		processar_desistencia(na.name, motivo="Mudou de cidade")

		with patch.object(beneficiarios, "notificar_nova_manifestacao_no_grupo_recepcao"):
			resultado = beneficiarios._reativar_beneficiario_desistente(
				na.name, responsavel_name, f"Jovem {CPF_JOVEM}", "2015-04-14"
			)

		na.reload()
		self.assertTrue(resultado["ok"])
		self.assertFalse(na.desistiu)
		self.assertIsNone(na.data_desistencia)
		# O registro volta exatamente de onde parou
		self.assertEqual(na.status, "Fila de espera")

	def test_registro_de_outra_familia_nao_e_reativado(self):
		na = self._criar_novo_associado()
		responsavel_name = self._criar_responsavel_com_user()
		frappe.db.commit()

		processar_desistencia(na.name)

		resultado = beneficiarios._reativar_beneficiario_desistente(
			na.name, responsavel_name, f"Jovem {CPF_JOVEM}", "2015-04-14"
		)

		na.reload()
		self.assertIsNone(resultado)
		self.assertTrue(na.desistiu)
