# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Testes das mensagens WhatsApp do fluxo de novos associados.

Todos os cenários rodam sem banco: as consultas e o transporte são substituídos por dublês
e ``today`` é congelado, de modo que a aritmética da cadência seja exata.
"""

from typing import ClassVar
from unittest.mock import patch

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
			"valor_bruto_do_single": modulo._valor_bruto_do_single,
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
		# Os interruptores msg_* leem tabSingles cru para distinguir 0 de linha ausente.
		modulo._valor_bruto_do_single = lambda fieldname: self.configuracoes.get(fieldname)
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
		modulo._valor_bruto_do_single = self._originais["valor_bruto_do_single"]
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

	def test_ficha_medica_espera_o_aviso_do_numero_de_registro(self):
		"""A etapa de efetivação é marcada à mão pela recepção e pode vir antes do aviso.

		Sem esta trava, a família era mandada para o Paxtu sem ter recebido o número com
		que entra nele.
		"""
		ambiente = self._rodar(
			recepcao_mensagens.enviar_lembretes_ficha_medica,
			[{"name": "NA-1", "nome_completo": "Joãozinho", "sexo": "Masculino"}],
		)

		for filtros in ambiente.filtros_usados:
			self.assertEqual(filtros["data_mensagem_registro_criado"], ["is", "set"])

	def test_id_escoteiros_espera_o_aviso_do_numero_de_registro(self):
		ambiente = self._rodar(
			recepcao_mensagens.enviar_lembretes_id_escoteiros,
			[{"name": "NA-1", "nome_completo": "Joãozinho", "sexo": "Masculino"}],
		)

		self.assertEqual(ambiente.filtros_usados[0]["data_mensagem_registro_criado"], ["is", "set"])

	def test_sem_a_mensagem_de_registro_as_cobrancas_nao_ficam_presas(self):
		"""Com o aviso desligado o carimbo nunca é gravado: travar seria silenciar para sempre."""
		for rotina in (
			recepcao_mensagens.enviar_lembretes_ficha_medica,
			recepcao_mensagens.enviar_lembretes_id_escoteiros,
		):
			with self.subTest(rotina=rotina.__name__):
				ambiente = self._rodar(
					rotina,
					[{"name": "NA-1", "nome_completo": "Joãozinho", "sexo": "Masculino"}],
					{"msg_registro_criado": 0},
				)

				for filtros in ambiente.filtros_usados:
					self.assertNotIn("data_mensagem_registro_criado", filtros)

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


class TestLinksNasMensagens(FrappeTestCase):
	"""Quem recebe a cobrança precisa do link junto: pedir sem dizer onde não resolve."""

	def test_lembrete_de_dados_leva_o_link_do_gris(self):
		mensagem = recepcao_mensagens._montar_lembrete_dados(
			primeiro_nome_responsavel="Maria",
			primeiro_nome_jovem="Joãozinho",
			sexo_jovem="Masculino",
			recepcionista=None,
		)

		self.assertIn(recepcao_mensagens.CAMINHO_GRIS_REGISTRO, mensagem)

	def test_ficha_medica_leva_o_link_do_paxtu(self):
		with patch.object(recepcao_mensagens, "_buscar_responsavel_administrativo", return_value=None):
			mensagem = recepcao_mensagens._montar_lembrete_ficha_medica(
				primeiro_nome_responsavel="Maria",
				primeiro_nome_jovem="Joãozinho",
				sexo_jovem="Masculino",
			)

		self.assertIn(recepcao_mensagens.PAXTU_BASE, mensagem)

	def test_registro_criado_leva_o_paxtu_do_dia_a_dia(self):
		with patch.object(recepcao_mensagens, "_buscar_responsavel_administrativo", return_value=None):
			mensagem = recepcao_mensagens._montar_registro_criado(
				primeiro_nome_responsavel="Maria",
				primeiro_nome_jovem="Joãozinho",
				sexo_jovem="Masculino",
				sexo_responsavel="Feminino",
				tipo_registro="Provisório",
				numero_registro="123456-7",
			)

		self.assertIn(recepcao_mensagens.PAXTU_PRIMEIRO_ACESSO, mensagem)
		self.assertIn(f"o Paxtu fica em {recepcao_mensagens.PAXTU_BASE}", mensagem)


class TestContatoDoAdministrativo(FrappeTestCase):
	"""Sem saber o número de registro, o responsável trava — a mensagem tem que dizer a quem perguntar."""

	ADMINISTRATIVO = frappe._dict(
		{
			"name": "A-1",
			"nome_completo": "Ana Administrativo",
			"sexo": "Feminino",
			"telefone": "+5511977776666",
		}
	)

	def _ficha_medica(self, administrativo):
		with patch.object(
			recepcao_mensagens, "_buscar_responsavel_administrativo", return_value=administrativo
		):
			return recepcao_mensagens._montar_lembrete_ficha_medica(
				primeiro_nome_responsavel="Maria",
				primeiro_nome_jovem="Joãozinho",
				sexo_jovem="Masculino",
			)

	def _id_escoteiros(self, administrativo):
		with patch.object(
			recepcao_mensagens, "_buscar_responsavel_administrativo", return_value=administrativo
		):
			return recepcao_mensagens._montar_lembrete_id_escoteiros("Maria")

	def _registro_criado(self, administrativo):
		with patch.object(
			recepcao_mensagens, "_buscar_responsavel_administrativo", return_value=administrativo
		):
			return recepcao_mensagens._montar_registro_criado(
				primeiro_nome_responsavel="Maria",
				primeiro_nome_jovem="Joãozinho",
				sexo_jovem="Masculino",
				sexo_responsavel="Feminino",
				tipo_registro="Provisório",
				numero_registro="123456-7",
			)

	def test_as_tres_mensagens_citam_o_administrativo(self):
		for rotulo, montar in (
			("ficha médica", self._ficha_medica),
			("id@escoteiros", self._id_escoteiros),
			("registro criado", self._registro_criado),
		):
			with self.subTest(mensagem=rotulo):
				mensagem = montar(self.ADMINISTRATIVO)

				# "fale a Ana" (Feminino), não "fale ao Ana".
				self.assertIn("a Ana Administrativo, do administrativo", mensagem)
				self.assertIn("+5511977776666", mensagem)

	def test_cobrancas_citam_o_administrativo_uma_vez_so(self):
		"""Dúvida de registro e aviso de "já fiz" levam à mesma pessoa: um parágrafo, uma menção."""
		for rotulo, montar in (
			("ficha médica", self._ficha_medica),
			("id@escoteiros", self._id_escoteiros),
		):
			with self.subTest(mensagem=rotulo):
				mensagem = montar(self.ADMINISTRATIVO)

				self.assertEqual(mensagem.count("Ana Administrativo"), 1)
				self.assertEqual(mensagem.count("+5511977776666"), 1)
				self.assertNotIn("Ficou em dúvida sobre o número de registro?", mensagem)

	def test_registro_criado_mantem_o_paragrafo_de_duvidas(self):
		"""A mensagem que entrega o número segue com o texto antigo, que não tem "já fez"."""
		mensagem = self._registro_criado(self.ADMINISTRATIVO)

		self.assertIn("Ficou em dúvida sobre o número de registro? Fale a Ana Administrativo", mensagem)
		self.assertNotIn("Se você já fez esta ação", mensagem)

	def test_sem_administrativo_configurado_o_paragrafo_some(self):
		for rotulo, montar in (
			("ficha médica", self._ficha_medica),
			("id@escoteiros", self._id_escoteiros),
		):
			with self.subTest(mensagem=rotulo):
				mensagem = montar(None)

				self.assertNotIn("do administrativo", mensagem)
				self.assertIn("Grande abraço!", mensagem)

	def test_administrativo_sem_telefone_nao_entra(self):
		sem_telefone = frappe._dict(dict(self.ADMINISTRATIVO, telefone=""))

		self.assertNotIn("do administrativo", self._ficha_medica(sem_telefone))

	def test_registro_criado_mantem_a_saida_antiga_sem_administrativo(self):
		mensagem = self._registro_criado(None)

		self.assertIn("perguntar para algum escotista da seção", mensagem)


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


class TestParagrafoAdministrativoDasCobrancas(FrappeTestCase):
	"""Quem já cumpriu a tarefa precisa saber a quem avisar para a série parar."""

	ADMINISTRATIVO = frappe._dict(
		{
			"name": "A-1",
			"nome_completo": "Ana Administrativo",
			"sexo": "Feminino",
			"telefone": "+5511977776666",
		}
	)

	def _montar(self, montador, administrativo):
		with patch.object(
			recepcao_mensagens, "_buscar_responsavel_administrativo", return_value=administrativo
		):
			return montador()

	def _ficha_medica(self, administrativo):
		return self._montar(
			lambda: recepcao_mensagens._montar_lembrete_ficha_medica(
				primeiro_nome_responsavel="Maria",
				primeiro_nome_jovem="Joãozinho",
				sexo_jovem="Masculino",
			),
			administrativo,
		)

	def _id_escoteiros(self, administrativo):
		return self._montar(
			lambda: recepcao_mensagens._montar_lembrete_id_escoteiros("Maria"),
			administrativo,
		)

	def test_as_duas_cobrancas_dao_a_saida_com_nome_e_telefone(self):
		for rotulo, montar in (
			("ficha médica", self._ficha_medica),
			("id@escoteiros", self._id_escoteiros),
		):
			with self.subTest(mensagem=rotulo):
				mensagem = montar(self.ADMINISTRATIVO)

				self.assertIn("Se você já fez esta ação, por favor desconsidere esta mensagem.", mensagem)
				# "fale a Ana" (Feminino), não "fale ao Ana".
				self.assertIn("fale a Ana Administrativo, do administrativo", mensagem)
				self.assertIn("+5511977776666", mensagem)

	def test_o_mesmo_paragrafo_cobre_a_duvida_de_registro(self):
		"""O parágrafo é um só justamente porque as duas coisas levam à mesma pessoa."""
		mensagem = self._ficha_medica(self.ADMINISTRATIVO)

		self.assertIn("tirar dúvida sobre o número de registro", mensagem)

	def test_frase_vem_antes_da_assinatura(self):
		"""O pedido foi "ao final da mensagem, antes do aviso de mensagem automática"."""
		mensagem = self._id_escoteiros(self.ADMINISTRATIVO)

		self.assertLess(
			mensagem.index("Se você já fez esta ação"),
			mensagem.index(recepcao_mensagens.ASSINATURA),
		)

	def test_sem_administrativo_a_frase_permanece_na_forma_generica(self):
		"""A saída vale mesmo sem contato cadastrado — só perde o nome e o telefone."""
		for rotulo, montar in (
			("ficha médica", self._ficha_medica),
			("id@escoteiros", self._id_escoteiros),
		):
			with self.subTest(mensagem=rotulo):
				mensagem = montar(None)

				self.assertIn("Se você já fez esta ação, por favor desconsidere esta mensagem.", mensagem)
				self.assertIn("avise o responsável pelo administrativo do grupo", mensagem)
				self.assertNotIn("pelo telefone", mensagem)

	def test_pesquisa_nao_ganha_a_frase(self):
		"""Só as cobranças que dependem de marcar etapa no Paxtu levam a saída."""
		self.assertNotIn(
			"Se você já fez esta ação",
			recepcao_mensagens._montar_lembrete_pesquisa("Maria"),
		)


class TestRepeticaoDoAvisoDeAcolhida(FrappeTestCase):
	JOVEM: ClassVar[dict] = {
		"name": "NA-1",
		"nome_completo": "Joãozinho Feliz",
		"sexo": "Masculino",
		"data_de_nascimento": "2014-09-01",
		"ramo": "Escoteiro",
	}

	def _enviar(self, data_lembrete_acolhida):
		with _AmbienteDeTeste(
			novos_associados=[dict(self.JOVEM, data_lembrete_acolhida=data_lembrete_acolhida)],
			links=VINCULO_PADRAO,
			responsaveis=RESPONSAVEL_PADRAO,
			configuracoes={"grupo_chefes_secao_whatsapp": "120@g.us"},
		) as ambiente:
			recepcao_mensagens.enviar_lembretes_acolhida_lenco()

		return ambiente.grupos[0]["mensagem"]

	def test_primeiro_envio_anuncia_que_chegou_a_hora(self):
		mensagem = self._enviar(None)

		self.assertIn("foi efetivado!", mensagem)
		self.assertIn("chegou a hora de fazer sua acolhida", mensagem)
		self.assertNotIn("ainda não foi realizada", mensagem)

	def test_repeticao_cobra_e_pede_para_marcar_no_gris(self):
		"""Depois do primeiro aviso o anúncio não cabe mais: vira cobrança com saída."""
		mensagem = self._enviar("2026-05-04")

		self.assertIn("A acolhida do jovem Joãozinho ainda não foi realizada", mensagem)
		self.assertIn("marque a etapa como concluída no Gris", mensagem)
		self.assertNotIn("chegou a hora", mensagem)

	def test_repeticao_mantem_a_ficha_e_a_assinatura(self):
		mensagem = self._enviar("2026-05-04")

		self.assertIn("*Responsável*: Maria Contente da Silva", mensagem)
		self.assertIn(recepcao_mensagens.ASSINATURA, mensagem)


class TestAvisoDeDesistencia(FrappeTestCase):
	def _notificar(self, *, sexo="Masculino", ramo="Escoteiro", configuracoes=None, chefes=None):
		with _AmbienteDeTeste(
			configuracoes=configuracoes
			if configuracoes is not None
			else {"grupo_chefes_secao_whatsapp": "120@g.us"},
			chefes=chefes or {},
		) as ambiente:
			recepcao_mensagens.notificar_desistencia(
				nome_completo="Joãozinho Feliz da Silva", sexo=sexo, ramo=ramo
			)

		return ambiente

	def test_menciona_o_chefe_do_ramo_no_corpo_e_no_payload(self):
		"""O WhatsApp só marca alguém quando o número está no texto E no campo mencionar."""
		ambiente = self._notificar(
			chefes={"Escoteiro": [frappe._dict({"nome_completo": "Ana Chefe", "telefone": "+5511988887777"})]}
		)

		envio = ambiente.grupos[0]
		self.assertEqual(envio["jid"], "120@g.us")
		self.assertEqual(envio["mencionar"], ["+5511988887777"])
		self.assertIn("@5511988887777", envio["mensagem"])

	def test_texto_usa_o_nome_completo_e_flexiona_o_desligamento(self):
		masculino = self._notificar(sexo="Masculino").grupos[0]["mensagem"]
		feminino = self._notificar(sexo="Feminino").grupos[0]["mensagem"]

		self.assertIn(
			"Passando para informar que Joãozinho Feliz da Silva não continuará as atividades",
			masculino,
		)
		self.assertIn("será desligado da UEL", masculino)
		self.assertIn("será desligada da UEL", feminino)
		self.assertIn(recepcao_mensagens.ASSINATURA, masculino)

	def test_sem_sexo_nao_arrisca_um_genero(self):
		self.assertIn("será desligado(a) da UEL", self._notificar(sexo=None).grupos[0]["mensagem"])

	def test_sem_chefe_cadastrado_envia_sem_mencao(self):
		envio = self._notificar(ramo="Escoteiro").grupos[0]

		self.assertIsNone(envio["mencionar"])
		self.assertNotIn("@55", envio["mensagem"])

	def test_sem_grupo_configurado_nao_envia(self):
		self.assertEqual(self._notificar(configuracoes={}).grupos, [])

	def test_sem_nome_nao_envia(self):
		"""Um aviso sem nome não informa nada e ainda assusta o grupo."""
		with _AmbienteDeTeste(configuracoes={"grupo_chefes_secao_whatsapp": "120@g.us"}) as ambiente:
			recepcao_mensagens.notificar_desistencia(nome_completo="   ")

		self.assertEqual(ambiente.grupos, [])


class TestOrientacaoPosVisita(FrappeTestCase):
	JOVEM: ClassVar[dict] = {
		"name": "NA-1",
		"nome_completo": "Joãozinho Feliz",
		"sexo": "Masculino",
		"responsavel_recepcao": "ana@escoteiros.org.br",
		"data_mensagem_orientacao_visita": None,
	}

	def _fake_get_value(self, jovem):
		def _get_value(doctype, *_args, **_kwargs):
			if doctype == "Novo Associado":
				return frappe._dict(jovem) if jovem else None
			if doctype == "User":
				return frappe._dict(
					{
						"name": "ana@escoteiros.org.br",
						"full_name": "Ana Recepção",
						"mobile_no": "+5511966665555",
					}
				)
			if doctype == "Associado":
				return frappe._dict({"sexo": "Feminino", "telefone": "+5511966665555"})
			return None

		return _get_value

	def _notificar(self, jovem=None, configuracoes=None):
		jovem = self.JOVEM if jovem is None else jovem
		with _AmbienteDeTeste(
			links=VINCULO_PADRAO,
			responsaveis=RESPONSAVEL_PADRAO,
			configuracoes=configuracoes or {},
		) as ambiente:
			with patch.object(
				recepcao_mensagens.frappe.db, "get_value", side_effect=self._fake_get_value(jovem)
			):
				recepcao_mensagens.notificar_orientacao_pos_visita("NA-1")

		return ambiente

	def test_orienta_o_responsavel_e_carimba(self):
		ambiente = self._notificar()

		self.assertEqual(len(ambiente.textos), 1)
		envio = ambiente.textos[0]
		self.assertEqual(envio["numero"], "+5511999992222")
		self.assertIn("Olá, Maria!", envio["mensagem"])
		self.assertIn("Foi muito bom receber vocês no Grupo Escoteiro hoje!", envio["mensagem"])
		self.assertIn("preencher os dados do Joãozinho", envio["mensagem"])
		self.assertIn(recepcao_mensagens.TUTORIAL_LOGIN, envio["mensagem"])
		self.assertIn(recepcao_mensagens.TUTORIAL_DADOS_REGISTRO, envio["mensagem"])
		self.assertEqual(
			ambiente.atualizacoes[0]["fieldname"],
			"data_mensagem_orientacao_visita",
		)

	def test_cita_o_recepcionista_com_a_concordancia_certa(self):
		mensagem = self._notificar().textos[0]["mensagem"]

		# "falar com a Ana" (Feminino), não "falar com o Ana".
		self.assertIn("é só falar com a Ana Recepção", mensagem)
		self.assertIn("+5511966665555", mensagem)

	def test_nao_reenvia_quando_ja_carimbado(self):
		ambiente = self._notificar(jovem=dict(self.JOVEM, data_mensagem_orientacao_visita="2026-05-10"))

		self.assertEqual(ambiente.textos, [])
		self.assertEqual(ambiente.atualizacoes, [])

	def test_sem_telefone_nao_envia_nem_carimba(self):
		with _AmbienteDeTeste(links=[], responsaveis=[]) as ambiente:
			with patch.object(
				recepcao_mensagens.frappe.db, "get_value", side_effect=self._fake_get_value(self.JOVEM)
			):
				recepcao_mensagens.notificar_orientacao_pos_visita("NA-1")

		self.assertEqual(ambiente.textos, [])
		self.assertEqual(ambiente.atualizacoes, [])

	def test_sem_recepcionista_o_paragrafo_de_contato_some(self):
		jovem = dict(self.JOVEM, responsavel_recepcao=None)
		mensagem = self._notificar(jovem=jovem).textos[0]["mensagem"]

		self.assertNotIn("está acompanhando sua recepção", mensagem)
		self.assertIn("Grande abraço!", mensagem)


class TestInterruptoresDeMensagem(FrappeTestCase):
	"""Cada mensagem tem um Check próprio em Configurações de Recepção."""

	JOVEM_ACOLHIDA: ClassVar[dict] = {
		"name": "NA-1",
		"nome_completo": "Joãozinho Feliz",
		"sexo": "Masculino",
		"data_de_nascimento": "2014-09-01",
		"ramo": "Escoteiro",
		"data_lembrete_acolhida": None,
		"data_lembrete_pesquisa": None,
		"data_lembrete_ficha_medica": None,
		"data_lembrete_id_escoteiros": None,
		"dados_para_registro_enviados": 1,
		"tipo_de_registro": "Definitivo",
	}
	GRUPOS: ClassVar[dict] = {
		"grupo_chefes_secao_whatsapp": "120@g.us",
		"grupo_recepcao_whatsapp": "121@g.us",
	}

	# job -> (fieldname do Check, atributo do ambiente onde o envio aparece)
	JOBS: ClassVar[tuple] = (
		("enviar_lembretes_pesquisa_novos_associados", "msg_lembrete_pesquisa", "textos"),
		("enviar_lembretes_ficha_medica", "msg_lembrete_ficha_medica", "textos"),
		("enviar_lembretes_id_escoteiros", "msg_lembrete_id_escoteiros", "textos"),
		("enviar_lembretes_acolhida_lenco", "msg_acolhida", "grupos"),
	)

	def _rodar(self, job, configuracoes):
		with _AmbienteDeTeste(
			novos_associados=[dict(self.JOVEM_ACOLHIDA)],
			links=VINCULO_PADRAO,
			responsaveis=RESPONSAVEL_PADRAO,
			configuracoes={**self.GRUPOS, **configuracoes},
		) as ambiente:
			getattr(recepcao_mensagens, job)()

		return ambiente

	def test_check_desmarcado_suspende_o_job(self):
		for job, campo, canal in self.JOBS:
			with self.subTest(job=job):
				ambiente = self._rodar(job, {campo: 0})

				self.assertEqual(getattr(ambiente, canal), [])
				self.assertEqual(ambiente.atualizacoes, [])

	def test_check_marcado_deixa_enviar(self):
		for job, campo, canal in self.JOBS:
			with self.subTest(job=job):
				self.assertTrue(getattr(self._rodar(job, {campo: 1}), canal))

	def test_campo_ausente_conta_como_ligado(self):
		"""Site que nunca salvou o Single não tem a linha em tabSingles — e não pode emudecer."""
		for job, _campo, canal in self.JOBS:
			with self.subTest(job=job):
				self.assertTrue(getattr(self._rodar(job, {}), canal))

	def test_um_check_nao_derruba_os_outros(self):
		ambiente = self._rodar("enviar_lembretes_acolhida_lenco", {"msg_lembrete_id_escoteiros": 0})

		self.assertTrue(ambiente.grupos)

	def test_lembrete_de_dados_respeita_o_proprio_check(self):
		jovem = {
			"name": "NA-1",
			"nome_completo": "Joãozinho Feliz",
			"sexo": "Masculino",
			"responsavel_recepcao": None,
			"data_status_aguardar_dados": "2026-05-01",
			"data_lembrete_dados": None,
		}
		for valor, esperado in ((0, 0), (1, 1)):
			with self.subTest(msg_lembrete_dados=valor):
				with _AmbienteDeTeste(
					novos_associados=[dict(jovem)],
					links=VINCULO_PADRAO,
					responsaveis=RESPONSAVEL_PADRAO,
					configuracoes={"msg_lembrete_dados": valor},
				) as ambiente:
					recepcao_mensagens.enviar_lembretes_dados_registro()

				self.assertEqual(len(ambiente.textos), esperado)

	def test_desistencia_respeita_o_proprio_check(self):
		with _AmbienteDeTeste(configuracoes={**self.GRUPOS, "msg_desistencia": 0}) as ambiente:
			recepcao_mensagens.notificar_desistencia(nome_completo="Joãozinho", ramo="Escoteiro")

		self.assertEqual(ambiente.grupos, [])

	def test_visitas_do_dia_respeita_o_proprio_check(self):
		with _AmbienteDeTeste(configuracoes={**self.GRUPOS, "msg_visitas_do_dia": 0}) as ambiente:
			recepcao_mensagens.notificar_visitas_do_dia()

		self.assertEqual(ambiente.grupos, [])

	def test_helper_le_o_check_do_single(self):
		with _AmbienteDeTeste(configuracoes={"msg_acolhida": 0, "msg_desistencia": 1}):
			self.assertFalse(recepcao_mensagens._mensagem_habilitada("msg_acolhida"))
			self.assertTrue(recepcao_mensagens._mensagem_habilitada("msg_desistencia"))
			self.assertTrue(recepcao_mensagens._mensagem_habilitada("msg_inexistente"))


class TestAvisoDoNumeroDeRegistro(FrappeTestCase):
	"""O aviso com o número de registro e de onde ele tira o número.

	Ele é a porta das cobranças de ficha médica e id@escoteiros: enquanto dependia só do
	cadastro do ``Associado``, a família era cobrada antes de receber o número.
	"""

	JOVEM: ClassVar[dict] = {
		"name": "NA-1",
		"nome_completo": "Joãozinho Feliz",
		"sexo": "Masculino",
		"numero_de_registro": "",
		"tipo_de_registro": "Definitivo",
		"data_mensagem_registro_criado": None,
	}

	def _enviar(self, jovem=None, associado=None):
		valores = {
			"Novo Associado": frappe._dict({**self.JOVEM, **(jovem or {})}),
			"Associado": frappe._dict(associado) if associado else None,
		}
		contato = {"nome": "Maria Feliz", "sexo": "Feminino", "telefone": "5511999999999"}

		with _AmbienteDeTeste(links=VINCULO_PADRAO, responsaveis=RESPONSAVEL_PADRAO) as ambiente:
			with (
				patch.object(
					recepcao_mensagens.frappe.db,
					"get_value",
					side_effect=lambda doctype, *_a, **_k: valores.get(doctype),
				),
				patch.object(
					recepcao_mensagens,
					"_buscar_contatos_responsaveis",
					return_value={"NA-1": frappe._dict(contato)},
				),
			):
				recepcao_mensagens.notificar_registro_criado("NA-1")

		return ambiente

	def test_usa_o_numero_do_associado_quando_ele_existe(self):
		ambiente = self._enviar(associado={"registro": "123456", "tipo_registro": "Definitivo"})

		self.assertIn("123456", ambiente.textos[0]["mensagem"])

	def test_usa_o_numero_do_funil_quando_o_associado_ainda_nao_existe(self):
		"""A recepção informa o número no diálogo da visão geral antes de efetivar."""
		ambiente = self._enviar(jovem={"numero_de_registro": "654321"})

		self.assertIn("654321", ambiente.textos[0]["mensagem"])
		self.assertEqual(ambiente.atualizacoes[0]["fieldname"], "data_mensagem_registro_criado")

	def test_o_numero_do_associado_tem_precedencia(self):
		ambiente = self._enviar(
			jovem={"numero_de_registro": "654321"},
			associado={"registro": "123456", "tipo_registro": "Definitivo"},
		)

		self.assertIn("123456", ambiente.textos[0]["mensagem"])

	def test_sem_numero_em_lugar_nenhum_nao_envia(self):
		ambiente = self._enviar()

		self.assertEqual(ambiente.textos, [])

	def test_nao_repete_o_aviso_ja_carimbado(self):
		ambiente = self._enviar(
			jovem={"numero_de_registro": "654321", "data_mensagem_registro_criado": "2026-05-11"}
		)

		self.assertEqual(ambiente.textos, [])


class TestGatilhoDoNumeroDeRegistro(FrappeTestCase):
	"""``on_novo_associado_atualizado``: informar o número dispara o aviso."""

	def _rodar(self, antes, depois):
		doc = frappe._dict({"name": "NA-1", "flags": frappe._dict(), **depois})
		doc.get_doc_before_save = lambda: frappe._dict(antes)

		with patch.object(recepcao_mensagens.frappe, "enqueue") as enfileirar:
			recepcao_mensagens.on_novo_associado_atualizado(doc)

		return enfileirar

	def test_numero_preenchido_enfileira_o_aviso(self):
		enfileirar = self._rodar(
			{"primeira_visita_realizada": 0, "numero_de_registro": ""},
			{"primeira_visita_realizada": 0, "numero_de_registro": "123456"},
		)

		enfileirar.assert_called_once()
		self.assertEqual(enfileirar.call_args.kwargs["associado_name"], "NA-1")

	def test_numero_que_ja_estava_la_nao_reenvia(self):
		enfileirar = self._rodar(
			{"primeira_visita_realizada": 0, "numero_de_registro": "123456"},
			{"primeira_visita_realizada": 0, "numero_de_registro": "123456"},
		)

		enfileirar.assert_not_called()

	def test_numero_em_branco_nao_dispara(self):
		enfileirar = self._rodar(
			{"primeira_visita_realizada": 0, "numero_de_registro": None},
			{"primeira_visita_realizada": 0, "numero_de_registro": "   "},
		)

		enfileirar.assert_not_called()
