import io

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today
from pypdf import PdfReader

from gris.api.festas.exportar_pdf import (
	_num,
	build_exportacao_context,
	download_festa_pdf,
	gerar_pdf_festa_bytes,
)


def _festa_com_dados():
	festa = frappe.get_doc(
		{
			"doctype": "Festa",
			"nome_festa": f"Festa PDF {frappe.generate_hash(length=8)}",
			"data": today(),
			"data_limite_vendas": today(),
			"status": "Em andamento",
			"expectativa_publico_min": 100,
			"expectativa_publico_intermediario": 150,
			"expectativa_publico_max": 200,
		}
	).insert(ignore_permissions=True)
	portaria = frappe.get_doc("Area da Festa", f"{festa.name} - Portaria")
	portaria.nome_coord = "Coord Portaria"
	portaria.email_coord = "portaria@example.com"
	portaria.telefone_coord = "+5511999999999"
	portaria.save(ignore_permissions=True)
	area = frappe.get_doc(
		{
			"doctype": "Area da Festa",
			"festa": festa.name,
			"nome_area": "Cozinha",
			"tipo_coord": "Outro",
			"nome_coord": "Ana <b>Coord</b>",
			"email_coord": "ana@example.com",
			"telefone_coord": "+5511999990001",
			"equipe": [
				{
					"tipo_pessoa": "Outro",
					"nome": "Beto",
					"funcao": "Chapeiro",
					"email": "beto@example.com",
					"telefone": "+5511999990002",
				}
			],
		}
	).insert(ignore_permissions=True)
	barraca = frappe.get_doc(
		{
			"doctype": "Barraca da Festa",
			"festa": festa.name,
			"nome_barraca": "Pastel",
			"area": area.name,
			"tipo_coord": "Outro",
			"nome_coord": "Caio",
			"email_coord": "caio@example.com",
			"telefone_coord": "+5511999990003",
		}
	).insert(ignore_permissions=True)
	frappe.get_doc(
		{
			"doctype": "Produto de Venda Festa",
			"festa": festa.name,
			"barraca": barraca.name,
			"nome_produto": "Pastel de queijo",
			"preco_custo": 3,
			"preco_venda": 8,
			"expectativa_venda_por_pessoa": 1,
		}
	).insert(ignore_permissions=True)
	frappe.get_doc(
		{
			"doctype": "Compra Festa",
			"festa": festa.name,
			"area": area.name,
			"nome_item": "Óleo",
			"unidade_compra": "kg",
			"quantidade_compra": 1,
			"quantidade_compra_final": 3,
			"cotacoes": [
				{"fornecedor": "Mercado A", "valor": 10, "quantidade": 1, "unidade_medida": "kg", "escolhida": 1},
				{"fornecedor": "Mercado B", "valor": 12, "quantidade": 1, "unidade_medida": "kg"},
			],
		}
	).insert(ignore_permissions=True)
	return festa


class TestExportarPdfFesta(FrappeTestCase):
	def test_contexto_tem_uma_secao_por_aba(self):
		festa = _festa_com_dados()
		ctx = build_exportacao_context(festa.name)

		self.assertEqual([p["nome_produto"] for p in ctx["produtos"]], ["Pastel de queijo"])
		compra = ctx["compras"][0]
		self.assertEqual(compra["fornecedor_escolhido"], "Mercado A")
		self.assertEqual(len(compra["cotacoes"]), 2)
		self.assertIn("Cozinha", [linha["label"] for linha in ctx["despesas_area"]["linhas"]])
		self.assertEqual(ctx["tarefas"]["linhas"], [])
		self.assertEqual(ctx["convites"]["pedidos"], [])
		self.assertFalse(ctx["avaliacao_equipe_iniciada"])

	def test_gera_pdf_com_texto_do_usuario_escapado(self):
		festa = _festa_com_dados()
		pdf = gerar_pdf_festa_bytes(festa.name)
		self.assertTrue(pdf.startswith(b"%PDF"))

		leitor = PdfReader(io.BytesIO(pdf))
		# Capa + 9 seções (uma por aba), cada uma começando em página nova.
		self.assertGreaterEqual(len(leitor.pages), 10)
		texto = "\n".join(pagina.extract_text() for pagina in leitor.pages)
		for titulo in ("Dados gerais", "Produtos vendidos", "Contratações", "Orçamento", "Gestão de tarefas"):
			self.assertIn(titulo, texto)
		self.assertIn("Pastel de queijo", texto)
		self.assertIn("Mercado A", texto)
		# Texto digitado vira texto, não HTML.
		self.assertIn("Ana <b>Coord</b>", texto)

	def test_download_exige_permissao(self):
		festa = _festa_com_dados()
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				download_festa_pdf(festa.name)
		finally:
			frappe.set_user("Administrator")

	def test_numero_no_formato_brasileiro(self):
		self.assertEqual(_num(1234.5), "1.234,5")
		self.assertEqual(_num(3), "3")
		self.assertEqual(_num(0.25), "0,25")
		self.assertEqual(_num(None), "0")
