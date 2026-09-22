"""Finalização da recepção e a identidade por CPF que ela depende.

"Finalizar Recepção" tira o jovem do funil: migra os vínculos do responsável para o
cadastro de ``Associado``, anonimiza o que era só do processo de registro e apaga o
``Novo Associado``. O botão nunca chegava a rodar porque o cadastro era procurado por um
identificador (md5 dos dígitos do CPF) diferente do que o próprio ``Associado`` gravava
(md5 do CPF pontuado).

Cenários cobertos:
1. Associado nasce com o identificador canônico do CPF, digitado com ou sem pontuação
2. Salvar de novo não re-hasheia o CPF
3. Finalização encontra cadastro nomeado pela convenção antiga
4. Finalização apaga o jovem mesmo com log de mensagem, fila de espera, visita e observação
5. Responsável perde documento e endereço, mas mantém e-mail e acesso ao portal
6. Sem cadastro de Associado, a finalização explica o que falta e não apaga nada
7. Sem permissão de apagar o jovem, a finalização é barrada
8. A visão geral só marca `cadastro_associado` para quem já tem cadastro
9. Toda ligação Link para o funil é tratada antes da exclusão
"""

from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.responsavel_acesso import get_responsavel_do_usuario
from gris.utils.documento import formatar_cpf, id_por_cpf, ids_possiveis_por_cpf
from gris.www.recepcao import visao_geral


def _gerar_cpf(base9: str) -> str:
	"""CPF fictício com dígitos verificadores corretos, a partir de 9 dígitos."""
	digitos = [int(d) for d in base9]
	for posicao in (9, 10):
		soma = sum(d * (posicao + 1 - i) for i, d in enumerate(digitos))
		resto = 11 - (soma % 11)
		digitos.append(0 if resto >= 10 else resto)
	return "".join(str(d) for d in digitos)


# CPFs exclusivos deste módulo, para não colidir com os dos outros testes.
CPF_JOVEM = _gerar_cpf("723456785")
CPF_JOVEM_LEGADO = _gerar_cpf("823456786")
CPF_JOVEM_SEM_CADASTRO = _gerar_cpf("923456787")
CPF_MAE = _gerar_cpf("123456780")

EMAIL_MAE = "mae.finalizacao@example.com"
EMAIL_RECEPCAO = "equipe.finalizacao@example.com"
EMAIL_SEM_PAPEL = "estranho.finalizacao@example.com"


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


def _criar_novo_associado(cpf: str, nome: str, **campos) -> str:
	dados = {
		"doctype": "Novo Associado",
		"cpf": formatar_cpf(cpf),
		"nome_completo": nome,
		"data_de_nascimento": "2015-05-10",
		"status": "Acompanhamento",
		"ramo": "Lobinho",
		"tipo_de_registro": "Definitivo",
	}
	dados.update(campos)
	doc = frappe.get_doc(dados)
	doc.insert(ignore_permissions=True)
	return doc.name


def _criar_associado(cpf: str, nome: str, **campos) -> str:
	dados = {
		"doctype": "Associado",
		"cpf": formatar_cpf(cpf),
		"nome_completo": nome,
		"data_de_nascimento": "2015-05-10",
		"categoria": "Beneficiário",
		"ramo": "Lobinho",
	}
	dados.update(campos)
	doc = frappe.get_doc(dados)
	doc.insert(ignore_permissions=True)
	return doc.name


