# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Criar, listar e excluir assembleias; permissões (spec RF-01 a RF-03)."""

from __future__ import annotations

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate

from gris.api.assembleias import constantes as c
from gris.api.assembleias import endpoints, padroes
from gris.api.assembleias.permissoes import pode_gerenciar_assembleias

USUARIO_SEM_PAPEL = "zz-teste-assembleia-sem-papel@example.com"
USUARIO_GESTOR = "zz-teste-assembleia-gestor@example.com"


def _usuario(email: str, papeis: tuple[str, ...] = ()) -> str:
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "ZZ Teste", "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	user = frappe.get_doc("User", email)
	user.set("roles", [])
	for papel in papeis:
		user.append("roles", {"role": papel})
	user.save(ignore_permissions=True)
	return email


def _criar(data=None, tipo=c.TIPO_ORDINARIA, hora="14:30", local="Sede") -> dict:
	data = data or add_days(getdate(), 90)
	return endpoints.criar_assembleia(
		json.dumps({"data": str(data), "tipo": tipo, "hora_primeira_convocacao": hora, "local": local})
	)


class _Base(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		# Assembleias que já existam no site atrapalham "um por dia" e a data anterior.
		for name in frappe.get_all(c.DOCTYPE_ASSEMBLEIA, pluck="name"):
			frappe.delete_doc(c.DOCTYPE_ASSEMBLEIA, name, force=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()


class TestCriacao(_Base):
	def test_cria_com_padroes(self):
		data = add_days(getdate(), 60)
		doc = frappe.get_doc(c.DOCTYPE_ASSEMBLEIA, _criar(data)["name"])

		self.assertEqual(str(doc.hora_segunda_convocacao), "15:00:00")
		self.assertEqual(len(doc.pauta), len(padroes.configuracoes().pauta_ordinaria))
		self.assertEqual(len(doc.checklist), len(c.CHECKLIST_PADRAO))
		self.assertTrue(doc.edital_texto_topo)
		self.assertTrue(doc.titulo.startswith("Assembleia Ordinária"))
		self.assertGreaterEqual(doc.vagas_delegados, 0)
		for item in doc.pauta:
			self.assertNotIn("{", item.titulo, item.titulo)
			self.assertTrue(item.orientacao_conducao)

	def test_titulos_resolvidos(self):
		data = getdate(f"{getdate().year + 1}-12-05")
		anterior = frappe.get_doc(
			{
				"doctype": c.DOCTYPE_ASSEMBLEIA,
				"data": add_days(data, -365),
				"tipo": c.TIPO_ORDINARIA,
				"local": "Sede",
				"hora_primeira_convocacao": "14:30:00",
			}
		).insert()
		doc = frappe.get_doc(c.DOCTYPE_ASSEMBLEIA, _criar(data)["name"])
		titulos = " | ".join(item.titulo for item in doc.pauta)

		self.assertIn(f"Gestão {data.year + 1}-{data.year + 2}", titulos)
		self.assertIn(f"exercício de {data.year}", titulos)
		self.assertIn(f"realizada em {padroes.data_curta(anterior.data)}", titulos)

	def test_extraordinaria_tem_a_pauta_curta(self):
		doc = frappe.get_doc(c.DOCTYPE_ASSEMBLEIA, _criar(tipo=c.TIPO_EXTRAORDINARIA)["name"])
		self.assertEqual(len(doc.pauta), len(padroes.configuracoes().pauta_extraordinaria))

	def test_mesmo_dia_e_recusado(self):
		data = add_days(getdate(), 40)
		_criar(data)
		with self.assertRaisesRegex(frappe.ValidationError, "Já existe uma assembleia"):
			_criar(data)

	def test_data_no_passado_e_recusada(self):
		with self.assertRaisesRegex(frappe.ValidationError, "passado"):
			_criar(add_days(getdate(), -1))

	def test_campos_obrigatorios(self):
		with self.assertRaises(frappe.ValidationError):
			_criar(local="")

	def test_mudar_configuracao_nao_altera_assembleia(self):
		doc = frappe.get_doc(c.DOCTYPE_ASSEMBLEIA, _criar()["name"])
		config = padroes.configuracoes()
		config.texto_topo_edital = "Outro texto em {data}."
		config.save()
		doc.reload()
		self.assertNotEqual(doc.edital_texto_topo, "Outro texto em {data}.")

	def test_segunda_convocacao(self):
		self.assertEqual(padroes.segunda_convocacao("14:30:00"), "15:00:00")
		self.assertEqual(padroes.segunda_convocacao("23:45:00"), "00:15:00")
		self.assertEqual(padroes.segunda_convocacao(""), "")

	def test_data_por_extenso(self):
		self.assertEqual(padroes.data_por_extenso("2026-12-05"), "05 de dezembro de 2026")


class TestExclusao(_Base):
	def _com_inscricoes(self) -> str:
		name = _criar()["name"]
		frappe.get_doc({"doctype": c.DOCTYPE_ASSUNTO, "assembleia": name, "conteudo": "Pauta extra"}).insert(
			ignore_permissions=True
		)
		return name

	def test_exclusao_apaga_inscricoes(self):
		name = self._com_inscricoes()
		self.assertEqual(endpoints.contagem_de_inscricoes(name)["assuntos"], 1)
		endpoints.excluir_assembleia(name)
		self.assertFalse(frappe.db.exists(c.DOCTYPE_ASSEMBLEIA, name))
		self.assertFalse(frappe.db.exists(c.DOCTYPE_ASSUNTO, {"assembleia": name}))

	def test_edital_publicado_recusa_exclusao(self):
		name = _criar()["name"]
		frappe.db.set_value(c.DOCTYPE_ASSEMBLEIA, name, "edital_publicado", 1)
		with self.assertRaises(frappe.PermissionError):
			endpoints.excluir_assembleia(name)
		self.assertTrue(frappe.db.exists(c.DOCTYPE_ASSEMBLEIA, name))

	def test_on_trash_pelo_desk_tambem_apaga(self):
		name = self._com_inscricoes()
		frappe.delete_doc(c.DOCTYPE_ASSEMBLEIA, name)
		self.assertFalse(frappe.db.exists(c.DOCTYPE_ASSUNTO, {"assembleia": name}))

	def test_gestor_sem_system_manager_nao_exclui_publicada_pelo_desk(self):
		name = _criar()["name"]
		frappe.db.set_value(c.DOCTYPE_ASSEMBLEIA, name, "edital_publicado", 1)
		frappe.set_user(_usuario(USUARIO_GESTOR, (c.ROLE_GESTOR_ASSEMBLEIAS,)))
		with self.assertRaises(frappe.PermissionError):
			frappe.delete_doc(c.DOCTYPE_ASSEMBLEIA, name)


class TestListaDeAssembleias(_Base):
	def test_separa_proximas_e_realizadas(self):
		futura = _criar(add_days(getdate(), 10))["name"]
		passada = frappe.get_doc(
			{
				"doctype": c.DOCTYPE_ASSEMBLEIA,
				"data": add_days(getdate(), -10),
				"tipo": c.TIPO_ORDINARIA,
				"local": "Sede",
				"hora_primeira_convocacao": "14:30:00",
			}
		).insert()
		lista = endpoints.listar_assembleias()
		self.assertEqual([a["name"] for a in lista["proximas"]], [futura])
		self.assertEqual([a["name"] for a in lista["realizadas"]], [passada.name])

	def test_situacao_do_edital(self):
		hoje = getdate()
		self.assertEqual(endpoints.situacao_do_edital(1, add_days(hoje, -5), hoje), "publicado")
		self.assertEqual(endpoints.situacao_do_edital(0, add_days(hoje, -1), hoje), "vencido")
		self.assertEqual(endpoints.situacao_do_edital(0, hoje, hoje), "rascunho")

	def test_conta_inscricoes(self):
		name = _criar()["name"]
		frappe.get_doc({"doctype": c.DOCTYPE_ASSUNTO, "assembleia": name, "conteudo": "A"}).insert(
			ignore_permissions=True
		)
		card = endpoints.listar_assembleias()["proximas"][0]
		self.assertEqual(card["assuntos"], 1)
		self.assertEqual(card["candidaturas"], 0)


class TestPermissoes(_Base):
	def test_sem_papel_nao_cria(self):
		frappe.set_user(_usuario(USUARIO_SEM_PAPEL))
		self.assertFalse(pode_gerenciar_assembleias())
		with self.assertRaises(frappe.PermissionError):
			_criar()

	def test_sem_papel_nao_exclui_nem_configura(self):
		name = _criar()["name"]
		frappe.set_user(_usuario(USUARIO_SEM_PAPEL))
		with self.assertRaises(frappe.PermissionError):
			endpoints.excluir_assembleia(name)
		with self.assertRaises(frappe.PermissionError):
			endpoints.salvar_configuracoes(json.dumps({"cidade": "X"}))

	def test_gestor_cria(self):
		frappe.set_user(_usuario(USUARIO_GESTOR, (c.ROLE_GESTOR_ASSEMBLEIAS,)))
		self.assertTrue(pode_gerenciar_assembleias())
		self.assertTrue(_criar()["name"])

	def test_gestor_salva_configuracoes(self):
		frappe.set_user(_usuario(USUARIO_GESTOR, (c.ROLE_GESTOR_ASSEMBLEIAS,)))
		dados = endpoints.salvar_configuracoes(json.dumps({"cidade": "Santo André", "materiais": ["Telão"]}))
		self.assertEqual(dados["materiais"], ["Telão"])

	def test_pauta_padrao_vazia_e_recusada(self):
		with self.assertRaisesRegex(frappe.ValidationError, "pelo menos um item"):
			endpoints.salvar_configuracoes(json.dumps({"pauta_ordinaria": [{"titulo": " "}]}))

	def test_finalidade_invalida_e_recusada(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Finalidade inválida"):
			endpoints.salvar_configuracoes(
				json.dumps({"pauta_ordinaria": [{"titulo": "A", "finalidade": "Outra"}]})
			)

	def test_paginas_registradas(self):
		from gris.api.portal_access import PAGE_ROLES

		for rota in (
			"/administracao/assembleias",
			"/administracao/assembleias/configuracoes",
			"/administracao/assembleias/assembleia",
		):
			self.assertIn(c.ROLE_GESTOR_ASSEMBLEIAS, PAGE_ROLES[rota])
