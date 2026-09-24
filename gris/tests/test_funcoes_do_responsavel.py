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
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate, nowdate

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
