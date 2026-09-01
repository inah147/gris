# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Testes das mensagens WhatsApp do fluxo de novos associados.

Todos os cenários rodam sem banco: as consultas e o transporte são substituídos por dublês
e ``today`` é congelado, de modo que a aritmética da cadência seja exata.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api import recepcao_mensagens


class _FakeLogger:
	def info(self, *_args, **_kwargs):
		return None

	def warning(self, *_args, **_kwargs):
		return None

	def exception(self, *_args, **_kwargs):
		return None


def _to_dicts(rows):
	return [frappe._dict(row) for row in rows]


class _AmbienteDeTeste:
	"""Substitui, e depois restaura, tudo que o módulo toca fora de si mesmo."""

	def __init__(
		self,
		*,
		novos_associados=None,
		visitas=None,
		links=None,
		responsaveis=None,
		configuracoes=None,
		chefes=None,
		data_hoje="2026-05-11",
	):
		self.novos_associados = novos_associados or []
		self.visitas = visitas or []
		self.links = links or []
		self.responsaveis = responsaveis or []
		self.configuracoes = configuracoes or {}
		self.chefes = chefes or {}
		self.data_hoje = data_hoje

		self.textos = []
		self.grupos = []
		self.atualizacoes = []
		self.filtros_usados = []

	def __enter__(self):
		modulo = recepcao_mensagens
		self._originais = {
			"get_all": modulo.frappe.get_all,
			"get_single_value": modulo.frappe.db.get_single_value,
			"set_value": modulo.frappe.db.set_value,
			"logger": modulo.frappe.logger,
			"today": modulo.today,
			"enviar_texto": modulo.enviar_texto,
			"enviar_para_grupo": modulo.enviar_para_grupo,
			"obter_logger": modulo.obter_logger,
			"definir_resumo": modulo.definir_resumo,
			"metrica": modulo.metrica,
			"buscar_contatos_chefes_por_ramo": modulo.buscar_contatos_chefes_por_ramo,
			"formatar_idade": modulo.formatar_idade,
		}

		def _fake_get_all(doctype, *_args, **kwargs):
			if doctype == "Novo Associado":
				self.filtros_usados.append(kwargs.get("filters", {}))
				return _to_dicts(self.novos_associados)
			if doctype == "Agenda de Visitas":
				return _to_dicts(self.visitas)
			if doctype == "Responsavel Vinculo":
				return _to_dicts(self.links)
			if doctype == "Responsavel":
				return _to_dicts(self.responsaveis)
			return []

		modulo.frappe.get_all = _fake_get_all
		modulo.frappe.db.get_single_value = lambda _doctype, fieldname: self.configuracoes.get(fieldname)
		modulo.frappe.db.set_value = lambda doctype, name, fieldname, valor, update_modified=True: (
			self.atualizacoes.append(
				{"doctype": doctype, "name": name, "fieldname": fieldname, "valor": str(valor)}
			)
		)
		modulo.frappe.logger = lambda *_a, **_k: _FakeLogger()
		modulo.today = lambda: self.data_hoje
		modulo.enviar_texto = lambda numero, mensagem, **_k: self.textos.append(
			{"numero": numero, "mensagem": mensagem}
		)
		modulo.enviar_para_grupo = lambda jid, mensagem, **kwargs: self.grupos.append(
			{"jid": jid, "mensagem": mensagem, **kwargs}
		)
		modulo.obter_logger = lambda *_a, **_k: _FakeLogger()
		modulo.definir_resumo = lambda *_a, **_k: None
		modulo.metrica = lambda *_a, **_k: None
		modulo.buscar_contatos_chefes_por_ramo = lambda ramos: self.chefes
		return self

	def __exit__(self, *_exc):
		modulo = recepcao_mensagens
		modulo.frappe.get_all = self._originais["get_all"]
		modulo.frappe.db.get_single_value = self._originais["get_single_value"]
		modulo.frappe.db.set_value = self._originais["set_value"]
		modulo.frappe.logger = self._originais["logger"]
		modulo.today = self._originais["today"]
		modulo.enviar_texto = self._originais["enviar_texto"]
		modulo.enviar_para_grupo = self._originais["enviar_para_grupo"]
		modulo.obter_logger = self._originais["obter_logger"]
		modulo.definir_resumo = self._originais["definir_resumo"]
		modulo.metrica = self._originais["metrica"]
		modulo.buscar_contatos_chefes_por_ramo = self._originais["buscar_contatos_chefes_por_ramo"]
		modulo.formatar_idade = self._originais["formatar_idade"]
		return False


