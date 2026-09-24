# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Funções do organograma alocadas a um `Responsavel`.

O responsável ganhou a mesma grade `funcoes_internas` do associado, com o mesmo child
DocType e `parenttype` diferente. O que está sob teste é o que essa segunda grade exigiu:
os endpoints passarem a endereçar a pessoa por chave com espaço de nomes, a montagem da
árvore aceitar dois tipos de pessoa, e o acordo de trabalho continuar sendo coisa só do
quadro de associados.

O cenário decisivo é o do homônimo: `Responsavel.name` e `Associado.name` são os dois md5
de CPF, então uma alocação endereçada pelo nome cru gravaria na grade da pessoa errada
sem erro nenhum.

A segunda parte cobre a liderança de área: `Unidade Organizacional.responsavel` virou
Dynamic Link e aceita os dois cadastros, então o par (tipo, nome) passou a ser o que
identifica o líder.
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate, nowdate

from gris.api.administracao.consultas import listar_unidades, opcoes_de_responsavel
from gris.api.administracao.endpoints import salvar_unidade
from gris.api.gestao_adultos.atribuicoes import (
	apagar_funcao,
	atribuir_funcao,
	encerrar_funcao,
	listar_funcoes_da_pessoa,
	listar_funcoes_do_associado,
)
from gris.api.gestao_adultos.identidade import chave_do_associado, chave_do_responsavel
from gris.api.gestao_adultos.organograma import obter_organograma
from gris.api.gestao_adultos.responsaveis import (
	AREA_CONSELHO,
	FUNCAO_RESPONSAVEL_LEGAL,
	garantir_estrutura_do_conselho,
	obter_detalhe_do_responsavel,
)

PREFIXO = "ZZ Teste Funcao Resp"

#: CPF fictício do par homônimo: o mesmo número gera o mesmo `name` nos dois DocTypes.
CPF_HOMONIMO = "37000000001"

#: Outro par homônimo, para os testes de liderança de área.
CPF_DO_LIDER = "37000000002"


