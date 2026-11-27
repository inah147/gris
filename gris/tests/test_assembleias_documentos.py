# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Documentos no timbrado e pasta no Drive (spec RF-11), com o Google simulado."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate

from gris.api.assembleias import constantes as c
from gris.api.assembleias import documentos, pagina
from gris.api.google_workspace import assembleia_drive
from gris.tests.test_assembleias_criacao import _criar
from gris.utils import docs_conteudo as dc

TIMBRADO = "https://docs.google.com/document/d/1TimbradoTesteABCDEFGHIJ/edit"
PASTA = "https://drive.google.com/drive/folders/1PastaDaAssembleiaABCDE"


class TestDocsConteudo(FrappeTestCase):
	def test_blocos(self):
		md = "# TÍTULO\n\n## Sub\n\nTexto com **negrito**\ncontinua.\n\n1. Um\n2. Dois\n\n| A | B |\n| --- | --- |\n| x | y |\n\nFim."
		blocos = dc.blocos(md)
		self.assertEqual([b["tipo"] for b in blocos], ["texto", "tabela", "texto"])
		paragrafos = blocos[0]["paragrafos"]
		self.assertEqual(
			[p["estilo"] for p in paragrafos], ["titulo1", "titulo2", "normal", "normal", "normal"]
		)
		self.assertEqual(paragrafos[2]["texto"], "Texto com **negrito**\ncontinua.")
		self.assertEqual([p["lista"] for p in paragrafos[3:]], ["numerada", "numerada"])
		self.assertEqual(blocos[1]["linhas"], [["A", "B"], ["x", "y"]])

	def test_indices_em_utf16_e_negrito(self):
		paragrafos = [{"texto": "😀 **ok**", "estilo": "normal", "lista": None}]
		requests, comprimento = dc.requests_de_texto(paragrafos, 10)
		self.assertEqual(requests[0]["insertText"], {"location": {"index": 10}, "text": "😀 ok\n"})
		# "😀" ocupa duas unidades UTF-16; "ok" começa na posição 3 do parágrafo.
		negrito = next(r for r in requests if r.get("updateTextStyle", {}).get("textStyle") == {"bold": True})
		self.assertEqual(negrito["updateTextStyle"]["range"], {"startIndex": 13, "endIndex": 15})
		self.assertEqual(comprimento, 6)

	def test_lista_vira_um_bloco_de_marcadores(self):
		paragrafos = [
			{"texto": "Um", "estilo": "normal", "lista": "numerada"},
			{"texto": "Dois", "estilo": "normal", "lista": "numerada"},
			{"texto": "Fim", "estilo": "normal", "lista": None},
		]
		requests, _comprimento = dc.requests_de_texto(paragrafos, 1)
		bullets = [r["createParagraphBullets"] for r in requests if "createParagraphBullets" in r]
		self.assertEqual(len(bullets), 1)
		self.assertEqual(bullets[0]["range"], {"startIndex": 1, "endIndex": 9})

	def test_titulo_centralizado(self):
		requests, _comprimento = dc.requests_de_texto(
			[{"texto": "EDITAL", "estilo": "titulo1", "lista": None}], 1
		)
		estilo = next(r["updateParagraphStyle"] for r in requests if "updateParagraphStyle" in r)
		self.assertEqual(estilo["paragraphStyle"]["alignment"], "CENTER")

	def test_preenchimento_da_tabela_de_tras_para_frente(self):
		tabela = {
			"tableRows": [
				{"tableCells": [{"content": [{"startIndex": 5}]}, {"content": [{"startIndex": 7}]}]},
				{"tableCells": [{"content": [{"startIndex": 10}]}, {"content": [{"startIndex": 12}]}]},
			]
		}
		requests = dc.requests_de_preenchimento(tabela, [["Nome", "Assinatura"], ["Ana", ""]])
		insercoes = [r["insertText"]["location"]["index"] for r in requests if "insertText" in r]
		self.assertEqual(insercoes, [10, 7, 5])
		# Cabeçalho em negrito.
		self.assertTrue(
			any(
				r.get("updateTextStyle", {}).get("range") == {"startIndex": 5, "endIndex": 9}
				for r in requests
			)
		)


