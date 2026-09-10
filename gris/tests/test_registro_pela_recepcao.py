"""Preenchimento de `/responsavel/registro` pela equipe de recepção.

A mesma tela do portal do responsável abre para quem tem o papel ``Recepcao``, que preenche
em nome da família — é o que atende quem não consegue usar o portal e o que permite conferir
o formulário sem depender de um jovem parado em "Aguardar Dados".

Cenários cobertos:
1. Recepção abre o formulário em nome do responsável já vinculado ao jovem
2. Jovem sem responsável nenhum abre com os dois cards em branco
3. Save pela recepção grava os dados, mantém o fluxo e registra quem preencheu
4. Save pela recepção não dispara o aviso com menção geral no grupo
5. Save do responsável do portal continua avisando o grupo, sem comentário de auditoria
6. Recepção pode atualizar por completo o cadastro do responsável vinculado
7. Quem não tem vínculo nem papel de recepção continua barrado
"""

import json
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.utils.documento import id_por_cpf
from gris.www.responsavel import registro


def _gerar_cpf(base9: str) -> str:
	"""CPF fictício com dígitos verificadores corretos, a partir de 9 dígitos."""
	digitos = [int(d) for d in base9]
	for posicao in (9, 10):
		soma = sum(d * (posicao + 1 - i) for i, d in enumerate(digitos))
		resto = 11 - (soma % 11)
		digitos.append(0 if resto >= 10 else resto)
	return "".join(str(d) for d in digitos)


# CPFs exclusivos deste módulo, para não colidir com os dos outros testes de registro.
CPF_MAE = _gerar_cpf("323456781")
CPF_JOVEM = _gerar_cpf("423456782")
CPF_JOVEM_SEM_RESPONSAVEL = _gerar_cpf("523456783")
CPF_NOVO_RESPONSAVEL = _gerar_cpf("623456784")

EMAIL_MAE = "mae.pela.recepcao@example.com"
EMAIL_RECEPCAO = "equipe.pela.recepcao@example.com"
EMAIL_SEM_PAPEL = "estranho.pela.recepcao@example.com"


def _garantir_papel(nome: str) -> None:
	if not frappe.db.exists("Role", nome):
		frappe.get_doc({"doctype": "Role", "role_name": nome, "desk_access": 0}).insert(
			ignore_permissions=True
		)


def _garantir_usuario(email: str, nome: str, papeis: tuple[str, ...] = ()) -> None:
	if frappe.db.exists("User", email):
		return

	user = frappe.new_doc("User")
	user.email = email
	user.first_name = nome
	user.send_welcome_email = 0
	for papel in papeis:
		_garantir_papel(papel)
		user.append("roles", {"role": papel})
	user.insert(ignore_permissions=True)


def _criar_responsavel(cpf: str, nome: str, **campos) -> str:
	name = id_por_cpf(cpf)
	if frappe.db.exists("Responsavel", name):
		return name

	doc = frappe.get_doc({"doctype": "Responsavel", "cpf": cpf, "nome_completo": nome, **campos})
	doc.insert(ignore_permissions=True)
	return doc.name


def _criar_novo_associado(cpf: str, nome: str) -> str:
	name = id_por_cpf(cpf)
	if frappe.db.exists("Novo Associado", name):
		return name

	doc = frappe.get_doc({"doctype": "Novo Associado", "cpf": cpf, "nome_completo": nome})
	doc.insert(ignore_permissions=True)
	return doc.name


def _vincular(responsavel: str, novo_associado: str) -> None:
	if frappe.db.exists(
		"Responsavel Vinculo",
		{"responsavel": responsavel, "beneficiario_novo_associado": novo_associado},
	):
		return

	frappe.get_doc(
		{
			"doctype": "Responsavel Vinculo",
			"responsavel": responsavel,
			"beneficiario_novo_associado": novo_associado,
		}
	).insert(ignore_permissions=True)


def _dados_associado(**extras) -> dict:
	dados = {
		"nome_completo": "Jovem da Recepção",
		"cpf": CPF_JOVEM,
		"email_cobranca": "cobranca.recepcao@example.com",
		"telefone_cobranca": "11991234567",
		"tipo_de_registro": "Provisório",
		"guarda_unilateral": 0,
	}
	dados.update(extras)
	return dados