VINCULO_PADRAO = [
	{
		"beneficiario_novo_associado": "NA-1",
		"responsavel": "RESP-1",
		"é_guardiao_legal": 1,
		"primeiro_responsavel": 1,
	}
]
RESPONSAVEL_PADRAO = [
	{
		"name": "RESP-1",
		"nome_completo": "Maria Contente da Silva",
		"sexo": "Feminino",
		"celular": "+5511999992222",
		"telefone_secundario": "",
	}
]


class TestCadenciaDoLembreteDeDados(FrappeTestCase):
	def _degraus(self, dias, configuracoes=None):
		with _AmbienteDeTeste(configuracoes=configuracoes or {}):
			return recepcao_mensagens._degraus_do_lembrete_de_dados(dias)

	def test_escada_padrao_de_quatro_seis_oito_e_depois_de_cinco_em_cinco(self):
		self.assertEqual(self._degraus(3), [])
		self.assertEqual(self._degraus(4), [4])
		self.assertEqual(self._degraus(5), [4])
		self.assertEqual(self._degraus(6), [4, 6])
		self.assertEqual(self._degraus(8), [4, 6, 8])
		self.assertEqual(self._degraus(12), [4, 6, 8])
		self.assertEqual(self._degraus(13), [4, 6, 8, 13])
		self.assertEqual(self._degraus(18), [4, 6, 8, 13, 18])

	def test_dias_iniciais_e_intervalo_vem_da_configuracao(self):
		configuracoes = {
			"lembrete_dados_dias_iniciais": "2, 3",
			"lembrete_dados_intervalo_dias": 10,
		}
		self.assertEqual(self._degraus(3, configuracoes), [2, 3])
		self.assertEqual(self._degraus(13, configuracoes), [2, 3, 13])

	def test_configuracao_invalida_cai_no_padrao(self):
		configuracoes = {"lembrete_dados_dias_iniciais": "abc, -1, "}
		self.assertEqual(self._degraus(8, configuracoes), [4, 6, 8])