class _Base(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		for name in frappe.get_all(c.DOCTYPE_ASSEMBLEIA, pluck="name"):
			frappe.delete_doc(c.DOCTYPE_ASSEMBLEIA, name, force=True)
		self.name = _criar(add_days(getdate(), 60))["name"]
		frappe.db.set_single_value("Configuracoes de Comunicacao", "link_papel_timbrado", TIMBRADO)

	def tearDown(self):
		frappe.db.rollback()

	def _google(self):
		"""Drive e Docs simulados; `documents().get` devolve um corpo com uma tabela."""
		drive = MagicMock()
		drive.files.return_value.copy.return_value.execute.return_value = {"id": "1DocGeradoABCDEFGHIJK"}
		drive.files.return_value.export.return_value.execute.return_value = b"%PDF-1.4 teste"
		docs = MagicMock()
		docs.documents.return_value.get.return_value.execute.return_value = {
			"body": {
				"content": [
					{"endIndex": 50},
					{
						"table": {"tableRows": [{"tableCells": [{"content": [{"startIndex": 52}]}]}]},
						"endIndex": 60,
					},
				]
			}
		}
		return drive, docs

	def _patches(self, drive, docs, upload="https://drive.google.com/file/d/1PdfGeradoABCDEFGHIJ/view"):
		return [
			patch.object(assembleia_drive, "_get_google_drive_service", return_value=drive),
			patch.object(assembleia_drive, "_get_docs_service", return_value=docs),
			patch.object(assembleia_drive, "_execute_with_retry", side_effect=lambda fn: fn()),
			patch.object(assembleia_drive, "upload_bytes_to_folder", return_value=upload),
			# gerar_documento faz commit (os arquivos já existem no Drive); no teste isso
			# gravaria o timbrado falso e a assembleia de vez no site.
			patch("frappe.db.commit"),
		]


class TestAssembleiaDrive(_Base):
	def test_pasta_desligada_registra_motivo(self):
		with patch("frappe.db.commit"):
			self.assertEqual(assembleia_drive.criar_pasta_assembleia(self.name), "")
		self.assertIn("desligadas", frappe.db.get_value(c.DOCTYPE_ASSEMBLEIA, self.name, "pasta_drive_erro"))

	def test_sem_timbrado(self):
		frappe.db.set_single_value("Configuracoes de Comunicacao", "link_papel_timbrado", "")
		with self.assertRaisesRegex(frappe.ValidationError, "papel timbrado"):
			assembleia_drive.gerar_documento(self.name, "edital", "texto")

	def test_gera_edital_e_substitui_rascunho(self):
		frappe.db.set_value(c.DOCTYPE_ASSEMBLEIA, self.name, "pasta_drive_link", PASTA)
		drive, docs = self._google()
		patches = self._patches(drive, docs)
		for p in patches:
			p.start()
		try:
			pdf = assembleia_drive.gerar_documento(self.name, "edital", "# EDITAL\n\nTexto.")
			self.assertEqual(pdf, b"%PDF-1.4 teste")
			links = frappe.db.get_value(
				c.DOCTYPE_ASSEMBLEIA,
				self.name,
				["edital_doc_link", "edital_pdf_link", "edital_final_gerado"],
				as_dict=True,
			)
			self.assertIn("1DocGeradoABCDEFGHIJK", links.edital_doc_link)
			self.assertEqual(links.edital_final_gerado, 0)
			copia = drive.files.return_value.copy.call_args.kwargs
			self.assertEqual(copia["body"]["parents"], ["1PastaDaAssembleiaABCDE"])
			# Segunda geração apaga os arquivos do rascunho anterior.
			assembleia_drive.gerar_documento(self.name, "edital", "# EDITAL\n\nDe novo.")
			apagados = [
				chamada.kwargs["fileId"] for chamada in drive.files.return_value.delete.call_args_list
			]
			self.assertIn("1DocGeradoABCDEFGHIJK", apagados)
		finally:
			for p in patches:
				p.stop()

	def test_erro_do_google_vira_mensagem(self):
		from googleapiclient.errors import HttpError

		frappe.db.set_value(c.DOCTYPE_ASSEMBLEIA, self.name, "pasta_drive_link", PASTA)
		drive, docs = self._google()
		resposta = MagicMock(status=403)
		drive.files.return_value.copy.return_value.execute.side_effect = HttpError(resposta, b"{}")
		patches = self._patches(drive, docs)
		for p in patches:
			p.start()
		try:
			with (
				patch("gris.api.google_workspace.assembleia_drive.frappe.log_error"),
				self.assertRaisesRegex(frappe.ValidationError, "service account"),
			):
				assembleia_drive.gerar_documento(self.name, "lista", "texto")
		finally:
			for p in patches:
				p.stop()

	def test_publicar_sem_drive_mantem_publicado_com_aviso(self):
		with patch("frappe.db.commit"):
			resposta = pagina.marcar_edital_publicado(self.name)
		self.assertEqual(resposta["edital"]["publicado"], 1)
		self.assertIn("PDF final", resposta["aviso"])

	def test_publicar_gera_edital_final(self):
		frappe.db.set_value(c.DOCTYPE_ASSEMBLEIA, self.name, "pasta_drive_link", PASTA)
		drive, docs = self._google()
		patches = self._patches(drive, docs)
		for p in patches:
			p.start()
		try:
			resposta = pagina.marcar_edital_publicado(self.name)
		finally:
			for p in patches:
				p.stop()
		self.assertEqual(resposta["aviso"], "")
		self.assertEqual(frappe.db.get_value(c.DOCTYPE_ASSEMBLEIA, self.name, "edital_final_gerado"), 1)
		nome = drive.files.return_value.copy.call_args.kwargs["body"]["name"]
		self.assertTrue(nome.endswith("(publicado)"))


class TestConteudoDocumentos(_Base):
	def test_lista_de_presenca(self):
		doc = frappe.get_doc(c.DOCTYPE_ASSEMBLEIA, self.name)
		doc.append(
			"votantes",
			{"nome": "Bia | Souza", "tipo_linha": c.LINHA_JOVEM_REPRESENTADO, "origem": "Automática"},
		)
		doc.append("votantes", {"nome": "Ana", "tipo_linha": c.LINHA_ESCOTISTA, "origem": "Automática"})
		doc.append(
			"votantes",
			{"nome": "Removida", "tipo_linha": c.LINHA_ESCOTISTA, "removido": 1, "origem": "Automática"},
		)
		texto = documentos.conteudo_da_lista(doc)
		self.assertIn("| Nome | Representado por | Assinatura |", texto)
		self.assertIn("2 com direito a voto", texto)
		self.assertNotIn("Removida", texto)
		self.assertLess(texto.index("| Ana |"), texto.index("Bia / Souza"))
		self.assertIn("Bia / Souza (representado por seu responsável legal) | Responsável:", texto)
		tabela = next(b for b in dc.blocos(texto) if b["tipo"] == "tabela")
		self.assertEqual(len(tabela["linhas"]), 3)

	def test_ata(self):
		doc = frappe.get_doc(c.DOCTYPE_ASSEMBLEIA, self.name)
		doc.ata_texto = "No dia **05**..."
		texto = documentos.conteudo_da_ata(doc)
		self.assertTrue(texto.startswith("# ATA DA REUNIÃO ORDINÁRIA"))
		self.assertIn("No dia **05**", texto)
