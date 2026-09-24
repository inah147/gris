# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Testes do Conselho de Responsáveis no organograma.

`montar_no_conselho` é pura e é testada direto. O resto cobre a estrutura fixa (área
raiz + função), a trava que impede a área de virar filha de outra e as duas regras da
função de Responsável Legal: ela fica enquanto houver beneficiário, e não exige Acordo
de Trabalho Voluntário.
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.gestao_adultos.atribuicoes import (
	apagar_funcao,
	atribuir_funcao,
	encerrar_funcao,
	listar_funcoes_da_pessoa,
)
from gris.api.gestao_adultos.atvs import listar_atvs, salvar_atv
from gris.api.gestao_adultos.identidade import chave_do_associado
from gris.api.gestao_adultos.organograma import obter_detalhe_do_adulto
from gris.api.gestao_adultos.responsaveis import (
	AREA_CONSELHO,
	FUNCAO_RESPONSAVEL_LEGAL,
	LINHA_RESPONSAVEL,
	PREFIXO_RESPONSAVEL,
	garantir_estrutura_do_conselho,
	montar_no_conselho,
)

PREFIXO = "ZZ Teste Conselho"

#: CPF fictício de quem tem os dois cadastros. Fixo para o `name` dos dois bater — é
#: justamente o que põe a pessoa no conselho pelo regime gravado.
CPF_DO_MISTO = "38000000001"


class TestMontarNoConselho(FrappeTestCase):
	"""Função pura: sem banco, sem fixture."""

	def test_sem_responsavel_nao_ha_no(self):
		self.assertIsNone(montar_no_conselho([]))

	def test_um_no_por_responsavel_em_ordem_de_nome(self):
		no = montar_no_conselho(
			[
				{"name": "b", "nome_completo": "Beatriz"},
				{"name": "a", "nome_completo": "Ana"},
			]
		)

		self.assertEqual(no["tipo"], "grupo")
		self.assertEqual(no["membros"], 2)
		self.assertEqual([filho["nome"] for filho in no["children"]], ["Ana", "Beatriz"])

	def test_o_grupo_nasce_recolhido(self):
		"""São mais de cem cards: abertos de saída, empurram o resto para fora da tela."""
		no = montar_no_conselho([{"name": "a", "nome_completo": "Ana"}])

		self.assertTrue(no["recolhido"])

	def test_a_chave_da_pessoa_tem_espaco_de_nomes(self):
		"""`Responsavel.name` e `Associado.name` são os dois md5 de CPF."""
		no = montar_no_conselho([{"name": "abc", "nome_completo": "Ana"}])

		filho = no["children"][0]
		self.assertEqual(filho["tipo_pessoa"], "responsavel")
		self.assertEqual(filho["pessoa"], f"{PREFIXO_RESPONSAVEL}abc")
		self.assertIsNone(filho["associado"])

	def test_todo_responsavel_tem_a_funcao_e_a_area_fixas(self):
		no = montar_no_conselho([{"name": "abc", "nome_completo": "Ana Maria Souza"}])

		filho = no["children"][0]
		self.assertEqual(filho["funcao_interna"], FUNCAO_RESPONSAVEL_LEGAL)
		self.assertEqual(filho["area"], AREA_CONSELHO)
		self.assertEqual(filho["linha"], LINHA_RESPONSAVEL)
		self.assertEqual(filho["iniciais"], "AS")

	def test_responsavel_sem_nome_cai_para_o_identificador(self):
		no = montar_no_conselho([{"name": "abc", "nome_completo": None}])

		self.assertEqual(no["children"][0]["nome"], "abc")