class TestLembretesDeDadosDeRegistro(FrappeTestCase):
	def _rodar(self, novos_associados, **kwargs):
		with _AmbienteDeTeste(
			novos_associados=novos_associados,
			links=kwargs.pop("links", VINCULO_PADRAO),
			responsaveis=kwargs.pop("responsaveis", RESPONSAVEL_PADRAO),
			**kwargs,
		) as ambiente:
			recepcao_mensagens.enviar_lembretes_dados_registro()
			return ambiente

	def test_envia_no_degrau_vencido_e_carimba_a_data(self):
		ambiente = self._rodar(
			[
				{
					"name": "NA-1",
					"nome_completo": "Joãozinho Feliz",
					"sexo": "Masculino",
					"responsavel_recepcao": None,
					"data_status_aguardar_dados": "2026-05-05",  # 6 dias antes de 11/05
					"data_lembrete_dados": "2026-05-09",  # cobre o degrau de 4 dias
				}
			]
		)

		self.assertEqual(len(ambiente.textos), 1)
		self.assertEqual(ambiente.textos[0]["numero"], "+5511999992222")
		self.assertIn("Olá, Maria!", ambiente.textos[0]["mensagem"])
		self.assertIn("registro do Joãozinho", ambiente.textos[0]["mensagem"])
		self.assertEqual(ambiente.atualizacoes[0]["fieldname"], "data_lembrete_dados")
		self.assertEqual(ambiente.atualizacoes[0]["valor"], "2026-05-11")

	def test_nao_reenvia_dentro_do_mesmo_degrau(self):
		ambiente = self._rodar(
			[
				{
					"name": "NA-1",
					"nome_completo": "Joãozinho Feliz",
					"sexo": "Masculino",
					"responsavel_recepcao": None,
					"data_status_aguardar_dados": "2026-05-05",
					"data_lembrete_dados": "2026-05-11",
				}
			]
		)

		self.assertEqual(ambiente.textos, [])
		self.assertEqual(ambiente.atualizacoes, [])

	def test_nao_envia_antes_do_primeiro_degrau(self):
		ambiente = self._rodar(
			[
				{
					"name": "NA-1",
					"nome_completo": "Joãozinho Feliz",
					"sexo": "Masculino",
					"responsavel_recepcao": None,
					"data_status_aguardar_dados": "2026-05-09",  # 2 dias
					"data_lembrete_dados": None,
				}
			]
		)

		self.assertEqual(ambiente.textos, [])

	def test_consulta_filtra_por_status_e_dados_pendentes(self):
		ambiente = self._rodar(
			[
				{
					"name": "NA-1",
					"nome_completo": "Joãozinho Feliz",
					"sexo": "Masculino",
					"responsavel_recepcao": None,
					"data_status_aguardar_dados": "2026-05-01",
					"data_lembrete_dados": None,
				}
			]
		)

		filtros = ambiente.filtros_usados[0]
		self.assertEqual(filtros["status"], "Aguardar Dados")
		self.assertEqual(filtros["dados_para_registro_enviados"], 0)
		self.assertEqual(filtros["data_status_aguardar_dados"], ["is", "set"])

	def test_sem_telefone_nao_envia_nem_carimba(self):
		ambiente = self._rodar(
			[
				{
					"name": "NA-1",
					"nome_completo": "Joãozinho Feliz",
					"sexo": "Masculino",
					"responsavel_recepcao": None,
					"data_status_aguardar_dados": "2026-05-01",
					"data_lembrete_dados": None,
				}
			],
			responsaveis=[
				{"name": "RESP-1", "nome_completo": "Maria", "celular": "", "telefone_secundario": ""}
			],
		)

		self.assertEqual(ambiente.textos, [])
		self.assertEqual(ambiente.atualizacoes, [])


