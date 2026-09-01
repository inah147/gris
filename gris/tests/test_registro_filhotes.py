"""Testes do fluxo exclusivo do ramo Filhotes em `/responsavel/registro`.

No ramo Filhotes o responsável também precisa de registro — só um adulto registrado pode
acompanhar a criança nas atividades. Isso muda o formulário, o dialog de tipo de registro
e acrescenta documentos hospedados no Google Drive.

Cenários cobertos:
1. Jovem de outro ramo não recebe nenhuma regra do fluxo Filhotes (não-regressão)
2. Filhotes com um único responsável: `sera_registrado` é forçado, sem depender do cliente
3. Filhotes com dois responsáveis e nenhum marcado é recusado
4. `tipo_de_registro` enviado como "Provisório" é gravado como "Definitivo"
5. Responsável marcado sem documento de identificação é recusado
6. Responsável marcado sem cidade/UF de nascimento é recusado (a declaração não fecha)
7. Data de nascimento corrigida para a faixa de Filhotes aplica as regras no mesmo save
8. Ciências obrigatórias e gravadas com a data
9. Upload de documento sem vínculo com o jovem levanta PermissionError
10. `gerar_declaracao_idoneidade` é idempotente e monta os marcadores do modelo
"""

import json
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_months, today

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
CPF_CRIANCA = _gerar_cpf("390533447")
CPF_ADOLESCENTE = _gerar_cpf("168995350")

EMAIL_MAE = "mae.filhotes@example.com"
LINK_DOC = "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrSt/view"


def _nascimento_com_idade(anos: float) -> str:
	"""Data de nascimento que produz a idade decimal pedida hoje."""
	return add_months(today(), -round(anos * 12))


def _criar_responsavel(cpf: str, nome: str, **campos) -> str:
	name = id_por_cpf(cpf)
	if frappe.db.exists("Responsavel", name):
		return name

	doc = frappe.get_doc({"doctype": "Responsavel", "cpf": cpf, "nome_completo": nome, **campos})
	doc.insert(ignore_permissions=True)
	return doc.name


def _criar_novo_associado(cpf: str, nome: str, data_de_nascimento: str) -> str:
	name = id_por_cpf(cpf)
	if frappe.db.exists("Novo Associado", name):
		return name

	doc = frappe.get_doc(
		{
			"doctype": "Novo Associado",
			"cpf": cpf,
			"nome_completo": nome,
			"data_de_nascimento": data_de_nascimento,
		}
	)
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


def _card(name: str = "", **campos) -> dict:
	card = {
		"name": name,
		"nome_completo": "Responsável",
		"cpf": "",
		"rg": "12345678",
		"orgao_expedidor": "SSP",
		"data_de_nascimento": "1990-05-10",
		"cidade_de_nascimento": "Santo André",
		"uf_de_nascimento": "SP",
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
		"cidade": "Santo André",
		"estado": "SP",
		"email": "card@example.com",
		"celular": "11991234567",
		"telefone_secundario": "",
		"é_guardiao_legal": 1,
		"sera_registrado": 1,
		"link_documento_identificacao": LINK_DOC,
	}
	card.update(campos)
	return card


def _card_mae(mae: str, **campos) -> dict:
	"""Card da mãe logada.

	O e-mail precisa ser o da sessão: `get_responsavel_do_usuario` resolve o responsável
	por `Responsavel.email`, e salvar um e-mail diferente derrubaria o acesso dela ao
	portal no passo seguinte do próprio teste.
	"""
	return _card(mae, nome_completo="Mãe Filhotes", cpf=CPF_MAE, email=EMAIL_MAE, **campos)


