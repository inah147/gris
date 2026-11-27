# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Configurações de Assembleias: padrões do patch e validações (spec RF-04)."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.assembleias import constantes as c
from gris.patches import preparar_assembleias


class TestConfiguracoes(FrappeTestCase):
	def tearDown(self):
		# FrappeTestCase só desfaz no fim da classe; cada teste mexe no mesmo Single.
		frappe.db.rollback()

	def _config(self):
		return frappe.get_single(c.DOCTYPE_CONFIGURACOES)

	def test_patch_cria_papel(self):
		preparar_assembleias.execute()
		self.assertTrue(frappe.db.exists("Role", c.ROLE_GESTOR_ASSEMBLEIAS))

	def test_patch_preenche_padroes_sem_sobrescrever(self):
		doc = self._config()
		doc.texto_topo_edital = "Texto da gestão em {data}."
		doc.dias_limite_edital = 45
		doc.set("pauta_ordinaria", [{"titulo": "Item único", "tem_votacao": 1}])
		doc.set("materiais", [])
		doc.modelo_ata = ""
		doc.save()

		preparar_assembleias.preencher_configuracoes()
		preparar_assembleias.preencher_configuracoes()

		doc = self._config()
		self.assertEqual(doc.texto_topo_edital, "Texto da gestão em {data}.")
		self.assertEqual(doc.dias_limite_edital, 45)
		self.assertEqual([i.titulo for i in doc.pauta_ordinaria], ["Item único"])
		# O que estava vazio é preenchido, e uma só vez.
		self.assertEqual([m.item for m in doc.materiais], list(c.MATERIAIS_PADRAO))
		self.assertEqual(len(doc.pauta_extraordinaria), len(c.PAUTA_EXTRAORDINARIA))
		self.assertEqual(doc.modelo_ata, c.MODELO_ATA)

	def test_pautas_padrao_tem_orientacao_e_finalidade(self):
		ordinaria = [titulo for titulo, _v, _f in c.PAUTA_ORDINARIA]
		self.assertEqual(len(ordinaria), 11)
		self.assertEqual(len(c.PAUTA_EXTRAORDINARIA), 5)
		finalidades = {f for _t, _v, f in c.PAUTA_ORDINARIA if f}
		self.assertEqual(finalidades, set(c.FINALIDADES))
		for finalidade in c.FINALIDADES:
			self.assertIn(finalidade, c.ORIENTACAO_POR_FINALIDADE)
		self.assertEqual(c.orientacao_da_finalidade(""), c.ORIENTACAO_APROVACAO_SIMPLES)

	def test_variavel_desconhecida_e_recusada(self):
		doc = self._config()
		doc.texto_rodape_edital = "Assinado por {presidente_da_ueb}."
		with self.assertRaisesRegex(frappe.ValidationError, r"\{presidente_da_ueb\}"):
			doc.save()

	def test_codigo_de_template_e_recusado(self):
		doc = self._config()
		doc.modelo_ata = "{{ frappe.session.user }}"
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_titulo_da_pauta_com_variavel_desconhecida(self):
		doc = self._config()
		doc.append("pauta_ordinaria", {"titulo": "Gestão {mandato}"})
		with self.assertRaisesRegex(frappe.ValidationError, r"\{mandato\}"):
			doc.save()

	def test_prazo_em_dias_precisa_ser_positivo(self):
		doc = self._config()
		doc.prazo_diretoria_unidade = c.PRAZO_DIAS
		doc.prazo_diretoria_valor = 0
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_sem_limite_aceita_valor_zero(self):
		doc = self._config()
		doc.prazo_mesa_unidade = c.PRAZO_SEM_LIMITE
		doc.prazo_mesa_valor = 0
		doc.save()

	def test_representacao_precisa_ser_antes_do_voto(self):
		doc = self._config()
		doc.voto_jovens = 1
		doc.voto_representado_por_responsavel = 1
		doc.idade_minima_voto_jovem = 16
		doc.idade_minima_representacao_meses = 16 * 12
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_pasta_ligada_exige_drive_e_pasta(self):
		doc = self._config()
		doc.habilitar_pastas_drive = 1
		doc.drive_compartilhado_assembleias = ""
		with self.assertRaisesRegex(frappe.ValidationError, "drive compartilhado"):
			doc.save()

	def test_link_da_pasta_vira_id(self):
		doc = self._config()
		doc.pasta_assembleias_id = "https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOp"
		doc.save()
		self.assertEqual(self._config().pasta_assembleias_id, "1AbCdEfGhIjKlMnOp")
