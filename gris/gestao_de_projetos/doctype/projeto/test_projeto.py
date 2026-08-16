# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.gestao_de_projetos.doctype.projeto import projeto as projeto_module


class _DummyDoc:
	def __init__(self, payload: dict):
		self.payload = payload

	def get(self, key: str):
		return self.payload.get(key)

	def set(self, key: str, value):
		self.payload[key] = value

	def append(self, key: str, value: dict):
		self.payload.setdefault(key, []).append(frappe._dict(value))


def _patch_person_payload_lookup():
	original = projeto_module._get_person_payload_by_type

	def fake_lookup(tipo_pessoa: str, docname: str, strict: bool):
		return {
			"nome": f"{tipo_pessoa}-{docname}",
			"email": f"{docname.lower()}@teste.local",
			"telefone": "11999990000",
		}

	projeto_module._get_person_payload_by_type = fake_lookup
	return original


def _patch_associado_payload():
	"""Evita a busca real de Associado na validação estrita de envolvidos."""
	original = projeto_module._get_associado_payload

	def fake_payload(name: str):
		return {
			"nome": f"Associado-{name}",
			"email": f"{name.lower()}@teste.local",
			"telefone": "11999990000",
		}

	projeto_module._get_associado_payload = fake_payload
	return original


def _patch_coordinator_profile(categoria: str = "", secao: str = "", ramo: str = ""):
	original = projeto_module._get_coordinator_profile

	def fake_profile(doc):
		return {
			"coordenador": (doc.get("coordenador") or "").strip(),
			"categoria": categoria,
			"secao": secao,
			"ramo": ramo,
		}

	projeto_module._get_coordinator_profile = fake_profile
	return original


def _patch_section_chiefs(chefes: list[str]):
	original = projeto_module._get_section_chief_associados

	def fake_section_chiefs(secao: str, ramo: str = ""):
		return list(chefes)

	projeto_module._get_section_chief_associados = fake_section_chiefs
	return original