class TestVisitasDoDia(FrappeTestCase):
	def _rodar(self, visitas, novos_associados, chefes=None):
		with _AmbienteDeTeste(
			visitas=visitas,
			novos_associados=novos_associados,
			links=VINCULO_PADRAO,
			responsaveis=RESPONSAVEL_PADRAO,
			configuracoes={"grupo_chefes_secao_whatsapp": "120@g.us"},
			chefes=chefes or {},
		) as ambiente:
			recepcao_mensagens.formatar_idade = lambda _data: "6 anos e 8 meses"
			recepcao_mensagens.notificar_visitas_do_dia()
			return ambiente

	def test_agrupa_por_ramo_e_marca_ramos_vazios(self):
		ambiente = self._rodar(
			visitas=[{"name": "AV-1", "jovem": "NA-1", "visita_confirmada": 1, "ramo": "Lobinho"}],
			novos_associados=[
				{
					"name": "NA-1",
					"nome_completo": "Joãozinho Feliz",
					"data_de_nascimento": "2019-09-01",
					"sexo": "Masculino",
					"ramo": "Lobinho",
				}
			],
		)

		self.assertEqual(len(ambiente.grupos), 1)
		mensagem = ambiente.grupos[0]["mensagem"]
		self.assertIn("*Visitas do dia 11/05/2026*", mensagem)
		self.assertIn(
			"_Ramo Lobinho_\n- Joãozinho Feliz - 6 anos e 8 meses - "
			"filho de Maria Contente da Silva (confirmado)",
			mensagem,
		)
		self.assertIn("_Ramo Filhotes_\n- Nenhuma visita", mensagem)
		self.assertIn("_Ramo Pioneiro_\n- Nenhuma visita", mensagem)
		self.assertTrue(mensagem.endswith("_Esta é uma mensagem automática_"))

	def test_sem_visitas_ainda_publica_a_lista_completa(self):
		ambiente = self._rodar(visitas=[], novos_associados=[])

		mensagem = ambiente.grupos[0]["mensagem"]
		self.assertEqual(mensagem.count("- Nenhuma visita"), 5)

	def test_visita_nao_confirmada_e_sexo_feminino(self):
		ambiente = self._rodar(
			visitas=[{"name": "AV-1", "jovem": "NA-1", "visita_confirmada": 0, "ramo": "Escoteiro"}],
			novos_associados=[
				{
					"name": "NA-1",
					"nome_completo": "Joaninha Alegre",
					"data_de_nascimento": "2014-09-01",
					"sexo": "Feminino",
					"ramo": "Escoteiro",
				}
			],
		)

		self.assertIn(
			"- Joaninha Alegre - 6 anos e 8 meses - filha de Maria Contente da Silva (não confirmado)",
			ambiente.grupos[0]["mensagem"],
		)

	def test_sem_grupo_configurado_nao_envia(self):
		with _AmbienteDeTeste(visitas=[], novos_associados=[], configuracoes={}) as ambiente:
			recepcao_mensagens.notificar_visitas_do_dia()

		self.assertEqual(ambiente.grupos, [])


class TestLembretesRecorrentes(FrappeTestCase):
	def _rodar(self, rotina, novos_associados, configuracoes=None):
		with _AmbienteDeTeste(
			novos_associados=novos_associados,
			links=VINCULO_PADRAO,
			responsaveis=RESPONSAVEL_PADRAO,
			configuracoes=configuracoes or {},
		) as ambiente:
			rotina()
			return ambiente

	def test_pesquisa_respeita_o_intervalo_configurado(self):
		jovem = {
			"name": "NA-1",
			"nome_completo": "Joãozinho Feliz",
			"sexo": "Masculino",
			"data_lembrete_pesquisa": "2026-05-09",  # 2 dias atrás
		}

		ambiente = self._rodar(
			recepcao_mensagens.enviar_lembretes_pesquisa_novos_associados,
			[jovem],
			{"lembrete_pesquisa_intervalo_dias": 3},
		)
		self.assertEqual(ambiente.textos, [])

		ambiente = self._rodar(
			recepcao_mensagens.enviar_lembretes_pesquisa_novos_associados,
			[jovem],
			{"lembrete_pesquisa_intervalo_dias": 2},
		)
		self.assertEqual(len(ambiente.textos), 1)
		self.assertIn("pesquisa de novos associados", ambiente.textos[0]["mensagem"])

	def test_primeiro_envio_acontece_sem_carimbo_anterior(self):
		ambiente = self._rodar(
			recepcao_mensagens.enviar_lembretes_id_escoteiros,
			[
				{
					"name": "NA-1",
					"nome_completo": "Joãozinho",
					"sexo": "Masculino",
					"data_lembrete_id_escoteiros": None,
				}
			],
		)

		self.assertEqual(len(ambiente.textos), 1)
		self.assertIn("id.escoteiros.org.br", ambiente.textos[0]["mensagem"])
		self.assertEqual(ambiente.atualizacoes[0]["fieldname"], "data_lembrete_id_escoteiros")

	def test_ficha_medica_consulta_a_etapa_de_cada_tipo_de_registro(self):
		ambiente = self._rodar(
			recepcao_mensagens.enviar_lembretes_ficha_medica,
			[
				{
					"name": "NA-1",
					"nome_completo": "Joãozinho",
					"sexo": "Feminino",
					"data_lembrete_ficha_medica": None,
				}
			],
		)

		# Uma consulta por tipo de registro, cada uma com a sua etapa de efetivação.
		provisorio, definitivo = ambiente.filtros_usados
		self.assertEqual(provisorio["tipo_de_registro"], "Provisório")
		self.assertEqual(provisorio["registro_provisorio_efetivado"], 1)
		self.assertEqual(provisorio["ficha_medica_preenchida"], 0)
		self.assertEqual(definitivo["tipo_de_registro"], "Definitivo")
		self.assertEqual(definitivo["registro_definitivo_efetivado"], 1)
		self.assertIn("ficha médica", ambiente.textos[0]["mensagem"])

	def test_consultas_ignoram_fila_de_espera_e_concluidos(self):
		ambiente = self._rodar(
			recepcao_mensagens.enviar_lembretes_id_escoteiros,
			[
				{
					"name": "NA-1",
					"nome_completo": "Joãozinho",
					"sexo": "Masculino",
					"data_lembrete_id_escoteiros": None,
				}
			],
		)

		self.assertEqual(ambiente.filtros_usados[0]["status"], ["not in", ["Fila de espera", "Concluído"]])


