# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.festas.convite_confirmado import (
	_build_redirect_url,
	_build_token,
	_is_safe_receipt_url,
	_is_valid_convite_name,
	_mask_email,
	_validate_token,
	get_status,
)


class TestConviteConfirmadoHelpers(FrappeTestCase):
	def test_convite_name_validacao(self):
		self.assertTrue(_is_valid_convite_name("CF-2026-00001"))
		self.assertTrue(_is_valid_convite_name("CF-2030-99999"))
		self.assertFalse(_is_valid_convite_name(""))
		self.assertFalse(_is_valid_convite_name(None))
		self.assertFalse(_is_valid_convite_name("XX-2026-00001"))
		self.assertFalse(_is_valid_convite_name("CF-26-00001"))
		self.assertFalse(_is_valid_convite_name("CF-2026"))
		# Injeção de path / caracteres especiais
		self.assertFalse(_is_valid_convite_name("CF-2026-1' OR '1'='1"))
		self.assertFalse(_is_valid_convite_name("../etc/passwd"))

	def test_token_valido_e_invalido(self):
		nome = "CF-2026-00042"
		token = _build_token(nome)
		self.assertTrue(_validate_token(nome, token))
		self.assertFalse(_validate_token(nome, ""))
		self.assertFalse(_validate_token(nome, token + "x"))
		# Token de outro convite não vale para este
		outro = _build_token("CF-2026-00043")
		self.assertFalse(_validate_token(nome, outro))
		# Nome inválido sempre falha
		self.assertFalse(_validate_token("XX-1", token))

	def test_build_token_rejeita_nome_invalido(self):
		with self.assertRaises(ValueError):
			_build_token("XX-1")

	def test_redirect_url_contem_token_assinado(self):
		nome = "CF-2026-00777"
		url = _build_redirect_url(nome)
		self.assertIn("/festas/convite_confirmado?c=", url)
		self.assertIn(f"c={nome}", url)
		token_esperado = _build_token(nome)
		self.assertIn(f"t={token_esperado}", url)

	def test_receipt_url_allowlist(self):
		self.assertTrue(_is_safe_receipt_url("https://recibo.infinitepay.io/abc"))
		self.assertTrue(_is_safe_receipt_url("https://api.infinitepay.io/x/y"))
		self.assertTrue(_is_safe_receipt_url("https://checkout.infinitepay.io/c/123"))
		# Domínio externo é rejeitado
		self.assertFalse(_is_safe_receipt_url("https://evil.com/redir?to=https://recibo.infinitepay.io"))
		# Apenas HTTPS é aceito
		self.assertFalse(_is_safe_receipt_url("http://recibo.infinitepay.io/abc"))
		self.assertFalse(_is_safe_receipt_url("ftp://recibo.infinitepay.io/abc"))
		# Valores vazios / None
		self.assertFalse(_is_safe_receipt_url(""))
		self.assertFalse(_is_safe_receipt_url(None))

	def test_mask_email(self):
		self.assertEqual(_mask_email("caio@example.com"), "c***@example.com")
		self.assertEqual(_mask_email("a@b.com"), "a***@b.com")
		# Sem domínio com ponto → não vaza
		self.assertEqual(_mask_email("a@invalid"), "")
		self.assertEqual(_mask_email(""), "")
		self.assertEqual(_mask_email(None), "")


class TestGetStatusEndpoint(FrappeTestCase):
	def setUp(self):
		# Limpa side-effects entre testes
		self.original_response = dict(frappe.local.response)
		self.addCleanup(self._restore_response)

	def _restore_response(self):
		frappe.local.response.clear()
		frappe.local.response.update(self.original_response)

	def test_get_status_sem_token_retorna_404(self):
		resultado = get_status(c="CF-2026-00001", t="invalido")
		self.assertEqual(frappe.local.response.get("http_status_code"), 404)
		self.assertEqual(resultado["status"], "Indisponivel")
		self.assertIsNone(resultado["atualizado_em"])

	def test_get_status_para_nome_invalido_retorna_404(self):
		resultado = get_status(c="../../etc/passwd", t="")
		self.assertEqual(frappe.local.response.get("http_status_code"), 404)
		self.assertEqual(resultado["status"], "Indisponivel")

	def test_get_status_para_convite_inexistente_retorna_404(self):
		nome = "CF-2099-99999"
		token = _build_token(nome)
		resultado = get_status(c=nome, t=token)
		self.assertEqual(frappe.local.response.get("http_status_code"), 404)
		self.assertEqual(resultado["status"], "Indisponivel")

	def test_get_status_so_devolve_status_e_timestamp(self):
		# Mocka frappe.db.get_value para simular um convite real sem precisar de fixtures
		nome = "CF-2026-12345"
		token = _build_token(nome)

		def _fake_get_value(doctype, name, fields, as_dict=False):
			if doctype == "Convite Festa" and name == nome:
				return frappe._dict({"cobranca_infinitepay": "CI-001", "modified": None})
			if doctype == "Cobranca Infinitepay" and name == "CI-001":
				return frappe._dict({"status": "Pago", "modified": None})
			return None

		with patch("frappe.db.get_value", side_effect=_fake_get_value):
			resultado = get_status(c=nome, t=token)

		self.assertEqual(set(resultado.keys()), {"status", "atualizado_em"})
		self.assertEqual(resultado["status"], "Pago")