class TestEstruturaDoConselho(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_a_area_e_raiz_e_automatica(self):
		garantir_estrutura_do_conselho()

		area = frappe.db.get_value(
			"Unidade Organizacional",
			AREA_CONSELHO,
			["responde_para", "ativa", "origem_automatica"],
			as_dict=True,
		)
		self.assertIsNone(area.responde_para)
		self.assertTrue(area.ativa)
		self.assertTrue(area.origem_automatica)

	def test_a_funcao_existe_e_esta_vinculada_a_area(self):
		garantir_estrutura_do_conselho()

		self.assertTrue(frappe.db.exists("Funcao Voluntario", FUNCAO_RESPONSAVEL_LEGAL))
		self.assertTrue(
			frappe.db.exists(
				"Funcao da Area",
				{
					"parent": AREA_CONSELHO,
					"parenttype": "Unidade Organizacional",
					"funcao": FUNCAO_RESPONSAVEL_LEGAL,
				},
			)
		)

	def test_rodar_de_novo_nao_cria_nada(self):
		garantir_estrutura_do_conselho()

		self.assertEqual(garantir_estrutura_do_conselho(), {"area": 0, "funcao": 0, "vinculo": 0})

	def test_o_conselho_nao_pode_responder_para_outra_area(self):
		"""A tela de administração arrasta áreas; sem a trava, o conselho sai da raiz."""
		garantir_estrutura_do_conselho()
		outra = f"{PREFIXO} Diretoria"
		if not frappe.db.exists("Unidade Organizacional", outra):
			frappe.get_doc({"doctype": "Unidade Organizacional", "area": outra}).insert(
				ignore_permissions=True
			)

		doc = frappe.get_doc("Unidade Organizacional", AREA_CONSELHO)
		doc.responde_para = outra

		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)


