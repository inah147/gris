# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Testes das funções internas do Associado (a grade que alimenta o organograma)."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

PREFIXO = "ZZ Teste Funcoes"


class TestFuncoesInternasDoAssociado(FrappeTestCase):
	def setUp(self):
		self.area = self._criar_area("Area")
		self.outra_area = self._criar_area("Outra Area")
		self.funcao_a = self._criar_funcao("A")
		self.funcao_b = self._criar_funcao("B")
		self._vincular(self.area, self.funcao_a)
		self._vincular(self.area, self.funcao_b)
		self.associado = self._criar_associado()

	def tearDown(self):
		# FrappeTestCase faz rollback por classe; sem isto o próximo teste
		# esbarra em DuplicateEntryError nos registros criados no setUp.
		frappe.db.rollback()

	def test_uma_funcao_principal_e_aceita(self):
		doc = frappe.get_doc("Associado", self.associado)
		doc.append("funcoes_internas", {"funcao": self.funcao_a, "area": self.area, "principal": 1})
		doc.append("funcoes_internas", {"funcao": self.funcao_b, "area": self.area, "principal": 0})
		doc.save(ignore_permissions=True)

		self.assertEqual(len(doc.funcoes_internas), 2)

	def test_duas_principais_sao_barradas(self):
		doc = frappe.get_doc("Associado", self.associado)
		doc.append("funcoes_internas", {"funcao": self.funcao_a, "area": self.area, "principal": 1})
		doc.append("funcoes_internas", {"funcao": self.funcao_b, "area": self.area, "principal": 1})

		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_data_fim_antes_do_inicio_e_barrada(self):
		doc = frappe.get_doc("Associado", self.associado)
		doc.append(
			"funcoes_internas",
			{
				"funcao": self.funcao_a,
				"area": self.area,
				"data_inicio": "2024-01-01",
				"data_fim": "2023-01-01",
			},
		)

		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_area_e_escolhida_na_linha(self):
		"""A área não vem mais da função: a mesma função pode valer em várias."""
		doc = frappe.get_doc("Associado", self.associado)
		doc.append("funcoes_internas", {"funcao": self.funcao_a, "area": self.area})
		doc.save(ignore_permissions=True)
		doc.reload()

		self.assertEqual(doc.funcoes_internas[0].area, self.area)

	def test_linha_nova_sem_area_e_barrada(self):
		doc = frappe.get_doc("Associado", self.associado)
		doc.append("funcoes_internas", {"funcao": self.funcao_a})

		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_par_funcao_area_sem_vinculo_e_barrado(self):
		doc = frappe.get_doc("Associado", self.associado)
		# A função existe e a área existe, mas a área não lista essa função.
		doc.append("funcoes_internas", {"funcao": self.funcao_a, "area": self.outra_area})

		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_mesma_funcao_em_duas_areas(self):
		self._vincular(self.outra_area, self.funcao_a)
		doc = frappe.get_doc("Associado", self.associado)
		doc.append("funcoes_internas", {"funcao": self.funcao_a, "area": self.area, "principal": 1})
		doc.append("funcoes_internas", {"funcao": self.funcao_a, "area": self.outra_area})
		doc.save(ignore_permissions=True)
		doc.reload()

		self.assertEqual({linha.area for linha in doc.funcoes_internas}, {self.area, self.outra_area})

	def test_linha_historica_com_vinculo_desfeito_nao_bloqueia_save(self):
		"""A trava que impede a edição de uma área de tornar pessoas insalváveis.

		Sem isto, desfazer um vínculo quebraria a importação do Paxtu semanas depois,
		por um motivo sem relação nenhuma com quem está sendo importado.
		"""
		doc = frappe.get_doc("Associado", self.associado)
		doc.append(
			"funcoes_internas",
			{
				"funcao": self.funcao_a,
				"area": self.area,
				"data_inicio": "2020-01-01",
				"data_fim": "2021-01-01",
			},
		)
		doc.save(ignore_permissions=True)

		# A área deixa de listar a função; a linha histórica continua apontando o par.
		area = frappe.get_doc("Unidade Organizacional", self.area)
		area.funcoes = [linha for linha in area.funcoes if linha.funcao != self.funcao_a]
		area.save(ignore_permissions=True)

		doc.reload()
		doc.nome_completo = f"{PREFIXO} Pessoa editada"
		# O save é o teste: ele não pode levantar por causa da linha histórica.
		doc.save(ignore_permissions=True)

		# O Associado normaliza o nome para Title Case, daí a comparação sem caixa.
		self.assertIn("editada", doc.nome_completo.lower())

	def test_linha_em_vigor_nao_impede_save_se_nao_mudou(self):
		"""Só o que entrou ou mudou agora é checado — o resto é dado, não decisão."""
		doc = frappe.get_doc("Associado", self.associado)
		doc.append("funcoes_internas", {"funcao": self.funcao_b, "area": self.area})
		doc.save(ignore_permissions=True)

		frappe.db.delete(
			"Funcao da Area",
			{"parent": self.area, "parenttype": "Unidade Organizacional", "funcao": self.funcao_b},
		)

		doc.reload()
		doc.nome_completo = f"{PREFIXO} Pessoa mantida"
		doc.save(ignore_permissions=True)

		self.assertIn("mantida", doc.nome_completo.lower())

	def _criar_area(self, sufixo):
		nome = f"{PREFIXO} {sufixo}"
		if not frappe.db.exists("Unidade Organizacional", nome):
			frappe.get_doc({"doctype": "Unidade Organizacional", "area": nome}).insert(
				ignore_permissions=True
			)
		return nome

	def _criar_funcao(self, sufixo):
		titulo = f"{PREFIXO} Funcao {sufixo}"
		if not frappe.db.exists("Funcao Voluntario", titulo):
			frappe.get_doc(
				{
					"doctype": "Funcao Voluntario",
					"titulo": titulo,
					"categoria": "Dirigente",
					"responsabilidades": [{"responsabilidade": f"Responsabilidade {sufixo}"}],
				}
			).insert(ignore_permissions=True)
		return titulo

	def _vincular(self, area, funcao):
		if frappe.db.exists(
			"Funcao da Area",
			{"parent": area, "parenttype": "Unidade Organizacional", "funcao": funcao},
		):
			return
		doc = frappe.get_doc("Unidade Organizacional", area)
		doc.append("funcoes", {"funcao": funcao})
		doc.save(ignore_permissions=True)

	def _criar_associado(self):
		doc = frappe.get_doc(
			{
				"doctype": "Associado",
				"nome_completo": f"{PREFIXO} Pessoa",
				"cpf": frappe.generate_hash(length=32),
				"data_de_nascimento": "1990-01-01",
				"categoria": "Dirigente",
				"status_no_grupo": "Ativo",
				"historico_no_grupo": [{"data_de_ingresso": "2020-01-01"}],
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name


class TestDesvinculoDeFuncaoDaArea(FrappeTestCase):
	"""Tirar uma função da área é barrado enquanto alguém ainda a exerce lá."""

	def setUp(self):
		self.area = f"{PREFIXO} Desvinculo"
		if not frappe.db.exists("Unidade Organizacional", self.area):
			frappe.get_doc({"doctype": "Unidade Organizacional", "area": self.area}).insert(
				ignore_permissions=True
			)
		self.funcao = f"{PREFIXO} Funcao Desvinculo"
		if not frappe.db.exists("Funcao Voluntario", self.funcao):
			frappe.get_doc(
				{"doctype": "Funcao Voluntario", "titulo": self.funcao, "categoria": "Dirigente"}
			).insert(ignore_permissions=True)

		area = frappe.get_doc("Unidade Organizacional", self.area)
		area.append("funcoes", {"funcao": self.funcao})
		area.save(ignore_permissions=True)

	def tearDown(self):
		frappe.db.rollback()

	def _pessoa_com_funcao(self, data_fim=None):
		doc = frappe.get_doc(
			{
				"doctype": "Associado",
				"nome_completo": f"{PREFIXO} Ocupante",
				"cpf": frappe.generate_hash(length=32),
				"data_de_nascimento": "1990-01-01",
				"categoria": "Dirigente",
				"status_no_grupo": "Ativo",
				"historico_no_grupo": [{"data_de_ingresso": "2020-01-01"}],
				"funcoes_internas": [
					{
						"funcao": self.funcao,
						"area": self.area,
						"data_inicio": "2024-01-01",
						"data_fim": data_fim,
					}
				],
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def _desvincular(self):
		area = frappe.get_doc("Unidade Organizacional", self.area)
		area.funcoes = [linha for linha in area.funcoes if linha.funcao != self.funcao]
		area.save(ignore_permissions=True)

	def test_funcao_repetida_na_lista_e_barrada(self):
		area = frappe.get_doc("Unidade Organizacional", self.area)
		area.append("funcoes", {"funcao": self.funcao})

		with self.assertRaises(frappe.ValidationError):
			area.save(ignore_permissions=True)

	def test_desvincular_sem_ninguem_e_permitido(self):
		self._desvincular()

		self.assertEqual(
			frappe.db.count("Funcao da Area", {"parent": self.area, "parenttype": "Unidade Organizacional"}),
			0,
		)

	def test_desvincular_com_pessoa_ativa_e_barrado(self):
		self._pessoa_com_funcao()

		with self.assertRaises(frappe.ValidationError):
			self._desvincular()

	def test_desvincular_com_data_fim_futura_e_barrado(self):
		"""O corte é o mesmo do organograma: só passou a valer quando a data já passou."""
		self._pessoa_com_funcao(data_fim=add_days(nowdate(), 30))

		with self.assertRaises(frappe.ValidationError):
			self._desvincular()

	def test_desvincular_com_data_fim_passada_e_permitido(self):
		self._pessoa_com_funcao(data_fim=add_days(nowdate(), -1))

		self._desvincular()

		self.assertEqual(
			frappe.db.count("Funcao da Area", {"parent": self.area, "parenttype": "Unidade Organizacional"}),
			0,
		)