class TestFuncoesDoResponsavel(FrappeTestCase):
	def setUp(self):
		self.area = _criar_area("Area")
		self.area_vazia = _criar_area("Area Vazia")
		self.funcao = _criar_funcao("Apoio")
		_vincular(self.area, self.funcao)
		self.responsavel = _criar_responsavel("Pessoa", CPF_HOMONIMO)

	def tearDown(self):
		frappe.db.rollback()

	def _payload(self, **kwargs):
		kwargs.setdefault("pessoa", chave_do_responsavel(self.responsavel))
		return json.dumps(kwargs)

	# ------------------------------------------------------------------
	# Alocação
	# ------------------------------------------------------------------

	def test_atribuir_funcao_a_um_responsavel(self):
		atribuir_funcao(self._payload(area=self.area, funcao=self.funcao))

		linhas = listar_funcoes_da_pessoa(chave_do_responsavel(self.responsavel))
		self.assertEqual(len(linhas), 1)
		self.assertEqual(linhas[0]["area"], self.area)
		self.assertEqual(linhas[0]["funcao"], self.funcao)
		self.assertEqual(linhas[0]["data_inicio"], getdate(nowdate()).isoformat())

	def test_a_linha_grava_na_grade_do_responsavel(self):
		atribuir_funcao(self._payload(area=self.area, funcao=self.funcao))

		linhas = frappe.get_all(
			"Funcao do Associado",
			filters={"parent": self.responsavel, "parenttype": "Responsavel"},
			pluck="name",
		)
		self.assertEqual(len(linhas), 1)

	def test_nao_grava_na_ficha_do_associado_homonimo(self):
		"""O cenário que a chave com espaço de nomes existe para impedir."""
		associado = _criar_associado("Homonimo", CPF_HOMONIMO)
		self.assertEqual(associado, self.responsavel, "o par precisa mesmo ser homônimo")

		atribuir_funcao(self._payload(area=self.area, funcao=self.funcao))

		self.assertEqual(listar_funcoes_do_associado(associado), [])
		self.assertEqual(len(listar_funcoes_da_pessoa(chave_do_responsavel(self.responsavel))), 1)

	def test_payload_antigo_continua_endereçando_o_associado(self):
		associado = _criar_associado("Antigo")

		atribuir_funcao(json.dumps({"associado": associado, "area": self.area, "funcao": self.funcao}))

		self.assertEqual(len(listar_funcoes_do_associado(associado)), 1)
		self.assertEqual(listar_funcoes_da_pessoa(chave_do_associado(associado))[0]["area"], self.area)

	def test_par_sem_vinculo_e_barrado_tambem_para_responsavel(self):
		"""A validação saiu do controller do Associado e vale para os dois."""
		with self.assertRaises(frappe.ValidationError):
			atribuir_funcao(self._payload(area=self.area_vazia, funcao=self.funcao))

	def test_o_mesmo_par_duas_vezes_e_barrado(self):
		atribuir_funcao(self._payload(area=self.area, funcao=self.funcao))

		with self.assertRaises(frappe.ValidationError):
			atribuir_funcao(self._payload(area=self.area, funcao=self.funcao))

	def test_encerrar_mantem_a_linha_no_historico(self):
		atribuir_funcao(self._payload(area=self.area, funcao=self.funcao))
		linha = listar_funcoes_da_pessoa(chave_do_responsavel(self.responsavel))[0]["linha"]

		encerrar_funcao(self._payload(linha=linha))

		linhas = listar_funcoes_da_pessoa(chave_do_responsavel(self.responsavel))
		self.assertEqual(len(linhas), 1, "encerrar preserva o histórico; apagar é o outro caminho")
		# Encerrada em hoje ainda conta como em vigor — mesmo corte de `lotacoes_atuais`.
		self.assertEqual(linhas[0]["data_fim"], getdate(nowdate()).isoformat())

	def test_apagar_remove_a_linha(self):
		atribuir_funcao(self._payload(area=self.area, funcao=self.funcao))
		linha = listar_funcoes_da_pessoa(chave_do_responsavel(self.responsavel))[0]["linha"]

		apagar_funcao(self._payload(linha=linha))

		self.assertEqual(listar_funcoes_da_pessoa(chave_do_responsavel(self.responsavel)), [])

	# ------------------------------------------------------------------
	# Acordo de trabalho voluntário
	# ------------------------------------------------------------------

	def test_responsavel_nao_tem_pendencia_de_atv(self):
		"""ATV é documento do quadro; cobrar um do responsável seria pendência insolúvel."""
		atribuir_funcao(self._payload(area=self.area, funcao=self.funcao))

		linha = listar_funcoes_da_pessoa(chave_do_responsavel(self.responsavel))[0]
		self.assertIsNone(linha["atv"])

	# ------------------------------------------------------------------
	# Organograma
	# ------------------------------------------------------------------

	def test_o_responsavel_alocado_aparece_na_area(self):
		atribuir_funcao(self._payload(area=self.area, funcao=self.funcao))

		arvore = obter_organograma()
		cards = _cards_da_area(arvore, self.area)

		self.assertIn(self.responsavel, [card["responsavel"] for card in cards])
		card = next(card for card in cards if card["responsavel"] == self.responsavel)
		self.assertEqual(card["tipo_pessoa"], "responsavel")
		self.assertIsNone(card["associado"])
		self.assertEqual(card["pessoa"], chave_do_responsavel(self.responsavel))

	def test_a_funcao_acumula_com_o_conselho(self):
		"""Alocar não tira ninguém do Conselho — é acúmulo, não troca."""
		garantir_estrutura_do_conselho()
		atribuir_funcao(self._payload(area=self.area, funcao=self.funcao))

		arvore = obter_organograma()

		na_area = [card["responsavel"] for card in _cards_da_area(arvore, self.area)]
		no_conselho = [card["responsavel"] for card in _cards_da_area(arvore, AREA_CONSELHO)]
		self.assertIn(self.responsavel, na_area)
		self.assertIn(self.responsavel, no_conselho)

	def test_responsavel_sem_funcao_nao_entra_no_quadro(self):
		"""Senão a centena de responsáveis do cadastro inundaria o desenho."""
		arvore = obter_organograma()

		self.assertEqual(_cards_da_area(arvore, self.area), [])

	def test_detalhe_junta_a_funcao_alocada_com_a_do_conselho(self):
		garantir_estrutura_do_conselho()
		atribuir_funcao(self._payload(area=self.area, funcao=self.funcao))

		detalhe = obter_detalhe_do_responsavel(self.responsavel)

		titulos = [funcao["titulo"] for funcao in detalhe["funcoes"]]
		self.assertIn(FUNCAO_RESPONSAVEL_LEGAL, titulos)
		self.assertIn(self.funcao, titulos)
		# A principal do painel é o que a pessoa faz no quadro, não o pano de fundo.
		self.assertEqual(detalhe["funcao_principal"], self.funcao)
		self.assertIn(self.area, detalhe["areas"])


