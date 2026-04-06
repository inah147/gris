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
					"aprovadores": [
						frappe._dict(
							{
								"tipo_pessoa": "Associado",
								"associado": "SPONSOR-1",
								"origem_regra": "padrinho_orientador",
								"permite_remover": 0,
							}
						),
						frappe._dict(
							{
								"tipo_pessoa": "Associado",
								"associado": "ASSOC-2",
								"origem_regra": "manual",
								"permite_remover": 1,
							}
						),
						frappe._dict(
							{
								"tipo_pessoa": "Associado",
								"associado": "DIR-1",
								"origem_regra": "diretor_presidente",
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
		try:
			doc = _DummyDoc(
				{
					"tipo_padrinho_ou_orientador": "Associado",
					"padrinho_associado": "SPONSOR-1",
					"aprovadores": [
						frappe._dict(
							{
								"tipo_pessoa": "Associado",
								"associado": "ASSOC-2",
								"origem_regra": "manual",
								"permite_remover": 1,
							}
						)
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
					"aprovadores": [
						frappe._dict(
							{
								"tipo_pessoa": "Associado",
								"associado": "SPONSOR-1",
								"origem_regra": "padrinho_orientador",
								"permite_remover": 0,
							}
						),
						frappe._dict(
							{
								"tipo_pessoa": "Associado",
								"associado": "DIR-1",
								"origem_regra": "diretor_presidente",
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
					"aprovadores": [
						frappe._dict(
							{
								"tipo_pessoa": "Associado",
								"associado": "SPONSOR-1",
								"origem_regra": "padrinho_orientador",
								"permite_remover": 0,
							}
						),
						frappe._dict(
							{
								"tipo_pessoa": "Associado",
								"associado": "DIR-1",
								"origem_regra": "diretor_presidente",
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
