# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Documentos do grupo como a Captação os lê: versão atual, histórico e situação.

O envio é da página Documentos da Administração e é testado em
`test_gestao_transparencia.py`; aqui os documentos entram por ela.
"""

from __future__ import annotations

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, nowdate

from gris.api.administracao.documentos import listar_documentos, situacao_do_documento
from gris.api.administracao.transparencia import salvar_documento_transparencia

DOMINIO = "documentos.teste.gris"
GESTOR = f"gestor@{DOMINIO}"
QUALQUER = f"qualquer@{DOMINIO}"


class TestDocumentosDoGrupo(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		# Parte de uma base limpa dos tipos testados: o site de desenvolvimento pode
		# já ter documentos reais cadastrados.
		frappe.db.delete("Transparencia", {"tipo_arquivo": ["in", ["Cartão CNPJ", "Estatuto"]]})
		self._criar_usuario(GESTOR, ["Gestor da UEL"])
		self._criar_usuario(QUALQUER, [])

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_a_versao_mais_recente_e_a_atual(self):
		frappe.set_user(GESTOR)
		self._salvar("Estatuto", data_emissao="2019-05-02", registrado_em_cartorio=True)
		self._salvar("Estatuto", data_emissao="2024-03-10")

		estatuto = self._documento("Estatuto")
		self.assertEqual(estatuto["atual"]["ano_referencia"], 2024)
		self.assertEqual(estatuto["atual"]["data_emissao"], "2024-03-10")
		self.assertEqual(len(estatuto["anteriores"]), 1)
		self.assertTrue(estatuto["anteriores"][0]["registrado_em_cartorio"])
		self.assertEqual(estatuto["situacao"], "em_dia")

	def test_nao_publicado_esconde_o_link_de_quem_nao_e_da_gestao(self):
		frappe.set_user(GESTOR)
		self._salvar("Estatuto", publicado=False)
		self.assertTrue(self._documento("Estatuto")["atual"]["arquivo"])

		frappe.set_user(QUALQUER)
		self.assertIsNone(self._documento("Estatuto")["atual"]["arquivo"])

	def test_situacao(self):
		hoje = getdate()
		vencido = {"data_validade": add_days(nowdate(), -1), "ano_referencia": hoje.year}
		self.assertEqual(
			situacao_do_documento("Consulta à regularidade do empregador", vencido)[0], "vencido"
		)
		self.assertEqual(situacao_do_documento("Estatuto", None)[0], "ausente")
		relatorio_velho = {"ano_referencia": hoje.year - 2}
		self.assertEqual(
			situacao_do_documento("Relatório de atividades", relatorio_velho)[0], "desatualizado"
		)
		relatorio_do_ano_passado = {"ano_referencia": hoje.year - 1}
		self.assertEqual(
			situacao_do_documento("Relatório de atividades", relatorio_do_ano_passado)[0], "em_dia"
		)

	# ------------------------------------------------------------------

	def _documento(self, tipo):
		return next(doc for doc in listar_documentos([tipo]) if doc["tipo"] == tipo)

	def _salvar(self, tipo, **extra):
		dados = {"tipo_arquivo": tipo, "arquivo": self._arquivo()}
		dados.update(extra)
		return salvar_documento_transparencia(json.dumps(dados))

	def _arquivo(self):
		codigo = frappe.generate_hash(length=8)
		return (
			frappe.get_doc(
				{
					"doctype": "File",
					# Texto e não PDF: o Frappe abre todo PDF enviado para procurar
					# JavaScript, e um PDF de mentira quebraria o insert.
					"file_name": f"{codigo}.txt",
					# Conteúdo único: o File deduplica pelo hash do conteúdo e devolveria a
					# URL de um arquivo anterior, de outro dono.
					"content": f"documento de teste {codigo}".encode(),
					"is_private": 0,
				}
			)
			.insert(ignore_permissions=True)
			.file_url
		)

	def _criar_usuario(self, email, roles):
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": email.split("@")[0],
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)
		user = frappe.get_doc("User", email)
		user.set("roles", [])
		for role in roles:
			user.append("roles", {"role": role})
		user.save(ignore_permissions=True)