class TestResponsavelLiderDeArea(FrappeTestCase):
	"""O responsável legal também pode liderar uma área, não só o associado."""

	def setUp(self):
		self.area = _criar_area("Area Liderada")
		self.funcao = _criar_funcao("Apoio")
		_vincular(self.area, self.funcao)
		self.responsavel = _criar_responsavel("Lider", CPF_DO_LIDER)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _definir_lider(self, pessoa: str) -> None:
		# O endpoint substitui o registro inteiro, então as funções da área viajam junto.
		salvar_unidade(
			json.dumps(
				{
					"name": self.area,
					"area": self.area,
					"responsavel": pessoa,
					"funcoes": [{"funcao": self.funcao}],
				}
			)
		)

	# ------------------------------------------------------------------
	# Gravação
	# ------------------------------------------------------------------

	def test_a_area_grava_o_par_tipo_e_nome(self):
		self._definir_lider(chave_do_responsavel(self.responsavel))

		area = frappe.db.get_value(
			"Unidade Organizacional", self.area, ["responsavel", "tipo_responsavel"], as_dict=True
		)
		self.assertEqual(area.responsavel, self.responsavel)
		self.assertEqual(area.tipo_responsavel, "Responsavel")

	def test_a_leitura_devolve_o_lider_como_chave(self):
		"""É o mesmo valor das opções do seletor — sem o prefixo, o homônimo entraria."""
		self._definir_lider(chave_do_responsavel(self.responsavel))

		unidade = next(u for u in listar_unidades() if u["name"] == self.area)
		self.assertEqual(unidade["responsavel"], chave_do_responsavel(self.responsavel))
		self.assertEqual(unidade["responsavel_nome"], f"{PREFIXO} Lider")

	def test_o_seletor_lista_os_dois_tipos_de_pessoa(self):
		associado = _criar_associado("Do Quadro")

		valores = {opcao["value"] for opcao in opcoes_de_responsavel()}

		self.assertIn(chave_do_associado(associado), valores)
		self.assertIn(chave_do_responsavel(self.responsavel), valores)

	def test_payload_sem_prefixo_continua_sendo_associado(self):
		"""Formulário antigo mandava o `name` cru de um `Associado`."""
		associado = _criar_associado("Antigo Lider")

		self._definir_lider(associado)

		area = frappe.db.get_value(
			"Unidade Organizacional", self.area, ["responsavel", "tipo_responsavel"], as_dict=True
		)
		self.assertEqual(area.responsavel, associado)
		self.assertEqual(area.tipo_responsavel, "Associado")

	def test_quem_tem_os_dois_cadastros_lidera_como_associado(self):
		"""Senão a chave `responsavel:` não casaria com o card `associado:` do desenho."""
		associado = _criar_associado("Homonimo Lider", CPF_DO_LIDER)
		self.assertEqual(associado, self.responsavel, "o par precisa mesmo ser homônimo")

		self._definir_lider(chave_do_responsavel(self.responsavel))

		area = frappe.db.get_value(
			"Unidade Organizacional", self.area, ["responsavel", "tipo_responsavel"], as_dict=True
		)
		self.assertEqual(area.tipo_responsavel, "Associado")

	# ------------------------------------------------------------------
	# Organograma
	# ------------------------------------------------------------------

	def test_o_responsavel_lidera_a_area_no_desenho(self):
		self._definir_lider(chave_do_responsavel(self.responsavel))

		arvore = obter_organograma()

		cards = _cards_da_area(arvore, self.area)
		lider = next(card for card in cards if card["pessoa"] == chave_do_responsavel(self.responsavel))
		self.assertEqual(lider["lidera_area"], self.area)
		self.assertEqual(lider["tipo_pessoa"], "responsavel")

	def test_liderar_basta_para_entrar_no_desenho(self):
		"""Sem função alocada, a área ficaria sem cabeça se o líder não fosse carregado."""
		self._definir_lider(chave_do_responsavel(self.responsavel))

		arvore = obter_organograma()

		self.assertIn(
			chave_do_responsavel(self.responsavel),
			[card["pessoa"] for card in _cards_da_area(arvore, self.area)],
		)

	def test_quem_tem_funcao_na_area_responde_ao_lider(self):
		self._definir_lider(chave_do_responsavel(self.responsavel))
		liderado = _criar_associado("Liderado")
		atribuir_funcao(
			json.dumps({"pessoa": chave_do_associado(liderado), "area": self.area, "funcao": self.funcao})
		)

		arvore = obter_organograma()

		cards = _cards_da_area(arvore, self.area)
		lider = next(card for card in cards if card["pessoa"] == chave_do_responsavel(self.responsavel))
		self.assertIn(chave_do_associado(liderado), [filho["pessoa"] for filho in lider["children"]])
		self.assertEqual(lider["diretos"], 1)

	def test_o_detalhe_do_responsavel_lista_as_areas_lideradas(self):
		garantir_estrutura_do_conselho()
		self._definir_lider(chave_do_responsavel(self.responsavel))

		detalhe = obter_detalhe_do_responsavel(self.responsavel)

		self.assertEqual(detalhe["areas_lideradas"], [self.area])
		self.assertIn(self.area, detalhe["areas"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cards_da_area(arvore: dict, area: str) -> list[dict]:
	"""Todos os nós de pessoa que o desenho pendurou naquela área."""
	achados: list[dict] = []

	def _visitar(nos):
		for no in nos:
			if no["tipo"] == "pessoa" and no.get("area") == area:
				achados.append(no)
			_visitar(no["children"])

	_visitar(arvore["raizes"])
	return achados


def _criar_area(sufixo: str) -> str:
	nome = f"{PREFIXO} {sufixo}"
	if not frappe.db.exists("Unidade Organizacional", nome):
		frappe.get_doc({"doctype": "Unidade Organizacional", "area": nome}).insert(ignore_permissions=True)
	return nome


def _criar_funcao(sufixo: str) -> str:
	titulo = f"{PREFIXO} Funcao {sufixo}"
	if not frappe.db.exists("Funcao Voluntario", titulo):
		frappe.get_doc(
			{"doctype": "Funcao Voluntario", "titulo": titulo, "categoria": "Colaborador", "ativa": 1}
		).insert(ignore_permissions=True)
	return titulo


def _vincular(area: str, funcao: str) -> None:
	doc = frappe.get_doc("Unidade Organizacional", area)
	doc.append("funcoes", {"funcao": funcao})
	doc.save(ignore_permissions=True)


def _criar_responsavel(sufixo: str, cpf: str) -> str:
	doc = frappe.get_doc({"doctype": "Responsavel", "nome_completo": f"{PREFIXO} {sufixo}", "cpf": cpf})
	doc.insert(ignore_permissions=True)
	return doc.name


def _criar_associado(sufixo: str, cpf: str | None = None) -> str:
	doc = frappe.get_doc(
		{
			"doctype": "Associado",
			"nome_completo": f"{PREFIXO} {sufixo}",
			"cpf": cpf or frappe.generate_hash(length=32),
			"data_de_nascimento": "1990-01-01",
			"categoria": "Dirigente",
			"status_no_grupo": "Ativo",
			"historico_no_grupo": [{"data_de_ingresso": "2020-01-01"}],
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name