class TestAvisoDeAcolhida(FrappeTestCase):
	def test_menciona_o_chefe_do_ramo_e_carimba(self):
		with _AmbienteDeTeste(
			novos_associados=[
				{
					"name": "NA-1",
					"nome_completo": "Joãozinho Feliz",
					"sexo": "Masculino",
					"data_de_nascimento": "2014-09-01",
					"ramo": "Escoteiro",
					"data_lembrete_acolhida": None,
				}
			],
			links=VINCULO_PADRAO,
			responsaveis=RESPONSAVEL_PADRAO,
			configuracoes={"grupo_chefes_secao_whatsapp": "120@g.us"},
			chefes={
				"Escoteiro": [frappe._dict({"nome_completo": "Ana Chefe", "telefone": "+5511988887777"})]
			},
		) as ambiente:
			recepcao_mensagens.enviar_lembretes_acolhida_lenco()

		self.assertEqual(len(ambiente.grupos), 1)
		envio = ambiente.grupos[0]
		self.assertEqual(envio["mencionar"], ["+5511988887777"])
		self.assertIn("@5511988887777", envio["mensagem"])
		self.assertIn("acolhida e entrega do lenço", envio["mensagem"])
		self.assertIn("*Responsável*: Maria Contente da Silva", envio["mensagem"])
		self.assertEqual(ambiente.atualizacoes[0]["fieldname"], "data_lembrete_acolhida")

	def test_sem_chefe_cadastrado_envia_sem_mencao(self):
		with _AmbienteDeTeste(
			novos_associados=[
				{
					"name": "NA-1",
					"nome_completo": "Joãozinho Feliz",
					"sexo": "Masculino",
					"data_de_nascimento": "2014-09-01",
					"ramo": "Escoteiro",
					"data_lembrete_acolhida": None,
				}
			],
			links=VINCULO_PADRAO,
			responsaveis=RESPONSAVEL_PADRAO,
			configuracoes={"grupo_chefes_secao_whatsapp": "120@g.us"},
		) as ambiente:
			recepcao_mensagens.enviar_lembretes_acolhida_lenco()

		self.assertIsNone(ambiente.grupos[0]["mencionar"])
		self.assertNotIn("@55", ambiente.grupos[0]["mensagem"])


