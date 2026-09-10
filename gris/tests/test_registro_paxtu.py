"""Ajustes do registro para a transcrição no Paxtu.

Cobre o que o documento de ajustes pediu e que antes não existia:
1. CPF conferido no save (só a busca por CPF conferia; o save aceitava qualquer coisa)
2. E-mail conferido em todos os campos, e não só no de cobrança
3. Tipo de guarda no lugar do booleano, com "Alternada" sinalizada para a recepção
4. País de nascimento definindo se a pessoa é estrangeira
5. Cidade conferida contra a lista de municípios do IBGE
6. Telefone separado do DDI, para a ficha ser copiada em pedaços
7. Consulta de CEP que degrada sem travar o cadastro
"""

import json
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.utils import localidades
from gris.utils.contato import partes_telefone
from gris.utils.documento import id_por_cpf
from gris.www.recepcao import ficha_campos
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
CPF_JOVEM = _gerar_cpf("390533447")
CPF_INVALIDO = "11111111111"

EMAIL_MAE = "mae.paxtu@example.com"


class TestRegistroPaxtu(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

		if not frappe.db.exists("User", EMAIL_MAE):
			user = frappe.new_doc("User")
			user.email = EMAIL_MAE
			user.first_name = "Mãe Paxtu"
			user.send_welcome_email = 0
			user.append("roles", {"role": "Responsavel"})
			user.insert(ignore_permissions=True)

		self.mae = self._responsavel(CPF_MAE, "Mãe Paxtu", email=EMAIL_MAE)
		self.pai = self._responsavel(CPF_PAI, "Pai Paxtu", email="pai.paxtu@example.com")
		self.jovem = self._novo_associado(CPF_JOVEM, "Jovem Paxtu")
		self._vincular(self.mae, self.jovem)

		frappe.set_user(EMAIL_MAE)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.form_dict.pop("novo_associado", None)
		frappe.db.rollback()

	# ----------------------------------------------------------------- infraestrutura
	def _responsavel(self, cpf, nome, **campos):
		name = id_por_cpf(cpf)
		if frappe.db.exists("Responsavel", name):
			return name

		doc = frappe.get_doc({"doctype": "Responsavel", "cpf": cpf, "nome_completo": nome, **campos})
		doc.insert(ignore_permissions=True)
		return doc.name

	def _novo_associado(self, cpf, nome):
		name = id_por_cpf(cpf)
		if frappe.db.exists("Novo Associado", name):
			return name

		doc = frappe.get_doc({"doctype": "Novo Associado", "cpf": cpf, "nome_completo": nome})
		doc.insert(ignore_permissions=True)
		return doc.name

	def _vincular(self, responsavel, novo_associado):
		if frappe.db.exists(
			"Responsavel Vinculo",
			{"responsavel": responsavel, "beneficiario_novo_associado": novo_associado},
		):
			return

		doc = frappe.get_doc(
			{
				"doctype": "Responsavel Vinculo",
				"responsavel": responsavel,
				"beneficiario_novo_associado": novo_associado,
			}
		)
		doc.insert(ignore_permissions=True)

	def _dados(self, **extras):
		dados = {
			"nome_completo": "Jovem Paxtu",
			"cpf": CPF_JOVEM,
			# Sem data de nascimento de propósito: as regras do ramo Filhotes rodam antes
			# destas validações e roubariam a mensagem de erro que cada teste confere.
			"email_cobranca": "cobranca.paxtu@example.com",
			"telefone_cobranca": "11991234567",
			"tipo_guarda": "Compartilhada",
		}
		dados.update(extras)
		return dados

	def _card(self, **campos):
		card = {"name": self.mae, "nome_completo": "Mãe Paxtu", "cpf": CPF_MAE}
		card.update(campos)
		return card

	def _salvar(self, dados=None, cards=None):
		with mock.patch.object(registro, "_notificar_dados_preenchidos"):
			return registro.update_novo_associado(
				self.jovem,
				json.dumps(dados or self._dados()),
				json.dumps(cards if cards is not None else [self._card()]),
			)

	def _vinculo(self, campo, responsavel=None):
		return frappe.db.get_value(
			"Responsavel Vinculo",
			{
				"responsavel": responsavel or self.mae,
				"beneficiario_novo_associado": self.jovem,
			},
			campo,
		)

	# ----------------------------------------------------------------- CPF
	def test_cpf_do_jovem_com_digito_errado_e_recusado(self):
		with self.assertRaises(frappe.ValidationError) as erro:
			self._salvar(self._dados(cpf=CPF_INVALIDO))

		self.assertIn("CPF inválido", str(erro.exception))

	def test_cpf_do_responsavel_com_digito_errado_e_recusado(self):
		with self.assertRaises(frappe.ValidationError) as erro:
			self._salvar(cards=[self._card(name="", cpf=CPF_INVALIDO)])

		self.assertIn("CPF inválido", str(erro.exception))

	def test_cpf_valido_passa(self):
		self._salvar()
		self.assertEqual(frappe.db.get_value("Novo Associado", self.jovem, "cpf"), CPF_JOVEM)

	# ----------------------------------------------------------------- e-mail
	def test_email_do_jovem_invalido_e_recusado(self):
		"""Antes só o e-mail de cobrança era conferido."""
		with self.assertRaises(frappe.ValidationError) as erro:
			self._salvar(self._dados(email="sem-arroba"))

		self.assertIn("Email", str(erro.exception))

	def test_email_do_responsavel_invalido_e_recusado(self):
		with self.assertRaises(frappe.ValidationError):
			self._salvar(cards=[self._card(email="tambem sem arroba")])

	def test_email_escoteiros_invalido_e_recusado(self):
		with self.assertRaises(frappe.ValidationError):
			self._salvar(self._dados(email_escoteiros="nao-e-email"))

	# ----------------------------------------------------------------- guarda
	def test_tipo_de_guarda_e_gravado_no_vinculo(self):
		self._salvar(self._dados(tipo_guarda="Alternada"))
		self.assertEqual(self._vinculo("tipo_guarda"), "Alternada")

	def test_guarda_unilateral_deriva_do_tipo_e_nao_da_resposta_do_cliente(self):
		"""O cliente pode mandar o booleano antigo; quem manda é o tipo de guarda."""
		self._salvar(
			self._dados(tipo_guarda="Unilateral", guarda_unilateral=0),
			cards=[self._card(**{"é_guardiao_legal": 1})],
		)
		self.assertEqual(self._vinculo("guarda_unilateral"), 1)

	def test_guarda_nao_unilateral_marca_todos_como_guardioes(self):
		self._salvar(self._dados(tipo_guarda="Alternada"))
		self.assertEqual(self._vinculo("é_guardiao_legal"), 1)
		self.assertEqual(self._vinculo("guarda_unilateral"), 0)

	def test_guarda_unilateral_sem_guardiao_e_recusada(self):
		with self.assertRaises(frappe.ValidationError) as erro:
			self._salvar(self._dados(tipo_guarda="Unilateral"))

		self.assertIn("guardião legal", str(erro.exception))

	def test_tipo_de_guarda_desconhecido_e_recusado(self):
		with self.assertRaises(frappe.ValidationError) as erro:
			self._salvar(self._dados(tipo_guarda="Inventada"))

		self.assertIn("Tipo de guarda", str(erro.exception))

	def test_sem_tipo_de_guarda_o_save_segue_como_nao_informado(self):
		"""Cadastros antigos nunca responderam a pergunta; recusá-los travaria a edição."""
		dados = self._dados()
		dados.pop("tipo_guarda")
		self._salvar(dados)
		self.assertEqual(self._vinculo("tipo_guarda"), "-")

	# ----------------------------------------------------------------- naturalidade
	def test_pais_estrangeiro_marca_estrangeiro_e_limpa_a_uf(self):
		self._salvar(self._dados(pais_nascimento="PT - Portugal", uf_de_nascimento="SP"))
		doc = frappe.get_doc("Novo Associado", self.jovem)
		self.assertEqual(doc.estrangeiro, 1)
		self.assertFalse(doc.uf_de_nascimento)

	def test_pais_brasil_desmarca_estrangeiro(self):
		self._salvar(self._dados(pais_nascimento="BR - Brasil", estrangeiro=1))
		self.assertEqual(frappe.db.get_value("Novo Associado", self.jovem, "estrangeiro"), 0)

	# ----------------------------------------------------------------- cidade / CEP
	def test_cidade_fora_da_lista_da_uf_e_recusada(self):
		with mock.patch.object(registro, "municipio_valido", return_value=False):
			with self.assertRaises(frappe.ValidationError) as erro:
				self._salvar(self._dados(estado="SP", cidade="Cidade Que Não Existe"))

		self.assertIn("Escolha uma da lista", str(erro.exception))

	def test_sem_lista_de_municipios_a_cidade_passa_como_antes(self):
		"""Sem o JSON do IBGE embarcado não há como conferir — e travar o cadastro seria pior."""
		with mock.patch.object(localidades, "municipios_por_uf", return_value=[]):
			self.assertTrue(localidades.municipio_valido("Qualquer Coisa", "SP"))

	def test_cep_e_gravado_pontuado(self):
		self._salvar(self._dados(cep="01001000"))
		self.assertEqual(frappe.db.get_value("Novo Associado", self.jovem, "cep"), "01001-000")

	def test_cep_incompleto_e_recusado(self):
		with self.assertRaises(frappe.ValidationError) as erro:
			self._salvar(self._dados(cep="0100"))

		self.assertIn("CEP inválido", str(erro.exception))

	def test_cep_com_letras_e_recusado(self):
		"""Conferir o tamanho do texto formatado deixaria passar nove caracteres quaisquer."""
		with self.assertRaises(frappe.ValidationError) as erro:
			self._salvar(self._dados(cep="abcde-fgh"))

		self.assertIn("CEP inválido", str(erro.exception))

	def test_cep_do_responsavel_tambem_e_conferido(self):
		with self.assertRaises(frappe.ValidationError) as erro:
			self._salvar(cards=[self._card(cep="123")])

		self.assertIn("do responsável", str(erro.exception))

	def test_busca_de_cep_devolve_o_endereco(self):
		endereco = {
			"cep": "01001-000",
			"endereco": "Praça da Sé",
			"bairro": "Sé",
			"cidade": "São Paulo",
			"estado": "SP",
		}
		with mock.patch.object(registro, "consultar_cep", return_value=endereco):
			resposta = registro.buscar_cep("01001000")

		self.assertEqual(resposta["status"], "success")
		self.assertEqual(resposta["endereco"]["cidade"], "São Paulo")

	def test_busca_de_cep_indisponivel_nao_estoura(self):
		"""ViaCEP fora do ar não pode travar o cadastro: o formulário segue no preenchimento manual."""
		with mock.patch.object(registro, "consultar_cep", return_value=None):
			self.assertEqual(registro.buscar_cep("01001000")["status"], "not_found")

	def test_consulta_de_cep_com_erro_de_rede_devolve_none(self):
		import requests

		with mock.patch.object(localidades.requests, "get", side_effect=requests.Timeout):
			self.assertIsNone(localidades.consultar_cep("01001000"))

	# ----------------------------------------------------------------- campos novos
	def test_campos_novos_do_paxtu_sao_gravados(self):
		self._salvar(
			self._dados(
				apelido_ou_nome_social="Jovinho",
				denominacao="Batista",
				email_escoteiros="jovem@escoteiros.org.br",
			)
		)
		doc = frappe.get_doc("Novo Associado", self.jovem)
		self.assertEqual(doc.apelido_ou_nome_social, "Jovinho")
		self.assertEqual(doc.denominacao, "Batista")
		self.assertEqual(doc.email_escoteiros, "jovem@escoteiros.org.br")


class TestTelefoneSeparadoDoDDI(FrappeTestCase):
	"""O Paxtu não usa o +55 que o GRIS grava junto do número."""

	def test_celular_brasileiro_de_nove_digitos(self):
		partes = partes_telefone("+5511912345678")
		self.assertEqual(partes["ddi"], "+55")
		self.assertEqual(partes["ddd"], "11")
		self.assertEqual(partes["numero"], "912345678")
		self.assertEqual(partes["nacional_formatado"], "(11) 9 1234-5678")

	def test_fixo_de_oito_digitos(self):
		self.assertEqual(partes_telefone("+551133334444")["nacional_formatado"], "(11) 3333-4444")

	def test_numero_sem_codigo_de_pais_assume_brasil(self):
		self.assertEqual(partes_telefone("11912345678")["ddi"], "+55")

	def test_numero_estrangeiro_nao_e_fatiado_como_brasileiro(self):
		partes = partes_telefone("+351912345678")
		self.assertEqual(partes["ddi"], "+351")
		self.assertEqual(partes["ddd"], "")
		self.assertEqual(partes["numero"], "912345678")

	def test_vazio_e_lixo_nao_estouram(self):
		for valor in ("", None, "abc"):
			self.assertEqual(partes_telefone(valor)["numero"], "")


class TestFichaCampos(FrappeTestCase):
	"""A ficha da recepção é lida na ordem do Paxtu e copiada campo a campo."""

	def test_telefone_vira_dois_campos_ddi_e_numero(self):
		doc = frappe._dict({"celular": "+5511912345678"})
		blocos = ficha_campos.montar_blocos(
			doc, [{"titulo": "Contato", "campos": [("celular", "Celular", ficha_campos.TELEFONE)]}]
		)
		campos = blocos[0]["campos"]
		self.assertEqual([c["label"] for c in campos], ["Celular (DDI)", "Celular"])
		self.assertEqual(campos[0]["valor"], "+55")
		self.assertEqual(campos[1]["valor"], "(11) 9 1234-5678")

	def test_campo_vazio_nao_ganha_botao_de_copiar(self):
		doc = frappe._dict({"rg": ""})
		blocos = ficha_campos.montar_blocos(
			doc, [{"titulo": "Pessoais", "campos": [("rg", "RG", ficha_campos.TEXTO)]}]
		)
		campo = blocos[0]["campos"][0]
		self.assertTrue(campo["vazio"])
		self.assertEqual(campo["valor"], "-")

	def test_data_e_formatada_no_padrao_brasileiro(self):
		doc = frappe._dict({"data_de_nascimento": "2014-05-16"})
		blocos = ficha_campos.montar_blocos(
			doc,
			[{"titulo": "Pessoais", "campos": [("data_de_nascimento", "Data", ficha_campos.DATA)]}],
		)
		self.assertEqual(blocos[0]["campos"][0]["valor"], "16/05/2014")

	def test_estrangeiro_e_lido_como_sim_ou_nao(self):
		for valor, esperado in ((1, "Sim"), (0, "Não")):
			doc = frappe._dict({"estrangeiro": valor})
			blocos = ficha_campos.montar_blocos(
				doc,
				[{"titulo": "Pessoais", "campos": [("estrangeiro", "É estrangeiro?", ficha_campos.SIM_NAO)]}],
			)
			self.assertEqual(blocos[0]["campos"][0]["valor"], esperado)

	def test_ordem_dos_campos_do_associado_e_a_do_paxtu(self):
		pessoais = next(b for b in ficha_campos.BLOCOS_DO_ASSOCIADO if b["titulo"] == "Dados do Associado")
		nomes = [fieldname for fieldname, _label, _tipo in pessoais["campos"]]
		self.assertEqual(
			nomes[:8],
			[
				"apelido_ou_nome_social",
				"data_de_nascimento",
				"etnia",
				"sexo",
				"estrangeiro",
				"pais_nascimento",
				"uf_de_nascimento",
				"cidade_de_nascimento",
			],
		)

	def test_endereco_do_associado_comeca_pelo_cep(self):
		endereco = next(
			b for b in ficha_campos.BLOCOS_DO_ASSOCIADO if b["titulo"] == "Endereço e Dados de Contato"
		)
		self.assertEqual(endereco["campos"][0][0], "cep")

	def test_blocos_do_responsavel_usam_os_fieldnames_acentuados_do_schema(self):
		meta = frappe.get_meta("Responsavel")
		for bloco in ficha_campos.BLOCOS_DO_RESPONSAVEL:
			for fieldname, _label, _tipo in bloco["campos"]:
				with self.subTest(fieldname=fieldname):
					self.assertIsNotNone(meta.get_field(fieldname), f"{fieldname} não existe")


class TestPaginasRenderizadas(FrappeTestCase):
	"""Smoke test das duas telas: erro de Jinja não aparece em teste de unidade nenhum."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.responsavel = self._responsavel()
		self.jovem = self._jovem()
		self._vincular()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.form_dict.clear()
		frappe.db.rollback()

	def _responsavel(self):
		name = id_por_cpf(CPF_PAI)
		if not frappe.db.exists("Responsavel", name):
			frappe.get_doc(
				{
					"doctype": "Responsavel",
					"cpf": CPF_PAI,
					"nome_completo": "Pai Ficha",
					"email": "pai.ficha@example.com",
					"celular": "+5511912345678",
					"estado": "SP",
					"cidade": "São Paulo",
				}
			).insert(ignore_permissions=True)
		return name

	def _jovem(self):
		name = id_por_cpf(CPF_JOVEM)
		if not frappe.db.exists("Novo Associado", name):
			frappe.get_doc(
				{
					"doctype": "Novo Associado",
					"cpf": CPF_JOVEM,
					"nome_completo": "Jovem Ficha",
					"data_de_nascimento": "2014-05-16",
					"celular": "+5511987654321",
					"tipo_de_registro": "Provisório",
					"estado": "SP",
					"cidade": "São Paulo",
				}
			).insert(ignore_permissions=True)
		return name

	def _vincular(self, tipo_guarda="Compartilhada"):
		existente = frappe.db.exists(
			"Responsavel Vinculo",
			{"responsavel": self.responsavel, "beneficiario_novo_associado": self.jovem},
		)
		if existente:
			frappe.db.set_value("Responsavel Vinculo", existente, "tipo_guarda", tipo_guarda)
			return

		frappe.get_doc(
			{
				"doctype": "Responsavel Vinculo",
				"responsavel": self.responsavel,
				"beneficiario_novo_associado": self.jovem,
				"tipo_guarda": tipo_guarda,
			}
		).insert(ignore_permissions=True)

	def _ficha(self):
		from frappe.website.serve import get_response

		frappe.form_dict.clear()
		frappe.form_dict["name"] = self.jovem
		return get_response("/recepcao/ficha_registro", 200).get_data(as_text=True)

	def test_ficha_separa_o_ddi_do_numero_e_oferece_copiar(self):
		pagina = self._ficha()

		self.assertIn("Celular (DDI)", pagina)
		self.assertIn("(11) 9 8765-4321", pagina)
		# O botão copia o número já sem o +55, que é o que o Paxtu aceita.
		self.assertIn('data-copiar="(11) 9 8765-4321"', pagina)

	def test_ficha_formata_a_data_de_nascimento(self):
		"""``frappe.format_date`` só existe no namespace do Jinja, não no módulo importado."""
		self.assertIn("16/05/2014", self._ficha())

	def test_ficha_destaca_o_tipo_de_registro(self):
		pagina = self._ficha()

		self.assertIn('data-tipo="Provisório"', pagina)
		self.assertIn("PROVISÓRIO", pagina)

	def test_ficha_avisa_quando_a_guarda_e_alternada(self):
		self._vincular(tipo_guarda="Alternada")
		pagina = self._ficha()

		self.assertIn('class="ficha-guarda-alerta"', pagina)
		self.assertIn("Pais separados com guarda alternada", pagina)

	def test_ficha_nao_avisa_quando_a_guarda_nao_e_alternada(self):
		# Pelo markup, e não pelo texto: o CSS da página vai inline no HTML, comentários incluídos.
		self.assertNotIn('class="ficha-guarda-alerta"', self._ficha())

	def test_formulario_oferece_tipo_de_guarda_e_profissao_como_lista(self):
		from frappe.website.serve import get_response

		frappe.set_user("Administrator")
		frappe.form_dict.clear()
		frappe.form_dict["novo_associado"] = self.jovem
		with mock.patch.object(registro, "get_responsavel_do_usuario", return_value=self.responsavel):
			pagina = get_response("/responsavel/registro", 200).get_data(as_text=True)

		self.assertIn('data-fieldname="tipo_guarda"', pagina)
		self.assertIn("Alternada", pagina)
		# Profissão continua Data no schema, mas o formulário oferece a lista do Paxtu.
		self.assertIn("* Outras Profissões *", pagina)
		self.assertIn("BR - Brasil", pagina)
		# O checkbox de estrangeiro saiu: quem responde isso agora é o país de nascimento.
		self.assertNotIn('data-fieldname="estrangeiro"', pagina)
