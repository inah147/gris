"""Testes do formulário de registro do responsável (`/responsavel/registro`).

Cenários cobertos:
1. Segundo filho recupera o responsável logado com os dados já salvos
2. Segundo filho traz o outro responsável da família, pronto para vincular
3. Card com responsável ainda não vinculado ao jovem cria o vínculo (em vez de ser ignorado)
4. CPF de responsável já existente em card novo reaproveita o cadastro, sem duplicar
5. Busca por CPF: encontrado, inexistente, CPF inválido e sem permissão sobre o jovem
6. Cadastro de terceiro (fora da família) não é sobrescrito ao ser vinculado
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


CPF_MAE = _gerar_cpf("111444777")
CPF_PAI = _gerar_cpf("529982247")
CPF_FILHO1 = _gerar_cpf("390533447")
CPF_FILHO2 = _gerar_cpf("168995350")
CPF_TERCEIRO = _gerar_cpf("246813579")
CPF_DESCONHECIDO = _gerar_cpf("135792468")

EMAIL_MAE = "mae.teste.registro@example.com"


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


def _vincular(responsavel: str, novo_associado: str) -> str:
	existente = frappe.db.get_value(
		"Responsavel Vinculo",
		{"responsavel": responsavel, "beneficiario_novo_associado": novo_associado},
		"name",
	)
	if existente:
		return existente

	doc = frappe.get_doc(
		{
			"doctype": "Responsavel Vinculo",
			"responsavel": responsavel,
			"beneficiario_novo_associado": novo_associado,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _dados_associado(**extras) -> dict:
	dados = {
		"nome_completo": "Filho Dois",
		"cpf": CPF_FILHO2,
		"email_cobranca": "cobranca.teste@example.com",
		"telefone_cobranca": "11991234567",
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
		"email": "card@example.com",
		"celular": "11991234567",
		"telefone_secundario": "",
		"é_guardiao_legal": 1,
	}
	card.update(campos)
	return card


class TestRegistroResponsavel(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

		if not frappe.db.exists("User", EMAIL_MAE):
			user = frappe.new_doc("User")
			user.email = EMAIL_MAE
			user.first_name = "Mãe Teste"
			user.send_welcome_email = 0
			user.append("roles", {"role": "Responsavel"})
			user.insert(ignore_permissions=True)

		# Mãe: dona da conta do portal, com o cadastro completo do registro do 1º filho.
		self.mae = _criar_responsavel(
			CPF_MAE,
			"Mãe Teste",
			email=EMAIL_MAE,
			rg="111111",
			escolaridade="Ensino superior completo",
			**{"endereço": "Rua das Flores", "número": 10, "profissão": "Engenheira"},
		)
		# Pai: cadastrado como segundo responsável do 1º filho.
		self.pai = _criar_responsavel(
			CPF_PAI,
			"Pai Teste",
			email="pai.teste.registro@example.com",
			rg="222222",
			**{"endereço": "Rua das Flores", "número": 10},
		)

		self.filho1 = _criar_novo_associado(CPF_FILHO1, "Filho Um")
		self.filho2 = _criar_novo_associado(CPF_FILHO2, "Filho Dois")

		_vincular(self.mae, self.filho1)
		_vincular(self.pai, self.filho1)
		# O segundo filho nasce só com o vínculo de quem o adicionou no portal.
		_vincular(self.mae, self.filho2)

		frappe.set_user(EMAIL_MAE)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.form_dict.pop("novo_associado", None)
		# FrappeTestCase só desfaz a transação no fim da classe: sem isto, o vínculo criado
		# por um teste mudaria o cenário do teste seguinte.
		frappe.db.rollback()

	def _get_context(self, novo_associado):
		frappe.form_dict["novo_associado"] = novo_associado
		context = frappe._dict()
		with mock.patch.object(registro, "enrich_context"):
			registro.get_context(context)
		return context

	def _salvar(self, novo_associado, cards, data=None):
		with mock.patch.object(registro, "_notificar_dados_preenchidos"):
			return registro.update_novo_associado(
				novo_associado,
				json.dumps(data or _dados_associado()),
				json.dumps(cards),
			)

	def test_primeiro_card_traz_o_responsavel_logado_com_os_dados_salvos(self):
		context = self._get_context(self.filho2)

		primeiro = context.responsaveis[0]
		self.assertEqual(primeiro["doc"].name, self.mae)
		self.assertEqual(primeiro["origem"], "sessao")
		self.assertEqual(primeiro["doc"].get("endereço"), "Rua das Flores")
		self.assertEqual(primeiro["doc"].rg, "111111")

	def test_segundo_card_recupera_o_outro_responsavel_da_familia(self):
		context = self._get_context(self.filho2)

		segundo = context.responsaveis[1]
		self.assertEqual(segundo["doc"].name, self.pai)
		self.assertEqual(segundo["origem"], "familia")
		self.assertEqual(segundo["doc"].get("endereço"), "Rua das Flores")

	def test_sempre_ha_um_card_em_branco_para_o_segundo_responsavel(self):
		# Família com um único responsável: o segundo card precisa existir mesmo assim,
		# senão não há onde cadastrar (nem buscar por CPF) o outro responsável.
		frappe.set_user("Administrator")
		filho_sozinho = _criar_novo_associado(_gerar_cpf("111222333"), "Filho Único")
		_vincular(self.mae, filho_sozinho)
		frappe.db.delete("Responsavel Vinculo", {"responsavel": self.pai})
		frappe.set_user(EMAIL_MAE)

		context = self._get_context(filho_sozinho)

		self.assertEqual(len(context.responsaveis), 2)
		self.assertEqual(context.responsaveis[0]["doc"].name, self.mae)
		self.assertEqual(context.responsaveis[1]["origem"], "novo")
		self.assertEqual(context.responsaveis[1]["doc"], {})

	def test_salvar_com_um_unico_responsavel(self):
		# O segundo responsável é opcional: o formulário pode enviar um card só.
		self._salvar(self.filho2, [_card(self.mae, nome_completo="Mãe Teste", cpf=CPF_MAE)])

		vinculos = frappe.get_all(
			"Responsavel Vinculo",
			filters={"beneficiario_novo_associado": self.filho2},
			pluck="responsavel",
		)
		self.assertEqual(vinculos, [self.mae])
		self.assertEqual(frappe.db.get_value("Novo Associado", self.filho2, "status"), "Fazer Registro")

	def test_card_com_responsavel_sem_vinculo_cria_o_vinculo_e_grava_os_dados(self):
		self._salvar(
			self.filho2,
			[
				_card(self.mae, nome_completo="Mãe Teste", cpf=CPF_MAE),
				_card(self.pai, nome_completo="Pai Teste", cpf=CPF_PAI, rg="999999"),
			],
		)

		self.assertTrue(
			frappe.db.exists(
				"Responsavel Vinculo",
				{"responsavel": self.pai, "beneficiario_novo_associado": self.filho2},
			)
		)
		self.assertEqual(frappe.db.get_value("Responsavel", self.pai, "rg"), "999999")

	def test_cpf_de_responsavel_existente_em_card_novo_nao_duplica_cadastro(self):
		# Card sem id (o usuário redigitou os dados do pai): o nome do Responsavel deriva do
		# CPF, então inserir de novo estouraria DuplicateEntryError.
		self._salvar(
			self.filho2,
			[
				_card(self.mae, nome_completo="Mãe Teste", cpf=CPF_MAE),
				_card(nome_completo="Pai Teste", cpf=CPF_PAI),
			],
		)

		self.assertEqual(frappe.db.count("Responsavel", {"cpf": CPF_PAI}), 1)
		self.assertTrue(
			frappe.db.exists(
				"Responsavel Vinculo",
				{"responsavel": self.pai, "beneficiario_novo_associado": self.filho2},
			)
		)

	def test_terceiro_fora_da_familia_nao_tem_dados_sobrescritos(self):
		frappe.set_user("Administrator")
		terceiro = _criar_responsavel(CPF_TERCEIRO, "Terceiro Teste", **{"endereço": "Rua Original"})
		frappe.set_user(EMAIL_MAE)

		self._salvar(
			self.filho2,
			[
				_card(self.mae, nome_completo="Mãe Teste", cpf=CPF_MAE),
				_card(terceiro, nome_completo="Terceiro Teste", cpf=CPF_TERCEIRO, rg="333333"),
			],
		)

		doc = frappe.get_doc("Responsavel", terceiro)
		# Endereço já preenchido é preservado; campo vazio recebe o valor informado.
		self.assertEqual(doc.get("endereço"), "Rua Original")
		self.assertEqual(doc.rg, "333333")

	def test_vincular_terceiro_exige_o_cpf(self):
		frappe.set_user("Administrator")
		terceiro = _criar_responsavel(CPF_TERCEIRO, "Terceiro Teste")
		frappe.set_user(EMAIL_MAE)

		# Id de fora da família sem o CPF correspondente: não pode trazer dados de terceiros.
		with self.assertRaisesRegex(frappe.ValidationError, "Informe o CPF do responsável"):
			self._salvar(
				self.filho2,
				[
					_card(self.mae, nome_completo="Mãe Teste", cpf=CPF_MAE),
					_card(terceiro, nome_completo="Terceiro Teste", cpf=CPF_PAI),
				],
			)

	def test_busca_por_cpf_retorna_os_dados_do_responsavel(self):
		# O pai ainda não está vinculado ao segundo filho: é o caso de uso da busca.
		resultado = registro.buscar_responsavel_por_cpf(self.filho2, CPF_PAI)

		self.assertTrue(resultado["encontrado"])
		self.assertEqual(resultado["name"], self.pai)
		self.assertFalse(resultado["vazio"])
		self.assertEqual(resultado["dados"]["endereco"], "Rua das Flores")
		self.assertEqual(resultado["dados"]["nome_completo"], "Pai Teste")

	def test_busca_por_cpf_inexistente(self):
		resultado = registro.buscar_responsavel_por_cpf(self.filho2, CPF_DESCONHECIDO)

		self.assertFalse(resultado["encontrado"])
		self.assertEqual(resultado["motivo"], "nao_encontrado")

	def test_busca_por_cpf_invalido_volta_como_motivo_e_nao_excecao(self):
		# Erro do servidor no portal vira texto solto na página e prende a tela: desfecho
		# previsto tem que voltar no payload para a tela mostrar o diálogo.
		resultado = registro.buscar_responsavel_por_cpf(self.filho2, "123")

		self.assertFalse(resultado["encontrado"])
		self.assertEqual(resultado["motivo"], "cpf_invalido")

	def test_busca_por_cpf_do_proprio_jovem(self):
		resultado = registro.buscar_responsavel_por_cpf(self.filho2, CPF_FILHO2)

		self.assertFalse(resultado["encontrado"])
		self.assertEqual(resultado["motivo"], "cpf_do_jovem")

	def test_busca_de_responsavel_ja_vinculado(self):
		resultado = registro.buscar_responsavel_por_cpf(self.filho2, CPF_MAE)

		self.assertFalse(resultado["encontrado"])
		self.assertEqual(resultado["motivo"], "ja_vinculado")
		self.assertEqual(resultado["nome"], "Mãe Teste")

	def test_busca_exige_permissao_sobre_o_jovem(self):
		frappe.set_user("Administrator")
		outro_jovem = _criar_novo_associado(_gerar_cpf("987654321"), "Jovem de Outra Família")
		frappe.set_user(EMAIL_MAE)

		with self.assertRaises(frappe.PermissionError):
			registro.buscar_responsavel_por_cpf(outro_jovem, CPF_PAI)