class TestFinalizacaoDaRecepcao(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

		# Os hooks do Associado enfileiram criação de usuário e sincronização com o Google
		# Workspace; o que está em teste é a identidade e a finalização, não os jobs.
		self._enqueue = mock.patch.object(frappe, "enqueue").start()
		self.addCleanup(mock.patch.stopall)

		_garantir_usuario(EMAIL_MAE, "Mãe Finalização", ("Responsavel",))
		_garantir_usuario(EMAIL_RECEPCAO, "Equipe Finalização", ("Recepcao",))
		_garantir_usuario(EMAIL_SEM_PAPEL, "Sem Papel Finalização")

		self.mae = self._criar_responsavel()
		self.jovem = _criar_novo_associado(CPF_JOVEM, "Jovem da Finalização", numero_de_registro="1234567")
		self._vincular(self.mae, self.jovem)

	def tearDown(self):
		frappe.set_user("Administrator")
		# FrappeTestCase só desfaz a transação no fim da classe: sem isto, o que um teste
		# gravou mudaria o cenário do teste seguinte.
		frappe.db.rollback()

	# ------------------------------------------------------------------ fixtures locais

	def _criar_responsavel(self) -> str:
		doc = frappe.get_doc(
			{
				"doctype": "Responsavel",
				"cpf": formatar_cpf(CPF_MAE),
				"nome_completo": "Mãe Finalização",
				"email": EMAIL_MAE,
				"celular": "11991234567",
				"rg": "12.345.678-9",
				"endereço": "Rua da Recepção",
				"o_que_gosta_de_fazer_no_dia_a_dia": "Acampar",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def _vincular(self, responsavel: str, novo_associado: str) -> str:
		doc = frappe.get_doc(
			{
				"doctype": "Responsavel Vinculo",
				"responsavel": responsavel,
				"beneficiario_novo_associado": novo_associado,
				"é_guardiao_legal": 1,
				"primeiro_responsavel": 1,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def _criar_associado_legado(self, cpf: str, nome: str) -> str:
		"""Cadastro nomeado pela convenção antiga: md5 do CPF pontuado."""
		canonico = _criar_associado(cpf, nome)
		legado = next(
			candidato for candidato in ids_possiveis_por_cpf(formatar_cpf(cpf)) if candidato != canonico
		)
		frappe.rename_doc("Associado", canonico, legado, force=True, show_alert=False)
		frappe.db.set_value("Associado", legado, "cpf", legado, update_modified=False)
		return legado

	# ------------------------------------------------------- identidade do CPF (a raiz)

	def test_associado_nasce_com_o_identificador_canonico_do_cpf(self):
		pontuado = _criar_associado(CPF_JOVEM_LEGADO, "Jovem Pontuado")

		self.assertEqual(pontuado, id_por_cpf(CPF_JOVEM_LEGADO))
		self.assertEqual(frappe.db.get_value("Associado", pontuado, "cpf"), pontuado)

	def test_cpf_sem_pontuacao_gera_o_mesmo_identificador(self):
		# CPF só com dígitos, como chega de planilha — o identificador é o mesmo do pontuado.
		doc = frappe.get_doc(
			{
				"doctype": "Associado",
				"cpf": CPF_JOVEM_LEGADO,
				"nome_completo": "Jovem Sem Pontuação",
				"data_de_nascimento": "2015-05-10",
			}
		)
		doc.insert(ignore_permissions=True)

		self.assertEqual(doc.name, id_por_cpf(CPF_JOVEM_LEGADO))
		self.assertEqual(doc.cpf, doc.name)

	def test_associado_compartilha_o_nome_com_o_jovem_do_funil(self):
		associado = _criar_associado(CPF_JOVEM, "Jovem da Finalização")

		self.assertEqual(associado, self.jovem)

	def test_salvar_de_novo_nao_re_hasheia_o_cpf(self):
		nome = _criar_associado(CPF_JOVEM_LEGADO, "Jovem Regravado")

		doc = frappe.get_doc("Associado", nome)
		doc.telefone = "11997654321"
		doc.save(ignore_permissions=True)

		self.assertEqual(doc.cpf, nome)
		self.assertEqual(frappe.db.get_value("Associado", nome, "cpf"), nome)

	# ------------------------------------------------------------------- a finalização

	def test_finaliza_encontrando_cadastro_com_o_nome_antigo(self):
		jovem = _criar_novo_associado(CPF_JOVEM_LEGADO, "Jovem Legado")
		vinculo = self._vincular(self.mae, jovem)
		legado = self._criar_associado_legado(CPF_JOVEM_LEGADO, "Jovem Legado")

		visao_geral.finalizar_processo_recepcao(jovem)

		self.assertFalse(frappe.db.exists("Novo Associado", jovem))
		self.assertEqual(
			frappe.db.get_value("Responsavel Vinculo", vinculo, "beneficiario_associado"), legado
		)
		self.assertFalse(frappe.db.get_value("Responsavel Vinculo", vinculo, "beneficiario_novo_associado"))

	def test_apaga_o_jovem_mesmo_com_mensagem_visita_e_fila_de_espera(self):
		_criar_associado(CPF_JOVEM, "Jovem da Finalização")

		frappe.get_doc(
			{
				"doctype": "Log de Mensagem",
				"novo_associado": self.jovem,
				"enviada_em": "2026-09-01 10:00:00",
				"status": "Enviada",
				"assunto": "Boas-vindas",
			}
		).insert(ignore_permissions=True)
		frappe.get_doc({"doctype": "Fila de Espera", "associado": self.jovem, "ramo": "Lobinho"}).insert(
			ignore_permissions=True
		)
		frappe.get_doc(
			{"doctype": "Agenda de Visitas", "jovem": self.jovem, "data_da_visita": "2026-08-01"}
		).insert(ignore_permissions=True)
		# Observação no card: quase todo jovem tem uma, e ela não pode travar a exclusão.
		frappe.get_doc(
			{
				"doctype": "Comment",
				"comment_type": "Comment",
				"reference_doctype": "Novo Associado",
				"reference_name": self.jovem,
				"content": "Família muito participativa.",
			}
		).insert(ignore_permissions=True)

		visao_geral.finalizar_processo_recepcao(self.jovem)

		self.assertFalse(frappe.db.exists("Novo Associado", self.jovem))
		self.assertFalse(frappe.db.exists("Log de Mensagem", {"novo_associado": self.jovem}))
		self.assertFalse(frappe.db.exists("Fila de Espera", {"associado": self.jovem}))
		self.assertFalse(frappe.db.exists("Agenda de Visitas", {"jovem": self.jovem}))
		self.assertFalse(
			frappe.db.exists("Comment", {"reference_doctype": "Novo Associado", "reference_name": self.jovem})
		)

	def test_responsavel_mantem_o_contato_e_o_acesso_ao_portal(self):
		_criar_associado(CPF_JOVEM, "Jovem da Finalização")

		visao_geral.finalizar_processo_recepcao(self.jovem)

		resp = frappe.get_doc("Responsavel", self.mae)
		self.assertEqual(resp.email, EMAIL_MAE)
		self.assertEqual(resp.celular, "11991234567")
		self.assertEqual(resp.nome_completo, "Mãe Finalização")
		self.assertEqual(resp.o_que_gosta_de_fazer_no_dia_a_dia, "Acampar")
		# O que só servia para montar o registro sai.
		self.assertFalse(resp.cpf)
		self.assertFalse(resp.rg)
		self.assertFalse(resp.get("endereço"))
		# E o portal do responsável continua reconhecendo a sessão dele.
		self.assertEqual(get_responsavel_do_usuario(EMAIL_MAE), self.mae)

	def test_sem_cadastro_de_associado_explica_o_que_falta_e_nao_apaga(self):
		jovem = _criar_novo_associado(CPF_JOVEM_SEM_CADASTRO, "Jovem Sem Cadastro")

		with self.assertRaises(frappe.ValidationError) as erro:
			visao_geral.finalizar_processo_recepcao(jovem)

		self.assertIn("Jovem Sem Cadastro", str(erro.exception))
		self.assertTrue(frappe.db.exists("Novo Associado", jovem))

	def test_sem_permissao_de_apagar_o_jovem_nao_finaliza(self):
		_criar_associado(CPF_JOVEM, "Jovem da Finalização")
		frappe.set_user(EMAIL_SEM_PAPEL)

		with self.assertRaises(frappe.PermissionError):
			visao_geral.finalizar_processo_recepcao(self.jovem)

		frappe.set_user("Administrator")
		self.assertTrue(frappe.db.exists("Novo Associado", self.jovem))
		self.assertTrue(frappe.db.get_value("Responsavel", self.mae, "cpf"))

	def test_recepcao_finaliza(self):
		_criar_associado(CPF_JOVEM, "Jovem da Finalização")
		frappe.set_user(EMAIL_RECEPCAO)

		visao_geral.finalizar_processo_recepcao(self.jovem)

		frappe.set_user("Administrator")
		self.assertFalse(frappe.db.exists("Novo Associado", self.jovem))

	# --------------------------------------------------------- o botão na visão geral

	def _card_do_jovem(self, novo_associado: str) -> dict | None:
		context = frappe._dict()
		with mock.patch.object(visao_geral, "enrich_context"):
			visao_geral.get_context(context)

		for cards in context.kanban_data.values():
			for card in cards:
				if card.name == novo_associado:
					return card
		return None

	def test_visao_geral_marca_apenas_quem_ja_tem_cadastro(self):
		sem_cadastro = _criar_novo_associado(CPF_JOVEM_SEM_CADASTRO, "Jovem Sem Cadastro")
		_criar_associado(CPF_JOVEM, "Jovem da Finalização")

		self.assertEqual(self._card_do_jovem(self.jovem).cadastro_associado, self.jovem)
		self.assertIsNone(self._card_do_jovem(sem_cadastro).cadastro_associado)

	# ----------------------------------------------------------- guarda de regressão

	def test_toda_ligacao_para_o_funil_e_tratada_antes_da_exclusao(self):
		# Tratados à parte: o vínculo é migrado para o Associado e a visita sai pelo
		# serviço de visitas.
		tratados_a_parte = {
			("Responsavel Vinculo", "beneficiario_novo_associado"),
			("Agenda de Visitas", "jovem"),
		}
		apagados = set(visao_geral.LIGACOES_APAGADAS_COM_O_FUNIL)

		ligacoes = {
			(campo.parent, campo.fieldname)
			for campo in frappe.get_all(
				"DocField",
				filters={"fieldtype": "Link", "options": "Novo Associado"},
				fields=["parent", "fieldname"],
			)
		}

		self.assertEqual(ligacoes - apagados - tratados_a_parte, set())