def _card(name: str = "", **campos) -> dict:
	card = {
		"name": name,
		"nome_completo": "Responsável",
		"cpf": "",
		"rg": "12345678",
		"orgao_expedidor": "SSP",
		"sexo": "Feminino",
		"estado_civil": "Casado(a)",
		"escolaridade": "Ensino superior completo",
		"profissao": "Analista",
		"local_de_trabalho": "Empresa",
		"cep": "01001-000",
		"endereco": "Rua Nova",
		"numero": "100",
		"complemento": "",
		"bairro": "Centro",
		"cidade": "São Paulo",
		"estado": "SP",
		"email": "card.recepcao@example.com",
		"celular": "11991234567",
		"telefone_secundario": "",
		"é_guardiao_legal": 1,
	}
	card.update(campos)
	return card


class TestRegistroPelaRecepcao(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

		_garantir_usuario(EMAIL_MAE, "Mãe Recepção", ("Responsavel",))
		_garantir_usuario(EMAIL_RECEPCAO, "Equipe Recepção", ("Recepcao",))
		_garantir_usuario(EMAIL_SEM_PAPEL, "Sem Papel")

		self.mae = _criar_responsavel(CPF_MAE, "Mãe Recepção", email=EMAIL_MAE, rg="111111")
		self.jovem = _criar_novo_associado(CPF_JOVEM, "Jovem da Recepção")
		self.jovem_sem_responsavel = _criar_novo_associado(CPF_JOVEM_SEM_RESPONSAVEL, "Jovem Sem Responsável")
		_vincular(self.mae, self.jovem)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.form_dict.pop("novo_associado", None)
		# FrappeTestCase só desfaz a transação no fim da classe: sem isto, o que um teste
		# gravou mudaria o cenário do teste seguinte.
		frappe.db.rollback()

	def _get_context(self, novo_associado):
		frappe.form_dict["novo_associado"] = novo_associado
		context = frappe._dict()
		with mock.patch.object(registro, "enrich_context"):
			registro.get_context(context)
		return context

	def _salvar(self, novo_associado, cards, data=None):
		with mock.patch.object(registro, "_notificar_dados_preenchidos") as aviso:
			resultado = registro.update_novo_associado(
				novo_associado,
				json.dumps(data or _dados_associado()),
				json.dumps(cards),
			)
		return resultado, aviso

	def _comentarios(self, novo_associado):
		return frappe.get_all(
			"Comment",
			filters={
				"reference_doctype": "Novo Associado",
				"reference_name": novo_associado,
				"comment_type": "Comment",
			},
			pluck="content",
		)

	# ----------------------------------------------------------------- abertura da tela

	def test_recepcao_abre_o_formulario_em_nome_do_responsavel_vinculado(self):
		frappe.set_user(EMAIL_RECEPCAO)

		context = self._get_context(self.jovem)

		self.assertTrue(context.pela_recepcao)
		self.assertEqual(context.responsavel_representado, "Mãe Recepção")
		self.assertEqual(context.responsaveis[0]["doc"].name, self.mae)
		self.assertEqual(context.responsaveis[0]["origem"], "vinculo")
		# A sidebar e o "voltar" seguem o módulo da recepção: sem isso a página cai no
		# "Acesso negado" do contexto de /responsavel, que exige o papel Responsavel.
		self.assertEqual(context.active_link, "/recepcao")
		self.assertIn(self.jovem, context.voltar_url)

	def test_jovem_sem_responsavel_abre_com_dois_cards_em_branco(self):
		frappe.set_user(EMAIL_RECEPCAO)

		context = self._get_context(self.jovem_sem_responsavel)

		self.assertTrue(context.pela_recepcao)
		self.assertEqual(context.responsavel_representado, "")
		self.assertEqual(len(context.responsaveis), 2)
		self.assertTrue(all(item["origem"] == "novo" for item in context.responsaveis))

	def test_responsavel_do_portal_continua_no_proprio_contexto(self):
		frappe.set_user(EMAIL_MAE)

		context = self._get_context(self.jovem)

		self.assertFalse(context.pela_recepcao)
		self.assertEqual(context.responsaveis[0]["origem"], "sessao")
		self.assertEqual(context.active_link, "/responsavel/beneficiarios")

	def test_pagina_renderiza_para_a_recepcao_com_o_aviso_de_quem_representa(self):
		from frappe.website.serve import get_response

		frappe.set_user(EMAIL_RECEPCAO)
		frappe.form_dict.clear()
		frappe.form_dict["novo_associado"] = self.jovem

		pagina = get_response("/responsavel/registro", 200).get_data(as_text=True)

		self.assertIn("preenchendo em nome do responsável", pagina)
		self.assertIn("Mãe Recepção", pagina)
		# O "voltar" leva para a ficha do jovem, e não para os beneficiários do responsável.
		self.assertIn(f"/recepcao/ficha_registro?name={self.jovem}", pagina)

	def test_ficha_da_recepcao_oferece_o_formulario_do_responsavel(self):
		from frappe.website.serve import get_response

		frappe.set_user(EMAIL_RECEPCAO)
		frappe.form_dict.clear()
		frappe.form_dict["name"] = self.jovem

		pagina = get_response("/recepcao/ficha_registro", 200).get_data(as_text=True)

		self.assertIn(f"/responsavel/registro?novo_associado={self.jovem}", pagina)
		self.assertIn("Preencher registro", pagina)

	# ----------------------------------------------------------------- gravação

	def test_recepcao_salva_em_nome_do_responsavel_e_registra_quem_preencheu(self):
		frappe.set_user(EMAIL_RECEPCAO)

		_resultado, aviso = self._salvar(
			self.jovem, [_card(self.mae, nome_completo="Mãe Recepção", cpf=CPF_MAE)]
		)

		self.assertEqual(frappe.db.get_value("Novo Associado", self.jovem, "status"), "Fazer Registro")
		self.assertEqual(frappe.db.get_value("Novo Associado", self.jovem, "dados_para_registro_enviados"), 1)
		# O aviso com menção geral no grupo não é disparado quando é a própria equipe que
		# preenche; o rastro fica no comentário da ficha.
		aviso.assert_not_called()
		comentarios = self._comentarios(self.jovem)
		self.assertEqual(len(comentarios), 1)
		self.assertIn("pela recepção", comentarios[0])
		self.assertIn("Mãe Recepção", comentarios[0])

	def test_save_do_responsavel_continua_avisando_o_grupo_sem_comentario(self):
		frappe.set_user(EMAIL_MAE)

		_resultado, aviso = self._salvar(
			self.jovem, [_card(self.mae, nome_completo="Mãe Recepção", cpf=CPF_MAE)]
		)

		aviso.assert_called_once_with(self.jovem)
		self.assertEqual(self._comentarios(self.jovem), [])

	def test_recepcao_atualiza_por_completo_o_cadastro_do_responsavel_vinculado(self):
		frappe.set_user(EMAIL_RECEPCAO)

		self._salvar(
			self.jovem,
			[_card(self.mae, nome_completo="Mãe Recepção", cpf=CPF_MAE, rg="999999")],
		)

		self.assertEqual(frappe.db.get_value("Responsavel", self.mae, "rg"), "999999")

	def test_recepcao_cadastra_o_primeiro_responsavel_do_jovem(self):
		frappe.set_user(EMAIL_RECEPCAO)

		self._salvar(
			self.jovem_sem_responsavel,
			[_card(nome_completo="Pai Novo", cpf=CPF_NOVO_RESPONSAVEL)],
			data=_dados_associado(nome_completo="Jovem Sem Responsável", cpf=CPF_JOVEM_SEM_RESPONSAVEL),
		)

		novo_responsavel = id_por_cpf(CPF_NOVO_RESPONSAVEL)
		self.assertTrue(frappe.db.exists("Responsavel", novo_responsavel))
		self.assertTrue(
			frappe.db.exists(
				"Responsavel Vinculo",
				{
					"responsavel": novo_responsavel,
					"beneficiario_novo_associado": self.jovem_sem_responsavel,
				},
			)
		)

	# ----------------------------------------------------------------- permissão

	def test_usuario_sem_papel_de_recepcao_nem_vinculo_nao_abre_a_tela(self):
		frappe.set_user(EMAIL_SEM_PAPEL)

		with self.assertRaises(frappe.ValidationError):
			self._get_context(self.jovem)

	def test_responsavel_de_outra_familia_nao_salva(self):
		frappe.set_user(EMAIL_MAE)

		with self.assertRaises(frappe.PermissionError):
			registro.update_novo_associado(
				self.jovem_sem_responsavel,
				json.dumps(
					_dados_associado(nome_completo="Jovem Sem Responsável", cpf=CPF_JOVEM_SEM_RESPONSAVEL)
				),
				json.dumps([_card(self.mae, nome_completo="Mãe Recepção", cpf=CPF_MAE)]),
			)

	def test_recepcao_nao_abre_jovem_inexistente(self):
		frappe.set_user(EMAIL_RECEPCAO)

		with self.assertRaises(frappe.ValidationError):
			self._get_context("nao-existe")
