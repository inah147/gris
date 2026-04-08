"""Testes para o fluxo de vínculo responsável ↔ associado durante importação.

Cenários cobertos:
1. Importação com vínculo pré-existente via Novo Associado → atualiza vínculo
2. Importação sem vínculo pré-existente → cria novo vínculo
3. Re-importação (vínculo já com beneficiario_associado) → skip
4. on_trash do Novo Associado limpa referência no vínculo
5. processar_desistencia não é afetado pelo on_trash
"""

import hashlib

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.associate.importer import _upsert_responsavel_vinculo

# CPFs fictícios para testes
CPF_JOVEM = "00000000001"
CPF_RESP = "00000000002"
CPF_JOVEM2 = "00000000003"


def _md5(value: str) -> str:
	return hashlib.md5(value.encode("utf-8")).hexdigest()


def _create_responsavel(cpf: str) -> str:
	if frappe.db.exists("Responsavel", _md5(cpf)):
		return _md5(cpf)
	doc = frappe.get_doc({"doctype": "Responsavel", "cpf": cpf, "nome_completo": f"Resp {cpf}"})
	doc.insert(ignore_permissions=True)
	return doc.name


def _create_novo_associado(cpf: str) -> str:
	if frappe.db.exists("Novo Associado", _md5(cpf)):
		return _md5(cpf)
	doc = frappe.get_doc({"doctype": "Novo Associado", "cpf": cpf, "nome_completo": f"Jovem {cpf}"})
	doc.insert(ignore_permissions=True)
	return doc.name


def _create_associado(cpf: str) -> str:
	name = _md5(cpf)
	if frappe.db.exists("Associado", name):
		return name
	doc = frappe.get_doc({
		"doctype": "Associado",
		"cpf": cpf,
		"nome_completo": f"Assoc {cpf}",
		"data_de_nascimento": "2015-01-01",
	})
	doc.insert(ignore_permissions=True)
	return doc.name


def _create_vinculo(responsavel_name: str, novo_associado_name: str = None, associado_name: str = None) -> str:
	doc = frappe.get_doc({
		"doctype": "Responsavel Vinculo",
		"responsavel": responsavel_name,
		"beneficiario_novo_associado": novo_associado_name,
		"beneficiario_associado": associado_name,
		"é_guardiao_legal": 1,
	})
	doc.insert(ignore_permissions=True)
	return doc.name


