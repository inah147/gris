# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Gestão dos documentos de transparência pelo portal (/administracao/transparencia)."""

from __future__ import annotations

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from gris.api.administracao.transparencia import (
	PARECERES,
	excluir_documento_transparencia,
	listar_documentos_transparencia,
	publicar_documento_transparencia,
	salvar_documento_transparencia,
	tipos_de_documento,
)
from gris.api.portal_access import user_has_access
from gris.api.transparencia import build_areas_por_ano

DOMINIO = "transparencia.teste.gris"
GESTOR = f"gestor@{DOMINIO}"
EDITOR_DE_PARECER = f"parecer@{DOMINIO}"
SYSTEM_MANAGER = f"admin@{DOMINIO}"
ROTA = "/administracao/transparencia"
# Ano fora do que o site de desenvolvimento tem cadastrado, para as consultas por ano
# enxergarem só o que o teste criou.
ANO = 2011


class TestGestaoTransparencia(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Transparencia", {"ano_referencia": ANO})
		self._criar_usuario(GESTOR, ["Gestor da UEL"])
		self._criar_usuario(EDITOR_DE_PARECER, ["Editor de Parecer"])
		self._criar_usuario(SYSTEM_MANAGER, ["System Manager"])

	def tearDown(self):
		frappe.set_user("Administrator")
		# FrappeTestCase só desfaz por classe: sem isto, o que um teste grava vaza para o próximo.
		frappe.db.rollback()

	# --- acesso -------------------------------------------------------

	def test_so_o_gestor_da_uel_abre_a_pagina(self):
		self.assertTrue(user_has_access(ROTA, user=GESTOR))
		self.assertFalse(user_has_access(ROTA, user=EDITOR_DE_PARECER))
		# Página estrita: o System Manager sem o papel também fica de fora.
		self.assertFalse(user_has_access(ROTA, user=SYSTEM_MANAGER))

	def test_quem_grava_na_transparencia_pelo_desk_nao_grava_por_aqui(self):
		# O Editor de Parecer tem write no DocType, mas a página é só da gestão.
		frappe.set_user(EDITOR_DE_PARECER)
		with self.assertRaises(frappe.PermissionError):
			salvar_documento_transparencia(
				json.dumps({"tipo_arquivo": "Estatuto", "arquivo": "/files/x.pdf"})
			)

	def test_publicar_e_excluir_tambem_exigem_o_gestor(self):
		frappe.set_user(GESTOR)
		name = self._salvar("Estatuto")["name"]

		frappe.set_user(SYSTEM_MANAGER)
		with self.assertRaises(frappe.PermissionError):
			publicar_documento_transparencia(name, 1)
		with self.assertRaises(frappe.PermissionError):
			excluir_documento_transparencia(name)

	# --- pareceres: só em /financeiro/pareceres -----------------------

	def test_pareceres_ficam_fora_da_lista_e_dos_tipos(self):
		parecer = self._parecer_do_financeiro()
		frappe.set_user(GESTOR)
		self._salvar("Estatuto")

		self.assertEqual([doc["tipo_arquivo"] for doc in self._do_ano()], ["Estatuto"])
		self.assertNotIn(parecer, [doc["name"] for doc in listar_documentos_transparencia()])
		self.assertFalse(set(PARECERES) & set(tipos_de_documento()))

	def test_parecer_nao_e_cadastrado_por_aqui(self):
		frappe.set_user(GESTOR)
		for tipo in PARECERES:
			with self.assertRaises(frappe.ValidationError):
				self._salvar(tipo, trimestre_referencia="1")

	def test_parecer_existente_nao_e_alterado_por_aqui(self):
		parecer = self._parecer_do_financeiro()
		frappe.set_user(GESTOR)

		with self.assertRaises(frappe.PermissionError):
			publicar_documento_transparencia(parecer, 1)
		with self.assertRaises(frappe.PermissionError):
			excluir_documento_transparencia(parecer)
		# Nem virando outro tipo: o `name` de um parecer é recusado antes de olhar o tipo.
		with self.assertRaises(frappe.PermissionError):
			self._salvar("Estatuto", name=parecer)

		frappe.set_user("Administrator")
		self.assertEqual(
			frappe.db.get_value("Transparencia", parecer, ["tipo_arquivo", "publicado"]),
			("Parecer anual da comissão fiscal", 0),
		)

	# --- cadastro e validações ----------------------------------------

	def test_trimestre_nao_nasce_preenchido_e_cartorio_so_vale_para_o_tipo_certo(self):
		frappe.set_user(GESTOR)
		name = self._salvar("Cartão CNPJ", registrado_em_cartorio=True)["name"]
		# Sem a opção vazia no Select, o insert gravava o trimestre "1" em todo documento.
		self.assertFalse(frappe.db.get_value("Transparencia", name, "trimestre_referencia"))
		self.assertFalse(frappe.db.get_value("Transparencia", name, "registrado_em_cartorio"))

		self._salvar("Estatuto", registrado_em_cartorio=True)
		estatuto = next(doc for doc in self._do_ano() if doc["tipo_arquivo"] == "Estatuto")
		self.assertTrue(estatuto["registrado_em_cartorio"])

	def test_o_ano_vem_da_emissao_e_nao_do_payload(self):
		frappe.set_user(GESTOR)
		# O ano não é mais campo do formulário: mesmo que chegue, vale o da emissão.
		com_emissao = self._salvar("Estatuto", data_emissao=f"{ANO}-03-10", ano_referencia=1999)["name"]
		self.assertEqual(frappe.db.get_value("Transparencia", com_emissao, "ano_referencia"), ANO)

		# Sem emissão, o documento novo fica no ano do cadastro.
		sem_emissao = self._salvar("Cartão CNPJ", data_emissao="")["name"]
		self.assertEqual(frappe.db.get_value("Transparencia", sem_emissao, "ano_referencia"), getdate().year)

		# Na edição, sem emissão o ano fica como estava; com emissão, acompanha.
		arquivo = frappe.db.get_value("Transparencia", com_emissao, "arquivo")
		self._salvar("Estatuto", name=com_emissao, arquivo=arquivo, data_emissao="")
		self.assertEqual(frappe.db.get_value("Transparencia", com_emissao, "ano_referencia"), ANO)
		self._salvar("Estatuto", name=com_emissao, arquivo=arquivo, data_emissao="2012-01-05")
		self.assertEqual(frappe.db.get_value("Transparencia", com_emissao, "ano_referencia"), 2012)

	def test_tipo_fora_do_doctype_e_recusado(self):
		frappe.set_user(GESTOR)
		with self.assertRaises(frappe.ValidationError):
			self._salvar("Parecer semestral da comissão fiscal")

	def test_validade_antes_da_emissao_e_recusada(self):
		frappe.set_user(GESTOR)
		with self.assertRaises(frappe.ValidationError):
			self._salvar(
				"Certidão negativa de tributos federais",
				data_emissao="10/03/2011",
				data_validade="01/03/2011",
			)

	def test_arquivo_de_outra_pessoa_e_recusado(self):
		arquivo = self._arquivo()  # enviado pelo Administrator
		frappe.set_user(GESTOR)
		with self.assertRaises(frappe.PermissionError):
			self._salvar("Estatuto", arquivo=arquivo)

	# --- edição -------------------------------------------------------

	def test_edicao_corrige_o_registro_sem_criar_outro(self):
		frappe.set_user(GESTOR)
		criado = self._salvar("Relatório de atividades")
		arquivo = self._do_ano()[0]["arquivo"]

		# Mesmo arquivo: não é envio novo, e passa mesmo já anexado ao documento.
		self._salvar(
			"Relatório de atividades",
			name=criado["name"],
			arquivo=arquivo,
			area="Financeiro",
			publicado=True,
		)
		(doc,) = self._do_ano()
		self.assertEqual(doc["name"], criado["name"])
		self.assertEqual(doc["area"], "Financeiro")
		self.assertTrue(doc["publicado"])

	def test_trocar_o_arquivo_na_edicao_exige_um_envio_proprio(self):
		frappe.set_user(GESTOR)
		name = self._salvar("Estatuto")["name"]

		frappe.set_user("Administrator")
		de_outro = self._arquivo()

		frappe.set_user(GESTOR)
		with self.assertRaises(frappe.PermissionError):
			self._salvar("Estatuto", name=name, arquivo=de_outro)

		novo = self._arquivo()
		self._salvar("Estatuto", name=name, arquivo=novo)
		self.assertEqual(self._do_ano()[0]["arquivo"], novo)

	# --- publicação e exclusão ----------------------------------------

	def test_publicar_e_despublicar_reflete_no_portal(self):
		frappe.set_user(GESTOR)
		name = self._salvar("Cartão CNPJ")["name"]
		self.assertEqual(build_areas_por_ano(ANO), {})

		publicar_documento_transparencia(name, True)
		areas = build_areas_por_ano(ANO)
		self.assertTrue(any("Cartão CNPJ" in item["title"] for item in areas["Documentos institucionais"]))

		publicar_documento_transparencia(name, "0")
		self.assertEqual(build_areas_por_ano(ANO), {})

	def test_excluir_apaga_o_documento_e_o_anexo(self):
		frappe.set_user(GESTOR)
		name = self._salvar("Estatuto")["name"]
		arquivo = self._do_ano()[0]["arquivo"]

		excluir_documento_transparencia(name)
		self.assertFalse(frappe.db.exists("Transparencia", name))
		self.assertFalse(frappe.db.exists("File", {"file_url": arquivo, "attached_to_name": name}))

	# ------------------------------------------------------------------

	def _parecer_do_financeiro(self):
		"""Um parecer como /financeiro/pareceres grava, direto no DocType."""
		return (
			frappe.get_doc(
				{
					"doctype": "Transparencia",
					"tipo_arquivo": "Parecer anual da comissão fiscal",
					"ano_referencia": ANO,
					"area": "Financeiro",
					"arquivo": self._arquivo(),
					"publicado": 0,
				}
			)
			.insert()
			.name
		)

	def _do_ano(self):
		return [doc for doc in listar_documentos_transparencia() if doc["ano_referencia"] == ANO]

	def _salvar(self, tipo, **extra):
		# O ano vem da emissão; por padrão, uma data em ANO.
		dados = {"tipo_arquivo": tipo, "data_emissao": f"{ANO}-06-15"}
		dados.update(extra)
		# Não `setdefault`: ele criaria o arquivo mesmo quando o teste passa o seu.
		if "arquivo" not in dados:
			dados["arquivo"] = self._arquivo()
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
