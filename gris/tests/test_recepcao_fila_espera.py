"""Fila de espera: ordem manual, histórico de passagens e volta ao status de origem.

Cenários cobertos:
1. Entrar na fila grava a passagem aberta com o status de origem e põe o jovem no fim do ramo
2. Chamar devolve o jovem ao status em que estava ao entrar, com as etapas intactas
3. Quem entrou antes de o status de origem ser gravado volta para o status das etapas
4. Sair da fila pelo status (caminho do Desk) fecha a passagem e apaga a entrada
5. Reordenar grava a posição; lista que não bate com a fila é recusada
6. Reordenar exige permissão de escrita na fila
7. A página e o MCP leem a fila na ordem gravada
"""

from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api import recepcao, recepcao_fila
from gris.api.mcp import recepcao as mcp_recepcao
from gris.utils.documento import formatar_cpf
from gris.www.recepcao import fila_espera


def _gerar_cpf(base9: str) -> str:
	"""CPF fictício com dígitos verificadores corretos, a partir de 9 dígitos."""
	digitos = [int(d) for d in base9]
	for posicao in (9, 10):
		soma = sum(d * (posicao + 1 - i) for i, d in enumerate(digitos))
		resto = 11 - (soma % 11)
		digitos.append(0 if resto >= 10 else resto)
	return "".join(str(d) for d in digitos)


# CPFs exclusivos deste módulo, para não colidir com os dos outros testes.
CPF_ANA = _gerar_cpf("314159265")
CPF_BRUNO = _gerar_cpf("271828182")
CPF_CARLA = _gerar_cpf("161803398")

EMAIL_SEM_PAPEL = "estranho.fila@example.com"


def _criar_novo_associado(cpf: str, nome: str, **campos) -> frappe._dict:
	dados = {
		"doctype": "Novo Associado",
		"cpf": formatar_cpf(cpf),
		"nome_completo": nome,
		"data_de_nascimento": "2017-03-10",
		"status": "Conversa Inicial",
		"tipo_de_registro": "Definitivo",
	}
	dados.update(campos)
	doc = frappe.get_doc(dados)
	doc.insert(ignore_permissions=True)
	return doc


def _entrada_da_fila(associado: str) -> str | None:
	return frappe.db.get_value("Fila de Espera", {"associado": associado}, "name")