class TestResponsavelVinculoImport(FrappeTestCase):
	"""Testa o fluxo de upsert de vínculo durante importação de associados."""

	def setUp(self):
		# Limpar registros de teste antes de cada teste
		self._cleanup()

	def tearDown(self):
		self._cleanup()

	def _cleanup(self):
		"""Remove registros de teste criados."""
		for cpf in [CPF_JOVEM, CPF_RESP, CPF_JOVEM2]:
			md5 = _md5(cpf)
			# Vínculos
			for v in frappe.get_all(
				"Responsavel Vinculo",
				or_filters={
					"responsavel": md5,
					"beneficiario_novo_associado": md5,
					"beneficiario_associado": md5,
				},
				pluck="name",
			):
				frappe.delete_doc("Responsavel Vinculo", v, ignore_permissions=True, force=True)
			# Associados
			if frappe.db.exists("Associado", md5):
				frappe.delete_doc("Associado", md5, ignore_permissions=True, force=True)
			# Novo Associado
			if frappe.db.exists("Novo Associado", md5):
				frappe.delete_doc("Novo Associado", md5, ignore_permissions=True, force=True)
			# Responsavel
			if frappe.db.exists("Responsavel", md5):
				frappe.delete_doc("Responsavel", md5, ignore_permissions=True, force=True)
		frappe.db.commit()

	def test_01_import_updates_existing_novo_associado_vinculo(self):
		"""Cenário principal: vínculo existe via Novo Associado, importação deve atualizar."""
		resp_name = _create_responsavel(CPF_RESP)
		na_name = _create_novo_associado(CPF_JOVEM)
		vinculo_name = _create_vinculo(resp_name, novo_associado_name=na_name)
		frappe.db.commit()

		# Simular criação do Associado (como faria a importação)
		assoc_name = _create_associado(CPF_JOVEM)
		frappe.db.commit()

		# Chamar upsert passando cpf_raw (como faz o importer)
		action = _upsert_responsavel_vinculo(resp_name, assoc_name, CPF_JOVEM)
		frappe.db.commit()

		self.assertEqual(action, "updated")

		# Verificar que o vínculo foi atualizado (mesmo registro, não um novo)
		vinculo = frappe.get_doc("Responsavel Vinculo", vinculo_name)
		self.assertEqual(vinculo.beneficiario_associado, assoc_name)
		self.assertEqual(vinculo.beneficiario_novo_associado, na_name)
		self.assertEqual(int(vinculo.é_guardiao_legal), 1)

		# Verificar que NÃO foi criado um segundo vínculo
		count = frappe.db.count("Responsavel Vinculo", {"responsavel": resp_name})
		self.assertEqual(count, 1)

	def test_02_import_creates_vinculo_when_no_preexisting(self):
		"""Sem vínculo pré-existente: cria novo normalmente."""
		resp_name = _create_responsavel(CPF_RESP)
		assoc_name = _create_associado(CPF_JOVEM)
		frappe.db.commit()

		action = _upsert_responsavel_vinculo(resp_name, assoc_name, CPF_JOVEM)
		frappe.db.commit()

		self.assertEqual(action, "created")

		# Verificar que o vínculo foi criado
		exists = frappe.db.get_value(
			"Responsavel Vinculo",
			{"responsavel": resp_name, "beneficiario_associado": assoc_name},
			"name",
		)
		self.assertTrue(exists)

	def test_03_reimport_skips_when_vinculo_already_has_associado(self):
		"""Re-importação: vínculo já com beneficiario_associado → skip."""
		resp_name = _create_responsavel(CPF_RESP)
		assoc_name = _create_associado(CPF_JOVEM)
		frappe.db.commit()

		# Primeira importação
		action1 = _upsert_responsavel_vinculo(resp_name, assoc_name, CPF_JOVEM)
		frappe.db.commit()
		self.assertEqual(action1, "created")

		# Segunda importação (re-import)
		action2 = _upsert_responsavel_vinculo(resp_name, assoc_name, CPF_JOVEM)
		self.assertEqual(action2, "skipped")

		# Apenas 1 registro
		count = frappe.db.count(
			"Responsavel Vinculo",
			{"responsavel": resp_name, "beneficiario_associado": assoc_name},
		)
		self.assertEqual(count, 1)

	def test_04_on_trash_clears_novo_associado_reference(self):
		"""Ao excluir Novo Associado, o campo beneficiario_novo_associado fica null."""
		resp_name = _create_responsavel(CPF_RESP)
		na_name = _create_novo_associado(CPF_JOVEM)
		assoc_name = _create_associado(CPF_JOVEM)
		frappe.db.commit()

		# Criar vínculo com ambos preenchidos (estado pós-importação)
		vinculo_name = _create_vinculo(resp_name, novo_associado_name=na_name, associado_name=assoc_name)
		frappe.db.commit()

		# Excluir Novo Associado
		frappe.delete_doc("Novo Associado", na_name, ignore_permissions=True)
		frappe.db.commit()

		# Verificar que o vínculo ainda existe mas sem referência ao Novo Associado
		vinculo = frappe.get_doc("Responsavel Vinculo", vinculo_name)
		self.assertIsNone(vinculo.beneficiario_novo_associado)
		self.assertEqual(vinculo.beneficiario_associado, assoc_name)
		self.assertEqual(vinculo.responsavel, resp_name)

	def test_05_on_trash_only_cleans_not_deletes(self):
		"""on_trash do Novo Associado NÃO deleta o vínculo (pode ter Associado)."""
		resp_name = _create_responsavel(CPF_RESP)
		na_name = _create_novo_associado(CPF_JOVEM)
		vinculo_name = _create_vinculo(resp_name, novo_associado_name=na_name)
		frappe.db.commit()

		# Excluir Novo Associado
		frappe.delete_doc("Novo Associado", na_name, ignore_permissions=True)
		frappe.db.commit()

		# Vínculo deve continuar existindo
		self.assertTrue(frappe.db.exists("Responsavel Vinculo", vinculo_name))
		vinculo = frappe.get_doc("Responsavel Vinculo", vinculo_name)
		self.assertIsNone(vinculo.beneficiario_novo_associado)

	def test_06_no_integrity_error_on_name_collision(self):
		"""Garante que não ocorre IntegrityError quando nomes colidem (cenário do bug)."""
		resp_name = _create_responsavel(CPF_RESP)
		na_name = _create_novo_associado(CPF_JOVEM)

		# Vínculo via recepção: name = resp_hash + "" + na_hash
		vinculo_name = _create_vinculo(resp_name, novo_associado_name=na_name)
		frappe.db.commit()

		# Criar Associado com mesmo CPF (importação)
		assoc_name = _create_associado(CPF_JOVEM)
		frappe.db.commit()

		# Sem o fix, isto daria IntegrityError (Duplicate entry)
		# porque resp_hash + assoc_hash + "" == resp_hash + "" + na_hash
		try:
			action = _upsert_responsavel_vinculo(resp_name, assoc_name, CPF_JOVEM)
			frappe.db.commit()
		except Exception as e:
			self.fail(f"IntegrityError inesperado: {e}")

		self.assertEqual(action, "updated")

		# Apenas 1 registro
		count = frappe.db.count("Responsavel Vinculo", {"responsavel": resp_name})
		self.assertEqual(count, 1)
