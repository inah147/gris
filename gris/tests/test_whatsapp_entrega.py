"""Conciliação da entrega: do aceite da Evolution ao que o WhatsApp confirmou."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime

from gris.utils import whatsapp_entrega
from gris.utils.whatsapp import ENTREGA_AGUARDANDO, ENTREGA_GRUPO
from gris.utils.whatsapp_errors import WhatsAppConfigurationError

CONFIG = {"url_api": "http://evolution.falsa", "api_key": "chave", "nome_instancia": "instancia"}


class TestEntregaPelosStatus(FrappeTestCase):
	def test_fica_com_o_status_mais_avancado(self):
		self.assertEqual(
			whatsapp_entrega.entrega_pelos_status(["SERVER_ACK", "READ", "DELIVERY_ACK"]), "Lida"
		)
		self.assertEqual(whatsapp_entrega.entrega_pelos_status(["PLAYED"]), "Lida")
		self.assertEqual(whatsapp_entrega.entrega_pelos_status(["SERVER_ACK", "DELIVERY_ACK"]), "Entregue")
		self.assertEqual(whatsapp_entrega.entrega_pelos_status(["ERROR"]), "Erro na entrega")

	def test_so_o_aceite_do_servidor_ainda_nao_diz_nada(self):
		self.assertIsNone(whatsapp_entrega.entrega_pelos_status(["SERVER_ACK"]))
		self.assertIsNone(whatsapp_entrega.entrega_pelos_status([]))


class TestConciliarEntregas(FrappeTestCase):
	def tearDown(self):
		# FrappeTestCase só desfaz por classe; sem isto as linhas vazam para o próximo teste.
		frappe.db.rollback()

	def _log(
		self,
		*,
		horas: float,
		id_mensagem: str = "",
		entrega: str = ENTREGA_AGUARDANDO,
		numero="5511999998888",
	):
		return frappe.get_doc(
			{
				"doctype": "Log de Mensagem",
				"enviada_em": now_datetime() - timedelta(hours=horas),
				"status": "Enviada",
				"destinatario_numero": numero,
				"conteudo": "Oi",
				"id_mensagem": id_mensagem,
				"entrega": entrega,
			}
		).insert(ignore_permissions=True)

	def _conciliar(self, status_por_id: dict | None = None, **kwargs):
		consultados: list[str] = []

		def _status(_config, id_mensagem):
			consultados.append(id_mensagem)
			if kwargs.get("falha"):
				raise ConnectionError("Evolution fora")
			return (status_por_id or {}).get(id_mensagem, [])

		with (
			patch.object(whatsapp_entrega, "_get_config", return_value=CONFIG),
			patch.object(whatsapp_entrega, "_status_na_evolution", side_effect=_status),
		):
			whatsapp_entrega.conciliar_entregas()
		return consultados

	def _entrega(self, doc) -> str:
		return frappe.db.get_value("Log de Mensagem", doc.name, "entrega")

	def test_entregue_e_lida(self):
		entregue = self._log(horas=1, id_mensagem="E2E-ENTREGUE")
		lida = self._log(horas=1, id_mensagem="E2E-LIDA")

		self._conciliar({"E2E-ENTREGUE": ["SERVER_ACK", "DELIVERY_ACK"], "E2E-LIDA": ["READ"]})

		self.assertEqual(self._entrega(entregue), "Entregue")
		self.assertEqual(self._entrega(lida), "Lida")
		self.assertTrue(frappe.db.get_value("Log de Mensagem", lida.name, "entrega_atualizada_em"))

	def test_sem_confirmacao_so_depois_de_um_dia(self):
		recente = self._log(horas=2, id_mensagem="E2E-RECENTE")
		antiga = self._log(horas=30, id_mensagem="E2E-ANTIGA")

		self._conciliar({"E2E-RECENTE": ["SERVER_ACK"], "E2E-ANTIGA": ["SERVER_ACK"]})

		self.assertEqual(self._entrega(recente), ENTREGA_AGUARDANDO)
		self.assertEqual(self._entrega(antiga), "Sem confirmação")

	def test_sem_confirmacao_ainda_pode_virar_entregue(self):
		"""Celular desligado por dois dias: a confirmação chega atrasada."""
		atrasada = self._log(horas=40, id_mensagem="E2E-ATRASADA", entrega="Sem confirmação")

		self._conciliar({"E2E-ATRASADA": ["DELIVERY_ACK"]})

		self.assertEqual(self._entrega(atrasada), "Entregue")

	def test_fora_da_janela_fecha_sem_consultar(self):
		velha = self._log(horas=100, id_mensagem="E2E-VELHA")

		consultados = self._conciliar()

		self.assertNotIn("E2E-VELHA", consultados)
		self.assertEqual(self._entrega(velha), "Sem confirmação")

	def test_grupo_e_linha_sem_id_nao_sao_consultados(self):
		grupo = self._log(horas=1, id_mensagem="E2E-GRUPO", entrega=ENTREGA_GRUPO, numero="1@g.us")
		self._log(horas=1)

		consultados = self._conciliar()

		self.assertNotIn("E2E-GRUPO", consultados)
		self.assertNotIn("", consultados)
		self.assertEqual(self._entrega(grupo), ENTREGA_GRUPO)

	def test_evolution_fora_interrompe_sem_mexer_nas_linhas(self):
		primeira = self._log(horas=30, id_mensagem="E2E-A")
		self._log(horas=29, id_mensagem="E2E-B")

		consultados = self._conciliar(falha=True)

		self.assertEqual(len([c for c in consultados if c.startswith("E2E-")]), 1)
		self.assertEqual(self._entrega(primeira), ENTREGA_AGUARDANDO)

	def test_integracao_desligada_nao_consulta(self):
		self._log(horas=1, id_mensagem="E2E-DESLIGADA")

		with (
			patch.object(whatsapp_entrega, "_get_config", side_effect=WhatsAppConfigurationError("off")),
			patch.object(whatsapp_entrega, "_status_na_evolution") as status,
		):
			whatsapp_entrega.conciliar_entregas()

		status.assert_not_called()

	def test_consulta_usa_o_id_no_find_status_message(self):
		with patch.object(
			whatsapp_entrega, "_post", return_value=[{"status": "DELIVERY_ACK"}, "lixo"]
		) as post:
			status = whatsapp_entrega._status_na_evolution(CONFIG, "ABC")

		self.assertEqual(status, ["DELIVERY_ACK"])
		self.assertEqual(post.call_args[0][0], "/chat/findStatusMessage/instancia")
		self.assertEqual(post.call_args[0][1], {"where": {"id": "ABC"}})