class TestConselhoNoOrganograma(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_o_conselho_entra_como_raiz_propria(self):
		from gris.api.gestao_adultos.organograma import obter_organograma

		garantir_estrutura_do_conselho()
		self._criar_responsavel()

		arvore = obter_organograma()

		conselhos = [no for no in arvore["raizes"] if no.get("nome") == AREA_CONSELHO]
		self.assertEqual(len(conselhos), 1)
		self.assertGreaterEqual(conselhos[0]["membros"], 1)

	def test_filtrar_por_outra_area_esconde_o_conselho(self):
		from gris.api.gestao_adultos.organograma import obter_organograma

		garantir_estrutura_do_conselho()
		self._criar_responsavel("Filtrado")
		outra = f"{PREFIXO} Area"
		if not frappe.db.exists("Unidade Organizacional", outra):
			frappe.get_doc({"doctype": "Unidade Organizacional", "area": outra}).insert(
				ignore_permissions=True
			)

		arvore = obter_organograma(outra)

		self.assertEqual([no for no in arvore["raizes"] if no.get("nome") == AREA_CONSELHO], [])

	def test_detalhe_do_responsavel_traz_a_funcao_automatica_do_conselho(self):
		from gris.api.gestao_adultos.responsaveis import obter_detalhe_do_responsavel

		nome = self._criar_responsavel("Detalhe")

		detalhe = obter_detalhe_do_responsavel(nome)

		self.assertEqual(detalhe["funcao_principal"], FUNCAO_RESPONSAVEL_LEGAL)
		self.assertEqual(detalhe["areas"], [AREA_CONSELHO])
		# A ficha do responsável existe desde que ele passou a poder receber função.
		self.assertTrue(detalhe["permite_ficha"])
		self.assertIn(nome, detalhe["ficha_url"])

		conselho = detalhe["funcoes"][0]
		self.assertTrue(conselho["automatica"])
		# Sem `linha` não há registro por trás: é o que impede encerrar, editar ou apagar.
		self.assertIsNone(conselho["linha"])
		self.assertIsNone(conselho["atv"])

	def test_detalhe_de_quem_nao_existe_e_recusado(self):
		from gris.api.gestao_adultos.responsaveis import obter_detalhe_do_responsavel

		with self.assertRaises(frappe.DoesNotExistError):
			obter_detalhe_do_responsavel("nao-existe")

	def test_os_dois_regimes_cabem_no_mesmo_no(self):
		"""Quem é associado entra pela linha gravada; quem só é responsável, derivado.

		Os dois no mesmo nó: dois grupos com o mesmo `id` fariam a interface marcar o card
		errado e a área apareceria duas vezes na tela.
		"""
		from gris.api.gestao_adultos.organograma import obter_organograma

		garantir_estrutura_do_conselho()
		self._criar_responsavel("Puro")
		associado = self._criar_associado_responsavel("Misto")

		arvore = obter_organograma()

		conselhos = [no for no in arvore["raizes"] if no.get("nome") == AREA_CONSELHO]
		self.assertEqual(len(conselhos), 1)

		filhos = conselhos[0]["children"]
		self.assertTrue(conselhos[0]["recolhido"])
		self.assertEqual(len(filhos), len({filho["id"] for filho in filhos}))
		self.assertEqual(conselhos[0]["membros"], len(filhos))
		self.assertEqual({filho["tipo_pessoa"] for filho in filhos}, {"responsavel", "associado"})
		self.assertIn(associado, [filho["associado"] for filho in filhos if filho["associado"]])

		# E a pessoa migrada entra uma vez só, pelo lado do associado.
		derivados = [filho["responsavel"] for filho in filhos if filho["tipo_pessoa"] == "responsavel"]
		self.assertNotIn(associado, derivados)

	def _criar_associado_responsavel(self, sufixo, cpf=CPF_DO_MISTO):
		"""Pessoa com os dois cadastros e um beneficiário — vai para o conselho gravada."""
		from gris.api.pessoas import vincular_responsavel_ao_associado

		associado = frappe.get_doc(
			{
				"doctype": "Associado",
				"nome_completo": f"{PREFIXO} {sufixo}",
				"cpf": cpf,
				"data_de_nascimento": "1985-01-01",
				"categoria": "Dirigente",
				"status_no_grupo": "Ativo",
				"historico_no_grupo": [{"data_de_ingresso": "2020-01-01"}],
			}
		)
		associado.insert(ignore_permissions=True)

		responsavel = frappe.get_doc(
			{"doctype": "Responsavel", "nome_completo": f"{PREFIXO} {sufixo}", "cpf": cpf}
		)
		responsavel.insert(ignore_permissions=True)

		frappe.get_doc(
			{
				"doctype": "Responsavel Vinculo",
				"responsavel": responsavel.name,
				"beneficiario_associado": associado.name,
			}
		).insert(ignore_permissions=True)

		vincular_responsavel_ao_associado(responsavel.name)
		return associado.name

	def _criar_responsavel(self, sufixo="Pessoa"):
		doc = frappe.get_doc(
			{
				"doctype": "Responsavel",
				"nome_completo": f"{PREFIXO} {sufixo}",
				"cpf": frappe.generate_hash(length=11),
				"celular": "11999990000",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name


class TestFuncaoObrigatoriaDoConselho(FrappeTestCase):
	"""A função de Responsável Legal não é alocação: ela acompanha o vínculo.

	Quem responde por um beneficiário tem de aparecer no Conselho, então nem a tela nem a
	grade do Desk podem tirar a linha de lá. O que a encerra é perder o último vínculo, e
	isso quem faz é `gris.api.pessoas`.
	"""

	def setUp(self):
		garantir_estrutura_do_conselho()
		self.associado = _criar_associado_com_vinculo("Obrigatoria")
		self.linha = _linha_do_conselho(self.associado)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _payload(self, **kwargs):
		kwargs.setdefault("pessoa", chave_do_associado(self.associado))
		return json.dumps(kwargs)

	# ------------------------------------------------------------------
	# Não pode ser excluída
	# ------------------------------------------------------------------

	def test_a_linha_nasce_com_o_vinculo(self):
		self.assertIsNotNone(self.linha)
		self.assertEqual(self.linha["area"], AREA_CONSELHO)
		self.assertEqual(self.linha["funcao"], FUNCAO_RESPONSAVEL_LEGAL)

	def test_apagar_e_recusado_enquanto_houver_beneficiario(self):
		with self.assertRaises(frappe.ValidationError):
			apagar_funcao(self._payload(linha=self.linha["linha"]))

		self.assertIsNotNone(_linha_do_conselho(self.associado))

	def test_encerrar_e_recusado_enquanto_houver_beneficiario(self):
		with self.assertRaises(frappe.ValidationError):
			encerrar_funcao(self._payload(linha=self.linha["linha"]))

		self.assertIsNone(_linha_do_conselho(self.associado)["data_fim"])

	def test_tirar_a_linha_na_grade_do_desk_tambem_e_recusado(self):
		"""A regra mora no controller, não só nos endpoints do portal."""
		doc = frappe.get_doc("Associado", self.associado)
		doc.funcoes_internas = [linha for linha in doc.funcoes_internas if linha.area != AREA_CONSELHO]

		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_encerrar_pela_grade_do_desk_tambem_e_recusado(self):
		from frappe.utils import getdate, nowdate

		doc = frappe.get_doc("Associado", self.associado)
		for linha in doc.funcoes_internas:
			if linha.area == AREA_CONSELHO:
				linha.data_fim = getdate(nowdate())

		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_sem_beneficiario_a_funcao_e_encerrada_sozinha_e_liberada(self):
		"""Perder o último vínculo é o caminho legítimo — e ele encerra, não apaga."""
		frappe.delete_doc(
			"Responsavel Vinculo",
			frappe.db.get_value("Responsavel Vinculo", {"responsavel": self.associado}, "name"),
			ignore_permissions=True,
		)

		encerrada = _linha_do_conselho(self.associado)
		self.assertIsNotNone(encerrada["data_fim"], "o vínculo saiu: a função tem de fechar")

		# E, encerrada, a linha volta a ser histórico comum — dá para apagar o lançamento.
		apagar_funcao(self._payload(linha=encerrada["linha"]))
		self.assertIsNone(_linha_do_conselho(self.associado))

	# ------------------------------------------------------------------
	# Não exige ATV
	# ------------------------------------------------------------------

	def test_a_funcao_do_conselho_nao_cobra_acordo(self):
		self.assertIsNone(self.linha["atv"], "responsável legal não assina ATV")
		self.assertTrue(self.linha["automatica"])

	def test_as_outras_funcoes_continuam_cobrando(self):
		"""O recorte é do par função+área, não da pessoa."""
		area, funcao = _area_com_funcao("Quadro")
		atribuir_funcao(self._payload(area=area, funcao=funcao))

		alocada = next(
			linha
			for linha in listar_funcoes_da_pessoa(chave_do_associado(self.associado))
			if linha["area"] == area
		)
		self.assertEqual(alocada["atv"]["situacao"], "sem_atv")
		self.assertFalse(alocada["automatica"])

	def test_a_funcao_do_conselho_fica_fora_da_tela_de_cobranca(self):
		linhas = [item for item in listar_atvs() if item["associado"] == self.associado]

		self.assertEqual([item["area"] for item in linhas if item["area"] == AREA_CONSELHO], [])

	def test_cadastrar_acordo_para_a_funcao_do_conselho_e_recusado(self):
		with self.assertRaises(frappe.ValidationError):
			salvar_atv(
				json.dumps(
					{
						"associado": self.associado,
						"linha": self.linha["linha"],
						"data_inicio": "2026-01-01",
						"data_fim": "2026-12-31",
					}
				)
			)

	def test_o_painel_do_organograma_nao_mostra_pendencia(self):
		detalhe = obter_detalhe_do_adulto(self.associado)

		conselho = next(f for f in detalhe["funcoes"] if f["area"] == AREA_CONSELHO)
		self.assertIsNone(conselho["atv"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _criar_associado_com_vinculo(sufixo: str) -> str:
	"""Pessoa com os dois cadastros e um beneficiário: entra no conselho pela linha gravada."""
	from gris.api.pessoas import vincular_responsavel_ao_associado

	cpf = frappe.generate_hash(length=11)
	associado = frappe.get_doc(
		{
			"doctype": "Associado",
			"nome_completo": f"{PREFIXO} {sufixo}",
			"cpf": cpf,
			"data_de_nascimento": "1985-01-01",
			"categoria": "Dirigente",
			"status_no_grupo": "Ativo",
			"historico_no_grupo": [{"data_de_ingresso": "2020-01-01"}],
		}
	)
	associado.insert(ignore_permissions=True)

	responsavel = frappe.get_doc(
		{"doctype": "Responsavel", "nome_completo": f"{PREFIXO} {sufixo}", "cpf": cpf}
	)
	responsavel.insert(ignore_permissions=True)

	frappe.get_doc(
		{
			"doctype": "Responsavel Vinculo",
			"responsavel": responsavel.name,
			"beneficiario_associado": associado.name,
		}
	).insert(ignore_permissions=True)

	vincular_responsavel_ao_associado(responsavel.name)
	return associado.name


def _linha_do_conselho(associado: str) -> dict | None:
	return next(
		(
			linha
			for linha in listar_funcoes_da_pessoa(chave_do_associado(associado))
			if linha["area"] == AREA_CONSELHO
		),
		None,
	)


def _area_com_funcao(sufixo: str) -> tuple[str, str]:
	area = f"{PREFIXO} Area {sufixo}"
	funcao = f"{PREFIXO} Funcao {sufixo}"
	if not frappe.db.exists("Funcao Voluntario", funcao):
		frappe.get_doc(
			{"doctype": "Funcao Voluntario", "titulo": funcao, "categoria": "Colaborador", "ativa": 1}
		).insert(ignore_permissions=True)
	if not frappe.db.exists("Unidade Organizacional", area):
		frappe.get_doc(
			{"doctype": "Unidade Organizacional", "area": area, "funcoes": [{"funcao": funcao}]}
		).insert(ignore_permissions=True)
	return area, funcao
