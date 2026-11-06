"""Observações (Comment) de um Novo Associado: só quem escreveu edita e apaga.

Cenários cobertos:
1. O autor edita a própria observação
2. O autor apaga a própria observação e recebe o total que sobrou
3. Outra pessoa da recepção não edita nem apaga observação alheia
4. Quem perdeu o acesso ao registro não mexe mais nem na própria observação
5. Só observação de Novo Associado passa por estes endpoints
"""

from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api import recepcao
from gris.utils.documento import formatar_cpf


def _gerar_cpf(base9: str) -> str:
	"""CPF fictício com dígitos verificadores corretos, a partir de 9 dígitos."""
	digitos = [int(d) for d in base9]
	for posicao in (9, 10):
		soma = sum(d * (posicao + 1 - i) for i, d in enumerate(digitos))
		resto = 11 - (soma % 11)
		digitos.append(0 if resto >= 10 else resto)
	return "".join(str(d) for d in digitos)


CPF_JOVEM = _gerar_cpf("141421356")

EMAIL_AUTORA = "autora.observacao@example.com"
EMAIL_COLEGA = "colega.observacao@example.com"
EMAIL_EX_RECEPCAO = "ex.recepcao.observacao@example.com"


def _garantir_usuario(email: str, nome: str, papeis: tuple[str, ...] = ()) -> None:
	if frappe.db.exists("User", email):
		return
	user = frappe.new_doc("User")
	user.email = email
	user.first_name = nome
	user.send_welcome_email = 0
	for papel in papeis:
		user.append("roles", {"role": papel})
	user.insert(ignore_permissions=True)


class TestObservacoesDoNovoAssociado(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		mock.patch.object(frappe, "enqueue").start()
		self.addCleanup(mock.patch.stopall)

		_garantir_usuario(EMAIL_AUTORA, "Autora Observação", ("Recepcao",))
		_garantir_usuario(EMAIL_COLEGA, "Colega Observação", ("Recepcao",))
		_garantir_usuario(EMAIL_EX_RECEPCAO, "Ex Recepção Observação", ("Recepcao",))

		jovem = frappe.get_doc(
			{
				"doctype": "Novo Associado",
				"cpf": formatar_cpf(CPF_JOVEM),
				"nome_completo": "Jovem Observação",
				"data_de_nascimento": "2016-04-10",
				"status": "Conversa Inicial",
			}
		)
		jovem.insert(ignore_permissions=True)
		self.jovem = jovem.name

		frappe.set_user(EMAIL_AUTORA)
		self.comentario = recepcao.adicionar_comentario(self.jovem, "Primeira versão")["name"]

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_autor_edita(self):
		resultado = recepcao.editar_comentario(self.comentario, "Versão corrigida")

		self.assertEqual(resultado["content_text"], "Versão corrigida")
		self.assertEqual(frappe.db.get_value("Comment", self.comentario, "content"), "Versão corrigida")

	def test_autor_apaga_e_recebe_o_total(self):
		recepcao.adicionar_comentario(self.jovem, "Outra observação")

		resultado = recepcao.excluir_comentario(self.comentario)

		self.assertFalse(frappe.db.exists("Comment", self.comentario))
		self.assertEqual(resultado["total"], 1)

	def test_colega_nao_edita_nem_apaga(self):
		frappe.set_user(EMAIL_COLEGA)

		with self.assertRaises(frappe.PermissionError):
			recepcao.editar_comentario(self.comentario, "Mexida alheia")
		with self.assertRaises(frappe.PermissionError):
			recepcao.excluir_comentario(self.comentario)

		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Comment", self.comentario, "content"), "Primeira versão")

	def test_quem_perdeu_o_acesso_nao_mexe_na_propria_observacao(self):
		frappe.set_user(EMAIL_EX_RECEPCAO)
		comentario = recepcao.adicionar_comentario(self.jovem, "Antes de sair")["name"]

		frappe.set_user("Administrator")
		frappe.get_doc("User", EMAIL_EX_RECEPCAO).remove_roles("Recepcao")
		frappe.set_user(EMAIL_EX_RECEPCAO)

		with self.assertRaises(frappe.PermissionError):
			recepcao.excluir_comentario(comentario)

	def test_so_observacao_de_novo_associado(self):
		frappe.set_user("Administrator")
		outro = frappe.get_doc(
			{
				"doctype": "Comment",
				"comment_type": "Comment",
				"reference_doctype": "User",
				"reference_name": EMAIL_AUTORA,
				"content": "Comentário em outro lugar",
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Comment", outro.name, "owner", EMAIL_AUTORA)

		frappe.set_user(EMAIL_AUTORA)
		with self.assertRaises(frappe.PermissionError):
			recepcao.excluir_comentario(outro.name)