class TestProjeto(FrappeTestCase):
	def test_initial_stage_requires_all_approvers(self):
		original_lookup = _patch_person_payload_lookup()
		try:
			doc = _DummyDoc(
				{
					"tipo_padrinho_ou_orientador": "Associado",
					"padrinho_associado": "SPONSOR-1",
					"envolvidos": [
						frappe._dict(
							{
								"tipo_pessoa": "Associado",
								"associado": "SPONSOR-1",
								"aprovador": 1,
								"padrinho_orientador": 1,
								"origem_regra_aprovador": "padrinho_orientador",
								"permite_remover": 0,
							}
						),
						frappe._dict(
							{
								"tipo_pessoa": "Associado",
								"associado": "ASSOC-2",
								"aprovador": 1,
								"origem_regra_aprovador": "manual",
								"permite_remover": 1,
							}
						),
						frappe._dict(
							{
								"tipo_pessoa": "Associado",
								"associado": "DIR-1",
								"aprovador": 1,
								"origem_regra_aprovador": "diretor_presidente",
								"permite_remover": 1,
							}
						),
					],
					"comentarios_revisao_aprovacao": [],
				}
			)

			pipeline = projeto_module._build_approval_pipeline(doc)
			self.assertEqual(pipeline[0]["key"], projeto_module.STAGE_APROVADORES_INICIAIS)
			self.assertEqual(pipeline[1]["key"], projeto_module.STAGE_DIRETOR)

			current_stage = projeto_module._get_current_approval_stage(doc, pipeline)
			self.assertEqual(current_stage["key"], projeto_module.STAGE_APROVADORES_INICIAIS)

			doc.payload["comentarios_revisao_aprovacao"] = [
				frappe._dict(
					{
						"tipo_revisao": "Aprovacao",
						"etapa_aprovacao": projeto_module.STAGE_APROVADORES_INICIAIS,
						"aprovador": "Associado:SPONSOR-1",
						"aprovador_tipo": "Associado",
						"aprovador_associado": "SPONSOR-1",
					}
				)
			]

			current_stage = projeto_module._get_current_approval_stage(doc, pipeline)
			self.assertEqual(current_stage["key"], projeto_module.STAGE_APROVADORES_INICIAIS)

			doc.payload["comentarios_revisao_aprovacao"].append(
				frappe._dict(
					{
						"tipo_revisao": "Aprovacao",
						"etapa_aprovacao": projeto_module.STAGE_APROVADORES_INICIAIS,
						"aprovador": "Associado:ASSOC-2",
						"aprovador_tipo": "Associado",
						"aprovador_associado": "ASSOC-2",
					}
				)
			)

			current_stage = projeto_module._get_current_approval_stage(doc, pipeline)
			self.assertEqual(current_stage["key"], projeto_module.STAGE_DIRETOR)

			doc.payload["comentarios_revisao_aprovacao"].append(
				frappe._dict(
					{
						"tipo_revisao": "Aprovacao",
						"etapa_aprovacao": projeto_module.STAGE_DIRETOR,
						"aprovador": "Associado:DIR-1",
						"aprovador_tipo": "Associado",
						"aprovador_associado": "DIR-1",
					}
				)
			)

			current_stage = projeto_module._get_current_approval_stage(doc, pipeline)
			self.assertIsNone(current_stage)
		finally:
			projeto_module._get_person_payload_by_type = original_lookup

	def test_sponsor_is_enforced_in_approver_rules(self):
		original_lookup = _patch_person_payload_lookup()
		original_payload = _patch_associado_payload()
		try:
			doc = _DummyDoc(
				{
					"tipo_padrinho_ou_orientador": "Associado",
					"padrinho_associado": "SPONSOR-1",
					"envolvidos": [
						# Padrinho presente como envolvido, mas ainda não marcado
						# como aprovador: a regra tem que promovê-lo.
						frappe._dict(
							{
								"tipo_pessoa": "Associado",
								"associado": "SPONSOR-1",
								"padrinho_orientador": 1,
								"aprovador": 0,
							}
						),
						frappe._dict(
							{
								"tipo_pessoa": "Associado",
								"associado": "ASSOC-2",
								"aprovador": 1,
								"origem_regra_aprovador": "manual",
								"permite_remover": 1,
							}
						),
					],
				}
			)

			projeto_module._sync_sponsor_approver(doc)
			projeto_module._assert_aprovadores_rules(doc)

			aprovadores = projeto_module._get_effective_aprovadores(doc, strict=True)
			sponsor_keys = [
				row.get("key")
				for row in aprovadores
				if row.get("origem_regra") == projeto_module.APPROVER_ORIGIN_PADRINHO
			]
			self.assertIn("Associado:SPONSOR-1", sponsor_keys)
		finally:
			projeto_module._get_person_payload_by_type = original_lookup
			projeto_module._get_associado_payload = original_payload

	def test_section_chief_stage_between_initial_and_director(self):
		original_lookup = _patch_person_payload_lookup()
		original_profile = _patch_coordinator_profile(categoria="Beneficiario", secao="Escoteiro")
		original_section_chiefs = _patch_section_chiefs(["CHEFE-1"])
		try:
			doc = _DummyDoc(
				{
					"coordenador": "COORD-1",
					"tipo_padrinho_ou_orientador": "Associado",
					"padrinho_associado": "SPONSOR-1",
					"envolvidos": [
						frappe._dict(
							{
								"tipo_pessoa": "Associado",
								"associado": "SPONSOR-1",
								"aprovador": 1,
								"padrinho_orientador": 1,
								"origem_regra_aprovador": "padrinho_orientador",
								"permite_remover": 0,
							}
						),
						frappe._dict(
							{
								"tipo_pessoa": "Associado",
								"associado": "DIR-1",
								"aprovador": 1,
								"origem_regra_aprovador": "diretor_presidente",
								"permite_remover": 1,
							}
						),
					],
					"comentarios_revisao_aprovacao": [],
				}
			)

			projeto_module._sync_sponsor_approver(doc)
			pipeline = projeto_module._build_approval_pipeline(doc)
			self.assertEqual(
				[item["key"] for item in pipeline],
				[
					projeto_module.STAGE_APROVADORES_INICIAIS,
					projeto_module.STAGE_CHEFE_SECAO,
					projeto_module.STAGE_DIRETOR,
				],
			)

			current_stage = projeto_module._get_current_approval_stage(doc, pipeline)
			self.assertEqual(current_stage["key"], projeto_module.STAGE_APROVADORES_INICIAIS)

			doc.payload["comentarios_revisao_aprovacao"] = [
				frappe._dict(
					{
						"tipo_revisao": "Aprovacao",
						"etapa_aprovacao": projeto_module.STAGE_APROVADORES_INICIAIS,
						"aprovador": "Associado:SPONSOR-1",
						"aprovador_tipo": "Associado",
						"aprovador_associado": "SPONSOR-1",
					}
				)
			]

			current_stage = projeto_module._get_current_approval_stage(doc, pipeline)
			self.assertEqual(current_stage["key"], projeto_module.STAGE_CHEFE_SECAO)

			doc.payload["comentarios_revisao_aprovacao"].append(
				frappe._dict(
					{
						"tipo_revisao": "Aprovacao",
						"etapa_aprovacao": projeto_module.STAGE_CHEFE_SECAO,
						"aprovador": "Associado:CHEFE-1",
						"aprovador_tipo": "Associado",
						"aprovador_associado": "CHEFE-1",
					}
				)
			)

			current_stage = projeto_module._get_current_approval_stage(doc, pipeline)
			self.assertEqual(current_stage["key"], projeto_module.STAGE_DIRETOR)
		finally:
			projeto_module._get_person_payload_by_type = original_lookup
			projeto_module._get_coordinator_profile = original_profile
			projeto_module._get_section_chief_associados = original_section_chiefs

	def test_section_chief_is_required_for_youth_coordinator(self):
		original_lookup = _patch_person_payload_lookup()
		original_profile = _patch_coordinator_profile(categoria="Beneficiario", secao="Escoteiro")
		original_section_chiefs = _patch_section_chiefs([])
		try:
			doc = _DummyDoc(
				{
					"coordenador": "COORD-1",
					"tipo_padrinho_ou_orientador": "Associado",
					"padrinho_associado": "SPONSOR-1",
					"envolvidos": [
						frappe._dict(
							{
								"tipo_pessoa": "Associado",
								"associado": "SPONSOR-1",
								"aprovador": 1,
								"padrinho_orientador": 1,
								"origem_regra_aprovador": "padrinho_orientador",
								"permite_remover": 0,
							}
						),
						frappe._dict(
							{
								"tipo_pessoa": "Associado",
								"associado": "DIR-1",
								"aprovador": 1,
								"origem_regra_aprovador": "diretor_presidente",
								"permite_remover": 1,
							}
						),
					],
				}
			)

			with self.assertRaises(frappe.ValidationError):
				projeto_module._assert_aprovadores_rules(doc)
		finally:
			projeto_module._get_person_payload_by_type = original_lookup
			projeto_module._get_coordinator_profile = original_profile
			projeto_module._get_section_chief_associados = original_section_chiefs

	def test_section_chief_lookup_fallbacks_to_ramo(self):
		original_get_all = projeto_module.frappe.get_all

		def fake_get_all(doctype, *args, **kwargs):
			if doctype == "Associado" and kwargs.get("filters") == {"funcao": ["like", "%Chefe%"]}:
				return [
					{
						"name": "CHEFE-ESCOTEIRO",
						"funcao": "Chefe de Seção",
						"secao": "",
						"ramo": "Escoteiro",
					},
					{
						"name": "CHEFE-LOBINHO",
						"funcao": "Chefe de Seção",
						"secao": "",
						"ramo": "Lobinho",
					},
				]
			return original_get_all(doctype, *args, **kwargs)

		projeto_module.frappe.get_all = fake_get_all
		try:
			chefes = projeto_module._get_section_chief_associados("Anhanguera", ramo="Escoteiro")
			self.assertEqual(chefes, ["CHEFE-ESCOTEIRO"])
		finally:
			projeto_module.frappe.get_all = original_get_all

	def test_current_stage_pending_approvers_excludes_already_approved(self):
		original_lookup = _patch_person_payload_lookup()
		try:
			doc = _DummyDoc(
				{
					"tipo_padrinho_ou_orientador": "Associado",
					"padrinho_associado": "SPONSOR-1",
					"envolvidos": [
						frappe._dict(
							{
								"tipo_pessoa": "Associado",
								"associado": "SPONSOR-1",
								"aprovador": 1,
								"padrinho_orientador": 1,
								"origem_regra_aprovador": "padrinho_orientador",
								"permite_remover": 0,
							}
						),
						frappe._dict(
							{
								"tipo_pessoa": "Associado",
								"associado": "ASSOC-2",
								"aprovador": 1,
								"origem_regra_aprovador": "manual",
								"permite_remover": 1,
							}
						),
						frappe._dict(
							{
								"tipo_pessoa": "Associado",
								"associado": "DIR-1",
								"aprovador": 1,
								"origem_regra_aprovador": "diretor_presidente",
								"permite_remover": 1,
							}
						),
					],
					"comentarios_revisao_aprovacao": [
						frappe._dict(
							{
								"tipo_revisao": "Aprovacao",
								"etapa_aprovacao": projeto_module.STAGE_APROVADORES_INICIAIS,
								"aprovador": "Associado:SPONSOR-1",
								"aprovador_tipo": "Associado",
								"aprovador_associado": "SPONSOR-1",
							}
						)
					],
				}
			)

			pipeline = projeto_module._build_approval_pipeline(doc)
			current_stage, pending = projeto_module._get_current_stage_pending_approvers(doc, pipeline)

			self.assertEqual(current_stage["key"], projeto_module.STAGE_APROVADORES_INICIAIS)
			self.assertEqual({row.get("key") for row in pending}, {"Associado:ASSOC-2"})
		finally:
			projeto_module._get_person_payload_by_type = original_lookup

	def test_enviar_emails_avaliacao_dispara_whatsapp_com_mesmo_link(self):
		original_sendmail = projeto_module.frappe.sendmail
		original_get_url = projeto_module.frappe.utils.get_url
		original_whatsapp = projeto_module._send_whatsapp_notification

		enviados_email: list[dict] = []
		enviados_whatsapp: list[dict] = []

		def fake_sendmail(**kwargs):
			enviados_email.append(kwargs)

		def fake_get_url(*args, **kwargs):
			return "https://gris.local"

		def fake_send_whatsapp(numero: str, mensagem: str, *, contexto: str) -> bool:
			enviados_whatsapp.append(
				{
					"numero": numero,
					"mensagem": mensagem,
					"contexto": contexto,
				}
			)
			return True

		projeto_module.frappe.sendmail = fake_sendmail
		projeto_module.frappe.utils.get_url = fake_get_url
		projeto_module._send_whatsapp_notification = fake_send_whatsapp

		try:
			projeto_doc = frappe._dict({"name": "PROJ-0001", "nome_do_projeto": "Projeto Teste"})
			avaliacao_doc = frappe._dict(
				{
					"avaliacoes_individuais": [
						frappe._dict(
							{
								"email": "ana@example.com",
								"token": "tok-123",
								"avaliador": "Ana",
							}
						)
					]
				}
			)

			reviewers = [{"nome": "Ana", "email": "ana@example.com", "telefone": "11999990000"}]

			projeto_module._enviar_emails_avaliacao(projeto_doc, avaliacao_doc, reviewers)

			self.assertEqual(len(enviados_email), 1)
			self.assertEqual(len(enviados_whatsapp), 1)
			self.assertEqual(enviados_whatsapp[0]["numero"], "11999990000")
			self.assertIn("mesmo link enviado por e-mail", enviados_whatsapp[0]["mensagem"])
			self.assertIn("tok-123", enviados_whatsapp[0]["mensagem"])
		finally:
			projeto_module.frappe.sendmail = original_sendmail
			projeto_module.frappe.utils.get_url = original_get_url
			projeto_module._send_whatsapp_notification = original_whatsapp

	def test_reenviar_avaliacao_individual_envia_email_e_whatsapp(self):
		original_sendmail = projeto_module.frappe.sendmail
		original_get_url = projeto_module.frappe.utils.get_url
		original_whatsapp = projeto_module._send_whatsapp_notification
		original_get_reviewers = projeto_module._get_all_reviewer_data

		enviados_email: list[dict] = []
		enviados_whatsapp: list[dict] = []

		def fake_sendmail(**kwargs):
			enviados_email.append(kwargs)

		def fake_get_url(*args, **kwargs):
			return "https://gris.local"

		def fake_send_whatsapp(numero: str, mensagem: str, *, contexto: str) -> bool:
			enviados_whatsapp.append(
				{
					"numero": numero,
					"mensagem": mensagem,
					"contexto": contexto,
				}
			)
			return True

		def fake_get_reviewers(_projeto_doc):
			return [{"nome": "Ana Silva", "email": "ana@example.com", "telefone": "11999990000"}]

		projeto_module.frappe.sendmail = fake_sendmail
		projeto_module.frappe.utils.get_url = fake_get_url
		projeto_module._send_whatsapp_notification = fake_send_whatsapp
		projeto_module._get_all_reviewer_data = fake_get_reviewers

		try:
			projeto_doc = frappe._dict({"name": "PROJ-0001", "nome_do_projeto": "Projeto Teste"})
			row = frappe._dict(
				{
					"email": "ana@example.com",
					"token": "tok-abc",
					"avaliador": "Ana Silva",
				}
			)

			result = projeto_module._enviar_email_avaliacao_individual(projeto_doc, row)

			self.assertEqual(len(enviados_email), 1)
			self.assertEqual(len(enviados_whatsapp), 1)
			self.assertEqual(enviados_whatsapp[0]["numero"], "11999990000")
			self.assertIn("tok-abc", enviados_whatsapp[0]["mensagem"])
			self.assertTrue(result["email_sent"])
			self.assertTrue(result["whatsapp_sent"])
		finally:
			projeto_module.frappe.sendmail = original_sendmail
			projeto_module.frappe.utils.get_url = original_get_url
			projeto_module._send_whatsapp_notification = original_whatsapp
			projeto_module._get_all_reviewer_data = original_get_reviewers

	def test_notificacao_entrada_aprovacao_envia_somente_etapa_atual(self):
		original_get_doc = projeto_module.frappe.get_doc
		original_build_pipeline = projeto_module._build_approval_pipeline
		original_pending = projeto_module._get_current_stage_pending_approvers
		original_link = projeto_module._build_project_portal_link
		original_whatsapp = projeto_module._send_whatsapp_project_button_notification
		original_coordinator_payload = projeto_module._get_associado_payload_loose

		enviados: list[dict] = []
		doc = frappe._dict(
			{
				"name": "PROJ-0002",
				"status": projeto_module.STATUS_EM_APROVACAO,
				"nome_do_projeto": "Projeto A",
				"coordenador": "COORD-1",
			}
		)

		def fake_get_doc(doctype: str, name: str):
			if doctype == "Projeto" and name == doc.name:
				return doc
			return original_get_doc(doctype, name)

		def fake_build_pipeline(_doc):
			return [{"key": "aprovadores_iniciais", "label": "Etapa inicial", "approvers": []}]

		def fake_pending(_doc, _pipeline):
			return (
				{"key": "aprovadores_iniciais", "label": "Etapa inicial"},
				[
					{"nome": "Aprovador 1", "telefone": "11988887777"},
					{"nome": "Aprovador sem telefone", "telefone": ""},
				],
			)

		def fake_link(path: str, projeto_name: str) -> str:
			self.assertEqual(path, "/projetos/aprovacao_projeto")
			self.assertEqual(projeto_name, "PROJ-0002")
			return "https://gris.local/projetos/aprovacao_projeto?projeto=PROJ-0002"

		def fake_send_whatsapp(
			numero: str,
			*,
			titulo: str,
			descricao: str,
			link: str,
			contexto: str,
		) -> bool:
			enviados.append(
				{
					"numero": numero,
					"titulo": titulo,
					"descricao": descricao,
					"link": link,
					"contexto": contexto,
				}
			)
			return True

		def fake_coordinator_payload(_name: str):
			return {"nome": "Coord", "email": "coord@example.com", "telefone": "11900000000"}

		projeto_module.frappe.get_doc = fake_get_doc
		projeto_module._build_approval_pipeline = fake_build_pipeline
		projeto_module._get_current_stage_pending_approvers = fake_pending
		projeto_module._build_project_portal_link = fake_link
		projeto_module._send_whatsapp_project_button_notification = fake_send_whatsapp
		projeto_module._get_associado_payload_loose = fake_coordinator_payload

		try:
			projeto_module.enviar_notificacao_whatsapp_entrada_aprovacao("PROJ-0002")
			self.assertEqual(len(enviados), 1)
			self.assertEqual(enviados[0]["numero"], "11988887777")
			self.assertEqual(enviados[0]["titulo"], "*Aprovacao de Projeto*")
			self.assertIn("Oi, Aprovador!", enviados[0]["descricao"])
			self.assertIn("Um novo projeto foi enviado para aprovação", enviados[0]["descricao"])
			self.assertIn("*Projeto*: Projeto A", enviados[0]["descricao"])
			self.assertIn("*Etapa*: Etapa inicial", enviados[0]["descricao"])
			self.assertIn("PROJ-0002", enviados[0]["link"])
		finally:
			projeto_module.frappe.get_doc = original_get_doc
			projeto_module._build_approval_pipeline = original_build_pipeline
			projeto_module._get_current_stage_pending_approvers = original_pending
			projeto_module._build_project_portal_link = original_link
			projeto_module._send_whatsapp_project_button_notification = original_whatsapp
			projeto_module._get_associado_payload_loose = original_coordinator_payload

	def test_aprovar_projeto_etapa_dispara_notificacao_imediata_da_proxima_etapa(self):
		original_require_access = projeto_module._require_project_read_access
		original_get_doc = projeto_module.frappe.get_doc
		original_build_pipeline = projeto_module._build_approval_pipeline
		original_get_current_stage = projeto_module._get_current_approval_stage
		original_get_stage_user = projeto_module._get_stage_user_approver
		original_get_approved_map = projeto_module._get_approved_keys_by_stage
		original_append_review = projeto_module._append_review_row
		original_enqueue = projeto_module._enqueue_project_whatsapp_job

		enqueued: list[dict] = []

		class _ApprovalDoc:
			def __init__(self):
				self.name = "PROJ-APP-01"
				self.status = projeto_module.STATUS_EM_APROVACAO
				self._saved = False

			def has_permission(self, permission):
				return permission == "read"

			def get(self, key):
				if key == "status":
					return self.status
				return None

			def save(self, ignore_permissions=False):
				self._saved = True

		doc = _ApprovalDoc()

		current_stage = {
			"key": projeto_module.STAGE_APROVADORES_INICIAIS,
			"label": "Etapa inicial",
			"approvers": [{"key": "Associado:CAIO"}],
		}
		next_stage = {
			"key": projeto_module.STAGE_DIRETOR,
			"label": "Diretor Presidente",
			"approvers": [{"key": "Associado:IURI"}],
		}

		calls = {"current_stage": 0}

		def fake_require_access():
			return "approver@example.com"

		def fake_get_doc(doctype: str, name: str):
			if doctype == "Projeto" and name == doc.name:
				return doc
			return original_get_doc(doctype, name)

		def fake_build_pipeline(_doc):
			return [current_stage, next_stage]

		def fake_get_current_stage(_doc, _pipeline):
			calls["current_stage"] += 1
			if calls["current_stage"] == 1:
				return current_stage
			return next_stage

		def fake_get_stage_user(_user, _stage):
			return {"key": "Associado:CAIO", "tipo_pessoa": "Associado", "associado": "CAIO"}

		def fake_get_approved_map(_doc):
			return {}

		def fake_append_review(*args, **kwargs):
			return None

		def fake_enqueue(method: str, **kwargs):
			enqueued.append({"method": method, "kwargs": kwargs})

		projeto_module._require_project_read_access = fake_require_access
		projeto_module.frappe.get_doc = fake_get_doc
		projeto_module._build_approval_pipeline = fake_build_pipeline
		projeto_module._get_current_approval_stage = fake_get_current_stage
		projeto_module._get_stage_user_approver = fake_get_stage_user
		projeto_module._get_approved_keys_by_stage = fake_get_approved_map
		projeto_module._append_review_row = fake_append_review
		projeto_module._enqueue_project_whatsapp_job = fake_enqueue

		try:
			result = projeto_module.aprovar_projeto_etapa(doc.name)
			self.assertTrue(doc._saved)
			self.assertEqual(result["status"], projeto_module.STATUS_EM_APROVACAO)
			self.assertEqual(result["proximo_passo"], "Diretor Presidente")
			self.assertEqual(len(enqueued), 1)
			self.assertEqual(
				enqueued[0]["method"],
				"gris.gestao_de_projetos.doctype.projeto.projeto.enviar_notificacao_whatsapp_avanco_etapa_aprovacao",
			)
			self.assertEqual(enqueued[0]["kwargs"]["projeto_name"], doc.name)
		finally:
			projeto_module._require_project_read_access = original_require_access
			projeto_module.frappe.get_doc = original_get_doc
			projeto_module._build_approval_pipeline = original_build_pipeline
			projeto_module._get_current_approval_stage = original_get_current_stage
			projeto_module._get_stage_user_approver = original_get_stage_user
			projeto_module._get_approved_keys_by_stage = original_get_approved_map
			projeto_module._append_review_row = original_append_review
			projeto_module._enqueue_project_whatsapp_job = original_enqueue

	def test_execution_edit_context_requires_active_user_and_involvement(self):
		original_get_roles = projeto_module.frappe.get_roles
		original_is_active = projeto_module._is_user_active_in_gris
		original_is_involved = projeto_module._is_user_involved_in_project

		state = {"active": True, "involved": True}

		def fake_get_roles(_user):
			return ["Editor de projetos"]

		def fake_is_active(_user):
			return state["active"]

		def fake_is_involved(_user, _doc):
			return state["involved"]

		projeto_module.frappe.get_roles = fake_get_roles
		projeto_module._is_user_active_in_gris = fake_is_active
		projeto_module._is_user_involved_in_project = fake_is_involved

		try:
			doc = _DummyDoc({"status": projeto_module.STATUS_EM_EXECUCAO})

			self.assertTrue(
				projeto_module._can_user_edit_project_execution_context("editor@example.com", doc)
			)

			state["involved"] = False
			self.assertFalse(
				projeto_module._can_user_edit_project_execution_context("editor@example.com", doc)
			)

			state["involved"] = True
			state["active"] = False
			self.assertFalse(
				projeto_module._can_user_edit_project_execution_context("editor@example.com", doc)
			)
		finally:
			projeto_module.frappe.get_roles = original_get_roles
			projeto_module._is_user_active_in_gris = original_is_active
			projeto_module._is_user_involved_in_project = original_is_involved

	def test_require_execution_edit_access_blocks_inactive_or_not_involved(self):
		original_is_active = projeto_module._is_user_active_in_gris
		original_is_involved = projeto_module._is_user_involved_in_project

		state = {"active": False, "involved": True}

		def fake_is_active(_user):
			return state["active"]

		def fake_is_involved(_user, _doc):
			return state["involved"]

		projeto_module._is_user_active_in_gris = fake_is_active
		projeto_module._is_user_involved_in_project = fake_is_involved

		try:
			doc = _DummyDoc({})

			with self.assertRaises(frappe.PermissionError):
				projeto_module._require_project_execution_edit_access(doc, user="editor@example.com")

			state["active"] = True
			state["involved"] = False
			with self.assertRaises(frappe.PermissionError):
				projeto_module._require_project_execution_edit_access(doc, user="editor@example.com")

			state["involved"] = True
			granted_user = projeto_module._require_project_execution_edit_access(
				doc, user="editor@example.com"
			)
			self.assertEqual(granted_user, "editor@example.com")
		finally:
			projeto_module._is_user_active_in_gris = original_is_active
			projeto_module._is_user_involved_in_project = original_is_involved

	def test_get_projeto_execucao_data_computes_can_edit_from_execution_rules(self):
		original_require_read = projeto_module._require_project_read_access
		original_get_doc = projeto_module.frappe.get_doc
		original_assert_visible = projeto_module._assert_project_visible_on_execution_page
		original_get_choices = projeto_module._get_selection_options
		original_serialize_projeto = projeto_module._serialize_projeto
		original_get_responsavel_options = projeto_module._get_responsavel_options
		original_can_edit_context = projeto_module._can_user_edit_project_execution_context

		state = {"status": projeto_module.STATUS_EM_EXECUCAO, "can_edit_context": True}

		class _ExecDoc:
			def has_permission(self, permission):
				return permission == "read"

			def get(self, key):
				if key == "status":
					return state["status"]
				return None

		exec_doc = _ExecDoc()

		def fake_require_read():
			return "editor@example.com"

		def fake_get_doc(doctype: str, name: str):
			self.assertEqual(doctype, "Projeto")
			self.assertEqual(name, "PROJ-0001")
			return exec_doc

		def fake_assert_visible(_doc):
			return None

		def fake_get_choices():
			return {"associados": [], "responsaveis": []}

		def fake_serialize_projeto(_doc):
			return {"name": "PROJ-0001"}

		def fake_get_responsavel_options(_doc):
			return []

		def fake_can_edit_context(_user, _doc):
			return state["can_edit_context"]

		projeto_module._require_project_read_access = fake_require_read
		projeto_module.frappe.get_doc = fake_get_doc
		projeto_module._assert_project_visible_on_execution_page = fake_assert_visible
		projeto_module._get_selection_options = fake_get_choices
		projeto_module._serialize_projeto = fake_serialize_projeto
		projeto_module._get_responsavel_options = fake_get_responsavel_options
		projeto_module._can_user_edit_project_execution_context = fake_can_edit_context

		try:
			result = projeto_module.get_projeto_execucao_data("PROJ-0001")
			self.assertTrue(result["can_edit"])

			state["status"] = projeto_module.STATUS_CONCLUIDO
			result = projeto_module.get_projeto_execucao_data("PROJ-0001")
			self.assertFalse(result["can_edit"])

			state["status"] = projeto_module.STATUS_EM_EXECUCAO
			state["can_edit_context"] = False
			result = projeto_module.get_projeto_execucao_data("PROJ-0001")
			self.assertFalse(result["can_edit"])
		finally:
			projeto_module._require_project_read_access = original_require_read
			projeto_module.frappe.get_doc = original_get_doc
			projeto_module._assert_project_visible_on_execution_page = original_assert_visible
			projeto_module._get_selection_options = original_get_choices
			projeto_module._serialize_projeto = original_serialize_projeto
			projeto_module._get_responsavel_options = original_get_responsavel_options
			projeto_module._can_user_edit_project_execution_context = original_can_edit_context

	def test_get_avaliacao_projeto_data_respects_execution_edit_context(self):
		original_require_read = projeto_module._require_project_read_access
		original_get_doc = projeto_module.frappe.get_doc
		original_assert_visible = projeto_module._assert_project_visible_on_execution_page
		original_get_avaliacao = projeto_module._get_avaliacao_for_projeto
		original_serialize_avaliacao = projeto_module._serialize_avaliacao
		original_is_coordinator = projeto_module._is_user_coordinator
		original_can_edit_context = projeto_module._can_user_edit_project_execution_context

		state = {
			"status": projeto_module.STATUS_EM_EXECUCAO,
			"avaliacao_doc": None,
			"can_edit_context": True,
		}

		class _ExecDoc:
			def has_permission(self, permission):
				return permission == "read"

			def get(self, key):
				if key == "status":
					return state["status"]
				return None

		exec_doc = _ExecDoc()

		def fake_require_read():
			return "editor@example.com"

		def fake_get_doc(doctype: str, name: str):
			self.assertEqual(doctype, "Projeto")
			self.assertEqual(name, "PROJ-0001")
			return exec_doc

		def fake_assert_visible(_doc):
			return None

		def fake_get_avaliacao(_projeto_name: str):
			return state["avaliacao_doc"]

		def fake_serialize_avaliacao(_avaliacao_doc):
			return {"name": "AVAL-0001"}

		def fake_is_coordinator(_user, _doc):
			return True

		def fake_can_edit_context(_user, _doc):
			return state["can_edit_context"]

		projeto_module._require_project_read_access = fake_require_read
		projeto_module.frappe.get_doc = fake_get_doc
		projeto_module._assert_project_visible_on_execution_page = fake_assert_visible
		projeto_module._get_avaliacao_for_projeto = fake_get_avaliacao
		projeto_module._serialize_avaliacao = fake_serialize_avaliacao
		projeto_module._is_user_coordinator = fake_is_coordinator
		projeto_module._can_user_edit_project_execution_context = fake_can_edit_context

		try:
			result = projeto_module.get_avaliacao_projeto_data("PROJ-0001")
			self.assertTrue(result["can_start_evaluation"])
			self.assertFalse(result["can_edit_general"])

			state["avaliacao_doc"] = frappe._dict({"name": "AVAL-0001"})
			result = projeto_module.get_avaliacao_projeto_data("PROJ-0001")
			self.assertFalse(result["can_start_evaluation"])
			self.assertTrue(result["can_edit_general"])

			state["can_edit_context"] = False
			result = projeto_module.get_avaliacao_projeto_data("PROJ-0001")
			self.assertFalse(result["can_start_evaluation"])
			self.assertFalse(result["can_edit_general"])
		finally:
			projeto_module._require_project_read_access = original_require_read
			projeto_module.frappe.get_doc = original_get_doc
			projeto_module._assert_project_visible_on_execution_page = original_assert_visible
			projeto_module._get_avaliacao_for_projeto = original_get_avaliacao
			projeto_module._serialize_avaliacao = original_serialize_avaliacao
			projeto_module._is_user_coordinator = original_is_coordinator
			projeto_module._can_user_edit_project_execution_context = original_can_edit_context

	def test_validate_drive_folder_link_normalizes_and_rejects_invalid_urls(self):
		class _DriveDoc:
			def __init__(self, link: str):
				self._data = {"link_pasta_google_drive": link}
				self.link_pasta_google_drive = link

			def get(self, key: str):
				return self._data.get(key)

		valid_doc = _DriveDoc("  https://drive.google.com/drive/folders/abcdefghijklmnop  ")
		projeto_module.Projeto._validate_drive_folder_link(valid_doc)
		self.assertEqual(
			valid_doc.link_pasta_google_drive,
			"https://drive.google.com/drive/folders/abcdefghijklmnop",
		)

		invalid_doc = _DriveDoc("https://example.com/sem/google-drive")
		with self.assertRaises(frappe.ValidationError):
			projeto_module.Projeto._validate_drive_folder_link(invalid_doc)

	def test_after_insert_enqueues_google_drive_folder_creation(self):
		original_enqueue_create = projeto_module._enqueue_project_drive_folder_creation
		original_ensure_board = projeto_module._ensure_project_board
		enqueued: list[str] = []
		boards: list[str] = []

		class _InsertedDoc:
			name = "PROJ-DRV-001"

		def fake_enqueue_create(projeto_name: str):
			enqueued.append(projeto_name)

		def fake_ensure_board(doc):
			boards.append(doc.name)

		projeto_module._enqueue_project_drive_folder_creation = fake_enqueue_create
		projeto_module._ensure_project_board = fake_ensure_board
		try:
			projeto_module.Projeto.after_insert(_InsertedDoc())
			self.assertEqual(enqueued, ["PROJ-DRV-001"])
			self.assertEqual(boards, ["PROJ-DRV-001"])
		finally:
			projeto_module._enqueue_project_drive_folder_creation = original_enqueue_create
			projeto_module._ensure_project_board = original_ensure_board

	def test_concluir_projeto_execucao_enqueues_drive_cleanup_when_link_exists(self):
		original_require_editor = projeto_module._require_project_editor_access
		original_get_doc = projeto_module.frappe.get_doc
		original_require_exec_access = projeto_module._require_project_execution_edit_access
		original_assert_execution = projeto_module._assert_project_in_execution
		original_enqueue_cleanup = projeto_module._enqueue_project_drive_folder_cleanup

		enqueued: list[str] = []

		class _ExecDoc:
			def __init__(self):
				self.name = "PROJ-DRV-002"
				self.status = projeto_module.STATUS_EM_EXECUCAO
				self.flags = frappe._dict()
				self._saved = False
				self._link = "https://drive.google.com/drive/folders/abcdefghijklmnop"

			def has_permission(self, permission: str):
				return permission == "write"

			def get(self, key: str):
				if key == "status":
					return self.status
				if key == "link_pasta_google_drive":
					return self._link
				return None

			def save(self):
				self._saved = True

		doc = _ExecDoc()

		def fake_require_editor():
			return "editor@example.com"

		def fake_get_doc(doctype: str, name: str):
			self.assertEqual(doctype, "Projeto")
			self.assertEqual(name, doc.name)
			return doc

		def fake_require_exec_access(_doc, *, user: str | None = None):
			self.assertEqual(user, "editor@example.com")
			return user or "editor@example.com"

		def fake_assert_execution(_doc):
			return None

		def fake_enqueue_cleanup(projeto_name: str):
			enqueued.append(projeto_name)

		projeto_module._require_project_editor_access = fake_require_editor
		projeto_module.frappe.get_doc = fake_get_doc
		projeto_module._require_project_execution_edit_access = fake_require_exec_access
		projeto_module._assert_project_in_execution = fake_assert_execution
		projeto_module._enqueue_project_drive_folder_cleanup = fake_enqueue_cleanup

		try:
			result = projeto_module.concluir_projeto_execucao(doc.name)
			self.assertTrue(doc._saved)
			self.assertEqual(doc.status, projeto_module.STATUS_CONCLUIDO)
			self.assertEqual(result["status"], projeto_module.STATUS_CONCLUIDO)
			self.assertEqual(enqueued, [doc.name])
		finally:
			projeto_module._require_project_editor_access = original_require_editor
			projeto_module.frappe.get_doc = original_get_doc
			projeto_module._require_project_execution_edit_access = original_require_exec_access
			projeto_module._assert_project_in_execution = original_assert_execution
			projeto_module._enqueue_project_drive_folder_cleanup = original_enqueue_cleanup
