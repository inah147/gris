"""Testes da tela de detalhe da contribuição mensal (`/financeiro/contribuicao`).

O detalhe deixou de ser um diálogo na lista e virou uma página própria: o que
antes o JavaScript montava a partir do payload da lista agora sai pronto do
`get_context`. Estes testes cobrem o recorte dessa página — quem ela encontra,
o que ela recusa e os dados de gestão que só o gestor recebe.
"""

import datetime
import hashlib

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.website.serve import get_response_content

from gris.api.financeiro.contribuicoes import ROLE_GESTOR, apurar_associados
from gris.www.financeiro import contribuicao

HOJE = datetime.date(2026, 8, 22)
VALOR = 60.0
VALOR_ATRASO = 70.0

CPF_BENEFICIARIO = "99000000101"
CPF_ESCOTISTA = "99000000102"


def _nome_por_cpf(cpf: str) -> str:
	"""Associado é nomeado pelo md5 do CPF, que também é gravado hasheado."""
	return hashlib.md5(cpf.encode("utf-8")).hexdigest()


class TestApuracaoComDadosDeGestao(FrappeTestCase):
	"""`incluir_gestao` é o que a página de detalhe pede a mais da apuração."""

	def setUp(self):
		self.associado = _criar_associado(
			CPF_BENEFICIARIO,
			"Beneficiário do Detalhe",
			categoria="Beneficiário",
			email_cobranca="cobranca@exemplo.com",
			telefone_cobranca="11999990101",
		)
		frappe.db.set_single_value(
			"Configuracoes Contribuicao Mensal",
			{"valor_base": VALOR, "valor_atraso": VALOR_ATRASO, "dia_vencimento": 10},
		)

	def test_sem_gestao_nao_devolve_dados_de_cobranca(self):
		apurado = apurar_associados([self.associado], 6, HOJE)[0]
		self.assertNotIn("email_cobranca", apurado)
		self.assertNotIn("telefone_cobranca", apurado)
		self.assertNotIn("acao_cadastro", apurado)

	def test_com_gestao_devolve_contatos_e_pendencia_de_cadastro(self):
		apurado = apurar_associados([self.associado], 6, HOJE, incluir_gestao=True)[0]
		self.assertEqual(apurado["email_cobranca"], "cobranca@exemplo.com")
		# O telefone é normalizado no cadastro (ganha o DDI): o detalhe mostra o que está gravado.
		self.assertTrue(apurado["telefone_cobranca"].endswith("11999990101"))
		# Ativo no grupo e com cobrança ativa: nada a cadastrar nem a cancelar.
		self.assertIsNone(apurado["acao_cadastro"])

	def test_inativo_com_cobranca_ativa_pede_cancelamento(self):
		frappe.db.set_value("Associado", self.associado, "status_no_grupo", "Inativo")
		try:
			apurado = apurar_associados([self.associado], 6, HOJE, incluir_gestao=True)[0]
			self.assertEqual(apurado["acao_cadastro"], "Cancelar")
		finally:
			frappe.db.set_value("Associado", self.associado, "status_no_grupo", "Ativo")


