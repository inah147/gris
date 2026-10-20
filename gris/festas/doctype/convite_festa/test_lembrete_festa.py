# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from gris.api.festas.convites import JOB_LEMBRETE, enviar_lembrete, previa_lembrete
from gris.festas.doctype.compra_festa.test_compra_festa import _nova_festa
from gris.festas.doctype.convite_festa.convite_festa import _criar_lista_entrada
from gris.festas.utils.lembrete_festa import (
	TIPO_COMPRADOR,
	TIPO_CONVIDADO,
	enviar_lembrete_festa,
	mascarar_email,
	mascarar_telefone,
	montar_lembretes,
	quando_e_a_festa,
	texto_do_lembrete,
)

PDF_FALSO = b"%PDF-FAKE"
TEL_CAIO = "11988887777"
TEL_DORA = "21977776666"
TEL_ENZO = "31966665555"


def _opcao(festa_name: str, *, portaria: bool = False):
	opcao = frappe.get_doc(
		{
			"doctype": "Opcao Convite Festa",
			"festa": festa_name,
			"nome_convite": f"Inteira {frappe.generate_hash(length=4)}",
			"valor": 50,
		}
	).insert(ignore_permissions=True)
	if portaria:
		frappe.db.set_value("Opcao Convite Festa", opcao.name, "portaria", 1)
	return opcao


