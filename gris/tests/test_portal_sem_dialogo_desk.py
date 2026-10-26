"""Trava contra modais do Desk sem estilo nas páginas do portal.

O portal não carrega o CSS do Desk, então frappe.msgprint/confirm/ui.Dialog aparecem
como um X gigante com a mensagem largada no rodapé. A regra mora em
scripts/checks/portal_sem_dialogo_desk.py (também no pre-commit); aqui ela roda junto
da suíte e tem o próprio detector testado.
"""

import runpy
import unittest
from pathlib import Path

CHECAGEM = runpy.run_path(
	str(Path(__file__).resolve().parents[2] / "scripts" / "checks" / "portal_sem_dialogo_desk.py")
)


class TestPortalSemDialogoDesk(unittest.TestCase):
	def test_shims_do_portal_estao_instalados(self):
		self.assertEqual(CHECAGEM["shims_ausentes"](), [])

	def test_msgprint_e_confirm_tem_shim(self):
		# O `frappe.call` do portal mostra o `frappe.throw` do servidor via msgprint.
		self.assertIn("msgprint", CHECAGEM["PORTAL_SHIMS"])
		self.assertIn("confirm", CHECAGEM["PORTAL_SHIMS"])

	def test_nenhuma_pagina_do_portal_usa_dialogo_do_desk_sem_shim(self):
		self.assertEqual(CHECAGEM["usos_proibidos"](), [])

	def test_detector_acha_dialogos_do_desk(self):
		codigo = "new frappe.ui.Dialog({});\nfrappe.prompt([], cb);\nfrappe.warn('a', 'b');"
		self.assertEqual(
			CHECAGEM["apis_proibidas_no_codigo"](codigo),
			[(1, "frappe.ui.Dialog"), (2, "frappe.prompt"), (3, "frappe.warn")],
		)

	def test_detector_ignora_comentarios_e_apis_com_shim(self):
		codigo = (
			"// frappe.prompt aqui não\n"
			"/* new frappe.ui.Dialog */\n"
			"{# frappe.ui.Dialog #}\n"
			"frappe.msgprint('ok'); frappe.confirm('?', () => {}); frappe.show_alert('x');\n"
			"const url = 'https://exemplo'; frappe.warn('a', 'b');"
		)
		self.assertEqual(CHECAGEM["apis_proibidas_no_codigo"](codigo), [(5, "frappe.warn")])

	def test_arquivos_do_desk_ficam_de_fora(self):
		arquivos = {p.name for p in CHECAGEM["arquivos_do_portal"]()}
		self.assertIn("extrato.js", arquivos)
		self.assertIn("captacao_comum.js", arquivos)
		# Só carregado pela página de Desk execucoes_de_jobs.
		self.assertNotIn("monitor_de_jobs_comum.js", arquivos)