class TestRegistroFilhotes(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

		# A faixa do ramo vem do Single Vagas; fixar aqui deixa o teste independente do
		# valor configurado no site.
		vagas = frappe.get_single("Vagas")
		vagas.idade_transicao_filhotes = 6.5
		vagas.idade_transicao_lobinho = 10.5
		vagas.idade_transicao_escoteiro = 14.5
		vagas.idade_transicao_senior = 17.5
		vagas.idade_transicao_pioneiro = 21.5
		vagas.save(ignore_permissions=True)

		if not frappe.db.exists("User", EMAIL_MAE):
			user = frappe.new_doc("User")
			user.email = EMAIL_MAE
			user.first_name = "Mãe Filhotes"
			user.send_welcome_email = 0
			user.append("roles", {"role": "Responsavel"})
			user.insert(ignore_permissions=True)

		self.mae = _criar_responsavel(CPF_MAE, "Mãe Filhotes", email=EMAIL_MAE, rg="111111")
		self.pai = _criar_responsavel(CPF_PAI, "Pai Filhotes", email="pai.filhotes@example.com")

		self.crianca = _criar_novo_associado(CPF_CRIANCA, "Criança Filhotes", _nascimento_com_idade(6))
		self.adolescente = _criar_novo_associado(
			CPF_ADOLESCENTE, "Jovem Escoteiro", _nascimento_com_idade(12)
		)

		_vincular(self.mae, self.crianca)
		_vincular(self.mae, self.adolescente)

		frappe.set_user(EMAIL_MAE)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.form_dict.pop("novo_associado", None)
		frappe.form_dict.pop("responsavel", None)
		frappe.form_dict.pop("responsavel_slot", None)
		# FrappeTestCase só desfaz a transação no fim da classe: sem isto, o vínculo criado
		# por um teste mudaria o cenário do seguinte.
		frappe.db.rollback()

	# ----------------------------------------------------------------------------------
	# Helpers
	# ----------------------------------------------------------------------------------

	def _get_context(self, novo_associado):
		frappe.form_dict["novo_associado"] = novo_associado
		context = frappe._dict()
		with mock.patch.object(registro, "enrich_context"):
			registro.get_context(context)
		return context

	def _dados(self, nascimento, **extras) -> dict:
		dados = {
			"nome_completo": "Criança Filhotes",
			"cpf": CPF_CRIANCA,
			"data_de_nascimento": nascimento,
			"email_cobranca": "cobranca.filhotes@example.com",
			"telefone_cobranca": "11991234567",
			"guarda_unilateral": 0,
			"tipo_de_registro": "Definitivo",
			"ciente_registro_responsavel_filhotes": 1,
			"ciente_acompanhamento_filhotes": 1,
		}
		dados.update(extras)
		return dados

	def _salvar(self, novo_associado, cards, data):
		with mock.patch.object(registro, "_notificar_dados_preenchidos"):
			return registro.update_novo_associado(novo_associado, json.dumps(data), json.dumps(cards))

	def _vinculo(self, responsavel, novo_associado, campo):
		return frappe.db.get_value(
			"Responsavel Vinculo",
			{"responsavel": responsavel, "beneficiario_novo_associado": novo_associado},
			campo,
		)

	# ----------------------------------------------------------------------------------
	# Não-regressão fora do ramo Filhotes
	# ----------------------------------------------------------------------------------

	def test_jovem_de_outro_ramo_nao_recebe_as_regras_de_filhotes(self):
		context = self._get_context(self.adolescente)
		self.assertFalse(context.is_filhotes)

		dados = {
			"nome_completo": "Jovem Escoteiro",
			"cpf": CPF_ADOLESCENTE,
			"data_de_nascimento": _nascimento_com_idade(12),
			"email_cobranca": "cobranca.filhotes@example.com",
			"telefone_cobranca": "11991234567",
			"guarda_unilateral": 0,
			"tipo_de_registro": "Provisório",
		}
		# Sem ciências, sem documento e sem `sera_registrado`: nada disso é exigido fora
		# do ramo Filhotes.
		card = _card_mae(self.mae, sera_registrado=0, link_documento_identificacao="")
		resultado = self._salvar(self.adolescente, [card], dados)

		self.assertEqual(resultado["status"], "success")
		self.assertEqual(resultado["is_filhotes"], 0)
		self.assertEqual(
			frappe.db.get_value("Novo Associado", self.adolescente, "tipo_de_registro"), "Provisório"
		)

	def test_registro_de_irmao_mais_velho_nao_apaga_dados_do_responsavel(self):
		"""O card de um jovem fora do ramo Filhotes não envia campos que não renderiza."""
		frappe.db.set_value("Responsavel", self.mae, "cidade_de_nascimento", "Santo André")

		dados = {
			"nome_completo": "Jovem Escoteiro",
			"cpf": CPF_ADOLESCENTE,
			"data_de_nascimento": _nascimento_com_idade(12),
			"email_cobranca": "cobranca.filhotes@example.com",
			"telefone_cobranca": "11991234567",
			"guarda_unilateral": 0,
		}
		card = _card_mae(self.mae)
		card.pop("cidade_de_nascimento")
		card.pop("uf_de_nascimento")
		self._salvar(self.adolescente, [card], dados)

		self.assertEqual(frappe.db.get_value("Responsavel", self.mae, "cidade_de_nascimento"), "Santo André")

	# ----------------------------------------------------------------------------------
	# Regras do ramo Filhotes
	# ----------------------------------------------------------------------------------

	def test_uf_de_nascimento_nasce_vazia_e_nao_com_a_primeira_opcao(self):
		"""Select sem linha em branco no topo faz o Frappe gravar a primeira opção sozinho.

		Aqui isso significaria todo responsável nascer com "AC" sem ninguém digitar — e esse
		valor iria impresso na declaração de idoneidade, que é documento assinado.
		"""
		novo = _criar_responsavel(_gerar_cpf("246813579"), "Sem Naturalidade")
		self.assertEqual(frappe.db.get_value("Responsavel", novo, "uf_de_nascimento") or "", "")

	def test_contexto_marca_filhotes_e_expoe_a_idade_de_transicao(self):
		context = self._get_context(self.crianca)

		self.assertTrue(context.is_filhotes)
		self.assertEqual(context.idade_transicao_filhotes, 6.5)

	def test_responsavel_unico_e_registrado_mesmo_sem_marcacao_do_cliente(self):
		card = _card_mae(self.mae, sera_registrado=0)
		self._salvar(self.crianca, [card], self._dados(_nascimento_com_idade(6)))

		self.assertEqual(self._vinculo(self.mae, self.crianca, "sera_registrado"), 1)

	def test_dois_responsaveis_sem_nenhum_marcado_e_recusado(self):
		cards = [
			_card_mae(self.mae, sera_registrado=0),
			_card(
				self.pai,
				nome_completo="Pai Filhotes",
				cpf=CPF_PAI,
				email="pai.filhotes@example.com",
				sera_registrado=0,
			),
		]
		with self.assertRaises(frappe.ValidationError):
			self._salvar(self.crianca, cards, self._dados(_nascimento_com_idade(6)))

	def test_tipo_provisorio_e_gravado_como_definitivo(self):
		card = _card_mae(self.mae)
		dados = self._dados(_nascimento_com_idade(6), tipo_de_registro="Provisório")
		self._salvar(self.crianca, [card], dados)

		self.assertEqual(
			frappe.db.get_value("Novo Associado", self.crianca, "tipo_de_registro"), "Definitivo"
		)

	def test_responsavel_marcado_sem_documento_e_recusado(self):
		card = _card_mae(self.mae, link_documento_identificacao="")
		with self.assertRaises(frappe.ValidationError):
			self._salvar(self.crianca, [card], self._dados(_nascimento_com_idade(6)))

	def test_responsavel_marcado_sem_cidade_de_nascimento_e_recusado(self):
		card = _card_mae(self.mae, cidade_de_nascimento="")
		with self.assertRaises(frappe.ValidationError):
			self._salvar(self.crianca, [card], self._dados(_nascimento_com_idade(6)))

	def test_naturalidade_e_exigida_tambem_de_quem_nao_sera_registrado(self):
		"""O segundo responsável pode virar o registrado depois; a declaração precisa do dado."""
		cards = [
			_card_mae(self.mae),
			_card(
				self.pai,
				nome_completo="Pai Filhotes",
				cpf=CPF_PAI,
				email="pai.filhotes@example.com",
				sera_registrado=0,
				uf_de_nascimento="",
			),
		]
		with self.assertRaises(frappe.ValidationError):
			self._salvar(self.crianca, cards, self._dados(_nascimento_com_idade(6)))

	def test_ciencias_sao_obrigatorias_e_ficam_gravadas(self):
		card = _card_mae(self.mae)

		with self.assertRaises(frappe.ValidationError):
			self._salvar(
				self.crianca,
				[card],
				self._dados(_nascimento_com_idade(6), ciente_acompanhamento_filhotes=0),
			)

		# Sem rollback aqui: a checagem das ciências acontece antes de qualquer gravação,
		# então não há estado parcial a desfazer — e o rollback levaria junto o cenário
		# montado no setUp, derrubando o acesso da mãe ao portal.
		self._salvar(self.crianca, [card], self._dados(_nascimento_com_idade(6)))

		doc = frappe.get_doc("Novo Associado", self.crianca)
		self.assertEqual(doc.ciente_registro_responsavel_filhotes, 1)
		self.assertEqual(doc.ciente_acompanhamento_filhotes, 1)
		self.assertTrue(doc.data_ciencia_filhotes)

	def test_data_corrigida_para_filhotes_aplica_as_regras_no_mesmo_save(self):
		"""O ramo vem da data enviada agora, não do campo `ramo` gravado no cadastro."""
		frappe.db.set_value("Novo Associado", self.crianca, "ramo", "Lobinho")

		card = _card_mae(self.mae, sera_registrado=0)
		resultado = self._salvar(self.crianca, [card], self._dados(_nascimento_com_idade(6)))

		self.assertEqual(resultado["is_filhotes"], 1)
		self.assertEqual(frappe.db.get_value("Novo Associado", self.crianca, "ramo"), "Filhotes")
		self.assertEqual(self._vinculo(self.mae, self.crianca, "sera_registrado"), 1)

	def test_save_devolve_os_responsaveis_para_registro(self):
		card = _card_mae(self.mae)
		resultado = self._salvar(self.crianca, [card], self._dados(_nascimento_com_idade(6)))

		nomes = [item["name"] for item in resultado["responsaveis_para_registro"]]
		self.assertEqual(nomes, [self.mae])

	def test_link_do_documento_fica_no_responsavel_com_a_data_de_envio(self):
		card = _card_mae(self.mae)
		self._salvar(self.crianca, [card], self._dados(_nascimento_com_idade(6)))

		doc = frappe.get_doc("Responsavel", self.mae)
		self.assertEqual(doc.link_documento_identificacao, LINK_DOC)
		self.assertTrue(doc.documento_identificacao_enviado_em)

	# ----------------------------------------------------------------------------------
	# Banner / dialog de retorno
	# ----------------------------------------------------------------------------------

	def test_declaracao_pendente_aparece_depois_do_save_e_some_com_o_envio(self):
		card = _card_mae(self.mae)
		self._salvar(self.crianca, [card], self._dados(_nascimento_com_idade(6)))

		context = self._get_context(self.crianca)
		self.assertTrue(context.declaracao_pendente)
		self.assertEqual([item["name"] for item in context.responsaveis_pendentes_declaracao], [self.mae])

		frappe.db.set_value(
			"Responsavel",
			self.mae,
			"link_declaracao_idoneidade_assinada",
			"https://drive.google.com/file/d/assinada/view",
		)
		context = self._get_context(self.crianca)
		self.assertFalse(context.declaracao_pendente)

	# ----------------------------------------------------------------------------------
	# Uploads
	# ----------------------------------------------------------------------------------

	def test_extra_params_do_upload_chegam_ao_html_como_json_parseavel(self):
		"""O `novo_associado` viaja para o servidor por este atributo.

		`tojson` devolve Markup com aspas duplas: sem `forceescape` o atributo termina no
		primeiro par de aspas, o JSON chega truncado ao navegador e o upload falha com
		"Novo Associado não especificado" — sem nenhum sinal no HTML de que algo quebrou.
		"""
		import html as htmllib
		import re

		from frappe.website.serve import get_response

		frappe.form_dict.clear()
		frappe.form_dict["novo_associado"] = self.crianca
		pagina = get_response("/responsavel/registro", 200).get_data(as_text=True)

		atributos = re.findall(r'data-extra-params="([^"]*)"', pagina)
		self.assertTrue(atributos, "nenhum data-extra-params renderizado")

		for bruto in atributos:
			payload = json.loads(htmllib.unescape(bruto))
			self.assertEqual(payload["novo_associado"], self.crianca)
			self.assertIn("responsavel_slot", payload)

	def test_nome_do_arquivo_usa_o_nome_do_responsavel(self):
		from gris.api.google_workspace import recepcao_drive

		frappe.form_dict.update(
			{
				"novo_associado": self.crianca,
				"responsavel_slot": "1",
				"responsavel_nome": "Maria da Silva Souza",
			}
		)
		frappe.local.uploaded_file = b"%PDF-1.4\n"
		frappe.local.uploaded_filename = "rg.pdf"

		with mock.patch.object(recepcao_drive, "upload_bytes_to_folder", return_value=LINK_DOC) as up:
			registro.upload_documento_identificacao()

		self.assertEqual(
			up.call_args.kwargs["filename"], "Documento de identidade - Maria da Silva Souza.pdf"
		)

	def test_nome_do_arquivo_sem_nome_no_card_cai_no_jovem_e_na_posicao(self):
		from gris.api.google_workspace import recepcao_drive

		frappe.form_dict.update({"novo_associado": self.crianca, "responsavel_slot": "2"})
		frappe.local.uploaded_file = b"%PDF-1.4\n"
		frappe.local.uploaded_filename = "rg.pdf"

		with mock.patch.object(recepcao_drive, "upload_bytes_to_folder", return_value=LINK_DOC) as up:
			registro.upload_documento_identificacao()

		self.assertIn("responsavel 2", up.call_args.kwargs["filename"])
		self.assertIn("Criança Filhotes", up.call_args.kwargs["filename"])

	def test_upload_de_documento_sem_vinculo_com_o_jovem_e_bloqueado(self):
		frappe.form_dict["novo_associado"] = _criar_novo_associado(
			_gerar_cpf("246813579"), "Jovem de Outra Família", _nascimento_com_idade(6)
		)
		frappe.local.uploaded_file = b"conteudo"
		frappe.local.uploaded_filename = "rg.pdf"

		with self.assertRaises(frappe.PermissionError):
			registro.upload_documento_identificacao()

	def test_upload_de_declaracao_para_responsavel_nao_marcado_e_recusado(self):
		card = _card_mae(self.mae)
		self._salvar(self.crianca, [card], self._dados(_nascimento_com_idade(6)))

		_vincular(self.pai, self.crianca)
		frappe.form_dict["novo_associado"] = self.crianca
		frappe.form_dict["responsavel"] = self.pai
		frappe.local.uploaded_file = b"conteudo"
		frappe.local.uploaded_filename = "declaracao.pdf"

		with self.assertRaises(frappe.ValidationError):
			registro.upload_declaracao_assinada()


class TestDeclaracaoIdoneidade(FrappeTestCase):
	"""Geração do PDF da declaração, com o Google Drive/Docs mockado."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.responsavel = _criar_responsavel(
			CPF_MAE,
			"Mãe Filhotes",
			rg="111111",
			data_de_nascimento="1990-05-10",
			cidade_de_nascimento="Santo André",
			uf_de_nascimento="SP",
		)

		config = frappe.get_single("Configuracoes de Recepcao")
		config.habilitar_documentos_drive = 0
		config.pasta_declaracoes_nao_assinadas_id = "pasta-nao-assinadas"
		config.drive_compartilhado_acesso_restrito = ""
		config.link_template_declaracao_idoneidade = (
			"https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789/edit"
		)
		config.flags.ignore_validate = True
		config.save(ignore_permissions=True)

	def tearDown(self):
		frappe.db.rollback()

	def test_gera_uma_vez_e_reaproveita_o_link_na_segunda_chamada(self):
		from gris.api.google_workspace import recepcao_drive

		frappe.db.set_value(
			"Responsavel",
			self.responsavel,
			"link_declaracao_idoneidade",
			"https://drive.google.com/file/d/ja-existe/view",
		)

		with mock.patch.object(recepcao_drive, "_get_google_drive_service") as drive:
			link = recepcao_drive.gerar_declaracao_idoneidade(self.responsavel)

		self.assertEqual(link, "https://drive.google.com/file/d/ja-existe/view")
		drive.assert_not_called()

	def test_marcadores_do_modelo_recebem_os_dados_do_responsavel(self):
		from gris.api.google_workspace import recepcao_drive

		resp_doc = frappe.get_doc("Responsavel", self.responsavel)
		marcadores = recepcao_drive._marcadores_da_declaracao(resp_doc)

		self.assertEqual(marcadores["<<Nome do Associado>>"], "Mãe Filhotes")
		self.assertEqual(marcadores["<<Data de nascimento do Associado>>"], "10/05/1990")
		self.assertEqual(marcadores["<<Cidade de Nascimento do Associado>>"], "Santo André")
		self.assertEqual(marcadores["<<UF de nascimento do Associado>>"], "SP")
		self.assertEqual(marcadores["<<CPF do Associado>>"], recepcao_drive.formatar_cpf(CPF_MAE))
		self.assertEqual(marcadores["<<RG do Associado>>"], "111111")
		self.assertIn(" de ", marcadores["<<Data de Início>>"])

	def test_modelo_da_declaracao_vem_de_configuracoes_de_recepcao(self):
		from gris.api.google_workspace import recepcao_drive

		settings = frappe.get_single("Configuracoes de Recepcao")
		self.assertEqual(
			recepcao_drive._template_declaracao_id(settings), "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
		)

	def test_modelo_da_declaracao_nao_configurado_falha_com_mensagem_de_configuracao(self):
		from gris.api.google_workspace import recepcao_drive

		settings = frappe.get_single("Configuracoes de Recepcao")
		settings.link_template_declaracao_idoneidade = ""

		with self.assertRaises(frappe.ValidationError):
			recepcao_drive._template_declaracao_id(settings)

	def test_responsavel_sem_dados_da_declaracao_e_recusado(self):
		from gris.api.google_workspace import recepcao_drive

		frappe.db.set_value("Responsavel", self.responsavel, "cidade_de_nascimento", "")
		resp_doc = frappe.get_doc("Responsavel", self.responsavel)

		with self.assertRaises(frappe.ValidationError):
			recepcao_drive._assert_dados_para_declaracao(resp_doc)

	def test_extract_google_doc_id_aceita_so_url_do_docs(self):
		from gris.api.google_workspace import recepcao_drive

		self.assertEqual(
			recepcao_drive.extract_google_doc_id(
				"https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrSt/edit?usp=sharing"
			),
			"1AbCdEfGhIjKlMnOpQrSt",
		)
		self.assertEqual(
			recepcao_drive.extract_google_doc_id(
				"https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrSt"
			),
			"",
		)
		self.assertEqual(recepcao_drive.extract_google_doc_id(""), "")
		self.assertEqual(
			recepcao_drive.extract_google_doc_id("http://docs.google.com/document/d/abc/edit"), ""
		)


class TestErrosDoGoogle(FrappeTestCase):
	"""Tratamento das falhas da API do Google nas rotinas de Drive/Docs."""

	def _http_error(self, status, reason=None):
		import json as _json

		from googleapiclient.errors import HttpError

		corpo = {"error": {"code": status, "message": "erro", "details": []}}
		if reason:
			corpo["error"]["details"] = [
				{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": reason}
			]
		resp = frappe._dict(status=status, reason="erro")
		return HttpError(resp, _json.dumps(corpo).encode("utf-8"), uri="https://exemplo")

	def test_403_de_api_desabilitada_nao_e_repetido(self):
		"""SERVICE_DISABLED é definitivo: repetir só faz o usuário esperar o backoff inteiro."""
		from gris.api.google_workspace import access_manager

		tentativas = []

		def operacao():
			tentativas.append(1)
			raise self._http_error(403, "SERVICE_DISABLED")

		with mock.patch.object(access_manager.time, "sleep") as dormir:
			with self.assertRaises(Exception):
				access_manager._execute_with_retry(operacao)

		self.assertEqual(len(tentativas), 1)
		dormir.assert_not_called()

	def test_403_de_limite_de_taxa_continua_sendo_repetido(self):
		from gris.api.google_workspace import access_manager

		tentativas = []

		def operacao():
			tentativas.append(1)
			raise self._http_error(403, "userRateLimitExceeded")

		with mock.patch.object(access_manager.time, "sleep"):
			with self.assertRaises(Exception):
				access_manager._execute_with_retry(operacao)

		self.assertEqual(len(tentativas), access_manager.MAX_RETRIES)

	def test_mensagem_aponta_a_api_desabilitada(self):
		from gris.api.google_workspace import recepcao_drive

		msg = recepcao_drive._mensagem_de_erro_do_google(self._http_error(403, "SERVICE_DISABLED"))
		self.assertIn("Google Docs API", msg)

	def test_mensagem_de_404_aponta_o_modelo(self):
		from gris.api.google_workspace import recepcao_drive

		msg = recepcao_drive._mensagem_de_erro_do_google(self._http_error(404))
		self.assertIn("Modelo da declaração", msg)

	def test_mensagem_de_403_sem_motivo_aponta_compartilhamento(self):
		from gris.api.google_workspace import recepcao_drive

		msg = recepcao_drive._mensagem_de_erro_do_google(self._http_error(403))
		self.assertIn("service account", msg)


class TestDownloadDeDocumentos(FrappeTestCase):
	"""Os arquivos são servidos pelo GRIS, não pelo link do Drive.

	O drive é de acesso restrito de propósito: o responsável é usuário de portal e não é
	membro dele, então abrir o link do Google sempre daria "sem acesso".
	"""

	def setUp(self):
		frappe.set_user("Administrator")
		if not frappe.db.exists("User", EMAIL_MAE):
			user = frappe.new_doc("User")
			user.email = EMAIL_MAE
			user.first_name = "Mãe Filhotes"
			user.send_welcome_email = 0
			user.append("roles", {"role": "Responsavel"})
			user.insert(ignore_permissions=True)

		self.mae = _criar_responsavel(
			CPF_MAE, "Mãe Filhotes", email=EMAIL_MAE, link_documento_identificacao=LINK_DOC
		)
		self.crianca = _criar_novo_associado(CPF_CRIANCA, "Criança Filhotes", _nascimento_com_idade(6))
		vinculo = _vincular(self.mae, self.crianca)
		frappe.db.set_value("Responsavel Vinculo", vinculo, "sera_registrado", 1)
		frappe.set_user(EMAIL_MAE)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.local.response = frappe._dict()
		frappe.db.rollback()

	def test_declaracao_e_devolvida_como_pdf_pelo_proprio_gris(self):
		from gris.api.google_workspace import recepcao_drive

		with (
			mock.patch.object(recepcao_drive, "gerar_declaracao_idoneidade", return_value=LINK_DOC),
			mock.patch.object(
				recepcao_drive,
				"download_file",
				return_value=(b"%PDF-1.4 conteudo", "arquivo.pdf", "application/pdf"),
			),
		):
			registro.baixar_declaracao_idoneidade(self.crianca, self.mae)

		self.assertEqual(frappe.local.response.type, "pdf")
		self.assertEqual(frappe.local.response.filecontent, b"%PDF-1.4 conteudo")
		self.assertIn("Declaracao de Idoneidade", frappe.local.response.filename)
		self.assertTrue(frappe.local.response.filename.endswith(".pdf"))

	def test_documento_de_identificacao_e_devolvido_pelo_proprio_gris(self):
		from gris.api.google_workspace import recepcao_drive

		with mock.patch.object(
			recepcao_drive,
			"download_file",
			return_value=(b"imagem", "rg.jpg", "image/jpeg"),
		):
			registro.baixar_documento_identificacao(self.crianca, self.mae)

		self.assertEqual(frappe.local.response.type, "download")
		self.assertEqual(frappe.local.response.filecontent, b"imagem")

	def test_download_de_responsavel_sem_vinculo_e_bloqueado(self):
		outro = _criar_responsavel(_gerar_cpf("246813579"), "Estranho")

		with self.assertRaises(frappe.PermissionError):
			registro.baixar_documento_identificacao(self.crianca, outro)

	def test_download_sem_documento_enviado_avisa(self):
		frappe.db.set_value("Responsavel", self.mae, "link_documento_identificacao", "")

		with self.assertRaises(frappe.ValidationError):
			registro.baixar_documento_identificacao(self.crianca, self.mae)

	def test_extract_drive_file_id_cobre_os_formatos_de_link(self):
		from gris.api.google_workspace import recepcao_drive

		self.assertEqual(
			recepcao_drive.extract_drive_file_id(
				"https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrSt/view?usp=drivesdk"
			),
			"1AbCdEfGhIjKlMnOpQrSt",
		)
		self.assertEqual(
			recepcao_drive.extract_drive_file_id("https://drive.google.com/open?id=1AbCdEfGhIjKlMnOpQrSt"),
			"1AbCdEfGhIjKlMnOpQrSt",
		)
		self.assertEqual(
			recepcao_drive.extract_drive_file_id("1AbCdEfGhIjKlMnOpQrSt"), "1AbCdEfGhIjKlMnOpQrSt"
		)
		self.assertEqual(recepcao_drive.extract_drive_file_id("https://exemplo.com/x"), "")
		self.assertEqual(recepcao_drive.extract_drive_file_id(""), "")