class TestLembreteFesta(FrappeTestCase):
	def setUp(self):
		for alvo, kwargs in (
			(
				"gris.financeiro.doctype.cobranca_infinitepay.cobranca_infinitepay.CobrancaInfinitepay._criar_link_pagamento",
				{"new": lambda self: None},
			),
			("gris.utils.whatsapp.enviar_texto", {}),
			("gris.utils.whatsapp.enviar_midia", {}),
			("gris.festas.utils.convite_qr.gerar_pdf_convite", {"return_value": PDF_FALSO}),
			("gris.festas.utils.lembrete_festa.time.sleep", {}),
			("frappe.utils.background_jobs.is_job_enqueued", {"return_value": False}),
			("frappe.enqueue", {}),
		):
			patcher = patch(alvo, **kwargs)
			mock = patcher.start()
			self.addCleanup(patcher.stop)
			if alvo.endswith("enviar_texto"):
				self.mock_texto = mock
			elif alvo.endswith("enviar_midia"):
				self.mock_midia = mock
			elif alvo == "frappe.enqueue":
				self.mock_enqueue = mock

		# O job comita por número; no teste isso gravaria os dados de verdade no site.
		commit_patcher = patch.object(frappe.db, "commit")
		commit_patcher.start()
		self.addCleanup(commit_patcher.stop)

		self.festa = _nova_festa()
		frappe.db.set_value("Festa", self.festa.name, "horario_inicio", "19:00:00")
		self.opcao = _opcao(self.festa.name)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _pedido(
		self,
		convidados,
		*,
		nome_pagador="Caio Bernardo",
		telefone_pagador=TEL_CAIO,
		pagador_recebe=False,
		opcao=None,
		pagar=True,
	):
		convite = frappe.get_doc(
			{
				"doctype": "Convite Festa",
				"festa": self.festa.name,
				"nome_pagador": nome_pagador,
				"telefone_pagador": telefone_pagador,
				"email_pagador": "caio@example.com",
				"pagador_recebe_qr_codes": 1 if pagador_recebe else 0,
				"itens": [
					{
						"eh_convite": 1,
						"opcao_convite": (opcao or self.opcao).name,
						"quantidade": len(convidados),
					}
				],
				"convidados": convidados,
			}
		).insert(ignore_permissions=True)
		if pagar:
			frappe.db.set_value("Cobranca Infinitepay", convite.cobranca_infinitepay, "status", "Pago")
		convite.reload()
		return convite

	def _por_tipo(self):
		destinatarios = montar_lembretes(self.festa.name)["destinatarios"]
		return {d.telefone: d for d in destinatarios}

	# ---------- Quem recebe o quê ----------

	def test_comprador_de_um_convite_para_outra_pessoa_so_o_convidado_recebe(self):
		self._pedido([{"nome": "Dora Lima", "email": "dora@example.com", "telefone": TEL_DORA}])

		destinatarios = self._por_tipo()

		self.assertEqual(list(destinatarios), [f"55{TEL_DORA}"])
		dora = destinatarios[f"55{TEL_DORA}"]
		self.assertEqual(dora.tipo, TIPO_CONVIDADO)
		self.assertEqual(dora.nome, "Dora Lima")
		self.assertEqual(len(dora.anexos), 1)

	def test_comprador_de_um_convite_para_si_recebe_a_mensagem_do_convidado(self):
		self._pedido([{"nome": "Caio Bernardo", "email": "caio@example.com", "telefone": TEL_CAIO}])

		destinatarios = self._por_tipo()

		self.assertEqual(list(destinatarios), [f"55{TEL_CAIO}"])
		self.assertEqual(destinatarios[f"55{TEL_CAIO}"].tipo, TIPO_CONVIDADO)

	def test_comprador_de_varios_convites_recebe_so_a_mensagem_do_comprador(self):
		self._pedido(
			[
				{"nome": "Caio Bernardo", "email": "caio@example.com", "telefone": TEL_CAIO},
				{"nome": "Dora Lima", "email": "dora@example.com", "telefone": TEL_DORA},
			]
		)

		destinatarios = self._por_tipo()

		caio = destinatarios[f"55{TEL_CAIO}"]
		self.assertEqual(caio.tipo, TIPO_COMPRADOR)
		self.assertEqual([a.nome for a in caio.anexos], ["Caio Bernardo"])
		self.assertEqual([c.nome for c in caio.lista], ["Dora Lima"])
		self.assertEqual(destinatarios[f"55{TEL_DORA}"].tipo, TIPO_CONVIDADO)

	def test_pedidos_do_mesmo_telefone_viram_uma_mensagem_com_a_lista_unida(self):
		self._pedido([{"nome": "Dora Lima", "email": "dora@example.com", "telefone": TEL_DORA}])
		self._pedido([{"nome": "Enzo Reis", "email": "enzo@example.com", "telefone": TEL_ENZO}])

		destinatarios = self._por_tipo()

		caio = destinatarios[f"55{TEL_CAIO}"]
		self.assertEqual(caio.tipo, TIPO_COMPRADOR)
		self.assertEqual(caio.anexos, [])
		self.assertEqual([c.nome for c in caio.lista], ["Dora Lima", "Enzo Reis"])
		self.assertEqual(len(destinatarios), 3)

	def test_pagador_recebe_todos_ganha_todos_os_pdfs_e_nenhuma_lista(self):
		self._pedido([{"nome": "Caio Bernardo"}, {"nome": "Dora Lima"}], pagador_recebe=True)

		destinatarios = self._por_tipo()

		self.assertEqual(list(destinatarios), [f"55{TEL_CAIO}"])
		caio = destinatarios[f"55{TEL_CAIO}"]
		self.assertEqual(caio.tipo, TIPO_COMPRADOR)
		self.assertEqual([a.nome for a in caio.anexos], ["Caio Bernardo", "Dora Lima"])
		self.assertEqual(caio.lista, [])

	def test_pedido_nao_pago_e_venda_de_portaria_ficam_de_fora(self):
		self._pedido([{"nome": "Dora Lima", "email": "dora@example.com", "telefone": TEL_DORA}], pagar=False)
		self._pedido(
			[{"nome": "Enzo Reis", "email": "enzo@example.com", "telefone": TEL_ENZO}],
			opcao=_opcao(self.festa.name, portaria=True),
		)

		self.assertEqual(self._por_tipo(), {})

	def test_quem_ja_entrou_nao_recebe(self):
		convite = self._pedido([{"nome": "Dora Lima", "email": "dora@example.com", "telefone": TEL_DORA}])
		_criar_lista_entrada(convite.name)
		frappe.db.set_value("Lista Entrada Festa", {"convite": convite.name}, "status", "Entrou")

		self.assertEqual(self._por_tipo(), {})

	def test_convidado_sem_telefone_entra_so_na_contagem(self):
		convite = self._pedido([{"nome": "Dora Lima", "email": "dora@example.com", "telefone": TEL_DORA}])
		frappe.db.set_value("Convidado Convite Festa", convite.convidados[0].name, "telefone", "")

		lembretes = montar_lembretes(self.festa.name)

		self.assertEqual(lembretes["destinatarios"], [])
		self.assertEqual(lembretes["sem_telefone"], 1)

	# ---------- Textos ----------

	def test_quando_e_a_festa(self):
		festa = frappe._dict(data=date(2026, 10, 24), horario_inicio="19:00:00")

		self.assertEqual(quando_e_a_festa(festa, hoje=date(2026, 10, 24)), "é hoje, às 19:00")
		self.assertEqual(quando_e_a_festa(festa, hoje=date(2026, 10, 23)), "é amanhã (24/10), às 19:00")
		self.assertEqual(
			quando_e_a_festa(festa, hoje=date(2026, 10, 20)), "é no dia 24/10 (sábado), às 19:00"
		)
		festa.horario_inicio = None
		self.assertEqual(quando_e_a_festa(festa, hoje=date(2026, 10, 24)), "é hoje")

	def test_mascaras(self):
		self.assertEqual(mascarar_email("dora.lima@example.com"), "dor***@example.com")
		self.assertEqual(mascarar_email(""), "")
		self.assertEqual(mascarar_telefone(TEL_DORA), "21*******66")

	def test_texto_do_convidado(self):
		self._pedido([{"nome": "Dora Lima", "email": "dora@example.com", "telefone": TEL_DORA}])
		festa = frappe.db.get_value("Festa", self.festa.name, ["*"], as_dict=True)

		texto = texto_do_lembrete(festa, self._por_tipo()[f"55{TEL_DORA}"])

		self.assertEqual(
			texto,
			f"Oi, Dora!\n\nPassando para te lembrar que a festa {festa.nome_festa} é hoje, às 19:00! "
			"Para facilitar, aqui está seu convite.\n\n"
			"Te esperamos lá para se divertir com a gente ❤️",
		)

	def test_texto_do_comprador_lista_os_convidados_mascarados(self):
		convite = self._pedido(
			[
				{"nome": "Caio Bernardo", "email": "caio@example.com", "telefone": TEL_CAIO},
				{"nome": "Dora Lima", "email": "dora@example.com", "telefone": TEL_DORA},
				{"nome": "Enzo Reis", "email": "enzo@example.com", "telefone": TEL_ENZO},
			]
		)
		frappe.db.set_value("Convidado Convite Festa", convite.convidados[2].name, "telefone", "")
		festa = frappe.db.get_value("Festa", self.festa.name, ["*"], as_dict=True)
		ontem = add_days(today(), -1)

		texto = texto_do_lembrete(festa, self._por_tipo()[f"55{TEL_CAIO}"], hoje=ontem)

		self.assertIn(f"a festa {festa.nome_festa} é amanhã", texto)
		self.assertIn("Para te ajudar, aqui está o seu convite.", texto)
		self.assertIn(
			"os convites dos seus convidados foram enviados para:\n"
			"- Dora - dor***@example.com | 21*******66\n"
			"- Enzo - enz***@example.com",
			texto,
		)

	def test_texto_do_comprador_que_recebe_todos(self):
		self._pedido([{"nome": "Caio Bernardo"}, {"nome": "Dora Lima"}], pagador_recebe=True)
		festa = frappe.db.get_value("Festa", self.festa.name, ["*"], as_dict=True)

		texto = texto_do_lembrete(festa, self._por_tipo()[f"55{TEL_CAIO}"])

		self.assertIn("Para te ajudar, aqui estão os seus convites.", texto)
		self.assertNotIn("Além disso", texto)

	# ---------- Envio ----------

	def test_job_manda_um_pdf_por_convite_com_o_texto_no_primeiro(self):
		self._pedido([{"nome": "Caio Bernardo"}, {"nome": "Dora Lima"}], pagador_recebe=True)

		enviar_lembrete_festa(self.festa.name)

		self.assertEqual(self.mock_midia.call_count, 2)
		primeira, segunda = self.mock_midia.call_args_list
		self.assertEqual(primeira.args[0], f"55{TEL_CAIO}")
		self.assertTrue(primeira.kwargs["caption"].startswith("Oi, Caio!"))
		self.assertEqual(segunda.kwargs["caption"], "🎟️ Convite de Dora Lima")
		self.assertEqual(primeira.kwargs["contexto"]["destinatario_tipo"], "Convidado de festa")
		self.mock_texto.assert_not_called()

	def test_job_manda_so_texto_ao_comprador_sem_convite_proprio(self):
		self._pedido([{"nome": "Dora Lima", "email": "dora@example.com", "telefone": TEL_DORA}])
		self._pedido([{"nome": "Enzo Reis", "email": "enzo@example.com", "telefone": TEL_ENZO}])

		enviar_lembrete_festa(self.festa.name)

		self.mock_texto.assert_called_once()
		self.assertEqual(self.mock_texto.call_args.args[0], f"55{TEL_CAIO}")
		self.assertIn("- Dora - dor***@example.com", self.mock_texto.call_args.args[1])
		self.assertEqual(self.mock_midia.call_count, 2)

	def test_job_cai_no_link_quando_o_pdf_falha(self):
		self._pedido([{"nome": "Dora Lima", "email": "dora@example.com", "telefone": TEL_DORA}])

		with patch("gris.festas.utils.convite_qr.gerar_pdf_convite", side_effect=RuntimeError("sem pdf")):
			enviar_lembrete_festa(self.festa.name)

		self.mock_midia.assert_not_called()
		self.mock_texto.assert_called_once()
		self.assertIn("/convite/", self.mock_texto.call_args.args[1])

	# ---------- Endpoints ----------

	def test_previa_conta_convidados_e_compradores(self):
		self._pedido(
			[
				{"nome": "Caio Bernardo", "email": "caio@example.com", "telefone": TEL_CAIO},
				{"nome": "Dora Lima", "email": "dora@example.com", "telefone": TEL_DORA},
			]
		)

		previa = previa_lembrete(self.festa.name)

		self.assertEqual((previa["convidados"], previa["compradores"]), (1, 1))
		self.assertEqual(previa["quando"], "é hoje, às 19:00")
		self.assertEqual(previa["ja_enviado_em"], "")

	def test_enviar_grava_quem_enviou_e_enfileira_o_job(self):
		self._pedido([{"nome": "Dora Lima", "email": "dora@example.com", "telefone": TEL_DORA}])

		enviar_lembrete(self.festa.name)

		festa = frappe.db.get_value(
			"Festa", self.festa.name, ["lembrete_enviado_em", "lembrete_enviado_por"], as_dict=True
		)
		self.assertTrue(festa.lembrete_enviado_em)
		self.assertEqual(festa.lembrete_enviado_por, "Administrator")
		jobs = [c for c in self.mock_enqueue.call_args_list if c.args and c.args[0] == JOB_LEMBRETE]
		self.assertEqual(len(jobs), 1)
		self.assertEqual(jobs[0].kwargs["festa_name"], self.festa.name)
		self.assertTrue(previa_lembrete(self.festa.name)["ja_enviado_em"])

	def test_enviar_recusa_festa_que_ja_passou(self):
		self._pedido([{"nome": "Dora Lima", "email": "dora@example.com", "telefone": TEL_DORA}])
		frappe.db.set_value("Festa", self.festa.name, "data", add_days(today(), -1))

		with self.assertRaises(frappe.ValidationError):
			enviar_lembrete(self.festa.name)

	def test_enviar_recusa_festa_sem_destinatarios(self):
		with self.assertRaises(frappe.ValidationError):
			enviar_lembrete(self.festa.name)

	def test_endpoints_exigem_gestor_de_festas(self):
		frappe.set_user("Guest")

		with self.assertRaises(frappe.PermissionError):
			previa_lembrete(self.festa.name)
		with self.assertRaises(frappe.PermissionError):
			enviar_lembrete(self.festa.name)