class TestMensagens(FrappeTestCase):
	def test_registro_provisorio_e_definitivo_mudam_apenas_o_termo(self):
		provisorio = recepcao_mensagens._montar_registro_criado(
			primeiro_nome_responsavel="Maria",
			primeiro_nome_jovem="Joãozinho",
			sexo_jovem="Masculino",
			sexo_responsavel="Feminino",
			tipo_registro="Provisório",
			numero_registro="123456-7",
		)
		definitivo = recepcao_mensagens._montar_registro_criado(
			primeiro_nome_responsavel="Maria",
			primeiro_nome_jovem="Joãozinho",
			sexo_jovem="Masculino",
			sexo_responsavel="Feminino",
			tipo_registro="Definitivo",
			numero_registro="123456-7",
		)

		self.assertIn("o registro provisório de Joãozinho", provisorio)
		self.assertIn("o registro definitivo de Joãozinho", definitivo)
		self.assertIn("123456-7", provisorio)
		self.assertIn("https://paxtu100.escoteiros.org.br/primeiro_acesso", provisorio)

	def test_lembrete_de_dados_cita_o_responsavel_pela_recepcao(self):
		mensagem = recepcao_mensagens._montar_lembrete_dados(
			primeiro_nome_responsavel="Maria",
			primeiro_nome_jovem="Joãozinho",
			sexo_jovem="Masculino",
			recepcionista=frappe._dict(
				{"nome": "Ana Recepção", "sexo": "Feminino", "telefone": "+5511988887777"}
			),
		)

		self.assertIn("só avisar a Ana Recepção", mensagem)
		self.assertIn("O telefone é: +5511988887777", mensagem)

	def test_lembrete_de_dados_omite_o_paragrafo_sem_responsavel_pela_recepcao(self):
		mensagem = recepcao_mensagens._montar_lembrete_dados(
			primeiro_nome_responsavel="Maria",
			primeiro_nome_jovem="Joãozinho",
			sexo_jovem="Masculino",
			recepcionista=None,
		)

		self.assertNotIn("só avisar", mensagem)
		self.assertIn("Grande abraço!", mensagem)

	def test_mencao_normaliza_o_numero_com_ddi(self):
		self.assertEqual(recepcao_mensagens._mencao("(11) 98888-7777"), "@5511988887777")
		self.assertEqual(recepcao_mensagens._mencao("+55 11 98888-7777"), "@5511988887777")
		self.assertEqual(recepcao_mensagens._mencao(""), "")