class TestContextoDaPaginaDeDetalhe(FrappeTestCase):
	"""O `get_context` da página, que substitui o diálogo da lista."""

	def setUp(self):
		self.associado = _criar_associado(
			CPF_BENEFICIARIO,
			"Beneficiário do Detalhe",
			categoria="Beneficiário",
			email_cobranca="cobranca@exemplo.com",
			telefone_cobranca="11999990101",
		)
		frappe.db.set_single_value(
			"Configuracoes Contribuicao Mensal",
			{"valor_base": VALOR, "valor_atraso": VALOR_ATRASO, "dia_vencimento": 10},
		)
		_garantir_role_gestor()
		self.form_dict_original = dict(frappe.local.form_dict)

	def tearDown(self):
		frappe.local.form_dict = frappe._dict(self.form_dict_original)

	def _contexto(self, **parametros):
		frappe.local.form_dict = frappe._dict(parametros)
		return contribuicao.get_context(frappe._dict())

	def test_sem_parametro_associado_a_pagina_avisa_em_vez_de_quebrar(self):
		contexto = self._contexto(meses="6")
		self.assertTrue(contexto.not_found)
		self.assertIn("associado", contexto.missing_reason)

	def test_associado_que_nao_contribui_nao_tem_detalhe(self):
		escotista = _criar_associado(CPF_ESCOTISTA, "Escotista de Teste", categoria="Escotista")
		contexto = self._contexto(associado=escotista, meses="6")
		self.assertTrue(contexto.not_found)

	def test_contexto_traz_apuracao_transacoes_e_volta_para_a_lista(self):
		contexto = self._contexto(associado=self.associado, meses="6")

		self.assertFalse(contexto.get("not_found"))
		self.assertEqual(contexto.assoc["id"], self.associado)
		self.assertEqual(len(contexto.assoc["linhas"]), 6)
		self.assertEqual(contexto.transacoes, [])
		self.assertEqual(contexto.total_transacoes, 0)
		# O período volta com o usuário para a lista de onde ele saiu.
		self.assertEqual(contexto.voltar_url, "/financeiro/contribuicoes?meses=6")
		# A sidebar continua destacando a lista: o detalhe é um passo dentro dela.
		self.assertEqual(contexto.active_link, "/financeiro/contribuicoes")

	def test_gestor_recebe_os_dados_de_cobranca_do_contribuinte(self):
		contexto = self._contexto(associado=self.associado, meses="6")
		self.assertTrue(contexto.can_manage_contributions)
		self.assertEqual(contexto.assoc["email_cobranca"], "cobranca@exemplo.com")

	def test_periodo_invalido_cai_no_padrao(self):
		contexto = self._contexto(associado=self.associado, meses="abacaxi")
		self.assertEqual(contexto.meses_selecionado, "12")
		self.assertEqual(len(contexto.assoc["linhas"]), 12)

	def _renderizar(self, rota, **parametros):
		"""Renderiza a rota do portal. O resolvedor não lê query string: os
		parâmetros da URL entram pelo `form_dict`, como no request real."""
		frappe.local.form_dict = frappe._dict(parametros)
		return get_response_content(rota)

	def test_pagina_renderiza_o_mes_a_mes_sem_javascript(self):
		"""A tela nasce pronta: o mês a mês vem no HTML, não de uma chamada depois."""
		conteudo = self._renderizar("/financeiro/contribuicao", associado=self.associado, meses="6")

		# O cadastro normaliza o nome (capitalização), então o teste compara com o
		# que está gravado, não com o que foi digitado.
		nome = frappe.db.get_value("Associado", self.associado, "nome_completo")
		self.assertIn(nome, conteudo)
		self.assertIn("Apuração mês a mês", conteudo)
		self.assertIn("Transações do período", conteudo)
		self.assertIn("/financeiro/contribuicoes?meses=6", conteudo)

	def test_lista_leva_para_a_tela_de_detalhe_em_vez_de_abrir_um_dialogo(self):
		conteudo = self._renderizar("/financeiro/contribuicoes", meses="6")

		self.assertIn(f"/financeiro/contribuicao?associado={self.associado}", conteudo)
		self.assertNotIn("detalheModal", conteudo)


def _criar_associado(cpf: str, nome_completo: str, categoria: str, **campos) -> str:
	nome = _nome_por_cpf(cpf)
	if frappe.db.exists("Associado", nome):
		return nome
	doc = frappe.get_doc(
		{
			"doctype": "Associado",
			"cpf": cpf,
			"nome_completo": nome_completo,
			"data_de_nascimento": "2015-01-01",
			"categoria": categoria,
			"status_no_grupo": "Ativo",
			"status_cobranca": "Ativo",
			"valor_contribuicao": VALOR,
			"inicio_do_pagamento": "2026-01-01",
			**campos,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _garantir_role_gestor() -> None:
	"""A página é estrita: nem Administrator entra sem a role de contribuição."""
	if not frappe.db.exists("Role", ROLE_GESTOR):
		frappe.get_doc({"doctype": "Role", "role_name": ROLE_GESTOR}).insert(ignore_permissions=True)
	usuario = frappe.get_doc("User", frappe.session.user)
	if ROLE_GESTOR not in {linha.role for linha in usuario.roles}:
		usuario.add_roles(ROLE_GESTOR)