class _BaseDaFila(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		# Saves do Novo Associado podem enfileirar mensagens; aqui só importa a fila.
		mock.patch.object(frappe, "enqueue").start()
		self.addCleanup(mock.patch.stopall)

	def tearDown(self):
		frappe.set_user("Administrator")
		# FrappeTestCase só desfaz no fim da classe: sem isto o CPF do setUp colide no
		# próximo teste.
		frappe.db.rollback()


class TestEntradaESaidaDaFila(_BaseDaFila):
	def test_entrar_grava_status_de_origem_e_vai_para_o_fim_do_ramo(self):
		ana = _criar_novo_associado(CPF_ANA, "Ana Fila", status="Aguardar Dados", primeira_visita_realizada=1)
		fim_antes = recepcao_fila.proxima_posicao(ana.ramo)

		recepcao.enviar_para_fila_espera(ana.name)

		ana.reload()
		self.assertEqual(ana.status, recepcao_fila.STATUS_FILA)
		self.assertEqual(len(ana.historico_fila_de_espera), 1)
		passagem = ana.historico_fila_de_espera[0]
		self.assertEqual(passagem.status_anterior, "Aguardar Dados")
		self.assertTrue(passagem.entrada_em)
		self.assertFalse(passagem.saida_em)

		entrada = _entrada_da_fila(ana.name)
		self.assertEqual(frappe.db.get_value("Fila de Espera", entrada, "posicao"), fim_antes)

	def test_entrar_de_novo_quem_ja_esta_na_fila_e_recusado(self):
		ana = _criar_novo_associado(CPF_ANA, "Ana Fila")
		recepcao.enviar_para_fila_espera(ana.name)

		with self.assertRaises(frappe.ValidationError):
			recepcao.enviar_para_fila_espera(ana.name)

		self.assertEqual(frappe.db.count("Fila de Espera", {"associado": ana.name}), 1)

	def test_entra_na_fila_de_qualquer_etapa_ate_o_acompanhamento_provisorio(self):
		etapas = {
			"visita_agendada": 1,
			"primeira_visita_realizada": 1,
			"dados_para_registro_enviados": 1,
			"registro_criado_no_paxtu": 1,
		}
		casos = (
			("Novo Contato", {}),
			("Visita Agendada", {"visita_agendada": 1}),
			("Fazer Registro", {"visita_agendada": 1, "primeira_visita_realizada": 1}),
			# Provisório ainda não efetivado: lista "Acompanhamento Provisório".
			("Acompanhamento", {**etapas, "tipo_de_registro": "Provisório"}),
		)
		for status, campos in casos:
			with self.subTest(status=status):
				ana = _criar_novo_associado(CPF_ANA, "Ana Fila", status=status, **campos)
				recepcao.enviar_para_fila_espera(ana.name)

				ana.reload()
				self.assertEqual(ana.status, recepcao_fila.STATUS_FILA)
				fila_espera.chamar_associado(_entrada_da_fila(ana.name))
				ana.reload()
				self.assertEqual(ana.status, status)
				frappe.db.rollback()

	def test_acompanhamento_definitivo_e_final_nao_entram_na_fila(self):
		etapas = {
			"visita_agendada": 1,
			"primeira_visita_realizada": 1,
			"dados_para_registro_enviados": 1,
			"registro_criado_no_paxtu": 1,
		}
		casos = (
			("Acompanhamento Definitivo", {**etapas, "tipo_de_registro": "Definitivo"}),
			(
				"Acompanhamento Definitivo",
				{
					**etapas,
					"tipo_de_registro": "Provisório",
					"boleto_provisorio_gerado": 1,
					"registro_provisorio_efetivado": 1,
					"numero_de_registro": "123",
				},
			),
			(
				"Acompanhamento Final",
				{
					**etapas,
					"boleto_definitivo_gerado": 1,
					"registro_definitivo_efetivado": 1,
					"numero_de_registro": "123",
				},
			),
		)
		for coluna, campos in casos:
			with self.subTest(coluna=coluna, campos=campos):
				ana = _criar_novo_associado(CPF_ANA, "Ana Fila", status="Acompanhamento", **campos)

				with self.assertRaises(frappe.ValidationError):
					recepcao.enviar_para_fila_espera(ana.name)

				self.assertEqual(frappe.db.get_value("Novo Associado", ana.name, "status"), "Acompanhamento")
				self.assertIsNone(_entrada_da_fila(ana.name))
				frappe.db.rollback()

	def test_chamar_volta_para_aguardar_dados_com_as_etapas_marcadas(self):
		ana = _criar_novo_associado(
			CPF_ANA,
			"Ana Fila",
			status="Aguardar Dados",
			visita_agendada=1,
			primeira_visita_realizada=1,
		)
		recepcao.enviar_para_fila_espera(ana.name)

		destino = fila_espera.chamar_associado(_entrada_da_fila(ana.name))

		self.assertEqual(destino, {"status": "Aguardar Dados"})
		ana.reload()
		self.assertEqual(ana.status, "Aguardar Dados")
		self.assertEqual(ana.visita_agendada, 1)
		self.assertEqual(ana.primeira_visita_realizada, 1)
		self.assertIsNone(_entrada_da_fila(ana.name))

		passagem = ana.historico_fila_de_espera[0]
		self.assertTrue(passagem.saida_em)
		self.assertEqual(passagem.status_posterior, "Aguardar Dados")

	def test_chamar_volta_para_conversa_inicial(self):
		bruno = _criar_novo_associado(CPF_BRUNO, "Bruno Fila", status="Conversa Inicial")
		recepcao.enviar_para_fila_espera(bruno.name)

		fila_espera.chamar_associado(_entrada_da_fila(bruno.name))

		self.assertEqual(frappe.db.get_value("Novo Associado", bruno.name, "status"), "Conversa Inicial")

	def test_cada_passagem_tem_sua_linha(self):
		ana = _criar_novo_associado(CPF_ANA, "Ana Fila", status="Conversa Inicial")
		recepcao.enviar_para_fila_espera(ana.name)
		fila_espera.chamar_associado(_entrada_da_fila(ana.name))

		ana.reload()
		ana.status = "Visita Agendada"
		ana.visita_agendada = 1
		ana.save()
		recepcao.enviar_para_fila_espera(ana.name)

		ana.reload()
		passagens = sorted(ana.historico_fila_de_espera, key=lambda linha: linha.idx)
		self.assertEqual(
			[(p.status_anterior, p.status_posterior or None) for p in passagens],
			[("Conversa Inicial", "Conversa Inicial"), ("Visita Agendada", None)],
		)
		self.assertEqual(recepcao_fila.status_de_retorno(ana), "Visita Agendada")

	def test_sem_status_de_origem_volta_para_o_status_das_etapas(self):
		carla = _criar_novo_associado(
			CPF_CARLA,
			"Carla Fila",
			status="Conversa Inicial",
			visita_agendada=1,
			primeira_visita_realizada=1,
		)
		recepcao.enviar_para_fila_espera(carla.name)
		# Como o patch deixa quem já estava na fila: passagem aberta sem status de origem.
		frappe.db.set_value(
			"Passagem pela Fila de Espera",
			{"parent": carla.name},
			"status_anterior",
			"",
		)

		fila_espera.chamar_associado(_entrada_da_fila(carla.name))

		self.assertEqual(frappe.db.get_value("Novo Associado", carla.name, "status"), "Aguardar Dados")

	def test_sair_da_fila_pelo_status_fecha_a_passagem_e_apaga_a_entrada(self):
		ana = _criar_novo_associado(CPF_ANA, "Ana Fila", status="Conversa Inicial")
		recepcao.enviar_para_fila_espera(ana.name)

		ana.reload()
		ana.status = "Visita Agendada"
		ana.save()

		ana.reload()
		self.assertIsNone(_entrada_da_fila(ana.name))
		self.assertEqual(ana.historico_fila_de_espera[0].status_posterior, "Visita Agendada")

	def test_historico_formatado_marca_passagem_aberta(self):
		ana = _criar_novo_associado(CPF_ANA, "Ana Fila", status="Conversa Inicial")
		recepcao.enviar_para_fila_espera(ana.name)

		historico = recepcao_fila.historico_por_associado([ana.name])[ana.name]

		self.assertEqual(len(historico), 1)
		self.assertTrue(historico[0]["aberta"])
		self.assertEqual(historico[0]["saida_em"], recepcao_fila.ROTULO_NA_FILA)
		self.assertEqual(historico[0]["status_anterior"], "Conversa Inicial")


class TestOrdemDaFila(_BaseDaFila):
	def setUp(self):
		super().setUp()
		self.ana = _criar_novo_associado(CPF_ANA, "Ana Fila")
		self.bruno = _criar_novo_associado(CPF_BRUNO, "Bruno Fila")
		self.carla = _criar_novo_associado(CPF_CARLA, "Carla Fila")
		for jovem in (self.ana, self.bruno, self.carla):
			recepcao.enviar_para_fila_espera(jovem.name)
		self.ramo = self.ana.ramo

	def _ordem_atual(self):
		return frappe.get_all(
			"Fila de Espera",
			filters={"ramo": self.ramo},
			order_by=recepcao_fila.ORDEM_DA_FILA,
			pluck="name",
		)

	def test_reordenar_grava_a_ordem_nova(self):
		ordem = self._ordem_atual()
		carla = _entrada_da_fila(self.carla.name)
		nova = [carla, *[nome for nome in ordem if nome != carla]]

		fila_espera.reordenar_fila(self.ramo, frappe.as_json(nova))

		self.assertEqual(self._ordem_atual(), nova)
		self.assertEqual(frappe.db.get_value("Fila de Espera", carla, "posicao"), 1)

	def test_lista_incompleta_e_recusada(self):
		ordem = self._ordem_atual()

		with self.assertRaises(frappe.ValidationError):
			fila_espera.reordenar_fila(self.ramo, frappe.as_json(ordem[1:]))

		self.assertEqual(self._ordem_atual(), ordem)

	def test_entrada_de_outro_ramo_e_recusada(self):
		outro_ramo = next(ramo for ramo in ("Lobinho", "Escoteiro") if ramo != self.ramo)

		with self.assertRaises(frappe.ValidationError):
			fila_espera.reordenar_fila(outro_ramo, frappe.as_json(self._ordem_atual()))

	def test_sem_permissao_nao_reordena(self):
		if not frappe.db.exists("User", EMAIL_SEM_PAPEL):
			user = frappe.new_doc("User")
			user.email = EMAIL_SEM_PAPEL
			user.first_name = "Sem Papel Fila"
			user.send_welcome_email = 0
			user.insert(ignore_permissions=True)

		frappe.set_user(EMAIL_SEM_PAPEL)
		with self.assertRaises(frappe.PermissionError):
			fila_espera.reordenar_fila(self.ramo, frappe.as_json(list(reversed(self._ordem_atual()))))

	def test_sem_permissao_nao_chama(self):
		if not frappe.db.exists("User", EMAIL_SEM_PAPEL):
			user = frappe.new_doc("User")
			user.email = EMAIL_SEM_PAPEL
			user.first_name = "Sem Papel Fila"
			user.send_welcome_email = 0
			user.insert(ignore_permissions=True)

		entrada = _entrada_da_fila(self.ana.name)
		frappe.set_user(EMAIL_SEM_PAPEL)
		with self.assertRaises(frappe.PermissionError):
			fila_espera.chamar_associado(entrada)

		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Novo Associado", self.ana.name, "status"), "Fila de espera")

	def test_pagina_e_mcp_seguem_a_ordem_gravada(self):
		nova = list(reversed(self._ordem_atual()))
		fila_espera.reordenar_fila(self.ramo, frappe.as_json(nova))

		contexto = frappe._dict()
		with mock.patch.object(fila_espera, "enrich_context"):
			fila_espera.get_context(contexto)
		na_pagina = [card.name for card in contexto.kanban_data[self.ramo]]
		# A página só mostra quem tem cadastro; a ordem relativa tem de ser a gravada.
		self.assertEqual(na_pagina, [nome for nome in nova if nome in na_pagina])
		self.assertEqual(
			[card.posicao for card in contexto.kanban_data[self.ramo]][: len(na_pagina)],
			list(range(1, len(na_pagina) + 1)),
		)
		carla = next(card for card in contexto.kanban_data[self.ramo] if card.associado == self.carla.name)
		self.assertEqual(carla.status_retorno, "Conversa Inicial")

		no_mcp = [linha["name"] for linha in mcp_recepcao.listar_fila_espera(self.ramo)["fila"]]
		self.assertEqual(no_mcp, nova)