class TestConcordanciaDeGenero(FrappeTestCase):
	"""Sabendo o sexo, o texto flexiona: nada de "do(a)" quando se conhece a pessoa."""

	JOVEM_F = frappe._dict(
		{
			"name": "NA-F",
			"nome_completo": "Joaninha Alegre Souza",
			"sexo": "Feminino",
			"data_de_nascimento": "2014-09-01",
			"ramo": "Escoteiro",
		}
	)
	RESP_M = frappe._dict({"nome": "Carlos Souza", "sexo": "Masculino", "telefone": "+5511988887777"})
	RESP_F = frappe._dict({"nome": "Carla Souza", "sexo": "Feminino", "telefone": "+5511988887777"})

	def test_dados_preenchidos_flexiona_nova_associada(self):
		self.assertIn(
			"registro da nova associada no PAXTU",
			recepcao_mensagens._montar_dados_preenchidos("Joaninha", "Carla", "Feminino"),
		)
		self.assertIn(
			"registro do novo associado no PAXTU",
			recepcao_mensagens._montar_dados_preenchidos("Joãozinho", "Carla", "Masculino"),
		)

	def test_lembrete_de_dados_flexiona_jovem_e_recepcionista(self):
		mensagem = recepcao_mensagens._montar_lembrete_dados(
			primeiro_nome_responsavel="Carla",
			primeiro_nome_jovem="Joaninha",
			sexo_jovem="Feminino",
			recepcionista=frappe._dict({"nome": "João Recepção", "sexo": "Masculino", "telefone": ""}),
		)

		self.assertIn("o registro da Joaninha", mensagem)
		self.assertIn("só avisar ao João Recepção", mensagem)

	def test_recepcao_realizada_flexiona_o_artigo_do_jovem(self):
		self.assertIn(
			"informar que a Joaninha fez a visita hoje",
			recepcao_mensagens._montar_recepcao_realizada(
				primeiro_nome_jovem="Joaninha", sexo_jovem="Feminino", mencao="", ficha=""
			),
		)
		self.assertIn(
			"informar que o Joãozinho fez a visita hoje",
			recepcao_mensagens._montar_recepcao_realizada(
				primeiro_nome_jovem="Joãozinho", sexo_jovem="Masculino", mencao="", ficha=""
			),
		)

	def test_registro_criado_flexiona_jovem_e_quem_le(self):
		mensagem = recepcao_mensagens._montar_registro_criado(
			primeiro_nome_responsavel="Carlos",
			primeiro_nome_jovem="Joaninha",
			sexo_jovem="Feminino",
			sexo_responsavel="Masculino",
			tipo_registro="Provisório",
			numero_registro="123456-7",
		)

		self.assertIn("primeiro acesso da jovem no Paxtu", mensagem)
		self.assertIn("o CPF da jovem", mensagem)
		# "pela qual" concorda com a jovem; "do responsável" concorda com quem lê.
		self.assertIn("Paxtu 100 da jovem pela qual você é responsável", mensagem)
		self.assertIn("número de registro do responsável", mensagem)

	def test_ficha_medica_flexiona_artigo_e_pronome(self):
		self.assertIn(
			"o registro da Joaninha já foi processado",
			recepcao_mensagens._montar_lembrete_ficha_medica(
				primeiro_nome_responsavel="Carla", primeiro_nome_jovem="Joaninha", sexo_jovem="Feminino"
			),
		)
		self.assertIn(
			"ficha médica dela!",
			recepcao_mensagens._montar_lembrete_ficha_medica(
				primeiro_nome_responsavel="Carla", primeiro_nome_jovem="Joaninha", sexo_jovem="Feminino"
			),
		)
		self.assertIn(
			"ficha médica dele!",
			recepcao_mensagens._montar_lembrete_ficha_medica(
				primeiro_nome_responsavel="Carla", primeiro_nome_jovem="Joãozinho", sexo_jovem="Masculino"
			),
		)

	def test_acolhida_flexiona_as_duas_ocorrencias(self):
		mensagem = recepcao_mensagens._montar_acolhida(
			primeiro_nome_jovem="Joaninha", sexo_jovem="Feminino", ficha="", mencao=""
		)

		self.assertIn("O registro definitivo da jovem Joaninha foi efetivado", mensagem)
		self.assertIn("Aqui estão os dados da jovem:", mensagem)

	def test_ficha_flexiona_o_rotulo_pelo_sexo_do_responsavel(self):
		self.assertIn(
			"*Telefone da responsável*",
			recepcao_mensagens._ficha_do_jovem(self.JOVEM_F, self.RESP_F),
		)
		self.assertIn(
			"*Telefone do responsável*",
			recepcao_mensagens._ficha_do_jovem(self.JOVEM_F, self.RESP_M),
		)

	def test_ficha_sem_responsavel_usa_a_forma_simples(self):
		"""Sem ninguém vinculado não há com quem concordar — "do(a)" só polui o texto."""
		ficha = recepcao_mensagens._ficha_do_jovem(self.JOVEM_F, None)

		self.assertIn("*Telefone do responsável*: não cadastrado", ficha)
		self.assertNotIn("do(a)", ficha)

	def test_filiacao_acompanha_o_sexo_do_jovem(self):
		self.assertEqual(recepcao_mensagens._filiacao("Feminino"), "filha de")
		self.assertEqual(recepcao_mensagens._filiacao("Masculino"), "filho de")
		self.assertEqual(recepcao_mensagens._filiacao(None), "filho(a) de")

	def test_sem_sexo_cai_na_forma_dupla_e_nunca_arrisca(self):
		"""Sexo ausente é raro na base, mas não pode virar chute de gênero."""
		mensagem = recepcao_mensagens._montar_acolhida(
			primeiro_nome_jovem="Alex", sexo_jovem=None, ficha="", mencao=""
		)
		self.assertIn("O registro definitivo do(a) jovem Alex", mensagem)
